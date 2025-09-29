"""Unified Qt Model/View implementation that replaces Shot, ThreeDe, and Previous item models.

This module provides a single configurable Qt Model/View implementation that
eliminates ~600+ lines of duplication by unifying the three separate models:
- ShotItemModel (207 lines)
- ThreeDEItemModel (308 lines)
- PreviousShotsItemModel (192 lines)

The unified model uses strategy pattern to handle the minor differences between
the three item types while sharing the vast majority of common functionality.
"""

from __future__ import annotations

from collections.abc import Sequence

# Standard library imports
from enum import IntEnum, auto
from pathlib import Path
from typing import TYPE_CHECKING, Union

# Third-party imports
from PySide6.QtCore import (
    QModelIndex,
    QObject,
    Qt,
    Signal,
)
from typing_extensions import override

# Local application imports
from base_item_model import BaseItemModel, BaseItemRole

if TYPE_CHECKING:
    # Local application imports
    # Protocol for underlying models
    from typing import Protocol

    from cache_manager import CacheManager
    from previous_shots_model import PreviousShotsModel
    from shot_model import RefreshResult, Shot
    from threede_scene_model import ThreeDEScene

    class UnderlyingModelProtocol(Protocol):
        """Protocol for objects that can serve as underlying models."""

        # Signal attributes - use object type to avoid Qt descriptor issues
        shots_updated: object  # Qt Signal for models that emit this signal

        # Methods
        def get_filtered_shots(self) -> Sequence[Shot]: ...
        def get_filtered_scenes(self) -> Sequence[ThreeDEScene]: ...
        def set_items_with_type_check(self, items: Sequence[ItemType]) -> None: ...
        def set_show_filter(self, show: str | None) -> None: ...


# Type alias for all supported item types
ItemType = Union["Shot", "ThreeDEScene"]


class UnifiedItemType(IntEnum):
    """Types of items supported by the unified model."""

    SHOT = auto()
    THREEDE = auto()
    PREVIOUS = auto()


class UnifiedRole(IntEnum):
    """Unified custom roles that work for all item types."""

    # Inherit all base roles
    DisplayRole = BaseItemRole.DisplayRole
    DecorationRole = BaseItemRole.DecorationRole
    ToolTipRole = BaseItemRole.ToolTipRole
    SizeHintRole = BaseItemRole.SizeHintRole

    # Common roles from base
    ObjectRole = BaseItemRole.ObjectRole
    ShowRole = BaseItemRole.ShowRole
    SequenceRole = BaseItemRole.SequenceRole
    FullNameRole = BaseItemRole.FullNameRole
    WorkspacePathRole = BaseItemRole.WorkspacePathRole
    ThumbnailPathRole = BaseItemRole.ThumbnailPathRole
    ThumbnailPixmapRole = BaseItemRole.ThumbnailPixmapRole
    LoadingStateRole = BaseItemRole.LoadingStateRole
    IsSelectedRole = BaseItemRole.IsSelectedRole

    # Unified specific roles (mapped to different attributes based on item type)
    # Use higher numbers to avoid conflicts with BaseItemRole (which uses +1 to +10)
    ItemSpecificRole1 = (
        Qt.ItemDataRole.UserRole + 20
    )  # shot.shot OR scene.shot OR shot.shot
    ItemSpecificRole2 = Qt.ItemDataRole.UserRole + 21  # N/A OR scene.user OR N/A
    ItemSpecificRole3 = Qt.ItemDataRole.UserRole + 22  # N/A OR scene.scene_path OR N/A
    ModifiedTimeRole = (
        Qt.ItemDataRole.UserRole + 23
    )  # N/A OR scene modified time OR N/A


