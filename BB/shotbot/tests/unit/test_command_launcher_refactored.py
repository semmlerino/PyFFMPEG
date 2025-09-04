"""Refactored command launcher tests using TestCommand and TestProcessPool.

This test suite follows UNIFIED_TESTING_GUIDE principles:
- Uses TestCommand and TestProcessPool instead of unittest.mock
- Tests at subprocess boundary only
- Tests behavior and outcomes, not implementation
- No Mock() or MagicMock usage
- Tests actual command results and side effects
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from PySide6.QtTest import QSignalSpy

import command_launcher
from command_launcher import CommandLauncher
from config import Config
from shot_model import Shot
from tests.test_doubles_library import (
    SubprocessModuleDouble,
    TestCompletedProcess,
    TestShot,
    TestSubprocess,
)
from threede_scene_model import ThreeDEScene

pytestmark = [pytest.mark.unit, pytest.mark.qt, pytest.mark.slow]


# TestCommandExecutor removed - using SubprocessModuleDouble instead


class TestCommandLauncherCore:
    """Core CommandLauncher tests using SubprocessModuleDouble."""

    def setup_method(self):
        """Setup with SubprocessModuleDouble at subprocess boundary."""
        self.launcher = CommandLauncher()

        # Create TestSubprocess instance
        self.test_subprocess = TestSubprocess()

        # Wrap it with SubprocessModuleDouble
        self.subprocess_double = SubprocessModuleDouble(self.test_subprocess)

        # Configure rez to be unavailable (as per testing guide)
        self.test_subprocess.set_command_output(
            "which rez", return_code=1, stderr="rez: command not found"
        )

        # Replace both subprocess.run and subprocess.Popen
        self.original_subprocess_run = subprocess.run
        self.original_subprocess_popen = subprocess.Popen
        subprocess.run = self.subprocess_double.run
        subprocess.Popen = self.subprocess_double.Popen

        # Also replace in the command_launcher module
        command_launcher.subprocess.run = self.subprocess_double.run
        command_launcher.subprocess.Popen = self.subprocess_double.Popen

        # Setup spies for signal tracking
        self.command_spy = QSignalSpy(self.launcher.command_executed)
        self.error_spy = QSignalSpy(self.launcher.command_error)

    def teardown_method(self):
        """Restore original subprocess methods."""
        subprocess.run = self.original_subprocess_run
        subprocess.Popen = self.original_subprocess_popen
        command_launcher.subprocess.run = self.original_subprocess_run
        command_launcher.subprocess.Popen = self.original_subprocess_popen

    def test_initialization(self, qtbot):
        """Test CommandLauncher initializes with correct state."""
        assert self.launcher.current_shot is None
        assert hasattr(self.launcher, "command_executed")
        assert hasattr(self.launcher, "command_error")
        # Signals will be validated when used with qtbot.waitSignal
        assert self.launcher.command_executed is not None
        assert self.launcher.command_error is not None

    def test_set_current_shot(self):
        """Test setting shot context."""
        # Create test shot
        shot = TestShot(
            show="test_show",
            sequence="seq01",
            shot="0010",
            workspace_path="/shows/test_show/shots/seq01/seq01_0010",
        )

        # Set shot
        self.launcher.set_current_shot(shot)
        assert self.launcher.current_shot == shot

        # Clear shot
        self.launcher.set_current_shot(None)
        assert self.launcher.current_shot is None

    def test_launch_app_success(self, qtbot):
        """Test successful app launch behavior."""
        # Configure subprocess to succeed for launcher commands
        self.test_subprocess.return_code = 0
        self.test_subprocess.stdout = "Nuke launched successfully"

        # Set current shot
        shot = Shot(
            show="test",
            sequence="seq01",
            shot="0010",
            workspace_path="/shows/test/shots/seq01/seq01_0010",
        )
        self.launcher.set_current_shot(shot)

        # Set up signal expectation with parameter checking
        def check_command_params(timestamp, command):
            return (
                isinstance(timestamp, str)
                and ":" in timestamp  # Has time format
                and "ws /shows/test/shots/seq01/seq01_0010" in command
                and "nuke" in command
            )

        with qtbot.waitSignal(
            self.launcher.command_executed, check_params_cb=check_command_params
        ):
            # Launch app
            result = self.launcher.launch_app("nuke")
            assert result is True
            assert (
                len(self.test_subprocess.executed_commands) > 0
            )  # Command was executed

    def test_launch_app_no_shot_selected(self, qtbot):
        """Test error when no shot is selected."""

        # Set up error signal expectation with parameter checking
        def check_error_params(timestamp, error):
            return "No shot selected" in error

        with qtbot.waitSignal(
            self.launcher.command_error, check_params_cb=check_error_params
        ):
            # Don't set a shot
            result = self.launcher.launch_app("nuke")
            assert result is False
            # Commands may be executed during rez check, but not main launch

    def test_launch_unknown_app(self, qtbot):
        """Test error for unknown application."""
        # Set shot
        shot = Shot(
            show="test", sequence="seq01", shot="0010", workspace_path="/test/workspace"
        )
        self.launcher.set_current_shot(shot)

        def check_error_params(timestamp, error):
            return "Unknown application: unknown_app" in error

        with qtbot.waitSignal(
            self.launcher.command_error, check_params_cb=check_error_params
        ):
            # Try unknown app
            result = self.launcher.launch_app("unknown_app")

            # Verify error behavior
            assert result is False
            # Commands may be executed during rez check, but not main launch

    def test_terminal_fallback(self):
        """Test fallback through different terminal options."""
        # Configure terminals to fail but direct bash to succeed
        self.test_subprocess.set_command_output(
            "gnome-terminal", return_code=1, stderr="Terminal not found"
        )
        self.test_subprocess.set_command_output(
            "xterm", return_code=1, stderr="Terminal not found"
        )
        self.test_subprocess.set_command_output(
            "konsole", return_code=1, stderr="Terminal not found"
        )
        # But let direct bash succeed
        self.test_subprocess.return_code = 0
        self.test_subprocess.stdout = "Direct bash execution"

        # Set shot and launch
        shot = Shot(
            show="test", sequence="seq01", shot="0010", workspace_path="/test/workspace"
        )
        self.launcher.set_current_shot(shot)

        result = self.launcher.launch_app("nuke")

        # Should eventually succeed with direct bash
        assert result is True
        assert len(self.test_subprocess.executed_commands) >= 1  # Commands were tried
        assert (
            self.command_spy.count() >= 1
        )  # May emit multiple signals during fallback


class TestWorkspaceCommands:
    """Test workspace command integration using SubprocessModuleDouble."""

    def setup_method(self):
        """Setup with SubprocessModuleDouble for workspace commands."""
        self.launcher = CommandLauncher()

        # Create TestSubprocess instance
        self.test_subprocess = TestSubprocess()

        # Wrap it with SubprocessModuleDouble
        self.subprocess_double = SubprocessModuleDouble(self.test_subprocess)

        # Configure rez to be unavailable
        self.test_subprocess.set_command_output(
            "which rez", return_code=1, stderr="rez: command not found"
        )

        # Configure workspace commands to succeed
        self.test_subprocess.return_code = 0
        self.test_subprocess.stdout = "Command executed"

        # Replace both subprocess.run and subprocess.Popen
        self.original_subprocess_run = subprocess.run
        self.original_subprocess_popen = subprocess.Popen
        subprocess.run = self.subprocess_double.run
        subprocess.Popen = self.subprocess_double.Popen

        # Also replace in the command_launcher module
        command_launcher.subprocess.run = self.subprocess_double.run
        command_launcher.subprocess.Popen = self.subprocess_double.Popen

        # Setup spies
        self.command_spy = QSignalSpy(self.launcher.command_executed)
        self.error_spy = QSignalSpy(self.launcher.command_error)

    def teardown_method(self):
        """Restore original subprocess methods."""
        subprocess.run = self.original_subprocess_run
        subprocess.Popen = self.original_subprocess_popen
        command_launcher.subprocess.run = self.original_subprocess_run
        command_launcher.subprocess.Popen = self.original_subprocess_popen

    def test_workspace_command_construction(self):
        """Test proper workspace command construction."""
        # Set shot
        shot = Shot(
            show="test",
            sequence="seq01",
            shot="0010",
            workspace_path="/shows/test/shots/seq01/seq01_0010",
        )
        self.launcher.set_current_shot(shot)

        # Launch app
        result = self.launcher.launch_app("maya")

        # Verify behavior
        assert result is True
        assert self.command_spy.count() >= 1

        # Check command includes workspace (check the final command)
        timestamp, command = self.command_spy.at(self.command_spy.count() - 1)
        assert "ws /shows/test/shots/seq01/seq01_0010" in command
        assert Config.APPS["maya"] in command
        assert "&&" in command  # Command chaining

        # Check subprocess was used
        assert len(self.test_subprocess.executed_commands) > 0

    def test_workspace_path_variations(self):
        """Test different workspace path formats."""
        test_paths = [
            "/shows/project/shots/seq01/seq01_0010",
            "/shows/another/shots/sequence_010/sequence_010_0001",
            "/mnt/storage/shows/test/shots/s001/s001_sh010",
        ]

        for workspace_path in test_paths:
            shot = Shot(
                show="test",
                sequence="seq01",
                shot="0010",
                workspace_path=workspace_path,
            )
            self.launcher.set_current_shot(shot)

            result = self.launcher.launch_app("nuke")
            assert result is True

            # Verify workspace path in command
            assert self.command_spy.count() > 0
            timestamp, command = self.command_spy.at(
                self.command_spy.count() - 1
            )  # Get last signal
            assert workspace_path in command


class TestThreeDESceneLaunching:
    """Test 3DE scene launching functionality."""

    def setup_method(self):
        """Setup for 3DE scene tests."""
        self.launcher = CommandLauncher()

        # Create TestSubprocess instance
        self.test_subprocess = TestSubprocess()

        # Wrap it with SubprocessModuleDouble
        self.subprocess_double = SubprocessModuleDouble(self.test_subprocess)

        # Configure rez to be unavailable
        self.test_subprocess.set_command_output(
            "which rez", return_code=1, stderr="rez: command not found"
        )

        # Replace both subprocess.run and subprocess.Popen
        self.original_subprocess_run = subprocess.run
        self.original_subprocess_popen = subprocess.Popen
        subprocess.run = self.subprocess_double.run
        subprocess.Popen = self.subprocess_double.Popen

        # Also replace in the command_launcher module
        command_launcher.subprocess.run = self.subprocess_double.run
        command_launcher.subprocess.Popen = self.subprocess_double.Popen

        # Setup spies
        self.command_spy = QSignalSpy(self.launcher.command_executed)
        self.error_spy = QSignalSpy(self.launcher.command_error)

    def teardown_method(self):
        """Restore original subprocess methods."""
        subprocess.run = self.original_subprocess_run
        subprocess.Popen = self.original_subprocess_popen
        command_launcher.subprocess.run = self.original_subprocess_run
        command_launcher.subprocess.Popen = self.original_subprocess_popen

    def test_launch_app_with_scene(self):
        """Test launching 3DE with scene file."""
        # Configure subprocess to succeed
        self.test_subprocess.return_code = 0
        self.test_subprocess.stdout = "3DE launched with scene"

        # Create test scene
        scene = ThreeDEScene(
            show="test",
            sequence="seq01",
            shot="0010",
            scene_path=Path("/path/to/scene.3de"),
            workspace_path="/shows/test/shots/seq01/seq01_0010",
            user="testuser",
            plate="bg01",
        )

        # Launch with scene
        result = self.launcher.launch_app_with_scene("3de", scene)

        # Verify behavior
        assert result is True
        assert len(self.test_subprocess.executed_commands) > 0
        assert self.command_spy.count() == 1

        # Check command includes scene file
        timestamp, command = self.command_spy.at(0)
        assert str(scene.scene_path) in command
        assert scene.workspace_path in command
        assert "3de" in command

    def test_launch_app_with_scene_unknown_app(self):
        """Test error for unknown app with scene."""
        scene = ThreeDEScene(
            show="test",
            sequence="seq01",
            shot="0010",
            scene_path=Path("/path/to/scene.3de"),
            workspace_path="/test/workspace",
            user="testuser",
            plate="bg01",
        )

        result = self.launcher.launch_app_with_scene("unknown_app", scene)

        assert result is False
        assert self.error_spy.count() == 1
        timestamp, error = self.error_spy.at(0)
        assert "Unknown application: unknown_app" in error

    def test_launch_app_with_scene_context(self):
        """Test launching app with scene context (no scene file)."""
        # Configure subprocess to succeed
        self.test_subprocess.return_code = 0
        self.test_subprocess.stdout = "Nuke launched in scene context"

        scene = ThreeDEScene(
            show="test",
            sequence="seq01",
            shot="0010",
            scene_path=Path("/path/to/scene.3de"),
            workspace_path="/shows/test/shots/seq01/seq01_0010",
            user="testuser",
            plate="bg01",
        )

        result = self.launcher.launch_app_with_scene_context("nuke", scene)

        assert result is True
        assert self.command_spy.count() == 1


class TestErrorHandling:
    """Test error handling and edge cases."""

    def setup_method(self):
        """Setup for error testing."""
        self.launcher = CommandLauncher()

        # Create TestSubprocess instance
        self.test_subprocess = TestSubprocess()

        # Wrap it with SubprocessModuleDouble
        self.subprocess_double = SubprocessModuleDouble(self.test_subprocess)

        # Configure rez to be unavailable
        self.test_subprocess.set_command_output(
            "which rez", return_code=1, stderr="rez: command not found"
        )

        # Replace both subprocess.run and subprocess.Popen
        self.original_subprocess_run = subprocess.run
        self.original_subprocess_popen = subprocess.Popen
        subprocess.run = self.subprocess_double.run
        subprocess.Popen = self.subprocess_double.Popen

        # Also replace in the command_launcher module
        command_launcher.subprocess.run = self.subprocess_double.run
        command_launcher.subprocess.Popen = self.subprocess_double.Popen

        self.error_spy = QSignalSpy(self.launcher.command_error)

    def teardown_method(self):
        """Restore original subprocess methods."""
        subprocess.run = self.original_subprocess_run
        subprocess.Popen = self.original_subprocess_popen
        command_launcher.subprocess.run = self.original_subprocess_run
        command_launcher.subprocess.Popen = self.original_subprocess_popen

    def test_subprocess_execution_failure(self):
        """Test handling of subprocess failures."""
        # First clear the rez side effect to allow the rez check
        self.test_subprocess.side_effect = None

        # Now create a custom Popen that fails
        def failing_popen(*args, **kwargs):
            raise Exception("Process execution failed")

        # Replace just Popen to let subprocess.run (rez check) work but Popen fail
        self.subprocess_double.Popen = failing_popen
        command_launcher.subprocess.Popen = failing_popen

        # Set shot and try to launch
        shot = Shot(
            show="test", sequence="seq01", shot="0010", workspace_path="/test/workspace"
        )
        self.launcher.set_current_shot(shot)

        result = self.launcher.launch_app("nuke")

        # Should handle failure gracefully
        assert result is False
        assert self.error_spy.count() == 1
        timestamp, error = self.error_spy.at(0)
        assert "Failed to launch nuke" in error

    def test_all_execution_methods_fail(self):
        """Test when all execution methods fail."""
        # First clear the rez side effect to allow the rez check
        self.test_subprocess.side_effect = None

        # Create custom methods that always fail
        def failing_popen(*args, **kwargs):
            raise Exception("All execution failed")

        def failing_run(*args, **kwargs):
            # Let rez check pass - the actual check is 'which rez'
            cmd = args[0] if args else ""
            cmd_str = str(cmd)
            # The rez check uses ["which", "rez"]
            if "which" in cmd_str and "rez" in cmd_str:
                # Return a TestCompletedProcess that indicates rez not found
                return TestCompletedProcess(
                    cmd, returncode=1, stderr="rez: command not found"
                )
            # For all other commands, fail
            raise Exception("All execution failed")

        # Replace both methods to fail (except rez check)
        self.subprocess_double.run = failing_run
        self.subprocess_double.Popen = failing_popen
        command_launcher.subprocess.run = failing_run
        command_launcher.subprocess.Popen = failing_popen

        shot = Shot(
            show="test", sequence="seq01", shot="0010", workspace_path="/test/workspace"
        )
        self.launcher.set_current_shot(shot)

        result = self.launcher.launch_app("nuke")

        assert result is False
        assert self.error_spy.count() == 1

    def test_special_characters_in_paths(self):
        """Test handling of special characters in paths."""
        # Configure subprocess to succeed
        self.test_subprocess.return_code = 0
        self.test_subprocess.stdout = "Command executed"

        special_paths = [
            "/shows/project with spaces/shots/seq01/seq01_0010",
            "/shows/project-dash/shots/seq_01/seq_01-0010",
            "/shows/project.dots/shots/seq.01/seq.01.0010",
        ]

        for workspace_path in special_paths:
            shot = Shot(
                show="test",
                sequence="seq01",
                shot="0010",
                workspace_path=workspace_path,
            )
            self.launcher.set_current_shot(shot)

            # Should handle special characters safely
            result = self.launcher.launch_app("maya")
            assert result is True

    def test_empty_workspace_path(self):
        """Test handling of empty workspace path."""
        # Configure subprocess to succeed
        self.test_subprocess.return_code = 0
        self.test_subprocess.stdout = "Command executed"

        shot = Shot(show="test", sequence="seq01", shot="0010", workspace_path="")
        self.launcher.set_current_shot(shot)

        result = self.launcher.launch_app("rv")
        assert result is True  # Should work with empty workspace


class TestNukeIntegration:
    """Test Nuke-specific integration features."""

    def setup_method(self):
        """Setup for Nuke tests."""
        self.launcher = CommandLauncher()

        # Create TestSubprocess instance
        self.test_subprocess = TestSubprocess()

        # Wrap it with SubprocessModuleDouble
        self.subprocess_double = SubprocessModuleDouble(self.test_subprocess)

        # Configure rez to be unavailable
        self.test_subprocess.set_command_output(
            "which rez", return_code=1, stderr="rez: command not found"
        )

        # Setup default success
        self.test_subprocess.return_code = 0
        self.test_subprocess.stdout = "Nuke launched"

        # Replace both subprocess.run and subprocess.Popen
        self.original_subprocess_run = subprocess.run
        self.original_subprocess_popen = subprocess.Popen
        subprocess.run = self.subprocess_double.run
        subprocess.Popen = self.subprocess_double.Popen

        # Also replace in the command_launcher module
        command_launcher.subprocess.run = self.subprocess_double.run
        command_launcher.subprocess.Popen = self.subprocess_double.Popen

    def teardown_method(self):
        """Restore original subprocess methods."""
        subprocess.run = self.original_subprocess_run
        subprocess.Popen = self.original_subprocess_popen
        command_launcher.subprocess.run = self.original_subprocess_run
        command_launcher.subprocess.Popen = self.original_subprocess_popen

    def test_nuke_with_raw_plate(self):
        """Test Nuke launching with raw plate integration."""

        # Create test doubles for dependencies
        class TestRawPlateFinder:
            @staticmethod
            def find_latest_raw_plate(workspace_path: str, shot_name: str) -> str:
                return "/path/to/plate.%04d.exr"

            @staticmethod
            def verify_plate_exists(plate_path: str) -> bool:
                return True

            @staticmethod
            def get_version_from_path(plate_path: str) -> str:
                return "v001"

        class TestNukeScriptGenerator:
            @staticmethod
            def create_plate_script(plate_path: str, shot_name: str) -> str:
                return "/tmp/script.nk"

        # Use dependency injection instead of module-level replacement
        launcher = CommandLauncher(
            raw_plate_finder=TestRawPlateFinder,
            nuke_script_generator=TestNukeScriptGenerator,
        )

        # Set shot and launch with raw plate
        shot = Shot(
            show="test",
            sequence="seq01",
            shot="0010",
            workspace_path="/shows/test/shots/seq01/seq01_0010",
        )
        launcher.set_current_shot(shot)

        result = launcher.launch_app("nuke", include_raw_plate=True)

        assert result is True
        assert len(self.test_subprocess.executed_commands) > 0

    def test_nuke_with_undistortion(self):
        """Test Nuke launching with undistortion."""

        # Create test double for UndistortionFinder
        class TestUndistortionFinder:
            @staticmethod
            def find_latest_undistortion(workspace_path: str, shot_name: str) -> Path:
                return Path("/path/to/undist.nk")

            @staticmethod
            def get_version_from_path(undist_path: Path) -> str:
                return "v001"

        # Use dependency injection instead of module-level replacement
        launcher = CommandLauncher(
            undistortion_finder=TestUndistortionFinder,
        )

        shot = Shot(
            show="test",
            sequence="seq01",
            shot="0010",
            workspace_path="/shows/test/shots/seq01/seq01_0010",
        )
        launcher.set_current_shot(shot)

        result = launcher.launch_app("nuke", include_undistortion=True)

        assert result is True

    def test_nuke_with_both_options(self):
        """Test Nuke with both raw plate and undistortion."""

        # Create test doubles for both finders
        class TestRawPlateFinder:
            @staticmethod
            def find_latest_raw_plate(workspace_path: str, shot_name: str) -> str:
                return "/path/to/plate.%04d.exr"

            @staticmethod
            def verify_plate_exists(plate_path: str) -> bool:
                return True

            @staticmethod
            def get_version_from_path(plate_path: str) -> str:
                return "v001"

        class TestUndistortionFinder:
            @staticmethod
            def find_latest_undistortion(workspace_path: str, shot_name: str) -> Path:
                return Path("/path/to/undist.nk")

            @staticmethod
            def get_version_from_path(undist_path: Path) -> str:
                return "v001"

        class TestNukeScriptGenerator:
            @staticmethod
            def create_plate_script_with_undistortion(
                plate_path: str, undistortion_path: str, shot_name: str
            ) -> str:
                return "/tmp/integrated_script.nk"

            @staticmethod
            def create_loader_script(
                plate_path: str, undistortion_path: str, shot_name: str
            ) -> str:
                return "/tmp/integrated_script.nk"

        # Use dependency injection for all dependencies
        launcher = CommandLauncher(
            raw_plate_finder=TestRawPlateFinder,
            undistortion_finder=TestUndistortionFinder,
            nuke_script_generator=TestNukeScriptGenerator,
        )

        shot = Shot(
            show="test",
            sequence="seq01",
            shot="0010",
            workspace_path="/shows/test/shots/seq01/seq01_0010",
        )
        launcher.set_current_shot(shot)

        result = launcher.launch_app(
            "nuke", include_raw_plate=True, include_undistortion=True
        )

        assert result is True


class TestTimestampGeneration:
    """Test timestamp generation for command logging."""

    def test_timestamp_format(self):
        """Test timestamp format in signal emissions."""
        launcher = CommandLauncher()

        # Setup spy
        error_spy = QSignalSpy(launcher.command_error)

        # Trigger error to get timestamp
        launcher.launch_app("nuke")  # No shot set

        # Check signal
        assert error_spy.count() == 1
        timestamp, error = error_spy.at(0)

        # Verify timestamp format (HH:MM:SS)
        assert isinstance(timestamp, str)
        parts = timestamp.split(":")
        assert len(parts) == 3

        # Verify parts are numeric
        hours, minutes, seconds = parts
        assert hours.isdigit() and 0 <= int(hours) <= 23
        assert minutes.isdigit() and 0 <= int(minutes) <= 59
        assert seconds.replace(".", "").isdigit()  # May have decimals

    def test_consistent_timestamp_format(self):
        """Test timestamp format consistency across signals."""
        launcher = CommandLauncher()

        # Create test subprocess setup
        test_subprocess = TestSubprocess()
        subprocess_double = SubprocessModuleDouble(test_subprocess)

        # Configure rez to be unavailable
        test_subprocess.set_command_output(
            "which rez", return_code=1, stderr="rez: command not found"
        )

        # Setup test command to succeed
        test_subprocess.return_code = 0
        test_subprocess.stdout = "Command executed"

        # Replace subprocess methods
        original_subprocess_run = subprocess.run
        original_subprocess_popen = subprocess.Popen
        subprocess.run = subprocess_double.run
        subprocess.Popen = subprocess_double.Popen
        command_launcher.subprocess.run = subprocess_double.run
        command_launcher.subprocess.Popen = subprocess_double.Popen

        try:
            # Setup spies
            executed_spy = QSignalSpy(launcher.command_executed)
            error_spy = QSignalSpy(launcher.command_error)

            # Set shot for successful execution
            shot = Shot(
                show="test",
                sequence="seq01",
                shot="0010",
                workspace_path="/test/workspace",
            )
            launcher.set_current_shot(shot)

            # Trigger successful execution
            launcher.launch_app("nuke")

            # Trigger error
            launcher.launch_app("unknown_app")

            # Check both signals
            assert executed_spy.count() >= 1
            assert error_spy.count() >= 1

            # Both should have same format
            executed_timestamp = executed_spy.at(0)[0]
            error_timestamp = error_spy.at(0)[0]

            assert len(executed_timestamp.split(":")) == 3
            assert len(error_timestamp.split(":")) == 3

        finally:
            subprocess.run = original_subprocess_run
            subprocess.Popen = original_subprocess_popen
            command_launcher.subprocess.run = original_subprocess_run
            command_launcher.subprocess.Popen = original_subprocess_popen
