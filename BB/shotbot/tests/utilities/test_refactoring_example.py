"""Example demonstrating test refactoring from anti-patterns to UNIFIED_TESTING_GUIDE principles.

This file shows the transformation from Mock-heavy testing to behavior-focused testing.
"""

# =============================================================================
# BEFORE: Anti-pattern example with excessive mocking
# =============================================================================

"""
# This is what we're AVOIDING - DO NOT WRITE TESTS LIKE THIS:

from unittest.mock import Mock, patch, MagicMock

class TestLauncherManager_ANTIPATTERN:
    '''Example of what NOT to do - excessive mocking and implementation testing.'''
    
    @patch('launcher_manager.subprocess.Popen')
    @patch('launcher_manager.os.chdir')
    @patch('launcher_manager.Path.exists')
    @patch('launcher_manager.json.load')
    @patch('launcher_manager.open')
    def test_execute_launcher_WRONG(self, mock_open, mock_json, mock_exists, 
                                    mock_chdir, mock_popen):
        '''WRONG: Testing implementation details with excessive mocking.'''
        # Setup ALL the mocks
        mock_exists.return_value = True
        mock_json.return_value = {'test': {'name': 'Test', 'command': 'echo test'}}
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file
        mock_process = Mock()
        mock_process.poll.return_value = None
        mock_popen.return_value = mock_process
        
        manager = LauncherManager()
        manager._validate_launcher = Mock(return_value=True)
        manager._substitute_variables = Mock(return_value='echo test')
        manager._emit_signal = Mock()
        
        # Execute
        result = manager.execute_launcher('test')
        
        # WRONG: Testing that methods were called (implementation details)
        mock_open.assert_called_once()
        mock_json.assert_called_once()
        mock_exists.assert_called()
        mock_chdir.assert_called()
        mock_popen.assert_called_with(['echo', 'test'], shell=False)
        manager._validate_launcher.assert_called_once_with('test')
        manager._substitute_variables.assert_called_once()
        manager._emit_signal.assert_called()
        
        # We don't actually know if the launcher worked correctly!
"""

# =============================================================================
# AFTER: Proper behavior-focused testing following UNIFIED_TESTING_GUIDE
# =============================================================================

import tempfile
import time
from pathlib import Path
from typing import Optional, List, Dict, Any

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtTest import QSignalSpy

# Import real components
from launcher_manager import LauncherManager, CustomLauncher, ProcessInfo
from shot_model import Shot


class ProcessDouble:
    """Test double for subprocess.Popen - simulates process behavior.
    
    This is at the SYSTEM BOUNDARY - we mock subprocess, not our code.
    """
    
    def __init__(self, command: str, return_code: int = 0, should_hang: bool = False):
        """Initialize with predictable behavior."""
        self.command = command
        self.return_code = return_code
        self.should_hang = should_hang
        self.pid = 12345
        self._running = True
        self._terminated = False
        self._killed = False
        self.start_time = time.time()
        
    def poll(self) -> Optional[int]:
        """Check if process is running."""
        if self._terminated or self._killed:
            self._running = False
            return self.return_code
            
        if self.should_hang:
            return None  # Still running
            
        # Simulate quick completion
        if time.time() - self.start_time > 0.1:
            self._running = False
            return self.return_code
            
        return None
        
    def terminate(self):
        """Terminate the process."""
        self._terminated = True
        self._running = False
        
    def kill(self):
        """Force kill the process."""
        self._killed = True
        self._running = False
        
    def wait(self, timeout=None):
        """Wait for process completion."""
        if self.should_hang and timeout:
            import subprocess
            raise subprocess.TimeoutExpired(self.command, timeout)
        self._running = False
        return self.return_code


