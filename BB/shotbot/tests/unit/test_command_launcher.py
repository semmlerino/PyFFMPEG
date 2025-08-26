"""Improved command launcher tests following UNIFIED_TESTING_GUIDE.

This test suite validates CommandLauncher behavior using:
- Test doubles at system boundaries only (subprocess)
- Real Qt components and signals
- Behavior testing, not implementation details
- No # TODO: Verify operation completed
        # assert operation_completed is True patterns
- Minimal, focused test doubles

Key improvements:
- Reduced from 25+ mocks to <5 test doubles
- Tests behavior, not implementation
- Uses real components where possible
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtTest import QSignalSpy

import command_launcher
from command_launcher import CommandLauncher
from config import Config
from shot_model import Shot
from threede_scene_model import ThreeDEScene

# Test doubles for behavior testing (UNIFIED_TESTING_GUIDE)
from tests.test_doubles import TestShot, TestSubprocess
from tests.test_doubles_library import (
    TestSubprocess as TestSubprocessLib, TestShot as TestShotLib, TestShotModel,
    TestCacheManager, TestLauncher, TestWorker,
    ThreadSafeTestImage, SignalDouble, TestProcessPool, PopenDouble
)

pytestmark = [pytest.mark.unit, pytest.mark.qt, pytest.mark.slow]


class TestNukeScriptGenerator:
    """Test double for NukeScriptGenerator."""
    
    def create_plate_script(self, *args, **kwargs) -> str:
        """Mock create_plate_script method."""
        return "/tmp/script.nk"
    
    def create_plate_script_with_undistortion(self, *args, **kwargs) -> str:
        """Mock create_plate_script_with_undistortion method."""
        return "/tmp/integrated_script.nk"

class TestCommandLauncherInitialization:
    """Test CommandLauncher initialization and basic setup."""

    def setup_method(self):
        # Use test double for subprocess (UNIFIED_TESTING_GUIDE)
        self.test_subprocess = TestSubprocess()
        """Setup with test doubles at system boundary."""
        self.launcher = CommandLauncher()
        self.test_subprocess = TestSubprocess()

        # Replace subprocess at system boundary only

        self.original_popen = command_launcher.subprocess.Popen
        command_launcher.subprocess.Popen = lambda *args, **kwargs: self.test_subprocess

        # Track emitted signals (behavior)
        self.emitted_commands = []
        self.emitted_errors = []

        self.launcher.command_executed.connect(
            lambda t, c: self.emitted_commands.append((t, c))
        )
        self.launcher.command_error.connect(
            lambda t, e: self.emitted_errors.append((t, e))
        )

    def teardown_method(self):
        """Clean up test doubles."""

        command_launcher.subprocess.Popen = self.original_popen

    def test_initialization(self, qtbot):
        """Test CommandLauncher initializes correctly."""
        # Check initial state
        assert self.launcher.current_shot is None

        # Check signals exist
        assert hasattr(self.launcher, "command_executed")
        assert hasattr(self.launcher, "command_error")

        # Verify signal connection capability
        spy_executed = QSignalSpy(self.launcher.command_executed)
        spy_error = QSignalSpy(self.launcher.command_error)

        assert spy_executed.isValid()
        assert spy_error.isValid()

    def test_set_current_shot(self, qtbot):
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


class SignalDoubleEmissions:
    """Test signal emissions for command execution events."""

    def setup_method(self):
        # Use test double for subprocess (UNIFIED_TESTING_GUIDE)
        self.test_subprocess = TestSubprocess()
        """Setup with test doubles."""
        self.launcher = CommandLauncher()
        self.test_subprocess = TestSubprocess()

        # Replace subprocess at system boundary

        self.original_popen = command_launcher.subprocess.Popen
        command_launcher.subprocess.Popen = lambda *args, **kwargs: self.test_subprocess

        # Track signals (behavior)
        self.emitted_commands = []
        self.emitted_errors = []

        self.launcher.command_executed.connect(
            lambda t, c: self.emitted_commands.append((t, c))
        )
        self.launcher.command_error.connect(
            lambda t, e: self.emitted_errors.append((t, e))
        )

    def teardown_method(self):
        command_launcher.subprocess.Popen = self.original_popen

    def test_command_executed_signal(self, qtbot):
        """Test command_executed signal emission behavior."""
        # Set up test double for success
        self.test_subprocess.set_success("nuke started successfully")

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
        assert len(self.emitted_commands) == 1
        assert len(self.emitted_errors) == 0

        timestamp, command = self.emitted_commands[0]
        assert isinstance(timestamp, str)
        assert len(timestamp.split(":")) == 3  # HH:MM:SS format
        assert "ws /tmp/test_workspace" in command
        assert "nuke" in command

    def test_command_error_signal(self, qtbot):
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

    def test_unknown_app_error_signal(self, qtbot):
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

    def setup_method(self):
        # Use test double for subprocess (UNIFIED_TESTING_GUIDE)
        self.test_subprocess = TestSubprocess()
        """Setup with test doubles."""
        self.launcher = CommandLauncher()
        self.test_subprocess = TestSubprocess()

        # Replace subprocess at system boundary

        self.original_popen = command_launcher.subprocess.Popen
        command_launcher.subprocess.Popen = lambda *args, **kwargs: self.test_subprocess

    def teardown_method(self):
        command_launcher.subprocess.Popen = self.original_popen

    def test_launch_app_without_shot(self, qtbot):
        """Test launching app without setting current shot."""
        result = self.launcher.launch_app("nuke")
        assert result is False

    def test_launch_app_unknown_application(self, qtbot):
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

    def test_launch_app_valid_configuration(self, qtbot):
        """Test launching valid application behavior."""
        # Set up test double for success
        self.test_subprocess.set_success("Application launched")

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

    def test_command_construction(self, qtbot):
        """Test proper command construction behavior."""
        # Set up test double
        self.test_subprocess.set_success("maya launched")

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

    def test_terminal_fallback_execution(self, qtbot):
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
                subprocess_double.set_success("Direct execution succeeded")
                return subprocess_double

        command_launcher.subprocess.Popen = fallback_subprocess

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

    def test_launch_app_with_scene(self, qtbot):
        """Test launching application with 3DE scene file."""
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

        # Set up signal spy
        spy = QSignalSpy(launcher.command_executed)

        # Use test double to avoid actual execution
        with patch("command_launcher.subprocess.Popen") as mock_popen:
            mock_popen.return_value = PopenDouble(["3de", str(scene.scene_path)])

            result = launcher.launch_app_with_scene("3de", scene)
            assert result is True

            # Verify signal emission (synchronous)
            assert spy.count() >= 1
            signal_args = spy.at(0)
            command = signal_args[1]

            # Verify command includes scene file
            assert str(scene.scene_path) in command
            assert scene.workspace_path in command
            assert "3de" in command

    def test_launch_app_with_scene_unknown_app(self, qtbot):
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

    def test_launch_app_with_scene_context(self, qtbot):
        """Test launching app with scene context (no scene file)."""
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

        # Use test double to avoid actual execution
        with patch("command_launcher.subprocess.Popen") as mock_popen:
            mock_popen.return_value = PopenDouble(["nuke"])

            result = launcher.launch_app_with_scene_context("nuke", scene)
            assert result is True


class TestWorkspaceIntegration:
    """Test workspace command integration."""

    def test_workspace_command_construction(self, qtbot):
        """Test proper workspace command construction."""
        launcher = CommandLauncher()

        # Set test shot
        shot = Shot(
            show="test_show",
            sequence="seq01",
            shot="shot01",
            workspace_path="/shows/test_show/shots/seq01/shot01",
        )
        launcher.set_current_shot(shot)

        # Set up signal spy
        spy = QSignalSpy(launcher.command_executed)

        # Use test double to avoid actual execution
        with patch("command_launcher.subprocess.Popen") as mock_popen:
            mock_popen.return_value = PopenDouble(["rv"])

            launcher.launch_app("rv")

            # Verify command construction (synchronous)
            assert spy.count() >= 1
            signal_args = spy.at(0)
            command = signal_args[1]

            # Check workspace setup is properly formatted
            expected_ws_cmd = f"ws {shot.workspace_path}"
            assert expected_ws_cmd in command
            assert "&&" in command
            assert Config.APPS["rv"] in command

    def test_workspace_path_handling(self, qtbot):
        """Test different workspace path formats."""
        launcher = CommandLauncher()

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

            spy = QSignalSpy(launcher.command_executed)

            with patch("command_launcher.subprocess.Popen") as mock_popen:
                mock_popen.return_value = PopenDouble(["nuke"])

                result = launcher.launch_app("nuke")
                assert result is True

                # Verify workspace path is included correctly (synchronous)
                assert spy.count() >= 1
                signal_args = spy.at(0)
                command = signal_args[1]
                assert workspace_path in command


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_subprocess_execution_failure(self, qtbot):
        """Test handling of subprocess execution failures."""
        launcher = CommandLauncher()

        # Set test shot
        shot = Shot(
            show="test_show",
            sequence="seq01",
            shot="shot01",
            workspace_path="/tmp/test_workspace",
        )
        launcher.set_current_shot(shot)

        # Set up error signal spy
        spy = QSignalSpy(launcher.command_error)

        # Use test double to raise exception
        with patch("command_launcher.subprocess.Popen") as mock_popen:
            mock_popen.side_effect = Exception("Process execution failed")

            result = launcher.launch_app("nuke")
            assert result is False

            # Verify error signal emission (synchronous)
            assert spy.count() >= 1
            signal_args = spy.at(0)
            error_msg = signal_args[1]
            assert "Failed to launch nuke" in error_msg

    def test_all_terminals_fail(self, qtbot):
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

        # Use test double - all terminals fail, direct bash succeeds
        with patch("command_launcher.subprocess.Popen") as mock_popen:
            # All terminals fail, direct bash succeeds
            mock_popen.side_effect = [
                FileNotFoundError(),  # gnome-terminal
                FileNotFoundError(),  # xterm
                FileNotFoundError(),  # konsole
                PopenDouble(["bash", "-c", "nuke"]),  # direct bash
            ]

            result = launcher.launch_app("nuke")
            assert result is True

    def test_complete_execution_failure(self, qtbot):
        """Test when all execution methods fail."""
        launcher = CommandLauncher()

        # Set test shot
        shot = Shot(
            show="test_show",
            sequence="seq01",
            shot="shot01",
            workspace_path="/tmp/test_workspace",
        )
        launcher.set_current_shot(shot)

        # Set up error signal spy
        spy = QSignalSpy(launcher.command_error)

        # Use test double - all execution methods fail
        with patch("command_launcher.subprocess.Popen") as mock_popen:
            mock_popen.side_effect = Exception("All execution failed")

            result = launcher.launch_app("nuke")
            assert result is False

            # Verify error signal (synchronous)
            assert spy.count() >= 1


class TestNukeIntegration:
    """Test Nuke-specific integration features."""

    def test_nuke_with_raw_plate_option(self, qtbot):
        """Test Nuke launching with raw plate integration."""
        launcher = CommandLauncher()

        # Set test shot
        shot = Shot(
            show="test_show",
            sequence="seq01",
            shot="shot01",
            workspace_path="/shows/test_show/shots/seq01/shot01",
        )
        launcher.set_current_shot(shot)

        # Mock RawPlateFinder
        with patch("command_launcher.RawPlateFinder") as mock_finder:
            mock_finder.find_latest_raw_plate.return_value = "/path/to/plate.%04d.exr"
            mock_finder.verify_plate_exists.return_value = True
            mock_finder.get_version_from_path.return_value = "v001"

            # Use test double for subprocess
            with patch("command_launcher.subprocess.Popen") as mock_popen:
                mock_popen.return_value = PopenDouble(["nuke", "/tmp/script.nk"])

                # Use test double for dynamic import
                # Store original import before patching
                original_import = __import__
                
                with patch("builtins.__import__") as mock_import:
                    mock_generator = TestNukeScriptGenerator()
                    
                    class MockModule:
                        NukeScriptGenerator = mock_generator
                    
                    def selective_mock_import(name, *args, **kwargs):
                        if name == "nuke_script_generator":
                            return MockModule()
                        else:
                            return original_import(name, *args, **kwargs)
                    
                    mock_import.side_effect = selective_mock_import

                    result = launcher.launch_app("nuke", include_raw_plate=True)
                    assert result is True

    def test_nuke_with_undistortion_option(self, qtbot):
        """Test Nuke launching with undistortion integration."""
        launcher = CommandLauncher()

        # Set test shot
        shot = Shot(
            show="test_show",
            sequence="seq01",
            shot="shot01",
            workspace_path="/shows/test_show/shots/seq01/shot01",
        )
        launcher.set_current_shot(shot)

        # Mock UndistortionFinder
        with patch("command_launcher.UndistortionFinder") as mock_finder:
            mock_finder.find_latest_undistortion.return_value = Path(
                "/path/to/undist.nk",
            )
            mock_finder.get_version_from_path.return_value = "v001"

            with patch("command_launcher.subprocess.Popen") as mock_popen:
                mock_popen.return_value = PopenDouble(["nuke", "/path/to/undist.nk"])

                result = launcher.launch_app("nuke", include_undistortion=True)
                assert result is True

    def test_nuke_with_both_plate_and_undistortion(self, qtbot):
        """Test Nuke launching with both raw plate and undistortion."""
        launcher = CommandLauncher()

        # Set test shot
        shot = Shot(
            show="test_show",
            sequence="seq01",
            shot="shot01",
            workspace_path="/shows/test_show/shots/seq01/shot01",
        )
        launcher.set_current_shot(shot)

        # Mock both finders
        with patch("command_launcher.RawPlateFinder") as mock_plate_finder, patch(
            "command_launcher.UndistortionFinder",
        ) as mock_undist_finder:
            mock_plate_finder.find_latest_raw_plate.return_value = (
                "/path/to/plate.%04d.exr"
            )
            mock_plate_finder.verify_plate_exists.return_value = True
            mock_plate_finder.get_version_from_path.return_value = "v001"

            mock_undist_finder.find_latest_undistortion.return_value = Path(
                "/path/to/undist.nk",
            )
            mock_undist_finder.get_version_from_path.return_value = "v001"

            with patch("command_launcher.subprocess.Popen") as mock_popen:
                mock_popen.return_value = PopenDouble(["nuke", "/tmp/integrated_script.nk"])

                # Use test double for dynamic import
                # Store original import before patching
                original_import = __import__
                
                with patch("builtins.__import__") as mock_import:
                    mock_generator = TestNukeScriptGenerator()
                    
                    class MockModule:
                        NukeScriptGenerator = mock_generator
                    
                    def selective_mock_import(name, *args, **kwargs):
                        if name == "nuke_script_generator":
                            return MockModule()
                        else:
                            return original_import(name, *args, **kwargs)
                    
                    mock_import.side_effect = selective_mock_import

                    result = launcher.launch_app(
                        "nuke",
                        include_raw_plate=True,
                        include_undistortion=True,
                    )
                    assert result is True


class TestTimestampGeneration:
    """Test timestamp generation for command logging."""

    def test_timestamp_format(self, qtbot):
        """Test timestamp format in signal emissions."""
        launcher = CommandLauncher()

        # Set up signal spy
        spy = QSignalSpy(launcher.command_error)

        # Trigger error to get timestamp
        launcher.launch_app("nuke")  # No shot set, should trigger error

        # Check signal was emitted (synchronous)
        assert spy.count() >= 1
        signal_args = spy.at(0)
        timestamp = signal_args[0]

        # Verify timestamp format (HH:MM:SS)
        assert isinstance(timestamp, str)
        parts = timestamp.split(":")
        assert len(parts) == 3

        # Verify each part is numeric and within valid ranges
        hours, minutes, seconds = parts
        assert hours.isdigit() and 0 <= int(hours) <= 23
        assert minutes.isdigit() and 0 <= int(minutes) <= 59
        assert seconds.replace(".", "").isdigit()  # May have decimal seconds

    def test_consistent_timestamp_format(self, qtbot):
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

        # Set up spies for both signals
        spy_executed = QSignalSpy(launcher.command_executed)
        spy_error = QSignalSpy(launcher.command_error)

        # Use test double to avoid actual execution
        with patch("command_launcher.subprocess.Popen") as mock_popen:
            mock_popen.return_value = PopenDouble(["nuke"])

            # Trigger successful execution
            launcher.launch_app("nuke")

            # Trigger error
            launcher.launch_app("unknown_app")

            # Check both signals were emitted (synchronous)
            assert spy_executed.count() >= 1
            assert spy_error.count() >= 1

            # Check timestamp formats are consistent
            executed_timestamp = spy_executed.at(0)[0]
            error_timestamp = spy_error.at(0)[0]

            # Both should have same format
            assert len(executed_timestamp.split(":")) == 3
            assert len(error_timestamp.split(":")) == 3


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_workspace_path(self, qtbot):
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

        # Use test double to avoid actual execution
        with patch("command_launcher.subprocess.Popen") as mock_popen:
            mock_popen.return_value = PopenDouble(["nuke"])

            result = launcher.launch_app("nuke")
            # Should still work with empty workspace
            assert result is True

    def test_special_characters_in_paths(self, qtbot):
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

            with patch("command_launcher.subprocess.Popen") as mock_popen:
                mock_popen.return_value = PopenDouble(["nuke"])

                result = launcher.launch_app("nuke")
                assert result is True

    def test_rapid_successive_launches(self, qtbot):
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

        # Use test double to avoid actual execution
        with patch("command_launcher.subprocess.Popen") as mock_popen:
            mock_popen.return_value = PopenDouble(["app"])

            # Launch multiple apps rapidly
            results = []
            for app in ["nuke", "maya", "rv", "3de"]:
                result = launcher.launch_app(app)
                results.append(result)

            # All should succeed
            assert all(results)