class UnifiedItemModel(BaseItemModel[ItemType]):
    """Unified Qt Model implementation that handles all item types.

    This model replaces ShotItemModel, ThreeDEItemModel, and PreviousShotsItemModel
    by using a configurable strategy pattern to handle the minor differences between
    item types while sharing the vast majority of common functionality.
    """

    # Type-specific signals (for backward compatibility)
    shots_updated = Signal()  # Emitted for SHOT and PREVIOUS types
    scenes_updated = Signal()  # Emitted for THREEDE type
    loading_started = Signal()  # For THREEDE type
    loading_progress = Signal(int, int)  # For THREEDE type
    loading_finished = Signal()  # For THREEDE type

    def __init__(
        self,
        item_type: UnifiedItemType,
        cache_manager: CacheManager | None = None,
        parent: QObject | None = None,
        underlying_model: UnderlyingModelProtocol | None = None,
    ) -> None:
        """Initialize the unified item model.

        Args:
            item_type: Type of items this model will handle
            cache_manager: Optional cache manager for thumbnails
            parent: Optional parent QObject
            underlying_model: For PREVIOUS type, the PreviousShotsModel instance
        """
        super().__init__(cache_manager, parent)

        self.item_type = item_type
        self._underlying_model = underlying_model
        self._is_loading = False
        self._updating_filter = False  # Recursion guard for filter updates

        # Connect type-specific signals to the unified items_updated signal
        if item_type in (UnifiedItemType.SHOT, UnifiedItemType.PREVIOUS):
            self.items_updated.connect(self.shots_updated)
        elif item_type == UnifiedItemType.THREEDE:
            self.items_updated.connect(self.scenes_updated)

        # For PREVIOUS type, connect to underlying model
        if item_type == UnifiedItemType.PREVIOUS and underlying_model:
            # Check if it's a real Qt signal or a test double
            if hasattr(underlying_model, "shots_updated") and hasattr(
                underlying_model.shots_updated, "emit"
            ):
                # Test double - connect without Qt.ConnectionType
                underlying_model.shots_updated.connect(  # type: ignore[attr-defined]
                    self._on_underlying_shots_updated
                )
            elif hasattr(underlying_model, "shots_updated"):
                # Real Qt signal - use proper connection type
                underlying_model.shots_updated.connect(  # type: ignore[attr-defined]
                    self._on_underlying_shots_updated,
                    Qt.ConnectionType.QueuedConnection,
                )
            # Initialize with current shots
            self._update_from_underlying_model()

        self.logger.info(f"UnifiedItemModel initialized for {item_type.name} items")

    # ============= Implement abstract methods =============

    @override
    def get_display_role_data(self, item: ItemType) -> str:
        """Get display text for an item.

        Args:
            item: The item to get display text for

        Returns:
            Display text string
        """
        return item.full_name

    @override
    def get_tooltip_data(self, item: ItemType) -> str:
        """Get tooltip text for an item.

        Args:
            item: The item to get tooltip for

        Returns:
            Tooltip text string
        """
        if self.item_type == UnifiedItemType.THREEDE:
            # ThreeDEScene has different tooltip format
            tooltip = f"Scene: {item.shot}\n"
            tooltip += f"User: {getattr(item, 'user', '')}\n"
            tooltip += f"Path: {getattr(item, 'scene_path', '')}"
            return tooltip
        else:
            # Shot format (for SHOT and PREVIOUS types)
            return f"{item.show} / {item.sequence} / {item.shot}\n{item.workspace_path}"

    @override
    def get_custom_role_data(self, item: ItemType, role: int) -> object:
        """Handle type-specific custom roles.

        Args:
            item: The item
            role: The data role

        Returns:
            Data for the role or None
        """
        # Handle unified roles
        if role == UnifiedRole.ItemSpecificRole1:
            # Always return the shot name/ID
            return item.shot
        elif (
            role == UnifiedRole.ItemSpecificRole2
            and self.item_type == UnifiedItemType.THREEDE
        ):
            # Only for ThreeDEScene: return user
            return getattr(item, 'user', '')
        elif (
            role == UnifiedRole.ItemSpecificRole3
            and self.item_type == UnifiedItemType.THREEDE
        ):
            # Only for ThreeDEScene: return scene path
            return getattr(item, 'scene_path', None)
        elif (
            role == UnifiedRole.ModifiedTimeRole
            and self.item_type == UnifiedItemType.THREEDE
        ):
            # Only for ThreeDEScene: return modification time
            scene_path = getattr(item, 'scene_path', None)
            if scene_path and isinstance(scene_path, Path):
                try:
                    return float(scene_path.stat().st_mtime)
                except OSError:
                    return 0.0  # Return 0 if file doesn't exist
            return 0.0
        elif role == UnifiedRole.ObjectRole:
            # Return the item object itself
            return item
        elif role == UnifiedRole.FullNameRole:
            return item.full_name

        # Handle legacy roles for backward compatibility
        elif role == (Qt.ItemDataRole.UserRole + 4):  # Legacy ShotRole.ShotNameRole
            if self.item_type in (UnifiedItemType.SHOT, UnifiedItemType.PREVIOUS):
                return item.shot
        elif (
            role == (Qt.ItemDataRole.UserRole + 5)
            and self.item_type == UnifiedItemType.THREEDE
        ):
            # Legacy ThreeDERole.UserRole
            return getattr(item, 'user', '')
        elif (
            role == (Qt.ItemDataRole.UserRole + 6)
            and self.item_type == UnifiedItemType.THREEDE
        ):
            # Legacy ThreeDERole.ScenePathRole
            return getattr(item, 'scene_path', None)
        elif (
            role == (Qt.ItemDataRole.UserRole + 11)
            and self.item_type == UnifiedItemType.THREEDE
        ):
            # Legacy ThreeDERole.ModifiedTimeRole
            scene_path = getattr(item, 'scene_path', None)
            if scene_path and isinstance(scene_path, Path):
                try:
                    return float(scene_path.stat().st_mtime)
                except OSError:
                    return 0.0
            return 0.0

        return None

    # ============= Unified methods that replace type-specific ones =============

    def set_items_with_type_check(self, items: Sequence[ItemType]) -> None:
        """Set items with backward compatibility aliases.

        Args:
            items: Sequence of items (Shot or ThreeDEScene objects)
        """
        self.set_items(list(items))  # Convert to list for BaseItemModel

    # Alias methods for backward compatibility
    def set_shots(self, shots: Sequence[Shot]) -> None:
        """Backward compatibility alias for set_items."""
        self.set_items_with_type_check(shots)

    def set_scenes(self, scenes: list[ThreeDEScene], reset: bool = True) -> None:
        """Backward compatibility alias for set_items."""
        if reset:
            self.set_items_with_type_check(scenes)
        else:
            # Incremental update (more complex, for future optimization)
            self.beginResetModel()
            self._items = list(scenes)
            self.endResetModel()
            self.scenes_updated.emit()
        self.logger.info(f"Set {len(scenes)} items in unified model")

    def refresh_shots(self, shots: list[Shot]) -> RefreshResult:
        """Backward compatibility method for shot refresh.

        Args:
            shots: New list of shots

        Returns:
            RefreshResult indicating success and changes
        """
        # Compare with existing items
        old_names = {item.full_name for item in self._items}
        new_names = {shot.full_name for shot in shots}

        has_changes = old_names != new_names

        if has_changes:
            self.set_shots(shots)

        # Import here to avoid circular imports
        from shot_model import RefreshResult

        return RefreshResult(success=True, has_changes=has_changes)

    def set_show_filter(self, data_model: UnderlyingModelProtocol, show: str | None) -> None:
        """Set show filter using appropriate strategy for item type.

        Args:
            data_model: The underlying data model (BaseShotModel, ThreeDESceneModel, etc.)
            show: Show name to filter by or None for all shows
        """
        # Guard against recursion for ThreeDe type
        if self.item_type == UnifiedItemType.THREEDE and self._updating_filter:
            return

        try:
            if self.item_type == UnifiedItemType.THREEDE:
                self._updating_filter = True

            # Set filter on the data model
            data_model.set_show_filter(show)

            # Get filtered items based on type
            if self.item_type == UnifiedItemType.SHOT:
                filtered_items = data_model.get_filtered_shots()
            elif self.item_type == UnifiedItemType.THREEDE:
                filtered_items = data_model.get_filtered_scenes()
            elif self.item_type == UnifiedItemType.PREVIOUS:
                filtered_items = data_model.get_filtered_shots()
            else:
                return

            self.set_items_with_type_check(
                list(filtered_items)
            )  # Convert to list for type safety

            # Emit filter changed signal for UI updates
            filter_display = show if show is not None else "All Shows"
            self.show_filter_changed.emit(filter_display)
            self.logger.info(
                f"Applied show filter: {filter_display}, {len(filtered_items)} items"
            )
        finally:
            if self.item_type == UnifiedItemType.THREEDE:
                self._updating_filter = False

    # ============= Compatibility methods with type-appropriate aliases =============

    def get_shot_at_index(self, index: QModelIndex) -> Shot | None:
        """Compatibility alias for get_item_at_index (Shot types)."""
        # Type casting is safe since this is only used for SHOT and PREVIOUS types
        from typing import cast

        return cast("Shot | None", self.get_item_at_index(index))

    def get_scene(self, index: QModelIndex) -> ThreeDEScene | None:
        """Compatibility alias for get_item_at_index (ThreeDEScene type)."""
        # Type casting is safe since this is only used for THREEDE type
        from typing import cast

        return cast("ThreeDEScene | None", self.get_item_at_index(index))

    def get_selected_shot(self) -> Shot | None:
        """Compatibility alias for get_selected_item (Shot types)."""
        # Type casting is safe since this is only used for SHOT and PREVIOUS types
        from typing import cast

        return cast("Shot | None", self.get_selected_item())

    def _find_shot_by_full_name(self, full_name: str) -> tuple[Shot, int] | None:
        """Compatibility alias for _find_item_by_full_name."""
        # Type casting is safe since this is only used for SHOT and PREVIOUS types
        from typing import cast

        return cast("tuple[Shot, int] | None", self._find_item_by_full_name(full_name))

    # ============= ThreeDe-specific methods =============

    def set_loading_state(self, loading: bool) -> None:
        """Set loading state (ThreeDe type only).

        Args:
            loading: Whether loading is in progress
        """
        if self.item_type != UnifiedItemType.THREEDE:
            return

        self._is_loading = loading
        if loading:
            self.loading_started.emit()
        else:
            self.loading_finished.emit()

    def update_loading_progress(self, current: int, total: int) -> None:
        """Update loading progress (ThreeDe type only).

        Args:
            current: Current item being loaded
            total: Total items to load
        """
        if self.item_type == UnifiedItemType.THREEDE:
            self.loading_progress.emit(current, total)

    def set_selected(self, index: QModelIndex) -> None:
        """Set selected item (enhanced version from ThreeDe model).

        Args:
            index: Index to select
        """
        # Convert to QPersistentModelIndex for proper comparison
        from PySide6.QtCore import QPersistentModelIndex

        persistent_index = QPersistentModelIndex(index)
        if self._selected_index != persistent_index:
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

    # ============= Previous shots specific methods =============

    def _on_underlying_shots_updated(self) -> None:
        """Handle shots update from underlying model (Previous type only)."""
        if self.item_type == UnifiedItemType.PREVIOUS:
            self._update_from_underlying_model()

    def _update_from_underlying_model(self) -> None:
        """Update items from underlying model (Previous type only)."""
        if self.item_type != UnifiedItemType.PREVIOUS or not self._underlying_model:
            return

        # Type casting is safe since this is only called for PREVIOUS type
        from typing import cast

        model = cast("PreviousShotsModel", self._underlying_model)
        new_shots = model.get_shots()
        self.set_items(new_shots)  # type: ignore[arg-type]
        self.logger.debug(f"Updated unified model with {len(new_shots)} previous shots")

    def refresh(self) -> None:
        """Trigger refresh of underlying model (Previous type only)."""
        if self.item_type == UnifiedItemType.PREVIOUS and self._underlying_model:
            # Type casting is safe since this is only called for PREVIOUS type
            from typing import cast

            model = cast("PreviousShotsModel", self._underlying_model)
            model.refresh_shots()

    def get_underlying_model(self) -> PreviousShotsModel | None:
        """Get underlying model (Previous type only)."""
        if self.item_type == UnifiedItemType.PREVIOUS:
            # Type casting is safe since this is only called for PREVIOUS type
            from typing import cast

            return cast("PreviousShotsModel | None", self._underlying_model)
        return None

    # ============= Properties =============

    @property
    def shots(self) -> list[Shot]:
        """Get items as shots (for compatibility)."""
        # Type casting is safe since this is only used for SHOT and PREVIOUS types
        from typing import cast

        return cast("list[Shot]", self._items)

    @property
    def scenes(self) -> list[ThreeDEScene]:
        """Get items as scenes (for compatibility)."""
        # Type casting is safe since this is only used for THREEDE type
        from typing import cast

        return cast("list[ThreeDEScene]", self._items)

    @property
    def is_loading(self) -> bool:
        """Check if loading is in progress (ThreeDe type)."""
        return self._is_loading if self.item_type == UnifiedItemType.THREEDE else False

    # ============= Cleanup =============

    def cleanup(self) -> None:
        """Clean up resources before deletion."""
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
        signals_to_disconnect = [
            self.items_updated,
            self.shots_updated,
            self.scenes_updated,
            self.thumbnail_loaded,
            self.selection_changed,
        ]

        if self.item_type == UnifiedItemType.THREEDE:
            signals_to_disconnect.extend(
                [
                    self.loading_started,
                    self.loading_progress,
                    self.loading_finished,
                ]
            )

        for signal in signals_to_disconnect:
            try:
                signal.disconnect()
            except (RuntimeError, TypeError):
                pass  # Already disconnected or no connections

        self.logger.info(f"UnifiedItemModel cleanup complete for {self.item_type.name}")

    def deleteLater(self) -> None:
        """Override deleteLater to ensure cleanup."""
        self.cleanup()
        super().deleteLater()


# ============= Factory functions for easy migration =============


def create_shot_item_model(
    cache_manager: CacheManager | None = None, parent: QObject | None = None
) -> UnifiedItemModel:
    """Factory function to create a shot item model.

    This replaces ShotItemModel and provides the same interface.
    """
    return UnifiedItemModel(UnifiedItemType.SHOT, cache_manager, parent)


def create_threede_item_model(
    cache_manager: CacheManager | None = None, parent: QObject | None = None
) -> UnifiedItemModel:
    """Factory function to create a 3DE item model.

    This replaces ThreeDEItemModel and provides the same interface.
    """
    return UnifiedItemModel(UnifiedItemType.THREEDE, cache_manager, parent)


def create_previous_shots_item_model(
    previous_shots_model: UnderlyingModelProtocol,
    cache_manager: CacheManager | None = None,
    parent: QObject | None = None,
) -> UnifiedItemModel:
    """Factory function to create a previous shots item model.

    This replaces PreviousShotsItemModel and provides the same interface.
    """
    return UnifiedItemModel(
        UnifiedItemType.PREVIOUS, cache_manager, parent, previous_shots_model
    )
