"""Comprehensive test doubles library following UNIFIED_TESTING_GUIDE best practices.

This module provides reusable test doubles that:
- Have real behavior, not just mock returns
- Support proper Qt signal emission
- Are thread-safe where needed
- Test behavior, not implementation
"""

# This test file follows UNIFIED_TESTING_GUIDE best practices:
# - Test behavior, not implementation
# - Use test doubles instead of mocks
# - Real components where possible
# - Thread-safe testing patterns


# This test file follows UNIFIED_TESTING_GUIDE best practices:
# - Test behavior, not implementation
# - Use test doubles instead of mocks
# - Real components where possible
# - Thread-safe testing patterns


from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from PySide6.QtCore import QObject, QSize, QThread, Signal
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QWidget


# =============================================================================
# SUBPROCESS TEST DOUBLES
# =============================================================================

# Test doubles are defined below

class TestCompletedProcess:
    """Test double for subprocess.CompletedProcess."""
    __test__ = False  # Prevent pytest from collecting this as a test class
    
    def __init__(self, args: Union[str, List[str]], returncode: int = 0, stdout: str = "", stderr: str = ""):
        """Initialize test completed process."""
        self.args = args
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
    
    def check_returncode(self) -> None:
        """Raise CalledProcessError if return code is non-zero."""
        if self.returncode != 0:
            raise subprocess.CalledProcessError(self.returncode, self.args, self.stdout, self.stderr)


class TestSubprocess:
    """Test double for subprocess operations with configurable behavior.
    
    Replaces @patch("subprocess.Popen") anti-pattern with real behavior testing.
    """
    __test__ = False  # Prevent pytest from collecting this as a test class
    
    def __init__(self) -> None:
        """Initialize test subprocess handler."""
        self.executed_commands: List[Union[str, List[str]]] = []
        self.execution_history: List[Dict[str, Any]] = []
        self.return_code: int = 0
        self.stdout: str = ""
        self.stderr: str = ""
        self.side_effect: Optional[Exception] = None
        self.delay: float = 0.0  # Simulate execution time
        
        # For different commands, different outputs
        self.command_outputs: Dict[str, Tuple[int, str, str]] = {}
    
    def run(
        self,
        command: Union[str, List[str]],
        shell: bool = False,
        capture_output: bool = False,
        text: bool = False,
        check: bool = False,
        timeout: Optional[float] = None,
        **kwargs: Any
    ) -> TestCompletedProcess:
        """Simulate subprocess.run() with real behavior."""
        self.executed_commands.append(command)
        self.execution_history.append({
            "command": command,
            "shell": shell,
            "capture_output": capture_output,
            "text": text,
            "check": check,
            "timeout": timeout,
            "kwargs": kwargs,
            "timestamp": time.time()
        })
        
        # Simulate delay if configured
        if self.delay > 0:
            time.sleep(self.delay)
        
        # Raise exception if configured
        if self.side_effect:
            raise self.side_effect
        
        # Check for command-specific output
        cmd_str = command if isinstance(command, str) else " ".join(command)
        for pattern, output in self.command_outputs.items():
            if pattern in cmd_str:
                return_code, stdout, stderr = output
                result = TestCompletedProcess(command, return_code, stdout, stderr)
                if check:
                    result.check_returncode()
                return result
        
        # Default output
        result = TestCompletedProcess(command, self.return_code, self.stdout, self.stderr)
        if check:
            result.check_returncode()
        return result
    
    def Popen(
        self,
        command: Union[str, List[str]],
        shell: bool = False,
        stdout: Any = None,
        stderr: Any = None,
        **kwargs: Any
    ) -> PopenDouble:
        """Simulate subprocess.Popen() for process management."""
        self.executed_commands.append(command)
        return PopenDouble(command, self.return_code, self.stdout, self.stderr)
    
    def set_command_output(self, pattern: str, return_code: int = 0, stdout: str = "", stderr: str = "") -> None:
        """Set specific output for commands matching pattern."""
        self.command_outputs[pattern] = (return_code, stdout, stderr)
    
    def clear(self) -> None:
        """Clear execution history for fresh test."""
        self.executed_commands.clear()
        self.execution_history.clear()
        self.command_outputs.clear()
    
    def get_last_command(self) -> Optional[Union[str, List[str]]]:
        """Get the last executed command."""
        return self.executed_commands[-1] if self.executed_commands else None
    
    def was_called_with(self, pattern: str) -> bool:
        """Check if any command contained the pattern."""
        for cmd in self.executed_commands:
            cmd_str = cmd if isinstance(cmd, str) else " ".join(cmd)
            if pattern in cmd_str:
                return True
        return False


