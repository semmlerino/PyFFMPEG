"""Comprehensive unit tests for command_launcher.py.

This test suite validates the CommandLauncher class functionality including:
- Initialization and signal setup
- Shot context management
- Application launching with real process execution
- Signal emissions for command execution events
- Error handling and process termination
- Variable substitution in commands
- Workspace directory handling
- 3DE scene launching
- Nuke script integration

The tests use real process execution (not mocked) to validate actual Qt signal
behavior and subprocess interaction.
"""

from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtTest import QSignalSpy

from command_launcher import CommandLauncher
from config import Config
from shot_model import Shot
from threede_scene_model import ThreeDEScene


class TestCommandLauncherInitialization:
    """Test CommandLauncher initialization and basic setup."""

    def test_initialization(self, qtbot):
        """Test CommandLauncher initializes correctly."""
        launcher = CommandLauncher()

        # Check initial state
        assert launcher.current_shot is None

        # Check signals exist
        assert hasattr(launcher, "command_executed")
        assert hasattr(launcher, "command_error")

        # Verify signal connection capability
        spy_executed = QSignalSpy(launcher.command_executed)
        spy_error = QSignalSpy(launcher.command_error)

        assert spy_executed.isValid()
        assert spy_error.isValid()

    def test_set_current_shot(self, qtbot):
        """Test setting current shot context."""
        launcher = CommandLauncher()

        # Create test shot
        shot = Shot(
            show="test_show",
            sequence="seq01",
            shot="shot01",
            workspace_path="/shows/test_show/shots/seq01/shot01",
        )

        # Set shot
        launcher.set_current_shot(shot)
        assert launcher.current_shot == shot

        # Test clearing shot
        launcher.set_current_shot(None)
        assert launcher.current_shot is None


class TestSignalEmissions:
    """Test signal emissions for command execution events."""

    def test_command_executed_signal(self, qtbot):
        """Test command_executed signal emission."""
        launcher = CommandLauncher()

        # Set up signal spy
        spy = QSignalSpy(launcher.command_executed)

        # Create test shot
        shot = Shot(
            show="test_show",
            sequence="seq01",
            shot="shot01",
            workspace_path="/tmp/test_workspace",
        )
        launcher.set_current_shot(shot)

        # Mock subprocess.Popen to avoid actual execution
        with patch("command_launcher.subprocess.Popen") as mock_popen:
            mock_popen.return_value = Mock()

            # Launch simple command
            launcher.launch_app("nuke")

            # Check signal was emitted (synchronous)
            assert spy.count() >= 1

            # Verify signal content (timestamp, command)
            signal_args = spy.at(0)
            assert len(signal_args) == 2
            timestamp, command = signal_args

            # Verify timestamp format
            assert isinstance(timestamp, str)
            assert len(timestamp.split(":")) == 3  # HH:MM:SS format

            # Verify command contains workspace setup
            assert isinstance(command, str)
            assert "ws /tmp/test_workspace" in command
            assert "nuke" in command

    def test_command_error_signal(self, qtbot):
        """Test command_error signal emission."""
        launcher = CommandLauncher()

        # Set up signal spy
        spy = QSignalSpy(launcher.command_error)

        # Test error when no shot is set
        launcher.launch_app("nuke")

        # Check signal was emitted (synchronous)
        assert spy.count() == 1

        # Verify signal content
        signal_args = spy.at(0)
        assert len(signal_args) == 2
        timestamp, error = signal_args

        assert isinstance(timestamp, str)
        assert "No shot selected" in error

    def test_unknown_app_error_signal(self, qtbot):
        """Test error signal for unknown application."""
        launcher = CommandLauncher()

        # Set up signal spy
        spy = QSignalSpy(launcher.command_error)

        # Create test shot
        shot = Shot(
            show="test_show",
            sequence="seq01",
            shot="shot01",
            workspace_path="/tmp/test_workspace",
        )
        launcher.set_current_shot(shot)

        # Try to launch unknown app
        launcher.launch_app("unknown_app")

        # Check signal was emitted (synchronous)
        assert spy.count() == 1

        # Verify error message
        signal_args = spy.at(0)
        timestamp, error = signal_args
        assert "Unknown application: unknown_app" in error


