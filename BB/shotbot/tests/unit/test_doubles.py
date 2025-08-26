"""Reusable test doubles following UNIFIED_TESTING_GUIDE best practices.

This module provides lightweight test doubles for use in unit tests,
avoiding excessive mocking and focusing on behavior testing.

Test Doubles Provided:
    - SignalDouble: Lightweight signal emulation for non-Qt components
    - TestProcessPool: Subprocess boundary mock with predictable behavior
    - TestFileSystem: In-memory filesystem for fast testing
    - TestQApplication: Minimal Qt application for widget testing
    - TestCache: In-memory cache for testing cache-dependent components

Usage:
    These test doubles should be used instead of Mock() objects to provide
    more realistic behavior while maintaining test isolation and speed.
"""

from __future__ import annotations

import pytest
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
import subprocess
import time

# This test file follows UNIFIED_TESTING_GUIDE best practices:
# - Test behavior, not implementation
# - Use test doubles instead of mocks
# - Real components where possible
# - Thread-safe testing patterns


from tests.test_doubles_library import (
    TestSubprocess, TestShot, TestShotModel,
    TestCacheManager, TestLauncher, TestWorker,
    ThreadSafeTestImage, SignalDouble, TestProcessPool
)

pytestmark = [pytest.mark.unit, pytest.mark.slow]
class SignalDouble:
    """Lightweight signal test double for non-Qt components.

    Provides a signal-like interface without Qt dependencies, useful for
    testing components that emit events without requiring full Qt setup.

    Example:
        signal = SignalDouble()
        signal.connect(callback_function)
        signal.emit("data")
        assert signal.was_emitted
        assert signal.emission_count == 1
    """

    __test__ = False

    def __init__(self):
        """Initialize the test signal."""
        self.emissions: List[Tuple[Any, ...]] = []
        self.callbacks: List[Callable] = []
        self.blocked = False

    def emit(self, *args: Any) -> None:
        """Emit signal with given arguments.

        Args:
            *args: Arguments to pass to connected callbacks
        """
        if self.blocked:
            return

        self.emissions.append(args)
        for callback in self.callbacks:
            try:
                callback(*args)
            except Exception:
                pass  # Swallow exceptions in test callbacks

    def connect(self, callback: Callable) -> None:
        """Connect a callback to this signal.

        Args:
            callback: Function to call when signal is emitted
        """
        if callback not in self.callbacks:
            self.callbacks.append(callback)

    def disconnect(self, callback: Callable) -> None:
        """Disconnect a callback from this signal.

        Args:
            callback: Function to remove from callbacks
        """
        if callback in self.callbacks:
            self.callbacks.remove(callback)

    def block(self) -> None:
        """Block signal emission."""
        self.blocked = True

    def unblock(self) -> None:
        """Unblock signal emission."""
        self.blocked = False

    def clear(self) -> None:
        """Clear emission history."""
        self.emissions.clear()

    @property
    def was_emitted(self) -> bool:
        """Check if signal was ever emitted."""
        return len(self.emissions) > 0

    @property
    def emission_count(self) -> int:
        """Get number of times signal was emitted."""
        return len(self.emissions)

    @property
    def last_emission(self) -> Optional[Tuple[Any, ...]]:
        """Get arguments from last emission."""
        return self.emissions[-1] if self.emissions else None