class TestLauncherManagerBehavior:
    """Test LauncherManager BEHAVIOR, not implementation.
    
    Key principles:
    1. Use real LauncherManager, not mocks
    2. Test outcomes and state changes
    3. Verify signal emissions
    4. Mock only at system boundaries (subprocess)
    """
    
    def test_successful_launcher_execution_behavior(self, qtbot):
        """Test that launcher executes and emits correct signals.
        
        CORRECT: We test the actual behavior and outcomes.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            # Use REAL LauncherManager with temp directory
            manager = LauncherManager(temp_dir)
            
            # Create a REAL launcher
            launcher_id = manager.create_launcher(
                name="Test App",
                command="echo 'hello world'"
            )
            assert launcher_id is not None
            
            # Set up signal spies to verify BEHAVIOR
            started_spy = QSignalSpy(manager.execution_started)
            finished_spy = QSignalSpy(manager.execution_finished)
            
            # Mock ONLY at system boundary (subprocess)
            test_process = ProcessDouble("echo 'hello world'", return_code=0)
            
            with patch('subprocess.Popen', return_value=test_process):
                # Execute the launcher
                result = manager.execute_launcher(launcher_id)
            
            # Test BEHAVIOR: Correct return value
            assert result == True
            
            # Test BEHAVIOR: Signals were emitted
            assert started_spy.count() == 1
            assert finished_spy.count() == 1
            
            # Test BEHAVIOR: Signal contains correct data
            launcher_id_from_signal, success = finished_spy.at(0)
            assert launcher_id_from_signal == launcher_id
            assert success == True
            
            # Test BEHAVIOR: Process was tracked
            # (We don't test HOW it was tracked, just that it was)
            
    def test_launcher_execution_with_error_recovery(self, qtbot):
        """Test that launcher handles errors gracefully.
        
        CORRECT: We test error recovery behavior, not error detection implementation.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = LauncherManager(temp_dir)
            
            # Create launcher
            launcher_id = manager.create_launcher(
                name="Failing App",
                command="nonexistent_command"
            )
            
            error_spy = QSignalSpy(manager.validation_error)
            finished_spy = QSignalSpy(manager.execution_finished)
            
            # Simulate command not found at system boundary
            with patch('subprocess.Popen', side_effect=FileNotFoundError("Command not found")):
                result = manager.execute_launcher(launcher_id)
            
            # Test BEHAVIOR: Execution failed gracefully
            assert result == False
            
            # Test BEHAVIOR: Error was reported
            assert error_spy.count() > 0
            error_message = error_spy.at(0)[1]
            assert "not found" in error_message.lower()
            
            # Test BEHAVIOR: Manager is still functional after error
            # (Can create new launchers, not broken)
            new_launcher = manager.create_launcher("Recovery Test", "echo test")
            assert new_launcher is not None
            
    def test_launcher_variable_substitution_behavior(self, qtbot):
        """Test that variables are substituted correctly in commands.
        
        CORRECT: We test the outcome of substitution, not the substitution method.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = LauncherManager(temp_dir)
            
            # Create launcher with variables
            launcher_id = manager.create_launcher(
                name="Shot Tool",
                command="echo Working on $show/$sequence/$shot"
            )
            
            # Create a real shot
            shot = Shot("myshow", "seq01", "shot001", temp_dir)
            
            # Set up to capture the actual command executed
            executed_commands = []
            
            def capture_command(*args, **kwargs):
                executed_commands.append(args[0] if args else kwargs.get('args', []))
                return ProcessDouble("echo", return_code=0)
            
            with patch('subprocess.Popen', side_effect=capture_command):
                # Execute in shot context
                result = manager.execute_in_shot_context(launcher_id, shot)
            
            # Test BEHAVIOR: Variables were substituted in executed command
            assert result == True
            assert len(executed_commands) == 1
            
            command_parts = executed_commands[0]
            command_str = ' '.join(command_parts) if isinstance(command_parts, list) else str(command_parts)
            
            # Verify substitution happened (behavior, not how)
            assert "myshow" in command_str
            assert "seq01" in command_str
            assert "shot001" in command_str
            assert "$show" not in command_str  # Variables were replaced
            
    def test_concurrent_launcher_execution_behavior(self, qtbot):
        """Test that multiple launchers can run concurrently.
        
        CORRECT: We test the behavior of concurrent execution, not thread management.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = LauncherManager(temp_dir)
            
            # Create multiple launchers
            launcher1 = manager.create_launcher("App 1", "sleep 1")
            launcher2 = manager.create_launcher("App 2", "sleep 1")
            
            # Track active processes
            active_processes = []
            
            def create_hanging_process(*args, **kwargs):
                process = ProcessDouble("sleep", should_hang=True)
                active_processes.append(process)
                return process
            
            with patch('subprocess.Popen', side_effect=create_hanging_process):
                # Start both launchers
                result1 = manager.execute_launcher(launcher1)
                result2 = manager.execute_launcher(launcher2)
            
            # Test BEHAVIOR: Both launchers started
            assert result1 == True
            assert result2 == True
            
            # Test BEHAVIOR: Both processes are running concurrently
            assert len(active_processes) == 2
            assert all(p._running for p in active_processes)
            
            # Test BEHAVIOR: Manager tracks both processes
            process_info = manager.get_active_process_info()
            assert len(process_info) >= 2
            
    def test_launcher_cleanup_on_shutdown(self, qtbot):
        """Test that launchers are cleaned up properly on shutdown.
        
        CORRECT: We test that cleanup happens, not how it's implemented.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = LauncherManager(temp_dir)
            
            launcher_id = manager.create_launcher("Long Running", "sleep 100")
            
            # Start a long-running process
            test_process = ProcessDouble("sleep 100", should_hang=True)
            
            with patch('subprocess.Popen', return_value=test_process):
                manager.execute_launcher(launcher_id)
            
            # Test BEHAVIOR: Process is running
            assert test_process._running == True
            
            # Shutdown the manager
            manager.shutdown()
            
            # Test BEHAVIOR: Process was terminated
            assert test_process._terminated or test_process._killed
            assert not test_process._running
            
            # Test BEHAVIOR: Manager is in shutdown state
            assert manager._shutting_down == True


class TestLauncherPersistence:
    """Test launcher persistence behavior.
    
    Uses real file I/O with temp directories instead of mocking.
    """
    
    def test_launcher_saves_and_loads_correctly(self):
        """Test that launchers persist across manager instances.
        
        CORRECT: We use real file I/O with temp directory, not mocks.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create and save launcher
            manager1 = LauncherManager(temp_dir)
            launcher_id = manager1.create_launcher(
                name="Persistent App",
                command="echo persistent",
                description="Test persistence"
            )
            assert launcher_id is not None
            
            # Create new manager instance (simulates restart)
            manager2 = LauncherManager(temp_dir)
            
            # Test BEHAVIOR: Launcher was loaded from disk
            loaded_launcher = manager2.get_launcher(launcher_id)
            assert loaded_launcher is not None
            assert loaded_launcher.name == "Persistent App"
            assert loaded_launcher.command == "echo persistent"
            assert loaded_launcher.description == "Test persistence"
            
    def test_corrupt_config_recovery(self):
        """Test that manager recovers from corrupted config.
        
        CORRECT: We test recovery behavior with real corrupted file.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = LauncherManager(temp_dir)
            
            # Corrupt the config file directly
            config_file = Path(temp_dir) / "launchers.json"
            config_file.write_text("{ invalid json }")
            
            # Test BEHAVIOR: Manager handles corruption gracefully
            manager2 = LauncherManager(temp_dir)
            launchers = manager2.list_launchers()
            
            # Should recover with empty launcher list
            assert launchers == []
            
            # Test BEHAVIOR: Can still create new launchers after corruption
            launcher_id = manager2.create_launcher("After Corruption", "echo test")
            assert launcher_id is not None


# =============================================================================
# KEY DIFFERENCES SUMMARIZED
# =============================================================================

"""
BEFORE (Anti-patterns):
1. Mock everything - LauncherManager, subprocess, os, json, Path, etc.
2. Test that methods were called - assert_called_once(), assert_called_with()
3. Mock internal methods - _validate_launcher, _substitute_variables
4. Test implementation details - how variables are substituted
5. Fragile tests that break when implementation changes

AFTER (Best practices):
1. Use real LauncherManager with temp directories
2. Test behavior and outcomes - signals emitted, state changes
3. Mock only at system boundaries - subprocess.Popen
4. Test what happens, not how - variables ARE substituted, not HOW
5. Robust tests that survive refactoring

The refactored tests:
- Are more reliable and less fragile
- Actually test that the code works correctly
- Don't break when implementation details change
- Are easier to understand and maintain
- Catch real bugs that mock-heavy tests miss
"""

if __name__ == "__main__":
    # This file is for demonstration only
    print("This file demonstrates test refactoring patterns.")
    print("See the code and comments for examples of before/after.")