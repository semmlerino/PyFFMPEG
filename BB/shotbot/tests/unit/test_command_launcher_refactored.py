"""Command launcher tests following UNIFIED_TESTING_GUIDE best practices.

This refactored test suite demonstrates:
- Using TestSubprocess instead of @patch("subprocess.Popen")
- Testing behavior, not implementation
- Real Qt components with proper signal testing
- Minimal test doubles at system boundaries only
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import pytest
from PySide6.QtCore import QObject
from PySide6.QtTest import QSignalSpy

# Add parent path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from command_launcher import CommandLauncher
from config import Config
from shot_model import Shot

# Import comprehensive test doubles
from tests.test_doubles_library import (
    PopenDouble,
    TestShot,
    TestSubprocess,
    TestWorker,
    ThreadSafeTestImage,
)

pytestmark = [pytest.mark.unit, pytest.mark.qt]


class TestCommandLauncherBehavior:
    """Test CommandLauncher behavior using test doubles instead of mocks."""

    def setup_method(self) -> None:
        """Setup with test doubles at system boundaries."""
        # Create real launcher with test subprocess
        self.test_subprocess = TestSubprocess()
        self.launcher = CommandLauncher()
        
        # Mock subprocess.Popen at system boundary
        import subprocess
        self.original_popen = subprocess.Popen
        self.popen_should_fail = False  # Flag to control failure
        
        # Create a mock Popen that records commands
        def mock_popen(cmd, *args, **kwargs):
            # Check if we should simulate failure
            if self.popen_should_fail:
                raise OSError("Cannot start process")
            
            # Record the command for verification
            if isinstance(cmd, list):
                self.test_subprocess.executed_commands.append(cmd)
            else:
                self.test_subprocess.executed_commands.append([cmd])
            # Return a test double process
            process = PopenDouble(cmd, returncode=0)
            return process
        
        subprocess.Popen = mock_popen
    
    def teardown_method(self) -> None:
        """Restore original subprocess.Popen."""
        import subprocess
        subprocess.Popen = self.original_popen
    
    def test_launch_app_successful_behavior(self, qtbot) -> None:
        """Test successful app launch behavior, not implementation."""
        # Setup test data
        shot = TestShot("myshow", "seq01", "0010")
        self.launcher.set_current_shot(shot)
        
        # Configure subprocess behavior
        self.test_subprocess.set_command_output(
            pattern="nuke",
            return_code=0,
            stdout="Nuke 14.0v1 starting..."
        )
        
        # Setup signal spy for real Qt signals
        spy_executed = QSignalSpy(self.launcher.command_executed)
        spy_error = QSignalSpy(self.launcher.command_error)
        
        # Execute real behavior
        result = self.launcher.launch_app("nuke")
        
        # Assert BEHAVIOR, not implementation
        assert result is True  # App launched successfully
        
        # Verify signals emitted (behavior)
        assert spy_executed.count() == 1
        assert spy_error.count() == 0
        
        # Verify signal data (behavior)
        signal_args = spy_executed.at(0)  # Get first emission
        timestamp = signal_args[0]
        command = signal_args[1]
        assert isinstance(timestamp, str)
        assert ":" in timestamp  # Has time format
        assert "nuke" in command.lower()
        assert shot.workspace_path in command
        
        # Verify subprocess was called with correct workspace
        assert self.test_subprocess.was_called_with(shot.workspace_path)
        assert self.test_subprocess.was_called_with("nuke")
    
    def test_launch_app_without_shot_behavior(self, qtbot) -> None:
        """Test launching app without shot context - behavior focused."""
        # No shot set - testing error behavior
        spy_executed = QSignalSpy(self.launcher.command_executed)
        spy_error = QSignalSpy(self.launcher.command_error)
        
        # Execute behavior
        result = self.launcher.launch_app("nuke")
        
        # Assert error behavior
        assert result is False
        assert spy_executed.count() == 0
        assert spy_error.count() == 1
        
        # Verify error message (behavior)
        signal_args = spy_error.at(0)  # Get first emission
        timestamp = signal_args[0]
        error_msg = signal_args[1]
        assert "no shot selected" in error_msg.lower()
        
        # Verify no subprocess calls were made
        assert len(self.test_subprocess.executed_commands) == 0
    
    def test_launch_unknown_app_behavior(self, qtbot) -> None:
        """Test launching unknown application - behavior focused."""
        shot = TestShot("myshow", "seq01", "0010")
        self.launcher.set_current_shot(shot)
        
        spy_error = QSignalSpy(self.launcher.command_error)
        
        # Try to launch non-existent app
        result = self.launcher.launch_app("nonexistent_app")
        
        # Assert error behavior
        assert result is False
        assert spy_error.count() == 1
        
        signal_args = spy_error.at(0)  # Get first emission
        timestamp = signal_args[0]
        error_msg = signal_args[1]
        assert "unknown application" in error_msg.lower()
        assert "nonexistent_app" in error_msg
    
    def test_launch_app_subprocess_failure_behavior(self, qtbot) -> None:
        """Test subprocess failure handling - behavior focused."""
        shot = TestShot("myshow", "seq01", "0010")
        self.launcher.set_current_shot(shot)
        
        # Configure subprocess to fail
        self.popen_should_fail = True
        
        spy_error = QSignalSpy(self.launcher.command_error)
        
        # Execute behavior
        result = self.launcher.launch_app("nuke")
        
        # Assert error handling behavior
        assert result is False
        assert spy_error.count() == 1
        
        signal_args = spy_error.at(0)  # Get first emission
        timestamp = signal_args[0]
        error_msg = signal_args[1]
        assert "cannot start process" in error_msg.lower()
    
    def test_multiple_app_launches_behavior(self, qtbot) -> None:
        """Test launching multiple apps sequentially - behavior focused."""
        shot = TestShot("myshow", "seq01", "0010")
        self.launcher.set_current_shot(shot)
        
        # Configure different outputs for different apps
        self.test_subprocess.set_command_output("nuke", 0, "Nuke started")
        self.test_subprocess.set_command_output("maya", 0, "Maya started")
        self.test_subprocess.set_command_output("3de", 0, "3DE started")
        
        spy_executed = QSignalSpy(self.launcher.command_executed)
        
        # Launch multiple apps
        apps_to_launch = ["nuke", "maya", "3de"]
        results = []
        
        for app in apps_to_launch:
            result = self.launcher.launch_app(app)
            results.append(result)
        
        # Assert all succeeded
        assert all(results)
        assert spy_executed.count() == 3
        
        # Verify each command contains the right app
        for i, app in enumerate(apps_to_launch):
            signal_args = spy_executed.at(i)  # Get i-th emission
            timestamp = signal_args[0]
            command = signal_args[1]
            assert app in command.lower()
    


if __name__ == "__main__":
    """Allow running tests directly."""
    pytest.main([__file__, "-v"])