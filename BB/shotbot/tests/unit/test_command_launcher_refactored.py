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
from typing import Any

import pytest
from PySide6.QtTest import QSignalSpy

import command_launcher
from command_launcher import CommandLauncher
from config import Config
from shot_model import Shot
from tests.test_doubles_extended import TestCommand
from tests.test_doubles_extended import TestProcessPoolDouble as TestProcessPool
from tests.test_doubles_library import TestShot
from threede_scene_model import ThreeDEScene

pytestmark = [pytest.mark.unit, pytest.mark.qt, pytest.mark.slow]


class TestCommandExecutor:
    """Subprocess.Popen replacement that uses TestCommand internally."""

    __test__ = False  # Prevent pytest from collecting this as a test class

    def __init__(self, test_command: TestCommand):
        self.test_command = test_command
        self.call_count = 0

    def __call__(self, cmd_list: list[str], *args: Any, **kwargs: Any) -> Any:
        """Simulate Popen execution."""
        self.call_count += 1

        # Reconstruct command string from list
        if isinstance(cmd_list, list):
            # Handle terminal commands like ["bash", "-i", "-c", "actual command"]
            if len(cmd_list) >= 3 and cmd_list[-2] == "-c":
                command = cmd_list[-1]  # The actual command is the last element
            else:
                command = " ".join(cmd_list)
        else:
            command = str(cmd_list)

        # Check if this is a terminal that should fail (for fallback testing)
        terminal_commands = ["gnome-terminal", "xterm", "konsole"]
        for term in terminal_commands:
            if term in cmd_list[0] if isinstance(cmd_list, list) else term in command:
                if self.test_command.should_fail:
                    raise FileNotFoundError(f"{term} not found")

        # Execute through test command
        try:
            result = self.test_command.execute(command)

            # Return a mock Popen-like object
            class MockPopen:
                def __init__(self, result_text: str):
                    self.stdout = result_text
                    self.stderr = ""
                    self.returncode = 0

            return MockPopen(result)
        except RuntimeError as e:
            # Simulate command failure
            if "not found" in str(e).lower():
                raise FileNotFoundError(str(e))
            raise


