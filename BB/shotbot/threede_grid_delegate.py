"""Custom delegate for efficient 3DE scene thumbnail rendering in grid views.

This module provides a QStyledItemDelegate implementation that handles
custom painting of 3DE scene thumbnails with selection states, loading indicators,
and optimized rendering for large datasets.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import (
    QModelIndex,
    QPersistentModelIndex,
    QRect,
    QRectF,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QWidget,
)
from typing_extensions import override

from config import Config
from threede_item_model import ThreeDERole

if TYPE_CHECKING:
    from datetime import datetime

logger = logging.getLogger(__name__)


class ThreeDEGridDelegate(QStyledItemDelegate):
    """Efficient delegate for rendering 3DE scene thumbnails in a grid.

    This delegate provides:
    - Custom painting with state handling
    - Loading indicators during thumbnail fetch
    - Selection and hover effects
    - User and timestamp display
    - Optimized rendering with clipping
    - Memory-efficient painting (no widget creation)
    """

    # Signals
    thumbnail_clicked = Signal(QModelIndex)
    thumbnail_double_clicked = Signal(QModelIndex)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the delegate.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)

        # Appearance settings
        self._thumbnail_size = Config.DEFAULT_THUMBNAIL_SIZE
        self._padding = 8
        self._text_height = 50  # Slightly taller for extra info
        self._border_radius = 8

        # Colors - 3DE specific theme
        self._bg_color = QColor("#2b2b3b")  # Slightly blue tint
        self._bg_hover_color = QColor("#3a3a4a")
        self._bg_selected_color = QColor("#0a5f73")  # Different from shot grid
        self._border_color = QColor("#445")
        self._border_hover_color = QColor("#889")
        self._border_selected_color = QColor("#00c9ff")  # 3DE blue
        self._text_color = QColor("#ffffff")
        self._text_selected_color = QColor("#00c9ff")
        self._user_color = QColor("#a0a0a0")  # Gray for user text

        # Fonts
        self._name_font = QFont()
        self._name_font.setPointSize(9)
        self._name_font.setBold(False)

        self._info_font = QFont()
        self._info_font.setPointSize(7)

        # Cache for expensive calculations
        self._metrics_cache = {}

        # Loading animation state
        self._loading_angle = 0

        logger.debug("ThreeDEGridDelegate initialized with optimized painting")

    @override
    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        """Paint the 3DE scene thumbnail with custom rendering.

        Args:
            painter: QPainter instance
            option: Style options
            index: Model index to paint
        """
        if not index.isValid():
            return

        painter.save()

        try:
            # Enable antialiasing for smooth rendering
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            # Get item data
            shot_name = index.data(ThreeDERole.ShotRole)
            user = index.data(ThreeDERole.UserRole)
            thumbnail = index.data(ThreeDERole.ThumbnailPixmapRole)
            loading_state = index.data(ThreeDERole.LoadingStateRole)
            is_selected = index.data(ThreeDERole.IsSelectedRole)
            modified_time = index.data(ThreeDERole.ModifiedTimeRole)

            # Determine state
            is_hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
            is_focused = bool(option.state & QStyle.StateFlag.State_HasFocus)

            # Override with model selection state
            if is_selected is not None:
                is_selected = bool(is_selected)
            else:
                is_selected = bool(option.state & QStyle.StateFlag.State_Selected)

            # Draw background
            self._paint_background(painter, option.rect, is_selected, is_hover)

            # Calculate regions
            thumbnail_rect = self._calculate_thumbnail_rect(option.rect)
            text_rect = self._calculate_text_rect(option.rect)

            # Draw thumbnail or loading indicator
            if isinstance(thumbnail, QPixmap) and not thumbnail.isNull():
                self._paint_thumbnail(painter, thumbnail_rect, thumbnail)
            elif loading_state == "loading":
                self._paint_loading_indicator(painter, thumbnail_rect)
            else:
                self._paint_placeholder(painter, thumbnail_rect)

            # Draw text (shot name, user, timestamp)
            self._paint_text(
                painter, text_rect, shot_name, user, modified_time, is_selected
            )

            # Draw focus indicator if focused
            if is_focused:
                self._paint_focus_indicator(painter, option.rect)

        finally:
            painter.restore()

    def _paint_background(
        self, painter: QPainter, rect: QRect, is_selected: bool, is_hover: bool
    ) -> None:
        """Paint the background with state-based colors.

        Args:
            painter: QPainter instance
            rect: Rectangle to paint
            is_selected: Selection state
            is_hover: Hover state
        """
        # Choose colors based on state
        if is_selected:
            bg_color = self._bg_selected_color
            border_color = self._border_selected_color
        elif is_hover:
            bg_color = self._bg_hover_color
            border_color = self._border_hover_color
        else:
            bg_color = self._bg_color
            border_color = self._border_color

        # Create rounded rectangle path
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect), self._border_radius, self._border_radius)

        # Fill background
        painter.fillPath(path, QBrush(bg_color))

        # Draw border
        pen = QPen(border_color, 2 if is_selected else 1)
        painter.setPen(pen)
        painter.drawPath(path)

    def _calculate_thumbnail_rect(self, item_rect: QRect) -> QRect:
        """Calculate the thumbnail display area.

        Args:
            item_rect: Full item rectangle

        Returns:
            Rectangle for thumbnail
        """
        x = item_rect.x() + self._padding
        y = item_rect.y() + self._padding
        size = min(
            item_rect.width() - 2 * self._padding,
            item_rect.height() - 2 * self._padding - self._text_height,
        )
        return QRect(x, y, size, size)

    def _calculate_text_rect(self, item_rect: QRect) -> QRect:
        """Calculate the text display area.

        Args:
            item_rect: Full item rectangle

        Returns:
            Rectangle for text
        """
        x = item_rect.x() + self._padding
        y = item_rect.bottom() - self._text_height
        width = item_rect.width() - 2 * self._padding
        return QRect(x, y, width, self._text_height)

    def _paint_thumbnail(self, painter: QPainter, rect: QRect, pixmap: QPixmap) -> None:
        """Paint the thumbnail image.

        Args:
            painter: QPainter instance
            rect: Rectangle for thumbnail
            pixmap: Thumbnail pixmap
        """
        # Scale pixmap to fit
        scaled = pixmap.scaled(
            rect.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        # Center in rect
        x = rect.x() + (rect.width() - scaled.width()) // 2
        y = rect.y() + (rect.height() - scaled.height()) // 2

        # Draw with rounded corners
        painter.save()
        path = QPainterPath()
        path.addRoundedRect(QRectF(x, y, scaled.width(), scaled.height()), 4, 4)
        painter.setClipPath(path)
        painter.drawPixmap(x, y, scaled)
        painter.restore()

    def _paint_loading_indicator(self, painter: QPainter, rect: QRect) -> None:
        """Paint a loading indicator.

        Args:
            painter: QPainter instance
            rect: Rectangle for indicator
        """
        painter.save()

        # Draw spinning arc
        pen = QPen(self._border_selected_color, 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        # Create smaller rect for arc
        size = min(rect.width(), rect.height()) // 3
        arc_rect = QRect(
            rect.center().x() - size // 2,
            rect.center().y() - size // 2,
            size,
            size,
        )

        # Draw arc (animate by changing start angle)
        painter.drawArc(arc_rect, self._loading_angle * 16, 270 * 16)

        # Update animation angle for next frame
        self._loading_angle = (self._loading_angle + 30) % 360

        painter.restore()

    def _paint_placeholder(self, painter: QPainter, rect: QRect) -> None:
        """Paint a placeholder for missing thumbnail.

        Args:
            painter: QPainter instance
            rect: Rectangle for placeholder
        """
        # Draw simple 3DE icon/text
        painter.setPen(QPen(self._text_color))
        painter.setFont(self._name_font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "3DE")

    def _paint_text(
        self,
        painter: QPainter,
        rect: QRect,
        shot_name: str | None,
        user: str | None,
        modified_time: datetime | None,
        is_selected: bool,
    ) -> None:
        """Paint the text information.

        Args:
            painter: QPainter instance
            rect: Rectangle for text
            shot_name: Shot name to display
            user: User name to display
            modified_time: Modification timestamp
            is_selected: Selection state
        """
        if not shot_name:
            return

        # Set text color
        text_color = self._text_selected_color if is_selected else self._text_color

        # Draw shot name
        painter.setPen(QPen(text_color))
        painter.setFont(self._name_font)

        name_rect = QRect(rect.x(), rect.y() + 2, rect.width(), rect.height() // 2)
        elided_name = painter.fontMetrics().elidedText(
            shot_name,
            Qt.TextElideMode.ElideRight,
            name_rect.width(),
        )
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignCenter, elided_name)

        # Draw user info
        if user:
            painter.setPen(QPen(self._user_color))
            painter.setFont(self._info_font)

            info_rect = QRect(
                rect.x(),
                rect.y() + rect.height() // 2,
                rect.width(),
                rect.height() // 2,
            )
            elided_user = painter.fontMetrics().elidedText(
                f"User: {user}",
                Qt.TextElideMode.ElideRight,
                info_rect.width(),
            )
            painter.drawText(info_rect, Qt.AlignmentFlag.AlignCenter, elided_user)

    def _paint_focus_indicator(self, painter: QPainter, rect: QRect) -> None:
        """Paint focus indicator.

        Args:
            painter: QPainter instance
            rect: Item rectangle
        """
        pen = QPen(self._border_selected_color, 2)
        pen.setStyle(Qt.PenStyle.DotLine)
        painter.setPen(pen)

        focus_rect = rect.adjusted(2, 2, -2, -2)
        painter.drawRoundedRect(focus_rect, self._border_radius, self._border_radius)

    @override
    def sizeHint(
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QSize:
        """Return the size hint for an item.

        Args:
            option: Style options
            index: Model index

        Returns:
            Size hint for the item
        """
        # Return consistent size for grid layout
        total_size = self._thumbnail_size + 2 * self._padding + self._text_height
        return QSize(self._thumbnail_size + 2 * self._padding, total_size)

    def set_thumbnail_size(self, size: int) -> None:
        """Update the thumbnail size.

        Args:
            size: New thumbnail size in pixels
        """
        self._thumbnail_size = size
        # Clear metrics cache since sizes changed
        self._metrics_cache.clear()
