"""Grid widget for displaying previous/approved shots."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from base_grid_widget import BaseGridWidget
from cache_manager import CacheManager
from progress_manager import ProgressManager
from shot_model import Shot
from thumbnail_widget import ThumbnailWidget

if TYPE_CHECKING:
    from previous_shots_model import PreviousShotsModel

logger = logging.getLogger(__name__)


class PreviousShotsGrid(BaseGridWidget["Shot"]):
    """Grid widget for displaying approved shots with thumbnails.

    This widget displays shots that the user has worked on but are
    no longer active (i.e., approved/completed shots).
    Extends BaseGridWidget with refresh functionality and progress tracking.
    """

    # Signals
    shot_selected = Signal(Shot)
    shot_double_clicked = Signal(Shot)

    def __init__(
        self,
        previous_shots_model: PreviousShotsModel,
        cache_manager: CacheManager | None = None,
        parent: QWidget | None = None,
    ):
        """Initialize the previous shots grid.

        Args:
            previous_shots_model: Model containing approved shots data.
            cache_manager: Optional cache manager for thumbnails.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._model = previous_shots_model
        self._cache_manager = cache_manager or CacheManager()

        # PERFORMANCE: Resize debouncing timer
        self._resize_timer = QTimer()
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._do_resize)
        self._resize_timer.setInterval(100)  # 100ms debounce
        self._pending_size: QSize | None = None

        self._connect_signals()

        # Initial population
        self.refresh_display()

        logger.info("PreviousShotsGrid initialized")

    def _create_header(self) -> QWidget | None:
        """Create header with refresh button and status label.

        Returns:
            Header widget.
        """
        widget = QWidget()
        header_layout = QHBoxLayout(widget)
        header_layout.setContentsMargins(0, 0, 0, 5)

        # Status label
        self._status_label = QLabel("Approved Shots")
        self._status_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        header_layout.addWidget(self._status_label)

        header_layout.addStretch()

        # Refresh button
        self._refresh_button = QPushButton("Refresh")
        self._refresh_button.clicked.connect(self._on_refresh_clicked)
        header_layout.addWidget(self._refresh_button)

        return widget

    def _connect_signals(self) -> None:
        """Connect model signals to grid updates."""
        self._model.shots_updated.connect(self.refresh_display)
        self._model.scan_started.connect(self._on_scan_started)
        self._model.scan_finished.connect(self._on_scan_finished)
        self._model.scan_progress.connect(self._on_scan_progress)

    @Slot()
    def _on_refresh_clicked(self) -> None:
        """Handle refresh button click."""
        logger.debug("Refresh button clicked")
        self._refresh_button.setEnabled(False)
        self._refresh_button.setText("Scanning...")
        self._model.refresh_shots()

    @Slot()
    def _on_scan_started(self) -> None:
        """Handle scan start."""
        self._refresh_button.setEnabled(False)
        self._refresh_button.setText("Scanning...")
        self._status_label.setText("Scanning for approved shots...")

        # Start progress operation for previous shots scan
        ProgressManager.start_operation("Scanning for previous shots")

    @Slot()
    def _on_scan_finished(self) -> None:
        """Handle scan completion."""
        # Finish progress operation
        ProgressManager.finish_operation(success=True)

        # Reset UI state
        self._refresh_button.setEnabled(True)
        self._refresh_button.setText("Refresh")
        shot_count = self._model.get_shot_count()
        self._status_label.setText(f"Approved Shots ({shot_count})")

    @Slot(int, int)
    def _on_scan_progress(self, current: int, total: int) -> None:
        """Handle scan progress updates.

        Args:
            current: Current progress value.
            total: Total progress value.
        """
        if total > 0:
            percent = int((current / total) * 100)
            self._status_label.setText(f"Scanning... {percent}%")

    def get_selected_shot(self) -> Shot | None:
        """Get the currently selected shot.

        Returns:
            Selected Shot object or None.
        """
        return self.selected_item

    def refresh(self) -> None:
        """Refresh the grid display."""
        self._model.refresh_shots()

    def resizeEvent(self, event) -> None:
        """Handle resize events to reflow grid with debouncing.

        Args:
            event: Resize event.
        """
        super().resizeEvent(event)

        # PERFORMANCE: Debounce resize to prevent excessive grid recreation
        if self._model.get_shot_count() > 0:
            self._pending_size = event.size()
            self._resize_timer.stop()  # Cancel any pending resize
            self._resize_timer.start()  # Start new timer

    @Slot()
    def _do_resize(self) -> None:
        """Perform the actual resize after debounce timer expires."""
        if self._pending_size:
            self._reflow_grid()
            self._pending_size = None
            logger.debug("Grid resized and repopulated after debounce")

    # Implement abstract methods from BaseGridWidget

    def _create_thumbnail_widget(self, item: Shot) -> QWidget:
        """Create a thumbnail widget for a shot.

        Args:
            item: Shot to create thumbnail for.

        Returns:
            ThumbnailWidget instance.
        """
        thumbnail = ThumbnailWidget(item, self.thumbnail_size)

        # Set the cache manager for the widget class if needed
        if self._cache_manager:
            ThumbnailWidget.set_cache_manager(self._cache_manager)

        # Set approved shot styling
        thumbnail.setStyleSheet("""
            ThumbnailWidget {
                border: 2px solid #4a90e2;
                border-radius: 5px;
                background-color: #f0f8ff;
            }
            ThumbnailWidget:hover {
                border: 2px solid #2e7cd6;
                background-color: #e6f3ff;
            }
        """)

        return thumbnail

    def _get_item_key(self, item: Shot) -> str:
        """Get unique key for a shot.

        Args:
            item: Shot to get key for.

        Returns:
            Shot's name as key.
        """
        return item.shot

    def _get_items(self) -> list[Shot]:
        """Get list of shots to display.

        Returns:
            List of shots from the model.
        """
        shots = self._model.get_shots()

        # Update status when getting items
        if hasattr(self, "_status_label"):
            self._status_label.setText(f"Approved Shots ({len(shots)})")

        return shots

    def _handle_item_selected(self, item: Shot) -> None:
        """Handle shot selection.

        Args:
            item: Selected shot.
        """
        self.shot_selected.emit(item)
        logger.debug(f"Selected approved shot: {item.shot}")

    def _handle_item_double_clicked(self, item: Shot) -> None:
        """Handle shot double-click.

        Args:
            item: Double-clicked shot.
        """
        self.shot_double_clicked.emit(item)
        logger.debug(f"Double-clicked approved shot: {item.shot}")

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

    def _show_empty_state(self) -> None:
        """Show custom empty state for approved shots."""
        empty_label = QLabel(
            "No approved shots found.\n"
            "Approved shots you've worked on will appear here."
        )
        empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_label.setStyleSheet("color: gray; font-style: italic;")
        self.grid_layout.addWidget(empty_label, 0, 0)
