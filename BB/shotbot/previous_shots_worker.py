"""Background worker for scanning previous/approved shots."""

import logging
import time
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QThread, Signal

from previous_shots_finder import PreviousShotsFinder
from shot_model import Shot

logger = logging.getLogger(__name__)


class PreviousShotsWorker(QThread):
    """Background worker thread for finding approved shots.

    This worker runs in a separate thread to avoid blocking the UI
    while scanning the filesystem for user shots.
    """

    # Signals
    started = Signal()  # Emitted when scan starts
    shot_found = Signal(dict)  # Emitted for each shot found
    scan_progress = Signal(int, int, str)  # current, total, current_operation
    scan_finished = Signal(list)  # List of all shots found
    error_occurred = Signal(str)  # Error message

    def __init__(
        self,
        active_shots: List[Shot],
        username: Optional[str] = None,
        shows_root: Path = Path("/shows"),
        parent=None,
    ):
        """Initialize the worker thread.

        Args:
            active_shots: List of currently active shots to filter out.
            username: Username to search for (uses current if None).
            shows_root: Root directory to search.
            parent: Optional parent QObject.
        """
        super().__init__(parent)

        self._active_shots = active_shots
        self._shows_root = shows_root
        self._finder = PreviousShotsFinder(username)
        self._should_stop = False
        self._found_shots: List[Shot] = []

        logger.info(
            f"PreviousShotsWorker initialized for user: {self._finder.username}"
        )

    def stop(self) -> None:
        """Request the worker to stop."""
        self._should_stop = True
        logger.debug("Stop requested for PreviousShotsWorker")

    def run(self) -> None:
        """Run the background scanning process."""
        logger.info("Starting previous shots scan")
        start_time = time.time()

        # Emit started signal
        self.started.emit()

        try:
            # Emit initial progress
            self.scan_progress.emit(0, 100, "Initializing scan...")

            # PERFORMANCE FIX: Use finder's efficient find command instead of manual traversal
            # This avoids duplicate filesystem scanning
            self.scan_progress.emit(10, 100, "Scanning filesystem...")
            all_user_shots = self._finder.find_user_shots(self._shows_root)

            if self._should_stop:
                logger.info("Scan stopped by user request")
                return

            self.scan_progress.emit(50, 100, "Filtering approved shots...")
            # Filter to get only approved shots
            approved_shots = self._finder.filter_approved_shots(
                all_user_shots, self._active_shots
            )

            # Convert to dictionaries for signal emission
            shot_dicts = []
            total_shots = len(approved_shots)

            for i, shot in enumerate(approved_shots):
                if self._should_stop:
                    break

                # Emit progress for processing each shot
                progress = 50 + int((i / total_shots) * 40)  # 50-90% range
                self.scan_progress.emit(
                    progress, 100, f"Processing shot {i + 1} of {total_shots}"
                )

                shot_dict = {
                    "show": shot.show,
                    "sequence": shot.sequence,
                    "shot": shot.shot,
                    "workspace_path": shot.workspace_path,
                }
                shot_dicts.append(shot_dict)
                self.shot_found.emit(shot_dict)

            # Final progress update
            self.scan_progress.emit(100, 100, "Scan completed")

            elapsed = time.time() - start_time
            logger.info(
                f"Previous shots scan completed in {elapsed:.2f}s. "
                f"Found {len(approved_shots)} approved shots."
            )

            # Emit final results
            self.scan_finished.emit(shot_dicts)

        except Exception as e:
            error_msg = f"Error during previous shots scan: {e}"
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)

    def _scan_for_user_shots(self) -> List[Shot]:
        """DEPRECATED: Use self._finder.find_user_shots() instead.

        This method duplicates functionality already in PreviousShotsFinder.
        Kept for backwards compatibility but should not be used.

        Returns:
            List of Shot objects where user has work.
        """
        shots = []

        try:
            # For progress tracking, we'll estimate based on shows
            if self._shows_root.exists():
                show_dirs = [
                    d
                    for d in self._shows_root.iterdir()
                    if d.is_dir() and not d.name.startswith(".")
                ]
                total_shows = len(show_dirs)

                logger.debug(f"Scanning {total_shows} shows for user work")

                for index, show_dir in enumerate(show_dirs):
                    if self._should_stop:
                        break

                    # Emit progress
                    self.scan_progress.emit(index + 1, total_shows)

                    # Find shots in this show
                    show_shots = self._find_shots_in_show(show_dir)
                    shots.extend(show_shots)

                    logger.debug(
                        f"Found {len(show_shots)} user shots in {show_dir.name}"
                    )

        except Exception as e:
            logger.error(f"Error scanning for user shots: {e}")

        return shots

    def _find_shots_in_show(self, show_dir: Path) -> List[Shot]:
        """Find user shots within a specific show.

        Args:
            show_dir: Show directory to search.

        Returns:
            List of Shot objects with user work.
        """
        shots = []

        try:
            shots_dir = show_dir / "shots"
            if not shots_dir.exists():
                return shots

            # Look for user directories in shot paths

            for sequence_dir in shots_dir.iterdir():
                if self._should_stop:
                    break

                if not sequence_dir.is_dir():
                    continue

                for shot_dir in sequence_dir.iterdir():
                    if self._should_stop:
                        break

                    if not shot_dir.is_dir():
                        continue

                    # Check if user has work in this shot
                    user_dir = shot_dir / "user" / self._finder.username
                    if user_dir.exists():
                        shot = Shot(
                            show=show_dir.name,
                            sequence=sequence_dir.name,
                            shot=shot_dir.name,
                            workspace_path=str(shot_dir),
                        )
                        shots.append(shot)

                        # Emit individual shot found
                        shot_dict = {
                            "show": shot.show,
                            "sequence": shot.sequence,
                            "shot": shot.shot,
                            "workspace_path": shot.workspace_path,
                        }
                        self.shot_found.emit(shot_dict)

        except Exception as e:
            logger.error(f"Error scanning show {show_dir}: {e}")

        return shots

    def get_found_shots(self) -> List[Shot]:
        """Get the list of shots found so far.

        Returns:
            List of Shot objects found during scanning.
        """
        return self._found_shots.copy()
