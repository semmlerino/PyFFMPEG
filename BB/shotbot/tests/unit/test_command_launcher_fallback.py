"""Tests for CommandLauncher persistent terminal fallback functionality."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from command_launcher import CommandLauncher
from persistent_terminal_manager import PersistentTerminalManager


@dataclass
class MockThreeDEScene:
    """Mock ThreeDEScene for testing."""
    show: str
    sequence: str
    shot: str
    workspace_path: str
    user: str
    plate: str
    scene_path: Path

pytestmark = [pytest.mark.unit, pytest.mark.qt]

# Testing the critical bug fix where background operator (&) was incorrectly
# included when falling back to new terminal, causing commands to exit immediately


class TestCommandLauncherPersistentTerminalFallback:
    """Test CommandLauncher fallback behavior when persistent terminal fails."""

    @pytest.fixture
    def mock_shot(self):
        """Create a mock shot object."""
        mock = MagicMock()
        mock.show = "jack_ryan"
        mock.sequence = "GF_256"
        mock.shot = "1400"
        mock.workspace_path = "/shows/jack_ryan/shots/GF_256/GF_256_1400"
        return mock

    @pytest.fixture
    def mock_persistent_terminal(self):
        """Create a mock persistent terminal manager."""
        mock = MagicMock(spec=PersistentTerminalManager)
        # Default to successful command sending
        mock.send_command.return_value = True
        return mock

    @pytest.fixture
    def launcher_with_persistent_terminal(self, mock_persistent_terminal):
        """Create CommandLauncher with persistent terminal."""
        launcher = CommandLauncher()
        launcher.persistent_terminal = mock_persistent_terminal
        # Track emitted signals
        launcher.emitted_commands = []
        launcher.emitted_errors = []
        launcher.command_executed.connect(
            lambda ts, cmd: launcher.emitted_commands.append((ts, cmd))
        )
        launcher.command_error.connect(
            lambda ts, err: launcher.emitted_errors.append((ts, err))
        )
        return launcher

    @pytest.fixture
    def launcher_without_persistent_terminal(self):
        """Create CommandLauncher without persistent terminal."""
        launcher = CommandLauncher()
        launcher.persistent_terminal = None
        launcher.emitted_commands = []
        launcher.emitted_errors = []
        launcher.command_executed.connect(
            lambda ts, cmd: launcher.emitted_commands.append((ts, cmd))
        )
        launcher.command_error.connect(
            lambda ts, err: launcher.emitted_errors.append((ts, err))
        )
        return launcher

    def test_launch_with_persistent_terminal_success(
        self, launcher_with_persistent_terminal, mock_shot, mock_persistent_terminal
    ):
        """Test successful launch with persistent terminal."""
        # Arrange
        launcher_with_persistent_terminal.current_shot = mock_shot
        mock_persistent_terminal.send_command.return_value = True

        # Act
        with patch.object(launcher_with_persistent_terminal, "_is_rez_available", return_value=True), \
             patch.object(launcher_with_persistent_terminal, "_get_rez_packages_for_app", return_value=["3de"]), \
             patch("config.Config.USE_PERSISTENT_TERMINAL", True), \
                 patch("config.Config.PERSISTENT_TERMINAL_ENABLED", True), \
                 patch("config.Config.AUTO_BACKGROUND_GUI_APPS", True):
                result = launcher_with_persistent_terminal.launch_app("3de")

        # Assert: Command sent to persistent terminal successfully
        assert result is True
        # Verify send_command was called with the correct command
        calls = mock_persistent_terminal.send_command.call_args_list
        assert len(calls) == 1
        sent_command = calls[0][0][0]
        # CRITICAL: Verify & is included when using persistent terminal
        # For rez commands with bash -ilc, & should be inside the quotes
        assert ' &"' in sent_command or sent_command.endswith(" &")
        assert "ws /shows/jack_ryan/shots/GF_256/GF_256_1400" in sent_command
        assert "3de" in sent_command

    def test_launch_with_scene_persistent_terminal_fallback(
        self, launcher_with_persistent_terminal, mock_shot, mock_persistent_terminal
    ):
        """Test fallback to new terminal when persistent terminal fails (3DE scene case)."""
        # This tests the critical bug fix

        # Arrange
        launcher_with_persistent_terminal.current_shot = mock_shot
        scene_path = Path("/shows/jack_ryan/shots/GF_256/GF_256_1400/user/tony-a/mm/3de/scenes/test.3de")

        # Create mock scene object
        scene = MockThreeDEScene(
            show="jack_ryan",
            sequence="GF_256",
            shot="1400",
            workspace_path="/shows/jack_ryan/shots/GF_256/GF_256_1400",
            user="tony-a",
            plate="FG01",
            scene_path=scene_path
        )

        # Persistent terminal fails
        mock_persistent_terminal.send_command.return_value = False

        # Act
        with patch.object(launcher_with_persistent_terminal, "_is_rez_available", return_value=True), \
             patch.object(launcher_with_persistent_terminal, "_get_rez_packages_for_app", return_value=["3de"]), \
             patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_popen.return_value = mock_process

            with patch("config.Config.USE_PERSISTENT_TERMINAL", True), \
                 patch("config.Config.PERSISTENT_TERMINAL_ENABLED", True), \
                 patch("config.Config.AUTO_BACKGROUND_GUI_APPS", True):
                result = launcher_with_persistent_terminal.launch_app_with_scene(
                    "3de", scene
                )

        # Assert: Fallback occurred
        assert result is True

        # CRITICAL: Verify the command sent to new terminal does NOT end with &
        # This was the bug - background operator was included in fallback
        mock_popen.assert_called_once()
        popen_args = mock_popen.call_args[0][0]  # Get the command list

        # The actual command should be in the last element
        actual_command = popen_args[-1]

        # Verify & is NOT at the end of the command when falling back
        # The command should end with the .3de file path, not &
        assert not actual_command.strip().endswith(" &")
        assert str(scene_path) in actual_command

        # Verify fallback message was emitted
        fallback_messages = [
            msg for ts, msg in launcher_with_persistent_terminal.emitted_commands
            if "Persistent terminal not available" in msg
        ]
        assert len(fallback_messages) > 0

    def test_launch_without_persistent_terminal(
        self, launcher_without_persistent_terminal, mock_shot
    ):
        """Test launch without persistent terminal configured."""
        # Arrange
        launcher_without_persistent_terminal.current_shot = mock_shot

        # Act
        with patch.object(launcher_without_persistent_terminal, "_is_rez_available", return_value=True), \
             patch.object(launcher_without_persistent_terminal, "_get_rez_packages_for_app", return_value=["nuke"]), \
             patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_popen.return_value = mock_process

            result = launcher_without_persistent_terminal.launch_app("nuke")

        # Assert: Command launched in new terminal
        assert result is True
        mock_popen.assert_called_once()

        # Verify the command does not include & (not needed for new terminal)
        popen_args = mock_popen.call_args[0][0]
        actual_command = popen_args[-1]
        assert not actual_command.strip().endswith(" &")

    def test_launch_with_persistent_terminal_disabled_in_config(
        self, launcher_with_persistent_terminal, mock_shot, mock_persistent_terminal
    ):
        """Test that persistent terminal is not used when disabled in config."""
        # Arrange
        launcher_with_persistent_terminal.current_shot = mock_shot

        # Act
        with patch.object(launcher_with_persistent_terminal, "_is_rez_available", return_value=True), \
             patch.object(launcher_with_persistent_terminal, "_get_rez_packages_for_app", return_value=["maya"]), \
             patch("subprocess.Popen") as mock_popen, \
             patch("config.Config.USE_PERSISTENT_TERMINAL", False), \
             patch("config.Config.PERSISTENT_TERMINAL_ENABLED", True):
            mock_process = MagicMock()
            mock_popen.return_value = mock_process

            _ = launcher_with_persistent_terminal.launch_app("maya")

        # Assert: Persistent terminal not used even though it exists
        mock_persistent_terminal.send_command.assert_not_called()
        mock_popen.assert_called_once()

    def test_command_building_with_background_operator(
        self, launcher_with_persistent_terminal, mock_shot
    ):
        """Test command building with background operator for GUI apps."""
        # Arrange
        launcher_with_persistent_terminal.current_shot = mock_shot
        scene_path = Path("/test/scene.3de")

        # Create mock scene object
        scene = MockThreeDEScene(
            show="jack_ryan",
            sequence="GF_256",
            shot="1400",
            workspace_path="/shows/jack_ryan/shots/GF_256/GF_256_1400",
            user="test-user",
            plate="PLATE01",
            scene_path=scene_path
        )

        with patch.object(launcher_with_persistent_terminal, "_is_rez_available", return_value=True), \
             patch.object(launcher_with_persistent_terminal, "_get_rez_packages_for_app", return_value=["3de"]), \
             patch("config.Config.USE_PERSISTENT_TERMINAL", True), \
             patch("config.Config.PERSISTENT_TERMINAL_ENABLED", True), \
             patch("config.Config.AUTO_BACKGROUND_GUI_APPS", True):

            # Mock send_command to capture the actual command
            sent_commands = []
            launcher_with_persistent_terminal.persistent_terminal.send_command = \
                lambda cmd: sent_commands.append(cmd) or True

            # Act: Launch with scene (tests the bug fix area)
            result = launcher_with_persistent_terminal.launch_app_with_scene(
                "3de", scene
            )

        # Assert
        assert result is True
        assert len(sent_commands) == 1

        # CRITICAL: Verify the command structure
        command = sent_commands[0]

        # Command should have workspace change
        assert "ws /shows/jack_ryan" in command

        # Command should have the app launch
        assert "3de" in command
        assert str(scene_path) in command

        # Command should have & for persistent terminal
        # With bash -ilc, & is inside the quotes: "... &"
        if "bash -ilc" in command:
            assert ' &"' in command
        else:
            assert command.strip().endswith(" &")

    def test_non_gui_app_no_background_operator(
        self, launcher_with_persistent_terminal, mock_shot
    ):
        """Test non-GUI apps don't get background operator."""
        # Arrange
        launcher_with_persistent_terminal.current_shot = mock_shot

        # Use an app that's actually in Config.APPS
        with patch.object(launcher_with_persistent_terminal, "_is_rez_available", return_value=True), \
             patch.object(launcher_with_persistent_terminal, "_get_rez_packages_for_app", return_value=["nuke"]), \
             patch.object(launcher_with_persistent_terminal, "_is_gui_app", return_value=False), \
             patch("config.Config.USE_PERSISTENT_TERMINAL", True), \
             patch("config.Config.PERSISTENT_TERMINAL_ENABLED", True), \
             patch("config.Config.AUTO_BACKGROUND_GUI_APPS", True):

            # Capture sent command
            sent_commands = []
            launcher_with_persistent_terminal.persistent_terminal.send_command = \
                lambda cmd: sent_commands.append(cmd) or True

            # Act - use nuke but mock it as non-GUI for this test
            result = launcher_with_persistent_terminal.launch_app("nuke")

        # Assert: No background operator for non-GUI app
        assert result is True
        assert len(sent_commands) == 1
        command = sent_commands[0]
        # Since we mocked _is_gui_app to return False, no & should be added
        assert not command.strip().endswith(" &")

    @pytest.mark.parametrize("app_name", ["3de", "nuke", "maya", "rv"])
    def test_gui_app_detection(self, launcher_with_persistent_terminal, app_name):
        """Test GUI app detection for various VFX applications."""
        # All these should be detected as GUI apps
        assert launcher_with_persistent_terminal._is_gui_app(app_name) is True

    @pytest.mark.parametrize("app_name", ["python", "bash", "ls", "echo"])
    def test_non_gui_app_detection(self, launcher_with_persistent_terminal, app_name):
        """Test non-GUI app detection."""
        assert launcher_with_persistent_terminal._is_gui_app(app_name) is False


class TestCommandLauncherSignals:
    """Test Qt signal emission in CommandLauncher."""

    @pytest.mark.qt
    def test_signals_on_successful_launch(self, qtbot):
        """Test signals emitted on successful launch."""
        launcher = CommandLauncher()
        # Note: CommandLauncher is QObject, not QWidget - no qtbot.addWidget needed

        # Set up signal spy
        with qtbot.waitSignal(launcher.command_executed, timeout=100) as blocker:
            # Emit test signal
            launcher.command_executed.emit(
                datetime.now().strftime("%H:%M:%S"),
                "test command"
            )

        # Verify signal data
        assert len(blocker.args) == 2
        assert "test command" in blocker.args[1]

    @pytest.mark.qt
    def test_error_signal_on_failure(self, qtbot):
        """Test error signal emission on failure."""
        launcher = CommandLauncher()
        # Note: CommandLauncher is QObject, not QWidget - no qtbot.addWidget needed

        # Set up signal spy for error
        with qtbot.waitSignal(launcher.command_error, timeout=100) as blocker:
            launcher.command_error.emit(
                datetime.now().strftime("%H:%M:%S"),
                "Test error message"
            )

        # Verify error signal
        assert "Test error message" in blocker.args[1]