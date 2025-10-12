"""Type definitions for shotbot application.

This module provides TypedDict, Protocol, and type alias definitions
used throughout the application for better type safety.
"""

from __future__ import annotations

# Standard library imports
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, NamedTuple, Protocol, TypedDict, TypeVar, cast

# Third-party imports
from PySide6.QtCore import Signal

# ==============================================================================
# Core Result Types
# ==============================================================================


class RefreshResult(NamedTuple):
    """Result of shot refresh operation with success status and change detection.

    This NamedTuple provides type-safe results from ShotModel.refresh_shots() operations,
    allowing callers to determine both operation success and whether the shot list
    actually changed. This enables efficient UI updates that only occur when needed.

    Attributes:
        success (bool): Whether the refresh operation completed successfully.
            True indicates the workspace command executed without errors and
            the shot list was parsed. False indicates command failure, timeout,
            or parsing errors that prevented shot list updates.

        has_changes (bool): Whether the shot list changed compared to the previous
            refresh. True indicates new shots were added, existing shots were
            removed, or shot metadata changed. False indicates the shot list
            is identical to the previous state. Only meaningful when success=True.

    Examples:
        Basic usage with tuple unpacking:
            >>> result = shot_model.refresh_shots()
            >>> success, has_changes = result
            >>> if success and has_changes:
            ...     update_ui_with_new_shots()

        Explicit attribute access:
            >>> result = shot_model.refresh_shots()
            >>> if result.success:
            ...     logger.info(f"Refresh successful, changes: {result.has_changes}")
            ... else:
            ...     logger.error("Shot refresh failed")

        Conditional UI updates:
            >>> result = shot_model.refresh_shots()
            >>> if result.success and result.has_changes:
            ...     shot_grid.update_shots(shot_model.get_shots())
            ... elif result.success:
            ...     logger.debug("Shot list unchanged, skipping UI update")
            ... else:
            ...     show_error_dialog("Failed to refresh shots")

    Type Safety:
        This NamedTuple enforces type safety at runtime and provides IDE
        autocompletion. It replaces the previous tuple return type:

        Before: tuple[bool, bool]  # Unclear which bool means what
        After:  RefreshResult      # Self-documenting with named fields
    """

    success: bool
    has_changes: bool


# ==============================================================================
# TypedDict Definitions for Data Structures
# ==============================================================================


class ShotDict(TypedDict):
    """Dictionary representation of a Shot."""

    show: str
    sequence: str
    shot: str
    workspace_path: str


# Sentinel value to distinguish between "not searched" and "searched but found nothing"
_NOT_SEARCHED = object()


@dataclass(slots=True)
class Shot:
    """Represents a single shot.

    This class is defined in type_definitions to avoid circular imports between
    shot_model.py and base_shot_model.py. It provides the core Shot data structure
    used throughout the application.
    """

    show: str
    sequence: str
    shot: str
    workspace_path: str
    _cached_thumbnail_path: Path | None | object = field(
        default=_NOT_SEARCHED,
        init=False,
        repr=False,
        compare=False,
    )

    @property
    def full_name(self) -> str:
        """Get full shot name."""
        return f"{self.sequence}_{self.shot}"

    @property
    def thumbnail_dir(self) -> Path:
        """Get thumbnail directory path."""
        # Import here to avoid circular dependency at module level
        from config import Config
        from utils import PathUtils

        return PathUtils.build_thumbnail_path(
            Config.SHOWS_ROOT,
            self.show,
            self.sequence,
            self.shot,
        )

    def get_thumbnail_path(self) -> Path | None:
        """Get first available thumbnail or None.

        Uses the unified thumbnail discovery logic from PathUtils.find_shot_thumbnail()
        to ensure consistent thumbnails across all views.

        Results are cached after the first search to avoid repeated
        expensive filesystem operations.
        """
        # Return cached result if we've already searched
        if self._cached_thumbnail_path is not _NOT_SEARCHED:
            return cast("Path | None", self._cached_thumbnail_path)

        # Import here to avoid circular dependency at module level
        from config import Config
        from utils import PathUtils

        # Use the unified thumbnail discovery method
        # Note: PathUtils.find_shot_thumbnail returns Path | None, but basedpyright
        # cannot infer the return type from the dynamic PathUtils class
        result = PathUtils.find_shot_thumbnail(  # type: ignore[attr-defined]
            Config.SHOWS_ROOT,
            self.show,
            self.sequence,
            self.shot,
        )
        # Explicit cast to help type checker understand the return type
        thumbnail: Path | None = cast("Path | None", result)

        # Cache the result (even if None) to avoid repeated searches
        self._cached_thumbnail_path = thumbnail
        return thumbnail

    def to_dict(self) -> ShotDict:
        """Convert shot to dictionary for serialization."""
        return {
            "show": self.show,
            "sequence": self.sequence,
            "shot": self.shot,
            "workspace_path": self.workspace_path,
        }

    @classmethod
    def from_dict(cls, data: ShotDict) -> Shot:
        """Create shot from dictionary data."""
        shot = cls(
            show=data["show"],
            sequence=data["sequence"],
            shot=data["shot"],
            workspace_path=data["workspace_path"],
        )
        # Don't restore cached thumbnail path from dict - let it be re-discovered if needed
        # This ensures we don't cache stale paths across sessions
        return shot


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
    description: str | None
    icon: str | None
    category: str | None
    show_in_menu: bool
    requires_shot: bool


