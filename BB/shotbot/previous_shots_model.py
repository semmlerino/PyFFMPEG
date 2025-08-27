"""Model for managing previous/approved shots data."""

import logging
import threading
from typing import Dict, List, Optional

from PySide6.QtCore import QObject, QTimer, Signal

from cache_manager import CacheManager
from previous_shots_finder import PreviousShotsFinder
from base_shot_model import BaseShotModel
from shot_model import Shot

logger = logging.getLogger(__name__)


class PreviousShotsModel(QObject):
    """Model for managing approved shots that are no longer active.

    This model maintains a list of shots the user has worked on that
    are no longer in the active workspace (i.e., approved/completed).
    """

    # Signals
    shots_updated = Signal()
    scan_started = Signal()
    scan_finished = Signal()
    scan_progress = Signal(int, int)  # current, total

    def __init__(
        self,
        shot_model: BaseShotModel,
        cache_manager: Optional[CacheManager] = None,
        parent: Optional[QObject] = None,
    ):
        """Initialize the previous shots model.

        Args:
            shot_model: The active shots model to compare against.
            cache_manager: Optional cache manager for persistence.
            parent: Optional parent QObject.
        """
        super().__init__(parent)

        self._shot_model = shot_model
        self._cache_manager = cache_manager or CacheManager()
        self._finder = PreviousShotsFinder()
        self._previous_shots: List[Shot] = []
        self._is_scanning = False

        # THREAD SAFETY: Lock for protecting _is_scanning flag
        self._scan_lock = threading.Lock()

        # Auto-refresh timer
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self.refresh_shots)
        self._refresh_timer.setInterval(5 * 60 * 1000)  # 5 minutes

        # Load from cache on init
        self._load_from_cache()

        logger.info("PreviousShotsModel initialized")

    def start_auto_refresh(self) -> None:
        """Start automatic refresh of previous shots."""
        self._refresh_timer.start()
        logger.info("Started auto-refresh for previous shots")

    def stop_auto_refresh(self) -> None:
        """Stop automatic refresh of previous shots."""
        self._refresh_timer.stop()
        logger.info("Stopped auto-refresh for previous shots")

    def refresh_shots(self) -> bool:
        """Refresh the list of previous shots.

        Returns:
            True if refresh was started, False if already scanning.
        """
        # THREAD SAFETY: Use lock to protect _is_scanning flag
        with self._scan_lock:
            if self._is_scanning:
                logger.debug("Already scanning for previous shots")
                return False
            self._is_scanning = True

        self.scan_started.emit()

        try:
            # Get active shots from the main model
            active_shots = self._shot_model.get_shots()

            # Find approved shots
            approved_shots = self._finder.find_approved_shots(active_shots)

            # Check if there are changes
            has_changes = self._has_changes(approved_shots)

            if has_changes:
                self._previous_shots = approved_shots
                self._save_to_cache()
                self.shots_updated.emit()
                logger.info(
                    f"Updated previous shots: {len(self._previous_shots)} shots"
                )
            else:
                logger.debug("No changes in previous shots")

            return True

        except Exception as e:
            logger.error(f"Error refreshing previous shots: {e}")
            return False

        finally:
            # THREAD SAFETY: Use lock when resetting flag
            with self._scan_lock:
                self._is_scanning = False
            self.scan_finished.emit()

    def _has_changes(self, new_shots: List[Shot]) -> bool:
        """Check if the shot list has changed.

        Args:
            new_shots: New list of shots to compare.

        Returns:
            True if there are changes, False otherwise.
        """
        if len(new_shots) != len(self._previous_shots):
            return True

        # Create sets for comparison
        current_ids = {(s.show, s.sequence, s.shot) for s in self._previous_shots}
        new_ids = {(s.show, s.sequence, s.shot) for s in new_shots}

        return current_ids != new_ids

    def get_shots(self) -> List[Shot]:
        """Get the list of previous/approved shots.

        Returns:
            List of Shot objects for approved shots.
        """
        return self._previous_shots.copy()

    def get_shot_count(self) -> int:
        """Get the number of previous shots.

        Returns:
            Number of approved shots.
        """
        return len(self._previous_shots)

    def get_shot_by_name(self, shot_name: str) -> Optional[Shot]:
        """Get a shot by its name.

        Args:
            shot_name: Name of the shot to find.

        Returns:
            Shot object if found, None otherwise.
        """
        for shot in self._previous_shots:
            if shot.shot == shot_name:
                return shot
        return None

    def get_shot_details(self, shot: Shot) -> Dict:
        """Get detailed information about a shot.

        Args:
            shot: Shot to get details for.

        Returns:
            Dictionary with shot details.
        """
        return self._finder.get_shot_details(shot)

    def _load_from_cache(self) -> None:
        """Load previous shots from cache."""
        try:
            # Use the correct method: get_cached_previous_shots()
            cached_data = self._cache_manager.get_cached_previous_shots()
            if cached_data and isinstance(cached_data, list):
                self._previous_shots = [
                    Shot(
                        show=s["show"],
                        sequence=s["sequence"],
                        shot=s["shot"],
                        workspace_path=s.get("workspace_path", ""),
                    )
                    for s in cached_data
                ]
                logger.info(
                    f"Loaded {len(self._previous_shots)} previous shots from cache"
                )
        except Exception as e:
            logger.error(f"Error loading previous shots from cache: {e}")

    def _save_to_cache(self) -> None:
        """Save previous shots to cache."""
        try:
            cache_data = [
                {
                    "show": s.show,
                    "sequence": s.sequence,
                    "shot": s.shot,
                    "workspace_path": s.workspace_path,
                }
                for s in self._previous_shots
            ]
            # Use the correct method: cache_previous_shots()
            self._cache_manager.cache_previous_shots(cache_data)
            logger.debug(f"Saved {len(self._previous_shots)} previous shots to cache")
        except Exception as e:
            logger.error(f"Error saving previous shots to cache: {e}")

    def clear_cache(self) -> None:
        """Clear the cached previous shots."""
        try:
            self._cache_manager.clear_cached_data("previous_shots")
            logger.info("Cleared previous shots cache")
        except Exception as e:
            logger.error(f"Error clearing previous shots cache: {e}")

    def is_scanning(self) -> bool:
        """Check if currently scanning for shots.

        Returns:
            True if scanning is in progress.
        """
        # THREAD SAFETY: Use lock when reading _is_scanning
        with self._scan_lock:
            return self._is_scanning
