"""Model for managing previous/approved shots data."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QMutex, QMutexLocker, QObject, Qt, QTimer, Signal

from cache_manager import CacheManager
from logging_mixin import LoggingMixin
from previous_shots_finder import ParallelShotsFinder
from previous_shots_worker import PreviousShotsWorker
from shot_model import Shot
from type_definitions import ShotDict

if TYPE_CHECKING:
    from base_shot_model import BaseShotModel


class PreviousShotsModel(LoggingMixin, QObject):
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
    ) -> None:
        """Initialize the previous shots model.

        Args:
            shot_model: The active shots model to compare against.
            cache_manager: Optional cache manager for persistence.
            parent: Optional parent QObject.
        """
        super().__init__(parent)

        self._shot_model = shot_model
        self._cache_manager = cache_manager or CacheManager()
        self._finder = ParallelShotsFinder()
        self._previous_shots: list[Shot] = []
        self._is_scanning = False
        self._worker: PreviousShotsWorker | None = None

        # THREAD SAFETY: Lock for protecting _is_scanning flag
        self._scan_lock = QMutex()

        # Auto-refresh timer
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self.refresh_shots)
        self._refresh_timer.setInterval(5 * 60 * 1000)  # 5 minutes

        # Load from cache on init
        self._load_from_cache()

        self.logger.info("PreviousShotsModel initialized")

    def start_auto_refresh(self) -> None:
        """Start automatic refresh of previous shots."""
        self._refresh_timer.start()
        self.logger.info("Started auto-refresh for previous shots")

    def stop_auto_refresh(self) -> None:
        """Stop automatic refresh of previous shots."""
        self._refresh_timer.stop()
        self.logger.info("Stopped auto-refresh for previous shots")

    def _cleanup_worker_safely(self) -> None:
        """Centralized worker cleanup to prevent race conditions and crashes.

        This method ensures proper cleanup sequence:
        1. Request stop first
        2. Wait with timeout to prevent hanging
        3. Clear reference before deletion
        4. Disconnect signals to prevent late emissions
        5. Schedule deletion on event loop
        """
        with QMutexLocker(self._scan_lock):
            if self._worker is not None:
                self.logger.debug("Safely cleaning up worker thread")

                # 1. Request stop first
                self._worker.stop()

                # 2. Wait with timeout (prevent hanging)
                if not self._worker.wait(2000):
                    self.logger.warning("Worker did not stop gracefully within 2s")
                    # Force termination if necessary
                    if self._worker.isRunning():
                        self._worker.terminate()
                        self._worker.wait(1000)

                # 3. Clear reference BEFORE scheduling deletion
                worker = self._worker
                self._worker = None

                # 4. Disconnect all signals to prevent late emissions
                try:
                    worker.scan_finished.disconnect()
                    worker.error_occurred.disconnect()
                    if hasattr(worker, "progress"):
                        getattr(worker, "progress").disconnect()
                except (RuntimeError, TypeError):
                    pass  # Already disconnected

                # 5. Schedule deletion on event loop
                worker.deleteLater()
                self.logger.debug("Worker thread cleanup completed")

    def refresh_shots(self) -> bool:
        """Refresh the list of previous shots using a background worker thread.

        Returns:
            True if refresh was started, False if already scanning.
        """
        # THREAD SAFETY: Use lock to protect _is_scanning flag
        with QMutexLocker(self._scan_lock):
            if self._is_scanning:
                self.logger.debug("Already scanning for previous shots")
                return False
            self._is_scanning = True

        self.scan_started.emit()

        # Clear caches for manual refresh
        self._clear_caches_for_refresh()

        try:
            # Stop any existing worker
            if self._worker is not None:
                self.logger.debug("Stopping existing worker before starting new scan")
                self._cleanup_worker_safely()

            # Get active shots from the main model
            active_shots = self._shot_model.get_shots()

            # Create and configure worker thread
            from config import Config

            self._worker = PreviousShotsWorker(
                active_shots=active_shots,
                username=self._finder.username,
                shows_root=Path(Config.SHOWS_ROOT),  # Use configured shows root
                parent=self,  # Set parent for proper cleanup hierarchy
            )

            # Connect worker signals with QueuedConnection for thread safety
            self._worker.scan_finished.connect(
                self._on_scan_finished, Qt.ConnectionType.QueuedConnection
            )
            self._worker.error_occurred.connect(
                self._on_scan_error, Qt.ConnectionType.QueuedConnection
            )

            # Start worker thread
            self.logger.info("Starting previous shots scan in background thread")
            self._worker.start()

            return True

        except Exception as e:
            self.logger.error(f"Error starting previous shots scan: {e}")
            # Reset scanning flag on error
            with QMutexLocker(self._scan_lock):
                self._is_scanning = False
            self.scan_finished.emit()
            return False

    def _on_scan_finished(self, approved_shots: list[dict[str, str]]) -> None:
        """Handle worker completion.

        Args:
            approved_shots: List of approved shot dictionaries found by worker.
        """
        try:
            # Convert dictionaries to Shot objects
            shot_objects: list[Shot] = (
                [
                    Shot(
                        show=shot_dict["show"],
                        sequence=shot_dict["sequence"],
                        shot=shot_dict["shot"],
                        workspace_path=shot_dict["workspace_path"],
                    )
                    for shot_dict in approved_shots
                ]
                if approved_shots
                else []
            )

            # Check if there are changes
            has_changes = self._has_changes(shot_objects)

            if has_changes:
                self._previous_shots = shot_objects
                self._save_to_cache()
                self.shots_updated.emit()
                self.logger.info(
                    f"Updated previous shots: {len(self._previous_shots)} shots"
                )
            else:
                self.logger.debug("No changes in previous shots")

        except Exception as e:
            self.logger.error(f"Error processing scan results: {e}")
        finally:
            # Reset scanning flag
            with QMutexLocker(self._scan_lock):
                self._is_scanning = False
            # Use centralized cleanup
            self._cleanup_worker_safely()
            self.scan_finished.emit()

    def _on_scan_error(self, error_msg: str) -> None:
        """Handle worker error.

        Args:
            error_msg: Error message from worker.
        """
        self.logger.error(f"Previous shots scan error: {error_msg}")
        # Reset scanning flag
        with QMutexLocker(self._scan_lock):
            self._is_scanning = False
        # Use centralized cleanup
        self._cleanup_worker_safely()
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

    def get_shot_details(self, shot: Shot) -> dict[str, str]:
        """Get detailed information about a shot.

        Args:
            shot: Shot to get details for.

        Returns:
            Dictionary with shot details.
        """
        # Type assertion since finder returns string values
        return dict[str, str](self._finder.get_shot_details(shot))

    def _load_from_cache(self) -> None:
        """Load previous shots from cache."""
        try:
            # Use the correct method: get_cached_previous_shots()
            cached_data = self._cache_manager.get_cached_previous_shots()
            if cached_data:
                self._previous_shots = [
                    Shot(
                        show=s["show"],
                        sequence=s["sequence"],
                        shot=s["shot"],
                        workspace_path=s.get("workspace_path", ""),
                    )
                    for s in cached_data
                ]
                self.logger.info(
                    f"Loaded {len(self._previous_shots)} previous shots from cache"
                )
        except Exception as e:
            self.logger.error(f"Error loading previous shots from cache: {e}")

    def _save_to_cache(self) -> None:
        """Save previous shots to cache."""
        try:
            cache_data: list[ShotDict] = [
                ShotDict(
                    show=s.show,
                    sequence=s.sequence,
                    shot=s.shot,
                    workspace_path=s.workspace_path,
                )
                for s in self._previous_shots
            ]
            # Use the correct method: cache_previous_shots()
            self._cache_manager.cache_previous_shots(cache_data)
            self.logger.debug(
                f"Saved {len(self._previous_shots)} previous shots to cache"
            )
        except Exception as e:
            self.logger.error(f"Error saving previous shots to cache: {e}")

    def clear_cache(self) -> None:
        """Clear the cached previous shots."""
        try:
            self._cache_manager.clear_cached_data("previous_shots")
            self.logger.info("Cleared previous shots cache")
        except Exception as e:
            self.logger.error(f"Error clearing previous shots cache: {e}")

    def _clear_caches_for_refresh(self) -> None:
        """Clear all relevant caches for manual refresh.

        This method clears directory caches, path caches, and filesystem caches
        to ensure fresh data when manually refreshing.
        """
        try:
            # Clear our own cache
            self.clear_cache()

            # Clear directory cache in 3DE scene finder
            from threede_scene_finder import ThreeDESceneFinder

            if hasattr(ThreeDESceneFinder, "refresh_cache"):
                cleared_count = ThreeDESceneFinder.refresh_cache()
                self.logger.debug(f"Cleared {cleared_count} directory cache entries")

            # Clear path cache in utils
            from utils import clear_all_caches

            clear_all_caches()
            self.logger.debug("Cleared path validation caches")

            self.logger.info("Successfully cleared all caches for manual refresh")

        except Exception as e:
            self.logger.error(f"Error clearing caches for refresh: {e}")

    def cleanup(self) -> None:
        """Clean up resources and stop worker thread."""
        self.logger.debug("PreviousShotsModel cleanup initiated")
        self.stop_auto_refresh()
        self._cleanup_worker_safely()  # Use centralized cleanup
        self.logger.info("PreviousShotsModel cleanup completed")

    def is_scanning(self) -> bool:
        """Check if currently scanning for shots.

        Returns:
            True if scanning is in progress.
        """
        # THREAD SAFETY: Use lock when reading _is_scanning
        with QMutexLocker(self._scan_lock):
            return self._is_scanning
