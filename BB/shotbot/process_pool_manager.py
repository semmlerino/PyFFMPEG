"""Process Pool Manager for optimized subprocess handling.

This module provides centralized process management with pooling, caching,
and session reuse to reduce the overhead of repeated subprocess calls.
"""

import concurrent.futures
import hashlib
import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Try to import fcntl for non-blocking I/O (Unix-only)
try:
    import fcntl

    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False
    logging.warning("fcntl module not available - will use blocking I/O")

from PySide6.QtCore import QObject, Signal

# Import debug utilities
try:
    from debug_utils import (
        CommandTracer,
        deadlock_detector,
        setup_enhanced_debugging,
        state_tracker,
        timing_profiler,
    )

    HAS_DEBUG_UTILS = True
except ImportError:
    HAS_DEBUG_UTILS = False

logger = logging.getLogger(__name__)

# Enable verbose debug logging if environment variable is set
DEBUG_VERBOSE = os.environ.get("SHOTBOT_DEBUG_VERBOSE", "").lower() in (
    "1",
    "true",
    "yes",
)
if DEBUG_VERBOSE:
    logger.setLevel(logging.DEBUG)
    logger.info("VERBOSE DEBUG MODE ENABLED for ProcessPoolManager")

# Setup enhanced debugging if available
if HAS_DEBUG_UTILS:
    setup_enhanced_debugging()


class CommandCache:
    """TTL-based cache for command results."""

    def __init__(self, default_ttl: int = 30):
        """Initialize command cache.

        Args:
            default_ttl: Default time-to-live in seconds
        """
        super().__init__()
        self._cache: Dict[
            str, Tuple[Any, float, int, str]
        ] = {}  # key -> (result, timestamp, ttl, original_command)
        self._lock = threading.RLock()
        self._default_ttl = default_ttl
        self._hits = 0
        self._misses = 0

    def get(self, command: str) -> Optional[Any]:
        """Get cached result if not expired.

        Args:
            command: Command string to look up

        Returns:
            Cached result or None if not found/expired
        """
        key = self._make_key(command)

        with self._lock:
            if key in self._cache:
                result, timestamp, ttl, _ = self._cache[key]
                if time.time() - timestamp < ttl:
                    self._hits += 1
                    logger.debug(f"Cache hit for command: {command[:50]}...")
                    return result
                else:
                    del self._cache[key]

            self._misses += 1
            return None

    def set(self, command: str, result: Any, ttl: Optional[int] = None):
        """Cache command result with TTL.

        Args:
            command: Command string
            result: Result to cache
            ttl: Time-to-live in seconds (uses default if None)
        """
        if ttl is None:
            ttl = self._default_ttl

        key = self._make_key(command)

        with self._lock:
            self._cache[key] = (result, time.time(), ttl, command)
            self._cleanup_expired()

    def invalidate(self, pattern: Optional[str] = None):
        """Invalidate cache entries.

        Args:
            pattern: Optional pattern to match (invalidates all if None)
        """
        with self._lock:
            if pattern is None:
                self._cache.clear()
                logger.info("Cleared entire command cache")
            else:
                # Check the original command (4th element in tuple) for pattern
                keys_to_remove: List[str] = []
                for key, value in self._cache.items():
                    if len(value) >= 4 and pattern in value[3]:
                        keys_to_remove.append(key)
                for key in keys_to_remove:
                    del self._cache[key]
                logger.info(
                    f"Invalidated {len(keys_to_remove)} cache entries matching '{pattern}'"
                )

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0

            return {
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": hit_rate,
                "size": len(self._cache),
                "total_requests": total,
            }

    def _make_key(self, command: str) -> str:
        """Generate cache key from command.

        Args:
            command: Command string

        Returns:
            MD5 hash of command
        """
        return hashlib.md5(command.encode()).hexdigest()

    def _cleanup_expired(self):
        """Remove expired entries."""
        if len(self._cache) <= 100:  # Don't cleanup small caches
            return

        current_time = time.time()
        expired = [
            key
            for key, (_, timestamp, ttl, _) in self._cache.items()
            if current_time - timestamp >= ttl
        ]
        for key in expired:
            del self._cache[key]

        if expired:
            logger.debug(f"Cleaned up {len(expired)} expired cache entries")


