"""Qt Model/View implementation for 3DE scene data using BaseItemModel.

This module provides a 3DE-specific Qt Model/View implementation that
inherits common functionality from BaseItemModel, reducing code duplication.
"""

from __future__ import annotations

from enum import IntEnum
from typing import TYPE_CHECKING

from PySide6.QtCore import (
    QModelIndex,
    QObject,
    Qt,
    Signal,
)
from typing_extensions import override

from base_item_model import BaseItemModel, BaseItemRole

if TYPE_CHECKING:
    from threede_scene_model import ThreeDEScene, ThreeDESceneModel


class ThreeDERole(IntEnum):
    """Custom roles for 3DE scene data access - extends BaseItemRole."""

    # Inherit all base roles
    DisplayRole = BaseItemRole.DisplayRole
    DecorationRole = BaseItemRole.DecorationRole
    ToolTipRole = BaseItemRole.ToolTipRole
    SizeHintRole = BaseItemRole.SizeHintRole

    # Common roles from base
    SceneObjectRole = BaseItemRole.ObjectRole
    ShowRole = BaseItemRole.ShowRole
    SequenceRole = BaseItemRole.SequenceRole
    FullNameRole = BaseItemRole.FullNameRole
    WorkspacePathRole = BaseItemRole.WorkspacePathRole
    ThumbnailPathRole = BaseItemRole.ThumbnailPathRole
    ThumbnailPixmapRole = BaseItemRole.ThumbnailPixmapRole
    LoadingStateRole = BaseItemRole.LoadingStateRole
    IsSelectedRole = BaseItemRole.IsSelectedRole

    # 3DE-specific roles
    ShotRole = Qt.ItemDataRole.UserRole + 4
    UserRole = Qt.ItemDataRole.UserRole + 5
    ScenePathRole = Qt.ItemDataRole.UserRole + 6
    ModifiedTimeRole = Qt.ItemDataRole.UserRole + 11


