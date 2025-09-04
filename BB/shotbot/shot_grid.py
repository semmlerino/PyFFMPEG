"""Shot grid widget for displaying thumbnails in a grid layout.

DEPRECATED: This module is deprecated and will be removed in a future version.
Please use shot_grid_view.py and shot_item_model.py (Model/View architecture) instead.
The new implementation provides 98.9% memory reduction and better performance.

Migration guide:
    Old usage:
        from shot_grid import ShotGrid
        grid = ShotGrid(shot_model)

    New usage:
        from shot_grid_view import ShotGridView
        from shot_item_model import ShotItemModel

        item_model = ShotItemModel(cache_manager=cache)
        item_model.set_shots(shot_model.shots)
        grid = ShotGridView(model=item_model)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Signal

from base_grid_widget import BaseGridWidget
from thumbnail_widget import ThumbnailWidget

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget

    from shot_model import Shot, ShotModel


class ShotGrid(BaseGridWidget["Shot"]):
    """Grid display of shot thumbnails.

    This class extends BaseGridWidget to provide shot-specific functionality.
    """

    # Signals
    shot_selected = Signal(object)  # Shot
    shot_double_clicked = Signal(object)  # Shot

    def __init__(self, shot_model: ShotModel):
        """Initialize the shot grid.

        Args:
            shot_model: Model containing shot data.
        """
        super().__init__()
        self.shot_model = shot_model

    def refresh_shots(self):
        """Refresh the shot display."""
        self.refresh_display()

    def select_shot(self, shot: Shot):
        """Select a shot programmatically.

        Args:
            shot: Shot to select.
        """
        self.select_item(shot)

    # Implement abstract methods from BaseGridWidget

    def _create_thumbnail_widget(self, item: Shot) -> QWidget:
        """Create a thumbnail widget for a shot.

        Args:
            item: Shot to create thumbnail for.

        Returns:
            ThumbnailWidget instance.
        """
        return ThumbnailWidget(item, self.thumbnail_size)

    def _get_item_key(self, item: Shot) -> str:
        """Get unique key for a shot.

        Args:
            item: Shot to get key for.

        Returns:
            Shot's full name as key.
        """
        return item.full_name

    def _get_items(self) -> list[Shot]:
        """Get list of shots to display.

        Returns:
            List of shots from the model.
        """
        return self.shot_model.shots

    def _handle_item_selected(self, item: Shot) -> None:
        """Handle shot selection.

        Args:
            item: Selected shot.
        """
        self.shot_selected.emit(item)

    def _handle_item_double_clicked(self, item: Shot) -> None:
        """Handle shot double-click.

        Args:
            item: Double-clicked shot.
        """
        self.shot_double_clicked.emit(item)

    def _update_thumbnail_size(self, thumbnail: QWidget, size: int) -> None:
        """Update thumbnail widget size.

        Args:
            thumbnail: Thumbnail widget to update.
            size: New size in pixels.
        """
        if isinstance(thumbnail, ThumbnailWidget):
            thumbnail.set_size(size)

    def _set_thumbnail_selected(self, thumbnail: QWidget, selected: bool) -> None:
        """Set thumbnail selection state.

        Args:
            thumbnail: Thumbnail widget.
            selected: Whether thumbnail is selected.
        """
        if isinstance(thumbnail, ThumbnailWidget):
            thumbnail.set_selected(selected)

    def _connect_thumbnail_signals(self, thumbnail: QWidget, item: Shot) -> None:
        """Connect thumbnail widget signals.

        Args:
            thumbnail: Thumbnail widget.
            item: Associated shot.
        """
        if isinstance(thumbnail, ThumbnailWidget):
            # Use lambda to pass the shot object
            thumbnail.clicked.connect(lambda: self._on_item_clicked(item))
            thumbnail.double_clicked.connect(lambda: self._on_item_double_clicked(item))

    @property
    def selected_shot(self) -> Shot | None:
        """Get the currently selected shot.

        Returns:
            Selected shot or None.
        """
        return self.selected_item
