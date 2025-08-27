"""Type definitions for shotbot application.

This module provides TypedDict, Protocol, and type alias definitions
used throughout the application for better type safety.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Protocol, TypedDict, Union

from PySide6.QtCore import Signal


# ==============================================================================
# Core Data Classes
# ==============================================================================

@dataclass
class Shot:
    """Represents a VFX shot with metadata.
    
    This is the basic Shot dataclass without complex dependencies.
    The full implementation with thumbnail paths is in shot_model.py.
    """

    show: str
    sequence: str
    shot: str
    workspace_path: str = ""

    @property
    def full_name(self) -> str:
        """Get full shot name."""
        return f"{self.sequence}_{self.shot}"

    @property
    def display_name(self) -> str:
        """Get display-friendly name."""
        return f"{self.sequence}/{self.shot}"

    def __str__(self) -> str:
        """String representation."""
        return self.full_name

    def __hash__(self) -> int:
        """Make Shot hashable for use in sets/dicts."""
        return hash((self.show, self.sequence, self.shot))

    def __eq__(self, other: object) -> bool:
        """Check equality based on shot identity."""
        if not isinstance(other, Shot):
            return False
        return (
            self.show == other.show
            and self.sequence == other.sequence
            and self.shot == other.shot
        )


# ==============================================================================
# TypedDict Definitions for Data Structures
# ==============================================================================

class ShotDict(TypedDict):
    """Dictionary representation of a Shot."""
    show: str
    sequence: str
    shot: str
    workspace_path: str


class ThreeDESceneDict(TypedDict):
    """Dictionary representation of a 3DE scene."""
    filepath: str
    show: str
    sequence: str
    shot: str
    user: str
    filename: str
    modified_time: float
    workspace_path: str


class LauncherDict(TypedDict, total=False):
    """Dictionary representation of a custom launcher."""
    id: str
    name: str
    command: str
    description: Optional[str]
    icon: Optional[str]
    category: Optional[str]
    show_in_menu: bool
    requires_shot: bool


class ProcessInfoDict(TypedDict):
    """Information about a running process."""
    pid: int
    command: str
    start_time: float
    shot_name: Optional[str]
    launcher_id: Optional[str]
    status: Literal["running", "finished", "error"]


class CacheMetricsDict(TypedDict):
    """Cache performance metrics."""
    total_size_bytes: int
    item_count: int
    hit_rate: float
    miss_rate: float
    eviction_count: int
    last_cleanup: float


class ThumbnailInfoDict(TypedDict, total=False):
    """Thumbnail information with metadata."""
    path: str
    size_bytes: int
    width: int
    height: int
    format: str
    cached_at: float


# ==============================================================================
# Protocol Definitions for Interfaces
# ==============================================================================

class CacheProtocol(Protocol):
    """Protocol for cache implementations."""
    
    def cache_shots(self, shots: List[ShotDict]) -> None:
        """Cache shot data."""
        ...
    
    def get_cached_shots(self) -> Optional[List[ShotDict]]:
        """Retrieve cached shots."""
        ...
    
    def clear_cache(self) -> None:
        """Clear all cached data."""
        ...
    
    def get_memory_usage(self) -> CacheMetricsDict:
        """Get cache memory usage statistics."""
        ...


class WorkerProtocol(Protocol):
    """Protocol for background worker threads."""
    
    # Qt signals
    started: Signal
    finished: Signal
    error_occurred: Signal
    
    def start(self) -> None:
        """Start the worker thread."""
        ...
    
    def stop(self) -> None:
        """Stop the worker thread."""
        ...
    
    def wait(self, timeout: int = 5000) -> bool:
        """Wait for worker to finish."""
        ...


class ThumbnailProcessorProtocol(Protocol):
    """Protocol for thumbnail processing backends."""
    
    def load_thumbnail(
        self, 
        path: Union[str, Path],
        size: tuple[int, int] = (100, 100)
    ) -> Optional[Any]:
        """Load and resize a thumbnail."""
        ...
    
    def supports_format(self, format: str) -> bool:
        """Check if processor supports given format."""
        ...


class LauncherProtocol(Protocol):
    """Protocol for application launchers."""
    
    def launch(
        self,
        command: str,
        shot_name: Optional[str] = None,
        environment: Optional[Dict[str, str]] = None
    ) -> ProcessInfoDict:
        """Launch an application."""
        ...
    
    def is_running(self, process_id: Union[int, str]) -> bool:
        """Check if a process is still running."""
        ...
    
    def terminate(self, process_id: Union[int, str]) -> bool:
        """Terminate a running process."""
        ...


class FinderProtocol(Protocol):
    """Protocol for file/scene finders."""
    
    def find_all(self) -> List[Any]:
        """Find all items."""
        ...
    
    def find_for_shot(
        self,
        show: str,
        sequence: str,
        shot: str
    ) -> List[Any]:
        """Find items for a specific shot."""
        ...


class AsyncLoaderProtocol(Protocol):
    """Protocol for async shot loaders with background processing."""
    
    # Qt signals for communication
    shots_loaded: Signal
    load_failed: Signal
    finished: Signal
    
    def start(self) -> None:
        """Start the async loading process."""
        ...
    
    def stop(self) -> None:
        """Stop the async loading process."""
        ...
    
    def wait(self, timeout: int = 5000) -> bool:
        """Wait for process to finish with timeout."""
        ...


# ==============================================================================
# Type Aliases for Common Patterns
# ==============================================================================

# Path types
PathLike = Union[str, Path]
OptionalPath = Optional[PathLike]

# Qt types
SignalType = Signal
OptionalSignal = Optional[Signal]

# Shot identifiers
ShotTuple = "tuple[str, str, str]"  # (show, sequence, shot)
ShotPathTuple = "tuple[str, str, str, str]"  # (workspace_path, show, sequence, shot)

# Command types
CommandList = List[str]
CommandDict = Dict[str, Union[str, List[str], Dict[str, str]]]

# Cache keys
CacheKey = str
CacheData = Union[Dict[str, Any], List[Any], str, bytes]

# Time types
Timestamp = float
Duration = float

# ==============================================================================
# Configuration Type Definitions
# ==============================================================================

class AppSettingsDict(TypedDict, total=False):
    """Application settings dictionary."""
    shows_root: str
    username: str
    excluded_users: List[str]
    cache_dir: str
    cache_ttl_minutes: int
    max_memory_mb: int
    thumbnail_size: int
    max_concurrent_processes: int
    command_whitelist: List[str]
    debug_mode: bool
    auto_refresh: bool
    refresh_interval: int


class WindowGeometryDict(TypedDict):
    """Window geometry settings."""
    x: int
    y: int
    width: int
    height: int
    maximized: bool
    splitter_sizes: List[int]


# ==============================================================================
# Error Types
# ==============================================================================

class ErrorInfoDict(TypedDict):
    """Error information dictionary."""
    type: str
    message: str
    traceback: Optional[str]
    timestamp: float
    context: Optional[Dict[str, Any]]


# ==============================================================================
# Test Type Definitions
# ==============================================================================

class TestResultDict(TypedDict):
    """Test result information."""
    test_name: str
    passed: bool
    duration: float
    error: Optional[str]
    stdout: Optional[str]
    stderr: Optional[str]


class PerformanceMetricsDict(TypedDict):
    """Performance metrics for optimized models with async loading."""
    cache_hit_count: int
    cache_miss_count: int
    cache_hit_rate: float
    loading_in_progress: bool
    session_warmed: bool
    last_load_time: float