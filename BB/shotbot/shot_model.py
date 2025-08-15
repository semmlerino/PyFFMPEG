"""Shot data model and parser for ws -sg output."""

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, NamedTuple, Optional

if TYPE_CHECKING:
    from cache_manager import CacheManager

from config import Config
from process_pool_manager import ProcessPoolManager
from utils import FileUtils, PathUtils, ValidationUtils

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
        default=_NOT_SEARCHED, init=False, repr=False, compare=False
    )

    @property
    def full_name(self) -> str:
        """Get full shot name."""
        return f"{self.sequence}_{self.shot}"

    @property
    def thumbnail_dir(self) -> Path:
        """Get thumbnail directory path."""
        return PathUtils.build_thumbnail_path(
            Config.SHOWS_ROOT, self.show, self.sequence, self.shot
        )

    def get_thumbnail_path(self) -> Optional[Path]:
        """Get first available thumbnail or None.

        Tries three fallback options:
        1. Editorial directory thumbnails
        2. Turnover plate thumbnails
        3. Any EXR file containing '1001' in publish folder

        Results are cached after the first search to avoid repeated
        expensive filesystem operations.
        """
        # Return cached result if we've already searched
        if self._cached_thumbnail_path is not _NOT_SEARCHED:
            return self._cached_thumbnail_path

        # Perform the search and cache the result
        thumbnail = None

        # Try editorial thumbnail first
        if PathUtils.validate_path_exists(self.thumbnail_dir, "Thumbnail directory"):
            # Use utility to find first image file
            thumbnail = FileUtils.get_first_image_file(self.thumbnail_dir)
            if thumbnail:
                self._cached_thumbnail_path = thumbnail
                return thumbnail

        # Fall back to turnover plate thumbnails
        thumbnail = PathUtils.find_turnover_plate_thumbnail(  # type: ignore[attr-defined]
            Config.SHOWS_ROOT, self.show, self.sequence, self.shot
        )
        if thumbnail:
            self._cached_thumbnail_path = thumbnail
            return thumbnail

        # Third fallback: any EXR with 1001 in publish folder
        thumbnail = PathUtils.find_any_publish_thumbnail(  # type: ignore[attr-defined]
            Config.SHOWS_ROOT, self.show, self.sequence, self.shot
        )

        # Cache the result (even if None) to avoid repeated searches
        self._cached_thumbnail_path = thumbnail
        return thumbnail

    def to_dict(self) -> Dict[str, str]:
        """Convert shot to dictionary for serialization."""
        return {
            "show": self.show,
            "sequence": self.sequence,
            "shot": self.shot,
            "workspace_path": self.workspace_path,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "Shot":
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


class ShotModel:
    """Manages shot data and parsing."""

    def __init__(
        self, cache_manager: Optional["CacheManager"] = None, load_cache: bool = True
    ):
        super().__init__()
        from cache_manager import (
            CacheManager,  # Runtime import to avoid circular dependency
        )

        self.shots: List[Shot] = []
        self.cache_manager = cache_manager or CacheManager()
        self._parse_pattern = re.compile(
            r"workspace\s+(/shows/(\w+)/shots/(\w+)/(\w+))"
        )
        # Initialize ProcessPoolManager singleton
        if DEBUG_VERBOSE:
            logger.debug("Getting ProcessPoolManager singleton instance")
        self._process_pool = ProcessPoolManager.get_instance()
        if DEBUG_VERBOSE:
            logger.debug(f"ProcessPoolManager instance obtained: {self._process_pool}")

        # Only load cache if requested (allows tests to start clean)
        if load_cache:
            if DEBUG_VERBOSE:
                logger.debug("Loading shots from cache...")
            loaded = self._load_from_cache()
            if DEBUG_VERBOSE:
                logger.debug(
                    f"Cache load result: {loaded}, shots loaded: {len(self.shots)}"
                )

    def _load_from_cache(self) -> bool:
        """Load shots from cache if available."""
        cached_data = self.cache_manager.get_cached_shots()
        if cached_data:
            self.shots = [Shot.from_dict(shot_data) for shot_data in cached_data]
            return True
        return False

    def refresh_shots(self) -> RefreshResult:
        """Fetch and parse shot list from ws -sg command.

        Uses ProcessPoolManager for optimized command execution with:
        - Command caching (30-second TTL for workspace commands)
        - Persistent bash session reuse
        - Automatic retry on session failure

        Returns:
            RefreshResult with success status and change indicator
        """
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
                        f"'ws -sg' command returned {len(output) if output else 0} bytes"
                    )
                    if output:
                        logger.debug(f"First 200 chars of output: {output[:200]}...")
            except TimeoutError as e:
                logger.error(f"Timeout while running ws -sg command: {e}")
                if DEBUG_VERBOSE:
                    logger.debug(f"TimeoutError details: {e}")
                return RefreshResult(success=False, has_changes=False)
            except RuntimeError as e:
                # Handle session failures and other runtime errors
                logger.error(f"Failed to execute ws -sg command: {e}")
                if DEBUG_VERBOSE:
                    logger.debug(f"RuntimeError details: {e}")
                    import traceback

                    logger.debug(f"Traceback: {traceback.format_exc()}")
                return RefreshResult(success=False, has_changes=False)

            # Parse output (reuse existing parser)
            try:
                if DEBUG_VERBOSE:
                    logger.debug("Parsing ws -sg output...")
                new_shots = self._parse_ws_output(output)
                if DEBUG_VERBOSE:
                    logger.debug(f"Parsed {len(new_shots)} shots from output")
            except ValueError as e:
                logger.error(f"Failed to parse ws -sg output: {e}")
                if DEBUG_VERBOSE:
                    logger.debug(f"Parse error details: {e}")
                return RefreshResult(success=False, has_changes=False)

            new_shot_data = {
                (shot.full_name, shot.workspace_path) for shot in new_shots
            }

            # Check if there are changes (added, removed, or path changed)
            has_changes = old_shot_data != new_shot_data

            if has_changes:
                self.shots = new_shots
                logger.info(f"Shot list updated: {len(new_shots)} shots found")

                # Cache the results - pass Shot objects directly
                if self.shots:
                    try:
                        self.cache_manager.cache_shots(self.shots)  # type: ignore[arg-type]
                    except (OSError, IOError) as e:
                        logger.warning(f"Failed to cache shots: {e}")
                        # Continue without caching - not critical for operation

            return RefreshResult(success=True, has_changes=has_changes)

        except Exception as e:
            # Catch any unexpected errors not handled by ProcessPoolManager
            logger.exception(f"Unexpected error while fetching shots: {e}")
            return RefreshResult(success=False, has_changes=False)

    def _parse_ws_output(self, output: str) -> List[Shot]:
        """Parse ws -sg output to extract shots.

        Args:
            output: Raw output from ws -sg command

        Returns:
            List of Shot objects parsed from the output

        Raises:
            ValueError: If output is invalid or cannot be parsed
        """
        if not isinstance(output, str):
            raise ValueError(f"Expected string output, got {type(output)}")

        shots: List[Shot] = []
        lines = output.strip().split("\n")

        # If output is completely empty, that might indicate an issue
        if not output.strip():
            logger.warning("ws -sg returned empty output")
            return shots

        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line:
                continue

            match = self._parse_pattern.search(line)
            if match:
                try:
                    workspace_path = match.group(1)
                    show = match.group(2)
                    sequence = match.group(3)
                    shot_name = match.group(4)

                    # Validate extracted components using utility
                    if not ValidationUtils.validate_not_empty(
                        workspace_path,
                        show,
                        sequence,
                        shot_name,
                        names=["workspace_path", "show", "sequence", "shot_name"],
                    ):
                        logger.warning(
                            f"Line {line_num}: Missing required components in: {line}"
                        )
                        continue

                    # Extract shot number from full name (e.g., "108_BQS_0005" -> "0005")
                    shot_parts = shot_name.split("_")
                    if len(shot_parts) >= 3:
                        shot = shot_parts[-1]
                    else:
                        shot = shot_name

                    shots.append(
                        Shot(
                            show=show,
                            sequence=sequence,
                            shot=shot,
                            workspace_path=workspace_path,
                        )
                    )
                except (IndexError, AttributeError) as e:
                    logger.warning(
                        f"Line {line_num}: Failed to parse shot data from: {line} ({e})"
                    )
                    continue
            else:
                # Log unmatched lines for debugging, but don't fail
                logger.debug(f"Line {line_num}: No match for workspace pattern: {line}")

        logger.info(f"Parsed {len(shots)} shots from ws -sg output")
        return shots

    def get_shot_by_index(self, index: int) -> Optional[Shot]:
        """Get shot by index."""
        if 0 <= index < len(self.shots):
            return self.shots[index]
        return None

    def find_shot_by_name(self, full_name: str) -> Optional[Shot]:
        """Find shot by full name."""
        for shot in self.shots:
            if shot.full_name == full_name:
                return shot
        return None

    def invalidate_workspace_cache(self) -> None:
        """Invalidate workspace command cache.

        Useful when shot assignments have changed and immediate
        refresh is needed without waiting for cache TTL expiry.
        This forces the next refresh_shots() call to fetch fresh data.
        """
        self._process_pool.invalidate_cache("ws -sg")
        logger.info("Invalidated workspace cache for immediate refresh")

    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get performance metrics for subprocess operations.

        Returns:
            Dictionary containing:
            - subprocess_calls: Total subprocess calls made
            - cache_hits: Number of cache hits
            - cache_misses: Number of cache misses
            - average_response_ms: Average command execution time
            - cache_hit_rate: Percentage of requests served from cache
            - sessions: Status of persistent bash sessions
        """
        return self._process_pool.get_metrics()
