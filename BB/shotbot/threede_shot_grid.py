"""3DE scene grid widget for displaying scene thumbnails in a grid layout."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget

from base_grid_widget import BaseGridWidget
from threede_thumbnail_widget import ThreeDEThumbnailWidget

if TYPE_CHECKING:
    from threede_scene_model import ThreeDEScene, ThreeDESceneModel


class ThreeDEShotGrid(BaseGridWidget["ThreeDEScene"]):
    """Grid display of 3DE scene thumbnails.

    This class extends BaseGridWidget to provide 3DE scene-specific functionality
    with additional loading indicators.
    """

    # Signals
    scene_selected = Signal(object)  # ThreeDEScene
    scene_double_clicked = Signal(object)  # ThreeDEScene

    def __init__(self, scene_model: ThreeDESceneModel):
        """Initialize the 3DE scene grid.

        Args:
            scene_model: Model containing 3DE scene data.
        """
        super().__init__()
        self.scene_model = scene_model
        self._is_loading = False

    def _create_extra_controls(self) -> QWidget | None:
        """Create loading indicators as extra controls.

        Returns:
            Widget containing loading indicators.
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Loading indicator
        self.loading_bar = QProgressBar()
        self.loading_bar.setRange(0, 0)  # Indeterminate
        self.loading_bar.setVisible(False)
        self.loading_bar.setMaximumHeight(3)
        layout.addWidget(self.loading_bar)

        # Loading label
        self.loading_label = QLabel("Scanning for 3DE scenes...")
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_label.setVisible(False)
        self.loading_label.setStyleSheet("color: #888; padding: 5px;")
        layout.addWidget(self.loading_label)

        return widget

    def set_loading(self, loading: bool, message: str = "Scanning for 3DE scenes..."):
        """Set loading state.

        Args:
            loading: Whether currently loading.
            message: Message to display.
        """
        self._is_loading = loading
        self.loading_bar.setVisible(loading)
        self.loading_label.setVisible(loading)
        self.loading_label.setText(message)

    def set_loading_progress(self, current: int, total: int):
        """Set loading progress.

        Args:
            current: Current progress value.
            total: Total progress value.
        """
        if total > 0:
            self.loading_bar.setRange(0, total)
            self.loading_bar.setValue(current)
            self.loading_label.setText(f"Scanning shots ({current}/{total})...")

    def refresh_scenes(self):
        """Refresh the scene display."""
        self.refresh_display()

    def select_scene(self, scene: ThreeDEScene):
        """Select a scene programmatically.

        Args:
            scene: Scene to select.
        """
        self.select_item(scene)

    # Implement abstract methods from BaseGridWidget

    def _create_thumbnail_widget(self, item: ThreeDEScene) -> QWidget:
        """Create a thumbnail widget for a 3DE scene.

        Args:
            item: Scene to create thumbnail for.

        Returns:
            ThreeDEThumbnailWidget instance.
        """
        return ThreeDEThumbnailWidget(item, self.thumbnail_size)

    def _get_item_key(self, item: ThreeDEScene) -> str:
        """Get unique key for a 3DE scene.

        Args:
            item: Scene to get key for.

        Returns:
            Scene's display name as key.
        """
        return item.display_name

    def _get_items(self) -> list[ThreeDEScene]:
        """Get list of scenes to display.

        Returns:
            List of scenes from the model.
        """
        return self.scene_model.scenes

    def _handle_item_selected(self, item: ThreeDEScene) -> None:
        """Handle scene selection.

        Args:
            item: Selected scene.
        """
        self.scene_selected.emit(item)

    def _handle_item_double_clicked(self, item: ThreeDEScene) -> None:
        """Handle scene double-click.

        Args:
            item: Double-clicked scene.
        """
        self.scene_double_clicked.emit(item)

    def _update_thumbnail_size(self, thumbnail: QWidget, size: int) -> None:
        """Update thumbnail widget size.

        Args:
            thumbnail: Thumbnail widget to update.
            size: New size in pixels.
        """
        if isinstance(thumbnail, ThreeDEThumbnailWidget):
            thumbnail.set_size(size)

    def _set_thumbnail_selected(self, thumbnail: QWidget, selected: bool) -> None:
        """Set thumbnail selection state.

        Args:
            thumbnail: Thumbnail widget.
            selected: Whether thumbnail is selected.
        """
        if isinstance(thumbnail, ThreeDEThumbnailWidget):
            thumbnail.set_selected(selected)

    def _connect_thumbnail_signals(
        self, thumbnail: QWidget, item: ThreeDEScene
    ) -> None:
        """Connect thumbnail widget signals.

        Args:
            thumbnail: Thumbnail widget.
            item: Associated scene.
        """
        if isinstance(thumbnail, ThreeDEThumbnailWidget):
            # Use lambda to pass the scene object
            thumbnail.clicked.connect(lambda: self._on_item_clicked(item))
            thumbnail.double_clicked.connect(lambda: self._on_item_double_clicked(item))

    def _show_empty_state(self) -> None:
        """Show custom empty state for 3DE scenes."""
        empty_label = QLabel("No 3DE scenes found from other users")
        empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_label.setStyleSheet("color: #888; font-size: 14px; padding: 40px;")
        self.grid_layout.addWidget(empty_label, 0, 0)

    @property
    def selected_scene(self) -> ThreeDEScene | None:
        """Get the currently selected scene.

        Returns:
            Selected scene or None.
        """
        return self.selected_item
