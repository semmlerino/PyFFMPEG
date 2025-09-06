"""Worker thread for launcher command execution.

This module contains the LauncherWorker class that handles subprocess
execution in a separate thread, extracted from the original launcher_manager.py.
"""

from __future__ import annotations

import logging
import re
import shlex
import subprocess

from PySide6.QtCore import Signal

from exceptions import SecurityError
from thread_safe_worker import ThreadSafeWorker

# Set up logger for this module
logger = logging.getLogger(__name__)


class LauncherWorker(ThreadSafeWorker):
    """Thread-safe worker for executing launcher commands.

    This worker inherits thread-safe lifecycle management from ThreadSafeWorker
    and adds launcher-specific functionality.
    """

    # Launcher-specific signals
    command_started = Signal(str, str)  # launcher_id, command
    command_finished = Signal(str, bool, int)  # launcher_id, success, return_code
    command_error = Signal(str, str)  # launcher_id, error_message

    def __init__(
        self,
        launcher_id: str,
        command: str,
        working_dir: str | None = None,
    ) -> None:
        """Initialize launcher worker.

        Args:
            launcher_id: Unique identifier for this launcher
            command: Command to execute
            working_dir: Optional working directory for the command
        """
        super().__init__()
        self.launcher_id = launcher_id
        self.command = command
        self.working_dir = working_dir
        self._process: subprocess.Popen[str] | None = None

    def _sanitize_command(self, command: str) -> tuple[list[str], bool]:
        """Safely parse and validate command to prevent shell injection.

        Args:
            command: Command string to sanitize

        Returns:
            Tuple of (command_list, use_shell) where use_shell is always False
            for security

        Raises:
            SecurityError: If command contains dangerous patterns or isn't whitelisted
        """
        # Whitelist of allowed base commands
        ALLOWED_COMMANDS = {
            "3de",
            "3de4",
            "3dequalizer",
            "nuke",
            "nuke_i",
            "nukex",
            "maya",
            "mayapy",
            "rv",
            "rvpkg",
            "houdini",
            "hython",
            "katana",
            "mari",
            "publish",
            "publish_standalone",
            "python",
            "python3",
            # SECURITY: bash and sh removed - use specific safe commands only
        }

        # Dangerous patterns that indicate potential injection attempts
        DANGEROUS_PATTERNS = [
            r";\s*(rm|sudo|su|chmod|chown|dd|mkfs|fdisk)\s",
            r"&&\s*(rm|sudo|su|chmod|chown|dd|mkfs|fdisk)\s",
            r"\|\s*(rm|sudo|su|chmod|chown|dd|mkfs|fdisk)\s",
            r"`[^`]*`",  # Command substitution
            r"\$\([^)]*\)",  # Command substitution
            r"\$\{[^}]*\}",  # Variable expansion that could be dangerous
            r">\s*/dev/(sda|sdb|sdc|null)",  # Dangerous redirects
            r"2>&1.*>/dev/null.*rm",  # Hidden rm commands
        ]

        # Check for dangerous patterns
        for pattern in DANGEROUS_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                raise SecurityError(
                    f"Command contains dangerous pattern and was blocked: {command[:100]}"
                )

        # Try to parse the command safely
        try:
            cmd_list = shlex.split(command)

            # Validate the base command is in whitelist
            if cmd_list:
                base_command = cmd_list[0].split("/")[
                    -1
                ]  # Get command name without path
                if base_command not in ALLOWED_COMMANDS:
                    # Check if it's a full path to an allowed command
                    allowed = False
                    for allowed_cmd in ALLOWED_COMMANDS:
                        if allowed_cmd in cmd_list[0]:
                            allowed = True
                            break

                    if not allowed:
                        logger.warning(
                            f"Command '{base_command}' not in whitelist. Command: {command[:100]}"
                        )
                        raise SecurityError(
                            f"Command '{base_command}' is not in the allowed command whitelist"
                        )

            # Never use shell=True for security
            return cmd_list, False

        except ValueError as e:
            # If shlex.split fails, the command is malformed
            # Do not fall back to shell=True - this is a security risk
            logger.error(f"Failed to parse command safely: {command[:100]}")
            raise SecurityError(
                f"Command could not be parsed safely and was blocked: {str(e)}"
            )

    def do_work(self) -> None:
        """Execute the launcher command with proper lifecycle management.

        This method is called by the base class run() method and includes
        proper state management and error handling.
        """
        try:
            # Emit start signal
            self.command_started.emit(self.launcher_id, self.command)
            logger.info(
                f"Worker {id(self)} starting launcher '{self.launcher_id}': {self.command}",
            )

            # Parse command properly to avoid shell injection
            # Use shlex to split if it's a string command
            if isinstance(self.command, str):
                # Security: Parse and validate command to prevent injection

                # Sanitize and validate the command
                cmd_list, use_shell = self._sanitize_command(self.command)
            else:
                cmd_list = self.command
                use_shell = False

            # Start the process
            self._process = subprocess.Popen(
                cmd_list,
                shell=use_shell,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=self.working_dir,
                start_new_session=True,  # Isolate process group
            )

            # Monitor process with periodic checks for stop requests
            while not self.is_stop_requested():
                try:
                    # Check if process finished with timeout
                    return_code = self._process.wait(timeout=1.0)
                    # Process finished normally
                    success = return_code == 0
                    logger.info(
                        f"Worker {id(self)} finished launcher '{self.launcher_id}' with code {return_code}",
                    )
                    self.command_finished.emit(self.launcher_id, success, return_code)
                    return
                except subprocess.TimeoutExpired:
                    # Process still running, check for stop request
                    continue

            # Stop was requested - terminate the process
            if self._process and self._process.poll() is None:
                logger.info(
                    f"Worker {id(self)} stopping launcher '{self.launcher_id}' due to stop request",
                )
                self._terminate_process()
                self.command_finished.emit(self.launcher_id, False, -2)

        except Exception as e:
            error_msg = f"Worker exception for launcher '{self.launcher_id}': {str(e)}"
            logger.exception(error_msg)
            self.command_error.emit(self.launcher_id, error_msg)
            self.command_finished.emit(self.launcher_id, False, -1)
        finally:
            # Ensure process is cleaned up
            self._cleanup_process()

    def _terminate_process(self) -> None:
        """Safely terminate the subprocess."""
        if not self._process:
            return

        try:
            # Try graceful termination first
            self._process.terminate()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                # Force kill if necessary
                logger.warning(
                    f"Force killing launcher '{self.launcher_id}' after timeout",
                )
                self._process.kill()
                self._process.wait(timeout=5)
        except Exception as e:
            logger.error(f"Error terminating process for '{self.launcher_id}': {e}")

    def _cleanup_process(self) -> None:
        """Clean up process resources."""
        if self._process:
            # Ensure process is terminated
            if self._process.poll() is None:
                try:
                    self._terminate_process()
                    # Only set to None if termination succeeded or process is dead
                    if self._process.poll() is not None:
                        self._process = None
                    else:
                        # Process still alive after termination attempt
                        logger.error(
                            f"Failed to terminate process for launcher '{self.launcher_id}', "
                            + f"process {self._process.pid} may be orphaned"
                        )
                        # Still set to None to avoid repeated termination attempts
                        # but log the issue for debugging
                        self._process = None
                except Exception as e:
                    logger.error(
                        f"Exception during process cleanup for launcher '{self.launcher_id}': {e}, "
                        + "process may be orphaned"
                    )
                    # Set to None to avoid repeated attempts but log the failure
                    self._process = None
            else:
                # Process already terminated
                self._process = None

    def request_stop(self) -> bool:
        """Override to handle process termination."""
        # Call parent implementation first
        if super().request_stop():
            # Also terminate the subprocess if running
            if self._process and self._process.poll() is None:
                self._terminate_process()
            return True
        return False
