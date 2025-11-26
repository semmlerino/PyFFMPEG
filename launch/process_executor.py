"""Process execution management for application launching.

This module handles process execution and management:
- New terminal window launching
- Process verification
- Signal-based status reporting
"""

import logging
import subprocess
import threading
import time
from datetime import UTC, datetime
from functools import partial
from typing import TYPE_CHECKING, Final

import psutil
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

    # App verification signals (for GUI app launch verification)
    app_verification_started: Signal = Signal(str)  # app_name
    app_verified: Signal = Signal(str, int)  # app_name, pid
    app_verification_failed: Signal = Signal(str, str)  # app_name, error_message
    app_verification_timeout: Signal = Signal(str)  # app_name

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

    def _build_terminal_command(self, terminal: str | None, command: str) -> list[str]:
        """Build terminal-specific command list.

        Args:
            terminal: Terminal emulator name, or None for headless execution
            command: The command to execute

        Returns:
            Command list suitable for subprocess.Popen
        """
        if terminal == "gnome-terminal":
            return ["gnome-terminal", "--", "bash", "-ilc", command]
        elif terminal == "konsole":
            return ["konsole", "-e", "bash", "-ilc", command]
        elif terminal == "kitty":
            # kitty uses different syntax: kitty bash -ilc "command"
            return ["kitty", "bash", "-ilc", command]
        elif terminal in [
            "xterm",
            "x-terminal-emulator",
            "xfce4-terminal",
            "mate-terminal",
            "alacritty",
            "terminology",
        ]:
            # These terminals all use -e flag for command execution
            return [terminal, "-e", "bash", "-ilc", command]
        else:
            # Headless fallback: direct bash execution
            return ["/bin/bash", "-ilc", command]

    def execute_in_new_terminal(
        self, command: str, app_name: str, terminal: str | None = None
    ) -> subprocess.Popen[bytes] | None:
        """Execute command in new terminal or headless if no terminal available.

        Args:
            command: Command to execute
            app_name: Application name (for error messages and verification)
            terminal: Terminal emulator name, or None for headless execution

        Returns:
            Popen object on success, None on failure

        Notes:
            - If terminal is None, executes directly via bash (headless mode)
            - Uses bash -ilc for interactive login shell (loads workspace functions)
            - Schedules process verification after 100ms
        """
        if terminal is None:
            self.logger.info(
                f"No terminal available, launching {app_name} directly (headless mode)"
            )
        else:
            self.logger.info(f"Launching {app_name} in new {terminal} terminal")

        # Build command for the detected terminal (or headless)
        term_cmd = self._build_terminal_command(terminal, command)

        try:
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

            return process

        except FileNotFoundError as e:
            self.logger.error(f"Failed to launch {app_name}: executable not found - {e}")
            return None
        except PermissionError as e:
            self.logger.error(f"Failed to launch {app_name}: permission denied - {e}")
            return None
        except OSError as e:
            self.logger.error(f"Failed to launch {app_name}: {e}")
            return None

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

    def start_app_verification(
        self,
        app_name: str,
        enqueue_time: float,
        timeout_sec: float | None = None,
        poll_interval_sec: float | None = None,
    ) -> None:
        """Start async verification that GUI app actually launched.

        This uses psutil to scan for the app process in a background thread,
        emitting signals when the process is found or verification times out.

        Args:
            app_name: Name of the application (e.g., "nuke", "maya", "3de")
            enqueue_time: Time when command was enqueued (filters out old processes)
            timeout_sec: How long to wait (default: from config)
            poll_interval_sec: How often to scan (default: from config)

        Signals emitted:
            app_verification_started: When verification begins
            app_verified: When process is found (with PID)
            app_verification_timeout: When timeout reached without finding process
            app_verification_failed: On errors
        """
        if not self.config.LAUNCH_VERIFICATION_ENABLED:
            self.logger.debug("Launch verification disabled")
            return

        if not self.is_gui_app(app_name):
            self.logger.debug(f"{app_name} is not a GUI app, skipping verification")
            return

        if timeout_sec is None:
            timeout_sec = self.config.LAUNCH_VERIFICATION_TIMEOUT_SEC
        if poll_interval_sec is None:
            poll_interval_sec = self.config.LAUNCH_VERIFICATION_POLL_SEC

        # Emit started signal
        try:
            self.app_verification_started.emit(app_name)
        except RuntimeError:
            return  # Object being cleaned up

        # Run verification in background thread
        thread = threading.Thread(
            target=self._verify_app_thread,
            args=(app_name, enqueue_time, timeout_sec, poll_interval_sec),
            daemon=True,
        )
        thread.start()

    def _verify_app_thread(
        self,
        app_name: str,
        enqueue_time: float,
        timeout_sec: float,
        poll_interval_sec: float,
    ) -> None:
        """Background thread for app verification.

        This method runs in a background thread and uses QTimer.singleShot
        to safely emit signals back to the main thread.
        """
        # Map app names to possible process names
        app_process_names: dict[str, list[str]] = {
            "nuke": ["nuke", "nuke.bin", "nukex", "nukex.bin", "nukestudio"],
            "maya": ["maya", "maya.bin", "mayapy"],
            "3de": ["3de", "3dequalizer", "tde4"],
            "rv": ["rv", "rv.bin", "rvio"],
            "houdini": ["houdini", "houdinifx", "hython"],
            "mari": ["mari", "mari.bin"],
            "katana": ["katana", "katana.bin"],
            "clarisse": ["clarisse", "cnode"],
        }
        search_names = app_process_names.get(app_name.lower(), [app_name.lower()])

        # Allow some clock skew tolerance
        clock_skew_tolerance = 2.0
        cutoff_time = enqueue_time - clock_skew_tolerance

        start_time = time.monotonic()
        while time.monotonic() - start_time < timeout_sec:
            try:
                for proc in psutil.process_iter(["name", "create_time", "pid"]):
                    try:
                        proc_name = proc.info.get("name", "").lower()
                        create_time = proc.info.get("create_time", 0)
                        proc_pid = proc.info.get("pid", 0)

                        # Check if process name matches and was created after our command
                        if any(name in proc_name for name in search_names):
                            if create_time >= cutoff_time:
                                found_pid: int = int(proc_pid) if proc_pid else 0
                                self.logger.info(
                                    f"Verified {app_name} process (PID: {found_pid})"
                                )
                                # Emit signal safely from main thread
                                QTimer.singleShot(
                                    0,
                                    partial(self._emit_verified, app_name, found_pid),
                                )
                                return
                    except (
                        psutil.NoSuchProcess,
                        psutil.AccessDenied,
                        psutil.ZombieProcess,
                    ):
                        continue
            except Exception as e:
                self.logger.warning(f"Error scanning processes: {e}")

            time.sleep(poll_interval_sec)

        # Timeout - process not found
        self.logger.warning(
            f"{app_name} process not found after {timeout_sec}s verification"
        )
        QTimer.singleShot(0, lambda: self._emit_timeout(app_name))

    def _emit_verified(self, app_name: str, pid: int) -> None:
        """Emit app_verified signal (called from main thread via QTimer)."""
        try:
            self.app_verified.emit(app_name, pid)
            timestamp = datetime.now(tz=UTC).strftime("%H:%M:%S")
            self.execution_progress.emit(
                timestamp, f"{app_name} verified running (PID: {pid})"
            )
        except RuntimeError:
            pass  # Object being cleaned up

    def _emit_timeout(self, app_name: str) -> None:
        """Emit app_verification_timeout signal (called from main thread via QTimer)."""
        try:
            self.app_verification_timeout.emit(app_name)
            timestamp = datetime.now(tz=UTC).strftime("%H:%M:%S")
            self.execution_progress.emit(
                timestamp,
                f"Note: Could not verify {app_name} process - may still be starting",
            )
        except RuntimeError:
            pass  # Object being cleaned up

    def __del__(self) -> None:
        """Cleanup on destruction."""
        try:
            self.cleanup()
        except Exception:
            pass  # Ignore errors in destructor