class ProcessInfoDict(TypedDict):
    """Information about a running process."""

    pid: int
    command: str
    start_time: float
    shot_name: str | None
    launcher_id: str | None
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

    def cache_shots(self, shots: list[ShotDict]) -> None:
        """Cache shot data."""
        ...

    def get_cached_shots(self) -> list[ShotDict] | None:
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
        self, path: str | Path, size: tuple[int, int] = (100, 100)
    ) -> object | None:  # Returns QPixmap/QImage/PIL.Image depending on backend
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
        shot_name: str | None = None,
        environment: dict[str, str] | None = None,
    ) -> ProcessInfoDict:
        """Launch an application."""
        ...

    def is_running(self, process_id: int | str) -> bool:
        """Check if a process is still running."""
        ...

    def terminate(self, process_id: int | str) -> bool:
        """Terminate a running process."""
        ...


# Generic type variable for finder results
T = TypeVar("T")


class FinderProtocol(Protocol[T]):
    """Protocol for file/scene finders."""

    def find_all(self) -> list[T]:
        """Find all items."""
        ...

    def find_for_shot(self, show: str, sequence: str, shot: str) -> list[T]:
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
PathLike = str | Path
# Removed: Path = PathLike | None (was shadowing pathlib.Path import)
# Use PathLike | None directly where needed

# Qt types
SignalType = Signal
# Removed: Signal = Signal | None (circular reference)
# Use Signal | None directly where needed

# Shot identifiers
ShotTuple = "tuple[str, str, str]"  # (show, sequence, shot)
ShotPathTuple = "tuple[str, str, str, str]"  # (workspace_path, show, sequence, shot)

# Command types
CommandList = list[str]
CommandDict = dict[str, str | list[str] | dict[str, str]]

# Cache keys
CacheKey = str
# Cache data can be various types of serializable data
CacheData = (
    dict[str, str | int | float | bool | None] | list[dict[str, str]] | str | bytes
)

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
    excluded_users: list[str]
    cache_dir: str
    cache_ttl_minutes: int
    max_memory_mb: int
    thumbnail_size: int
    max_concurrent_processes: int
    command_whitelist: list[str]
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
    splitter_sizes: list[int]


# ==============================================================================
# Error Types
# ==============================================================================


class ErrorInfoDict(TypedDict):
    """Error information dictionary."""

    type: str
    message: str
    traceback: str | None
    timestamp: float
    context: dict[str, str | int | float | bool] | None


# ==============================================================================
# Test Type Definitions
# ==============================================================================


class TestResultDict(TypedDict):
    """Test result information."""

    test_name: str
    passed: bool
    duration: float
    error: str | None
    stdout: str | None
    stderr: str | None


class PerformanceMetricsDict(TypedDict):
    """Performance metrics for shot models.

    Contains base metrics from BaseShotModel and extended metrics
    from OptimizedShotModel with async loading support.
    """

    # Base metrics from BaseShotModel.get_performance_metrics()
    total_shots: int
    total_refreshes: int
    last_refresh_time: float
    cache_hits: int
    cache_misses: int
    cache_hit_rate: float

    # Extended metrics from OptimizedShotModel (optional for base model)
    cache_hit_count: int
    cache_miss_count: int
    loading_in_progress: bool
    session_warmed: bool


class ValidationResultDict(TypedDict, total=False):
    """Result of cache validation operations.

    All fields except 'valid' are optional to allow for partial updates
    and error conditions.
    """

    valid: bool
    issues_found: int
    issues_fixed: int
    orphaned_files: int
    missing_files: int
    size_mismatches: int
    memory_usage_corrected: bool
    details: list[str]
    error: str | None  # Added for error handling in validate_cache line 106


class CacheDataDict(TypedDict):
    """Cache data structure for storing shots or scenes."""

    timestamp: str
    version: str
    count: int
    data: list[ShotDict] | list[ThreeDESceneDict]
    metadata: dict[str, str | int | float | bool] | None


class CacheInfoDict(TypedDict):
    """Detailed cache information for debugging."""

    cache_file: str
    exists: bool
    size_bytes: int
    modified_time: str | None
    is_expired: bool
    entry_count: int
    last_update: str | None
    metadata: dict[str, str | int | float | bool] | None


class MemoryStatsDict(TypedDict):
    """Memory usage statistics from memory manager."""

    current_usage: int
    limit: int
    usage_percentage: float
    item_count: int
    oldest_item: str | None
    newest_item: str | None
    evictions_performed: int


class FailureInfoDict(TypedDict):
    """Information about a failed thumbnail attempt."""

    path: str
    attempts: int
    last_attempt: str
    next_retry: str
    backoff_minutes: int
    error: str | None


class CacheEfficiencyDict(TypedDict):
    """Cache efficiency analysis results."""

    total_files: int
    total_size_mb: float
    average_file_size_kb: float
    oldest_file: str | None
    newest_file: str | None
    access_patterns: dict[str, int]
    recommended_actions: list[str]
