"""Optimized grid view for shot thumbnails using Qt Model/View architecture.

This module provides a QListView-based implementation that replaces the manual
widget management approach, providing virtualization, efficient scrolling,
and proper Model/View integration.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import (
    QModelIndex,
    Qt,
    QThreadPool,
    Signal,
    Slot,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QMenu,
    QWidget,
)

from base_grid_view import BaseGridView
from shot_grid_delegate import ShotGridDelegate
from shot_item_model import ShotItemModel, ShotRole
from shot_model import Shot
from thumbnail_widget_base import FolderOpenerWorker

if TYPE_CHECKING:
    from PySide6.QtGui import QContextMenuEvent

    from base_shot_model import BaseShotModel
    from base_thumbnail_delegate import BaseThumbnailDelegate


class ShotGridView(BaseGridView):
    """Optimized grid view for displaying shot thumbnails.

    This view provides:
    - Virtualization (only renders visible items)
    - Efficient scrolling for large datasets
    - Lazy loading of thumbnails
    - Proper Model/View integration
    - Dynamic grid layout based on window size
    - Context menu for folder operations
    """

    # Additional signals specific to ShotGridView
    shot_selected = Signal(Shot)  # Shot object
    shot_double_clicked = Signal(Shot)  # Shot object

    def __init__(
        self,
        model: ShotItemModel | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the grid view.

        Args:
            model: Optional shot item model
            parent: Optional parent widget
        """
        # Initialize base class
        super().__init__(parent)

        # ShotGridView-specific attributes
        self._selected_shot: Shot | None = None
        self._model: ShotItemModel | None = model

        if model:
            self.set_model(model)

        self.logger.info("ShotGridView initialized with Model/View architecture")

    def _create_delegate(self) -> BaseThumbnailDelegate:
        """Create the shot grid delegate.

        Returns:
            ShotGridDelegate instance
        """
        return ShotGridDelegate(self)

    @property
    def model(self) -> ShotItemModel | None:
        """Get the current data model.

        Returns:
            The shot item model or None
        """
        return self._model

    @property
    def selected_shot(self) -> Shot | None:
        """Get the currently selected shot.

        Returns:
            The selected Shot object or None
        """
        return self._selected_shot

    @property
    def thumbnail_size(self) -> int:
        """Get the current thumbnail size.

        Returns:
            Current thumbnail size in pixels
        """
        return self._thumbnail_size

    def refresh_shots(self) -> None:
        """Compatibility method for refreshing shots.

        This method exists for compatibility with the old ShotGrid interface.
        It's not needed for Model/View as updates happen through the model.
        """
        # Model/View updates automatically when model data changes
        # This method is kept for interface compatibility
        if self._model:
            # Force a view update
            self.list_view.viewport().update()
            self.logger.debug(
                "View refresh requested (Model/View updates automatically)"
            )

    def set_model(self, model: ShotItemModel) -> None:
        """Set the data model for the view.

        Args:
            model: Shot item model
        """
        self._model = model
        self.list_view.setModel(model)

        # Set up selection model
        selection_model = self.list_view.selectionModel()
        if selection_model:
            selection_model.currentChanged.connect(self._on_selection_changed)

        # Connect to model signals
        model.shots_updated.connect(self._on_model_updated)

        self.logger.debug(f"Model set with {model.rowCount()} items")

    def populate_show_filter(self, shot_model: BaseShotModel) -> None:
        """Populate the show filter combo box with available shows.

        Args:
            shot_model: Shot model to get available shows from
        """
        if not shot_model:
            return

        # Use base class method
        shows = shot_model.get_available_shows()
        super().populate_show_filter(list(shows))

    @Slot()
    def _on_model_updated(self) -> None:
        """Handle model updates."""
        # Update grid layout based on new item count
        self._update_grid_size()

        # Reset visible range tracking
        self._update_visible_range()

    @Slot(QModelIndex)
    def _on_item_clicked(self, index: QModelIndex) -> None:
        """Handle item click.

        Args:
            index: Clicked model index
        """
        if not index.isValid() or not self._model:
            return

        shot: Shot | None = index.data(ShotRole.ShotObjectRole)
        if shot:
            self._selected_shot = shot

            # Update selection in model
            self._model.setData(index, True, ShotRole.IsSelectedRole)

            # Emit signal
            self.shot_selected.emit(shot)

            self.logger.debug(f"Shot selected: {shot.full_name}")

    @Slot(QModelIndex)
    def _on_item_double_clicked(self, index: QModelIndex) -> None:
        """Handle item double-click.

        Args:
            index: Double-clicked model index
        """
        if not index.isValid() or not self._model:
            return

        shot: Shot | None = index.data(ShotRole.ShotObjectRole)
        if shot:
            self.shot_double_clicked.emit(shot)
            self.logger.debug(f"Shot double-clicked: {shot.full_name}")

    @Slot(QModelIndex, QModelIndex)
    def _on_selection_changed(
        self,
        current: QModelIndex,
        previous: QModelIndex,
    ) -> None:
        """Handle selection change.

        Args:
            current: Current selection index
            previous: Previous selection index
        """
        if not self._model:
            return

        # Clear previous selection in model
        if previous.isValid():
            self._model.setData(previous, False, ShotRole.IsSelectedRole)

        # Set current selection in model
        if current.isValid():
            self._model.setData(current, True, ShotRole.IsSelectedRole)

            shot: Shot | None = current.data(ShotRole.ShotObjectRole)
            if shot:
                self._selected_shot = shot
                self.shot_selected.emit(shot)

    def _handle_visible_range_update(self, start: int, end: int) -> None:
        """Handle the visible range update for lazy loading.

        Args:
            start: Start row index
            end: End row index (exclusive)
        """
        if self._model:
            self._model.set_visible_range(start, end)

    def select_shot_by_name(self, shot_name: str) -> None:
        """Select a shot by its full name.

        Args:
            shot_name: Full shot name to select
        """
        if not self._model:
            return

        # Find the shot in the model
        for row in range(self._model.rowCount()):
            index = self._model.index(row, 0)
            shot: Shot | None = index.data(ShotRole.ShotObjectRole)

            if shot and shot.full_name == shot_name:
                # Select in view
                self.list_view.setCurrentIndex(index)

                # Ensure it's visible
                self.list_view.scrollTo(
                    index,
                    QAbstractItemView.ScrollHint.PositionAtCenter,
                )

                # Trigger selection
                self._on_item_clicked(index)
                break

    def clear_selection(self) -> None:
        """Clear the current selection."""
        if self.list_view.selectionModel():
            self.list_view.selectionModel().clear()

        self._selected_shot = None

    def refresh_view(self) -> None:
        """Force a complete view refresh."""
        self.list_view.viewport().update()
        self._update_visible_range()

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """Handle right-click context menu.

        Args:
            event: Context menu event
        """
        # Convert global position to list view coordinates
        list_view_pos = self.list_view.mapFromGlobal(event.globalPos())

        # Get the index at the clicked position
        index = self.list_view.indexAt(list_view_pos)

        if not index.isValid() or not self._model:
            # No item clicked, show no menu
            return

        shot: Shot | None = index.data(ShotRole.ShotObjectRole)
        if not shot:
            return

        # Create context menu
        menu = QMenu(self)

        # Add "Open Shot Folder" action
        open_folder_action = menu.addAction("Open Shot Folder")
        open_folder_action.triggered.connect(lambda: self._open_shot_folder(shot))

        # Show menu at cursor position
        menu.exec(event.globalPos())

        self.logger.debug(f"Context menu shown for shot: {shot.full_name}")

    def _open_shot_folder(self, shot: Shot) -> None:
        """Open the shot's workspace folder in system file manager (non-blocking).

        Args:
            shot: Shot object containing workspace path
        """
        folder_path = shot.workspace_path

        # Create worker to open folder in background
        worker = FolderOpenerWorker(folder_path)

        # Connect signals with QueuedConnection for thread safety
        worker.signals.error.connect(
            self._on_folder_open_error, Qt.ConnectionType.QueuedConnection
        )
        worker.signals.success.connect(
            self._on_folder_open_success, Qt.ConnectionType.QueuedConnection
        )

        # Start the worker
        QThreadPool.globalInstance().start(worker)

        self.logger.info(f"Opening folder: {folder_path}")

    @Slot(str)
    def _on_folder_open_error(self, error_msg: str) -> None:
        """Handle folder open error.

        Args:
            error_msg: Error message from worker
        """
        self.logger.error(f"Failed to open folder: {error_msg}")
        # Could show a QMessageBox here if desired

    @Slot()
    def _on_folder_open_success(self) -> None:
        """Handle successful folder opening."""
        self.logger.debug("Folder opened successfully")


# Example usage
if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication

    from shot_model import Shot

    app = QApplication(sys.argv)

    # Create sample data
    shots = [
        Shot("show1", "seq01", f"shot{i:04d}", f"/shows/show1/shots/seq01/shot{i:04d}")
        for i in range(100)
    ]

    # Create model and view
    model = ShotItemModel()
    model.set_shots(shots)

    view = ShotGridView(model)
    view.resize(800, 600)
    view.show()

    # Connect signals
    view.shot_selected.connect(lambda shot: print(f"Selected: {shot.full_name}"))
    view.shot_double_clicked.connect(
        lambda shot: print(f"Double-clicked: {shot.full_name}"),
    )

    sys.exit(app.exec())
