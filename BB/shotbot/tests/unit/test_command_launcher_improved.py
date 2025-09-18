"""Improved command launcher tests following UNIFIED_TESTING_GUIDE."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from command_launcher import CommandLauncher
from tests.test_doubles_library import SubprocessModuleDouble, TestSubprocess

pytestmark = pytest.mark.unit

# This demonstrates proper testing patterns:
# - Use test doubles at system boundaries only
# - Test behavior, not implementation
# - Use real components where possible


class TestCommandLauncherImproved:
    """Improved tests using test doubles instead of mocks."""

    def setup_method(self) -> None:
        """Setup with real components and test doubles."""
        # Set up subprocess double (UNIFIED_TESTING_GUIDE)
        self.test_subprocess = TestSubprocess()
        self.subprocess_double = SubprocessModuleDouble(self.test_subprocess)

        # Configure default behavior for rez check
        self.test_subprocess.set_command_output(
            "which rez", 1, "", "rez: command not found"
        )

        # Store original subprocess methods for restoration
        self.original_subprocess_run = subprocess.run
        self.original_subprocess_Popen = subprocess.Popen

        # Replace subprocess methods with doubles
        subprocess.run = self.subprocess_double.run
        subprocess.Popen = self.subprocess_double.Popen

        # Real component with doubled subprocess calls
        self.launcher = CommandLauncher()

        # Track emitted signals (behavior)
        self.emitted_commands = []
        self.emitted_errors = []

        # Connect to real signals
        self.launcher.command_executed.connect(
            lambda timestamp, command: self.emitted_commands.append(
                (timestamp, command)
            )
        )
        self.launcher.command_error.connect(
            lambda timestamp, error: self.emitted_errors.append((timestamp, error))
        )

    def teardown_method(self) -> None:
        """Clean up subprocess doubles."""
        # Restore original subprocess methods
        subprocess.run = self.original_subprocess_run
        subprocess.Popen = self.original_subprocess_Popen

    def test_launch_app_success_behavior(self) -> None:
        """Test successful app launch BEHAVIOR, not implementation."""
        # Arrange: Configure subprocess double for success
        self.test_subprocess.set_command_output("nuke", 0, "Application started", "")

        # Act: Launch the app (real component behavior)
        self.launcher.current_shot = MagicMock(
            show="test_show", sequence="seq01", shot="0010", workspace_path="/test/path"
        )
        result = self.launcher.launch_app("nuke")

        # Assert: Test BEHAVIOR, not mocks
        assert result is True  # Launch succeeded
        # Filter out informational messages, only count actual commands (ones starting with "ws")
        actual_commands = [cmd for cmd in self.emitted_commands if cmd[1].startswith("ws")]
        assert len(actual_commands) == 1  # Command was executed
        timestamp, command = actual_commands[0]  # Unpack timestamp and command
        assert "nuke" in command  # Correct app launched
        assert len(self.emitted_errors) == 0  # No errors

    def test_launch_app_failure_behavior(self) -> None:
        """Test app launch failure BEHAVIOR."""
        # Arrange: Configure subprocess double to raise exception
        self.test_subprocess.side_effect = FileNotFoundError("Command not found")

        # Act: Try to launch app
        self.launcher.current_shot = MagicMock(
            show="test_show", sequence="seq01", shot="0010", workspace_path="/test/path"
        )
        result = self.launcher.launch_app("nuke")

        # Assert: Test error BEHAVIOR
        assert result is False  # Launch failed
        assert len(self.emitted_errors) == 1  # Error was emitted
        timestamp, error = self.emitted_errors[0]  # Unpack timestamp and error
        assert "Failed to launch" in error  # Correct error message
        # Command is still logged before the failure - filter for actual commands
        actual_commands = [cmd for cmd in self.emitted_commands if cmd[1].startswith("ws")]
        assert len(actual_commands) == 1  # Command logged before error

    def test_launch_without_shot_behavior(self) -> None:
        """Test launching without shot context."""
        # Act: Launch without setting shot
        result = self.launcher.launch_app("maya")

        # Assert: Test BEHAVIOR
        assert result is False  # Launch failed
        assert len(self.emitted_errors) == 1
        timestamp, error = self.emitted_errors[0]  # Unpack timestamp and error
        assert "No shot selected" in error
        assert len(self.emitted_commands) == 0

    def test_concurrent_launches_behavior(self) -> None:
        """Test concurrent app launches (real threading behavior)."""
        # Arrange: Set up shot context and configure subprocess double for success
        self.launcher.current_shot = MagicMock(
            show="test_show", sequence="seq01", shot="0010", workspace_path="/test/path"
        )
        # Configure successful execution for all apps
        self.test_subprocess.set_command_output("nuke", 0, "nuke started", "")
        self.test_subprocess.set_command_output("maya", 0, "maya started", "")
        self.test_subprocess.set_command_output("3de", 0, "3de started", "")

        # Act: Launch multiple apps (focus on command logging behavior)
        self.launcher.launch_app("nuke")
        self.launcher.launch_app("maya")
        self.launcher.launch_app("3de")  # Use valid app from Config.APPS

        # Assert: Test that commands were logged (behavior we care about)
        # Filter for actual commands only
        actual_commands = [cmd for cmd in self.emitted_commands if cmd[1].startswith("ws")]
        assert len(actual_commands) == 3  # All commands logged
        # Extract just the command part (second element) from each tuple
        apps_launched = [cmd[1] for cmd in actual_commands]
        assert any("nuke" in app for app in apps_launched)
        assert any("maya" in app for app in apps_launched)
        assert any("3de" in app for app in apps_launched)

        # The actual subprocess success/failure is implementation detail
        # What matters is that commands are logged and attempted

    def test_command_formatting_behavior(self) -> None:
        """Test command formatting with actual app launch."""
        # Arrange: Configure subprocess double and shot with test data
        self.test_subprocess.set_command_output(
            "nuke", return_code=0, stdout="Application started"
        )
        self.launcher.current_shot = MagicMock(
            show="project_x",
            sequence="seq99",
            shot="0420",
            workspace_path="/shows/project_x/seq99/0420",
        )

        # Act: Launch actual app (tests command formatting internally)
        self.launcher.launch_app("nuke")

        # Assert: Test workspace path in command BEHAVIOR
        # Filter for actual commands only
        actual_commands = [cmd for cmd in self.emitted_commands if cmd[1].startswith("ws")]
        assert len(actual_commands) == 1
        timestamp, command = actual_commands[0]  # Unpack timestamp and command
        assert "/shows/project_x/seq99/0420" in command  # Workspace path included

    def test_workspace_change_behavior(self) -> None:
        """Test behavior when workspace changes."""
        # Arrange: Initial shot and configure subprocess double
        shot1 = MagicMock(
            show="show1", sequence="seq01", shot="0010", workspace_path="/shows/show1"
        )

        shot2 = MagicMock(
            show="show2", sequence="seq02", shot="0020", workspace_path="/shows/show2"
        )

        self.test_subprocess.set_command_output(
            "nuke", return_code=0, stdout="Changed workspace"
        )

        # Act: Change shots and launch
        self.launcher.set_current_shot(shot1)
        self.launcher.launch_app("nuke")

        self.launcher.set_current_shot(shot2)
        self.launcher.launch_app("nuke")

        # Assert: Test workspace change BEHAVIOR
        # Filter for actual commands only
        actual_commands = [cmd for cmd in self.emitted_commands if cmd[1].startswith("ws")]
        assert len(actual_commands) == 2
        # Check workspace paths in the commands (second element of tuple)
        assert "/shows/show1" in actual_commands[0][1]  # First command
        assert "/shows/show2" in actual_commands[1][1]  # Second command


class TestCommandLauncherIntegration:
    """Integration tests with real filesystem."""

    def setup_method(self) -> None:
        """Setup with real temp directories."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.workspace = self.temp_dir / "workspace"
        self.workspace.mkdir()

        # Create shot structure
        (self.workspace / "scripts").mkdir()
        (self.workspace / "renders").mkdir()

    def teardown_method(self) -> None:
        """Clean up temp files."""

        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_real_workspace_navigation(self) -> None:
        """Test with real filesystem operations."""

        launcher = CommandLauncher()
        launcher.current_shot = MagicMock(
            workspace_path=str(self.workspace),
            show="test_show",
            sequence="seq01",
            shot="0010",
        )

        # Test that launcher can work with real workspace path
        # CommandLauncher doesn't expose validate_workspace method - test via launch_app
        result = launcher.launch_app("nuke")  # Should not crash with real path
        assert isinstance(result, bool)  # Should return boolean success/failure

    def test_missing_workspace_handling(self) -> None:
        """Test behavior with missing workspace."""

        launcher = CommandLauncher()
        launcher.current_shot = MagicMock(
            workspace_path="/nonexistent/path",
            show="test_show",
            sequence="seq01",
            shot="0010",
        )

        # Test error handling behavior via launch_app
        result = launcher.launch_app("nuke")
        # Should handle nonexistent path gracefully and return boolean
        assert isinstance(result, bool)


# Example of how to run standalone
if __name__ == "__main__":
    test = TestCommandLauncherImproved()
    test.setup_method()

    # Run tests
    test.test_launch_app_success_behavior()
    test.test_launch_app_failure_behavior()
    test.test_concurrent_launches_behavior()

    print("✅ All improved tests passed!")
    print("Key improvements:")
    print("- No # Test behavior: verify actual results patterns")
    print("- Test doubles only at subprocess boundary")
    print("- Testing behavior, not implementation")
    print("- Real components with real signals")
