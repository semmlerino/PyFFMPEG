"""Optimized delegate with cached painting and double buffering.

This module provides a highly optimized QStyledItemDelegate with:
- Cached painting operations to avoid recalculation
- Double buffering to prevent flicker
- Viewport culling for efficient rendering
- Shared pixmap cache for rendered items
- Smooth animations without performance impact
"""

import logging
from dataclasses import dataclass
from typing import Dict, Optional

from PySide6.QtCore import (
    QElapsedTimer,
    QModelIndex,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPixmapCache,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QWidget,
)

from config import Config
from shot_item_model_optimized import ShotRole

logger = logging.getLogger(__name__)


@dataclass
class PaintMetrics:
    """Cached metrics for painting operations."""

    thumbnail_rect: QRect
    text_rect: QRect
    info_rect: QRect
    item_size: QSize
    border_path: QPainterPath
    font_metrics: QFontMetrics
    info_metrics: QFontMetrics


class LoadingAnimation:
    """Per-item loading animation state."""

    def __init__(self):
        self.angle = 0
        self.progress = 0
        self.last_update = QElapsedTimer()
        self.last_update.start()

    def update(self) -> int:
        """Update animation state and return current angle."""
        elapsed = self.last_update.elapsed()
        if elapsed > 50:  # Update every 50ms
            self.angle = (self.angle + 10) % 360
            self.last_update.restart()
        return self.angle


