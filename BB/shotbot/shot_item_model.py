"""Qt Model/View implementation for shot data using QAbstractItemModel.

This module provides a proper Qt Model/View implementation that replaces
the current plain Python class approach, enabling efficient data handling,
virtualization, and proper update notifications.
"""

from __future__ import annotations

import logging
from concurrent.futures import Future
from enum import IntEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from typing_extensions import override

if TYPE_CHECKING:
    from cache.thumbnail_loader import ThumbnailCacheResult

from PySide6.QtCore import (
    Q_ARG,
    QAbstractListModel,
    QByteArray,
    QMetaObject,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QSize,
    Qt,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import QIcon, QImage, QPixmap

from cache.thumbnail_loader import ThumbnailCacheResult
from cache_manager import CacheManager
from config import Config
from shot_model import RefreshResult, Shot

logger = logging.getLogger(__name__)


class ShotRole(IntEnum):
    """Custom roles for shot data access."""

    # Standard roles
    DisplayRole = Qt.ItemDataRole.DisplayRole
    DecorationRole = Qt.ItemDataRole.DecorationRole
    ToolTipRole = Qt.ItemDataRole.ToolTipRole
    SizeHintRole = Qt.ItemDataRole.SizeHintRole

    # Custom roles starting from UserRole
    ShotObjectRole = Qt.ItemDataRole.UserRole + 1
    ShowRole = Qt.ItemDataRole.UserRole + 2
    SequenceRole = Qt.ItemDataRole.UserRole + 3
    ShotNameRole = Qt.ItemDataRole.UserRole + 4
    FullNameRole = Qt.ItemDataRole.UserRole + 5
    WorkspacePathRole = Qt.ItemDataRole.UserRole + 6
    ThumbnailPathRole = Qt.ItemDataRole.UserRole + 7
    ThumbnailPixmapRole = Qt.ItemDataRole.UserRole + 8
    LoadingStateRole = Qt.ItemDataRole.UserRole + 9
    IsSelectedRole = Qt.ItemDataRole.UserRole + 10


class ShotItemModel(QAbstractListModel):
    """Proper Qt Model implementation for shot data.

    This model provides:
    - Efficient data access through Qt's Model/View framework
    - Lazy loading of thumbnails
    - Proper change notifications
    - Memory-efficient virtualization
    - Batch updates support
    """

    # Signals
    shots_updated = Signal()
    thumbnail_loaded = Signal(int)  # row index
    selection_changed = Signal(QModelIndex)

    def __init__(
        self,
        cache_manager: CacheManager | None = None,
        parent: QObject | None = None,
    ):
        """Initialize the shot item model.

        Args:
            cache_manager: Optional cache manager for thumbnails
            parent: Optional parent QObject
        """
        super().__init__(parent)

        self._shots: list[Shot] = []
        self._cache_manager = cache_manager or CacheManager()
        # Use QImage for thread safety - QImage can be safely shared between threads
        # Convert to QPixmap only when needed in the main thread for display
        self._thumbnail_cache: dict[str, QImage] = {}
        self._loading_states: dict[str, str] = {}
        self._selected_index = QPersistentModelIndex()

        # Lazy loading timer for thumbnails
        self._thumbnail_timer = QTimer()
        self._thumbnail_timer.timeout.connect(self._load_visible_thumbnails)
        self._thumbnail_timer.setInterval(100)  # 100ms delay

        # Track visible range for lazy loading
        self._visible_start = 0
        self._visible_end = 0

        logger.info("ShotItemModel initialized with Model/View architecture")

    @override
    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        """Return number of shots in the model.

        Args:
            parent: Parent index (unused for list model)

        Returns:
            Number of shots
        """
        if parent.isValid():
            return 0  # List models don't have children
        return len(self._shots)

    @override
    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        """Get data for the given index and role.

        Args:
            index: Model index
            role: Data role

        Returns:
            Data for the role, or None if invalid
        """
        if not index.isValid() or not (0 <= index.row() < len(self._shots)):
            return None

        shot = self._shots[index.row()]

        # Handle standard roles
        if role == Qt.ItemDataRole.DisplayRole:
            return shot.full_name

        if role == Qt.ItemDataRole.ToolTipRole:
            return f"{shot.show} / {shot.sequence} / {shot.shot}\n{shot.workspace_path}"

        if role == Qt.ItemDataRole.SizeHintRole:
            # Return size hint for delegates
            return QSize(
                Config.DEFAULT_THUMBNAIL_SIZE,
                Config.DEFAULT_THUMBNAIL_SIZE + 40,
            )

        # Handle custom roles
        if role == ShotRole.ShotObjectRole:
            return shot

        if role == ShotRole.ShowRole:
            return shot.show

        if role == ShotRole.SequenceRole:
            return shot.sequence

        if role == ShotRole.ShotNameRole:
            return shot.shot

        if role == ShotRole.FullNameRole:
            return shot.full_name

        if role == ShotRole.WorkspacePathRole:
            return shot.workspace_path

        if role == ShotRole.ThumbnailPathRole:
            return str(shot.get_thumbnail_path()) if shot.get_thumbnail_path() else None

        if role == ShotRole.ThumbnailPixmapRole:
            # Return cached thumbnail if available
            return self._get_thumbnail_pixmap(shot)

        if role == ShotRole.LoadingStateRole:
            return self._loading_states.get(shot.full_name, "idle")

        if role == ShotRole.IsSelectedRole:
            return self._selected_index == QPersistentModelIndex(index)

        if role == Qt.ItemDataRole.DecorationRole:
            # Return thumbnail icon for decoration
            pixmap = self._get_thumbnail_pixmap(shot)
            return QIcon(pixmap) if pixmap else None

        return None

    @override
    def roleNames(self) -> dict[int, QByteArray]:
        """Get role names for QML compatibility.

        Returns:
            Dictionary mapping role IDs to role names
        """
        # Get base roles from parent class
        roles = super().roleNames()
        
        # Add custom roles with QByteArray
        roles.update(
            {
                ShotRole.ShotObjectRole: QByteArray(b"shotObject"),
                ShotRole.ShowRole: QByteArray(b"show"),
                ShotRole.SequenceRole: QByteArray(b"sequence"),
                ShotRole.ShotNameRole: QByteArray(b"shotName"),
                ShotRole.FullNameRole: QByteArray(b"fullName"),
                ShotRole.WorkspacePathRole: QByteArray(b"workspacePath"),
                ShotRole.ThumbnailPathRole: QByteArray(b"thumbnailPath"),
                ShotRole.ThumbnailPixmapRole: QByteArray(b"thumbnailPixmap"),
                ShotRole.LoadingStateRole: QByteArray(b"loadingState"),
                ShotRole.IsSelectedRole: QByteArray(b"isSelected"),
            },
        )
        return roles

    @override
    def flags(self, index: QModelIndex | QPersistentModelIndex) -> Qt.ItemFlag:
        """Get flags for the given index.

        Args:
            index: Model index

        Returns:
            Item flags
        """
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags

        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    @override
    def setData(
        self,
        index: QModelIndex | QPersistentModelIndex,
        value: Any,
        role: int = Qt.ItemDataRole.EditRole,
    ) -> bool:
        """Set data for the given index and role.

        Args:
            index: Model index
            value: New value
            role: Data role

        Returns:
            True if successful, False otherwise
        """
        if not index.isValid() or not (0 <= index.row() < len(self._shots)):
            return False

        shot = self._shots[index.row()]

        # Handle selection state
        if role == ShotRole.IsSelectedRole:
            if value:
                self._selected_index = QPersistentModelIndex(index)
                self.selection_changed.emit(index)
            else:
                self._selected_index = QPersistentModelIndex()

            # Emit dataChanged for selection update
            self.dataChanged.emit(index, index, [ShotRole.IsSelectedRole])
            return True

        # Handle loading state
        if role == ShotRole.LoadingStateRole:
            self._loading_states[shot.full_name] = value
            self.dataChanged.emit(index, index, [ShotRole.LoadingStateRole])
            return True

        return False

    @Slot(list)
    def set_shots(self, shots: list[Shot]) -> None:
        """Set the shot list with proper model reset.

        Args:
            shots: List of Shot objects
        """
        self.beginResetModel()

        self._shots = shots
        self._thumbnail_cache.clear()
        self._loading_states.clear()
        self._selected_index = QPersistentModelIndex()

        self.endResetModel()

        self.shots_updated.emit()
        logger.info(f"Model updated with {len(shots)} shots")

    @Slot(int, int)
    def set_visible_range(self, start: int, end: int) -> None:
        """Set the visible range for lazy loading.

        Args:
            start: Start index
            end: End index
        """
        self._visible_start = max(0, start)
        self._visible_end = min(len(self._shots), end)

        # Start thumbnail loading timer
        if not self._thumbnail_timer.isActive():
            self._thumbnail_timer.start()

    def _load_visible_thumbnails(self) -> None:
        """Load thumbnails for visible items only."""
        # Buffer zone for smoother scrolling
        buffer_size = 5
        start = max(0, self._visible_start - buffer_size)
        end = min(len(self._shots), self._visible_end + buffer_size)

        for row in range(start, end):
            shot = self._shots[row]

            # Skip if already loaded
            if shot.full_name in self._thumbnail_cache:
                continue

            # Skip if loading or previously failed
            state = self._loading_states.get(shot.full_name)
            if state in ("loading", "failed"):
                continue

            # Start loading
            self._load_thumbnail_async(row, shot)

        # Stop timer if no more loading needed
        all_loaded = all(
            self._shots[i].full_name in self._thumbnail_cache for i in range(start, end)
        )
        if all_loaded:
            self._thumbnail_timer.stop()

    def _load_thumbnail_async(self, row: int, shot: Shot) -> None:
        """Start async thumbnail loading for a shot.

        Args:
            row: Row index
            shot: Shot object
        """
        # Mark as loading
        self._loading_states[shot.full_name] = "loading"
        index = self.index(row, 0)
        self.dataChanged.emit(index, index, [ShotRole.LoadingStateRole])

        # Simulate async loading (in real implementation, use QRunnable)
        # For now, load synchronously but emit proper signals
        thumbnail_path = shot.get_thumbnail_path()
        if thumbnail_path and thumbnail_path.exists():
            # Use cache manager for proper thumbnail handling
            # It will automatically resize EXR files using PIL if needed
            if self._cache_manager:
                # First, cache the thumbnail (handles EXR with PIL resizing)
                cached_path = self._cache_manager.cache_thumbnail(
                    thumbnail_path,
                    shot.show,
                    shot.sequence,
                    shot.shot,
                    wait=False,  # Don't block UI - load asynchronously
                )

                # Handle both sync and async results
                if isinstance(cached_path, ThumbnailCacheResult):
                    # Async result - set up callback with immutable shot identifier
                    shot_full_name = shot.full_name  # Capture immutable identifier
                    # Type checker: cached_path is now narrowed to ThumbnailCacheResult
                    result: ThumbnailCacheResult = cached_path
                    result.future.add_done_callback(
                        lambda fut: self._on_thumbnail_cached_safe(fut, shot_full_name)
                    )
                elif isinstance(cached_path, Path) and cached_path.exists():
                    # Sync result - cached thumbnail was already available
                    self._load_cached_pixmap(cached_path, row, shot, index)
                else:
                    # Immediate failure
                    logger.warning(f"Failed to cache thumbnail from {thumbnail_path}")
                    self._loading_states[shot.full_name] = "failed"
                    self.dataChanged.emit(index, index, [ShotRole.LoadingStateRole])
            else:
                # Fallback without cache manager - only load lightweight formats
                suffix_lower = thumbnail_path.suffix.lower()
                if suffix_lower in Config.THUMBNAIL_EXTENSIONS:
                    # Use QImage for thread-safe loading instead of QPixmap
                    image = QImage(str(thumbnail_path))
                    if not image.isNull():
                        # Scale to thumbnail size using QImage (thread-safe)
                        scaled_image = image.scaled(
                            Config.DEFAULT_THUMBNAIL_SIZE,
                            Config.DEFAULT_THUMBNAIL_SIZE,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                        # Store QImage directly (thread-safe)
                        self._thumbnail_cache[shot.full_name] = scaled_image
                        self._loading_states[shot.full_name] = "loaded"

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
                        self.thumbnail_loaded.emit(row)
                    else:
                        self._loading_states[shot.full_name] = "failed"
                        self.dataChanged.emit(index, index, [ShotRole.LoadingStateRole])
                else:
                    logger.debug(
                        f"Cannot load {suffix_lower} file without cache manager: {thumbnail_path}"
                    )
                    self._loading_states[shot.full_name] = "failed"
                    self.dataChanged.emit(index, index, [ShotRole.LoadingStateRole])
        else:
            self._loading_states[shot.full_name] = "failed"
            self.dataChanged.emit(index, index, [ShotRole.LoadingStateRole])

    def _on_thumbnail_cached_safe(self, future: Future[Path | None], shot_full_name: str) -> None:
        """Handle thumbnail caching completion with race condition protection.
        
        This method is called from background threads and uses QMetaObject.invokeMethod
        to safely queue operations to the main thread with only immutable identifiers.
        """
        try:
            cached_path = future.result()
            if cached_path:
                # Only pass immutable identifiers to main thread - no race conditions
                QMetaObject.invokeMethod(
                    self, "_handle_thumbnail_success_atomically",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, shot_full_name),  # Immutable identifier
                    Q_ARG(str, str(cached_path))   # Convert Path to string for Qt
                )
            else:
                # Caching failed - pass only immutable identifier
                QMetaObject.invokeMethod(
                    self, "_handle_thumbnail_failure_atomically",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, shot_full_name)  # Immutable identifier only
                )
        except Exception as e:
            logger.error(f"Thumbnail caching failed for {shot_full_name}: {e}")
            # Handle failure atomically in main thread
            QMetaObject.invokeMethod(
                self, "_handle_thumbnail_failure_atomically",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(str, shot_full_name)  # Immutable identifier only
            )

    def _find_shot_by_full_name(self, full_name: str) -> tuple[Shot, int] | None:
        """Find a shot and its row index by full_name. Returns None if not found."""
        for row, shot in enumerate(self._shots):
            if shot.full_name == full_name:
                return shot, row
        return None


    @Slot(str, str)  # shot_full_name: str, cached_path: str
    def _handle_thumbnail_success_atomically(self, shot_full_name: str, cached_path: str) -> None:
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
            logger.debug(f"Shot {shot_full_name} no longer exists in model, ignoring success callback")
    
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
            shot, row = shot_data
            self._loading_states[shot.full_name] = "failed"
            index = self.index(row, 0)
            self.dataChanged.emit(index, index, [ShotRole.LoadingStateRole])
        else:
            logger.debug(f"Shot {shot_full_name} no longer exists in model, ignoring failure callback")

    @Slot(object, int, object)  # cached_path: object (Path), row: int, shot: object (Shot)
    def _load_cached_pixmap_safe(self, cached_path: object, row: int, shot: object) -> None:
        """Safely load cached pixmap on main thread."""
        # Assert types for runtime safety
        assert isinstance(cached_path, Path), f"Expected Path, got {type(cached_path)}"
        from shot_model import Shot
        assert isinstance(shot, Shot), f"Expected Shot, got {type(shot)}"
        index = self.index(row, 0)
        self._load_cached_pixmap(cached_path, row, shot, index)

    @Slot(int, object)
    def _on_thumbnail_cache_failed_safe(self, row: int, shot: Shot) -> None:
        """Handle thumbnail cache failure on main thread."""
        self._loading_states[shot.full_name] = "failed"
        index = self.index(row, 0)
        self.dataChanged.emit(index, index, [ShotRole.LoadingStateRole])

    def _load_cached_pixmap(self, cached_path: Path, row: int, shot: Shot, index: QModelIndex) -> None:
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
            self._thumbnail_cache[shot.full_name] = pixmap.toImage()
            self._loading_states[shot.full_name] = "loaded"
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
            self.thumbnail_loaded.emit(row)
        else:
            logger.warning(f"Failed to load cached thumbnail pixmap from {cached_path}")
            self._loading_states[shot.full_name] = "failed"
            self.dataChanged.emit(index, index, [ShotRole.LoadingStateRole])

    def _get_thumbnail_pixmap(self, shot: Shot) -> QPixmap | None:
        """Get cached thumbnail pixmap for a shot.

        Thread-safe: Converts QImage to QPixmap in main thread for display.

        Args:
            shot: Shot object

        Returns:
            QPixmap converted from cached QImage or None
        """
        qimage = self._thumbnail_cache.get(shot.full_name)
        if qimage:
            # Convert QImage to QPixmap in main thread
            return QPixmap.fromImage(qimage)
        return None

    def get_shot_at_index(self, index: QModelIndex) -> Shot | None:
        """Get shot object at the given index.

        Args:
            index: Model index

        Returns:
            Shot object or None if invalid
        """
        if index.isValid() and 0 <= index.row() < len(self._shots):
            return self._shots[index.row()]
        return None

    def refresh_shots(self, shots: list[Shot]) -> RefreshResult:
        """Refresh shots with intelligent updates.

        Args:
            shots: New list of shots

        Returns:
            RefreshResult indicating success and changes
        """
        # Compare with existing shots
        old_shot_names = {shot.full_name for shot in self._shots}
        new_shot_names = {shot.full_name for shot in shots}

        has_changes = old_shot_names != new_shot_names

        if has_changes:
            # Use beginInsertRows/beginRemoveRows for incremental updates
            # For simplicity, doing full reset here, but could be optimized
            self.set_shots(shots)

        return RefreshResult(success=True, has_changes=has_changes)

    def clear_thumbnail_cache(self) -> None:
        """Clear the thumbnail cache to free memory."""
        self._thumbnail_cache.clear()

        # Notify all items that thumbnails need reloading
        if self._shots:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self._shots) - 1, 0),
                [ShotRole.ThumbnailPixmapRole, Qt.ItemDataRole.DecorationRole],
            )
