"""Qt Model/View implementation for shot data using BaseItemModel.

This module provides a Shot-specific Qt Model/View implementation that
inherits common functionality from BaseItemModel, reducing code duplication.
"""

from __future__ import annotations

from enum import IntEnum
from typing import TYPE_CHECKING

from typing_extensions import override

if TYPE_CHECKING:
    from base_shot_model import BaseShotModel
    from cache_manager import CacheManager

from PySide6.QtCore import (
    QModelIndex,
    QObject,
    Qt,
    Slot,
)

from base_item_model import BaseItemModel, BaseItemRole
from shot_model import RefreshResult, Shot


class ShotRole(IntEnum):
    """Custom roles for shot data access - extends BaseItemRole."""

    # Inherit all base roles
    DisplayRole = BaseItemRole.DisplayRole
    DecorationRole = BaseItemRole.DecorationRole
    ToolTipRole = BaseItemRole.ToolTipRole
    SizeHintRole = BaseItemRole.SizeHintRole

    # Common roles from base
    ShotObjectRole = BaseItemRole.ObjectRole
    ShowRole = BaseItemRole.ShowRole
    SequenceRole = BaseItemRole.SequenceRole
    FullNameRole = BaseItemRole.FullNameRole
    WorkspacePathRole = BaseItemRole.WorkspacePathRole
    ThumbnailPathRole = BaseItemRole.ThumbnailPathRole
    ThumbnailPixmapRole = BaseItemRole.ThumbnailPixmapRole
    LoadingStateRole = BaseItemRole.LoadingStateRole
    IsSelectedRole = BaseItemRole.IsSelectedRole

    # Shot-specific roles
    ShotNameRole = Qt.ItemDataRole.UserRole + 4


class ShotItemModel(BaseItemModel[Shot]):
    """Shot-specific Qt Model implementation.

    This model provides Shot-specific functionality while
    inheriting common behavior from BaseItemModel.
    """

    def __init__(
        self,
        cache_manager: CacheManager | None = None,
        parent: QObject | None = None,
    ) -> None:
        """Initialize the shot item model.

        Args:
            cache_manager: Optional cache manager for thumbnails
            parent: Optional parent QObject
        """
        super().__init__(cache_manager, parent)

        # For backward compatibility, provide shots_updated signal
        # (BaseItemModel provides items_updated)
        self.shots_updated = self.items_updated

    # ============= Implement abstract methods =============

    @override
    def get_display_role_data(self, item: Shot) -> str:
        """Get display text for a shot.

        Args:
            item: The shot to get display text for

        Returns:
            Display text string
        """
        return item.full_name

    @override
    def get_tooltip_data(self, item: Shot) -> str:
        """Get tooltip text for a shot.

        Args:
            item: The shot to get tooltip for

        Returns:
            Tooltip text string
        """
        return f"{item.show} / {item.sequence} / {item.shot}\n{item.workspace_path}"

    @override
    def get_custom_role_data(self, item: Shot, role: int) -> object:
        """Handle shot-specific custom roles.

        Args:
            item: The shot
            role: The data role

        Returns:
            Data for the role or None
        """
        if role == ShotRole.ShotNameRole:
            return item.shot

        return None

    # ============= Shot-specific methods =============

    @Slot(list)
    def set_shots(self, shots: list[Shot]) -> None:
        """Set the shot list with proper model reset.

        Args:
            shots: List of Shot objects
        """
        # Use base class set_items method
        self.set_items(shots)

    def refresh_shots(self, shots: list[Shot]) -> RefreshResult:
        """Refresh shots with intelligent updates.

        Args:
            shots: New list of shots

        Returns:
            RefreshResult indicating success and changes
        """
        # Compare with existing shots
        old_shot_names = {shot.full_name for shot in self._items}
        new_shot_names = {shot.full_name for shot in shots}

        has_changes = old_shot_names != new_shot_names

        if has_changes:
            # Use beginInsertRows/beginRemoveRows for incremental updates
            # For simplicity, doing full reset here, but could be optimized
            self.set_shots(shots)

        return RefreshResult(success=True, has_changes=has_changes)

    def set_show_filter(self, shot_model: BaseShotModel, show: str | None) -> None:
        """Set show filter and update the model.

        Args:
            shot_model: Shot model to get filtered shots from
            show: Show name to filter by or None for all shows
        """
        if not shot_model:
            return

        # Set filter on the shot model
        shot_model.set_show_filter(show)

        # Get filtered shots and update our display
        filtered_shots = shot_model.get_filtered_shots()
        self.set_shots(filtered_shots)

        # Emit filter changed signal for UI updates
        filter_display = show if show is not None else "All Shows"
        self.show_filter_changed.emit(filter_display)
        self.logger.info(
            f"Applied show filter: {filter_display}, {len(filtered_shots)} shots"
        )

    # ============= Compatibility methods =============

    def get_shot_at_index(self, index: QModelIndex) -> Shot | None:
        """Get shot object at the given index.

        Compatibility wrapper for get_item_at_index.

        Args:
            index: Model index

        Returns:
            Shot object or None if invalid
        """
        return self.get_item_at_index(index)

    def _find_shot_by_full_name(self, full_name: str) -> tuple[Shot, int] | None:
        """Find a shot and its row index by full_name.

        Thread-safe compatibility wrapper for _find_item_by_full_name.

        Args:
            full_name: The full name of the shot to find

        Returns:
            Tuple of (shot, row) or None if not found
        """
        return self._find_item_by_full_name(full_name)
