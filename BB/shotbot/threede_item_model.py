"""Qt Model/View implementation for 3DE scene data using QAbstractItemModel.

This module provides a proper Qt Model/View implementation for 3DE scenes,
replacing the widget-based approach with efficient data handling, virtualization,
and proper update notifications.
"""

from __future__ import annotations

import logging
from enum import IntEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from typing_extensions import override

if TYPE_CHECKING:
    from cache.thumbnail_loader import ThumbnailCacheResult

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import QImage, QPixmap

from cache_manager import CacheManager
from config import Config
from threede_scene_model import ThreeDEScene

logger = logging.getLogger(__name__)


class ThreeDERole(IntEnum):
    """Custom roles for 3DE scene data access."""
    
    # Standard roles
    DisplayRole = Qt.ItemDataRole.DisplayRole
    DecorationRole = Qt.ItemDataRole.DecorationRole
    ToolTipRole = Qt.ItemDataRole.ToolTipRole
    SizeHintRole = Qt.ItemDataRole.SizeHintRole
    
    # Custom roles starting from UserRole
    SceneObjectRole = Qt.ItemDataRole.UserRole + 1
    ShowRole = Qt.ItemDataRole.UserRole + 2
    SequenceRole = Qt.ItemDataRole.UserRole + 3
    ShotRole = Qt.ItemDataRole.UserRole + 4
    UserRole = Qt.ItemDataRole.UserRole + 5
    ScenePathRole = Qt.ItemDataRole.UserRole + 6
    ThumbnailPathRole = Qt.ItemDataRole.UserRole + 7
    ThumbnailPixmapRole = Qt.ItemDataRole.UserRole + 8
    LoadingStateRole = Qt.ItemDataRole.UserRole + 9
    IsSelectedRole = Qt.ItemDataRole.UserRole + 10
    ModifiedTimeRole = Qt.ItemDataRole.UserRole + 11


