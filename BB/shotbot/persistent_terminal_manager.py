"""Persistent Terminal Manager for ShotBot.

This module manages a single persistent terminal window that handles all commands,
eliminating the need to spawn new terminals for each command.
"""

from __future__ import annotations

import errno
import logging
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal

if TYPE_CHECKING:
    from typing import Any

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
        self.terminal_process: subprocess.Popen[Any] | None = None

        # Ensure FIFO exists
        self._ensure_fifo()

        logger.info(
            f"PersistentTerminalManager initialized with FIFO: {self.fifo_path}"
        )

    def _ensure_fifo(self) -> None:
        """Ensure the FIFO exists for command communication."""
        if not os.path.exists(self.fifo_path):
            try:
                os.mkfifo(self.fifo_path, 0o600)  # Only user can read/write
                logger.debug(f"Created FIFO at {self.fifo_path}")
            except OSError as e:
                logger.warning(f"Could not create FIFO: {e}")

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

        # Send command to FIFO using non-blocking I/O
        fifo_fd = None
        try:
            # Open FIFO in non-blocking mode to prevent hanging
            fifo_fd = os.open(self.fifo_path, os.O_WRONLY | os.O_NONBLOCK)

            # Convert file descriptor to file object for easier writing
            with os.fdopen(fifo_fd, "w") as fifo:
                fifo_fd = None  # File object now owns the descriptor
                fifo.write(f"{command}\n")
                fifo.flush()

            logger.info(f"Successfully sent command to terminal via FIFO: {command}")
            logger.debug(
                f"FIFO path: {self.fifo_path}, Terminal PID: {self.terminal_pid}"
            )
            self.command_sent.emit(command)
            return True

        except OSError as e:
            if e.errno == errno.ENXIO:
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
