"""Base grid widget for displaying thumbnails in a grid layout.

This abstract base class provides common functionality for all grid widgets
in the application, reducing code duplication across shot_grid, threede_shot_grid,
and previous_shots_grid.
"""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Generic, TypeVar

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from config import Config

if TYPE_CHECKING:
    from PySide6.QtGui import QKeyEvent, QResizeEvent, QWheelEvent

# Generic type for the items displayed in the grid
T = TypeVar("T")


# Create a metaclass that combines Qt's metaclass with ABCMeta
class BaseGridMeta(type(QWidget), ABCMeta):
    """Metaclass that combines Qt's metaclass with ABCMeta for abstract base classes."""

    pass


class BaseGridWidget(QWidget, Generic[T], metaclass=BaseGridMeta):
    """Abstract base class for grid widgets displaying thumbnails.

    This class provides common functionality for:
    - Thumbnail size control with slider
    - Grid layout management and reflow
    - Keyboard navigation (arrow keys, home/end, shortcuts)
    - Mouse wheel zoom with Ctrl
    - Responsive column calculation

    Subclasses must implement:
    - _create_thumbnail_widget(): Create thumbnail widgets for items
    - _get_item_key(): Get unique key for an item
    - _get_items(): Get list of items to display
    - _handle_item_selected(): Handle item selection
    - _handle_item_double_clicked(): Handle item double-click
    """

    # Common signals - subclasses can add more specific ones
    app_launch_requested = Signal(str)  # app_name

    def __init__(self, parent: QWidget | None = None):
        """Initialize the base grid widget.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self.thumbnails: dict[str, QWidget] = {}
        self.selected_item: T | None = None
        self._thumbnail_size = Config.DEFAULT_THUMBNAIL_SIZE

        self._setup_base_ui()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _setup_base_ui(self) -> None:
        """Set up the base UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Add header section (can be extended by subclasses)
        header_widget = self._create_header()
        if header_widget:
            layout.addWidget(header_widget)

        # Size control
        size_layout = self._create_size_control()
        layout.addLayout(size_layout)

        # Add any additional controls from subclasses
        extra_controls = self._create_extra_controls()
        if extra_controls:
            layout.addWidget(extra_controls)

        # Scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )

        # Container widget
        self.container = QWidget()
        self.grid_layout = QGridLayout(self.container)
        self.grid_layout.setSpacing(Config.THUMBNAIL_SPACING)

        self.scroll_area.setWidget(self.container)
        layout.addWidget(self.scroll_area)

    def _create_header(self) -> QWidget | None:
        """Create optional header widget. Override in subclasses if needed.

        Returns:
            Header widget or None.
        """
        return None

    def _create_size_control(self) -> QHBoxLayout:
        """Create the thumbnail size control layout.

        Returns:
            Layout containing size controls.
        """
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

        return size_layout

    def _create_extra_controls(self) -> QWidget | None:
        """Create additional controls. Override in subclasses if needed.

        Returns:
            Extra controls widget or None.
        """
        return None

    @property
    def thumbnail_size(self) -> int:
        """Get the current thumbnail size.

        Returns:
            Current thumbnail size in pixels.
        """
        return self._thumbnail_size

    def refresh_display(self) -> None:
        """Refresh the display with current items."""
        # Clear existing thumbnails
        self._clear_grid()

        # Get items from subclass
        items = self._get_items()

        if not items:
            self._show_empty_state()
            return

        # Create thumbnails for all items
        for i, item in enumerate(items):
            thumbnail = self._create_thumbnail_widget(item)
            self._connect_thumbnail_signals(thumbnail, item)

            key = self._get_item_key(item)
            self.thumbnails[key] = thumbnail

            # Add to grid
            row = i // self._get_column_count()
            col = i % self._get_column_count()
            self.grid_layout.addWidget(thumbnail, row, col)

    def _clear_grid(self) -> None:
        """Clear all thumbnails from grid."""
        for thumbnail in self.thumbnails.values():
            self.grid_layout.removeWidget(thumbnail)
            thumbnail.deleteLater()
        self.thumbnails.clear()

    def _get_column_count(self) -> int:
        """Calculate number of columns based on width.

        Returns:
            Number of columns for the grid.
        """
        available_width = self.scroll_area.viewport().width()
        if available_width <= 0:
            return Config.GRID_COLUMNS

        # Calculate based on thumbnail size and spacing
        item_width = self._thumbnail_size + Config.THUMBNAIL_SPACING
        columns = max(1, available_width // item_width)
        return columns

    def _reflow_grid(self) -> None:
        """Reflow grid layout based on new size."""
        if not self.thumbnails:
            return

        # Remove all widgets
        for widget in self.thumbnails.values():
            self.grid_layout.removeWidget(widget)

        # Re-add in new positions
        items = self._get_items()
        for i, item in enumerate(items):
            key = self._get_item_key(item)
            if key in self.thumbnails:
                thumbnail = self.thumbnails[key]
                row = i // self._get_column_count()
                col = i % self._get_column_count()
                self.grid_layout.addWidget(thumbnail, row, col)

    def _on_size_changed(self, value: int) -> None:
        """Handle thumbnail size change.

        Args:
            value: New thumbnail size.
        """
        self._thumbnail_size = value
        self.size_label.setText(f"{value}px")

        # Update all thumbnails
        for item in self._get_items():
            key = self._get_item_key(item)
            if key in self.thumbnails:
                self._update_thumbnail_size(self.thumbnails[key], value)

        # Reflow grid
        self._reflow_grid()

    @abstractmethod
    def _connect_thumbnail_signals(self, thumbnail: QWidget, item: T) -> None:
        """Connect thumbnail widget signals.

        Args:
            thumbnail: Thumbnail widget.
            item: Associated item.
        """
        pass

    def _on_item_clicked(self, item: T) -> None:
        """Handle item click.

        Args:
            item: Clicked item.
        """
        # Update selection
        if self.selected_item:
            old_key = self._get_item_key(self.selected_item)
            if old_key in self.thumbnails:
                self._set_thumbnail_selected(self.thumbnails[old_key], False)

        self.selected_item = item
        key = self._get_item_key(item)
        if key in self.thumbnails:
            self._set_thumbnail_selected(self.thumbnails[key], True)

        # Call subclass handler
        self._handle_item_selected(item)

    def _on_item_double_clicked(self, item: T) -> None:
        """Handle item double click.

        Args:
            item: Double-clicked item.
        """
        self._handle_item_double_clicked(item)

    def select_item(self, item: T) -> None:
        """Select an item programmatically.

        Args:
            item: Item to select.
        """
        self._on_item_clicked(item)

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Handle resize to reflow grid.

        Args:
            event: Resize event.
        """
        super().resizeEvent(event)
        self._reflow_grid()

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Handle wheel event for thumbnail size adjustment with Ctrl.

        Args:
            event: Wheel event.
        """
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                new_size = min(self._thumbnail_size + 10, Config.MAX_THUMBNAIL_SIZE)
            else:
                new_size = max(self._thumbnail_size - 10, Config.MIN_THUMBNAIL_SIZE)

            self.size_slider.setValue(new_size)
            event.accept()
        else:
            super().wheelEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle keyboard navigation.

        Args:
            event: Key press event.
        """
        items = self._get_items()
        if not items:
            super().keyPressEvent(event)
            return

        # Get current selection index
        current_index = -1
        if self.selected_item:
            selected_key = self._get_item_key(self.selected_item)
            for i, item in enumerate(items):
                if self._get_item_key(item) == selected_key:
                    current_index = i
                    break

        # Calculate grid dimensions
        columns = self._get_column_count()
        total_items = len(items)

        new_index = current_index

        # Handle arrow keys
        if event.key() == Qt.Key.Key_Right:
            new_index = (
                min(current_index + 1, total_items - 1) if current_index >= 0 else 0
            )
        elif event.key() == Qt.Key.Key_Left:
            new_index = max(current_index - 1, 0) if current_index >= 0 else 0
        elif event.key() == Qt.Key.Key_Down:
            if current_index >= 0:
                new_index = min(current_index + columns, total_items - 1)
            else:
                new_index = 0
        elif event.key() == Qt.Key.Key_Up:
            if current_index >= 0:
                new_index = max(current_index - columns, 0)
            else:
                new_index = 0
        elif event.key() == Qt.Key.Key_Home:
            new_index = 0
        elif event.key() == Qt.Key.Key_End:
            new_index = total_items - 1
        elif event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            # Double-click on current selection
            if self.selected_item:
                self._handle_item_double_clicked(self.selected_item)
            event.accept()
            return
        # Application launch shortcuts
        elif event.key() == Qt.Key.Key_3:
            if self.selected_item:
                self.app_launch_requested.emit("3de")
            event.accept()
            return
        elif event.key() == Qt.Key.Key_N:
            if self.selected_item:
                self.app_launch_requested.emit("nuke")
            event.accept()
            return
        elif event.key() == Qt.Key.Key_M:
            if self.selected_item:
                self.app_launch_requested.emit("maya")
            event.accept()
            return
        elif event.key() == Qt.Key.Key_R:
            if self.selected_item:
                self.app_launch_requested.emit("rv")
            event.accept()
            return
        elif event.key() == Qt.Key.Key_P:
            if self.selected_item:
                self.app_launch_requested.emit("publish")
            event.accept()
            return
        else:
            # Let subclasses handle additional keys
            if not self._handle_extra_keys(event):
                super().keyPressEvent(event)
            return

        # Select new item if index changed
        if new_index != current_index and 0 <= new_index < total_items:
            new_item = items[new_index]
            self.select_item(new_item)

            # Ensure the selected thumbnail is visible
            key = self._get_item_key(new_item)
            if key in self.thumbnails:
                thumbnail = self.thumbnails[key]
                self.scroll_area.ensureWidgetVisible(thumbnail)

        event.accept()

    def _handle_extra_keys(self, event: QKeyEvent) -> bool:
        """Handle additional keyboard shortcuts. Override in subclasses.

        Args:
            event: Key press event.

        Returns:
            True if event was handled, False otherwise.
        """
        return False

    # Abstract methods that subclasses must implement

    @abstractmethod
    def _create_thumbnail_widget(self, item: T) -> QWidget:
        """Create a thumbnail widget for an item.

        Args:
            item: Item to create thumbnail for.

        Returns:
            Thumbnail widget.
        """
        pass

    @abstractmethod
    def _get_item_key(self, item: T) -> str:
        """Get a unique key for an item.

        Args:
            item: Item to get key for.

        Returns:
            Unique string key.
        """
        pass

    @abstractmethod
    def _get_items(self) -> list[T]:
        """Get list of items to display.

        Returns:
            List of items.
        """
        pass

    @abstractmethod
    def _handle_item_selected(self, item: T) -> None:
        """Handle item selection. Emit appropriate signals.

        Args:
            item: Selected item.
        """
        pass

    @abstractmethod
    def _handle_item_double_clicked(self, item: T) -> None:
        """Handle item double-click. Emit appropriate signals.

        Args:
            item: Double-clicked item.
        """
        pass

    @abstractmethod
    def _update_thumbnail_size(self, thumbnail: QWidget, size: int) -> None:
        """Update thumbnail widget size.

        Args:
            thumbnail: Thumbnail widget to update.
            size: New size in pixels.
        """
        pass

    @abstractmethod
    def _set_thumbnail_selected(self, thumbnail: QWidget, selected: bool) -> None:
        """Set thumbnail selection state.

        Args:
            thumbnail: Thumbnail widget.
            selected: Whether thumbnail is selected.
        """
        pass

    def _show_empty_state(self) -> None:
        """Show empty state. Override in subclasses for custom empty states."""
        # Default implementation - subclasses can override
        empty_label = QLabel("No items to display")
        empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_label.setStyleSheet("color: #888; font-size: 14px; padding: 40px;")
        self.grid_layout.addWidget(empty_label, 0, 0)
