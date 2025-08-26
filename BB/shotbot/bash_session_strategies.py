"""Strategy classes and managers for PersistentBashSession I/O operations.

This module contains the extracted complexity from _read_with_backoff method,
organized into focused, testable components using the Strategy pattern.
"""

from __future__ import annotations

import logging
import os
import time
from abc import ABC, abstractmethod
from typing import IO, List, Optional

logger = logging.getLogger(__name__)
DEBUG_VERBOSE = os.environ.get("DEBUG_VERBOSE", "").lower() in ("true", "1", "yes")

# Platform-specific imports
try:
    import select
    HAS_SELECT = True
except ImportError:
    select = None
    HAS_SELECT = False

try:
    import fcntl
    HAS_FCNTL = True
except ImportError:
    fcntl = None
    HAS_FCNTL = False


# =============================================================================
# I/O Strategy Classes
# =============================================================================

class IOStrategy(ABC):
    """Abstract base class for I/O reading strategies."""
    
    @abstractmethod
    def read(self, stream: IO, poll_interval: float, timeout: float) -> Optional[str]:
        """Read data from the stream.
        
        Args:
            stream: The I/O stream to read from
            poll_interval: Current polling interval
            timeout: Maximum time to wait for data
            
        Returns:
            Data read from stream, or None if no data available
        """
        pass
    
    @abstractmethod
    def name(self) -> str:
        """Get the strategy name for logging."""
        pass


class SelectIOStrategy(IOStrategy):
    """I/O strategy using select() for non-blocking reads."""
    
    def read(self, stream: IO, poll_interval: float, timeout: float) -> Optional[str]:
        """Read using select() to check for available data."""
        if not HAS_SELECT:
            raise RuntimeError("select module not available")
        
        # Use select to check if data is available
        ready, _, _ = select.select([stream], [], [], min(poll_interval, timeout))
        
        if ready:
            try:
                # Read available data (non-blocking if fcntl is available)
                if HAS_FCNTL:
                    # Read up to 4KB of data
                    data = stream.read(4096)
                else:
                    # Fallback to readline
                    data = stream.readline()
                
                return data if data else None
            except IOError as e:
                if DEBUG_VERBOSE:
                    logger.debug(f"SelectIOStrategy read error: {e}")
                return None
        
        return None
    
    def name(self) -> str:
        return "select"


class FCNTLIOStrategy(IOStrategy):
    """I/O strategy using fcntl for non-blocking reads (Unix/Linux only)."""
    
    def __init__(self):
        """Initialize and verify fcntl availability."""
        if not HAS_FCNTL:
            raise RuntimeError("fcntl module not available")
    
    def read(self, stream: IO, poll_interval: float, timeout: float) -> Optional[str]:
        """Read using non-blocking I/O with fcntl."""
        try:
            # Attempt non-blocking read
            import errno
            
            data = ""
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                try:
                    chunk = stream.read(4096)
                    if chunk:
                        data += chunk
                        if "\n" in chunk:
                            # Got complete line(s)
                            break
                    else:
                        # No more data available
                        break
                except IOError as e:
                    if e.errno == errno.EAGAIN:
                        # No data available, wait a bit
                        time.sleep(min(poll_interval, timeout - (time.time() - start_time)))
                    else:
                        raise
            
            return data if data else None
            
        except Exception as e:
            if DEBUG_VERBOSE:
                logger.debug(f"FCNTLIOStrategy read error: {e}")
            return None
    
    def name(self) -> str:
        return "fcntl"


class BlockingIOStrategy(IOStrategy):
    """Fallback I/O strategy using blocking reads with timeout."""
    
    def read(self, stream: IO, poll_interval: float, timeout: float) -> Optional[str]:
        """Read using blocking I/O with manual timeout management."""
        try:
            # Simple blocking readline with no timeout control
            # This is the fallback when neither select nor fcntl are available
            line = stream.readline()
            return line if line else None
        except Exception as e:
            if DEBUG_VERBOSE:
                logger.debug(f"BlockingIOStrategy read error: {e}")
            return None
    
    def name(self) -> str:
        return "blocking"


