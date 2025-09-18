"""Optimized grid view for 3DE scene thumbnails using Qt Model/View architecture.

This module provides a QListView-based implementation that replaces the manual
widget management approach, providing virtualization, efficient scrolling,
loading indicators, and proper Model/View integration for 3DE scenes.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import (
    QModelIndex,
    QMutex,
    QMutexLocker,
    QPoint,
    QSize,
    Qt,
    QThreadPool,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListView,
    QMenu,
    QProgressBar,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from config import Config
from logging_mixin import LoggingMixin
from qt_widget_mixin import QtWidgetMixin
from threede_grid_delegate_refactored import ThreeDEGridDelegate
from thumbnail_widget_base import FolderOpenerWorker

if TYPE_CHECKING:
    from PySide6.QtGui import QKeyEvent

    from threede_item_model import ThreeDEItemModel
    from threede_scene_model import ThreeDEScene, ThreeDESceneModel

logger = logging.getLogger(__name__)

# Thread-safe logging mutex to prevent recursion issues in VFX environments
_log_mutex = QMutex()
_log_recursion_depth = 0
_max_log_recursion = 3


def safe_log_info(message: str) -> None:
    """Thread-safe logging wrapper to prevent RecursionError in logging system.

    This addresses a known issue in Qt/PySide6 applications where Python's
    logging formatter can enter infinite recursion in the usesTime() method.

    Args:
        message: Log message to output safely
    """
    global _log_recursion_depth

    # Guard against deep recursion
    if _log_recursion_depth >= _max_log_recursion:
        # Write directly to stderr to avoid any further recursion
        try:
            os.write(2, f"[RECURSION GUARD] {message}\n".encode())
        except Exception:
            pass
        return

    _log_recursion_depth += 1
    try:
        with QMutexLocker(_log_mutex):
            logger.info(message)
    except RecursionError:
        # Fallback: write directly to stderr
        try:
            os.write(2, f"[RECURSION ERROR] {message}\n".encode())
        except Exception:
            pass
    except Exception:
        # Fallback: silent failure to prevent crashes
        pass
    finally:
        _log_recursion_depth -= 1


class ThreeDEGridView(QtWidgetMixin, LoggingMixin, QWidget):
    """Optimized grid view for displaying 3DE scene thumbnails.

    This view provides:
    - Virtualization (only renders visible items)
    - Efficient scrolling for large datasets
    - Lazy loading of thumbnails
    - Loading progress indicators
    - User filtering support
    - Proper Model/View integration
    - Dynamic grid layout based on window size
    """

    # Signals
    scene_selected = Signal(object)  # ThreeDEScene object
    scene_double_clicked = Signal(object)  # ThreeDEScene object
    app_launch_requested = Signal(str, object)  # app_name, scene
    show_filter_requested = Signal(str)  # show name or None for all

    def __init__(
        self,
        model: ThreeDEItemModel | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the 3DE grid view.

        Args:
            model: Optional 3DE item model
            parent: Optional parent widget
        """
        super().__init__(parent)

        self._model = model
        self._thumbnail_size = Config.DEFAULT_THUMBNAIL_SIZE
        self._selected_scene = None
        self._is_loading = False
        self._updating_filter = False  # Recursion guard for filter updates

        self._setup_ui()

        if model:
            self.set_model(model)

        # Visibility tracking timer for lazy loading
        self._visibility_timer = QTimer()
        self._visibility_timer.timeout.connect(self._update_visible_range)
        self._visibility_timer.setInterval(100)
        self._visibility_timer.start()

        safe_log_info("ThreeDEGridView initialized with Model/View architecture")

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Loading indicators
        loading_layout = QVBoxLayout()
        loading_layout.setSpacing(2)

        # Progress bar
        self.loading_bar = QProgressBar()
        self.loading_bar.setVisible(False)
        self.loading_bar.setMaximum(100)
        self.loading_bar.setTextVisible(True)
        loading_layout.addWidget(self.loading_bar)

        # Loading label
        self.loading_label = QLabel("")
        self.loading_label.setVisible(False)
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading_layout.addWidget(self.loading_label)

        layout.addLayout(loading_layout)

        # Show filter combo box
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Show:"))

        self.show_combo = QComboBox()
        self.show_combo.addItem("All Shows")
        self.show_combo.currentTextChanged.connect(self._on_show_filter_changed)
        filter_layout.addWidget(self.show_combo)

        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # Size control slider
        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel("Thumbnail Size:"))

        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setMinimum(Config.MIN_THUMBNAIL_SIZE)
        self.size_slider.setMaximum(Config.MAX_THUMBNAIL_SIZE)
        self.size_slider.setValue(self._thumbnail_size)
        self.size_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.size_slider.setTickInterval(50)
        self.size_slider.valueChanged.connect(self._on_size_changed)
        size_layout.addWidget(self.size_slider)

        self.size_label = QLabel(f"{self._thumbnail_size}px")
        self.size_label.setMinimumWidth(50)
        size_layout.addWidget(self.size_label)

        # Scene count label
        size_layout.addStretch()
        self.count_label = QLabel("0 scenes")
        size_layout.addWidget(self.count_label)

        layout.addLayout(size_layout)

        # Create QListView with grid mode
        self.list_view = QListView()
        self.list_view.setViewMode(QListView.ViewMode.IconMode)
        self.list_view.setResizeMode(QListView.ResizeMode.Adjust)
        self.list_view.setLayoutMode(QListView.LayoutMode.Batched)
        self.list_view.setBatchSize(20)  # Process 20 items at a time
        self.list_view.setUniformItemSizes(True)  # Optimization for equal-sized items
        self.list_view.setSpacing(Config.THUMBNAIL_SPACING)

        # Set selection behavior
        self.list_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_view.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectItems,
        )

        # Enable smooth scrolling
        self.list_view.setVerticalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel,
        )
        self.list_view.setHorizontalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel,
        )

        # Create and set custom delegate
        self._delegate = ThreeDEGridDelegate(self)
        self.list_view.setItemDelegate(self._delegate)

        # Connect signals
        self.list_view.clicked.connect(self._on_item_clicked)
        self.list_view.doubleClicked.connect(self._on_item_double_clicked)

        layout.addWidget(self.list_view)

        # Enable keyboard focus
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.list_view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Enable context menu
        self.list_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_view.customContextMenuRequested.connect(self._show_context_menu)

    def set_model(self, model: ThreeDEItemModel) -> None:
        """Set the item model.

        Args:
            model: ThreeDEItemModel instance
        """
        self._model = model
        self.list_view.setModel(model)

        # Connect model signals
        model.scenes_updated.connect(self._on_scenes_updated)
        model.thumbnail_loaded.connect(self._on_thumbnail_loaded)
        model.loading_started.connect(self._on_loading_started)
        model.loading_progress.connect(self._on_loading_progress)
        model.loading_finished.connect(self._on_loading_finished)

        # Update grid size based on thumbnail size
        self._update_grid_size()

        # Update scene count
        self._update_scene_count()

    def populate_show_filter(self, threede_scene_model: ThreeDESceneModel) -> None:
        """Populate the show filter combo box with available shows.

        Args:
            threede_scene_model: The scene model to get shows from
        """
        # Guard against recursion
        if self._updating_filter:
            return

        self._updating_filter = True
        try:
            # Save current selection
            current_text = self.show_combo.currentText()

            # Temporarily disconnect signal to prevent recursion
            try:
                self.show_combo.currentTextChanged.disconnect()
            except RuntimeError:
                pass  # No connections to disconnect

            # Clear and repopulate
            self.show_combo.clear()
            self.show_combo.addItem("All Shows")

            unique_shows = threede_scene_model.get_unique_shows()
            for show in unique_shows:
                self.show_combo.addItem(show)

            # Restore selection if possible
            index = self.show_combo.findText(current_text)
            if index >= 0:
                self.show_combo.setCurrentIndex(index)
            else:
                self.show_combo.setCurrentIndex(0)  # Default to "All Shows"

            # Reconnect signal
            self.show_combo.currentTextChanged.connect(self._on_show_filter_changed)
        finally:
            self._updating_filter = False

        safe_log_info(f"Populated show filter with {len(unique_shows)} shows")

    @Slot()
    def _on_scenes_updated(self) -> None:
        """Handle scenes updated signal."""
        self._update_scene_count()
        self.list_view.viewport().update()

    @Slot(int)
    def _on_thumbnail_loaded(self, row: int) -> None:
        """Handle thumbnail loaded signal.

        Args:
            row: Row index of loaded thumbnail
        """
        # Update the specific item
        if self._model:
            index = self._model.index(row, 0)
            self.list_view.update(index)

    @Slot()
    def _on_loading_started(self) -> None:
        """Handle loading started signal."""
        self._is_loading = True
        self.loading_bar.setVisible(True)
        self.loading_label.setVisible(True)
        self.loading_label.setText("Scanning for 3DE scenes...")
        self.loading_bar.setValue(0)

    @Slot(int, int)
    def _on_loading_progress(self, current: int, total: int) -> None:
        """Handle loading progress signal.

        Args:
            current: Current item being loaded
            total: Total items to load
        """
        if total > 0:
            progress = int((current / total) * 100)
            self.loading_bar.setValue(progress)
            self.loading_label.setText(f"Found {current} scenes...")

    @Slot()
    def _on_loading_finished(self) -> None:
        """Handle loading finished signal."""
        self._is_loading = False
        self.loading_bar.setVisible(False)
        self.loading_label.setVisible(False)
        self._update_scene_count()

    def _update_scene_count(self) -> None:
        """Update the scene count label."""
        if self._model:
            count = self._model.rowCount()
            self.count_label.setText(f"{count} scene{'s' if count != 1 else ''}")

    @Slot(QModelIndex)
    def _on_item_clicked(self, index: QModelIndex) -> None:
        """Handle item click.

        Args:
            index: Clicked model index
        """
        if not self._model:
            return

        scene = self._model.get_scene(index)
        if scene:
            self._selected_scene = scene
            self._model.set_selected(index)
            self.scene_selected.emit(scene)

    @Slot(QModelIndex)
    def _on_item_double_clicked(self, index: QModelIndex) -> None:
        """Handle item double-click.

        Args:
            index: Double-clicked model index
        """
        if not self._model:
            return

        scene = self._model.get_scene(index)
        if scene:
            self.scene_double_clicked.emit(scene)
            # Launch 3DE by default
            self.app_launch_requested.emit("3de", scene)

    @Slot(int)
    def _on_size_changed(self, value: int) -> None:
        """Handle thumbnail size change.

        Args:
            value: New size value
        """
        self._thumbnail_size = value
        self.size_label.setText(f"{value}px")

        # Update delegate
        self._delegate.set_thumbnail_size(value)

        # Update grid size
        self._update_grid_size()

        # Trigger view update
        self.list_view.viewport().update()

    @Slot(str)
    def _on_show_filter_changed(self, show_text: str) -> None:
        """Handle show filter change.

        Args:
            show_text: Selected show text from combo box
        """
        # Guard against recursion
        if self._updating_filter:
            return

        self._updating_filter = True
        try:
            # Convert "All Shows" to None for the model
            show_filter = None if show_text == "All Shows" else show_text
            self.show_filter_requested.emit(
                show_filter or ""
            )  # Emit empty string for None
            safe_log_info(f"Show filter requested: {show_text}")
        finally:
            self._updating_filter = False

    def _update_grid_size(self) -> None:
        """Update the grid size based on thumbnail size."""
        # Calculate item size including padding and text
        item_size = self._thumbnail_size + 16 + 50  # padding + text height
        grid_size = QSize(self._thumbnail_size + 16, item_size)

        self.list_view.setGridSize(grid_size)

    @Slot()
    def _update_visible_range(self) -> None:
        """Update visible range for lazy loading."""
        if not self._model:
            return

        # Get visible rect
        visible_rect = self.list_view.viewport().rect()

        # Get first and last visible items
        top_left = self.list_view.indexAt(visible_rect.topLeft())
        bottom_right = self.list_view.indexAt(visible_rect.bottomRight())

        if top_left.isValid() and bottom_right.isValid():
            # Add some buffer for smooth scrolling
            start = max(0, top_left.row() - 5)
            end = min(self._model.rowCount() - 1, bottom_right.row() + 5)

            # Update model's visible range
            self._model.set_visible_range(start, end)

    def _show_context_menu(self, pos: QPoint) -> None:
        """Show context menu at position.

        Args:
            pos: Context menu position
        """
        index = self.list_view.indexAt(pos)
        if not index.isValid() or not self._model:
            return

        scene = self._model.get_scene(index)
        if not scene:
            return

        menu = QMenu(self)

        # Add "Open in 3DE" action
        open_3de_action = menu.addAction("Open in 3DE")
        open_3de_action.triggered.connect(lambda: self._open_scene_in_3de(scene))

        # Add "Open folder" action
        open_folder_action = menu.addAction("Open Folder")
        open_folder_action.triggered.connect(lambda: self._open_scene_folder(scene))

        # Add separator
        menu.addSeparator()

        # Add "Copy path" action
        copy_path_action = menu.addAction("Copy Path")
        copy_path_action.triggered.connect(lambda: self._copy_scene_path(scene))

        menu.exec(self.list_view.mapToGlobal(pos))

    def _open_scene_in_3de(self, scene: ThreeDEScene) -> None:
        """Open scene in 3DE.

        Args:
            scene: Scene to open
        """
        self.app_launch_requested.emit("3de", scene)

    def _open_scene_folder(self, scene: ThreeDEScene) -> None:
        """Open scene folder in file manager.

        Args:
            scene: Scene whose folder to open
        """
        scene_path = Path(scene.scene_path)
        if scene_path.exists():
            folder_path = str(scene_path.parent)
            worker = FolderOpenerWorker(folder_path)
            QThreadPool.globalInstance().start(worker)

    def _copy_scene_path(self, scene: ThreeDEScene) -> None:
        """Copy scene path to clipboard.

        Args:
            scene: Scene whose path to copy
        """
        from PySide6.QtWidgets import QApplication

        clipboard = QApplication.clipboard()
        clipboard.setText(str(scene.scene_path))
        safe_log_info(f"Copied path to clipboard: {scene.scene_path}")

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle key press events.

        Args:
            event: Key press event
        """
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            # Launch selected scene
            current = self.list_view.currentIndex()
            if current.isValid() and self._model:
                scene = self._model.get_scene(current)
                if scene:
                    self.scene_double_clicked.emit(scene)
                    self.app_launch_requested.emit("3de", scene)
        else:
            super().keyPressEvent(event)

    def select_scene(self, scene: ThreeDEScene) -> None:
        """Select a scene programmatically.

        Args:
            scene: Scene to select
        """
        if not self._model:
            return

        # Find scene in model
        for row in range(self._model.rowCount()):
            index = self._model.index(row, 0)
            model_scene = self._model.get_scene(index)
            if model_scene and model_scene.full_name == scene.full_name:
                self.list_view.setCurrentIndex(index)
                self._model.set_selected(index)
                self._selected_scene = scene
                self.scene_selected.emit(scene)
                break

    @property
    def selected_scene(self) -> ThreeDEScene | None:
        """Get the currently selected scene."""
        return self._selected_scene

    @property
    def is_loading(self) -> bool:
        """Check if loading is in progress."""
        return self._is_loading
