"""Improved command launcher tests following UNIFIED_TESTING_GUIDE.

This test suite validates CommandLauncher behavior using:
- Test doubles at system boundaries only (subprocess)
- Real Qt components and signals
- Behavior testing, not implementation details
- No mock.Mock or MagicMock usage
- TestCommand and TestProcessPool instead of unittest.mock

Key improvements:
- Uses TestCommand for command execution testing
- Uses TestProcessPool for workspace command testing
- Tests behavior, not implementation
- Uses real components where possible
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import NoReturn

import pytest

from command_launcher import CommandLauncher
from config import Config
from shot_model import Shot
from tests.test_doubles_extended import TestCommand
from tests.test_doubles_extended import TestProcessPoolDouble as TestProcessPool

# Test doubles for behavior testing (UNIFIED_TESTING_GUIDE)
from tests.test_doubles_library import SubprocessModuleDouble, TestShot, TestSubprocess
from threede_scene_model import ThreeDEScene

pytestmark = [pytest.mark.unit, pytest.mark.qt, pytest.mark.slow]


class TestNukeScriptGenerator:
    """Test double for NukeScriptGenerator."""

    def create_plate_script(self, *args, **kwargs) -> str:
        """Mock create_plate_script method."""
        return "/tmp/script.nk"

    def create_plate_script_with_undistortion(self, *args, **kwargs) -> str:
        """Mock create_plate_script_with_undistortion method."""
        return "/tmp/integrated_script.nk"

    def create_loader_script(self, *args, **kwargs) -> str:
        """Mock create_loader_script method."""
        return "/tmp/loader_script.nk"


class TestCommandLauncherInitialization:
    """Test CommandLauncher initialization and basic setup."""

    def setup_method(self) -> None:
        """Setup with test doubles at system boundary."""
        self.launcher = CommandLauncher()
        self.command_executor = TestCommand()

        # Replace command execution with test double
        # This depends on how CommandLauncher executes commands
        # We'll patch at subprocess level for workspace commands
        self.process_pool = TestProcessPool()

        # Track emitted signals (behavior)
        self.emitted_commands = []
        self.emitted_errors = []

        self.launcher.command_executed.connect(
            lambda t, c: self.emitted_commands.append((t, c))
        )
        self.launcher.command_error.connect(
            lambda t, e: self.emitted_errors.append((t, e))
        )

    def test_initialization(self, qtbot) -> None:
        """Test CommandLauncher initializes correctly."""
        # Check initial state
        assert self.launcher.current_shot is None

        # Check signals exist
        assert hasattr(self.launcher, "command_executed")
        assert hasattr(self.launcher, "command_error")

        # Verify signals are valid by checking they can be connected
        # (qtbot.waitSignal will validate the signal when used)
        assert self.launcher.command_executed is not None
        assert self.launcher.command_error is not None

    def test_set_current_shot(self, qtbot) -> None:
        """Test setting current shot context."""
        # Create test shot using test double
        shot = TestShot(
            show="test_show",
            sequence="seq01",
            shot="shot01",
            workspace_path="/shows/test_show/shots/seq01/shot01",
        )

        # Set shot
        self.launcher.set_current_shot(shot)
        assert self.launcher.current_shot == shot

        # Test clearing shot
        self.launcher.set_current_shot(None)
        assert self.launcher.current_shot is None


class TestSignalEmissions:
    """Test signal emissions for command execution events."""

    def setup_method(self) -> None:
        """Setup with test doubles."""
        self.launcher = CommandLauncher()
        self.test_subprocess = TestSubprocess()
        self.subprocess_double = SubprocessModuleDouble(self.test_subprocess)

        # Configure test subprocess to make rez unavailable
        self.test_subprocess.set_command_output(
            "which rez", 1, "", "rez: command not found"
        )

        # Replace subprocess at system boundary
        self.original_subprocess_run = subprocess.run
        self.original_subprocess_popen = subprocess.Popen

        subprocess.run = self.subprocess_double.run
        subprocess.Popen = self.subprocess_double.Popen

        # Track signals (behavior)
        self.emitted_commands = []
        self.emitted_errors = []

        self.launcher.command_executed.connect(
            lambda t, c: self.emitted_commands.append((t, c))
        )
        self.launcher.command_error.connect(
            lambda t, e: self.emitted_errors.append((t, e))
        )

    def teardown_method(self) -> None:
        subprocess.run = self.original_subprocess_run
        subprocess.Popen = self.original_subprocess_popen

    def test_command_executed_signal(self, qtbot) -> None:
        """Test command_executed signal emission behavior."""
        # Set up test double for success
        self.test_subprocess.return_code = 0
        self.test_subprocess.stdout = "nuke started successfully"

        # Create test shot using test double
        shot = TestShot(
            show="test_show",
            sequence="seq01",
            shot="shot01",
            workspace_path="/tmp/test_workspace",
        )
        self.launcher.set_current_shot(shot)

        # Launch app (real component behavior)
        result = self.launcher.launch_app("nuke")

        # Test behavior, not implementation
        assert result is True
        # With Nuke environment fixes, we may emit multiple log messages
        assert len(self.emitted_commands) >= 1
        assert len(self.emitted_errors) == 0

        # Check the actual command is in the emissions (may have setup logs first)
        final_command_found = False
        for timestamp, command in self.emitted_commands:
            assert isinstance(timestamp, str)
            assert len(timestamp.split(":")) == 3  # HH:MM:SS format
            if "ws /tmp/test_workspace" in command and "nuke" in command:
                final_command_found = True
                break

        assert final_command_found, "Expected command with workspace and nuke not found"

    def test_command_error_signal(self, qtbot) -> None:
        """Test command_error signal emission behavior."""
        # Test error when no shot is set
        result = self.launcher.launch_app("nuke")

        # Test behavior
        assert result is False
        assert len(self.emitted_errors) == 1
        assert len(self.emitted_commands) == 0

        timestamp, error = self.emitted_errors[0]
        assert isinstance(timestamp, str)
        assert "No shot selected" in error

    def test_unknown_app_error_signal(self, qtbot) -> None:
        """Test error signal for unknown application."""
        # Create test shot
        shot = TestShot(
            show="test_show",
            sequence="seq01",
            shot="shot01",
            workspace_path="/tmp/test_workspace",
        )
        self.launcher.set_current_shot(shot)

        # Try to launch unknown app
        result = self.launcher.launch_app("unknown_app")

        # Test behavior
        assert result is False
        assert len(self.emitted_errors) == 1
        assert len(self.emitted_commands) == 0

        timestamp, error = self.emitted_errors[0]
        assert "Unknown application: unknown_app" in error


class TestApplicationLaunching:
    """Test application launching functionality with behavior focus."""

    def setup_method(self) -> None:
        """Setup with test doubles."""
        self.launcher = CommandLauncher()
        self.test_subprocess = TestSubprocess()
        self.subprocess_double = SubprocessModuleDouble(self.test_subprocess)

        # Configure test subprocess to make rez unavailable
        self.test_subprocess.set_command_output(
            "which rez", 1, "", "rez: command not found"
        )

        # Replace subprocess at system boundary
        self.original_subprocess_run = subprocess.run
        self.original_subprocess_popen = subprocess.Popen

        subprocess.run = self.subprocess_double.run
        subprocess.Popen = self.subprocess_double.Popen

    def teardown_method(self) -> None:
        subprocess.run = self.original_subprocess_run
        subprocess.Popen = self.original_subprocess_popen

    def test_launch_app_without_shot(self, qtbot) -> None:
        """Test launching app without setting current shot."""
        result = self.launcher.launch_app("nuke")
        assert result is False

    def test_launch_app_unknown_application(self, qtbot) -> None:
        """Test launching unknown application."""
        # Set test shot using test double
        shot = TestShot(
            show="test_show",
            sequence="seq01",
            shot="shot01",
            workspace_path="/tmp/test_workspace",
        )
        self.launcher.set_current_shot(shot)

        result = self.launcher.launch_app("nonexistent_app")
        assert result is False

    def test_launch_app_valid_configuration(self, qtbot) -> None:
        """Test launching valid application behavior."""
        # Set up test double for success
        self.test_subprocess.return_code = 0
        self.test_subprocess.stdout = "Application launched"

        # Set test shot using test double
        shot = TestShot(
            show="test_show",
            sequence="seq01",
            shot="shot01",
            workspace_path="/tmp/test_workspace",
        )
        self.launcher.set_current_shot(shot)

        result = self.launcher.launch_app("nuke")
        assert result is True

    def test_command_construction(self, qtbot) -> None:
        """Test proper command construction behavior."""
        # Set up test double
        self.test_subprocess.return_code = 0
        self.test_subprocess.stdout = "maya launched"

        # Track signals for behavior testing
        emitted_commands = []
        self.launcher.command_executed.connect(
            lambda t, c: emitted_commands.append((t, c))
        )

        # Set test shot using test double
        shot = TestShot(
            show="test_show",
            sequence="seq01",
            shot="shot01",
            workspace_path="/shows/test_show/shots/seq01/shot01",
        )
        self.launcher.set_current_shot(shot)

        self.launcher.launch_app("maya")

        # Test behavior - command was constructed and executed
        assert len(emitted_commands) >= 1
        timestamp, command = emitted_commands[0]

        # Verify command contains workspace setup and app command
        expected_workspace = "ws /shows/test_show/shots/seq01/shot01"
        expected_app = Config.APPS["maya"]

        assert expected_workspace in command
        assert expected_app in command
        assert "&&" in command  # Command chaining

    def test_terminal_fallback_execution(self, qtbot) -> None:
        """Test terminal fallback behavior."""

        # Set up test double to simulate terminal failures then success
        def fallback_subprocess(*args, **kwargs):
            # Create a test double that tracks attempts
            subprocess_double = TestSubprocess()

            # First few calls fail, then success
            if not hasattr(self, "_terminal_attempts"):
                self._terminal_attempts = 0
            self._terminal_attempts += 1

            if self._terminal_attempts <= 3:
                # Simulate terminal not found
                raise FileNotFoundError("Terminal not found")
            else:
                # Direct bash succeeds
                subprocess_double.return_code = 0
                subprocess_double.stdout = "Direct execution succeeded"
                return subprocess_double

        subprocess.Popen = fallback_subprocess

        # Set test shot
        shot = TestShot(
            show="test_show",
            sequence="seq01",
            shot="shot01",
            workspace_path="/tmp/test_workspace",
        )
        self.launcher.set_current_shot(shot)

        result = self.launcher.launch_app("nuke")

        # Test behavior - fallback should eventually succeed
        assert result is True
        assert self._terminal_attempts >= 3  # Multiple attempts made


class TestThreeDESceneLaunching:
    """Test 3DE scene launching functionality."""

    def setup_method(self) -> None:
        """Setup with test doubles."""
        self.test_subprocess = TestSubprocess()
        self.subprocess_double = SubprocessModuleDouble(self.test_subprocess)

        # Configure test subprocess to make rez unavailable
        self.test_subprocess.set_command_output(
            "which rez", 1, "", "rez: command not found"
        )

        self.original_subprocess_run = subprocess.run
        self.original_subprocess_popen = subprocess.Popen

        subprocess.run = self.subprocess_double.run
        subprocess.Popen = self.subprocess_double.Popen

    def teardown_method(self) -> None:
        """Restore original subprocess."""
        subprocess.run = self.original_subprocess_run
        subprocess.Popen = self.original_subprocess_popen

    def test_launch_app_with_scene(self, qtbot) -> None:
        """Test launching application with 3DE scene file."""
        launcher = CommandLauncher()

        # Set up test double for success
        self.test_subprocess.return_code = 0
        self.test_subprocess.stdout = "3de launched successfully"

        # Create test scene
        scene = ThreeDEScene(
            show="test_show",
            sequence="seq01",
            shot="shot01",
            scene_path=Path("/path/to/scene.3de"),
            workspace_path="/shows/test_show/shots/seq01/shot01",
            user="testuser",
            plate="bg01",
        )

        # Set up signal expectation with parameter checking
        def check_command_params(timestamp, command):
            return (
                str(scene.scene_path) in command
                and scene.workspace_path in command
                and "3de" in command
            )

        with qtbot.waitSignal(
            launcher.command_executed, check_params_cb=check_command_params
        ):
            result = launcher.launch_app_with_scene("3de", scene)
            assert result is True

    def test_launch_app_with_scene_unknown_app(self, qtbot) -> None:
        """Test error handling for unknown app with scene."""
        launcher = CommandLauncher()

        # Create test scene
        scene = ThreeDEScene(
            show="test_show",
            sequence="seq01",
            shot="shot01",
            scene_path=Path("/path/to/scene.3de"),
            workspace_path="/shows/test_show/shots/seq01/shot01",
            user="testuser",
            plate="bg01",
        )

        result = launcher.launch_app_with_scene("unknown_app", scene)
        assert result is False

    def test_launch_app_with_scene_context(self, qtbot) -> None:
        """Test launching app with scene context (no scene file)."""
        launcher = CommandLauncher()

        # Set up test double for success
        self.test_subprocess.return_code = 0
        self.test_subprocess.stdout = "nuke launched successfully"

        # Create test scene
        scene = ThreeDEScene(
            show="test_show",
            sequence="seq01",
            shot="shot01",
            scene_path=Path("/path/to/scene.3de"),
            workspace_path="/shows/test_show/shots/seq01/shot01",
            user="testuser",
            plate="bg01",
        )

        result = launcher.launch_app_with_scene_context("nuke", scene)
        assert result is True


class TestWorkspaceIntegration:
    """Test workspace command integration."""

    def setup_method(self) -> None:
        """Setup with test doubles."""
        self.test_subprocess = TestSubprocess()
        self.subprocess_double = SubprocessModuleDouble(self.test_subprocess)

        # Configure test subprocess to make rez unavailable
        self.test_subprocess.set_command_output(
            "which rez", 1, "", "rez: command not found"
        )

        self.original_subprocess_run = subprocess.run
        self.original_subprocess_popen = subprocess.Popen

        subprocess.run = self.subprocess_double.run
        subprocess.Popen = self.subprocess_double.Popen

    def teardown_method(self) -> None:
        """Restore original subprocess."""
        subprocess.run = self.original_subprocess_run
        subprocess.Popen = self.original_subprocess_popen

    def test_workspace_command_construction(self, qtbot) -> None:
        """Test proper workspace command construction."""
        launcher = CommandLauncher()

        # Set up test double for success
        self.test_subprocess.return_code = 0
        self.test_subprocess.stdout = "rv launched successfully"

        # Set test shot
        shot = Shot(
            show="test_show",
            sequence="seq01",
            shot="shot01",
            workspace_path="/shows/test_show/shots/seq01/shot01",
        )
        launcher.set_current_shot(shot)

        # Set up signal expectation with parameter checking
        def check_workspace_command_params(timestamp, command):
            expected_ws_cmd = f"ws {shot.workspace_path}"
            return (
                expected_ws_cmd in command
                and "&&" in command
                and Config.APPS["rv"] in command
            )

        with qtbot.waitSignal(
            launcher.command_executed, check_params_cb=check_workspace_command_params
        ):
            launcher.launch_app("rv")

    def test_workspace_path_handling(self, qtbot) -> None:
        """Test different workspace path formats."""
        launcher = CommandLauncher()

        # Set up test double for success
        self.test_subprocess.return_code = 0
        self.test_subprocess.stdout = "nuke launched successfully"

        # Test different path formats
        test_paths = [
            "/shows/project/shots/seq01/shot01",
            "/shows/another_project/shots/sequence_010/shot_0001",
            "/mnt/storage/shows/test/shots/s001/sh010",
        ]

        for workspace_path in test_paths:
            shot = Shot(
                show="test_show",
                sequence="seq01",
                shot="shot01",
                workspace_path=workspace_path,
            )
            launcher.set_current_shot(shot)

            # Set up signal expectation for this workspace path
            def check_workspace_path(timestamp, command):
                return workspace_path in command

            with qtbot.waitSignal(
                launcher.command_executed, check_params_cb=check_workspace_path
            ):
                result = launcher.launch_app("nuke")
                assert result is True


class TestErrorHandling:
    """Test error handling and edge cases."""

    def setup_method(self) -> None:
        """Setup with test doubles."""
        self.test_subprocess = TestSubprocess()
        self.subprocess_double = SubprocessModuleDouble(self.test_subprocess)

        self.original_subprocess_run = subprocess.run
        self.original_subprocess_popen = subprocess.Popen

    def teardown_method(self) -> None:
        """Restore original subprocess."""
        subprocess.run = self.original_subprocess_run
        subprocess.Popen = self.original_subprocess_popen

    def test_subprocess_execution_failure(self, qtbot) -> None:
        """Test handling of subprocess execution failures."""
        launcher = CommandLauncher()
        test_subprocess = TestSubprocess()
        subprocess_double = SubprocessModuleDouble(test_subprocess)

        # Configure test subprocess to make rez unavailable but allow its check to succeed
        test_subprocess.set_command_output("which rez", 1, "", "rez: command not found")

        # Replace subprocess at system boundary
        original_subprocess_run = subprocess.run
        original_subprocess_popen = subprocess.Popen

        subprocess.run = subprocess_double.run

        # Make Popen fail for terminal commands
        def failing_popen(*args, **kwargs) -> NoReturn:
            raise Exception("Process execution failed")

        subprocess.Popen = failing_popen

        # Set test shot
        shot = Shot(
            show="test_show",
            sequence="seq01",
            shot="shot01",
            workspace_path="/tmp/test_workspace",
        )
        launcher.set_current_shot(shot)

        # Set up error signal expectation with parameter checking
        def check_error_params(timestamp, error_msg):
            return "Failed to launch nuke" in error_msg

        try:
            with qtbot.waitSignal(
                launcher.command_error, check_params_cb=check_error_params
            ):
                result = launcher.launch_app("nuke")
                assert result is False
        finally:
            subprocess.run = original_subprocess_run
            subprocess.Popen = original_subprocess_popen

    def test_all_terminals_fail(self, qtbot) -> None:
        """Test when all terminal attempts fail but direct execution succeeds."""
        launcher = CommandLauncher()

        # Set test shot
        shot = Shot(
            show="test_show",
            sequence="seq01",
            shot="shot01",
            workspace_path="/tmp/test_workspace",
        )
        launcher.set_current_shot(shot)

        # Track execution attempts
        attempt_count = 0

        def fallback_popen(*args, **kwargs):
            nonlocal attempt_count
            attempt_count += 1

            # First few attempts fail (terminals not found)
            if attempt_count <= 3:
                raise FileNotFoundError("Terminal not found")
            else:
                # Direct bash succeeds
                success_subprocess = TestSubprocess()
                success_subprocess.return_code = 0
                success_subprocess.stdout = "nuke launched successfully"
                return success_subprocess.Popen(*args, **kwargs)

        subprocess.Popen = fallback_popen

        result = launcher.launch_app("nuke")
        assert result is True
        assert attempt_count >= 3  # Multiple attempts made

    def test_complete_execution_failure(self, qtbot) -> None:
        """Test when all execution methods fail."""
        launcher = CommandLauncher()
        test_subprocess = TestSubprocess()
        subprocess_double = SubprocessModuleDouble(test_subprocess)

        # Configure test subprocess to make rez unavailable but allow its check to succeed
        test_subprocess.set_command_output("which rez", 1, "", "rez: command not found")

        # Replace subprocess at system boundary
        original_subprocess_run = subprocess.run
        original_subprocess_popen = subprocess.Popen

        subprocess.run = subprocess_double.run

        # Make Popen always fail
        def failing_popen(*args, **kwargs) -> NoReturn:
            raise Exception("All execution failed")

        subprocess.Popen = failing_popen

        # Set test shot
        shot = Shot(
            show="test_show",
            sequence="seq01",
            shot="shot01",
            workspace_path="/tmp/test_workspace",
        )
        launcher.set_current_shot(shot)

        # Set up error signal expectation
        try:
            with qtbot.waitSignal(launcher.command_error):
                result = launcher.launch_app("nuke")
                assert result is False
        finally:
            subprocess.run = original_subprocess_run
            subprocess.Popen = original_subprocess_popen


class TestNukeIntegration:
    """Test Nuke-specific integration features."""

    def setup_method(self) -> None:
        """Setup with test doubles."""
        self.test_subprocess = TestSubprocess()
        self.test_subprocess.return_code = 0
        self.test_subprocess.stdout = "nuke launched successfully"
        self.subprocess_double = SubprocessModuleDouble(self.test_subprocess)

        self.original_subprocess_run = subprocess.run
        self.original_subprocess_popen = subprocess.Popen

        subprocess.run = self.subprocess_double.run
        subprocess.Popen = self.subprocess_double.Popen

    def teardown_method(self) -> None:
        """Restore original subprocess."""
        subprocess.run = self.original_subprocess_run
        subprocess.Popen = self.original_subprocess_popen

    def test_nuke_with_raw_plate_option(self, qtbot) -> None:
        """Test Nuke launching with raw plate integration."""

        # Create test doubles for dependencies
        class TestRawPlateFinder:
            @staticmethod
            def find_latest_raw_plate(*args, **kwargs) -> str:
                return "/path/to/plate.%04d.exr"

            @staticmethod
            def verify_plate_exists(*args, **kwargs) -> bool:
                return True

            @staticmethod
            def get_version_from_path(*args, **kwargs) -> str:
                return "v001"

        # Use dependency injection instead of module-level replacement
        launcher = CommandLauncher(
            raw_plate_finder=TestRawPlateFinder,
            nuke_script_generator=TestNukeScriptGenerator,
        )

        # Set test shot
        shot = Shot(
            show="test_show",
            sequence="seq01",
            shot="shot01",
            workspace_path="/shows/test_show/shots/seq01/shot01",
        )
        launcher.set_current_shot(shot)

        result = launcher.launch_app("nuke", include_raw_plate=True)
        assert result is True

    def test_nuke_with_undistortion_option(self, qtbot) -> None:
        """Test Nuke launching with undistortion integration."""

        # Create test double for UndistortionFinder
        class TestUndistortionFinder:
            @staticmethod
            def find_latest_undistortion(*args, **kwargs):
                return Path("/path/to/undist.nk")

            @staticmethod
            def get_version_from_path(*args, **kwargs) -> str:
                return "v001"

        # Use dependency injection instead of module-level replacement
        launcher = CommandLauncher(
            undistortion_finder=TestUndistortionFinder,
        )

        # Set test shot
        shot = Shot(
            show="test_show",
            sequence="seq01",
            shot="shot01",
            workspace_path="/shows/test_show/shots/seq01/shot01",
        )
        launcher.set_current_shot(shot)

        result = launcher.launch_app("nuke", include_undistortion=True)
        assert result is True

    def test_nuke_with_both_plate_and_undistortion(self, qtbot) -> None:
        """Test Nuke launching with both raw plate and undistortion."""

        # Create test doubles for both finders
        class TestRawPlateFinder:
            @staticmethod
            def find_latest_raw_plate(*args, **kwargs) -> str:
                return "/path/to/plate.%04d.exr"

            @staticmethod
            def verify_plate_exists(*args, **kwargs) -> bool:
                return True

            @staticmethod
            def get_version_from_path(*args, **kwargs) -> str:
                return "v001"

        class TestUndistortionFinder:
            @staticmethod
            def find_latest_undistortion(*args, **kwargs):
                return Path("/path/to/undist.nk")

            @staticmethod
            def get_version_from_path(*args, **kwargs) -> str:
                return "v001"

        # Use dependency injection for all dependencies
        launcher = CommandLauncher(
            raw_plate_finder=TestRawPlateFinder,
            undistortion_finder=TestUndistortionFinder,
            nuke_script_generator=TestNukeScriptGenerator,
        )

        # Set test shot
        shot = Shot(
            show="test_show",
            sequence="seq01",
            shot="shot01",
            workspace_path="/shows/test_show/shots/seq01/shot01",
        )
        launcher.set_current_shot(shot)

        result = launcher.launch_app(
            "nuke",
            include_raw_plate=True,
            include_undistortion=True,
        )
        assert result is True


class TestTimestampGeneration:
    """Test timestamp generation for command logging."""

    def test_timestamp_format(self, qtbot) -> None:
        """Test timestamp format in signal emissions."""
        launcher = CommandLauncher()

        # Set up signal expectation with timestamp validation
        def check_timestamp_format(timestamp, error_msg):
            # Verify timestamp format (HH:MM:SS)
            assert isinstance(timestamp, str)
            parts = timestamp.split(":")
            if len(parts) != 3:
                return False

            # Verify each part is numeric and within valid ranges
            hours, minutes, seconds = parts
            return (
                hours.isdigit()
                and 0 <= int(hours) <= 23
                and minutes.isdigit()
                and 0 <= int(minutes) <= 59
                and seconds.replace(".", "").isdigit()  # May have decimal seconds
            )

        with qtbot.waitSignal(
            launcher.command_error, check_params_cb=check_timestamp_format
        ):
            # Trigger error to get timestamp
            launcher.launch_app("nuke")  # No shot set, should trigger error

    def test_consistent_timestamp_format(self, qtbot) -> None:
        """Test timestamp format consistency across different signals."""
        launcher = CommandLauncher()

        # Set test shot for successful execution
        shot = Shot(
            show="test_show",
            sequence="seq01",
            shot="shot01",
            workspace_path="/tmp/test_workspace",
        )
        launcher.set_current_shot(shot)

        # Set up test double for success
        test_subprocess = TestSubprocess()
        test_subprocess.return_code = 0
        test_subprocess.stdout = "nuke launched successfully"

        subprocess_double = SubprocessModuleDouble(test_subprocess)
        original_subprocess_run = subprocess.run
        original_subprocess_popen = subprocess.Popen

        subprocess.run = subprocess_double.run
        subprocess.Popen = subprocess_double.Popen

        try:
            # Check executed signal timestamp format
            def check_executed_timestamp(timestamp, command):
                return len(timestamp.split(":")) == 3

            with qtbot.waitSignal(
                launcher.command_executed, check_params_cb=check_executed_timestamp
            ):
                # Trigger successful execution
                launcher.launch_app("nuke")

            # Check error signal timestamp format
            def check_error_timestamp(timestamp, error):
                return len(timestamp.split(":")) == 3

            with qtbot.waitSignal(
                launcher.command_error, check_params_cb=check_error_timestamp
            ):
                # Trigger error
                launcher.launch_app("unknown_app")
        finally:
            subprocess.run = original_subprocess_run
            subprocess.Popen = original_subprocess_popen


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def setup_method(self) -> None:
        """Setup with test doubles."""
        self.test_subprocess = TestSubprocess()
        self.test_subprocess.return_code = 0
        self.test_subprocess.stdout = "app launched successfully"
        self.subprocess_double = SubprocessModuleDouble(self.test_subprocess)

        self.original_subprocess_run = subprocess.run
        self.original_subprocess_popen = subprocess.Popen

        subprocess.run = self.subprocess_double.run
        subprocess.Popen = self.subprocess_double.Popen

    def teardown_method(self) -> None:
        """Restore original subprocess."""
        subprocess.run = self.original_subprocess_run
        subprocess.Popen = self.original_subprocess_popen

    def test_empty_workspace_path(self, qtbot) -> None:
        """Test handling of empty workspace path."""
        launcher = CommandLauncher()

        # Set shot with empty workspace path
        shot = Shot(
            show="test_show",
            sequence="seq01",
            shot="shot01",
            workspace_path="",
        )
        launcher.set_current_shot(shot)

        result = launcher.launch_app("nuke")
        # Should still work with empty workspace
        assert result is True

    def test_special_characters_in_paths(self, qtbot) -> None:
        """Test handling of special characters in workspace paths."""
        launcher = CommandLauncher()

        # Test paths with special characters
        special_paths = [
            "/shows/project with spaces/shots/seq01/shot01",
            "/shows/project-dash/shots/seq_01/shot-01",
            "/shows/project.dots/shots/seq.01/shot.01",
        ]

        for workspace_path in special_paths:
            shot = Shot(
                show="test_show",
                sequence="seq01",
                shot="shot01",
                workspace_path=workspace_path,
            )
            launcher.set_current_shot(shot)

            result = launcher.launch_app("nuke")
            assert result is True

    def test_rapid_successive_launches(self, qtbot) -> None:
        """Test rapid successive application launches."""
        launcher = CommandLauncher()

        # Set test shot
        shot = Shot(
            show="test_show",
            sequence="seq01",
            shot="shot01",
            workspace_path="/tmp/test_workspace",
        )
        launcher.set_current_shot(shot)

        # Test each app individually for better error isolation
        apps_to_test = ["nuke", "maya", "rv", "3de"]
        for app in apps_to_test:
            result = launcher.launch_app(app)
            assert result, f"Failed to launch {app}"

    @pytest.mark.parametrize(
        "app_name",
        [
            "nuke",
            "maya",
            "rv",
            pytest.param("3de", marks=pytest.mark.slow, id="3de_slow_launch"),
        ],
    )
    def test_individual_app_launch_parametrized(self, qtbot, app_name) -> None:
        """Test individual app launches with better error isolation."""
        launcher = CommandLauncher()

        # Set test shot
        shot = Shot(
            show="test_show",
            sequence="seq01",
            shot="shot01",
            workspace_path="/tmp/test_workspace",
        )
        launcher.set_current_shot(shot)

        result = launcher.launch_app(app_name)
        assert result, f"Failed to launch {app_name}"