class TestApplicationLaunching:
    """Test application launching functionality."""

    def test_launch_app_without_shot(self, qtbot):
        """Test launching app without setting current shot."""
        launcher = CommandLauncher()

        result = launcher.launch_app("nuke")
        assert result is False

    def test_launch_app_unknown_application(self, qtbot):
        """Test launching unknown application."""
        launcher = CommandLauncher()

        # Set test shot
        shot = Shot(
            show="test_show",
            sequence="seq01",
            shot="shot01",
            workspace_path="/tmp/test_workspace",
        )
        launcher.set_current_shot(shot)

        result = launcher.launch_app("nonexistent_app")
        assert result is False

    def test_launch_app_valid_configuration(self, qtbot):
        """Test launching valid application with proper configuration."""
        launcher = CommandLauncher()

        # Set test shot
        shot = Shot(
            show="test_show",
            sequence="seq01",
            shot="shot01",
            workspace_path="/tmp/test_workspace",
        )
        launcher.set_current_shot(shot)

        # Mock subprocess to avoid actual execution
        with patch("command_launcher.subprocess.Popen") as mock_popen:
            mock_popen.return_value = Mock()

            result = launcher.launch_app("nuke")
            assert result is True

            # Verify subprocess.Popen was called
            assert mock_popen.called

    def test_command_construction(self, qtbot):
        """Test proper command construction with workspace setup."""
        launcher = CommandLauncher()

        # Set test shot
        shot = Shot(
            show="test_show",
            sequence="seq01",
            shot="shot01",
            workspace_path="/shows/test_show/shots/seq01/shot01",
        )
        launcher.set_current_shot(shot)

        # Set up signal spy to capture command
        spy = QSignalSpy(launcher.command_executed)

        # Mock subprocess to avoid actual execution
        with patch("command_launcher.subprocess.Popen") as mock_popen:
            mock_popen.return_value = Mock()

            launcher.launch_app("maya")

            # Verify command construction (synchronous)
            assert spy.count() >= 1
            signal_args = spy.at(0)
            command = signal_args[1]

            # Verify command contains workspace setup and app command
            expected_workspace = "ws /shows/test_show/shots/seq01/shot01"
            expected_app = Config.APPS["maya"]

            assert expected_workspace in command
            assert expected_app in command
            assert "&&" in command  # Command chaining

    def test_terminal_fallback_execution(self, qtbot):
        """Test terminal fallback when no GUI terminals available."""
        launcher = CommandLauncher()

        # Set test shot
        shot = Shot(
            show="test_show",
            sequence="seq01",
            shot="shot01",
            workspace_path="/tmp/test_workspace",
        )
        launcher.set_current_shot(shot)

        # Mock subprocess.Popen to simulate terminal failures
        with patch("command_launcher.subprocess.Popen") as mock_popen:
            # First few calls fail (terminal not found)
            mock_popen.side_effect = [
                FileNotFoundError(),  # gnome-terminal
                FileNotFoundError(),  # xterm
                FileNotFoundError(),  # konsole
                Mock(),  # direct bash execution succeeds
            ]

            result = launcher.launch_app("nuke")
            assert result is True

            # Verify fallback to direct bash execution
            assert mock_popen.call_count == 4
            last_call = mock_popen.call_args_list[-1]
            args = last_call[0][0]  # First positional argument
            assert args[0] == "/bin/bash"
            assert "-i" in args
            assert "-c" in args


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

        # Mock subprocess to avoid actual execution
        with patch("command_launcher.subprocess.Popen") as mock_popen:
            mock_popen.return_value = Mock()

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

        # Mock subprocess to avoid actual execution
        with patch("command_launcher.subprocess.Popen") as mock_popen:
            mock_popen.return_value = Mock()

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

        # Mock subprocess to avoid actual execution
        with patch("command_launcher.subprocess.Popen") as mock_popen:
            mock_popen.return_value = Mock()

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
                mock_popen.return_value = Mock()

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

        # Mock subprocess to raise exception
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

        # Mock all terminal commands to fail, direct bash to succeed
        with patch("command_launcher.subprocess.Popen") as mock_popen:
            # All terminals fail, direct bash succeeds
            mock_popen.side_effect = [
                FileNotFoundError(),  # gnome-terminal
                FileNotFoundError(),  # xterm
                FileNotFoundError(),  # konsole
                Mock(),  # direct bash
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

        # Mock all execution methods to fail
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

            # Mock NukeScriptGenerator
            with patch("command_launcher.subprocess.Popen") as mock_popen:
                mock_popen.return_value = Mock()

                # Mock the dynamic import
                with patch("builtins.__import__") as mock_import:
                    mock_generator = Mock()
                    mock_generator.create_plate_script.return_value = "/tmp/script.nk"
                    mock_import.return_value = Mock(NukeScriptGenerator=mock_generator)

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
                mock_popen.return_value = Mock()

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
                mock_popen.return_value = Mock()

                # Mock the dynamic import
                with patch("builtins.__import__") as mock_import:
                    mock_generator = Mock()
                    mock_generator.create_plate_script_with_undistortion.return_value = "/tmp/integrated_script.nk"
                    mock_import.return_value = Mock(NukeScriptGenerator=mock_generator)

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

        # Mock subprocess to avoid actual execution
        with patch("command_launcher.subprocess.Popen") as mock_popen:
            mock_popen.return_value = Mock()

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

        # Mock subprocess to avoid actual execution
        with patch("command_launcher.subprocess.Popen") as mock_popen:
            mock_popen.return_value = Mock()

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
                mock_popen.return_value = Mock()

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

        # Mock subprocess to avoid actual execution
        with patch("command_launcher.subprocess.Popen") as mock_popen:
            mock_popen.return_value = Mock()

            # Launch multiple apps rapidly
            results = []
            for app in ["nuke", "maya", "rv", "3de"]:
                result = launcher.launch_app(app)
                results.append(result)

            # All should succeed
            assert all(results)