class TestCommandLauncherCore:
    """Core CommandLauncher tests using TestCommand."""

    def setup_method(self):
        """Setup with TestCommand at subprocess boundary."""
        self.launcher = CommandLauncher()
        self.test_command = TestCommand()
        self.executor = TestCommandExecutor(self.test_command)

        # Replace subprocess.Popen at system boundary
        self.original_popen = subprocess.Popen
        subprocess.Popen = self.executor
        command_launcher.subprocess.Popen = self.executor

        # Track emitted signals
        self.command_spy = QSignalSpy(self.launcher.command_executed)
        self.error_spy = QSignalSpy(self.launcher.command_error)

    def teardown_method(self):
        """Restore original subprocess.Popen."""
        subprocess.Popen = self.original_popen
        command_launcher.subprocess.Popen = self.original_popen

    def test_initialization(self):
        """Test CommandLauncher initializes with correct state."""
        assert self.launcher.current_shot is None
        assert hasattr(self.launcher, "command_executed")
        assert hasattr(self.launcher, "command_error")
        assert self.command_spy.isValid()
        assert self.error_spy.isValid()

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

    def test_launch_app_success(self):
        """Test successful app launch behavior."""
        # Setup test command to succeed
        self.test_command.set_output(
            "ws /shows/test/shots/seq01/seq01_0010 && nuke",
            "Nuke launched successfully",
        )

        # Set current shot
        shot = Shot(
            show="test",
            sequence="seq01",
            shot="0010",
            workspace_path="/shows/test/shots/seq01/seq01_0010",
        )
        self.launcher.set_current_shot(shot)

        # Launch app
        result = self.launcher.launch_app("nuke")

        # Verify behavior
        assert result is True
        assert self.executor.call_count > 0  # Command was executed
        assert self.command_spy.count() == 1  # Signal emitted
        assert self.error_spy.count() == 0  # No errors

        # Check signal data
        timestamp, command = self.command_spy.at(0)
        assert isinstance(timestamp, str)
        assert ":" in timestamp  # Has time format
        assert "ws /shows/test/shots/seq01/seq01_0010" in command
        assert "nuke" in command

    def test_launch_app_no_shot_selected(self):
        """Test error when no shot is selected."""
        # Don't set a shot
        result = self.launcher.launch_app("nuke")

        # Verify error behavior
        assert result is False
        assert self.executor.call_count == 0  # No command executed
        assert self.command_spy.count() == 0
        assert self.error_spy.count() == 1

        # Check error message
        timestamp, error = self.error_spy.at(0)
        assert "No shot selected" in error

    def test_launch_unknown_app(self):
        """Test error for unknown application."""
        # Set shot
        shot = Shot(
            show="test", sequence="seq01", shot="0010", workspace_path="/test/workspace"
        )
        self.launcher.set_current_shot(shot)

        # Try unknown app
        result = self.launcher.launch_app("unknown_app")

        # Verify error behavior
        assert result is False
        assert self.executor.call_count == 0
        assert self.error_spy.count() == 1

        timestamp, error = self.error_spy.at(0)
        assert "Unknown application: unknown_app" in error

    def test_terminal_fallback(self):
        """Test fallback through different terminal options."""
        # Configure to fail for terminals but succeed for direct bash
        fallback_count = [0]

        def custom_popen(cmd_list: list[str], *args: Any, **kwargs: Any) -> Any:
            fallback_count[0] += 1

            # Fail for terminal commands
            if isinstance(cmd_list, list) and len(cmd_list) > 0:
                if any(
                    term in cmd_list[0]
                    for term in ["gnome-terminal", "xterm", "konsole"]
                ):
                    raise FileNotFoundError("Terminal not found")

            # Succeed for direct bash
            class MockPopen:
                stdout = "Direct bash execution"
                stderr = ""
                returncode = 0

            return MockPopen()

        command_launcher.subprocess.Popen = custom_popen

        # Set shot and launch
        shot = Shot(
            show="test", sequence="seq01", shot="0010", workspace_path="/test/workspace"
        )
        self.launcher.set_current_shot(shot)

        result = self.launcher.launch_app("nuke")

        # Should eventually succeed with direct bash
        assert result is True
        assert fallback_count[0] >= 3  # Tried terminals then direct bash
        assert self.command_spy.count() == 1


