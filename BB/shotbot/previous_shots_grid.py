"""Grid widget for displaying previous/approved shots."""

from __future__ import annotations

import logging

from PySide6.QtCore import QSize, Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from cache_manager import CacheManager
from config import Config
from previous_shots_model import PreviousShotsModel
from progress_manager import ProgressManager
from shot_model import Shot
from thumbnail_widget import ThumbnailWidget

logger = logging.getLogger(__name__)


class PreviousShotsGrid(QWidget):
    """Grid widget for displaying approved shots with thumbnails.

    This widget displays shots that the user has worked on but are
    no longer active (i.e., approved/completed shots).
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
        self._thumbnail_widgets: dict[str, ThumbnailWidget] = {}
        self._selected_shot: Shot | None = None
        self._thumbnail_size = Config.DEFAULT_THUMBNAIL_SIZE  # type: ignore[attr-defined]

        # PERFORMANCE: Resize debouncing timer
        self._resize_timer = QTimer()
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._do_resize)
        self._resize_timer.setInterval(100)  # 100ms debounce
        self._pending_size: QSize | None = None

        self._setup_ui()
        self._connect_signals()

        # Initial population
        self._populate_grid()

        logger.info("PreviousShotsGrid initialized")

    @property
    def thumbnail_size(self) -> int:
        """Get the current thumbnail size.

        Returns:
            Current thumbnail size in pixels
        """
        return self._thumbnail_size  # type: ignore[attr-defined]

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        layout = QVBoxLayout(self)

        # Header with refresh button and status
        header_layout = QHBoxLayout()

        # Status label
        self._status_label = QLabel("Approved Shots")
        self._status_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        header_layout.addWidget(self._status_label)

        header_layout.addStretch()

        # Refresh button
        self._refresh_button = QPushButton("Refresh")
        self._refresh_button.clicked.connect(self._on_refresh_clicked)
        header_layout.addWidget(self._refresh_button)

        layout.addLayout(header_layout)

        # Scroll area for grid
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

        # Grid widget
        self._grid_widget = QWidget()
        self._grid_layout = QGridLayout(self._grid_widget)
        self._grid_layout.setSpacing(10)

        scroll_area.setWidget(self._grid_widget)
        layout.addWidget(scroll_area)

        # Info label for empty state
        self._empty_label = QLabel(
            "No approved shots found.\n"
            "Approved shots you've worked on will appear here."
        )
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("color: gray; font-style: italic;")
        self._empty_label.hide()
        layout.addWidget(self._empty_label)

    def _connect_signals(self) -> None:
        """Connect model signals to grid updates."""
        self._model.shots_updated.connect(self._populate_grid)
        self._model.scan_started.connect(self._on_scan_started)
        self._model.scan_finished.connect(self._on_scan_finished)
        self._model.scan_progress.connect(self._on_scan_progress)

    @Slot(int, int, str)
    def _on_scan_progress(self, current: int, total: int, operation: str) -> None:
        """Handle scan progress updates.

        Args:
            current: Current progress value
            total: Total progress value
            operation: Current operation description
        """
        # Update progress operation if active
        operation_obj = ProgressManager.get_current_operation()
        if operation_obj:
            operation_obj.set_total(total)
            operation_obj.update(current, operation)

        # Update status label
        self._status_label.setText(f"Scanning: {operation}")

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
        """Handle scan completion."""
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

    @Slot()
    def _populate_grid(self) -> None:
        """Populate the grid with approved shots."""
        # Clear existing widgets
        self._clear_grid()

        # Get shots from model
        shots = self._model.get_shots()

        if not shots:
            self._empty_label.show()
            self._grid_widget.hide()
            return

        self._empty_label.hide()
        self._grid_widget.show()

        # Calculate grid dimensions
        columns = max(1, self.width() // (self._thumbnail_size + 20))  # type: ignore[attr-defined]

        # Add thumbnails to grid
        for index, shot in enumerate(shots):
            row = index // columns
            col = index % columns

            # Create thumbnail widget
            thumbnail = self._create_thumbnail_widget(shot)
            self._grid_layout.addWidget(thumbnail, row, col)
            self._thumbnail_widgets[shot.shot] = thumbnail

        # Update status
        self._status_label.setText(f"Approved Shots ({len(shots)})")

        logger.info(f"Populated grid with {len(shots)} approved shots")

    def _create_thumbnail_widget(self, shot: Shot) -> ThumbnailWidget:
        """Create a thumbnail widget for a shot.

        Args:
            shot: Shot to create thumbnail for.

        Returns:
            ThumbnailWidget instance.
        """
        # FIX: ThumbnailWidget takes (shot, size) not (shot, cache_manager)
        thumbnail = ThumbnailWidget(shot, self._thumbnail_size)  # type: ignore[attr-defined]

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

        # Connect signals (ThumbnailWidget uses 'clicked' and 'double_clicked')
        thumbnail.clicked.connect(self._on_shot_selected)
        thumbnail.double_clicked.connect(self._on_shot_double_clicked)

        # Add approved indicator if method exists
        if hasattr(thumbnail, "set_status_text"):
            thumbnail.set_status_text("APPROVED")

        return thumbnail

    def _clear_grid(self) -> None:
        """Clear all widgets from the grid."""
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._thumbnail_widgets.clear()
        self._selected_shot = None

    @Slot(object)
    def _on_shot_selected(self, shot: Shot) -> None:
        """Handle shot selection.

        Args:
            shot: Selected shot.
        """
        # Update selection state
        self._selected_shot = shot

        # Update visual selection
        for shot_name, widget in self._thumbnail_widgets.items():
            widget.set_selected(shot_name == shot.shot)

        # Emit signal
        self.shot_selected.emit(shot)

        logger.debug(f"Selected approved shot: {shot.shot}")

    @Slot(object)
    def _on_shot_double_clicked(self, shot: Shot) -> None:
        """Handle shot double-click.

        Args:
            shot: Double-clicked shot.
        """
        self.shot_double_clicked.emit(shot)
        logger.debug(f"Double-clicked approved shot: {shot.shot}")

    def get_selected_shot(self) -> Shot | None:
        """Get the currently selected shot.

        Returns:
            Selected Shot object or None.
        """
        return self._selected_shot

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
            self._populate_grid()
            self._pending_size = None
            logger.debug("Grid resized and repopulated after debounce")