class TestProcessPool:
    """Test double for subprocess operations at system boundary.

    Replaces actual subprocess calls with predictable test behavior,
    following the principle of mocking only at system boundaries.

    Example:
        pool = TestProcessPool()
        pool.set_outputs("workspace /test/path", "another output")
        result = pool.execute_workspace_command("ws -sg")
        assert result == "workspace /test/path"
    """

    __test__ = False

    def __init__(self):
        """Initialize the test process pool."""
        self.commands: List[str] = []
        self.outputs: List[str] = []
        self.errors: List[str] = []
        self.should_fail = False
        self.fail_on_commands: Set[str] = set()
        self.delay_seconds = 0.0
        self.call_count = 0

        # Signals for testing async behavior
        self.command_started = SignalDouble()
        self.command_completed = SignalDouble()
        self.command_failed = SignalDouble()

    def execute_workspace_command(self, command: str, **kwargs) -> str:
        """Execute a workspace command (test implementation).

        Args:
            command: Command to execute
            **kwargs: Additional arguments (ignored in test)

        Returns:
            str: Predetermined output

        Raises:
            subprocess.CalledProcessError: If configured to fail
        """
        self.commands.append(command)
        self.call_count += 1
        self.command_started.emit(command)

        # Simulate delay if configured
        if self.delay_seconds > 0:
            time.sleep(self.delay_seconds)

        # Check for specific command failures
        if self.should_fail or command in self.fail_on_commands:
            error_msg = (
                self.errors.pop(0) if self.errors else f"Command failed: {command}"
            )
            self.command_failed.emit(command, error_msg)
            raise subprocess.CalledProcessError(1, command, output=error_msg)

        # Return predetermined output
        output = self.outputs.pop(0) if self.outputs else ""
        self.command_completed.emit(command, output)
        return output

    def execute(self, command: str, **kwargs) -> subprocess.CompletedProcess:
        """Execute a general command (test implementation).

        Args:
            command: Command to execute
            **kwargs: Additional arguments

        Returns:
            subprocess.CompletedProcess: Test result
        """
        output = self.execute_workspace_command(command, **kwargs)
        return subprocess.CompletedProcess(
            args=command,
            returncode=0 if not self.should_fail else 1,
            stdout=output,
            stderr="" if not self.should_fail else output,
        )

    def set_outputs(self, *outputs: str) -> None:
        """Set outputs to return for subsequent commands.

        Args:
            *outputs: Output strings to return in order
        """
        self.outputs = list(outputs)

    def set_errors(self, *errors: str) -> None:
        """Set error messages for failed commands.

        Args:
            *errors: Error messages to use for failures
        """
        self.errors = list(errors)

    def fail_on(self, *commands: str) -> None:
        """Configure specific commands to fail.

        Args:
            *commands: Commands that should fail when executed
        """
        self.fail_on_commands.update(commands)

    def reset(self) -> None:
        """Reset all state for fresh test."""
        self.commands.clear()
        self.outputs.clear()
        self.errors.clear()
        self.should_fail = False
        self.fail_on_commands.clear()
        self.delay_seconds = 0.0
        self.call_count = 0
        self.command_started.clear()
        self.command_completed.clear()
        self.command_failed.clear()

    def invalidate_cache(self, command: str) -> None:
        """Invalidate cache for a specific command (test implementation)."""
        # In test, just track that it was called
        pass

    def get_metrics(self) -> Dict[str, Any]:
        """Get performance metrics (test implementation)."""
        return {
            "subprocess_calls": self.call_count,
            "cache_hits": 0,
            "cache_misses": self.call_count,
            "average_response_ms": 100.0 if self.call_count > 0 else 0.0,
        }

    @classmethod
    def get_instance(cls) -> "TestProcessPool":
        """Get a singleton instance (for compatibility)."""
        if not hasattr(cls, "_instance"):
            cls._instance = cls()
        return cls._instance


