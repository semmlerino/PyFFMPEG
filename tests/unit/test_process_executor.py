"""Tests for ProcessExecutor component.

This test suite provides comprehensive coverage of process execution:
- New terminal window launching
- Process verification
- Signal emission and handling
- GUI app detection
"""

from unittest.mock import MagicMock, patch

import pytest
from pytestqt.qtbot import QtBot

from config import Config
from launch.process_executor import ProcessExecutor


@pytest.fixture
def mock_config() -> MagicMock:
    """Create a mock Config object."""
    return MagicMock(spec=Config)


@pytest.fixture
def executor(mock_config: MagicMock) -> ProcessExecutor:
    """Create a ProcessExecutor with mocked dependencies."""
    return ProcessExecutor(mock_config)


class TestGuiAppDetection:
    """Tests for GUI application detection."""

    def test_nuke_is_gui_app(self, executor: ProcessExecutor) -> None:
        """Test that Nuke is detected as GUI app."""
        assert executor.is_gui_app("nuke") is True

    def test_maya_is_gui_app(self, executor: ProcessExecutor) -> None:
        """Test that Maya is detected as GUI app."""
        assert executor.is_gui_app("maya") is True

    def test_3de_is_gui_app(self, executor: ProcessExecutor) -> None:
        """Test that 3DEqualizer is detected as GUI app."""
        assert executor.is_gui_app("3de") is True

    def test_rv_is_gui_app(self, executor: ProcessExecutor) -> None:
        """Test that RV is detected as GUI app."""
        assert executor.is_gui_app("rv") is True

    def test_case_insensitive(self, executor: ProcessExecutor) -> None:
        """Test that GUI app detection is case insensitive."""
        assert executor.is_gui_app("NUKE") is True
        assert executor.is_gui_app("Nuke") is True
        assert executor.is_gui_app("nuKE") is True

    def test_unknown_app_is_not_gui(self, executor: ProcessExecutor) -> None:
        """Test that unknown apps are not detected as GUI apps."""
        assert executor.is_gui_app("unknown") is False
        assert executor.is_gui_app("python") is False
        assert executor.is_gui_app("bash") is False


class TestNewTerminalExecution:
    """Tests for new terminal window execution."""

    @patch("subprocess.Popen")
    @patch("launch.process_executor.QTimer")
    def test_gnome_terminal_execution(
        self,
        mock_timer_class: MagicMock,
        mock_popen: MagicMock,
        executor: ProcessExecutor,
    ) -> None:
        """Test execution in gnome-terminal."""
        mock_process = MagicMock()
        mock_popen.return_value = mock_process
        mock_timer = MagicMock()
        mock_timer_class.return_value = mock_timer

        result = executor.execute_in_new_terminal("nuke", "nuke", "gnome-terminal")

        assert result is True
        mock_popen.assert_called_once_with(
            ["gnome-terminal", "--", "bash", "-ilc", "nuke"]
        )
        # Verify process verification timer was created and started
        mock_timer.setSingleShot.assert_called_once_with(True)
        mock_timer.setInterval.assert_called_once_with(100)
        mock_timer.start.assert_called_once()

    @patch("subprocess.Popen")
    @patch("launch.process_executor.QTimer")
    def test_konsole_execution(
        self,
        mock_timer_class: MagicMock,
        mock_popen: MagicMock,
        executor: ProcessExecutor,
    ) -> None:
        """Test execution in konsole."""
        mock_process = MagicMock()
        mock_popen.return_value = mock_process
        mock_timer = MagicMock()
        mock_timer_class.return_value = mock_timer

        result = executor.execute_in_new_terminal("maya", "maya", "konsole")

        assert result is True
        mock_popen.assert_called_once_with(["konsole", "-e", "bash", "-ilc", "maya"])

    @patch("subprocess.Popen")
    @patch("launch.process_executor.QTimer")
    def test_xterm_execution(
        self,
        mock_timer_class: MagicMock,
        mock_popen: MagicMock,
        executor: ProcessExecutor,
    ) -> None:
        """Test execution in xterm."""
        mock_process = MagicMock()
        mock_popen.return_value = mock_process
        mock_timer = MagicMock()
        mock_timer_class.return_value = mock_timer

        result = executor.execute_in_new_terminal("3de", "3de", "xterm")

        assert result is True
        mock_popen.assert_called_once_with(["xterm", "-e", "bash", "-ilc", "3de"])

    @patch("subprocess.Popen")
    @patch("launch.process_executor.QTimer")
    def test_fallback_execution(
        self,
        mock_timer_class: MagicMock,
        mock_popen: MagicMock,
        executor: ProcessExecutor,
    ) -> None:
        """Test fallback to direct bash execution."""
        mock_process = MagicMock()
        mock_popen.return_value = mock_process
        mock_timer = MagicMock()
        mock_timer_class.return_value = mock_timer

        result = executor.execute_in_new_terminal("unknown", "unknown", "unknown-term")

        assert result is True
        mock_popen.assert_called_once_with(["/bin/bash", "-ilc", "unknown"])


class TestProcessVerification:
    """Tests for process spawn verification."""

    @patch("launch.process_executor.NotificationManager.error")
    def test_process_crashed_immediately(
        self,
        mock_notification: MagicMock,
        executor: ProcessExecutor,
        qtbot: QtBot,
    ) -> None:
        """Test detection of immediate process crash."""
        mock_process = MagicMock()
        mock_process.poll.return_value = 1  # Non-None = process exited

        # Use wait_signal instead of signal_blocker
        with (
            qtbot.waitSignal(executor.execution_error, timeout=1000),
            qtbot.waitSignal(executor.execution_completed, timeout=1000),
        ):
            # Call verification
            executor.verify_spawn(mock_process, "nuke")

        # Verify notification was shown
        mock_notification.assert_called_once()

    def test_process_spawned_successfully(
        self, executor: ProcessExecutor, qtbot: QtBot
    ) -> None:
        """Test successful process spawn detection."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # None = process still running
        mock_process.pid = 12345

        # Use wait_signal instead of signal_blocker
        with qtbot.waitSignal(executor.execution_progress, timeout=1000):
            # Call verification
            executor.verify_spawn(mock_process, "nuke")