# =============================================================================
# Manager Classes
# =============================================================================

class BufferManager:
    """Manages buffering and line splitting for I/O operations."""
    
    def __init__(self):
        """Initialize the buffer manager."""
        self._buffer = ""
        self._output_lines: List[str] = []
    
    def add_data(self, data: str) -> List[str]:
        """Add data to buffer and return complete lines.
        
        Args:
            data: Raw data to add to buffer
            
        Returns:
            List of complete lines extracted from buffer
        """
        self._buffer += data
        
        # Split into lines
        lines = self._buffer.split("\n")
        
        # Keep the last incomplete line in buffer
        self._buffer = lines[-1]
        
        # Return complete lines
        return lines[:-1]
    
    def add_output_line(self, line: str):
        """Add a cleaned line to the output."""
        if line:
            self._output_lines.append(line)
    
    def get_output(self) -> str:
        """Get the accumulated output as a single string."""
        return "\n".join(self._output_lines)
    
    def get_remaining_buffer(self) -> str:
        """Get any remaining data in the buffer."""
        return self._buffer
    
    def clear(self):
        """Clear the buffer and output."""
        self._buffer = ""
        self._output_lines.clear()


class PollingManager:
    """Manages polling intervals with exponential backoff."""
    
    # Polling configuration
    INITIAL_POLL_INTERVAL = 0.01  # 10ms
    MAX_POLL_INTERVAL = 1.0  # 1 second
    BACKOFF_MULTIPLIER = 1.5
    
    def __init__(self):
        """Initialize the polling manager."""
        self._current_interval = self.INITIAL_POLL_INTERVAL
        self._consecutive_empty_polls = 0
    
    def get_interval(self) -> float:
        """Get the current polling interval."""
        return self._current_interval
    
    def reset(self):
        """Reset polling interval after successful read."""
        self._current_interval = self.INITIAL_POLL_INTERVAL
        self._consecutive_empty_polls = 0
    
    def apply_backoff(self):
        """Apply exponential backoff after empty read."""
        self._consecutive_empty_polls += 1
        
        # Apply backoff after multiple empty polls
        if self._consecutive_empty_polls > 2:
            self._current_interval = min(
                self._current_interval * self.BACKOFF_MULTIPLIER,
                self.MAX_POLL_INTERVAL
            )
            
            if DEBUG_VERBOSE and self._consecutive_empty_polls % 10 == 0:
                logger.debug(
                    f"Polling backoff: interval={self._current_interval:.3f}s, "
                    f"empty_polls={self._consecutive_empty_polls}"
                )
    
    def get_stats(self) -> dict:
        """Get polling statistics."""
        return {
            "current_interval": self._current_interval,
            "consecutive_empty_polls": self._consecutive_empty_polls,
        }


# =============================================================================
# Utility Functions
# =============================================================================

def create_io_strategy() -> IOStrategy:
    """Factory function to create the appropriate I/O strategy.
    
    Returns:
        The most appropriate IOStrategy implementation for the platform
    """
    if HAS_SELECT:
        return SelectIOStrategy()
    elif HAS_FCNTL:
        return FCNTLIOStrategy()
    else:
        logger.warning(
            "Neither select nor fcntl available - using blocking I/O. "
            "This may cause hangs in some situations."
        )
        return BlockingIOStrategy()


def strip_ansi_escape_sequences(text: str) -> str:
    """Strip ANSI escape sequences from text.
    
    Args:
        text: Text potentially containing ANSI escape sequences
        
    Returns:
        Text with escape sequences removed
    """
    import re
    # Comprehensive ANSI escape sequence pattern
    ansi_escape = re.compile(
        r'''
        \x1B  # ESC
        (?:   # 7-bit C1 Fe (except CSI)
            [@-Z\\-_]
        |     # or [ for CSI, followed by parameter bytes
            \[
            [0-?]*  # Parameter bytes
            [ -/]*  # Intermediate bytes
            [@-~]   # Final byte
        )
        ''',
        re.VERBOSE
    )
    return ansi_escape.sub('', text)