class TestWorkspaceCommands:
    """Test workspace command integration using TestProcessPool."""

    def setup_method(self):
        """Setup with TestProcessPool for workspace commands."""
        self.launcher = CommandLauncher()
        self.process_pool = TestProcessPool()

        # Setup workspace outputs
        self.process_pool.set_outputs(
            "workspace /shows/test/shots/seq01/seq01_0010",
            "workspace /shows/test/shots/seq01/seq01_0020",
        )

        # Custom Popen that uses process pool for ws commands
        def custom_popen(cmd_list: list[str], *args: Any, **kwargs: Any) -> Any:
            # Extract command
            if (
                isinstance(cmd_list, list)
                and len(cmd_list) >= 3
                and cmd_list[-2] == "-c"
            ):
                command = cmd_list[-1]

                # Check if it's a workspace command
                if "ws " in command:
                    result = self.process_pool.execute_workspace_command(command)

                    class MockPopen:
                        stdout = result
                        stderr = ""
                        returncode = 0

                    return MockPopen()

            # Default behavior
            class MockPopen:
                stdout = "Command executed"
                stderr = ""
                returncode = 0

            return MockPopen()

        self.original_popen = subprocess.Popen
        command_launcher.subprocess.Popen = custom_popen

        # Setup spies
        self.command_spy = QSignalSpy(self.launcher.command_executed)
        self.error_spy = QSignalSpy(self.launcher.command_error)

    def teardown_method(self):
        """Restore original Popen."""
        command_launcher.subprocess.Popen = self.original_popen

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
        assert self.command_spy.count() == 1

        # Check command includes workspace
        timestamp, command = self.command_spy.at(0)
        assert "ws /shows/test/shots/seq01/seq01_0010" in command
        assert Config.APPS["maya"] in command
        assert "&&" in command  # Command chaining

        # Check process pool was used
        assert self.process_pool.get_execution_count() > 0

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
        self.test_command = TestCommand()
        self.executor = TestCommandExecutor(self.test_command)

        # Replace subprocess.Popen
        self.original_popen = subprocess.Popen
        command_launcher.subprocess.Popen = self.executor

        # Setup spies
        self.command_spy = QSignalSpy(self.launcher.command_executed)
        self.error_spy = QSignalSpy(self.launcher.command_error)

    def teardown_method(self):
        """Restore original Popen."""
        command_launcher.subprocess.Popen = self.original_popen

    def test_launch_app_with_scene(self):
        """Test launching 3DE with scene file."""
        # Configure success
        self.test_command.set_output(
            "ws /shows/test/shots/seq01/seq01_0010 && 3de /path/to/scene.3de",
            "3DE launched with scene",
        )

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
        assert self.executor.call_count > 0
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
        # Configure success
        self.test_command.set_output(
            "ws /shows/test/shots/seq01/seq01_0010 && nuke",
            "Nuke launched in scene context",
        )

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
        self.test_command = TestCommand()

        # Setup command to fail
        self.test_command.should_fail = False

        self.executor = TestCommandExecutor(self.test_command)
        self.original_popen = subprocess.Popen
        command_launcher.subprocess.Popen = self.executor

        self.error_spy = QSignalSpy(self.launcher.command_error)

    def teardown_method(self):
        """Restore original Popen."""
        command_launcher.subprocess.Popen = self.original_popen

    def test_subprocess_execution_failure(self):
        """Test handling of subprocess failures."""

        # Configure command to fail
        def failing_popen(*args: Any, **kwargs: Any) -> Any:
            raise Exception("Process execution failed")

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

        # Configure to always fail
        def always_failing(*args: Any, **kwargs: Any) -> Any:
            raise Exception("All execution failed")

        command_launcher.subprocess.Popen = always_failing

        shot = Shot(
            show="test", sequence="seq01", shot="0010", workspace_path="/test/workspace"
        )
        self.launcher.set_current_shot(shot)

        result = self.launcher.launch_app("nuke")

        assert result is False
        assert self.error_spy.count() == 1

    def test_special_characters_in_paths(self):
        """Test handling of special characters in paths."""
        # Configure success for any command
        self.test_command.default_output = "Command executed"

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
        # Empty workspace should still work
        self.test_command.default_output = "Command executed"

        shot = Shot(show="test", sequence="seq01", shot="0010", workspace_path="")
        self.launcher.set_current_shot(shot)

        result = self.launcher.launch_app("rv")
        assert result is True  # Should work with empty workspace