class PersistentBashSession:
    """Reusable bash session to avoid repeated process spawning."""

    # Exponential backoff configuration
    INITIAL_RETRY_DELAY = 0.1  # 100ms
    MAX_RETRY_DELAY = 5.0  # 5 seconds
    BACKOFF_MULTIPLIER = 2.0
    MAX_RETRIES = 5

    def __init__(self, session_id: str):
        """Initialize persistent bash session.

        Args:
            session_id: Unique identifier for this session
        """
        super().__init__()
        self.session_id = session_id
        self._process: Optional[subprocess.Popen[str]] = None
        self._lock = threading.Lock()
        self._command_count = 0
        self._start_time = time.time()
        self._last_command_time = time.time()
        self._retry_count = 0
        self._retry_delay = self.INITIAL_RETRY_DELAY
        self._last_retry_time = 0
        self._start_session()

    def _start_session(self, with_backoff: bool = False):
        """Start persistent bash session with optional exponential backoff.

        Args:
            with_backoff: Whether to use exponential backoff for retries
        """
        if DEBUG_VERBOSE:
            logger.debug(
                f"[{self.session_id}] Starting session (with_backoff={with_backoff})"
            )

        # Track state transition
        if HAS_DEBUG_UTILS:
            state_tracker.transition(
                self.session_id, "STARTING", "Session initialization"
            )

        # Ensure any existing process is cleaned up first
        if self._process is not None:
            if DEBUG_VERBOSE:
                logger.debug(
                    f"[{self.session_id}] Cleaning up existing process before start"
                )
            self._kill_session()

        if with_backoff:
            # Apply exponential backoff if this is a retry
            if self._retry_count > 0:
                current_time = time.time()
                time_since_last_retry = current_time - self._last_retry_time

                # Only apply delay if we're retrying quickly
                if time_since_last_retry < self._retry_delay:
                    sleep_time = self._retry_delay - time_since_last_retry
                    logger.info(
                        f"Backing off for {sleep_time:.2f}s before retry {self._retry_count}"
                    )
                    time.sleep(sleep_time)

                # Update retry delay with exponential backoff
                self._retry_delay = min(
                    self._retry_delay * self.BACKOFF_MULTIPLIER, self.MAX_RETRY_DELAY
                )
                self._last_retry_time = current_time

        try:
            # Use interactive bash (required for ws command)
            if DEBUG_VERBOSE:
                logger.debug(
                    f"[{self.session_id}] Creating subprocess.Popen with interactive bash"
                )
                # Log file descriptors before subprocess creation
                import sys

                logger.debug(
                    f"[{self.session_id}] FDs before Popen: stdin={sys.stdin.fileno() if hasattr(sys.stdin, 'fileno') else 'N/A'}, stdout={sys.stdout.fileno() if hasattr(sys.stdout, 'fileno') else 'N/A'}, stderr={sys.stderr.fileno() if hasattr(sys.stderr, 'fileno') else 'N/A'}"
                )

            # Prepare environment to prevent terminal escape sequences
            env = os.environ.copy()
            env['TERM'] = 'dumb'  # Disable terminal escape sequences
            env['PS1'] = ''  # Clear primary prompt
            env['PS2'] = ''  # Clear secondary prompt
            
            self._process = subprocess.Popen(
                ["/bin/bash", "-i"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # Redirect stderr to stdout to prevent separate buffer deadlock
                text=True,
                bufsize=1,  # Line buffered (unbuffered not supported with text mode)
                env=env,
                # CRITICAL Linux fixes to prevent file descriptor inheritance deadlock
                close_fds=True,  # Close all FDs except stdin/stdout/stderr to prevent Qt FD inheritance
                start_new_session=True,  # Create new process group (POSIX only, ignored on Windows)
                restore_signals=True,  # Reset signal handlers to defaults (prevents Qt signal interference)
            )

            if DEBUG_VERBOSE:
                logger.debug(
                    f"[{self.session_id}] Process created with PID: {self._process.pid}"
                )
                if self._process.stdin and self._process.stdout:
                    logger.debug(
                        f"[{self.session_id}] Process FDs: stdin={self._process.stdin.fileno()}, stdout={self._process.stdout.fileno()}"
                    )

            # Verify process started successfully
            if self._process.poll() is not None:
                raise RuntimeError("Bash process died immediately after starting")

            # Set stdout to non-blocking mode to avoid hanging in pytest
            try:
                if self._process.stdout is None:
                    raise RuntimeError("Process stdout is None")

                stdout_fd = self._process.stdout.fileno()

                # Only attempt non-blocking I/O if fcntl is available
                if HAS_FCNTL:
                    if hasattr(os, "set_blocking"):
                        # Python 3.5+ way
                        os.set_blocking(stdout_fd, False)
                    else:
                        # Fallback for older Python - fcntl already imported at module level
                        flags = fcntl.fcntl(stdout_fd, fcntl.F_GETFL)
                        fcntl.fcntl(stdout_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
                else:
                    logger.debug(
                        "Skipping non-blocking I/O setup (fcntl not available)"
                    )

            except (OSError, ValueError, AttributeError) as e:
                logger.debug(f"Could not set non-blocking mode on stdout: {e}")
                # This is not critical - continue without non-blocking mode
                pass

            # Set up session - simplified without problematic draining
            try:
                # Delay to let bash initialize properly
                # Increase delay for subsequent sessions to avoid resource contention
                if "workspace_1" in self.session_id or "workspace_2" in self.session_id:
                    time.sleep(0.2)  # More delay for second/third sessions
                else:
                    time.sleep(0.1)  # Standard delay for first session

                # Send a unique marker to verify session is ready
                import uuid

                marker = f"SHOTBOT_INIT_{uuid.uuid4().hex[:8]}"

                # Simple initialization - just set PS1 and echo marker
                init_command = f"export PS1=''; export PS2=''; echo '{marker}'\n"
                if self._process.stdin is not None:
                    self._process.stdin.write(init_command)
                    self._process.stdin.flush()
                else:
                    raise RuntimeError("Process stdin is None")

                # CRITICAL FIX: Read output until we find our marker
                # This ensures the session is ready and prevents deadlock
                start_time = time.time()
                timeout = 2.0  # 2 second timeout for initialization
                found_marker = False

                if DEBUG_VERBOSE:
                    logger.debug(
                        f"[{self.session_id}] Waiting for initialization marker: {marker}"
                    )

                # Track state
                if HAS_DEBUG_UTILS:
                    state_tracker.transition(
                        self.session_id, "WAITING_MARKER", "Waiting for init marker"
                    )
                    deadlock_detector.waiting(self.session_id, "initialization_marker")

                # Accumulate all output to search for marker
                accumulated_output = ""

                while time.time() - start_time < timeout:
                    elapsed = time.time() - start_time

                    if self._process.stdout:
                        try:
                            if HAS_FCNTL:
                                # Non-blocking read - check if data is available
                                try:
                                    import select

                                    if (
                                        DEBUG_VERBOSE and int(elapsed * 10) % 5 == 0
                                    ):  # Log every 0.5 seconds
                                        logger.debug(
                                            f"[{self.session_id}] Checking for data at {elapsed:.1f}s..."
                                        )

                                    # Use very short timeout to avoid hanging
                                    ready, _, _ = select.select(
                                        [self._process.stdout], [], [], 0.01
                                    )
                                    if ready:
                                        # Read available data - use readline to avoid blocking
                                        line = self._process.stdout.readline()
                                        if line:
                                            accumulated_output += line
                                            if DEBUG_VERBOSE:
                                                logger.debug(
                                                    f"[{self.session_id}] Read line ({len(line)} bytes): {line[:100].strip()}"
                                                )
                                            if marker in accumulated_output:
                                                found_marker = True
                                                logger.debug(
                                                    f"[{self.session_id}] Session initialized successfully (non-blocking)"
                                                )
                                                break
                                    elif DEBUG_VERBOSE and elapsed > 0.5:
                                        # Log if we've been waiting a while with no data
                                        logger.debug(
                                            f"[{self.session_id}] No data available after {elapsed:.1f}s, continuing to wait..."
                                        )
                                except ImportError:
                                    # select not available, fall back to readline
                                    logger.debug(
                                        "select module not available, using readline"
                                    )
                                    line = self._process.stdout.readline()
                                    if line:
                                        accumulated_output += line
                                        if marker in accumulated_output:
                                            found_marker = True
                                            logger.debug(
                                                "Session initialized successfully (readline)"
                                            )
                                            break
                            else:
                                # Blocking read with readline
                                line = self._process.stdout.readline()
                                if line:
                                    accumulated_output += line
                                    if marker in accumulated_output:
                                        found_marker = True
                                        logger.debug(
                                            "Session initialized successfully (blocking)"
                                        )
                                        break
                        except Exception as read_error:
                            logger.debug(
                                f"[{self.session_id}] Read error during initialization: {read_error}"
                            )
                            # Small sleep to avoid busy loop
                            time.sleep(0.01)

                    # Also check if process died
                    if self._process.poll() is not None:
                        exit_code = self._process.returncode
                        logger.error(
                            f"[{self.session_id}] Bash process died during initialization with exit code: {exit_code}"
                        )
                        raise RuntimeError(
                            f"Bash process died during initialization (exit code: {exit_code})"
                        )

                # Check if we successfully initialized
                if not found_marker:
                    logger.warning(
                        f"[{self.session_id}] Session initialization marker not found after {timeout}s"
                    )
                    logger.warning(
                        f"[{self.session_id}] Accumulated output: {accumulated_output[:500]}"
                    )
                    # Try a simpler initialization as fallback
                    try:
                        if self._process.stdin:
                            self._process.stdin.write("echo 'FALLBACK_INIT'\n")
                            self._process.stdin.flush()
                            time.sleep(0.2)
                            # Try to read any response
                            if self._process.stdout:
                                try:
                                    test_line = self._process.stdout.readline()
                                    if test_line:
                                        logger.info(
                                            f"[{self.session_id}] Fallback init response: {test_line.strip()}"
                                        )
                                except (IOError, OSError):
                                    pass
                    except (IOError, OSError):
                        pass
                    # Continue anyway - the session might still work

            except Exception as e:
                logger.error(f"Failed to initialize bash session: {e}")
                self._kill_session()
                raise RuntimeError(f"Session initialization failed: {e}")

            # Reset retry count on successful start
            self._retry_count = 0
            self._retry_delay = self.INITIAL_RETRY_DELAY

            logger.info(f"Started persistent bash session: {self.session_id}")
            if DEBUG_VERBOSE:
                logger.debug(f"[{self.session_id}] Session fully initialized and ready")

            # Track successful initialization
            if HAS_DEBUG_UTILS:
                state_tracker.transition(
                    self.session_id, "READY", "Session initialized"
                )
                deadlock_detector.done_waiting(self.session_id)

        except Exception as e:
            self._process = None  # Ensure clean state
            self._retry_count += 1
            if self._retry_count > self.MAX_RETRIES:
                logger.error(
                    f"Failed to start bash session {self.session_id} after {self.MAX_RETRIES} retries: {e}"
                )
                self._retry_count = 0  # Reset for next attempt
                raise
            logger.warning(
                f"Failed to start bash session {self.session_id} (retry {self._retry_count}/{self.MAX_RETRIES}): {e}"
            )
            raise

    def _strip_escape_sequences(self, text: str) -> str:
        """Strip ANSI/terminal escape sequences from text.
        
        Args:
            text: Text potentially containing escape sequences
            
        Returns:
            Clean text without escape sequences
        """
        import re
        
        # Remove OSC (Operating System Command) sequences like ]777;...
        text = re.sub(r'\x1b\].*?(\x07|\x1b\\)', '', text)  # ESC ] ... BEL or ESC \
        text = re.sub(r'\]777;[^\x07\n]*', '', text)  # ]777; sequences without ESC
        
        # Remove CSI (Control Sequence Introducer) sequences like ESC[...
        text = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', text)
        
        # Remove other escape sequences
        text = re.sub(r'\x1b[>=]', '', text)  # ESC > or ESC =
        text = re.sub(r'\x1b\([B0UK]', '', text)  # Character set sequences
        
        # Remove any remaining control characters except newline and tab
        text = ''.join(char for char in text if ord(char) >= 32 or char in '\n\t')
        
        return text

    def execute(self, command: str, timeout: int = 120) -> str:
        """Execute command in persistent session.

        Args:
            command: Command to execute
            timeout: Timeout in seconds

        Returns:
            Command output

        Raises:
            TimeoutError: If command times out
            RuntimeError: If session is dead
        """
        if DEBUG_VERBOSE:
            logger.debug(
                f"[{self.session_id}] Execute called with command: {command[:100]}..."
            )

        # Trace command execution
        if HAS_DEBUG_UTILS:
            CommandTracer.trace(command, self.session_id)
            state_tracker.transition(self.session_id, "EXECUTING", "Running command")

        with self._lock:
            # Try to restart session with exponential backoff if dead
            if not self._is_alive():
                logger.warning(
                    f"Session {self.session_id} died, restarting with backoff..."
                )

                # Attempt restart with exponential backoff
                restart_attempts = 0
                while restart_attempts < self.MAX_RETRIES:
                    try:
                        self._start_session(with_backoff=True)
                        break
                    except Exception as e:
                        restart_attempts += 1
                        if restart_attempts >= self.MAX_RETRIES:
                            raise RuntimeError(
                                f"Failed to restart session {self.session_id} after {self.MAX_RETRIES} attempts: {e}"
                            )
                        logger.debug(
                            f"Restart attempt {restart_attempts} failed, retrying..."
                        )

            # Verify process is available after restart
            if (
                self._process is None
                or self._process.stdin is None
                or self._process.stdout is None
            ):
                raise RuntimeError(f"Failed to start session {self.session_id}")

            # Send command with unique marker
            marker = f"<<<SHOTBOT_{self.session_id}_{time.time()}>>>"
            # Always print the marker, even if command fails (using || true to bypass set -e)
            full_command = f'({command}) || true; echo "{marker}"'

            if DEBUG_VERBOSE:
                logger.debug(
                    f"[{self.session_id}] Sending command with marker: {marker}"
                )
                logger.debug(
                    f"[{self.session_id}] Full command: {full_command[:200]}..."
                )

            try:
                self._process.stdin.write(f"{full_command}\n")
                self._process.stdin.flush()

                if DEBUG_VERBOSE:
                    logger.debug(
                        f"[{self.session_id}] Command sent to stdin and flushed"
                    )

                # Read output until marker using non-blocking I/O
                output: List[str] = []
                start_time = time.time()
                buffer = ""  # Buffer for partial lines

                while True:
                    elapsed = time.time() - start_time
                    if elapsed > timeout:
                        logger.debug(
                            f"[{self.session_id}] Timeout reached after {elapsed:.2f}s for command: {command[:50]}..."
                        )
                        if DEBUG_VERBOSE:
                            logger.debug(
                                f"[{self.session_id}] Output collected before timeout: {output[:5] if output else 'None'}"
                            )
                        # Try to recover
                        self._kill_session()
                        # Don't try to restart here - let next execute() handle it
                        self._process = None
                        raise TimeoutError(
                            f"Command timed out after {timeout}s: {command}"
                        )

                    # Safe access with None check
                    if self._process is None or self._process.stdout is None:
                        raise RuntimeError("Process died during execution")

                    # Read from stdout (blocking or non-blocking depending on fcntl availability)
                    try:
                        if HAS_FCNTL:
                            # Non-blocking read
                            if (
                                DEBUG_VERBOSE and elapsed - int(elapsed) < 0.01
                            ):  # Log once per second
                                logger.debug(
                                    f"[{self.session_id}] Reading (non-blocking) at {elapsed:.1f}s..."
                                )
                            chunk = self._process.stdout.read(4096)
                        else:
                            # Blocking read with readline to avoid hanging
                            if (
                                DEBUG_VERBOSE and elapsed - int(elapsed) < 0.01
                            ):  # Log once per second
                                logger.debug(
                                    f"[{self.session_id}] Reading line (blocking) at {elapsed:.1f}s..."
                                )
                            line = self._process.stdout.readline()
                            if line:
                                if DEBUG_VERBOSE:
                                    logger.debug(
                                        f"[{self.session_id}] Read line ({len(line)} chars): {line[:100] if line else 'empty'}"
                                    )
                                if marker in line:
                                    logger.debug(
                                        f"[{self.session_id}] Found marker, command complete"
                                    )
                                    self._command_count += 1
                                    self._last_command_time = time.time()
                                    result = "\n".join(output)
                                    # Strip escape sequences from the result
                                    result = self._strip_escape_sequences(result)
                                    if DEBUG_VERBOSE:
                                        logger.debug(
                                            f"[{self.session_id}] Returning {len(result)} chars of output (after stripping escape sequences)"
                                        )
                                    return result
                                # Filter out initialization markers and clean escape sequences
                                if not line.startswith("SHOTBOT_INIT_"):
                                    # Strip escape sequences from individual lines as well
                                    clean_line = self._strip_escape_sequences(line.rstrip())
                                    if clean_line:  # Only append non-empty lines
                                        output.append(clean_line)
                            continue  # Skip the chunk processing below

                        # Process chunk for non-blocking mode
                        if chunk:
                            buffer += chunk
                            # Process complete lines
                            lines = buffer.split("\n")
                            # Keep incomplete line in buffer
                            buffer = lines[-1]
                            # Process complete lines
                            for line in lines[:-1]:
                                logger.debug(
                                    f"Read line: {line[:100] if line else 'empty'}"
                                )
                                if marker in line:
                                    logger.debug("Found marker, breaking")
                                    # Return everything collected so far
                                    self._command_count += 1
                                    self._last_command_time = time.time()
                                    result = "\n".join(output)
                                    # Strip escape sequences from the result
                                    result = self._strip_escape_sequences(result)
                                    return result
                                # Filter out initialization markers and clean escape sequences
                                if not line.startswith("SHOTBOT_INIT_"):
                                    # Strip escape sequences from individual lines as well
                                    clean_line = self._strip_escape_sequences(line.rstrip())
                                    if clean_line:  # Only append non-empty lines
                                        output.append(clean_line)
                    except (IOError, OSError) as e:
                        # EAGAIN means no data available (expected for non-blocking)
                        if HAS_FCNTL:
                            import errno

                            if e.errno != errno.EAGAIN:
                                raise
                        else:
                            raise

                    # Small sleep to avoid busy waiting (only for non-blocking mode)
                    if HAS_FCNTL:
                        time.sleep(0.01)

            except TimeoutError:
                # Re-raise timeout errors as-is
                raise
            except Exception as e:
                logger.error(
                    f"Error executing command in session {self.session_id}: {e}"
                )
                # Try to recover with exponential backoff
                self._kill_session()
                self._retry_count += 1
                logger.warning(
                    f"Command execution failed, attempting recovery (retry {self._retry_count})"
                )
                # Don't restart here - let next execute() handle it
                self._process = None
                raise

    def _execute_internal(self, command: str) -> None:
        """Execute internal setup command without markers.

        Args:
            command: Setup command to execute

        Raises:
            RuntimeError: If process is not available
        """
        if not self._process or not self._process.stdin:
            raise RuntimeError("Process not available for internal command")

        try:
            self._process.stdin.write(f"{command}\n")
            self._process.stdin.flush()
            time.sleep(0.1)  # Brief pause for command to complete
        except (BrokenPipeError, OSError) as e:
            logger.error(f"Failed to execute internal command: {e}")
            raise RuntimeError(f"Internal command failed: {e}")

    def _is_alive(self) -> bool:
        """Check if session is still alive.

        Returns:
            True if session is alive
        """
        return self._process is not None and self._process.poll() is None

    def _kill_session(self):
        """Kill the current session."""
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                logger.warning(
                    f"Session {self.session_id} didn't terminate gracefully, killing"
                )
                try:
                    self._process.kill()
                    self._process.wait(timeout=1)
                except Exception as e:
                    logger.error(f"Failed to kill session {self.session_id}: {e}")
            except OSError as e:
                logger.warning(f"Error terminating session {self.session_id}: {e}")
            finally:
                self._process = None

    def get_stats(self) -> Dict[str, Any]:
        """Get session statistics.

        Returns:
            Dictionary with session stats
        """
        uptime = time.time() - self._start_time
        idle_time = time.time() - self._last_command_time

        return {
            "session_id": self.session_id,
            "alive": self._is_alive(),
            "commands_executed": self._command_count,
            "uptime_seconds": uptime,
            "idle_seconds": idle_time,
        }

    def close(self):
        """Close the session gracefully."""
        self._kill_session()
        logger.info(f"Closed bash session: {self.session_id}")


class ProcessPoolManager(QObject):
    """Centralized process management with pooling and caching.

    This singleton class manages all subprocess operations for the application,
    providing session reuse, command caching, and parallel execution.
    """

    # Singleton instance
    _instance = None
    _lock = threading.Lock()

    # Qt signals
    command_completed = Signal(str, object)  # command_id, result
    command_failed = Signal(str, str)  # command_id, error

    def __new__(cls, *args, **kwargs):
        """Ensure singleton pattern."""
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, max_workers: int = 4, sessions_per_type: int = 3):
        """Initialize process pool manager.

        Args:
            max_workers: Maximum concurrent workers
            sessions_per_type: Number of sessions to maintain per type for parallelism
        """
        # Only initialize once
        with ProcessPoolManager._lock:
            if hasattr(self, "_initialized"):
                return

            super().__init__()

            self._executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=max_workers
            )
            # Session pools: type -> list of sessions
            self._session_pools: Dict[str, List[PersistentBashSession]] = {}
            self._session_round_robin: Dict[str, int] = {}  # Track next session to use
            self._sessions_per_type = sessions_per_type
            self._cache = CommandCache(default_ttl=30)
            self._session_lock = threading.RLock()
            self._metrics = ProcessMetrics()
            self._initialized = True

        logger.info(f"ProcessPoolManager initialized with {max_workers} workers")

    @classmethod
    def get_instance(cls) -> "ProcessPoolManager":
        """Get singleton instance.

        Returns:
            ProcessPoolManager singleton
        """
        if not cls._instance:
            cls._instance = cls()
        return cls._instance

    def execute_workspace_command(
        self, command: str, cache_ttl: int = 30, timeout: int = 120
    ) -> str:
        """Execute workspace command with caching and session reuse.

        Args:
            command: Command to execute
            cache_ttl: Cache time-to-live in seconds
            timeout: Command execution timeout in seconds (default 120s)

        Returns:
            Command output
        """
        if DEBUG_VERBOSE:
            logger.debug(f"execute_workspace_command called: {command[:50]}...")

        # Check cache first
        cached = self._cache.get(command)
        if cached is not None:
            self._metrics.cache_hits += 1
            if DEBUG_VERBOSE:
                logger.debug(f"Cache HIT for command: {command[:50]}...")
            return cached

        if DEBUG_VERBOSE:
            logger.debug(f"Cache MISS for command: {command[:50]}... - will execute")

        self._metrics.cache_misses += 1
        self._metrics.subprocess_calls += 1

        # Get or create bash session
        session = self._get_bash_session("workspace")

        # Execute command
        start_time = time.time()
        try:
            result = session.execute(command, timeout=timeout)

            # Cache result
            self._cache.set(command, result, ttl=cache_ttl)

            # Update metrics
            elapsed = (time.time() - start_time) * 1000
            self._metrics.update_response_time(elapsed)

            # Emit completion signal
            self.command_completed.emit(command, result)

            return result

        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            self.command_failed.emit(command, str(e))
            raise

    def batch_execute(
        self, commands: List[str], cache_ttl: int = 30, session_type: str = "workspace"
    ) -> Dict[str, Optional[str]]:
        """Execute multiple commands in parallel using session pool.

        Leverages multiple sessions for true parallel execution.

        Args:
            commands: List of commands to execute
            cache_ttl: Cache time-to-live in seconds
            session_type: Type of session pool to use

        Returns:
            Dictionary mapping commands to results
        """
        # Check cache first and separate cached from non-cached
        results: Dict[str, Optional[str]] = {}
        commands_to_execute: List[str] = []

        for cmd in commands:
            cached = self._cache.get(cmd)
            if cached is not None:
                results[cmd] = cached
                self._metrics.cache_hits += 1
                logger.debug(f"Batch: cache hit for {cmd[:50]}...")
            else:
                commands_to_execute.append(cmd)
                self._metrics.cache_misses += 1

        if not commands_to_execute:
            return results  # All results were cached

        # Execute non-cached commands in parallel
        futures: Dict[concurrent.futures.Future[str], str] = {}
        for cmd in commands_to_execute:
            future = self._executor.submit(
                self._execute_with_session_pool, cmd, cache_ttl, session_type
            )
            futures[future] = cmd

        # Collect results
        for future in concurrent.futures.as_completed(futures):
            cmd = futures[future]
            try:
                result = future.result()
                results[cmd] = result
                # Cache successful results
                self._cache.set(cmd, result, ttl=cache_ttl)
            except Exception as e:
                logger.error(f"Batch command failed: {cmd} - {e}")
                results[cmd] = None

        return results

    def _execute_with_session_pool(
        self, command: str, cache_ttl: int, session_type: str
    ) -> str:
        """Execute command using session pool for true parallelism.

        This method is designed to be called in parallel threads.

        Args:
            command: Command to execute
            cache_ttl: Cache time-to-live
            session_type: Type of session pool

        Returns:
            Command output
        """
        # Get next available session from pool
        session = self._get_bash_session(session_type)

        # Execute command
        start_time = time.time()
        try:
            result = session.execute(command)

            # Update metrics
            elapsed = (time.time() - start_time) * 1000
            self._metrics.update_response_time(elapsed)
            self._metrics.subprocess_calls += 1

            return result

        except Exception as e:
            logger.error(f"Session pool execution failed: {e}")
            raise

    def find_files_python(self, directory: str, pattern: str) -> List[str]:
        """Find files using Python instead of subprocess.

        Args:
            directory: Directory to search
            pattern: File pattern to match

        Returns:
            List of matching file paths
        """
        # Use Python pathlib instead of subprocess find
        self._metrics.python_operations += 1

        try:
            path = Path(directory)
            if not path.exists():
                return []

            # Use rglob for recursive search
            files = list(path.rglob(pattern))
            return [str(f) for f in files]

        except Exception as e:
            logger.error(f"File search failed: {e}")
            return []

    def _get_bash_session(self, session_type: str) -> PersistentBashSession:
        """Get next available bash session from pool using round-robin.

        Creates sessions lazily on first use to avoid conflicts with Qt initialization.

        Args:
            session_type: Type of session (workspace, general, etc.)

        Returns:
            PersistentBashSession instance
        """
        if DEBUG_VERBOSE:
            logger.debug(f"Getting bash session for type: {session_type}")

        with self._session_lock:
            # Initialize pool structure if needed (but don't create sessions yet)
            if session_type not in self._session_pools:
                self._session_pools[session_type] = []
                self._session_round_robin[session_type] = 0
                logger.info(f"Initialized empty pool for session type: {session_type}")
                if DEBUG_VERBOSE:
                    logger.debug("Pool structure created, no sessions yet (lazy init)")

            # Get or create sessions as needed
            pool = self._session_pools[session_type]

            # Create sessions lazily if pool is empty
            if not pool:
                logger.info(
                    f"LAZY INIT: Creating {self._sessions_per_type} sessions for pool type: {session_type}"
                )
                if DEBUG_VERBOSE:
                    logger.debug(
                        f"This is the FIRST use of {session_type} pool - creating sessions now"
                    )

                for i in range(self._sessions_per_type):
                    session_id = f"{session_type}_{i}"
                    try:
                        if DEBUG_VERBOSE:
                            logger.debug(
                                f"Creating session {i + 1}/{self._sessions_per_type}: {session_id}"
                            )

                        # Time session creation
                        if HAS_DEBUG_UTILS:
                            with timing_profiler.measure(
                                f"create_session_{session_id}"
                            ):
                                session = PersistentBashSession(session_id)
                        else:
                            session = PersistentBashSession(session_id)

                        pool.append(session)
                        logger.info(f"Created session {session_id} in pool")

                        # Delay between creating sessions to avoid resource contention
                        if i < self._sessions_per_type - 1:
                            time.sleep(0.3)  # Increased from 0.1 to 0.3
                            if DEBUG_VERBOSE:
                                logger.debug(
                                    "Pause before creating next session (0.3s)..."
                                )
                    except Exception as e:
                        logger.error(f"Failed to create session {session_id}: {e}")
                        # Continue with fewer sessions if some fail

                if not pool:
                    raise RuntimeError(
                        f"Failed to create any sessions for type {session_type}"
                    )

            # Get next session using round-robin
            index = self._session_round_robin[session_type]
            session = pool[index]

            if DEBUG_VERBOSE:
                logger.debug(
                    f"Selected session {session.session_id} (index {index}/{len(pool)})"
                )

            # Update round-robin counter
            self._session_round_robin[session_type] = (index + 1) % len(pool)

            # Check if session is alive, restart if needed
            # Access private method safely - this is internal to our module
            if not session._is_alive():  # type: ignore[reportPrivateUsage]
                logger.warning(f"Session {session.session_id} dead, restarting")
                if DEBUG_VERBOSE:
                    logger.debug(
                        f"Session {session.session_id} needs restart (process dead)"
                    )
                session._start_session()  # type: ignore[reportPrivateUsage]
            elif DEBUG_VERBOSE:
                logger.debug(f"Session {session.session_id} is alive and ready")

            return session

    def invalidate_cache(self, pattern: Optional[str] = None):
        """Invalidate command cache.

        Args:
            pattern: Optional pattern to match
        """
        self._cache.invalidate(pattern)

    def get_metrics(self) -> Dict[str, Any]:
        """Get performance metrics.

        Returns:
            Dictionary with metrics
        """
        metrics = self._metrics.get_report()
        metrics["cache_stats"] = self._cache.get_stats()

        # Add session stats for all pools
        session_stats = {}
        with self._session_lock:
            for session_type, pool in self._session_pools.items():
                pool_stats: List[Dict[str, Any]] = []
                for session in pool:
                    pool_stats.append(session.get_stats())
                session_stats[session_type] = {
                    "pool_size": len(pool),
                    "sessions": pool_stats,
                }

        metrics["sessions"] = session_stats

        return metrics

    def shutdown(self):
        """Shutdown the process pool manager."""
        # Close all bash sessions in all pools
        with self._session_lock:
            for session_type, pool in self._session_pools.items():
                logger.info(
                    f"Shutting down {len(pool)} sessions in {session_type} pool"
                )
                for session in pool:
                    session.close()
            self._session_pools.clear()
            self._session_round_robin.clear()

        # Shutdown executor
        self._executor.shutdown(wait=True)

        logger.info("ProcessPoolManager shutdown complete")


