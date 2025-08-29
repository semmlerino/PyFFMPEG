"""Model for managing previous/approved shots data."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Dict

from PySide6.QtCore import QObject, QTimer, Signal

from base_shot_model import BaseShotModel
from cache_manager import CacheManager
from previous_shots_finder import PreviousShotsFinder
from previous_shots_worker import PreviousShotsWorker
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
        cache_manager: CacheManager | None = None,
        parent: QObject | None = None,
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
        self._previous_shots: list[Shot] = []
        self._is_scanning = False
        self._worker: PreviousShotsWorker | None = None

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
        """Refresh the list of previous shots using a background worker thread.

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
            # Stop any existing worker
            if self._worker is not None:
                logger.debug("Stopping existing worker")
                self._worker.stop()
                self._worker.wait(1000)  # Wait up to 1 second
                self._worker = None

            # Get active shots from the main model
            active_shots = self._shot_model.get_shots()

            # Create and configure worker thread
            self._worker = PreviousShotsWorker(
                active_shots=active_shots,
                username=self._finder.username,
                shows_root=Path("/shows"),  # Use default shows root
            )

            # Connect worker signals
            self._worker.scan_finished.connect(self._on_scan_finished)
            self._worker.error_occurred.connect(self._on_scan_error)
            
            # Start worker thread
            logger.info("Starting previous shots scan in background thread")
            self._worker.start()

            return True

        except Exception as e:
            logger.error(f"Error starting previous shots scan: {e}")
            # Reset scanning flag on error
            with self._scan_lock:
                self._is_scanning = False
            self.scan_finished.emit()
            return False

    def _on_scan_finished(self, approved_shots: list) -> None:
        """Handle worker completion.
        
        Args:
            approved_shots: List of approved shots found by worker.
        """
        try:
            # Convert dictionaries back to Shot objects if needed
            if approved_shots and isinstance(approved_shots[0], dict):
                approved_shots = [Shot.from_dict(shot_dict) for shot_dict in approved_shots]
            
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
                
        except Exception as e:
            logger.error(f"Error processing scan results: {e}")
        finally:
            # Reset scanning flag and cleanup worker
            with self._scan_lock:
                self._is_scanning = False
            if self._worker:
                self._worker.deleteLater()
                self._worker = None
            self.scan_finished.emit()

    def _on_scan_error(self, error_msg: str) -> None:
        """Handle worker error.
        
        Args:
            error_msg: Error message from worker.
        """
        logger.error(f"Previous shots scan error: {error_msg}")
        # Reset scanning flag and cleanup
        with self._scan_lock:
            self._is_scanning = False
        if self._worker:
            self._worker.deleteLater()
            self._worker = None
        self.scan_finished.emit()

    def _has_changes(self, new_shots: list[Shot]) -> bool:
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

    def get_shots(self) -> list[Shot]:
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

    def get_shot_by_name(self, shot_name: str) -> Shot | None:
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

    def cleanup(self) -> None:
        """Clean up resources and stop worker thread."""
        self.stop_auto_refresh()
        if self._worker is not None:
            logger.debug("Stopping worker thread for cleanup")
            self._worker.stop()
            self._worker.wait(2000)  # Wait up to 2 seconds
            self._worker.deleteLater()
            self._worker = None
    
    def is_scanning(self) -> bool:
        """Check if currently scanning for shots.

        Returns:
            True if scanning is in progress.
        """
        # THREAD SAFETY: Use lock when reading _is_scanning
        with self._scan_lock:
            return self._is_scanning
