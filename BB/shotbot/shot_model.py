"""Shot data model and parser for ws -sg output."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

# Use typing_extensions for override (available in venv)
from typing_extensions import override

from base_shot_model import BaseShotModel

if TYPE_CHECKING:
    from cache_manager import CacheManager
    from process_pool_manager import ProcessPoolManager

from config import Config
from exceptions import WorkspaceError
from type_definitions import PerformanceMetricsDict, ShotDict
from utils import PathUtils

# Set up logger for this module
logger = logging.getLogger(__name__)

# Enable verbose debug logging if environment variable is set
DEBUG_VERBOSE = os.environ.get("SHOTBOT_DEBUG_VERBOSE", "").lower() in (
    "1",
    "true",
    "yes",
)
if DEBUG_VERBOSE:
    logger.setLevel(logging.DEBUG)
    logger.info("VERBOSE DEBUG MODE ENABLED for ShotModel")

# Sentinel value to distinguish between "not searched" and "searched but found nothing"
_NOT_SEARCHED = object()


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


@dataclass
class Shot:
    """Represents a single shot."""

    show: str
    sequence: str
    shot: str
    workspace_path: str
    _cached_thumbnail_path: Any = field(
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
            return self._cached_thumbnail_path

        # Use the unified thumbnail discovery method
        thumbnail = PathUtils.find_shot_thumbnail(  # type: ignore[attr-defined]
            Config.SHOWS_ROOT,
            self.show,
            self.sequence,
            self.shot,
        )

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


class ShotModel(BaseShotModel):
    """Synchronous shot model implementation.

    This model provides synchronous, blocking shot loading and refreshing.
    It maintains full backward compatibility with the existing API while
    inheriting common functionality from BaseShotModel.

    All signals are inherited from BaseShotModel.
    """

    def __init__(
        self,
        cache_manager: CacheManager | None = None,
        load_cache: bool = True,
    ):
        """Initialize synchronous shot model.

        Args:
            cache_manager: cache manager instance
            load_cache: Whether to load from cache on initialization
        """
        super().__init__(cache_manager, load_cache)

    @override
    def load_shots(self) -> RefreshResult:
        """Load shots synchronously (same as refresh for sync model).

        Returns:
            RefreshResult with success and change status
        """
        return self.refresh_strategy()

    @override
    def refresh_strategy(self) -> RefreshResult:
        """Fetch and parse shot list from ws -sg command.

        Uses ProcessPoolManager for optimized command execution with:
        - Command caching (30-second TTL for workspace commands)
        - Persistent bash session reuse
        - Automatic retry on session failure

        Emits signals:
        - refresh_started: When refresh begins
        - shots_changed: If shot list changes
        - error_occurred: If an error occurs
        - cache_updated: When cache is successfully updated
        - refresh_finished: When refresh completes with status

        Returns:
            RefreshResult with success status and change indicator
        """
        # Emit signal to indicate refresh is starting
        self.refresh_started.emit()

        try:
            # Save current shots for comparison (include workspace path)
            old_shot_data = {
                (shot.full_name, shot.workspace_path) for shot in self.shots
            }

            # Execute workspace command through ProcessPoolManager
            # 30-second cache TTL is appropriate for workspace commands
            # as shot assignments change infrequently
            if DEBUG_VERBOSE:
                logger.debug("Executing 'ws -sg' command via ProcessPoolManager")
                logger.debug(f"ProcessPoolManager instance: {self._process_pool}")
            try:
                output = self._process_pool.execute_workspace_command(
                    "ws -sg",
                    cache_ttl=30,  # Cache for 30 seconds
                )
                if DEBUG_VERBOSE:
                    logger.debug(
                        f"'ws -sg' command returned {len(output) if output else 0} bytes",
                    )
                    if output:
                        logger.debug(f"First 200 chars of output: {output[:200]}...")
            except TimeoutError as e:
                error_msg = f"Timeout while running ws -sg command: {e}"
                logger.error(error_msg)
                if DEBUG_VERBOSE:
                    logger.debug(f"TimeoutError details: {e}")
                self.error_occurred.emit(error_msg)
                self.refresh_finished.emit(False, False)
                return RefreshResult(success=False, has_changes=False)
            except (RuntimeError, WorkspaceError) as e:
                # Handle session failures and other runtime errors
                error_msg = f"Failed to execute ws -sg command: {e}"
                logger.error(error_msg)
                if DEBUG_VERBOSE:
                    logger.debug(f"Error details: {e}")
                    import traceback

                    logger.debug(f"Traceback: {traceback.format_exc()}")
                self.error_occurred.emit(error_msg)
                self.refresh_finished.emit(False, False)
                return RefreshResult(success=False, has_changes=False)

            # Parse output (reuse existing parser)
            try:
                if DEBUG_VERBOSE:
                    logger.debug("Parsing ws -sg output...")
                new_shots = self._parse_ws_output(output)
                if DEBUG_VERBOSE:
                    logger.debug(f"Parsed {len(new_shots)} shots from output")
            except (ValueError, WorkspaceError) as e:
                error_msg = f"Failed to parse ws -sg output: {e}"
                logger.error(error_msg)
                if DEBUG_VERBOSE:
                    logger.debug(f"Parse error details: {e}")
                self.error_occurred.emit(error_msg)
                self.refresh_finished.emit(False, False)
                return RefreshResult(success=False, has_changes=False)

            new_shot_data = {
                (shot.full_name, shot.workspace_path) for shot in new_shots
            }

            # Check if there are changes (added, removed, or path changed)
            has_changes = old_shot_data != new_shot_data

            if has_changes:
                self.shots = new_shots
                logger.info(f"Shot list updated: {len(new_shots)} shots found")

                # Emit signal to notify of changed shots
                self.shots_changed.emit(self.shots)

                # Cache the results - pass Shot objects directly
                if self.shots:
                    try:
                        self.cache_manager.cache_shots(self.shots)
                        # Emit cache updated signal
                        self.cache_updated.emit()
                    except OSError as e:
                        logger.warning(f"Failed to cache shots: {e}")
                        # Continue without caching - not critical for operation

            # Emit refresh finished signal with results
            self.refresh_finished.emit(True, has_changes)
            return RefreshResult(success=True, has_changes=has_changes)

        except Exception as e:
            # Catch any unexpected errors not handled by ProcessPoolManager
            error_msg = f"Unexpected error while fetching shots: {e}"
            logger.exception(error_msg)
            self.error_occurred.emit(error_msg)
            self.refresh_finished.emit(False, False)
            return RefreshResult(success=False, has_changes=False)

    # Note: We use the _parse_ws_output from BaseShotModel which has been
    # enhanced with the robust validation and error handling from this implementation

    def get_shot_by_index(self, index: int) -> Shot | None:
        """Get shot by index."""
        if 0 <= index < len(self.shots):
            return self.shots[index]  # type: ignore[reportReturnType]
        return None

    @override
    def find_shot_by_name(self, full_name: str) -> "Shot | None":  # type: ignore[override]
        """Find shot by full name."""
        for shot in self.shots:
            if shot.full_name == full_name:
                return shot  # type: ignore[return-value]
        return None

    def get_shot_by_name(self, full_name: str) -> Shot | None:
        """Get shot by full name (alias for find_shot_by_name)."""
        return self.find_shot_by_name(full_name)

    def invalidate_workspace_cache(self) -> None:
        """Invalidate workspace command cache.

        Useful when shot assignments have changed and immediate
        refresh is needed without waiting for cache TTL expiry.
        This forces the next refresh_shots() call to fetch fresh data.
        """
        self._process_pool.invalidate_cache("ws -sg")
        logger.info("Invalidated workspace cache for immediate refresh")

    def select_shot_by_name(self, full_name: str) -> bool:
        """Select a shot by its full name.

        Args:
            full_name: The full name of the shot to select

        Returns:
            True if the shot was found and selected, False otherwise
        """
        shot = self.find_shot_by_name(full_name)
        if shot:
            self.select_shot(shot)  # type: ignore[arg-type]
            return True
        return False

    def clear_selection(self) -> None:
        """Clear the current shot selection."""
        self.select_shot(None)

    @override
    def get_performance_metrics(self) -> PerformanceMetricsDict:
        """Get performance metrics for subprocess operations.

        Extends base metrics with process pool statistics.

        Returns:
            Combined metrics from base class and process pool
        """
        metrics = super().get_performance_metrics()
        # Add process pool metrics
        pool_metrics = self._process_pool.get_metrics()
        metrics.update(pool_metrics)
        return metrics

    # ================================================================
    # Test-Specific Accessor Methods
    # ================================================================
    # WARNING: These methods are for testing purposes ONLY.
    # They provide controlled access to private attributes for tests.
    # DO NOT use these methods in production code.

    @property
    def test_process_pool(self) -> ProcessPoolManager:
        """Test-only access to process pool manager."""
        return self._process_pool

    def test_load_from_cache(self) -> bool:
        """Test-only access to _load_from_cache method."""
        return self._load_from_cache()

    def test_parse_ws_output(self, output: str) -> list[Shot]:
        """Test-only access to _parse_ws_output method."""
        return self._parse_ws_output(output)  # type: ignore[reportReturnType]
