"""Base Qt Model implementation for item data using QAbstractListModel.

This module provides a base implementation that extracts common functionality
from ShotItemModel, ThreeDEItemModel, and PreviousShotsItemModel, reducing
code duplication by ~70-80%.
"""

from __future__ import annotations

# Standard library imports
from abc import abstractmethod
from enum import IntEnum
from pathlib import Path
from typing import Generic, TypeVar

# Third-party imports
from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QMutex,
    QMutexLocker,
    QObject,
    QPersistentModelIndex,
    QSize,
    Qt,
    QTimer,
    Signal,
    Slot,  # type: ignore[attr-defined]
)
from PySide6.QtGui import QImage, QPixmap
from typing_extensions import override

# Local application imports
from cache_manager import CacheManager
from config import Config
from logging_mixin import LoggingMixin
from protocols import SceneDataProtocol

# Type variable for the data items (Shot or ThreeDEScene)
T = TypeVar("T", bound=SceneDataProtocol)


class BaseItemRole(IntEnum):
    """Common roles shared across all item models."""

    # Standard Qt roles
    DisplayRole = Qt.ItemDataRole.DisplayRole
    DecorationRole = Qt.ItemDataRole.DecorationRole
    ToolTipRole = Qt.ItemDataRole.ToolTipRole
    SizeHintRole = Qt.ItemDataRole.SizeHintRole

    # Common custom roles
    ObjectRole = Qt.ItemDataRole.UserRole + 1
    ShowRole = Qt.ItemDataRole.UserRole + 2
    SequenceRole = Qt.ItemDataRole.UserRole + 3
    FullNameRole = Qt.ItemDataRole.UserRole + 5
    WorkspacePathRole = Qt.ItemDataRole.UserRole + 6
    ThumbnailPathRole = Qt.ItemDataRole.UserRole + 7
    ThumbnailPixmapRole = Qt.ItemDataRole.UserRole + 8
    LoadingStateRole = Qt.ItemDataRole.UserRole + 9
    IsSelectedRole = Qt.ItemDataRole.UserRole + 10

    # Item-specific roles (for backward compatibility with old tests)
    ItemSpecificRole1 = Qt.ItemDataRole.UserRole + 20  # shot.shot for Shot items, scene.shot for ThreeDEScene
    ItemSpecificRole2 = Qt.ItemDataRole.UserRole + 21  # scene.user for ThreeDEScene
    ItemSpecificRole3 = Qt.ItemDataRole.UserRole + 22  # scene.scene_path for ThreeDEScene


