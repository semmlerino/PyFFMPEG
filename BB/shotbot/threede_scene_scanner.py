"""Background scanner for 3DE scenes with progress reporting."""

from typing import Optional, Set

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from shot_model import Shot
from threede_scene_finder import ThreeDESceneFinder
from threede_scene_model import ThreeDEScene


class ThreeDESceneScanner(QRunnable):
    """Background scanner for discovering 3DE scenes with progress."""

    class Signals(QObject):
        """Signals for the scanner."""

        progress = Signal(int, int)  # current, total
        scene_found = Signal(object)  # ThreeDEScene
        finished = Signal(list)  # List[ThreeDEScene]
        error = Signal(str)

    def __init__(self, shots: list[Shot], excluded_users: Set[str]):
        """Initialize scanner.

        Args:
            shots: List of shots to scan
            excluded_users: Set of usernames to exclude
        """
        super().__init__()
        self.shots = shots
        self.excluded_users = excluded_users
        self.signals = self.Signals()
        self._is_cancelled = False

    def run(self):
        """Run the scan in background."""
        all_scenes: list[ThreeDEScene] = []

        try:
            total_shots = len(self.shots)

            for i, shot in enumerate(self.shots):
                # Check if cancelled
                if self._is_cancelled:
                    break

                # Emit progress
                self.signals.progress.emit(i, total_shots)

                # Find scenes for this shot
                scenes = ThreeDESceneFinder.find_scenes_for_shot(
                    shot.workspace_path,
                    shot.show,
                    shot.sequence,
                    shot.shot,
                    self.excluded_users,
                )

                # Emit each found scene
                for scene in scenes:
                    if not self._is_cancelled:
                        self.signals.scene_found.emit(scene)
                        all_scenes.append(scene)

            # Final progress update
            self.signals.progress.emit(total_shots, total_shots)

            # Sort scenes
            all_scenes.sort(key=lambda s: (s.full_name, s.user, s.plate))

            # Emit finished signal
            self.signals.finished.emit(all_scenes)

        except Exception as e:
            self.signals.error.emit(str(e))

    def cancel(self):
        """Cancel the scan."""
        self._is_cancelled = True


class ThreeDEScannerManager(QObject):
    """Manager for 3DE scene scanning operations."""

    # Signals
    scan_started = Signal()
    scan_progress = Signal(int, int)  # current, total
    scan_finished = Signal(list)  # List[ThreeDEScene]
    scan_error = Signal(str)

    def __init__(self):
        super().__init__()
        self._current_scanner: Optional[ThreeDESceneScanner] = None

    def start_scan(self, shots: list[Shot], excluded_users: Set[str]):
        """Start a background scan for 3DE scenes.

        Args:
            shots: List of shots to scan
            excluded_users: Set of usernames to exclude
        """
        # Cancel any existing scan
        if self._current_scanner:
            self._current_scanner.cancel()

        # Create new scanner
        self._current_scanner = ThreeDESceneScanner(shots, excluded_users)

        # Connect signals
        self._current_scanner.signals.progress.connect(self.scan_progress.emit)
        self._current_scanner.signals.finished.connect(self._on_scan_finished)
        self._current_scanner.signals.error.connect(self.scan_error.emit)

        # Emit started signal
        self.scan_started.emit()

        # Start in thread pool
        QThreadPool.globalInstance().start(self._current_scanner)

    def _on_scan_finished(self, scenes: list[ThreeDEScene]):
        """Handle scan completion."""
        self._current_scanner = None
        self.scan_finished.emit(scenes)

    def cancel_scan(self):
        """Cancel the current scan if any."""
        if self._current_scanner:
            self._current_scanner.cancel()
            self._current_scanner = None