class ThreeDEItemModel(BaseItemModel["ThreeDEScene"]):
    """3DE scene-specific Qt Model implementation.

    This model provides 3DE-specific functionality while
    inheriting common behavior from BaseItemModel.
    """

    # Additional 3DE-specific signals
    loading_started = Signal()
    loading_progress = Signal(int, int)  # current, total
    loading_finished = Signal()

    def __init__(
        self,
        cache_manager: QObject | None = None,
        parent: QObject | None = None,
    ) -> None:
        """Initialize the 3DE item model.

        Args:
            cache_manager: Optional cache manager for thumbnails
            parent: Optional parent QObject
        """
        super().__init__(cache_manager, parent)

        self._is_loading = False
        self._updating_filter = False  # Recursion guard for filter updates

        # For backward compatibility, provide scenes_updated signal
        # (BaseItemModel provides items_updated)
        self.scenes_updated = self.items_updated

        self.logger.info("ThreeDEItemModel initialized with Model/View architecture")

    # ============= Implement abstract methods =============

    @override
    def get_display_role_data(self, item: ThreeDEScene) -> str:
        """Get display text for a scene.

        Args:
            item: The scene to get display text for

        Returns:
            Display text string
        """
        return item.full_name

    @override
    def get_tooltip_data(self, item: ThreeDEScene) -> str:
        """Get tooltip text for a scene.

        Args:
            item: The scene to get tooltip for

        Returns:
            Tooltip text string
        """
        tooltip = f"Scene: {item.shot}\n"
        tooltip += f"User: {item.user}\n"
        tooltip += f"Path: {item.scene_path}"
        return tooltip

    @override
    def get_custom_role_data(self, item: ThreeDEScene, role: int) -> object:
        """Handle 3DE-specific custom roles.

        Args:
            item: The scene
            role: The data role

        Returns:
            Data for the role or None
        """
        if role == ThreeDERole.ShotRole:
            return item.shot
        elif role == ThreeDERole.UserRole:
            return item.user
        elif role == ThreeDERole.ScenePathRole:
            return item.scene_path
        elif role == ThreeDERole.ModifiedTimeRole:
            # Get modification time from the scene file
            try:
                return item.scene_path.stat().st_mtime
            except OSError:
                return 0.0  # Return 0 if file doesn't exist or can't be accessed

        return None

    # ============= 3DE-specific methods =============

    def set_scenes(self, scenes: list[ThreeDEScene], reset: bool = True) -> None:
        """Set the scenes for the model.

        Args:
            scenes: List of 3DE scenes
            reset: Whether to reset the model
        """
        if reset:
            # Use base class set_items method
            self.set_items(scenes)
        else:
            # Incremental update (more complex, for future optimization)
            self.beginResetModel()
            self._items = scenes
            self.endResetModel()
            self.scenes_updated.emit()

        self.logger.info(f"Set {len(scenes)} 3DE scenes in model")

    def set_show_filter(
        self, threede_scene_model: ThreeDESceneModel, show: str | None
    ) -> None:
        """Set show filter and update the model.

        Args:
            threede_scene_model: The scene model to get filtered scenes from
            show: Show name to filter by, or None for all shows
        """
        # Guard against recursion
        if self._updating_filter:
            return

        self._updating_filter = True
        try:
            threede_scene_model.set_show_filter(show)
            filtered_scenes = threede_scene_model.get_filtered_scenes()
            self.set_scenes(filtered_scenes, reset=True)

            # Emit filter changed signal for UI updates
            filter_display = show if show is not None else "All Shows"
            self.show_filter_changed.emit(filter_display)
            self.logger.info(
                f"Applied show filter: {filter_display}, {len(filtered_scenes)} scenes"
            )
        finally:
            self._updating_filter = False

    def get_scene(self, index: QModelIndex) -> ThreeDEScene | None:
        """Get scene at the given index.

        Compatibility wrapper for get_item_at_index.

        Args:
            index: Model index

        Returns:
            ThreeDEScene or None if invalid
        """
        return self.get_item_at_index(index)

    def set_selected(self, index: QModelIndex) -> None:
        """Set the selected scene.

        Args:
            index: Index to select
        """
        if self._selected_index != index:
            # Clear old selection
            if self._selected_index.isValid():
                from PySide6.QtCore import QModelIndex

                old_index = QModelIndex(self._selected_index)
                self.dataChanged.emit(
                    old_index, old_index, [BaseItemRole.IsSelectedRole]
                )

            # Set new selection
            from PySide6.QtCore import QPersistentModelIndex

            self._selected_index = QPersistentModelIndex(index)
            if index.isValid():
                self.dataChanged.emit(index, index, [BaseItemRole.IsSelectedRole])
                self._selected_item = self.get_item_at_index(index)
            else:
                self._selected_item = None

            self.selection_changed.emit(index)

    def set_loading_state(self, loading: bool) -> None:
        """Set the loading state.

        Args:
            loading: Whether loading is in progress
        """
        self._is_loading = loading
        if loading:
            self.loading_started.emit()
        else:
            self.loading_finished.emit()

    def update_loading_progress(self, current: int, total: int) -> None:
        """Update loading progress.

        Args:
            current: Current item being loaded
            total: Total items to load
        """
        self.loading_progress.emit(current, total)

    @property
    def scenes(self) -> list[ThreeDEScene]:
        """Get the list of scenes."""
        return self._items

    @property
    def is_loading(self) -> bool:
        """Check if loading is in progress."""
        return self._is_loading

    def cleanup(self) -> None:
        """Clean up resources before deletion.

        This method should be called before the model is deleted to prevent
        memory leaks and ensure proper resource cleanup.
        """
        # Stop timers
        if hasattr(self, "_thumbnail_timer"):
            self._thumbnail_timer.stop()
            self._thumbnail_timer.deleteLater()

        # Clear caches
        self.clear_thumbnail_cache()

        # Clear selection
        from PySide6.QtCore import QPersistentModelIndex

        self._selected_index = QPersistentModelIndex()

        # Disconnect signals safely
        for signal in [
            self.scenes_updated,
            self.thumbnail_loaded,
            self.selection_changed,
            self.loading_started,
            self.loading_progress,
            self.loading_finished,
        ]:
            try:
                signal.disconnect()
            except (RuntimeError, TypeError):
                pass  # Already disconnected or no connections

        self.logger.info("ThreeDEItemModel resources cleaned up")

    def deleteLater(self) -> None:
        """Override deleteLater to ensure cleanup."""
        self.cleanup()
        super().deleteLater()
