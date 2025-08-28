"""Base class for shot models with shared functionality."""

from __future__ import annotations

import logging
import os
import re
from abc import abstractmethod
from typing import TYPE_CHECKING, Any

from type_definitions import PerformanceMetricsDict

from PySide6.QtCore import QObject, Signal

if TYPE_CHECKING:
    from cache_manager import CacheManager
    from shot_model import Shot

from exceptions import WorkspaceError
from process_pool_manager import ProcessPoolManager
from utils import ValidationUtils

logger = logging.getLogger(__name__)

# Enable verbose debug logging if environment variable is set
DEBUG_VERBOSE = os.environ.get("SHOTBOT_DEBUG_VERBOSE", "").lower() in (
    "1",
    "true",
    "yes",
)


class BaseShotModel(QObject):
    """Abstract base class for shot models with shared functionality.

    This base class provides common signals, shot parsing logic, caching,
    and performance metrics collection that is shared between ShotModel
    and OptimizedShotModel implementations.

    Subclasses must implement:
        - load_shots(): Method to load shots (sync or async)
        - refresh_strategy(): How to refresh the shot list
    """

    # Common Qt signals
    shots_loaded = Signal(list)  # List of Shot objects
    shots_changed = Signal(list)  # List of Shot objects
    refresh_started = Signal()
    refresh_finished = Signal(bool, bool)  # success, has_changes
    error_occurred = Signal(str)  # Error message
    shot_selected = Signal(object)  # Shot object
    cache_updated = Signal()

    def __init__(
        self,
        cache_manager: "CacheManager" | None = None,
        load_cache: bool = True,
    ):
        """Initialize base shot model.

        Args:
            cache_manager: cache manager instance
            load_cache: Whether to load from cache on init
        """
        super().__init__()
        from cache_manager import CacheManager

        self.shots: list[Any] = []
        self.cache_manager = cache_manager or CacheManager()
        self._parse_pattern = re.compile(
            r"workspace\s+(/shows/(\w+)/shots/(\w+)/(\w+))",
        )
        self._selected_shot: "Shot" | None = None

        # Initialize ProcessPoolManager singleton
        if DEBUG_VERBOSE:
            logger.debug("Getting ProcessPoolManager singleton instance")
        self._process_pool = ProcessPoolManager.get_instance()

        # Performance metrics
        self._last_refresh_time = 0.0
        self._total_refreshes = 0
        self._cache_hits = 0
        self._cache_misses = 0

        # Load cache if requested
        if load_cache:
            self._load_from_cache()

    def _load_from_cache(self) -> bool:
        """Load shots from cache if available.

        Returns:
            True if cache was loaded, False otherwise
        """
        cached_data = self.cache_manager.get_cached_shots()
        if cached_data:
            from shot_model import Shot

            self.shots = [Shot.from_dict(shot_data) for shot_data in cached_data]
            self.shots_loaded.emit(self.shots)
            self._cache_hits += 1
            logger.info(f"Loaded {len(self.shots)} shots from cache")
            return True
        self._cache_misses += 1
        return False

    def _parse_ws_output(self, output: str) -> list[Any]:
        """Parse ws -sg output to extract shots.

        Args:
            output: Raw output from ws -sg command

        Returns:
            List of Shot objects parsed from the output

        Raises:
            WorkspaceError: If output is invalid or cannot be parsed
        """
        if not isinstance(output, str):
            raise WorkspaceError(
                "Invalid workspace output type",
                command="ws -sg",
                details={"expected": "str", "got": str(type(output))},
            )

        from shot_model import Shot

        shots: list[Any] = []
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
                            f"Line {line_num}: Missing required components in: {line}",
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
                        ),
                    )
                except (IndexError, AttributeError) as e:
                    logger.warning(
                        f"Line {line_num}: Failed to parse shot data from: {line} ({e})",
                    )
                    continue
            else:
                # Log unmatched lines for debugging, but don't fail
                logger.debug(f"Line {line_num}: No match for workspace pattern: {line}")

        logger.info(f"Parsed {len(shots)} shots from ws -sg output")
        return shots

    def _check_for_changes(self, new_shots: list[Any]) -> bool:
        """Check if the shot list has changed.

        Args:
            new_shots: New list of shots to compare

        Returns:
            True if shots changed, False otherwise
        """
        # Compare shot data including workspace paths
        old_shot_data = {(shot.full_name, shot.workspace_path) for shot in self.shots}
        new_shot_data = {(shot.full_name, shot.workspace_path) for shot in new_shots}
        return old_shot_data != new_shot_data

    def get_shots(self) -> list[Any]:
        """Get current list of shots.

        Returns:
            List of Shot objects
        """
        return self.shots

    def get_shot_count(self) -> int:
        """Get number of shots.

        Returns:
            Number of shots
        """
        return len(self.shots)

    def select_shot(self, shot: Any | None) -> None:
        """Select a shot and emit signal.

        Args:
            shot: Shot to select or None to clear selection
        """
        self._selected_shot = shot
        self.shot_selected.emit(shot)

    def get_selected_shot(self) -> Any | None:
        """Get currently selected shot.

        Returns:
            Selected shot or None
        """
        return self._selected_shot

    def find_shot_by_name(self, full_name: str) -> Any | None:
        """Find a shot by its full name.

        Args:
            full_name: Full shot name (SHOW.SEQ.SHOT)

        Returns:
            Shot object if found, None otherwise
        """
        for shot in self.shots:
            if shot.full_name == full_name:
                return shot
        return None

    def get_performance_metrics(self) -> PerformanceMetricsDict:
        """Get performance metrics.

        Returns:
            Performance metrics dictionary
        """
        cache_total = self._cache_hits + self._cache_misses
        return {
            "total_shots": len(self.shots),
            "total_refreshes": self._total_refreshes,
            "last_refresh_time": self._last_refresh_time,
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "cache_hit_rate": self._cache_hits / max(1, cache_total),
        }

    @abstractmethod
    def load_shots(self) -> Any:
        """Load shots using implementation-specific strategy.

        Subclasses must implement this to provide either synchronous
        or asynchronous loading behavior.

        Returns:
            RefreshResult with success and change status
        """
        pass

    @abstractmethod
    def refresh_strategy(self) -> Any:
        """Refresh shot list using implementation-specific strategy.

        Subclasses must implement this to define how refreshing works
        (e.g., synchronous blocking vs asynchronous background).

        Returns:
            RefreshResult with success and change status
        """
        pass

    def refresh_shots(self) -> Any:
        """Public API to refresh shots.

        Delegates to implementation-specific refresh_strategy.

        Returns:
            RefreshResult with success and change status
        """
        self._total_refreshes += 1
        return self.refresh_strategy()