class TestNukeIntegration:
    """Test Nuke-specific integration features."""

    def setup_method(self):
        """Setup for Nuke tests."""
        self.launcher = CommandLauncher()
        self.test_command = TestCommand()
        self.executor = TestCommandExecutor(self.test_command)

        self.original_popen = subprocess.Popen
        command_launcher.subprocess.Popen = self.executor

        # Setup default success
        self.test_command.default_output = "Nuke launched"

    def teardown_method(self):
        """Restore original Popen."""
        command_launcher.subprocess.Popen = self.original_popen

    def test_nuke_with_raw_plate(self, monkeypatch):
        """Test Nuke launching with raw plate integration."""

        # Mock RawPlateFinder
        class MockRawPlateFinder:
            @staticmethod
            def find_latest_raw_plate(workspace_path: str, shot_name: str) -> str:
                return "/path/to/plate.%04d.exr"

            @staticmethod
            def verify_plate_exists(plate_path: str) -> bool:
                return True

            @staticmethod
            def get_version_from_path(plate_path: str) -> str:
                return "v001"

        monkeypatch.setattr("command_launcher.RawPlateFinder", MockRawPlateFinder)

        # Mock NukeScriptGenerator
        class MockNukeScriptGenerator:
            @staticmethod
            def create_plate_script(plate_path: str, shot_name: str) -> str:
                return "/tmp/script.nk"

        # Patch the dynamic import
        import builtins

        original_import = builtins.__import__

        def mock_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "nuke_script_generator":

                class MockModule:
                    NukeScriptGenerator = MockNukeScriptGenerator

                return MockModule()
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", mock_import)

        # Set shot and launch with raw plate
        shot = Shot(
            show="test",
            sequence="seq01",
            shot="0010",
            workspace_path="/shows/test/shots/seq01/seq01_0010",
        )
        self.launcher.set_current_shot(shot)

        result = self.launcher.launch_app("nuke", include_raw_plate=True)

        assert result is True
        assert self.executor.call_count > 0

    def test_nuke_with_undistortion(self, monkeypatch):
        """Test Nuke launching with undistortion."""

        # Mock UndistortionFinder
        class MockUndistortionFinder:
            @staticmethod
            def find_latest_undistortion(workspace_path: str, shot_name: str) -> Path:
                return Path("/path/to/undist.nk")

            @staticmethod
            def get_version_from_path(undist_path: Path) -> str:
                return "v001"

        monkeypatch.setattr(
            "command_launcher.UndistortionFinder", MockUndistortionFinder
        )

        shot = Shot(
            show="test",
            sequence="seq01",
            shot="0010",
            workspace_path="/shows/test/shots/seq01/seq01_0010",
        )
        self.launcher.set_current_shot(shot)

        result = self.launcher.launch_app("nuke", include_undistortion=True)

        assert result is True

    def test_nuke_with_both_options(self, monkeypatch):
        """Test Nuke with both raw plate and undistortion."""

        # Mock both finders
        class MockRawPlateFinder:
            @staticmethod
            def find_latest_raw_plate(workspace_path: str, shot_name: str) -> str:
                return "/path/to/plate.%04d.exr"

            @staticmethod
            def verify_plate_exists(plate_path: str) -> bool:
                return True

            @staticmethod
            def get_version_from_path(plate_path: str) -> str:
                return "v001"

        class MockUndistortionFinder:
            @staticmethod
            def find_latest_undistortion(workspace_path: str, shot_name: str) -> Path:
                return Path("/path/to/undist.nk")

            @staticmethod
            def get_version_from_path(undist_path: Path) -> str:
                return "v001"

        monkeypatch.setattr("command_launcher.RawPlateFinder", MockRawPlateFinder)
        monkeypatch.setattr(
            "command_launcher.UndistortionFinder", MockUndistortionFinder
        )

        # Mock NukeScriptGenerator
        class MockNukeScriptGenerator:
            @staticmethod
            def create_plate_script_with_undistortion(
                plate_path: str, undistortion_path: str, shot_name: str
            ) -> str:
                return "/tmp/integrated_script.nk"

        import builtins

        original_import = builtins.__import__

        def mock_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "nuke_script_generator":

                class MockModule:
                    NukeScriptGenerator = MockNukeScriptGenerator

                return MockModule()
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", mock_import)

        shot = Shot(
            show="test",
            sequence="seq01",
            shot="0010",
            workspace_path="/shows/test/shots/seq01/seq01_0010",
        )
        self.launcher.set_current_shot(shot)

        result = self.launcher.launch_app(
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
        test_command = TestCommand()
        executor = TestCommandExecutor(test_command)

        # Setup test command
        test_command.default_output = "Command executed"
        original_popen = subprocess.Popen
        command_launcher.subprocess.Popen = executor

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
            command_launcher.subprocess.Popen = original_popen