class BaseItemModel(LoggingMixin, QAbstractListModel, Generic[T]):
    """Base Qt Model implementation for item data.

    This base class provides:
    - Efficient data access through Qt's Model/View framework
    - Lazy loading of thumbnails
    - Proper change notifications
    - Memory-efficient virtualization
    - Thread-safe thumbnail caching
    - Common selection management
    - Show filtering support

    Subclasses must implement abstract methods to provide
    specific behavior for their data types.
    """

    # Common signals
    items_updated = Signal()  # Emitted when items list changes
    thumbnail_loaded = Signal(int)  # row index
    selection_changed = Signal(QModelIndex)
    show_filter_changed = Signal(str)  # show name or "All Shows"

    def __init__(
        self,
        cache_manager: CacheManager | None = None,
        parent: QObject | None = None,
    ) -> None:
        """Initialize the base item model.

        Args:
            cache_manager: Optional cache manager for thumbnails
            parent: Optional parent QObject
        """
        # Ensure we're in the main thread for Qt model creation
        # Third-party imports
        from PySide6.QtCore import QCoreApplication, QThread

        app = QCoreApplication.instance()
        if app and not QThread.currentThread() == app.thread():
            raise RuntimeError(
                f"{self.__class__.__name__} must be created in the main thread. "
                f"Current thread: {QThread.currentThread()}, "
                f"Main thread: {app.thread()}"
            )
        super().__init__(parent)

        # Core data storage
        self._items: list[T] = []
        self._cache_manager = cache_manager or CacheManager()

        # Thumbnail cache - use QImage for thread safety
        # QImage can be safely shared between threads
        self._thumbnail_cache: dict[str, QImage] = {}
        self._loading_states: dict[str, str] = {}
        self._cache_mutex = QMutex()  # Thread-safe cache access

        # Selection tracking
        self._selected_index = QPersistentModelIndex()
        self._selected_item: T | None = None

        # Lazy loading timer for thumbnails
        self._thumbnail_timer = QTimer()
        self._thumbnail_timer.timeout.connect(self._load_visible_thumbnails)
        self._thumbnail_timer.setInterval(100)  # 100ms delay

        # Track visible range for lazy loading
        self._visible_start = 0
        self._visible_end = 0

        self.logger.info(
            f"{self.__class__.__name__} initialized with Model/View architecture"
        )

    @override
    def rowCount(
        self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()
    ) -> int:
        """Return number of items in the model.

        Args:
            parent: Parent index (unused for list model)

        Returns:
            Number of items
        """
        if parent.isValid():
            return 0  # List models don't have children
        return len(self._items)

    @override
    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        """Get data for the given index and role.

        Args:
            index: Model index
            role: Data role

        Returns:
            Data for the role, or None if invalid
        """
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return None

        item = self._items[index.row()]

        # Handle standard roles
        if role == Qt.ItemDataRole.DisplayRole:
            return self.get_display_role_data(item)

        if role == Qt.ItemDataRole.ToolTipRole:
            return self.get_tooltip_data(item)

        if role == Qt.ItemDataRole.SizeHintRole:
            return self.get_size_hint()

        # Handle common custom roles
        if role == BaseItemRole.ObjectRole:
            return item

        if role == BaseItemRole.ShowRole:
            return item.show

        if role == BaseItemRole.SequenceRole:
            return item.sequence

        if role == BaseItemRole.FullNameRole:
            return item.full_name

        if role == BaseItemRole.WorkspacePathRole:
            return item.workspace_path

        if role == BaseItemRole.ThumbnailPathRole:
            thumb_path = item.get_thumbnail_path()
            return str(thumb_path) if thumb_path else None

        if role == BaseItemRole.ThumbnailPixmapRole:
            return self._get_thumbnail_pixmap(item)

        if role == BaseItemRole.LoadingStateRole:
            with QMutexLocker(self._cache_mutex):
                return self._loading_states.get(item.full_name, "idle")

        if role == BaseItemRole.IsSelectedRole:
            return self._selected_index == QPersistentModelIndex(index)

        if role == Qt.ItemDataRole.DecorationRole:
            # Return thumbnail icon for decoration
            pixmap = self._get_thumbnail_pixmap(item)
            # Third-party imports
            from PySide6.QtGui import QIcon

            return QIcon(pixmap) if pixmap else None

        # Let subclass handle model-specific roles
        return self.get_custom_role_data(item, role)

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
        value: object,
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
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return False

        item = self._items[index.row()]

        # Handle selection state
        if role == BaseItemRole.IsSelectedRole:
            if value:
                self._selected_index = QPersistentModelIndex(index)
                self._selected_item = item
                self.selection_changed.emit(index)
            else:
                self._selected_index = QPersistentModelIndex()
                self._selected_item = None

            # Emit dataChanged for selection update
            self.dataChanged.emit(index, index, [BaseItemRole.IsSelectedRole])
            return True

        # Handle loading state
        if role == BaseItemRole.LoadingStateRole:
            with QMutexLocker(self._cache_mutex):
                self._loading_states[item.full_name] = (
                    str(value) if value is not None else ""
                )
            self.dataChanged.emit(index, index, [BaseItemRole.LoadingStateRole])
            return True

        # Let subclass handle model-specific data setting
        return self.set_custom_data(item, value, role)

    @Slot(int, int)
    def set_visible_range(self, start: int, end: int) -> None:
        """Set the visible range for lazy loading.

        Args:
            start: Start index
            end: End index
        """
        self._visible_start = max(0, start)
        self._visible_end = min(len(self._items) - 1, end) if self._items else 0

        # Start thumbnail loading timer
        if not self._thumbnail_timer.isActive():
            self._thumbnail_timer.start()

    def _load_visible_thumbnails(self) -> None:
        """Load thumbnails for visible items only."""
        # Buffer zone for smoother scrolling
        buffer_size = 5
        start = max(0, self._visible_start - buffer_size)
        end = min(len(self._items), self._visible_end + buffer_size)

        # DEBUG: Log how many items we're checking
        if self._items:
            self.logger.debug(
                f"_load_visible_thumbnails: checking {end - start} items "
                f"(range {start}-{end}, total items: {len(self._items)})"
            )

        for row in range(start, end):
            item = self._items[row]

            # Skip if already loaded
            with QMutexLocker(self._cache_mutex):
                if item.full_name in self._thumbnail_cache:
                    continue

                # Skip if loading or previously failed
                state = self._loading_states.get(item.full_name)
                if state in ("loading", "failed"):
                    continue

            # Start loading
            self.logger.debug(f"Starting thumbnail load for item {row}: {item.full_name}")
            self._load_thumbnail_async(row, item)

        # Stop timer if no more loading needed
        all_loaded = all(
            self._items[i].full_name in self._thumbnail_cache for i in range(start, end)
        )
        if all_loaded:
            self._thumbnail_timer.stop()

    def _load_thumbnail_async(self, row: int, item: T) -> None:
        """Start async thumbnail loading for an item.

        Args:
            row: Row index
            item: Item object
        """
        # Mark as loading
        with QMutexLocker(self._cache_mutex):
            self._loading_states[item.full_name] = "loading"
        index = self.index(row, 0)
        self.dataChanged.emit(index, index, [BaseItemRole.LoadingStateRole])

        thumbnail_path = item.get_thumbnail_path()
        if thumbnail_path and thumbnail_path.exists():
            # Use cache manager for proper thumbnail handling
            if self._cache_manager:
                # Cache the thumbnail (synchronous in simplified implementation)
                cached_result = self._cache_manager.cache_thumbnail(
                    thumbnail_path,
                    item.show,
                    item.sequence,
                    item.shot,
                    wait=False,  # Ignored in simplified implementation
                    timeout=30.0,  # Ignored in simplified implementation
                )

                # Handle result (always synchronous Path | None)
                if isinstance(cached_result, Path) and cached_result.exists():
                    # Cached thumbnail available
                    self._load_cached_pixmap(cached_result, row, item, index)
                else:
                    # Immediate failure
                    self.logger.warning(
                        f"Failed to cache thumbnail from {thumbnail_path}"
                    )
                    with QMutexLocker(self._cache_mutex):
                        self._loading_states[item.full_name] = "failed"
                    self.dataChanged.emit(index, index, [BaseItemRole.LoadingStateRole])
            else:
                # Fallback without cache manager - only load lightweight formats
                suffix_lower = thumbnail_path.suffix.lower()
                if suffix_lower in Config.THUMBNAIL_EXTENSIONS:
                    # Use QImage for thread-safe loading
                    image = QImage(str(thumbnail_path))
                    if not image.isNull():
                        # Scale to thumbnail size
                        scaled_image = image.scaled(
                            Config.DEFAULT_THUMBNAIL_SIZE,
                            Config.DEFAULT_THUMBNAIL_SIZE,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                        # Store QImage directly (thread-safe)
                        with QMutexLocker(self._cache_mutex):
                            self._thumbnail_cache[item.full_name] = scaled_image
                            self._loading_states[item.full_name] = "loaded"

                        # Notify view of update
                        self.dataChanged.emit(
                            index,
                            index,
                            [
                                BaseItemRole.ThumbnailPixmapRole,
                                BaseItemRole.LoadingStateRole,
                                Qt.ItemDataRole.DecorationRole,
                            ],
                        )
                        self.thumbnail_loaded.emit(row)
                    else:
                        with QMutexLocker(self._cache_mutex):
                            self._loading_states[item.full_name] = "failed"
                        self.dataChanged.emit(
                            index, index, [BaseItemRole.LoadingStateRole]
                        )
                else:
                    self.logger.debug(
                        f"Cannot load {suffix_lower} file without cache manager: {thumbnail_path}"
                    )
                    with QMutexLocker(self._cache_mutex):
                        self._loading_states[item.full_name] = "failed"
                    self.dataChanged.emit(index, index, [BaseItemRole.LoadingStateRole])
        else:
            with QMutexLocker(self._cache_mutex):
                self._loading_states[item.full_name] = "failed"
            self.dataChanged.emit(index, index, [BaseItemRole.LoadingStateRole])


    def _load_cached_pixmap(
        self, cached_path: Path, row: int, item: T, index: QModelIndex
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
            with QMutexLocker(self._cache_mutex):
                self._thumbnail_cache[item.full_name] = pixmap.toImage()
                self._loading_states[item.full_name] = "loaded"
            self.logger.debug(f"Loaded thumbnail for {item.full_name} from cache")

            # Notify view of update
            self.dataChanged.emit(
                index,
                index,
                [
                    BaseItemRole.ThumbnailPixmapRole,
                    BaseItemRole.LoadingStateRole,
                    Qt.ItemDataRole.DecorationRole,
                ],
            )
            self.thumbnail_loaded.emit(row)
        else:
            self.logger.warning(
                f"Failed to load cached thumbnail pixmap from {cached_path}"
            )
            with QMutexLocker(self._cache_mutex):
                self._loading_states[item.full_name] = "failed"
            self.dataChanged.emit(index, index, [BaseItemRole.LoadingStateRole])

    def _get_thumbnail_pixmap(self, item: T) -> QPixmap | None:
        """Get cached thumbnail pixmap for an item.

        Thread-safe: Converts QImage to QPixmap in main thread for display.

        Args:
            item: Item object

        Returns:
            QPixmap converted from cached QImage or None
        """
        with QMutexLocker(self._cache_mutex):
            qimage = self._thumbnail_cache.get(item.full_name)
        if qimage:
            # Convert QImage to QPixmap in main thread
            return QPixmap.fromImage(qimage)
        return None

    def get_item_at_index(self, index: QModelIndex) -> T | None:
        """Get item object at the given index.

        Args:
            index: Model index

        Returns:
            Item object or None if invalid
        """
        if index.isValid() and 0 <= index.row() < len(self._items):
            return self._items[index.row()]
        return None

    def get_selected_item(self) -> T | None:
        """Get currently selected item.

        Returns:
            Selected item or None
        """
        return self._selected_item

    def clear_selection(self) -> None:
        """Clear the current selection."""
        if self._selected_item:
            # Find and update the index
            for i, item in enumerate(self._items):
                if item == self._selected_item:
                    index = self.index(i, 0)
                    self.setData(index, False, BaseItemRole.IsSelectedRole)
                    break

    def clear_thumbnail_cache(self) -> None:
        """Clear the thumbnail cache to free memory."""
        # Stop thumbnail loading timer to prevent reloading
        if self._thumbnail_timer.isActive():
            self._thumbnail_timer.stop()

        with QMutexLocker(self._cache_mutex):
            self._thumbnail_cache.clear()
            self._loading_states.clear()

        # Notify all items that thumbnails need reloading
        if self._items:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self._items) - 1, 0),
                [BaseItemRole.ThumbnailPixmapRole, Qt.ItemDataRole.DecorationRole],
            )

    def set_items(self, items: list[T]) -> None:
        """Set the item list with proper model reset.

        Args:
            items: List of item objects
        """
        self.beginResetModel()

        # Stop any active thumbnail loading
        if self._thumbnail_timer.isActive():
            self._thumbnail_timer.stop()

        self._items = items
        with QMutexLocker(self._cache_mutex):
            self._thumbnail_cache.clear()
            self._loading_states.clear()
        self._selected_index = QPersistentModelIndex()
        self._selected_item = None

        self.endResetModel()

        self.items_updated.emit()
        self.logger.info(f"Model updated with {len(items)} items")

    # ============= Abstract methods for subclasses =============

    @abstractmethod
    def get_display_role_data(self, item: T) -> str:
        """Get display text for an item.

        Args:
            item: The item to get display text for

        Returns:
            Display text string
        """
        pass

    @abstractmethod
    def get_tooltip_data(self, item: T) -> str:
        """Get tooltip text for an item.

        Args:
            item: The item to get tooltip for

        Returns:
            Tooltip text string
        """
        pass

    def get_size_hint(self) -> QSize:
        """Get size hint for items.

        Returns:
            QSize object or None

        Can be overridden by subclasses for custom sizing.
        """
        return QSize(
            Config.DEFAULT_THUMBNAIL_SIZE,
            Config.DEFAULT_THUMBNAIL_SIZE + 40,
        )

    def get_custom_role_data(self, item: T, role: int) -> object | None:
        """Handle model-specific custom roles.

        Args:
            item: The item
            role: The data role

        Returns:
            Data for the role or None

        Override in subclasses to handle model-specific roles.
        """
        return None

    def set_custom_data(self, item: T, value: object | None, role: int) -> bool:
        """Handle model-specific data setting.

        Args:
            item: The item
            value: Value to set
            role: The data role

        Returns:
            True if handled, False otherwise

        Override in subclasses to handle model-specific data setting.
        """
        return False
