"""Persistent Terminal Manager for ShotBot.

This module manages a single persistent terminal window that handles all commands,
eliminating the need to spawn new terminals for each command.
"""

from __future__ import annotations

import errno
import logging
import os
import signal
import stat
import subprocess
import time
from pathlib import Path

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)


class PersistentTerminalManager(QObject):
    """Manages a single persistent terminal for all commands."""

    # Signals
    terminal_started = Signal(int)  # PID of terminal
    terminal_closed = Signal()
    command_sent = Signal(str)  # Command that was sent

    def __init__(
        self, fifo_path: str | None = None, dispatcher_path: str | None = None
    ) -> None:
        """Initialize the persistent terminal manager.

        Args:
            fifo_path: Path to the FIFO for command communication
            dispatcher_path: Path to the terminal dispatcher script
        """
        super().__init__()

        # Set up paths
        self.fifo_path = fifo_path or "/tmp/shotbot_commands.fifo"

        # Find dispatcher script relative to this module
        if dispatcher_path:
            self.dispatcher_path = dispatcher_path
        else:
            module_dir = Path(__file__).parent
            self.dispatcher_path = str(module_dir / "terminal_dispatcher.sh")

        # Terminal state
        self.terminal_pid: int | None = None
        self.terminal_process: subprocess.Popen[bytes] | None = None

        # Ensure FIFO exists
        if not self._ensure_fifo():
            logger.warning(
                f"Failed to create FIFO at {self.fifo_path}, persistent terminal may not work properly"
            )

        logger.info(
            f"PersistentTerminalManager initialized with FIFO: {self.fifo_path}"
        )

    def _ensure_fifo(self) -> bool:
        """Ensure the FIFO exists for command communication.

        Returns:
            True if FIFO exists or was created successfully, False otherwise
        """
        if not os.path.exists(self.fifo_path):
            try:
                # Remove any existing file first (in case it's not a FIFO)
                try:
                    os.unlink(self.fifo_path)
                except FileNotFoundError:
                    pass

                os.mkfifo(self.fifo_path, 0o600)  # Only user can read/write
                logger.debug(f"Created FIFO at {self.fifo_path}")
            except OSError as e:
                logger.error(f"Could not create FIFO at {self.fifo_path}: {e}")
                return False

        # Verify it's actually a FIFO
        if not os.path.exists(self.fifo_path):
            logger.error(
                f"FIFO does not exist after creation attempt: {self.fifo_path}"
            )
            return False

        # Check if path is a FIFO using cross-platform compatible method
        try:
            file_stat = os.stat(self.fifo_path)
            if not stat.S_ISFIFO(file_stat.st_mode):
                logger.error(f"Path exists but is not a FIFO: {self.fifo_path}")
                return False
        except OSError as e:
            logger.error(f"Could not stat FIFO path {self.fifo_path}: {e}")
            return False

        return True

    def _is_dispatcher_running(self) -> bool:
        """Check if the terminal dispatcher is running and ready to read from FIFO.

        Returns:
            True if dispatcher appears to be running, False otherwise
        """
        if not os.path.exists(self.fifo_path):
            return False

        try:
            # Try to open FIFO for writing in non-blocking mode
            # If no reader is available, this will fail with ENXIO
            fd = os.open(self.fifo_path, os.O_WRONLY | os.O_NONBLOCK)
            os.close(fd)
            return True
        except OSError as e:
            if e.errno == errno.ENXIO:
                # No reader available - dispatcher not running
                return False
            # Other errors might indicate different issues
            return False

    def _is_terminal_alive(self) -> bool:
        """Check if the terminal process is still running."""
        if self.terminal_pid is None:
            return False

        try:
            # Check if process exists (doesn't actually kill it)
            os.kill(self.terminal_pid, 0)
            return True
        except ProcessLookupError:
            logger.debug(f"Terminal process {self.terminal_pid} no longer exists")
            self.terminal_pid = None
            self.terminal_process = None
            return False
        except PermissionError:
            # Process exists but we can't access it
            return True

    def _launch_terminal(self) -> bool:
        """Launch the persistent terminal with dispatcher script.

        Returns:
            True if terminal launched successfully, False otherwise
        """
        if not os.path.exists(self.dispatcher_path):
            logger.error(f"Dispatcher script not found: {self.dispatcher_path}")
            return False

        # Try different terminal emulators
        terminal_commands = [
            # gnome-terminal with title
            [
                "gnome-terminal",
                "--title=ShotBot Terminal",
                "--",
                "bash",
                self.dispatcher_path,
                self.fifo_path,
            ],
            # konsole
            [
                "konsole",
                "--title",
                "ShotBot Terminal",
                "-e",
                "bash",
                self.dispatcher_path,
                self.fifo_path,
            ],
            # xterm
            [
                "xterm",
                "-title",
                "ShotBot Terminal",
                "-e",
                "bash",
                self.dispatcher_path,
                self.fifo_path,
            ],
            # fallback to any available terminal
            ["x-terminal-emulator", "-e", "bash", self.dispatcher_path, self.fifo_path],
        ]

        for cmd in terminal_commands:
            try:
                logger.debug(f"Trying to launch terminal with: {cmd[0]}")
                self.terminal_process = subprocess.Popen(cmd, start_new_session=True)
                self.terminal_pid = self.terminal_process.pid

                # Give terminal time to start
                time.sleep(0.5)

                if self._is_terminal_alive():
                    logger.info(
                        f"Terminal launched successfully with PID: {self.terminal_pid}"
                    )
                    self.terminal_started.emit(self.terminal_pid)
                    return True

            except FileNotFoundError:
                logger.debug(f"Terminal emulator not found: {cmd[0]}")
                continue
            except Exception as e:
                logger.error(f"Error launching terminal with {cmd[0]}: {e}")
                continue

        logger.error("Failed to launch terminal with any available emulator")
        return False

    def send_command(self, command: str, ensure_terminal: bool = True) -> bool:
        """Send a command to the persistent terminal.

        Args:
            command: The command to execute
            ensure_terminal: Whether to launch terminal if not running

        Returns:
            True if command was sent successfully, False otherwise
        """
        # Ensure terminal is running if requested
        if ensure_terminal and not self._is_terminal_alive():
            logger.info("Terminal not running, launching new instance...")
            if not self._launch_terminal():
                logger.error("Failed to launch terminal")
                return False
            # Give terminal time to set up
            time.sleep(0.5)

        # Ensure FIFO exists before trying to use it
        if not os.path.exists(self.fifo_path):
            logger.warning(f"FIFO missing, attempting to recreate: {self.fifo_path}")
            if not self._ensure_fifo():
                logger.error(f"Failed to recreate FIFO: {self.fifo_path}")
                return False
            # Give the terminal a moment to reconnect to the new FIFO
            time.sleep(0.2)

        # Check if dispatcher is running
        if not self._is_dispatcher_running():
            logger.warning(
                f"Terminal dispatcher not reading from FIFO {self.fifo_path}. "
                f"Terminal process alive: {self._is_terminal_alive()}"
            )
            # Don't return False here - we'll let the actual write attempt handle the error

        # Send command to FIFO using non-blocking I/O
        fifo_fd = None
        max_retries = 2

        for attempt in range(max_retries):
            try:
                # Open FIFO in non-blocking mode to prevent hanging
                fifo_fd = os.open(self.fifo_path, os.O_WRONLY | os.O_NONBLOCK)

                # Convert file descriptor to file object for easier writing
                with os.fdopen(fifo_fd, "w") as fifo:
                    fifo_fd = None  # File object now owns the descriptor
                    fifo.write(f"{command}\n")
                    fifo.flush()

                logger.info(
                    f"Successfully sent command to terminal via FIFO: {command}"
                )
                logger.debug(
                    f"FIFO path: {self.fifo_path}, Terminal PID: {self.terminal_pid}"
                )
                self.command_sent.emit(command)
                return True

            except OSError as e:
                if e.errno == errno.ENOENT:
                    # FIFO doesn't exist
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"FIFO disappeared during write, recreating (attempt {attempt + 1}/{max_retries})"
                        )
                        if self._ensure_fifo():
                            time.sleep(0.2)
                            continue
                    logger.error(f"Failed to send command to FIFO: {e}")
                elif e.errno == errno.ENXIO:
                    # No reader available - terminal not running
                    if attempt == 0 and ensure_terminal:
                        # Try to restart terminal once
                        logger.warning(
                            "No reader available for FIFO, attempting to restart terminal..."
                        )
                        if self.restart_terminal():
                            logger.info(
                                "Terminal restarted successfully, retrying command..."
                            )
                            time.sleep(0.5)  # Give terminal time to set up
                            continue  # Retry the command
                        else:
                            logger.error("Failed to restart terminal")
                    else:
                        logger.warning(
                            "No reader available for FIFO (terminal_dispatcher.sh not running?)"
                        )
                elif e.errno == errno.EAGAIN:
                    logger.warning("FIFO write would block (buffer full?)")
                else:
                    logger.error(f"Failed to send command to FIFO: {e}")
                return False
            finally:
                # Clean up file descriptor if it wasn't converted to file object
                if fifo_fd is not None:
                    try:
                        os.close(fifo_fd)
                    except OSError:
                        pass

        # If we get here, all attempts failed
        return False

    def clear_terminal(self) -> bool:
        """Clear the terminal screen.

        Returns:
            True if clear command was sent successfully
        """
        return self.send_command("CLEAR_TERMINAL", ensure_terminal=False)

    def close_terminal(self) -> bool:
        """Close the persistent terminal.

        Returns:
            True if terminal was closed successfully
        """
        # Send exit command
        self.send_command("EXIT_TERMINAL", ensure_terminal=False)

        # Give it time to exit gracefully
        time.sleep(0.5)

        # Force kill if still running
        if self._is_terminal_alive() and self.terminal_pid:
            try:
                os.kill(self.terminal_pid, signal.SIGTERM)
                time.sleep(0.5)
                if self._is_terminal_alive():
                    os.kill(self.terminal_pid, signal.SIGKILL)
                logger.info(f"Force killed terminal process {self.terminal_pid}")
            except ProcessLookupError:
                pass
            except Exception as e:
                logger.error(f"Error killing terminal process: {e}")

        self.terminal_pid = None
        self.terminal_process = None
        self.terminal_closed.emit()
        return True

    def restart_terminal(self) -> bool:
        """Restart the persistent terminal.

        Returns:
            True if terminal was restarted successfully
        """
        self.close_terminal()
        time.sleep(0.5)
        return self._launch_terminal()

    def cleanup(self) -> None:
        """Clean up resources (FIFO and terminal)."""
        # Close terminal if running
        if self._is_terminal_alive():
            self.close_terminal()

        # Remove FIFO if it exists
        if os.path.exists(self.fifo_path):
            try:
                os.unlink(self.fifo_path)
                logger.debug(f"Removed FIFO at {self.fifo_path}")
            except OSError as e:
                logger.warning(f"Could not remove FIFO: {e}")

    def cleanup_fifo_only(self) -> None:
        """Clean up FIFO without closing the terminal.

        This is useful when we want to keep the terminal open
        after the application exits.
        """
        # Only remove FIFO, leave terminal running
        if os.path.exists(self.fifo_path):
            try:
                os.unlink(self.fifo_path)
                logger.debug(f"Removed FIFO at {self.fifo_path}, terminal left running")
            except OSError as e:
                logger.warning(f"Could not remove FIFO: {e}")

    def __del__(self) -> None:
        """Cleanup on deletion."""
        try:
            # Only cleanup FIFO, leave terminal running
            if hasattr(self, "fifo_path") and os.path.exists(self.fifo_path):
                os.unlink(self.fifo_path)
        except Exception:
            pass