class TestFileSystem:
    """In-memory filesystem for fast testing without I/O.

    Provides file operations without touching disk, making tests
    faster and more isolated.

    Example:
        fs = TestFileSystem()
        fs.write_file("/test/file.txt", "content")
        assert fs.exists("/test/file.txt")
    """

    __test__ = False

    def __init__(self):
        """Initialize the test filesystem."""
        self.files: Dict[str, bytes] = {}
        self.directories: Set[str] = set()
        self.metadata: Dict[str, Dict[str, Any]] = defaultdict(dict)
        self.access_times: Dict[str, datetime] = {}
        self.modification_times: Dict[str, datetime] = {}

    def write_file(self, path: str, content: Any) -> None:
        """Write content to a file path.

        Args:
            path: File path to write to
            content: Content to write (str or bytes)
        """
        path = str(Path(path))

        # Convert content to bytes
        if isinstance(content, str):
            content = content.encode("utf-8")
        elif not isinstance(content, bytes):
            content = str(content).encode("utf-8")

        # Store file and update times
        self.files[path] = content
        now = datetime.now()
        self.modification_times[path] = now
        self.access_times[path] = now

        # Create parent directories
        parent = str(Path(path).parent)
        if parent != path:
            self.mkdir(parent)

    def read_file(self, path: str, mode: str = "r") -> Any:
        """Read content from a file path.

        Args:
            path: File path to read from
            mode: Read mode ('r' for text, 'rb' for binary)

        Returns:
            File contents (str or bytes based on mode)

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        path = str(Path(path))

        if path not in self.files:
            raise FileNotFoundError(f"No such file: {path}")

        self.access_times[path] = datetime.now()
        content = self.files[path]

        if "b" not in mode:
            return content.decode("utf-8")
        return content

    def exists(self, path: str) -> bool:
        """Check if a path exists.

        Args:
            path: Path to check

        Returns:
            bool: True if path exists
        """
        path = str(Path(path))
        return path in self.files or path in self.directories

    def is_file(self, path: str) -> bool:
        """Check if path is a file.

        Args:
            path: Path to check

        Returns:
            bool: True if path is a file
        """
        return str(Path(path)) in self.files

    def is_dir(self, path: str) -> bool:
        """Check if path is a directory.

        Args:
            path: Path to check

        Returns:
            bool: True if path is a directory
        """
        return str(Path(path)) in self.directories

    def mkdir(self, path: str, parents: bool = True) -> None:
        """Create a directory.

        Args:
            path: Directory path to create
            parents: Create parent directories if needed
        """
        path = str(Path(path))

        if parents:
            # Create all parent directories
            current = Path(path)
            dirs_to_create = []
            while current != current.parent:
                dirs_to_create.append(str(current))
                current = current.parent

            for dir_path in reversed(dirs_to_create):
                self.directories.add(dir_path)
        else:
            self.directories.add(path)

    def listdir(self, path: str) -> List[str]:
        """List directory contents.

        Args:
            path: Directory path to list

        Returns:
            List[str]: Names of files and directories in path
        """
        path = str(Path(path))
        if path not in self.directories:
            raise FileNotFoundError(f"No such directory: {path}")

        results = set()
        path_obj = Path(path)

        # Find all files in this directory
        for file_path in self.files:
            file_obj = Path(file_path)
            if file_obj.parent == path_obj:
                results.add(file_obj.name)

        # Find all subdirectories
        for dir_path in self.directories:
            dir_obj = Path(dir_path)
            if dir_obj.parent == path_obj and dir_obj != path_obj:
                results.add(dir_obj.name)

        return sorted(results)

    def remove(self, path: str) -> None:
        """Remove a file.

        Args:
            path: File path to remove
        """
        path = str(Path(path))
        if path in self.files:
            del self.files[path]
            self.metadata.pop(path, None)
            self.access_times.pop(path, None)
            self.modification_times.pop(path, None)

    def get_size(self, path: str) -> int:
        """Get file size.

        Args:
            path: File path

        Returns:
            int: Size in bytes
        """
        path = str(Path(path))
        if path in self.files:
            return len(self.files[path])
        return 0

    def get_mtime(self, path: str) -> float:
        """Get modification time.

        Args:
            path: File path

        Returns:
            float: Modification time as timestamp
        """
        path = str(Path(path))
        if path in self.modification_times:
            return self.modification_times[path].timestamp()
        return 0.0

    def clear(self) -> None:
        """Clear all files and directories."""
        self.files.clear()
        self.directories.clear()
        self.metadata.clear()
        self.access_times.clear()
        self.modification_times.clear()


class TestCache:
    """In-memory cache for testing cache-dependent components.

    Provides a cache implementation that doesn't persist to disk,
    making tests faster and more isolated.

    Example:
        cache = TestCache()
        cache.set("key", "value", ttl_seconds=60)
        assert cache.get("key") == "value"
    """

    __test__ = False

    def __init__(self):
        """Initialize the test cache."""
        self.data: Dict[str, Any] = {}
        self.expiry_times: Dict[str, datetime] = {}
        self.access_counts: Dict[str, int] = defaultdict(int)
        self.cache_hits = 0
        self.cache_misses = 0

    def get(self, key: str, default: Any = None) -> Any:
        """Get value from cache.

        Args:
            key: Cache key
            default: Default value if not found or expired

        Returns:
            Cached value or default
        """
        self.access_counts[key] += 1

        # Check expiry
        if key in self.expiry_times:
            if datetime.now() > self.expiry_times[key]:
                self.data.pop(key, None)
                self.expiry_times.pop(key, None)

        if key in self.data:
            self.cache_hits += 1
            return self.data[key]

        self.cache_misses += 1
        return default

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        """Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl_seconds: Time to live in seconds
        """
        self.data[key] = value

        if ttl_seconds is not None:
            self.expiry_times[key] = datetime.now() + timedelta(seconds=ttl_seconds)

    def delete(self, key: str) -> bool:
        """Delete key from cache.

        Args:
            key: Cache key to delete

        Returns:
            bool: True if key existed
        """
        existed = key in self.data
        self.data.pop(key, None)
        self.expiry_times.pop(key, None)
        return existed

    def clear(self) -> None:
        """Clear all cached data."""
        self.data.clear()
        self.expiry_times.clear()
        self.access_counts.clear()
        self.cache_hits = 0
        self.cache_misses = 0

    def expire_all(self) -> None:
        """Expire all cached entries."""
        self.expiry_times = {
            key: datetime.now() - timedelta(seconds=1) for key in self.data
        }

    def has(self, key: str) -> bool:
        """Check if key exists and is not expired.

        Args:
            key: Cache key to check

        Returns:
            bool: True if key exists and is valid
        """
        if key in self.expiry_times:
            if datetime.now() > self.expiry_times[key]:
                return False
        return key in self.data

    @property
    def size(self) -> int:
        """Get number of cached items."""
        return len(self.data)

    @property
    def hit_rate(self) -> float:
        """Get cache hit rate."""
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return 0.0
        return self.cache_hits / total


class TestQApplication:
    """Minimal Qt application mock for widget testing.

    Provides just enough Qt application behavior for testing widgets
    without requiring full Qt application setup.
    """

    __test__ = False

    def __init__(self):
        """Initialize the test application."""
        self.clipboard_text = ""
        self.style_sheet = ""
        self.application_name = "TestApp"
        self.organization_name = "TestOrg"
        self.quit_called = False

    def clipboard(self):
        """Get clipboard mock."""
        return self

    def setText(self, text: str) -> None:
        """Set clipboard text."""
        self.clipboard_text = text

    def text(self) -> str:
        """Get clipboard text."""
        return self.clipboard_text

    def setStyleSheet(self, style: str) -> None:
        """Set application style sheet."""
        self.style_sheet = style

    def quit(self) -> None:
        """Mark application as quit."""
        self.quit_called = True

    def processEvents(self) -> None:
        """Process events (no-op in test)."""
        pass

    @staticmethod
    def instance():
        """Get application instance."""
        if not hasattr(TestQApplication, "_instance"):
            TestQApplication._instance = TestQApplication()
        return TestQApplication._instance
