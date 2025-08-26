"""Refactored PersistentBashSession with simplified complex methods.

This refactored version breaks down the complex methods:
- _start_session (F-55) into smaller, focused methods
- _read_with_backoff (E-39) into strategy-based I/O handling
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
import uuid
from typing import Dict, Optional, Tuple

from bash_session_strategies import (
    BufferManager,
    IOStrategy,
    PollingManager,
    create_io_strategy,
    strip_ansi_escape_sequences,
)

logger = logging.getLogger(__name__)
DEBUG_VERBOSE = os.environ.get("DEBUG_VERBOSE", "").lower() in ("true", "1", "yes")

# Platform-specific imports for non-blocking I/O
HAS_FCNTL = False
HAS_SELECT = False
try:
    import fcntl
    HAS_FCNTL = True
except ImportError:
    fcntl = None

try:
    import select
    HAS_SELECT = True
except ImportError:
    select = None

# Optional debug utilities (may not be present in all environments)
try:
    from debug_utils import operation_timer, state_tracker
    HAS_DEBUG_UTILS = True
except ImportError:
    HAS_DEBUG_UTILS = False


class PersistentBashSession:
    """Manages a persistent bash shell session with simplified complexity."""
    
    # Timeouts and retry configuration
    DEFAULT_TIMEOUT = 30  # seconds
    BACKOFF_MULTIPLIER = 2.0
    MAX_RETRY_DELAY = 60.0
    INITIAL_RETRY_DELAY = 1.0
    
    # Initialization markers
    INIT_MARKER = f"__INIT_COMPLETE_{uuid.uuid4().hex[:8]}__"
    
    def __init__(self, session_id: str):
        """Initialize the persistent bash session."""
        self.session_id = session_id
        self._process: Optional[subprocess.Popen[str]] = None
        self._lock = threading.Lock()
        self._output_buffer = []
        self._error_buffer = []
        self._command_count = 0
        self._start_time = time.time()
        self._last_activity = time.time()
        
        # Retry logic state
        self._retry_count = 0
        self._retry_delay = self.INITIAL_RETRY_DELAY
        self._last_retry_time = 0.0
        
        # Performance metrics
        self._total_reads = 0
        self._total_bytes = 0
        
    def _start_session(self, with_backoff: bool = False):
        """Start persistent bash session - REFACTORED VERSION.
        
        This method is now simplified by extracting responsibilities into:
        - _handle_backoff_delay()
        - _cleanup_existing_process()
        - _create_subprocess()
        - _configure_nonblocking_io()
        - _send_initialization_commands()
        - _wait_for_initialization()
        """
        if DEBUG_VERBOSE:
            logger.debug(f"[{self.session_id}] Starting session (with_backoff={with_backoff})")
        
        # Track state transition
        if HAS_DEBUG_UTILS:
            state_tracker.transition(self.session_id, "STARTING", "Session initialization")
        
        # Step 1: Clean up any existing process
        self._cleanup_existing_process()
        
        # Step 2: Apply backoff delay if needed
        if with_backoff:
            self._handle_backoff_delay()
        
        try:
            # Step 3: Create the subprocess
            self._process = self._create_subprocess()
            
            # Step 4: Configure non-blocking I/O
            self._configure_nonblocking_io()
            
            # Step 5: Send initialization commands
            self._send_initialization_commands()
            
            # Step 6: Wait for initialization to complete
            if not self._wait_for_initialization():
                raise RuntimeError("Failed to initialize bash session")
            
            # Success - reset retry counter
            self._retry_count = 0
            self._retry_delay = self.INITIAL_RETRY_DELAY
            
            if DEBUG_VERBOSE:
                logger.debug(f"[{self.session_id}] Session started successfully")
                
        except Exception as e:
            logger.error(f"[{self.session_id}] Failed to start session: {e}")
            self._handle_startup_error(e, with_backoff)
            raise
    
    def _cleanup_existing_process(self):
        """Clean up any existing process before starting a new one."""
        if self._process is not None:
            if DEBUG_VERBOSE:
                logger.debug(f"[{self.session_id}] Cleaning up existing process")
            self._kill_session()
    
    def _handle_backoff_delay(self):
        """Apply exponential backoff delay for retries."""
        if self._retry_count > 0:
            current_time = time.time()
            time_since_last_retry = current_time - self._last_retry_time
            
            # Only apply delay if we're retrying quickly
            if time_since_last_retry < self._retry_delay:
                sleep_time = self._retry_delay - time_since_last_retry
                logger.info(f"Backing off for {sleep_time:.2f}s before retry {self._retry_count}")
                time.sleep(sleep_time)
            
            # Update retry delay with exponential backoff
            self._retry_delay = min(
                self._retry_delay * self.BACKOFF_MULTIPLIER,
                self.MAX_RETRY_DELAY
            )
            self._last_retry_time = current_time
    
    def _create_subprocess(self) -> subprocess.Popen[str]:
        """Create the bash subprocess with proper configuration.
        
        Returns:
            The created subprocess.Popen instance
        """
        if DEBUG_VERBOSE:
            logger.debug(f"[{self.session_id}] Creating subprocess with interactive bash")
        
        # Set up environment
        env = os.environ.copy()
        env["PS1"] = ""  # Clear primary prompt
        env["PS2"] = ""  # Clear secondary prompt
        
        # Create the subprocess
        process = subprocess.Popen(
            ["/bin/bash", "-i"],  # Interactive mode required for ws command
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # Line buffered
            env=env,
            # Critical Linux fixes to prevent file descriptor inheritance deadlock
            close_fds=True,
            start_new_session=True,
            restore_signals=True,
        )
        
        # Verify process started successfully
        if process.poll() is not None:
            raise RuntimeError("Bash process died immediately after starting")
        
        if DEBUG_VERBOSE:
            logger.debug(f"[{self.session_id}] Process created with PID: {process.pid}")
        
        return process
    
    def _configure_nonblocking_io(self):
        """Configure non-blocking I/O on stdout to prevent hanging."""
        if self._process is None or self._process.stdout is None:
            raise RuntimeError("Process or stdout is None")
        
        stdout_fd = self._process.stdout.fileno()
        
        # Only attempt non-blocking I/O if fcntl is available
        if HAS_FCNTL:
            try:
                if hasattr(os, "set_blocking"):
                    # Python 3.5+ way
                    os.set_blocking(stdout_fd, False)
                else:
                    # Fallback for older Python
                    flags = fcntl.fcntl(stdout_fd, fcntl.F_GETFL)
                    fcntl.fcntl(stdout_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
                
                if DEBUG_VERBOSE:
                    logger.debug(f"[{self.session_id}] Non-blocking I/O configured")
            except Exception as e:
                logger.warning(f"[{self.session_id}] Could not set non-blocking I/O: {e}")
        else:
            if DEBUG_VERBOSE:
                logger.debug(f"[{self.session_id}] fcntl not available, using blocking I/O")
    
    def _send_initialization_commands(self):
        """Send initialization commands to set up the shell environment."""
        if self._process is None or self._process.stdin is None:
            raise RuntimeError("Process or stdin is None")
        
        initialization_commands = [
            "set +x",  # Turn off command echoing
            "set +v",  # Turn off verbose mode
            "unset PROMPT_COMMAND",  # Clear any prompt commands
            "export PS1=''",  # Clear primary prompt
            "export PS2=''",  # Clear secondary prompt
            f"echo '{self.INIT_MARKER}'",  # Send initialization marker
        ]
        
        for cmd in initialization_commands:
            if DEBUG_VERBOSE:
                logger.debug(f"[{self.session_id}] Sending init command: {cmd}")
            self._process.stdin.write(f"{cmd}\n")
            self._process.stdin.flush()
    
    def _wait_for_initialization(self, timeout: float = 10.0) -> bool:
        """Wait for the initialization marker to appear in output.
        
        Args:
            timeout: Maximum time to wait for initialization
            
        Returns:
            True if initialization completed, False otherwise
        """
        if self._process is None or self._process.stdout is None:
            return False
        
        start_time = time.time()
        accumulated_output = []
        
        while time.time() - start_time < timeout:
            try:
                # Try to read output
                output = self._read_available_output(timeout=0.1)
                if output:
                    accumulated_output.append(output)
                    
                    # Check for initialization marker
                    full_output = "".join(accumulated_output)
                    if self.INIT_MARKER in full_output:
                        if DEBUG_VERBOSE:
                            logger.debug(f"[{self.session_id}] Initialization marker found")
                        
                        # Clear output up to and including the marker
                        marker_pos = full_output.find(self.INIT_MARKER)
                        remaining = full_output[marker_pos + len(self.INIT_MARKER):]
                        self._output_buffer = [remaining] if remaining else []
                        
                        return True
                        
            except Exception as e:
                logger.warning(f"[{self.session_id}] Error reading during init: {e}")
            
            # Small delay to avoid busy-waiting
            time.sleep(0.01)
        
        logger.error(f"[{self.session_id}] Initialization timeout - marker not found")
        return False
    
    def _read_available_output(self, timeout: float = 0.1) -> str:
        """Read available output from stdout - simplified version.
        
        This is a simplified version that will be further refactored with
        strategy pattern in the full implementation.
        """
        if self._process is None or self._process.stdout is None:
            return ""
        
        # Simple polling read for now - will be refactored with strategies
        if HAS_SELECT:
            ready, _, _ = select.select([self._process.stdout], [], [], timeout)
            if ready:
                try:
                    return self._process.stdout.readline()
                except IOError:
                    return ""
        else:
            # Fallback to simple read
            try:
                return self._process.stdout.readline()
            except IOError:
                return ""
        
        return ""
    
    def _handle_startup_error(self, error: Exception, with_backoff: bool):
        """Handle errors during session startup."""
        self._retry_count += 1
        
        # Clean up the failed process
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=1)
            except (subprocess.TimeoutExpired, OSError):
                try:
                    self._process.kill()
                except (ProcessLookupError, OSError):
                    pass  # Process already dead
            self._process = None
        
        # Log the error with retry information
        logger.error(
            f"[{self.session_id}] Startup failed (attempt {self._retry_count}): {error}"
        )
        
        # Update state if tracking
        if HAS_DEBUG_UTILS:
            state_tracker.transition(
                self.session_id,
                "ERROR",
                f"Startup failed: {error}"
            )
    
    def _kill_session(self):
        """Kill the current session process."""
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=1)
            except Exception as e:
                logger.warning(f"[{self.session_id}] Error killing process: {e}")
            finally:
                self._process = None
    
    # =========================================================================
    # _read_with_backoff refactored with strategy pattern
    # =========================================================================
    
    def _read_with_backoff(
        self,
        timeout: float,
        marker: Optional[str] = None,
    ) -> Tuple[str, bool]:
        """Read output with backoff - REFACTORED VERSION.
        
        This refactored version uses strategy pattern to handle different I/O methods.
        
        Args:
            timeout: Maximum time to wait for data
            marker: Optional marker to stop reading when found
            
        Returns:
            Tuple of (output, found_marker)
        """
        if self._process is None or self._process.stdout is None:
            raise RuntimeError("Process not available for reading")
        
        # Select appropriate I/O strategy
        io_strategy = self._select_io_strategy()
        
        # Initialize managers
        buffer_manager = BufferManager()
        polling_manager = PollingManager()
        
        # Read with selected strategy
        return self._read_with_strategy(
            io_strategy,
            buffer_manager,
            polling_manager,
            timeout,
            marker
        )
    
    def _select_io_strategy(self) -> IOStrategy:
        """Select the appropriate I/O strategy based on platform capabilities."""
        return create_io_strategy()
    
    def _read_with_strategy(
        self,
        strategy: 'IOStrategy',
        buffer_mgr: 'BufferManager',
        polling_mgr: 'PollingManager',
        timeout: float,
        marker: Optional[str]
    ) -> Tuple[str, bool]:
        """Read using the selected I/O strategy."""
        start_time = time.time()
        found_marker = False
        
        while time.time() - start_time < timeout:
            remaining_time = timeout - (time.time() - start_time)
            
            # Use strategy to read data
            data = strategy.read(
                self._process.stdout,
                polling_mgr.get_interval(),
                remaining_time
            )
            
            if data:
                # Process the data through buffer manager
                lines = buffer_mgr.add_data(data)
                
                for line in lines:
                    # Check for marker
                    if marker and marker in line:
                        found_marker = True
                        return buffer_mgr.get_output(), found_marker
                    
                    # Filter and clean line
                    if self._should_include_line(line):
                        clean_line = self._strip_escape_sequences(line)
                        buffer_mgr.add_output_line(clean_line)
                
                # Reset polling on successful read
                polling_mgr.reset()
            else:
                # Apply backoff on empty read
                polling_mgr.apply_backoff()
        
        # Timeout reached
        return buffer_mgr.get_output(), found_marker
    
    def _should_include_line(self, line: str) -> bool:
        """Check if a line should be included in output."""
        # Filter out initialization markers and empty lines
        return (
            line and
            not line.startswith("SHOTBOT_INIT_") and
            not line.startswith(self.INIT_MARKER)
        )
    
    def _strip_escape_sequences(self, text: str) -> str:
        """Strip ANSI escape sequences from text."""
        return strip_ansi_escape_sequences(text)
    
    def execute(self, command: str, timeout: Optional[float] = None) -> str:
        """Execute a command in the persistent bash session."""
        # Simplified implementation - full version to be completed
        with self._lock:
            if self._process is None or not self._is_alive():
                self._start_session()
            
            if self._process is None or self._process.stdin is None:
                raise RuntimeError("Failed to start session")
            
            # Send command
            self._process.stdin.write(f"{command}\n")
            self._process.stdin.flush()
            self._command_count += 1
            self._last_activity = time.time()
            
            # Read output (simplified for now)
            output = []
            timeout = timeout or self.DEFAULT_TIMEOUT
            deadline = time.time() + timeout
            
            while time.time() < deadline:
                line = self._read_available_output(0.1)
                if line:
                    output.append(line)
                    if line.strip().endswith("$"):  # Simple prompt detection
                        break
            
            return "".join(output)
    
    def _is_alive(self) -> bool:
        """Check if the session is still alive."""
        return self._process is not None and self._process.poll() is None
    
    def close(self):
        """Close the session."""
        with self._lock:
            self._kill_session()
            
    def get_stats(self) -> Dict[str, any]:
        """Get session statistics."""
        return {
            "session_id": self.session_id,
            "alive": self._is_alive(),
            "command_count": self._command_count,
            "uptime": time.time() - self._start_time,
            "last_activity": time.time() - self._last_activity,
            "retry_count": self._retry_count,
        }