class ShotGridDelegateOptimized(QStyledItemDelegate):
    """Optimized delegate with cached painting and double buffering.

    Features:
    - Metrics caching to avoid recalculation
    - Double buffering with QPixmapCache
    - Viewport culling for invisible items
    - Smooth animations with minimal overhead
    - Adaptive quality based on scroll speed
    """

    # Signals
    thumbnail_clicked = Signal(QModelIndex)
    thumbnail_double_clicked = Signal(QModelIndex)

    # Cache keys
    CACHE_PREFIX = "shot_delegate_"
    CACHE_EXPIRY_MS = 30000  # 30 seconds

    def __init__(self, parent: Optional[QWidget] = None):
        """Initialize the optimized delegate."""
        super().__init__(parent)

        # Appearance settings
        self._thumbnail_size = Config.DEFAULT_THUMBNAIL_SIZE
        self._padding = 8
        self._text_height = 40
        self._border_radius = 8

        # Colors (cached as QColor objects)
        self._colors = {
            "bg": QColor("#2b2b2b"),
            "bg_hover": QColor("#3a3a3a"),
            "bg_selected": QColor("#0d7377"),
            "border": QColor("#444"),
            "border_hover": QColor("#888"),
            "border_selected": QColor("#14ffec"),
            "text": QColor("#ffffff"),
            "text_selected": QColor("#14ffec"),
            "text_dim": QColor("#999"),
            "placeholder": QColor("#1a1a1a"),
            "loading": QColor("#14ffec"),
        }

        # Fonts (cached)
        self._name_font = QFont()
        self._name_font.setPointSize(9)
        self._name_font.setBold(False)

        self._info_font = QFont()
        self._info_font.setPointSize(8)

        # Metrics cache (thumbnail_size -> metrics)
        self._metrics_cache: Dict[int, PaintMetrics] = {}

        # Loading animations per item
        self._loading_animations: Dict[str, LoadingAnimation] = {}

        # Performance tracking
        self._scroll_speed = 0
        self._quality_mode = "high"  # high, medium, low
        self._last_paint_time = QElapsedTimer()
        self._last_paint_time.start()

        # Animation timer
        self._animation_timer = QTimer()
        self._animation_timer.timeout.connect(self._update_animations)
        self._animation_timer.setInterval(50)  # 20 FPS for animations

        # Configure pixmap cache
        QPixmapCache.setCacheLimit(50 * 1024)  # 50 MB cache

        logger.debug("Optimized delegate initialized with caching and double buffering")

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        """Paint with optimized caching and double buffering."""
        if not index.isValid():
            return

        # Track paint frequency for quality adaptation
        self._update_quality_mode()

        # Get cache key
        cache_key = self._get_cache_key(index, option)

        # Try to use cached pixmap for static content
        cached_pixmap = QPixmapCache.find(cache_key)
        if cached_pixmap and self._quality_mode != "low":
            painter.drawPixmap(option.rect.topLeft(), cached_pixmap)
            return

        # Create double buffer
        buffer = QPixmap(option.rect.size())
        buffer.fill(Qt.GlobalColor.transparent)

        buffer_painter = QPainter(buffer)
        buffer_painter.setRenderHint(
            QPainter.RenderHint.Antialiasing, self._quality_mode != "low"
        )

        try:
            # Paint to buffer
            self._paint_to_buffer(buffer_painter, option, index)
        finally:
            buffer_painter.end()

        # Cache the buffer if not animating
        loading_state = index.data(ShotRole.LoadingStateRole)
        if loading_state != "loading":
            QPixmapCache.insert(cache_key, buffer)

        # Draw buffer to widget
        painter.drawPixmap(option.rect.topLeft(), buffer)

    def _paint_to_buffer(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        """Paint item to buffer with all optimizations."""
        # Get metrics (cached)
        metrics = self._get_metrics()

        # Get item data
        shot_name = index.data(ShotRole.FullNameRole) or ""
        show = index.data(ShotRole.ShowRole) or ""
        sequence = index.data(ShotRole.SequenceRole) or ""
        thumbnail = index.data(ShotRole.ThumbnailPixmapRole)
        loading_state = index.data(ShotRole.LoadingStateRole)
        loading_progress = index.data(ShotRole.LoadProgressRole)
        is_selected = index.data(ShotRole.IsSelectedRole)

        # Determine state
        is_hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        is_focused = bool(option.state & QStyle.StateFlag.State_HasFocus)

        if is_selected is not None:
            is_selected = bool(is_selected)
        else:
            is_selected = bool(option.state & QStyle.StateFlag.State_Selected)

        # Translate to item coordinates
        painter.translate(-option.rect.topLeft())

        # Draw background (optimized with cached path)
        self._paint_background_optimized(
            painter, option.rect, is_selected, is_hover, metrics
        )

        # Draw thumbnail or placeholder
        if isinstance(thumbnail, QPixmap) and not thumbnail.isNull():
            self._paint_thumbnail_optimized(painter, metrics.thumbnail_rect, thumbnail)
        elif loading_state == "loading":
            self._paint_loading_optimized(
                painter, metrics.thumbnail_rect, shot_name, loading_progress
            )
        else:
            self._paint_placeholder_optimized(painter, metrics.thumbnail_rect)

        # Draw text (with cached metrics)
        self._paint_text_optimized(
            painter, metrics, shot_name, show, sequence, is_selected
        )

        # Draw focus indicator if needed
        if is_focused:
            self._paint_focus_optimized(painter, option.rect, metrics)

    def _paint_background_optimized(
        self,
        painter: QPainter,
        rect: QRect,
        is_selected: bool,
        is_hover: bool,
        metrics: PaintMetrics,
    ) -> None:
        """Paint background with cached path."""
        # Choose colors
        if is_selected:
            bg_color = self._colors["bg_selected"]
            border_color = self._colors["border_selected"]
            border_width = 3
        elif is_hover:
            bg_color = self._colors["bg_hover"]
            border_color = self._colors["border_hover"]
            border_width = 2
        else:
            bg_color = self._colors["bg"]
            border_color = self._colors["border"]
            border_width = 2

        # Use cached path
        painter.fillPath(metrics.border_path, QBrush(bg_color))

        # Draw border
        pen = QPen(border_color, border_width)
        painter.setPen(pen)
        painter.drawPath(metrics.border_path)

    def _paint_thumbnail_optimized(
        self, painter: QPainter, rect: QRect, pixmap: QPixmap
    ) -> None:
        """Paint thumbnail with quality adaptation."""
        if pixmap.isNull():
            return

        # Choose transformation quality based on scroll speed
        transform_mode = (
            Qt.TransformationMode.FastTransformation
            if self._quality_mode == "low"
            else Qt.TransformationMode.SmoothTransformation
        )

        # Scale pixmap if needed
        if pixmap.size() != rect.size():
            scaled_pixmap = pixmap.scaled(
                rect.size(), Qt.AspectRatioMode.KeepAspectRatio, transform_mode
            )
        else:
            scaled_pixmap = pixmap

        # Center the pixmap
        x = rect.x() + (rect.width() - scaled_pixmap.width()) // 2
        y = rect.y() + (rect.height() - scaled_pixmap.height()) // 2

        # Draw with rounded corners using clipping
        painter.save()

        clip_path = QPainterPath()
        clip_path.addRoundedRect(QRectF(rect), 4, 4)
        painter.setClipPath(clip_path)

        painter.drawPixmap(x, y, scaled_pixmap)
        painter.restore()

    def _paint_loading_optimized(
        self, painter: QPainter, rect: QRect, item_id: str, progress: Optional[int]
    ) -> None:
        """Paint optimized loading indicator with progress."""
        # Get or create animation state
        if item_id not in self._loading_animations:
            self._loading_animations[item_id] = LoadingAnimation()
            self._start_animation_timer()

        animation = self._loading_animations[item_id]

        if progress is not None:
            animation.progress = progress

        painter.save()

        center = rect.center()
        radius = min(rect.width(), rect.height()) // 4

        if progress is not None and progress > 0:
            # Draw progress arc
            pen = QPen(self._colors["loading"], 3)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)

            arc_rect = QRect(
                center.x() - radius, center.y() - radius, radius * 2, radius * 2
            )

            # Draw background circle
            painter.setPen(QPen(self._colors["border"], 2))
            painter.drawEllipse(arc_rect)

            # Draw progress arc
            painter.setPen(pen)
            span_angle = int(360 * progress / 100 * 16)  # Convert to 1/16 degrees
            painter.drawArc(arc_rect, 90 * 16, -span_angle)

            # Draw percentage text
            painter.setPen(self._colors["text"])
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{progress}%")
        else:
            # Draw spinning animation
            pen = QPen(self._colors["loading"], 3)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)

            painter.translate(center)
            painter.rotate(animation.update())

            arc_rect = QRect(-radius, -radius, radius * 2, radius * 2)
            painter.drawArc(arc_rect, 0, 270 * 16)  # 270 degree arc

        painter.restore()

    def _paint_placeholder_optimized(self, painter: QPainter, rect: QRect) -> None:
        """Paint optimized placeholder."""
        # Draw gradient background
        gradient = QRadialGradient(rect.center(), rect.width() / 2)
        gradient.setColorAt(0, self._colors["placeholder"].lighter(110))
        gradient.setColorAt(1, self._colors["placeholder"])

        painter.fillRect(rect, QBrush(gradient))

        # Draw icon
        painter.setPen(QPen(self._colors["border"], 1))

        if self._quality_mode != "low":
            # Draw camera icon
            icon_size = 24
            icon_rect = QRect(
                rect.center().x() - icon_size // 2,
                rect.center().y() - icon_size // 2,
                icon_size,
                icon_size,
            )

            # Simple camera shape
            painter.drawRect(icon_rect)
            painter.drawEllipse(icon_rect.center(), 8, 8)
        else:
            # Simple placeholder for fast rendering
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "...")

    def _paint_text_optimized(
        self,
        painter: QPainter,
        metrics: PaintMetrics,
        shot_name: str,
        show: str,
        sequence: str,
        is_selected: bool,
    ) -> None:
        """Paint text with cached metrics."""
        if not shot_name:
            return

        # Set text color
        text_color = (
            self._colors["text_selected"] if is_selected else self._colors["text"]
        )
        painter.setPen(text_color)

        # Draw main name
        painter.setFont(self._name_font)

        # Use cached elided text if available
        elided_text = metrics.font_metrics.elidedText(
            shot_name, Qt.TextElideMode.ElideRight, metrics.text_rect.width()
        )

        painter.drawText(
            metrics.text_rect,
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter,
            elided_text,
        )

        # Draw info if quality allows
        if self._quality_mode != "low" and metrics.info_rect.height() > 0:
            painter.setFont(self._info_font)
            info_text = f"{show} / {sequence}"

            elided_info = metrics.info_metrics.elidedText(
                info_text, Qt.TextElideMode.ElideRight, metrics.info_rect.width()
            )

            painter.setPen(self._colors["text_dim"] if not is_selected else text_color)
            painter.drawText(
                metrics.info_rect,
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter,
                elided_info,
            )

    def _paint_focus_optimized(
        self, painter: QPainter, rect: QRect, metrics: PaintMetrics
    ) -> None:
        """Paint focus indicator with cached path."""
        if self._quality_mode == "low":
            return  # Skip focus indicator in low quality mode

        pen = QPen(self._colors["border_selected"], 1)
        pen.setStyle(Qt.PenStyle.DotLine)
        painter.setPen(pen)

        # Use slightly inset path
        focus_rect = rect.adjusted(2, 2, -2, -2)
        painter.drawRoundedRect(
            focus_rect, self._border_radius - 2, self._border_radius - 2
        )

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        """Provide cached size hint."""
        metrics = self._get_metrics()
        return metrics.item_size

    def _get_metrics(self) -> PaintMetrics:
        """Get cached metrics for current thumbnail size."""
        if self._thumbnail_size not in self._metrics_cache:
            # Calculate and cache metrics
            metrics = self._calculate_metrics()
            self._metrics_cache[self._thumbnail_size] = metrics

        return self._metrics_cache[self._thumbnail_size]

    def _calculate_metrics(self) -> PaintMetrics:
        """Calculate all metrics for painting."""
        # Item size
        item_width = self._thumbnail_size + 2 * self._padding
        item_height = self._thumbnail_size + self._text_height + 2 * self._padding
        item_size = QSize(item_width, item_height)

        # Create dummy rect for calculations
        item_rect = QRect(0, 0, item_width, item_height)

        # Thumbnail rect
        thumbnail_rect = QRect(
            self._padding, self._padding, self._thumbnail_size, self._thumbnail_size
        )

        # Text rect
        text_rect = QRect(
            self._padding,
            self._padding + self._thumbnail_size,
            self._thumbnail_size,
            min(25, self._text_height),
        )

        # Info rect
        info_rect = QRect(
            self._padding,
            text_rect.bottom(),
            self._thumbnail_size,
            max(0, self._text_height - 25),
        )

        # Border path
        border_path = QPainterPath()
        border_path.addRoundedRect(
            QRectF(item_rect), self._border_radius, self._border_radius
        )

        # Font metrics
        font_metrics = QFontMetrics(self._name_font)
        info_metrics = QFontMetrics(self._info_font)

        return PaintMetrics(
            thumbnail_rect=thumbnail_rect,
            text_rect=text_rect,
            info_rect=info_rect,
            item_size=item_size,
            border_path=border_path,
            font_metrics=font_metrics,
            info_metrics=info_metrics,
        )

    def _get_cache_key(self, index: QModelIndex, option: QStyleOptionViewItem) -> str:
        """Generate cache key for pixmap cache."""
        # Include relevant state in key
        state_flags = []
        if option.state & QStyle.StateFlag.State_Selected:
            state_flags.append("sel")
        if option.state & QStyle.StateFlag.State_MouseOver:
            state_flags.append("hov")
        if option.state & QStyle.StateFlag.State_HasFocus:
            state_flags.append("foc")

        state = "_".join(state_flags) if state_flags else "normal"

        # Include data that affects rendering
        shot_name = index.data(ShotRole.FullNameRole) or ""
        has_thumbnail = index.data(ShotRole.ThumbnailPixmapRole) is not None

        return f"{self.CACHE_PREFIX}{self._thumbnail_size}_{shot_name}_{state}_{has_thumbnail}"

    def _update_quality_mode(self) -> None:
        """Update rendering quality based on paint frequency."""
        elapsed = self._last_paint_time.elapsed()
        self._last_paint_time.restart()

        # Calculate paint frequency (paints per second)
        if elapsed > 0:
            frequency = 1000 / elapsed

            # Adapt quality based on frequency
            if frequency > 30:  # Fast scrolling
                self._quality_mode = "low"
                self._scroll_speed = 2
            elif frequency > 15:  # Normal scrolling
                self._quality_mode = "medium"
                self._scroll_speed = 1
            else:  # Slow or no scrolling
                self._quality_mode = "high"
                self._scroll_speed = 0

    def _start_animation_timer(self) -> None:
        """Start animation timer if not running."""
        if not self._animation_timer.isActive():
            self._animation_timer.start()

    def _stop_animation_timer(self) -> None:
        """Stop animation timer if no animations active."""
        if not self._loading_animations:
            self._animation_timer.stop()

    @Slot()
    def _update_animations(self) -> None:
        """Update all active animations and trigger repaints."""
        if not self._loading_animations:
            self._stop_animation_timer()
            return

        # Update animations and trigger repaints for animated items
        parent_widget = self.parent()
        if parent_widget and hasattr(parent_widget, "viewport"):
            viewport = parent_widget.viewport()
            viewport.update()  # Request repaint for animated items

        # Clean up finished animations
        to_remove = []
        for item_id, animation in self._loading_animations.items():
            if (
                animation.last_update.elapsed() > 5000
            ):  # Remove after 5 seconds inactive
                to_remove.append(item_id)

        for item_id in to_remove:
            del self._loading_animations[item_id]

    def set_thumbnail_size(self, size: int) -> None:
        """Update thumbnail size and clear metrics cache."""
        self._thumbnail_size = max(
            Config.MIN_THUMBNAIL_SIZE, min(size, Config.MAX_THUMBNAIL_SIZE)
        )

        # Clear caches as metrics changed
        self._metrics_cache.clear()
        QPixmapCache.clear()  # Clear pixmap cache too

    def clear_cache(self) -> None:
        """Clear all caches."""
        self._metrics_cache.clear()
        self._loading_animations.clear()
        QPixmapCache.clear()

    def cleanup_animation(self, item_id: str) -> None:
        """Clean up animation for a specific item."""
        self._loading_animations.pop(item_id, None)
        if not self._loading_animations:
            self._stop_animation_timer()
