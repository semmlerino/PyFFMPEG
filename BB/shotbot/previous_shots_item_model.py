"""Qt Model/View item model for previous shots display using BaseItemModel.

This module provides a Previous Shots-specific Qt Model/View implementation that
inherits common functionality from BaseItemModel, reducing code duplication.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import (
    QObject,
    Qt,
    Slot,
)
from typing_extensions import override

from base_item_model import BaseItemModel
from shot_item_model import ShotRole  # Reuse the same roles

if TYPE_CHECKING:
    from cache_manager import CacheManager
    from previous_shots_model import PreviousShotsModel
    from shot_model import Shot


class PreviousShotsItemModel(BaseItemModel["Shot"]):
    """Previous shots-specific Qt Model implementation.

    This model wraps PreviousShotsModel and provides the Qt Model/View
    interface for efficient display in views. It inherits common
    functionality from BaseItemModel.
    """

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
        super().__init__(cache_manager, parent)

        self._model = previous_shots_model

        # For backward compatibility, provide shots_updated signal
        # (BaseItemModel provides items_updated)
        self.shots_updated = self.items_updated

        # Connect to underlying model signals with QueuedConnection for thread safety
        self._model.shots_updated.connect(
            self._on_shots_updated, Qt.ConnectionType.QueuedConnection
        )

        # Initialize with current shots
        self._update_shots()

        self.logger.info(f"PreviousShotsItemModel initialized with {len(self._items)} shots")

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
        # PreviousShotsItemModel reuses ShotRole, handle shot-specific roles
        if role == ShotRole.ShotNameRole:
            return item.shot
        elif role == ShotRole.ShotObjectRole:
            return item
        elif role == ShotRole.FullNameRole:
            return item.full_name

        return None

    # ============= Previous shots specific methods =============

    @property
    def shots(self) -> list[Shot]:
        """Get the current list of shots.

        Returns:
            List of Shot objects
        """
        return self._items

    @Slot()
    def _on_shots_updated(self) -> None:
        """Handle shots update from underlying model."""
        self._update_shots()

    def _update_shots(self) -> None:
        """Update the shot list from the underlying model."""
        # Get shots from PreviousShotsModel
        new_shots = self._model.get_shots()

        # Use base class set_items method which handles everything
        # (model reset, cache clearing, selection update)
        self.set_items(new_shots)

        self.logger.debug(f"Updated model with {len(new_shots)} previous shots")

    def get_selected_shot(self) -> Shot | None:
        """Get the currently selected shot.

        Compatibility wrapper for get_selected_item.

        Returns:
            Selected shot or None
        """
        return self.get_selected_item()

    def refresh(self) -> None:
        """Trigger a refresh of the underlying model."""
        self._model.refresh_shots()

    def get_underlying_model(self) -> PreviousShotsModel:
        """Get the underlying PreviousShotsModel.

        Returns:
            The underlying previous shots model
        """
        return self._model

    def set_show_filter(
        self, previous_shots_model: PreviousShotsModel, show: str | None
    ) -> None:
        """Set show filter and update the model.

        Args:
            previous_shots_model: Model to get filtered shots from
            show: Show name to filter by or None for all shows
        """
        if not previous_shots_model:
            return

        # Set filter on the model
        previous_shots_model.set_show_filter(show)

        # Get filtered shots and update our display
        filtered_shots = previous_shots_model.get_filtered_shots()

        # Update our shots list with filtered shots
        self.set_items(filtered_shots)

        # Emit filter changed signal for UI updates
        filter_display = show if show is not None else "All Shows"
        self.show_filter_changed.emit(filter_display)
        self.logger.info(
            f"Applied show filter: {filter_display}, {len(filtered_shots)} shots"
        )
