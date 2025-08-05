"""QThread-based worker for background 3DE scene discovery."""

import logging
from typing import List, Optional, Set

from PySide6.QtCore import QThread, Signal

from shot_model import Shot
from threede_scene_finder import ThreeDESceneFinder
from threede_scene_model import ThreeDEScene
from utils import ValidationUtils

# Set up logger for this module
logger = logging.getLogger(__name__)


class ThreeDESceneWorker(QThread):
    """QThread worker for performing 3DE scene discovery in the background.

    This worker moves the expensive 3DE scene discovery operation to a separate
    thread to prevent UI blocking during show-wide searches that can scan
    hundreds of shots.
    """

    # Signals
    started = Signal()  # Emitted when discovery starts
    progress = Signal(int, int, str)  # Emitted with (current, total, description)
    finished = Signal(list)  # Emitted with list of ThreeDEScene objects
    error = Signal(str)  # Emitted when an error occurs

    def __init__(self, shots: List[Shot], excluded_users: Optional[Set[str]] = None):
        """Initialize the worker with shots to search.

        Args:
            shots: List of shots to use for determining shows to search
            excluded_users: Set of usernames to exclude from search
        """
        super().__init__()
        self.shots = shots
        self.excluded_users = excluded_users or ValidationUtils.get_excluded_users()
        self._should_stop = False

    def stop(self):
        """Request the worker to stop processing."""
        self._should_stop = True

    def run(self):
        """Main worker thread execution."""
        try:
            logger.info("Starting background 3DE scene discovery")
            self.started.emit()

            if not self.shots:
                logger.warning("No shots provided for 3DE scene discovery")
                self.finished.emit([])
                return

            # Check if we should stop before starting
            if self._should_stop:
                logger.info("3DE scene discovery cancelled before starting")
                self.finished.emit([])
                return

            # Extract unique shows from user's shots for progress tracking
            shows_to_search = set()
            for shot in self.shots:
                shows_to_search.add(shot.show)

            self.progress.emit(
                0, len(shows_to_search), f"Analyzing {len(shows_to_search)} shows"
            )
            logger.info(f"Will search shows: {shows_to_search}")

            # Perform the actual discovery using the existing finder
            scenes = self._discover_scenes_with_progress()

            if self._should_stop:
                logger.info("3DE scene discovery cancelled during processing")
                self.finished.emit([])
                return

            logger.info(
                f"Background 3DE scene discovery completed: {len(scenes)} scenes found"
            )
            self.finished.emit(scenes)

        except Exception as e:
            logger.error(f"Error in 3DE scene discovery worker: {e}")
            self.error.emit(str(e))

    def _discover_scenes_with_progress(self) -> List[ThreeDEScene]:
        """Perform scene discovery with progress updates.

        Returns:
            List of discovered ThreeDEScene objects
        """
        from pathlib import Path

        from config import Config

        all_scenes = []

        # Extract unique shows and show roots
        shows_to_search = set()
        show_roots = set()

        for shot in self.shots:
            shows_to_search.add(shot.show)
            # Extract show root from workspace path
            workspace_parts = Path(shot.workspace_path).parts
            if "shows" in workspace_parts:
                shows_idx = workspace_parts.index("shows")
                show_root = "/".join(workspace_parts[: shows_idx + 1])
                show_roots.add(show_root)

        if not show_roots:
            # Use configured show roots or fallback
            configured_roots = (
                Config.SHOW_ROOT_PATHS
                if hasattr(Config, "SHOW_ROOT_PATHS")
                else ["/shows"]
            )
            show_roots = set(configured_roots)

        total_shows = len(shows_to_search)
        current_show = 0

        # Process each show
        for show_root in show_roots:
            for show in shows_to_search:
                if self._should_stop:
                    break

                current_show += 1
                self.progress.emit(
                    current_show, total_shows, f"Discovering shots in {show}"
                )

                # Discover all shots in this show
                all_shots = ThreeDESceneFinder.discover_all_shots_in_show(
                    show_root, show
                )

                if not all_shots:
                    logger.warning(f"No shots discovered in {show}")
                    continue

                self.progress.emit(
                    current_show,
                    total_shows,
                    f"Searching {len(all_shots)} shots in {show}",
                )

                # Search each discovered shot with periodic progress updates
                shot_count = 0
                for workspace_path, show_name, sequence, shot in all_shots:
                    if self._should_stop:
                        break

                    shot_count += 1

                    # Update progress every 10 shots to avoid too many signals
                    if shot_count % 10 == 0:
                        self.progress.emit(
                            current_show,
                            total_shows,
                            f"Searching {show} ({shot_count}/{len(all_shots)} shots)",
                        )

                    scenes = ThreeDESceneFinder.find_scenes_for_shot(
                        workspace_path, show_name, sequence, shot, self.excluded_users
                    )
                    all_scenes.extend(scenes)

                if self._should_stop:
                    break

            if self._should_stop:
                break

        # Final progress update
        if not self._should_stop:
            self.progress.emit(
                total_shows,
                total_shows,
                f"Discovery complete: {len(all_scenes)} scenes found",
            )

        return all_scenes
