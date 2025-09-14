"""Qt Model/View item model for previous shots display.

This model provides a QAbstractListModel implementation for displaying
approved/completed shots in a view, enabling efficient virtualization
and lazy loading of thumbnails.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import (
    Q_ARG,
    QAbstractListModel,
    QMetaObject,
    QModelIndex,
    QMutex,
    QMutexLocker,
    QObject,
    QPersistentModelIndex,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtGui import QImage, QPixmap

from config import Config
from shot_item_model import ShotRole  # Reuse the same roles

if TYPE_CHECKING:
    from concurrent.futures import Future

    from cache_manager import CacheManager
    from previous_shots_model import PreviousShotsModel
    from shot_model import Shot

logger = logging.getLogger(__name__)


class PreviousShotsItemModel(QAbstractListModel):
    """Qt item model for previous/approved shots.

    This model wraps PreviousShotsModel and provides the Qt Model/View
    interface for efficient display in views. It handles:
    - Data provision for views
    - Thumbnail loading coordination
    - Selection state management
    """

    # Signals
    shots_updated = Signal()
    selection_changed = Signal(
        object
    )  # Shot | None - using object for Qt signal compatibility

    def __init__(
        self,
        previous_shots_model: PreviousShotsModel,
        cache_manager: CacheManager | None = None,
        parent: QObject | None = None,
    ) -> None:
        """Initialize the item model.

        Args:
            previous_shots_model: The underlying previous shots model
            cache_manager: Optional cache manager for thumbnails
            parent: Optional parent object
        """
        super().__init__(parent)

        self._model = previous_shots_model
        self._cache_manager = cache_manager
        self._shots: list[Shot] = []
        self._thumbnail_cache: dict[str, QPixmap | QImage | None] = {}
        self._cache_mutex = QMutex()  # Thread-safe cache access
        self._visible_start = 0
        self._visible_end = 0
        self._selected_shot: Shot | None = None

        # Connect to underlying model signals with QueuedConnection for thread safety
        self._model.shots_updated.connect(
            self._on_shots_updated, Qt.ConnectionType.QueuedConnection
        )

        # Initialize with current shots
        self._update_shots()

        logger.info(f"PreviousShotsItemModel initialized with {len(self._shots)} shots")

    @property
    def shots(self) -> list[Shot]:
        """Get the current list of shots.

        Returns:
            List of Shot objects
        """
        return self._shots

    def rowCount(
        self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()
    ) -> int:
        """Return the number of rows (shots) in the model.

        Args:
            parent: Parent index (unused in list model)

        Returns:
            Number of shots
        """
        if parent.isValid():
            return 0
        return len(self._shots)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        """Return data for the given index and role.

        Args:
            index: Model index
            role: Data role

        Returns:
            Requested data or None
        """
        if not index.isValid() or index.row() >= len(self._shots):
            return None

        shot = self._shots[index.row()]

        # Reuse ShotRole enum for consistency
        if role == Qt.ItemDataRole.DisplayRole:
            return shot.full_name
        elif role == ShotRole.FullNameRole:
            return shot.full_name
        elif role == ShotRole.ShowRole:
            return shot.show
        elif role == ShotRole.SequenceRole:
            return shot.sequence
        elif role == ShotRole.ShotNameRole:
            return shot.shot
        elif role == ShotRole.ShotObjectRole:
            return shot
        elif role == ShotRole.ThumbnailPathRole:
            return shot.get_thumbnail_path()
        elif role == ShotRole.ThumbnailPixmapRole:
            # Return cached pixmap if available (thread-safe)
            return self._get_thumbnail_pixmap(shot)
        elif role == ShotRole.LoadingStateRole:
            # Could track loading state per shot
            return "idle"
        elif role == ShotRole.IsSelectedRole:
            return shot == self._selected_shot

        return None

    def setData(
        self,
        index: QModelIndex | QPersistentModelIndex,
        value: Any,
        role: int = Qt.ItemDataRole.EditRole,
    ) -> bool:
        """Set data for the given index and role.

        Args:
            index: Model index
            value: Value to set
            role: Data role

        Returns:
            True if successful
        """
        if not index.isValid() or index.row() >= len(self._shots):
            return False

        if role == ShotRole.ThumbnailPixmapRole:
            # Cache thumbnail pixmap (thread-safe)
            shot = self._shots[index.row()]
            with QMutexLocker(self._cache_mutex):
                self._thumbnail_cache[shot.full_name] = value
            self.dataChanged.emit(index, index, [role])
            return True
        elif role == ShotRole.IsSelectedRole:
            # Update selection
            shot = self._shots[index.row()]
            if value:
                self._selected_shot = shot
                self.selection_changed.emit(shot)
            elif shot == self._selected_shot:
                self._selected_shot = None
                self.selection_changed.emit(None)
            self.dataChanged.emit(index, index, [role])
            return True

        return False

    def set_visible_range(self, start: int, end: int) -> None:
        """Set the visible range for lazy loading.

        Args:
            start: First visible row
            end: Last visible row (exclusive)
        """
        self._visible_start = max(0, start)
        self._visible_end = min(end, len(self._shots))

        # Trigger thumbnail loading for visible items
        if self._cache_manager:
            for i in range(self._visible_start, self._visible_end):
                if i < len(self._shots):
                    shot = self._shots[i]
                    # Check cache with thread safety
                    with QMutexLocker(self._cache_mutex):
                        has_thumbnail = shot.full_name in self._thumbnail_cache
                    if not has_thumbnail:
                        # Request thumbnail loading
                        self._load_thumbnail(shot, i)

    def _load_thumbnail(self, shot: Shot, row: int) -> None:
        """Load thumbnail for a shot asynchronously.

        Args:
            shot: Shot object
            row: Row index
        """
        thumbnail_path = shot.get_thumbnail_path()
        if not thumbnail_path:
            return

        if not self._cache_manager:
            return

        # Mark as loading
        index = self.index(row, 0)
        self.dataChanged.emit(index, index, [ShotRole.LoadingStateRole])

        # Import here to avoid circular dependency
        from cache.thumbnail_loader import ThumbnailCacheResult

        # Use cache manager to cache the thumbnail
        cached_result = self._cache_manager.cache_thumbnail(
            thumbnail_path,
            shot.show,
            shot.sequence,
            shot.shot,
            wait=False,  # Don't block UI - load asynchronously
        )

        # Handle both sync and async results
        if isinstance(cached_result, ThumbnailCacheResult):
            # Async result - set up callback with immutable shot identifier
            shot_full_name = shot.full_name  # Capture immutable identifier
            cached_result.future.add_done_callback(
                lambda fut: self._on_thumbnail_cached_safe(fut, shot_full_name)
            )
        elif isinstance(cached_result, Path) and cached_result.exists():
            # Sync result - cached thumbnail was already available
            self._load_cached_pixmap(cached_result, row, shot, index)
        else:
            # Immediate failure
            logger.warning(f"Failed to cache thumbnail for {shot.full_name}")
            self.dataChanged.emit(index, index, [ShotRole.LoadingStateRole])

    @Slot()
    def _on_shots_updated(self) -> None:
        """Handle shots update from underlying model."""
        self._update_shots()

    def _update_shots(self) -> None:
        """Update the shot list from the underlying model."""
        self.beginResetModel()

        # Get shots from PreviousShotsModel
        self._shots = self._model.get_shots()

        # Clear thumbnail cache for removed shots (thread-safe)
        current_names = {shot.full_name for shot in self._shots}
        with QMutexLocker(self._cache_mutex):
            self._thumbnail_cache = {
                name: pixmap
                for name, pixmap in self._thumbnail_cache.items()
                if name in current_names
            }

        # Clear selection if shot was removed
        if self._selected_shot and self._selected_shot not in self._shots:
            self._selected_shot = None
            self.selection_changed.emit(None)

        self.endResetModel()
        self.shots_updated.emit()

        logger.debug(f"Updated model with {len(self._shots)} previous shots")

    def get_selected_shot(self) -> Shot | None:
        """Get the currently selected shot.

        Returns:
            Selected shot or None
        """
        return self._selected_shot

    def clear_selection(self) -> None:
        """Clear the current selection."""
        if self._selected_shot:
            # Find and update the index
            for i, shot in enumerate(self._shots):
                if shot == self._selected_shot:
                    index = self.index(i, 0)
                    self.setData(index, False, ShotRole.IsSelectedRole)
                    break

    def refresh(self) -> None:
        """Trigger a refresh of the underlying model."""
        self._model.refresh_shots()

    def get_underlying_model(self) -> PreviousShotsModel:
        """Get the underlying PreviousShotsModel.

        Returns:
            The underlying previous shots model
        """
        return self._model

    def _on_thumbnail_cached_safe(
        self, future: Future[Path | None], shot_full_name: str
    ) -> None:
        """Handle thumbnail caching completion with race condition protection.

        This method is called from background threads and uses QMetaObject.invokeMethod
        to safely queue operations to the main thread with only immutable identifiers.
        """
        try:
            cached_path = future.result()
            if cached_path:
                # Only pass immutable identifiers to main thread - no race conditions
                QMetaObject.invokeMethod(
                    self,
                    "_handle_thumbnail_success_atomically",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, shot_full_name),  # Immutable identifier
                    Q_ARG(str, str(cached_path)),  # Convert Path to string for Qt
                )
            else:
                # Caching failed - pass only immutable identifier
                QMetaObject.invokeMethod(
                    self,
                    "_handle_thumbnail_failure_atomically",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, shot_full_name),  # Immutable identifier only
                )
        except Exception as e:
            logger.error(f"Thumbnail caching failed for {shot_full_name}: {e}")
            # Handle failure atomically in main thread
            QMetaObject.invokeMethod(
                self,
                "_handle_thumbnail_failure_atomically",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(str, shot_full_name),  # Immutable identifier only
            )

    def _find_shot_by_full_name(self, full_name: str) -> tuple[Shot, int] | None:
        """Find a shot and its row index by full_name.

        Returns None if not found.
        """
        for row, shot in enumerate(self._shots):
            if shot.full_name == full_name:
                return shot, row
        return None

    @Slot(str, str)  # shot_full_name: str, cached_path: str
    def _handle_thumbnail_success_atomically(
        self, shot_full_name: str, cached_path: str
    ) -> None:
        """Atomically handle thumbnail success in main thread - prevents race conditions.

        This method does validation and processing atomically in the main thread,
        preventing race conditions where shot data could become stale between
        validation and processing.

        Args:
            shot_full_name: Immutable identifier for the shot
            cached_path: Path to the cached thumbnail (passed as string for Qt compatibility)
        """
        # Convert string back to Path for internal use
        cached_path_obj = Path(cached_path)

        # Validation and processing happen atomically in main thread
        shot_data = self._find_shot_by_full_name(shot_full_name)
        if shot_data is not None:
            shot, row = shot_data
            index = self.index(row, 0)
            self._load_cached_pixmap(cached_path_obj, row, shot, index)
        else:
            logger.debug(
                f"Shot {shot_full_name} no longer exists in model, ignoring success callback"
            )

    @Slot(str)  # shot_full_name: str
    def _handle_thumbnail_failure_atomically(self, shot_full_name: str) -> None:
        """Atomically handle thumbnail failure in main thread - prevents race conditions.

        This method does validation and processing atomically in the main thread,
        preventing race conditions where shot data could become stale.

        Args:
            shot_full_name: Immutable identifier for the shot
        """
        # Validation and processing happen atomically in main thread
        shot_data = self._find_shot_by_full_name(shot_full_name)
        if shot_data is not None:
            _, row = shot_data
            index = self.index(row, 0)
            self.dataChanged.emit(index, index, [ShotRole.LoadingStateRole])
        else:
            logger.debug(
                f"Shot {shot_full_name} no longer exists in model, ignoring failure callback"
            )

    def _load_cached_pixmap(
        self, cached_path: Path, row: int, shot: Shot, index: QModelIndex
    ) -> None:
        """Load pixmap from cached path (main thread only)."""
        # Load the cached JPEG as QPixmap
        pixmap = QPixmap(str(cached_path))
        if not pixmap.isNull():
            # Scale to display size if needed
            pixmap = pixmap.scaled(
                Config.DEFAULT_THUMBNAIL_SIZE,
                Config.DEFAULT_THUMBNAIL_SIZE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            # Convert to QImage for thread-safe storage
            qimage = pixmap.toImage()
            with QMutexLocker(self._cache_mutex):
                self._thumbnail_cache[shot.full_name] = qimage
            logger.debug(f"Loaded thumbnail for {shot.full_name} from cache")

            # Notify view of update
            self.dataChanged.emit(
                index,
                index,
                [
                    ShotRole.ThumbnailPixmapRole,
                    ShotRole.LoadingStateRole,
                    Qt.ItemDataRole.DecorationRole,
                ],
            )
        else:
            logger.warning(f"Failed to load cached thumbnail pixmap from {cached_path}")
            self.dataChanged.emit(index, index, [ShotRole.LoadingStateRole])

    def _get_thumbnail_pixmap(self, shot: Shot) -> QPixmap | None:
        """Get cached thumbnail pixmap for a shot.

        Thread-safe: Converts QImage to QPixmap in main thread for display.

        Args:
            shot: Shot object

        Returns:
            QPixmap converted from cached QImage or None
        """
        with QMutexLocker(self._cache_mutex):
            qimage = self._thumbnail_cache.get(shot.full_name)
        if qimage:
            # Convert QImage to QPixmap in main thread
            if isinstance(qimage, QImage):
                return QPixmap.fromImage(qimage)
            elif isinstance(qimage, QPixmap):
                return qimage
            # Handle None case implicitly
        return None