class PopenDouble:
    """Test double for subprocess.Popen."""
    
    def __init__(self, args: Union[str, List[str]], returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        """Initialize test process."""
        self.args = args
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.pid = 12345  # Fake PID
        self._terminated = False
        self._killed = False
    
    def poll(self) -> Optional[int]:
        """Check if process has terminated."""
        if self._terminated or self._killed:
            return self.returncode
        return None
    
    def wait(self, timeout: Optional[float] = None) -> int:
        """Wait for process to complete."""
        if timeout:
            time.sleep(min(timeout, 0.1))  # Simulate brief wait
        self._terminated = True
        return self.returncode
    
    def terminate(self) -> None:
        """Terminate the process."""
        self._terminated = True
    
    def kill(self) -> None:
        """Kill the process."""
        self._killed = True
    
    def communicate(self, input: Optional[bytes] = None, timeout: Optional[float] = None) -> Tuple[str, str]:
        """Communicate with process."""
        if timeout:
            time.sleep(min(timeout, 0.1))
        self._terminated = True
        return self.stdout, self.stderr


# =============================================================================
# SHOT AND MODEL TEST DOUBLES
# =============================================================================

@dataclass
class TestShot:
    """Test double for Shot objects with real behavior."""
    __test__ = False  # Prevent pytest from collecting this as a test class
    
    show: str = "test_show"
    sequence: str = "seq01"
    shot: str = "0010"
    workspace_path: Optional[str] = None
    name: Optional[str] = None
    
    def __post_init__(self) -> None:
        """Initialize computed fields."""
        if not self.workspace_path:
            self.workspace_path = f"/shows/{self.show}/shots/{self.sequence}/{self.sequence}_{self.shot}"
        if not self.name:
            self.name = f"{self.sequence}_{self.shot}"
    
    def get_thumbnail_path(self) -> Path:
        """Get path to thumbnail with real path construction."""
        return Path(self.workspace_path) / "publish" / "editorial" / "thumbnail.jpg"
    
    def get_plate_path(self) -> Path:
        """Get path to plate directory."""
        return Path(self.workspace_path) / "publish" / "plates"
    
    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary for serialization."""
        return {
            "show": self.show,
            "sequence": self.sequence,
            "shot": self.shot,
            "workspace_path": self.workspace_path,
            "name": self.name
        }


class TestShotModel(QObject):
    """Test double for ShotModel with real Qt signals."""
    __test__ = False  # Prevent pytest from collecting this as a test class
    
    # Real Qt signals for proper testing
    shots_updated = Signal()
    shot_selected = Signal(str)
    refresh_started = Signal()
    refresh_finished = Signal(bool)
    
    def __init__(self, parent: Optional[QObject] = None) -> None:
        """Initialize test shot model."""
        super().__init__(parent)
        self._shots: List[TestShot] = []
        self._selected_shot: Optional[TestShot] = None
        self.refresh_count = 0
        self.signal_emissions: Dict[str, int] = {
            "shots_updated": 0,
            "shot_selected": 0,
            "refresh_started": 0,
            "refresh_finished": 0
        }
        
        # Connect signals to track emissions
        self.shots_updated.connect(lambda: self._track_signal("shots_updated"))
        self.shot_selected.connect(lambda x: self._track_signal("shot_selected"))
        self.refresh_started.connect(lambda: self._track_signal("refresh_started"))
        self.refresh_finished.connect(lambda x: self._track_signal("refresh_finished"))
    
    def _track_signal(self, signal_name: str) -> None:
        """Track signal emissions for testing."""
        self.signal_emissions[signal_name] += 1
    
    def add_shot(self, shot: TestShot) -> None:
        """Add a shot and emit signal."""
        self._shots.append(shot)
        self.shots_updated.emit()
    
    def add_test_shots(self, shots: List[TestShot]) -> None:
        """Add multiple shots at once."""
        self._shots.extend(shots)
        self.shots_updated.emit()
    
    def get_shots(self) -> List[TestShot]:
        """Get all shots."""
        return self._shots.copy()
    
    @property
    def shots(self) -> List[TestShot]:
        """Get all shots as property for compatibility with ShotGrid."""
        return self._shots.copy()
    
    def get_shot_by_name(self, name: str) -> Optional[TestShot]:
        """Find shot by name."""
        for shot in self._shots:
            if shot.name == name:
                return shot
        return None
    
    def refresh_shots(self) -> Tuple[bool, bool]:
        """Simulate shot refresh with configurable behavior."""
        self.refresh_count += 1
        self.refresh_started.emit()
        
        # Simulate some work
        time.sleep(0.01)
        
        # Determine if there are changes
        has_changes = self.refresh_count == 1 or len(self._shots) == 0
        
        if has_changes and self.refresh_count == 1:
            # Add default test shots on first refresh
            self.add_test_shots([
                TestShot("show1", "seq01", "0010"),
                TestShot("show1", "seq01", "0020"),
                TestShot("show1", "seq02", "0030")
            ])
        
        self.refresh_finished.emit(True)
        return (True, has_changes)
    
    def select_shot(self, shot: Union[TestShot, str]) -> None:
        """Select a shot and emit signal."""
        if isinstance(shot, str):
            shot = self.get_shot_by_name(shot)
        if shot:
            self._selected_shot = shot
            self.shot_selected.emit(shot.name)
    
    def clear(self) -> None:
        """Clear all shots."""
        self._shots.clear()
        self._selected_shot = None
        self.shots_updated.emit()


# =============================================================================
# CACHE TEST DOUBLES
# =============================================================================

class TestCacheManager(QObject):
    """Test double for CacheManager with real behavior."""
    __test__ = False  # Prevent pytest from collecting this as a test class
    
    cache_updated = Signal()
    thumbnail_cached = Signal(str)
    
    def __init__(self, cache_dir: Optional[Path] = None) -> None:
        """Initialize test cache manager."""
        super().__init__()
        self.cache_dir = cache_dir or Path("/tmp/test_cache")
        self._cached_thumbnails: Dict[str, Path] = {}
        self._cached_shots: List[TestShot] = []
        self._memory_usage_bytes: int = 0
        self._cache_operations: List[Dict[str, Any]] = []
    
    def cache_thumbnail(
        self,
        source_path: Union[str, Path],
        show: str,
        sequence: str,
        shot: str,
        wait: bool = True
    ) -> Optional[Path]:
        """Cache a thumbnail with real behavior."""
        source = Path(source_path)
        cache_key = f"{show}_{sequence}_{shot}"
        
        # Record operation
        self._cache_operations.append({
            "operation": "cache_thumbnail",
            "source": str(source),
            "key": cache_key,
            "timestamp": time.time()
        })
        
        # Simulate caching
        cached_path = self.cache_dir / "thumbnails" / show / sequence / f"{shot}.jpg"
        cached_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Simulate file copy (just track it)
        self._cached_thumbnails[cache_key] = cached_path
        self._memory_usage_bytes += 50000  # Simulate 50KB thumbnail
        
        self.thumbnail_cached.emit(cache_key)
        self.cache_updated.emit()
        
        return cached_path
    
    def get_cached_thumbnail(self, show: str, sequence: str, shot: str) -> Optional[Path]:
        """Get cached thumbnail path."""
        cache_key = f"{show}_{sequence}_{shot}"
        return self._cached_thumbnails.get(cache_key)
    
    def cache_shots(self, shots: List[Union[TestShot, Dict[str, str]]]) -> bool:
        """Cache shot data."""
        self._cached_shots.clear()
        for shot in shots:
            if isinstance(shot, dict):
                shot = TestShot(**shot)
            self._cached_shots.append(shot)
        self.cache_updated.emit()
        return True
    
    def get_cached_shots(self) -> List[TestShot]:
        """Get cached shots."""
        return self._cached_shots.copy()
    
    def get_memory_usage(self) -> Dict[str, Any]:
        """Get memory usage statistics."""
        return {
            "total_mb": self._memory_usage_bytes / (1024 * 1024),
            "thumbnail_count": len(self._cached_thumbnails),
            "shot_count": len(self._cached_shots)
        }
    
    def clear_cache(self) -> None:
        """Clear all caches."""
        self._cached_thumbnails.clear()
        self._cached_shots.clear()
        self._memory_usage_bytes = 0
        self._cache_operations.clear()
        self.cache_updated.emit()
    
    def validate_cache(self) -> Dict[str, Any]:
        """Validate cache integrity."""
        return {
            "valid": True,
            "orphaned_files": 0,
            "missing_files": 0,
            "invalid_entries": 0,
            "issues_found": 0,
            "issues_fixed": 0
        }


# =============================================================================
# LAUNCHER TEST DOUBLES
# =============================================================================

class TestLauncherEnvironment:
    """Test double for launcher environment."""
    __test__ = False  # Prevent pytest from collecting this as a test class
    
    def __init__(self, type: str = "none", packages: List[str] = None, command_prefix: str = ""):
        self.type = type
        self.packages = packages or []
        self.command_prefix = command_prefix


class TestLauncherTerminal:
    """Test double for launcher terminal settings."""
    __test__ = False  # Prevent pytest from collecting this as a test class
    
    def __init__(self, persist: bool = False):
        self.persist = persist


class TestLauncher:
    """Test double for launcher configuration."""
    __test__ = False  # Prevent pytest from collecting this as a test class
    
    def __init__(
        self,
        id: str = "test_launcher",
        name: str = "Test Launcher",
        command: str = "echo {shot_name}",
        description: str = "Test launcher",
        category: str = "test",
        enabled: bool = True,
        environment = None,
        terminal = None
    ) -> None:
        """Initialize test launcher."""
        self.id = id
        self.name = name
        self.command = command
        self.description = description
        self.category = category
        self.enabled = enabled
        self.environment = environment or TestLauncherEnvironment()
        self.terminal = terminal or TestLauncherTerminal()
        self.execution_count = 0
        self.last_execution_args: Optional[Dict[str, str]] = None
    
    def execute(self, **kwargs: str) -> bool:
        """Simulate launcher execution."""
        self.execution_count += 1
        self.last_execution_args = kwargs
        return True


class LauncherManagerDouble(QObject):
    """Test double for LauncherManager with real signals."""
    
    launcher_added = Signal(str)
    launcher_removed = Signal(str)
    launcher_executed = Signal(str)
    execution_started = Signal(str)
    execution_finished = Signal(str, bool)
    launchers_changed = Signal()
    
    def __init__(self) -> None:
        """Initialize test launcher manager."""
        super().__init__()
        self._launchers: Dict[str, TestLauncher] = {}
        self._execution_history: List[Dict[str, Any]] = []
        self._validation_results: Dict[str, Tuple[bool, Optional[str]]] = {}
        self._test_command: Optional[str] = None  # For temporary test launchers
    
    def validate_command_syntax(self, command: str) -> Tuple[bool, Optional[str]]:
        """Validate command syntax with real behavior."""
        if not command or not command.strip():
            return (False, "Command cannot be empty")
        
        # Check for basic syntax issues
        if command.startswith('{') and not command.endswith('}'):
            return (False, "Unclosed variable substitution")
        
        # Allow override for testing specific scenarios
        if command in self._validation_results:
            return self._validation_results[command]
        
        return (True, None)
    
    def set_validation_result(self, command: str, is_valid: bool, error: Optional[str] = None) -> None:
        """Set custom validation result for testing."""
        self._validation_results[command] = (is_valid, error)
    
    def set_test_command(self, command: str) -> None:
        """Set command for temporary test launcher."""
        self._test_command = command
    
    def get_launcher_by_name(self, name: str) -> Optional[TestLauncher]:
        """Find launcher by name with real search behavior."""
        for launcher in self._launchers.values():
            if launcher.name == name:
                return launcher
        return None
    
    def create_launcher(
        self,
        name: str,
        command: str,
        description: str = "",
        category: str = "custom",
        environment = None,
        terminal = None
    ) -> Optional[str]:
        """Create a test launcher with real behavior."""
        # Check for duplicate names
        if self.get_launcher_by_name(name):
            return None  # Simulate creation failure
        
        launcher_id = f"launcher_{len(self._launchers)}"
        launcher = TestLauncher(launcher_id, name, command, description, category)
        self._launchers[launcher_id] = launcher
        self.launcher_added.emit(launcher_id)
        self.launchers_changed.emit()
        return launcher_id
    
    def update_launcher(
        self,
        launcher_id: str,
        name: str = None,
        command: str = None,
        description: str = None,
        category: str = None,
        environment = None,
        terminal = None
    ) -> bool:
        """Update existing launcher with real behavior."""
        if launcher_id not in self._launchers:
            return False
        
        launcher = self._launchers[launcher_id]
        
        # Check for name conflicts (excluding self)
        if name and name != launcher.name:
            existing = self.get_launcher_by_name(name)
            if existing and existing.id != launcher_id:
                return False
        
        # Apply updates
        if name is not None:
            launcher.name = name
        if command is not None:
            launcher.command = command
        if description is not None:
            launcher.description = description
        if category is not None:
            launcher.category = category
        
        self.launchers_changed.emit()
        return True
    
    def delete_launcher(self, launcher_id: str) -> bool:
        """Delete launcher with real behavior."""
        if launcher_id not in self._launchers:
            return False
        
        del self._launchers[launcher_id]
        self.launcher_removed.emit(launcher_id)
        self.launchers_changed.emit()
        return True
    
    def execute_launcher(
        self, 
        launcher_id_or_launcher, 
        custom_vars: Optional[Dict[str, str]] = None, 
        dry_run: bool = False
    ) -> bool:
        """Execute a launcher with real behavior."""
        # Handle both launcher_id string and launcher object
        if hasattr(launcher_id_or_launcher, 'id'):
            # It's a launcher object
            launcher_obj = launcher_id_or_launcher
            launcher_id = launcher_obj.id
            if launcher_id not in self._launchers:
                # For test launcher objects, add temporarily
                self._launchers[launcher_id] = launcher_obj
        elif isinstance(launcher_id_or_launcher, str):
            # It's a launcher_id string
            launcher_id = launcher_id_or_launcher
        else:
            # Unsupported type
            raise ValueError(f"Expected launcher object or launcher_id string, got {type(launcher_id_or_launcher)}")
        
        if launcher_id not in self._launchers:
            # For test scenarios, create a temporary launcher if it doesn't exist
            if launcher_id == "test":
                command = self._test_command or "echo test"
                temp_launcher = TestLauncher(
                    id=launcher_id,
                    name="Temporary Test Launcher", 
                    command=command
                )
                self._launchers[launcher_id] = temp_launcher
            else:
                return False
        
        launcher = self._launchers[launcher_id]
        
        if not dry_run:
            self.execution_started.emit(launcher_id)
        
        # Record execution
        self._execution_history.append({
            "launcher_id": launcher_id,
            "custom_vars": custom_vars,
            "dry_run": dry_run,
            "timestamp": time.time()
        })
        
        # Simulate execution (always succeeds unless command has issues)
        success = not launcher.command.startswith("bad")  # Simple failure simulation
        
        if not success:
            # Simulate execution failure with an exception
            raise RuntimeError(f"Command execution failed: {launcher.command}")
        
        if not dry_run:
            self.launcher_executed.emit(launcher_id)
            self.execution_finished.emit(launcher_id, success)
        
        return success
    
    def list_launchers(self) -> List[TestLauncher]:
        """List all launchers."""
        return list(self._launchers.values())
    
    def get_launcher(self, launcher_id: str) -> Optional[TestLauncher]:
        """Get specific launcher."""
        return self._launchers.get(launcher_id)
    
    def was_dry_run_executed(self) -> bool:
        """Check if any dry run was executed (for testing)."""
        return any(entry.get("dry_run", False) for entry in self._execution_history)
    
    def get_created_launcher_count(self) -> int:
        """Get number of launchers created (for testing)."""
        return len(self._launchers)
    
    def get_last_created_launcher(self) -> Optional[TestLauncher]:
        """Get the most recently created launcher (for testing)."""
        if not self._launchers:
            return None
        # Return the launcher with highest ID number (most recent)
        return max(self._launchers.values(), key=lambda l: int(l.id.split('_')[-1]))


# =============================================================================
# WORKER TEST DOUBLES
# =============================================================================

class TestWorker(QThread):
    """Test double for worker threads with real Qt signals."""
    __test__ = False  # Prevent pytest from collecting this as a test class
    
    # Real signals for testing
    started = Signal()
    finished = Signal(str)
    progress = Signal(int)
    error = Signal(str)
    result_ready = Signal(object)
    
    def __init__(self, parent: Optional[QObject] = None) -> None:
        """Initialize test worker."""
        super().__init__(parent)
        self.test_result: Any = "success"
        self.test_error: Optional[str] = None
        self.progress_values: List[int] = [25, 50, 75, 100]
        self.execution_time: float = 0.01  # Fast for tests
        self.was_started = False
        self.was_stopped = False
    
    def set_test_result(self, result: Any) -> None:
        """Set the result that will be emitted."""
        self.test_result = result
    
    def set_test_error(self, error: str) -> None:
        """Set an error to be emitted."""
        self.test_error = error
    
    def run(self) -> None:
        """Run the worker thread."""
        self.was_started = True
        self.started.emit()
        
        # Simulate work with progress
        for progress_value in self.progress_values:
            if self.isInterruptionRequested():
                self.was_stopped = True
                break
            time.sleep(self.execution_time / len(self.progress_values))
            self.progress.emit(progress_value)
        
        # Emit result or error
        if self.test_error:
            self.error.emit(self.test_error)
            self.finished.emit("error")
        else:
            self.result_ready.emit(self.test_result)
            self.finished.emit("success")
    
    def stop(self) -> None:
        """Stop the worker."""
        self.requestInterruption()
        self.wait(1000)  # Wait up to 1 second
        self.was_stopped = True


# =============================================================================
# QT WIDGET TEST DOUBLES
# =============================================================================

class ThreadSafeTestImage:
    """Thread-safe test double for QPixmap using QImage internally.
    
    Critical for avoiding Qt threading violations in tests.
    QPixmap is NOT thread-safe and causes fatal errors in worker threads.
    QImage IS thread-safe and should be used instead.
    """
    
    def __init__(self, width: int = 100, height: int = 100) -> None:
        """Create a thread-safe test image."""
        # Use QImage which is thread-safe, unlike QPixmap
        self._image = QImage(width, height, QImage.Format.Format_RGB32)
        self._width = width
        self._height = height
        self._image.fill(QColor(255, 255, 255))  # White by default
    
    def fill(self, color: Optional[QColor] = None) -> None:
        """Fill the image with a color."""
        if color is None:
            color = QColor(255, 255, 255)
        self._image.fill(color)
    
    def scaled(self, width: int, height: int) -> 'ThreadSafeTestImage':
        """Scale the image."""
        new_image = ThreadSafeTestImage(width, height)
        new_image._image = self._image.scaled(width, height)
        return new_image
    
    def size(self) -> Tuple[int, int]:
        """Get image size as tuple."""
        return (self._width, self._height)
    
    def save(self, path: Union[str, Path]) -> bool:
        """Save image to file."""
        return self._image.save(str(path))
    
    def isNull(self) -> bool:
        """Check if image is null."""
        return self._image.isNull()
    
    def sizeInBytes(self) -> int:
        """Get size in bytes."""
        return self._image.sizeInBytes()


class TestPILImage:
    """Test double for PIL Image with real behavior."""
    __test__ = False  # Prevent pytest from collecting this as a test class
    
    def __init__(self, width: int = 100, height: int = 100, mode: str = "RGB") -> None:
        """Create a test PIL image."""
        self.size = (width, height)
        self.mode = mode
        self._width = width
        self._height = height
        self._thumbnail_called = False
        self._thumbnail_size = None
        
    def thumbnail(self, size: Tuple[int, int], resample=None) -> None:
        """Simulate thumbnail operation."""
        self._thumbnail_called = True
        self._thumbnail_size = size
        # Simulate thumbnail resizing by updating size
        self.size = (min(self._width, size[0]), min(self._height, size[1]))
        
    def save(self, path: Union[str, Path], format: Optional[str] = None) -> None:
        """Simulate saving the image."""
        # Test double: just record that save was called
        pass
        
    def convert(self, mode: str) -> 'TestPILImage':
        """Convert image mode."""
        new_image = TestPILImage(self._width, self._height, mode)
        new_image._thumbnail_called = self._thumbnail_called
        new_image._thumbnail_size = self._thumbnail_size
        return new_image
        
    def was_thumbnail_called(self) -> bool:
        """Check if thumbnail method was called (for testing)."""
        return self._thumbnail_called
        
    def get_thumbnail_size(self) -> Optional[Tuple[int, int]]:
        """Get the thumbnail size that was requested (for testing)."""
        return self._thumbnail_size


class SignalDouble:
    """Test double for signals when not using real Qt objects."""
    
    def __init__(self) -> None:
        """Initialize test signal."""
        self.emissions: List[Tuple[Any, ...]] = []
        self.callbacks: List[Callable] = []
        self.emit_count = 0
        self.was_emitted = False
        self.last_emission: Optional[Tuple[Any, ...]] = None
    
    def emit(self, *args: Any) -> None:
        """Emit the signal."""
        self.emissions.append(args)
        self.emit_count += 1
        self.was_emitted = True
        self.last_emission = args
        
        # Call connected callbacks
        for callback in self.callbacks:
            callback(*args)
    
    def connect(self, callback: Callable) -> None:
        """Connect a callback."""
        self.callbacks.append(callback)
    
    def disconnect(self, callback: Optional[Callable] = None) -> None:
        """Disconnect callback(s)."""
        if callback:
            if callback in self.callbacks:
                self.callbacks.remove(callback)
        else:
            self.callbacks.clear()
    
    def reset(self) -> None:
        """Reset emission tracking."""
        self.emissions.clear()
        self.emit_count = 0
        self.was_emitted = False
        self.last_emission = None


# =============================================================================
# PROCESS POOL TEST DOUBLE
# =============================================================================

class TestProcessPool:
    """Test double for process pool with configurable outputs."""
    __test__ = False  # Prevent pytest from collecting this as a test class
    
    def __init__(self) -> None:
        """Initialize test process pool."""
        self.commands: List[str] = []
        self.outputs: List[str] = []
        self.current_output_index = 0
        self.default_output = "workspace /test/path"
        self._cache: Dict[str, Any] = {}  # Cache for commands
    
    def execute_workspace_command(self, command: str, **kwargs: Any) -> str:
        """Execute workspace command with test output."""
        self.commands.append(command)
        
        if self.outputs and self.current_output_index < len(self.outputs):
            output = self.outputs[self.current_output_index]
            self.current_output_index += 1
            return output
        
        return self.default_output
    
    def set_outputs(self, *outputs: str) -> None:
        """Set outputs for subsequent calls."""
        self.outputs = list(outputs)
        self.current_output_index = 0
    
    def reset(self) -> None:
        """Reset for fresh test."""
        self.commands.clear()
        self.outputs.clear()
        self.current_output_index = 0
    
    def invalidate_cache(self, command: str) -> None:
        """Invalidate cache for a command (test double behavior)."""
        # Test double: track invalidation and clear from cache
        self.commands.append(f"invalidate_cache:{command}")
        if command in self._cache:
            del self._cache[command]


class TestBashSession:
    """Test double for PersistentBashSession with real behavior."""
    __test__ = False  # Prevent pytest from collecting this as a test class
    
    def __init__(self) -> None:
        """Initialize test bash session."""
        self.executed_commands: List[str] = []
        self.command_outputs: Dict[str, str] = {}
        self.default_output = "test output"
        self.side_effect: Optional[Exception] = None
        self._current_output_index = 0
        self._output_sequence: List[str] = []
        
    def execute(self, command: str, timeout: float = 30.0) -> str:
        """Execute a command and return test output."""
        self.executed_commands.append(command)
        
        # Raise exception if configured
        if self.side_effect:
            raise self.side_effect
            
        # Check for specific command outputs
        for pattern, output in self.command_outputs.items():
            if pattern in command:
                return output
        
        # Use sequence outputs if configured
        if self._output_sequence and self._current_output_index < len(self._output_sequence):
            output = self._output_sequence[self._current_output_index]
            self._current_output_index += 1
            return output
            
        return self.default_output
        
    def set_command_output(self, pattern: str, output: str) -> None:
        """Set output for commands matching pattern."""
        self.command_outputs[pattern] = output
        
    def set_output_sequence(self, outputs: List[str]) -> None:
        """Set sequence of outputs for subsequent calls."""
        self._output_sequence = outputs
        self._current_output_index = 0
        
    def set_side_effect(self, exception: Exception) -> None:
        """Set exception to be raised."""
        self.side_effect = exception
        
    def shutdown(self) -> None:
        """Simulate session shutdown."""
        pass
        
    def was_command_executed(self, pattern: str) -> bool:
        """Check if any command contained the pattern."""
        return any(pattern in cmd for cmd in self.executed_commands)
        
    def get_executed_commands(self) -> List[str]:
        """Get all executed commands."""
        return self.executed_commands.copy()
        
    def reset(self) -> None:
        """Reset for fresh test."""
        self.executed_commands.clear()
        self.command_outputs.clear()
        self._output_sequence.clear()
        self._current_output_index = 0
        self.side_effect = None


# =============================================================================
# PROGRESS MANAGER TEST DOUBLES
# =============================================================================

class TestProgressOperation:
    """Test double for ProgressOperation with real behavior."""
    __test__ = False  # Prevent pytest from collecting this as a test class
    
    def __init__(self, title: str = "Test Operation", cancelable: bool = False):
        """Initialize test progress operation."""
        self.title = title
        self.cancelable = cancelable
        self.current_value = 0
        self.total_value = 0
        self.is_indeterminate = True
        self.is_cancelled_flag = False
        self.current_message = title
        self.start_time = time.time()
        self.last_update_time = 0.0
        
    def set_total(self, total: int) -> None:
        """Set the total number of steps for determinate progress."""
        self.total_value = total
        self.is_indeterminate = False
        
    def set_indeterminate(self) -> None:
        """Set progress to indeterminate mode (spinner)."""
        self.is_indeterminate = True
        
    def update(self, value: int, message: str = "") -> None:
        """Update progress value and optional message."""
        self.current_value = value
        if message:
            self.current_message = message
        self.last_update_time = time.time()
        
    def is_cancelled(self) -> bool:
        """Check if the operation has been cancelled."""
        return self.is_cancelled_flag
        
    def cancel(self) -> None:
        """Cancel the operation and trigger cleanup."""
        self.is_cancelled_flag = True
        
    def get_eta_string(self) -> str:
        """Calculate and return ETA string."""
        if self.is_indeterminate or self.total_value == 0:
            return "Unknown"
        elapsed = time.time() - self.start_time
        if self.current_value == 0:
            return "Unknown"
        remaining = (self.total_value - self.current_value) * elapsed / self.current_value
        return f"{remaining:.0f}s"


class TestProgressManager:
    """Test double for ProgressManager with static methods."""
    __test__ = False  # Prevent pytest from collecting this as a test class
    
    _current_operation: Optional[TestProgressOperation] = None
    _operations_started: List[TestProgressOperation] = []
    _operations_finished: List[Dict[str, Any]] = []
    
    @classmethod
    def start_operation(cls, config) -> TestProgressOperation:
        """Start a new progress operation."""
        if isinstance(config, str):
            operation = TestProgressOperation(title=config)
        else:
            # Handle config object
            title = getattr(config, 'title', 'Test Operation')
            cancelable = getattr(config, 'cancelable', False)
            operation = TestProgressOperation(title=title, cancelable=cancelable)
        
        cls._current_operation = operation
        cls._operations_started.append(operation)
        return operation
        
    @classmethod
    def finish_operation(cls, success: bool = True, error_message: str = "") -> None:
        """Finish the current progress operation."""
        if cls._current_operation:
            cls._operations_finished.append({
                'operation': cls._current_operation,
                'success': success,
                'error_message': error_message,
                'timestamp': time.time()
            })
            cls._current_operation = None
            
    @classmethod
    def get_current_operation(cls) -> Optional[TestProgressOperation]:
        """Get the current progress operation."""
        return cls._current_operation
        
    @classmethod
    def clear_all_operations(cls) -> None:
        """Clear all operations for testing."""
        cls._current_operation = None
        cls._operations_started.clear()
        cls._operations_finished.clear()
        
    @classmethod
    def get_operations_started_count(cls) -> int:
        """Get number of operations started (for testing)."""
        return len(cls._operations_started)
        
    @classmethod
    def get_operations_finished_count(cls) -> int:
        """Get number of operations finished (for testing)."""
        return len(cls._operations_finished)


# =============================================================================
# EXPORT ALL TEST DOUBLES
# =============================================================================

__all__ = [
    # Subprocess
    'TestSubprocess',
    'PopenDouble',
    'TestCompletedProcess',
    
    # Models
    'TestShot',
    'TestShotModel',
    
    # Cache
    'TestCacheManager',
    
    # Launchers
    'TestLauncher',
    'TestLauncherEnvironment', 
    'TestLauncherTerminal',
    'LauncherManagerDouble',
    
    # Workers
    'TestWorker',
    
    # Qt/Threading
    'ThreadSafeTestImage',
    'TestPILImage',
    'SignalDouble',
    
    # Process Pool
    'TestProcessPool',
    'TestBashSession',
    
    # Progress Manager
    'TestProgressOperation',
    'TestProgressManager',
]