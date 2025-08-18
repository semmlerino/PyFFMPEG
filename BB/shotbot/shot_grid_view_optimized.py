"""Optimized grid view with scroll-based prefetching and performance monitoring.

This module provides a high-performance QListView implementation with:
- Scroll-based intelligent prefetching
- Performance monitoring and adaptation
- Memory-efficient virtualization
- Smooth scrolling with predictive loading
"""

import logging
from typing import Optional

from PySide6.QtCore import (
    QElapsedTimer,
    QModelIndex,
    QSize,
    Qt,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import QKeyEvent, QWheelEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListView,
    QProgressBar,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from config import Config
from shot_grid_delegate_optimized import ShotGridDelegateOptimized
from shot_item_model_optimized import ShotItemModelOptimized, ShotRole

logger = logging.getLogger(__name__)


class PerformanceMonitor:
    """Monitor view performance and provide optimization hints."""
    
    def __init__(self):
        self.scroll_timer = QElapsedTimer()
        self.last_scroll_pos = 0
        self.scroll_velocity = 0
        self.frame_times = []
        self.max_frame_samples = 30
        
    def update_scroll(self, new_pos: int) -> float:
        """Update scroll metrics and return velocity."""
        if not self.scroll_timer.isValid():
            self.scroll_timer.start()
            self.last_scroll_pos = new_pos
            return 0.0
            
        elapsed = self.scroll_timer.elapsed()
        if elapsed > 0:
            # Calculate velocity (items per second)
            distance = abs(new_pos - self.last_scroll_pos)
            self.scroll_velocity = (distance * 1000) / elapsed
            
        self.scroll_timer.restart()
        self.last_scroll_pos = new_pos
        
        return self.scroll_velocity
        
    def add_frame_time(self, ms: int) -> None:
        """Add frame render time sample."""
        self.frame_times.append(ms)
        if len(self.frame_times) > self.max_frame_samples:
            self.frame_times.pop(0)
            
    def get_average_frame_time(self) -> float:
        """Get average frame render time."""
        if not self.frame_times:
            return 0.0
        return sum(self.frame_times) / len(self.frame_times)
        
    def get_optimization_mode(self) -> str:
        """Determine optimization mode based on performance."""
        avg_frame = self.get_average_frame_time()
        
        if avg_frame > 50:  # > 50ms per frame
            return "aggressive"
        elif avg_frame > 16:  # > 16ms per frame (60 FPS threshold)
            return "balanced"
        else:
            return "quality"


class ShotGridViewOptimized(QWidget):
    """Optimized grid view with intelligent prefetching and performance monitoring.
    
    Features:
    - Scroll-direction aware prefetching
    - Performance monitoring and adaptation
    - Virtual viewport with efficient culling
    - Progressive loading with visual feedback
    - Memory-aware caching strategies
    """
    
    # Signals
    shot_selected = Signal(object)  # Shot object
    shot_double_clicked = Signal(object)  # Shot object
    app_launch_requested = Signal(str)  # app_name
    performance_changed = Signal(str)  # performance mode
    
    def __init__(
        self, 
        model: Optional[ShotItemModelOptimized] = None,
        parent: Optional[QWidget] = None
    ):
        """Initialize the optimized grid view."""
        super().__init__(parent)
        
        self._model = model
        self._thumbnail_size = Config.DEFAULT_THUMBNAIL_SIZE
        self._selected_shot = None
        
        # Performance monitoring
        self._performance = PerformanceMonitor()
        self._optimization_mode = "quality"
        
        # Scroll tracking
        self._last_scroll_value = 0
        self._scroll_direction = 0
        self._scroll_prediction_enabled = True
        
        # Frame timing
        self._frame_timer = QElapsedTimer()
        
        self._setup_ui()
        
        if model:
            self.set_model(model)
            
        # Update timer for visible range (adaptive interval)
        self._update_timer = QTimer()
        self._update_timer.timeout.connect(self._update_visible_range_smart)
        self._update_timer.setInterval(50)  # Start with 50ms
        
        logger.info("Optimized grid view initialized with performance monitoring")
        
    def _setup_ui(self) -> None:
        """Set up the user interface with performance indicators."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Control panel
        control_layout = QHBoxLayout()
        
        # Size control
        control_layout.addWidget(QLabel("Thumbnail Size:"))
        
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setMinimum(Config.MIN_THUMBNAIL_SIZE)
        self.size_slider.setMaximum(Config.MAX_THUMBNAIL_SIZE)
        self.size_slider.setValue(self._thumbnail_size)
        self.size_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.size_slider.setTickInterval(50)
        self.size_slider.valueChanged.connect(self._on_size_changed)
        control_layout.addWidget(self.size_slider)
        
        self.size_label = QLabel(f"{self._thumbnail_size}px")
        self.size_label.setMinimumWidth(50)
        control_layout.addWidget(self.size_label)
        
        control_layout.addStretch()
        
        # Performance indicator
        control_layout.addWidget(QLabel("Performance:"))
        self.performance_label = QLabel("Quality")
        self.performance_label.setMinimumWidth(80)
        self.performance_label.setStyleSheet("color: #0f0;")
        control_layout.addWidget(self.performance_label)
        
        # FPS indicator
        self.fps_label = QLabel("60 FPS")
        self.fps_label.setMinimumWidth(60)
        control_layout.addWidget(self.fps_label)
        
        layout.addLayout(control_layout)
        
        # Loading progress bar
        self.loading_bar = QProgressBar()
        self.loading_bar.setMaximumHeight(3)
        self.loading_bar.setTextVisible(False)
        self.loading_bar.setVisible(False)
        layout.addWidget(self.loading_bar)
        
        # Create optimized QListView
        self.list_view = QListView()
        self.list_view.setViewMode(QListView.ViewMode.IconMode)
        self.list_view.setResizeMode(QListView.ResizeMode.Adjust)
        self.list_view.setLayoutMode(QListView.LayoutMode.Batched)
        self.list_view.setBatchSize(50)  # Larger batch for performance
        self.list_view.setUniformItemSizes(True)
        self.list_view.setSpacing(Config.THUMBNAIL_SPACING)
        
        # Optimization settings
        self.list_view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list_view.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        
        # Reduce update regions
        self.list_view.viewport().setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.list_view.viewport().setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        
        # Selection
        self.list_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        
        # Create and set optimized delegate
        self._delegate = ShotGridDelegateOptimized(self)
        self.list_view.setItemDelegate(self._delegate)
        
        # Connect signals
        self.list_view.clicked.connect(self._on_item_clicked)
        self.list_view.doubleClicked.connect(self._on_item_double_clicked)
        
        # Connect to scroll bar for intelligent prefetching
        scrollbar = self.list_view.verticalScrollBar()
        if scrollbar:
            scrollbar.valueChanged.connect(self._on_scroll_changed)
            scrollbar.sliderPressed.connect(self._on_scroll_started)
            scrollbar.sliderReleased.connect(self._on_scroll_ended)
            
        layout.addWidget(self.list_view)
        
        # Enable keyboard focus
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.list_view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
    @property
    def model(self) -> Optional[ShotItemModelOptimized]:
        """Get the current model."""
        return self._model
        
    @property
    def selected_shot(self):
        """Get the currently selected shot."""
        return self._selected_shot
        
    def set_model(self, model: ShotItemModelOptimized) -> None:
        """Set the data model for the view."""
        self._model = model
        self.list_view.setModel(model)
        
        # Set up selection model
        selection_model = self.list_view.selectionModel()
        if selection_model:
            selection_model.currentChanged.connect(self._on_selection_changed)
            
        # Connect to model signals
        model.shots_updated.connect(self._on_model_updated)
        model.loading_progress.connect(self._on_loading_progress)
        model.thumbnail_loaded.connect(self._on_thumbnail_loaded)
        
        # Initial update
        self._update_grid_size()
        self._update_visible_range_smart()
        
        logger.debug(f"Model set with {model.rowCount()} initial items")
        
    @Slot()
    def _on_model_updated(self) -> None:
        """Handle model updates."""
        self._update_grid_size()
        self._update_visible_range_smart()
        
        # Reset performance monitoring
        self._performance = PerformanceMonitor()
        
    @Slot(int, int)
    def _on_loading_progress(self, loaded: int, total: int) -> None:
        """Handle loading progress updates."""
        if total > 0:
            self.loading_bar.setVisible(True)
            self.loading_bar.setMaximum(total)
            self.loading_bar.setValue(loaded)
            
            if loaded >= total:
                # Hide after delay
                QTimer.singleShot(500, lambda: self.loading_bar.setVisible(False))
        else:
            self.loading_bar.setVisible(False)
            
    @Slot(int)
    def _on_thumbnail_loaded(self, row: int) -> None:
        """Handle thumbnail loaded notification."""
        # Could trigger partial viewport update for the specific item
        if self._is_row_visible(row):
            index = self._model.index(row, 0)
            self.list_view.update(index)
            
    @Slot(int)
    def _on_scroll_changed(self, value: int) -> None:
        """Handle scroll changes for intelligent prefetching."""
        # Update performance metrics
        velocity = self._performance.update_scroll(value)
        
        # Determine scroll direction
        if value > self._last_scroll_value:
            self._scroll_direction = 1  # Down
        elif value < self._last_scroll_value:
            self._scroll_direction = -1  # Up
        else:
            self._scroll_direction = 0  # None
            
        self._last_scroll_value = value
        
        # Adapt update timer based on scroll velocity
        self._adapt_update_timer(velocity)
        
        # Update visible range immediately for fast scrolling
        if velocity > 100:  # Fast scrolling threshold
            self._update_visible_range_smart()
            
        # Start update timer if not running
        if not self._update_timer.isActive():
            self._update_timer.start()
            
    @Slot()
    def _on_scroll_started(self) -> None:
        """Handle scroll start for optimization."""
        # Switch to fast rendering mode
        self._delegate._quality_mode = "low"
        
        # Increase update frequency
        self._update_timer.setInterval(25)
        
    @Slot()
    def _on_scroll_ended(self) -> None:
        """Handle scroll end for quality restoration."""
        # Restore quality rendering
        self._delegate._quality_mode = "high"
        
        # Restore normal update frequency
        self._update_timer.setInterval(100)
        
        # Final update with high quality
        self._update_visible_range_smart()
        self.list_view.viewport().update()
        
    def _adapt_update_timer(self, velocity: float) -> None:
        """Adapt update timer interval based on scroll velocity."""
        if velocity > 500:
            interval = 10  # Very fast updates
        elif velocity > 100:
            interval = 25  # Fast updates
        elif velocity > 10:
            interval = 50  # Normal updates
        else:
            interval = 100  # Slow updates
            
        self._update_timer.setInterval(interval)
        
    @Slot()
    def _update_visible_range_smart(self) -> None:
        """Update visible range with intelligent prefetching."""
        if not self._model:
            return
            
        # Stop timer if scrolling stopped
        if self._performance.scroll_velocity < 1:
            self._update_timer.stop()
            
        # Measure frame time
        self._frame_timer.start()
        
        # Get visible rectangle
        viewport = self.list_view.viewport()
        visible_rect = viewport.rect()
        
        # Find visible items
        first_index = self.list_view.indexAt(visible_rect.topLeft())
        last_index = self.list_view.indexAt(visible_rect.bottomRight())
        
        if not first_index.isValid():
            first_index = self._model.index(0, 0)
            
        if not last_index.isValid():
            # Estimate last visible based on grid
            items_per_row = self._calculate_items_per_row()
            visible_rows = visible_rect.height() // (self._thumbnail_size + 40)
            estimated_last = min(
                first_index.row() + items_per_row * visible_rows,
                self._model.rowCount() - 1
            )
            last_index = self._model.index(estimated_last, 0)
            
        # Calculate prefetch range based on scroll direction and velocity
        prefetch_factor = self._calculate_prefetch_factor()
        
        if self._scroll_direction > 0:
            # Scrolling down - prefetch more below
            start = first_index.row()
            end = min(last_index.row() + prefetch_factor, self._model.rowCount())
        elif self._scroll_direction < 0:
            # Scrolling up - prefetch more above
            start = max(0, first_index.row() - prefetch_factor)
            end = last_index.row() + 1
        else:
            # No scroll - balanced prefetch
            start = max(0, first_index.row() - prefetch_factor // 2)
            end = min(last_index.row() + prefetch_factor // 2, self._model.rowCount())
            
        # Update model's visible range
        if first_index.isValid() and last_index.isValid():
            self._model.set_visible_range(start, end)
            
        # Update performance metrics
        frame_time = self._frame_timer.elapsed()
        self._performance.add_frame_time(frame_time)
        self._update_performance_display()
        
        # Check if we need to fetch more data (virtual proxy)
        if self._should_fetch_more(last_index.row()):
            self._model.fetchMore(QModelIndex())
            
    def _calculate_prefetch_factor(self) -> int:
        """Calculate prefetch factor based on performance and scroll velocity."""
        base_prefetch = 20
        
        # Adjust based on velocity
        velocity_factor = min(self._performance.scroll_velocity / 100, 3.0)
        
        # Adjust based on performance mode
        if self._optimization_mode == "aggressive":
            performance_factor = 0.5
        elif self._optimization_mode == "balanced":
            performance_factor = 1.0
        else:
            performance_factor = 1.5
            
        return int(base_prefetch * velocity_factor * performance_factor)
        
    def _should_fetch_more(self, last_visible_row: int) -> bool:
        """Determine if more data should be fetched."""
        if not self._model:
            return False
            
        total_rows = self._model.rowCount()
        
        # Fetch more if within threshold of the end
        threshold = self._calculate_items_per_row() * 3  # 3 rows ahead
        
        return (
            self._model.canFetchMore(QModelIndex()) and
            last_visible_row >= total_rows - threshold
        )
        
    def _calculate_items_per_row(self) -> int:
        """Calculate number of items per row in grid."""
        viewport_width = self.list_view.viewport().width()
        if viewport_width <= 0:
            return Config.GRID_COLUMNS
            
        item_width = self._thumbnail_size + Config.THUMBNAIL_SPACING + 16  # padding
        return max(1, viewport_width // item_width)
        
    def _is_row_visible(self, row: int) -> bool:
        """Check if a row is currently visible."""
        viewport = self.list_view.viewport()
        index = self._model.index(row, 0)
        rect = self.list_view.visualRect(index)
        
        return viewport.rect().intersects(rect)
        
    def _update_performance_display(self) -> None:
        """Update performance indicators."""
        # Determine optimization mode
        old_mode = self._optimization_mode
        self._optimization_mode = self._performance.get_optimization_mode()
        
        if old_mode != self._optimization_mode:
            self.performance_changed.emit(self._optimization_mode)
            
        # Update labels
        if self._optimization_mode == "aggressive":
            self.performance_label.setText("Fast")
            self.performance_label.setStyleSheet("color: #f00;")
        elif self._optimization_mode == "balanced":
            self.performance_label.setText("Balanced")
            self.performance_label.setStyleSheet("color: #ff0;")
        else:
            self.performance_label.setText("Quality")
            self.performance_label.setStyleSheet("color: #0f0;")
            
        # Update FPS
        avg_frame = self._performance.get_average_frame_time()
        if avg_frame > 0:
            fps = min(60, int(1000 / avg_frame))
            self.fps_label.setText(f"{fps} FPS")
            
    @Slot(int)
    def _on_size_changed(self, size: int) -> None:
        """Handle thumbnail size change."""
        self._thumbnail_size = size
        self.size_label.setText(f"{size}px")
        
        # Update delegate
        self._delegate.set_thumbnail_size(size)
        
        # Update grid
        self._update_grid_size()
        
        # Force complete refresh
        self.list_view.viewport().update()
        self._update_visible_range_smart()
        
    def _update_grid_size(self) -> None:
        """Update grid size based on thumbnail size."""
        # Calculate item size including padding and text
        item_size = self._thumbnail_size + 2 * 8 + 40
        
        # Set grid size
        self.list_view.setGridSize(QSize(item_size, item_size))
        
        # Ensure uniform sizes
        self.list_view.setUniformItemSizes(True)
        
    @Slot(QModelIndex)
    def _on_item_clicked(self, index: QModelIndex) -> None:
        """Handle item click."""
        if not index.isValid() or not self._model:
            return
            
        shot = index.data(ShotRole.ShotObjectRole)
        if shot:
            self._selected_shot = shot
            self._model.setData(index, True, ShotRole.IsSelectedRole)
            self.shot_selected.emit(shot)
            
    @Slot(QModelIndex)
    def _on_item_double_clicked(self, index: QModelIndex) -> None:
        """Handle item double-click."""
        if not index.isValid() or not self._model:
            return
            
        shot = index.data(ShotRole.ShotObjectRole)
        if shot:
            self.shot_double_clicked.emit(shot)
            
    @Slot(QModelIndex, QModelIndex)
    def _on_selection_changed(
        self, current: QModelIndex, previous: QModelIndex
    ) -> None:
        """Handle selection change."""
        if not self._model:
            return
            
        # Clear previous selection
        if previous.isValid():
            self._model.setData(previous, False, ShotRole.IsSelectedRole)
            
        # Set current selection
        if current.isValid():
            self._model.setData(current, True, ShotRole.IsSelectedRole)
            shot = current.data(ShotRole.ShotObjectRole)
            if shot:
                self._selected_shot = shot
                self.shot_selected.emit(shot)
                
    def wheelEvent(self, event: QWheelEvent) -> None:
        """Handle wheel event for size adjustment."""
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
        """Handle keyboard shortcuts."""
        if not self._selected_shot:
            super().keyPressEvent(event)
            return
            
        # App launch shortcuts
        key_map = {
            Qt.Key.Key_3: "3de",
            Qt.Key.Key_N: "nuke",
            Qt.Key.Key_M: "maya",
            Qt.Key.Key_R: "rv",
            Qt.Key.Key_P: "publish",
        }
        
        if event.key() in key_map:
            self.app_launch_requested.emit(key_map[event.key()])
            event.accept()
        else:
            self.list_view.keyPressEvent(event)
            
    def select_shot_by_name(self, shot_name: str) -> None:
        """Select a shot by its full name."""
        if not self._model:
            return
            
        for row in range(self._model.rowCount()):
            index = self._model.index(row, 0)
            shot = index.data(ShotRole.ShotObjectRole)
            
            if shot and shot.full_name == shot_name:
                self.list_view.setCurrentIndex(index)
                self.list_view.scrollTo(
                    index, QAbstractItemView.ScrollHint.PositionAtCenter
                )
                self._on_item_clicked(index)
                break
                
    def clear_selection(self) -> None:
        """Clear the current selection."""
        if self.list_view.selectionModel():
            self.list_view.selectionModel().clear()
        self._selected_shot = None
        
    def refresh_view(self) -> None:
        """Force a complete view refresh."""
        self._delegate.clear_cache()
        self.list_view.viewport().update()
        self._update_visible_range_smart()
        
    def enable_performance_mode(self, mode: str) -> None:
        """Set specific performance mode.
        
        Args:
            mode: One of "quality", "balanced", "aggressive"
        """
        self._optimization_mode = mode
        
        if mode == "aggressive":
            self.list_view.setBatchSize(100)
            self._delegate._quality_mode = "low"
            if self._model:
                self._model.enable_virtual_proxy(True)
        elif mode == "balanced":
            self.list_view.setBatchSize(50)
            self._delegate._quality_mode = "medium"
            if self._model:
                self._model.enable_virtual_proxy(True)
        else:  # quality
            self.list_view.setBatchSize(20)
            self._delegate._quality_mode = "high"
            if self._model:
                self._model.enable_virtual_proxy(False)
                
        self._update_performance_display()