class ProcessMetrics:
    """Track process optimization metrics."""

    def __init__(self):
        """Initialize process metrics tracking."""
        super().__init__()
        self.subprocess_calls = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self.python_operations = 0
        self.total_response_time = 0.0
        self.response_count = 0
        self.start_time = time.time()

    def update_response_time(self, time_ms: float):
        """Update response time metrics.

        Args:
            time_ms: Response time in milliseconds
        """
        self.total_response_time += time_ms
        self.response_count += 1

    def get_report(self) -> Dict[str, Any]:
        """Generate performance report.

        Returns:
            Dictionary with performance metrics
        """
        avg_response = (
            self.total_response_time / self.response_count
            if self.response_count > 0
            else 0
        )

        uptime = time.time() - self.start_time

        return {
            "subprocess_calls": self.subprocess_calls,
            "python_operations": self.python_operations,
            "average_response_ms": avg_response,
            "uptime_seconds": uptime,
            "calls_per_minute": (self.subprocess_calls / uptime * 60)
            if uptime > 0
            else 0,
        }


# Example usage
if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    # Get singleton instance
    pool = ProcessPoolManager.get_instance()

    # Test workspace command with caching
    result1 = pool.execute_workspace_command("echo 'test'", cache_ttl=5)
    print(f"First call: {result1}")

    result2 = pool.execute_workspace_command("echo 'test'", cache_ttl=5)
    print(f"Second call (cached): {result2}")

    # Test batch execution
    commands = ["echo 'one'", "echo 'two'", "echo 'three'"]
    results = pool.batch_execute(commands)
    print(f"Batch results: {results}")

    # Test file finding with Python
    files = pool.find_files_python("/tmp", "*.txt")
    print(f"Found files: {files}")

    # Print metrics
    metrics = pool.get_metrics()
    print(f"\nMetrics: {metrics}")

    # Cleanup
    pool.shutdown()

    sys.exit(0)