class ThreeDEItemModel(QAbstractListModel):
    """Qt Model implementation for 3DE scene data.
    
    This model provides:
    - Efficient data access through Qt's Model/View framework
    - Lazy loading of thumbnails
    - Proper change notifications
    - Memory-efficient virtualization
    - Support for loading indicators
    """
    
    # Signals
    scenes_updated = Signal()
    thumbnail_loaded = Signal(int)  # row index
    selection_changed = Signal(QModelIndex)
    loading_started = Signal()
    loading_progress = Signal(int, int)  # current, total
    loading_finished = Signal()
    
    def __init__(
        self,
        cache_manager: CacheManager | None = None,
        parent: QObject | None = None,
    ):
        """Initialize the 3DE item model.
        
        Args:
            cache_manager: Optional cache manager for thumbnails
            parent: Optional parent QObject
        """
        super().__init__(parent)
        
        self._scenes: list[ThreeDEScene] = []
        self._cache_manager = cache_manager or CacheManager()
        # Use QImage for thread safety
        self._thumbnail_cache: dict[str, QImage] = {}
        self._loading_states: dict[str, str] = {}
        self._selected_index = QPersistentModelIndex()
        self._is_loading = False
        
        # Lazy loading timer for thumbnails
        self._thumbnail_timer = QTimer()
        self._thumbnail_timer.timeout.connect(self._load_visible_thumbnails)
        self._thumbnail_timer.setInterval(100)  # 100ms delay
        
        # Track visible range for lazy loading
        self._visible_start = 0
        self._visible_end = 0
        
        logger.info("ThreeDEItemModel initialized with Model/View architecture")
    
    @override
    def rowCount(
        self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()
    ) -> int:
        """Return number of 3DE scenes in the model.
        
        Args:
            parent: Parent index (unused for list model)
            
        Returns:
            Number of scenes
        """
        if parent.isValid():
            return 0  # List models don't have children
        return len(self._scenes)
    
    @override
    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        """Get data for the given index and role.
        
        Args:
            index: Model index
            role: Data role
            
        Returns:
            Data for the role, or None if invalid
        """
        if not index.isValid() or not (0 <= index.row() < len(self._scenes)):
            return None
        
        scene = self._scenes[index.row()]
        
        # Handle standard roles
        if role == Qt.ItemDataRole.DisplayRole:
            return scene.full_name
        elif role == Qt.ItemDataRole.ToolTipRole:
            tooltip = f"Scene: {scene.shot_name}\n"
            tooltip += f"User: {scene.user}\n"
            tooltip += f"Path: {scene.scene_path}"
            return tooltip
        
        # Handle custom roles
        elif role == ThreeDERole.SceneObjectRole:
            return scene
        elif role == ThreeDERole.ShowRole:
            return scene.show
        elif role == ThreeDERole.SequenceRole:
            return scene.sequence
        elif role == ThreeDERole.ShotRole:
            return scene.shot
        elif role == ThreeDERole.UserRole:
            return scene.user
        elif role == ThreeDERole.ScenePathRole:
            return scene.scene_path
        elif role == ThreeDERole.ThumbnailPathRole:
            thumb_path = scene.get_thumbnail_path()
            return str(thumb_path) if thumb_path else None
        elif role == ThreeDERole.ThumbnailPixmapRole:
            return self._get_thumbnail_pixmap(scene)
        elif role == ThreeDERole.LoadingStateRole:
            return self._loading_states.get(scene.shot_name, "idle")
        elif role == ThreeDERole.IsSelectedRole:
            return index == self._selected_index
        elif role == ThreeDERole.ModifiedTimeRole:
            return scene.modified_time
        
        return None
    
    def _get_thumbnail_pixmap(self, scene: ThreeDEScene) -> QPixmap | None:
        """Get thumbnail pixmap for a scene, loading if necessary.
        
        Args:
            scene: The 3DE scene
            
        Returns:
            QPixmap or None if not available
        """
        cache_key = scene.full_name
        
        # Check memory cache first
        if cache_key in self._thumbnail_cache:
            return QPixmap.fromImage(self._thumbnail_cache[cache_key])
        
        # Check if thumbnail exists
        thumb_path = scene.get_thumbnail_path()
        if thumb_path and thumb_path.exists():
            # Load thumbnail
            image = QImage(str(thumb_path))
            if not image.isNull():
                # Cache it
                self._thumbnail_cache[cache_key] = image
                return QPixmap.fromImage(image)
        
        # Return placeholder or None
        return None
    
    @Slot()
    def _load_visible_thumbnails(self):
        """Load thumbnails for visible scenes."""
        for row in range(self._visible_start, min(self._visible_end + 1, len(self._scenes))):
            scene = self._scenes[row]
            cache_key = scene.full_name
            
            # Skip if already cached
            if cache_key in self._thumbnail_cache:
                continue
            
            # Skip if already loading
            if self._loading_states.get(cache_key) == "loading":
                continue
            
            # Start loading
            self._loading_states[cache_key] = "loading"
            self._load_thumbnail_async(scene, row)
    
    def _load_thumbnail_async(self, scene: ThreeDEScene, row: int):
        """Start async thumbnail loading for a scene.
        
        Args:
            scene: The 3DE scene
            row: Row index for updates
        """
        thumb_path = scene.get_thumbnail_path()
        if not thumb_path:
            return
        
        # Use cache manager to load thumbnail
        from PySide6.QtCore import QMetaObject, Q_ARG
        
        def on_thumbnail_loaded(path: Path | None):
            """Handle loaded thumbnail."""
            if path and path.exists():
                image = QImage(str(path))
                if not image.isNull():
                    self._thumbnail_cache[scene.full_name] = image
                    self._loading_states[scene.full_name] = "loaded"
                    
                    # Update the specific row
                    index = self.index(row, 0)
                    self.dataChanged.emit(index, index, [ThreeDERole.ThumbnailPixmapRole])
                    self.thumbnail_loaded.emit(row)
        
        # Schedule loading in main thread
        QMetaObject.invokeMethod(
            self,
            "_do_load_thumbnail",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(object, scene),
            Q_ARG(object, on_thumbnail_loaded),
        )
    
    @Slot(object, object)
    def _do_load_thumbnail(self, scene: ThreeDEScene, callback):
        """Load thumbnail in main thread.
        
        Args:
            scene: The 3DE scene
            callback: Callback function for completion
        """
        thumb_path = scene.get_thumbnail_path()
        if thumb_path:
            callback(thumb_path)
    
    def set_visible_range(self, start: int, end: int):
        """Set the visible range for lazy loading.
        
        Args:
            start: First visible row
            end: Last visible row
        """
        self._visible_start = max(0, start)
        self._visible_end = min(end, len(self._scenes) - 1)
        
        # Trigger thumbnail loading for visible items
        if not self._thumbnail_timer.isActive():
            self._thumbnail_timer.start()
    
    def set_scenes(self, scenes: list[ThreeDEScene], reset: bool = True):
        """Set the scenes for the model.
        
        Args:
            scenes: List of 3DE scenes
            reset: Whether to reset the model
        """
        if reset:
            self.beginResetModel()
            self._scenes = scenes
            self._thumbnail_cache.clear()
            self._loading_states.clear()
            self._selected_index = QPersistentModelIndex()
            self.endResetModel()
            self.scenes_updated.emit()
        else:
            # Incremental update (more complex, for future optimization)
            self.beginResetModel()
            self._scenes = scenes
            self.endResetModel()
            self.scenes_updated.emit()
        
        logger.info(f"Set {len(scenes)} 3DE scenes in model")
    
    def get_scene(self, index: QModelIndex) -> ThreeDEScene | None:
        """Get scene at the given index.
        
        Args:
            index: Model index
            
        Returns:
            ThreeDEScene or None if invalid
        """
        if not index.isValid() or not (0 <= index.row() < len(self._scenes)):
            return None
        return self._scenes[index.row()]
    
    def set_selected(self, index: QModelIndex):
        """Set the selected scene.
        
        Args:
            index: Index to select
        """
        if self._selected_index != index:
            # Clear old selection
            if self._selected_index.isValid():
                old_index = QModelIndex(self._selected_index)
                self.dataChanged.emit(
                    old_index, old_index, [ThreeDERole.IsSelectedRole]
                )
            
            # Set new selection
            self._selected_index = QPersistentModelIndex(index)
            if index.isValid():
                self.dataChanged.emit(
                    index, index, [ThreeDERole.IsSelectedRole]
                )
            
            self.selection_changed.emit(index)
    
    def set_loading_state(self, loading: bool):
        """Set the loading state.
        
        Args:
            loading: Whether loading is in progress
        """
        self._is_loading = loading
        if loading:
            self.loading_started.emit()
        else:
            self.loading_finished.emit()
    
    def update_loading_progress(self, current: int, total: int):
        """Update loading progress.
        
        Args:
            current: Current item being loaded
            total: Total items to load
        """
        self.loading_progress.emit(current, total)
    
    @property
    def scenes(self) -> list[ThreeDEScene]:
        """Get the list of scenes."""
        return self._scenes
    
    @property
    def is_loading(self) -> bool:
        """Check if loading is in progress."""
        return self._is_loading