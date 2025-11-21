"""Process execution management for application launching.

This module handles process execution and management:
- New terminal window launching
- Process verification
- Signal-based status reporting
"""

import logging
import subprocess
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

from PySide6.QtCore import QObject, QTimer, Signal

from notification_manager import NotificationManager


if TYPE_CHECKING:
    from config import Config

logger = logging.getLogger(__name__)


class ProcessExecutor(QObject):
    """Executes commands via terminal or subprocess.

    This class handles the actual execution of commands by spawning new terminal
    windows. It provides signal-based status reporting and handles process verification.

    Signals:
        execution_progress: Emitted for progress updates
                           Args: (timestamp: str, message: str)
        execution_completed: Emitted when execution completes
                            Args: (success: bool, error_message: str)
        execution_error: Emitted on execution errors
                        Args: (timestamp: str, error_message: str)
    """

    # Signals - type annotations for clarity
    execution_progress: Signal = Signal(str, str)  # timestamp, message
    execution_completed: Signal = Signal(bool, str)  # success, error_message
    execution_error: Signal = Signal(str, str)  # timestamp, error_message

    # Known GUI applications that should run in background
    GUI_APPS: Final[set[str]] = {
        "3de",
        "nuke",
        "maya",
        "rv",
        "houdini",
        "mari",
        "katana",
        "clarisse",
    }

    def __init__(
        self,
        config: "type[Config]",
        parent: QObject | None = None,
    ) -> None:
        """Initialize ProcessExecutor.

        Args:
            config: Application configuration class
            parent: Optional Qt parent object
        """
        super().__init__(parent)
        self.config: type[Config] = config
        self.logger: logging.Logger = logger
        self._pending_timers: list[QTimer] = []

    def is_gui_app(self, app_name: str) -> bool:
        """Check if an application is a GUI application.

        Args:
            app_name: Name of the application

        Returns:
            True if the app is a GUI application that should run in background

        Notes:
            GUI apps are typically backgrounded when launched so they don't
            block the terminal. Non-GUI apps run in foreground for interactivity.
        """
        return app_name.lower() in self.GUI_APPS

    def execute_in_new_terminal(
        self, command: str, app_name: str, terminal: str
    ) -> bool:
        """Execute command in new terminal window.

        Args:
            command: Command to execute
            app_name: Application name (for error messages and verification)
            terminal: Terminal emulator to use (gnome-terminal, konsole, xterm, etc.)

        Returns:
            True if process spawned successfully

        Raises:
            FileNotFoundError: If terminal executable not found
            PermissionError: If insufficient permissions to execute
            OSError: If other execution errors occur

        Notes:
            - Spawns new terminal window
            - Uses bash -ilc for interactive login shell (loads workspace functions)
            - Schedules process verification after 100ms
        """
        self.logger.info(f"Launching {app_name} in new {terminal} terminal")

        # Build command for the detected terminal
        if terminal == "gnome-terminal":
            term_cmd = ["gnome-terminal", "--", "bash", "-ilc", command]
        elif terminal == "konsole":
            term_cmd = ["konsole", "-e", "bash", "-ilc", command]
        elif terminal in ["xterm", "x-terminal-emulator"]:
            term_cmd = [terminal, "-e", "bash", "-ilc", command]
        else:
            # Fallback to direct execution
            term_cmd = ["/bin/bash", "-ilc", command]

        # Spawn process
        process = subprocess.Popen(term_cmd)

        # Verify spawn after 100ms (asynchronous to avoid blocking UI)
        # Use a cancellable QTimer to avoid "Signal source deleted" errors
        # when ProcessExecutor is cleaned up before the timer fires
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(100)

        # Store timer reference for cleanup
        self._pending_timers.append(timer)

        # Connect with cleanup of timer from list
        def on_timeout() -> None:
            # Check if timer was removed by cleanup() - if so, skip callback
            if timer not in self._pending_timers:
                return  # Cleanup already happened, ProcessExecutor may be deleted
            self._pending_timers.remove(timer)
            self.verify_spawn(process, app_name)
            timer.deleteLater()

        _ = timer.timeout.connect(on_timeout)
        timer.start()

        return True

    def verify_spawn(self, process: subprocess.Popen[bytes], app_name: str) -> None:
        """Verify process didn't crash immediately after spawning.

        This method polls the process after a short delay to detect immediate crashes.
        If the process has already exited, it indicates a launch failure.

        Args:
            process: The subprocess.Popen object to verify
            app_name: Name of the application being launched (for error messages)

        Notes:
            - Called via QTimer.singleShot after 100ms
            - Emits error signals if process crashed
            - Shows notification on failure
        """
        exit_code = process.poll()
        if exit_code is not None:
            # Process crashed
            timestamp = datetime.now(tz=UTC).strftime("%H:%M:%S")
            error_msg = f"{app_name} crashed immediately (exit code {exit_code})"

            try:
                self.execution_error.emit(timestamp, error_msg)
                self.execution_completed.emit(False, error_msg)
            except RuntimeError:
                # Signal source deleted - object is being cleaned up
                return

            NotificationManager.error(
                "Launch Failed", f"{app_name} crashed immediately"
            )
        else:
            # Process spawned successfully
            self.logger.debug(f"{app_name} process spawned successfully (PID {process.pid})")
            timestamp = datetime.now(tz=UTC).strftime("%H:%M:%S")
            try:
                self.execution_progress.emit(
                    timestamp, f"{app_name} started successfully (PID {process.pid})"
                )
            except RuntimeError:
                # Signal source deleted - object is being cleaned up
                pass

    def cleanup(self) -> None:
        """Cleanup resources.

        This method is called before deleting the ProcessExecutor instance.
        Stops all pending timers to prevent "Signal source deleted" errors.
        """
        # Stop and clean up all pending timers
        for timer in self._pending_timers:
            try:
                timer.stop()
                timer.deleteLater()
            except RuntimeError:
                pass  # Timer may already be deleted
        self._pending_timers.clear()
        self.logger.debug("ProcessExecutor cleanup completed")

    def __del__(self) -> None:
        """Cleanup on destruction."""
        try:
            self.cleanup()
        except Exception:
            pass  # Ignore errors in destructor

