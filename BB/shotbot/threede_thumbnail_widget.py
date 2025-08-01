"""Enhanced thumbnail widget for displaying 3DE scene thumbnails with additional info."""

from enum import Enum
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from cache_manager import CacheManager, ThumbnailCacheLoader
from config import Config
from threede_scene_model import ThreeDEScene
from thumbnail_loading_indicator import ThumbnailLoadingIndicator


class LoadingState(Enum):
    """Thumbnail loading states."""

    IDLE = "idle"
    LOADING = "loading"
    LOADED = "loaded"
    FAILED = "failed"


class ThreeDEThumbnailLoader(QRunnable):
    """Runnable for loading thumbnails in background."""

    class Signals(QObject):
        loaded = Signal(object, QPixmap)  # widget, pixmap
        failed = Signal(object)  # widget

    def __init__(self, widget: "ThreeDEThumbnailWidget", path: Path):
        super().__init__()
        self.widget = widget
        self.path = path
        self.signals = self.Signals()

    def run(self):
        """Load the thumbnail."""
        try:
            pixmap = QPixmap(str(self.path))
            if not pixmap.isNull():
                self.signals.loaded.emit(self.widget, pixmap)
            else:
                self.signals.failed.emit(self.widget)
        except Exception:
            self.signals.failed.emit(self.widget)


class ThreeDEThumbnailWidget(QFrame):
    """Widget displaying a 3DE scene thumbnail with shot, user, and plate info."""

    # Signals
    clicked = Signal(object)  # ThreeDEScene
    double_clicked = Signal(object)  # ThreeDEScene

    # Shared cache manager
    _cache_manager = CacheManager()

    @classmethod
    def set_cache_manager(cls, cache_manager: CacheManager):
        """Set the shared cache manager for all thumbnail widgets."""
        cls._cache_manager = cache_manager

    def __init__(self, scene: ThreeDEScene, size: int = Config.DEFAULT_THUMBNAIL_SIZE):
        super().__init__()
        self.scene = scene
        self._thumbnail_size = size
        self._selected = False
        self._pixmap: Optional[QPixmap] = None
        self._loading_state = LoadingState.IDLE
        self._setup_ui()
        self._load_thumbnail()

    def _setup_ui(self):
        """Set up the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(3)

        # Thumbnail label
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setObjectName("thumbnail")
        self.thumbnail_label.setFixedSize(self._thumbnail_size, self._thumbnail_size)
        self.thumbnail_label.setScaledContents(True)
        self.thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Set placeholder
        self._set_placeholder()

        # Create a container for thumbnail and loading indicator
        self.thumbnail_container = QWidget()
        self.thumbnail_container.setFixedSize(
            self._thumbnail_size, self._thumbnail_size
        )
        container_layout = QVBoxLayout(self.thumbnail_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.addWidget(self.thumbnail_label)

        # Loading indicator (overlay)
        self.loading_indicator = ThumbnailLoadingIndicator(self.thumbnail_container)
        self.loading_indicator.move(
            (self._thumbnail_size - 40) // 2,  # Center horizontally
            (self._thumbnail_size - 40) // 2,  # Center vertically
        )
        self.loading_indicator.hide()

        layout.addWidget(self.thumbnail_container)

        # Shot name label (larger, bold)
        self.shot_label = QLabel(self.scene.full_name)
        self.shot_label.setObjectName("shot")
        self.shot_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.shot_label.setWordWrap(True)
        shot_font = self.shot_label.font()
        shot_font.setPointSize(10)
        shot_font.setBold(True)
        self.shot_label.setFont(shot_font)

        layout.addWidget(self.shot_label)

        # User label (smaller)
        self.user_label = QLabel(self.scene.user)
        self.user_label.setObjectName("user")
        self.user_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        user_font = self.user_label.font()
        user_font.setPointSize(8)
        self.user_label.setFont(user_font)

        layout.addWidget(self.user_label)

        # Plate label (highlighted)
        self.plate_label = QLabel(self.scene.plate)
        self.plate_label.setObjectName("plate")
        self.plate_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        plate_font = self.plate_label.font()
        plate_font.setPointSize(9)
        plate_font.setBold(True)
        self.plate_label.setFont(plate_font)

        layout.addWidget(self.plate_label)

        # Set cursor
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # Apply initial style
        self._update_style()

    def _set_placeholder(self):
        """Set placeholder image."""
        placeholder = QPixmap(self._thumbnail_size, self._thumbnail_size)
        placeholder.fill(QColor(Config.PLACEHOLDER_COLOR))

        # Draw text on placeholder
        painter = QPainter(placeholder)
        painter.setPen(QColor("#888"))
        painter.setFont(QFont("Arial", 12))
        painter.drawText(placeholder.rect(), Qt.AlignmentFlag.AlignCenter, "No Image")
        painter.end()

        self.thumbnail_label.setPixmap(placeholder)

    def _load_thumbnail(self):
        """Load thumbnail from cache or source."""
        # Set loading state and show indicator
        self._loading_state = LoadingState.LOADING
        self.loading_indicator.start()

        # First check cache
        cache_path = self._cache_manager.get_cached_thumbnail(
            self.scene.show, self.scene.sequence, self.scene.shot
        )

        if cache_path and cache_path.exists():
            # Load from cache
            loader = ThreeDEThumbnailLoader(self, cache_path)
            loader.signals.loaded.connect(self._on_thumbnail_loaded)
            loader.signals.failed.connect(self._on_thumbnail_failed)
            QThreadPool.globalInstance().start(loader)
        else:
            # Try to load from source
            thumb_path = self.scene.get_thumbnail_path()
            if thumb_path and thumb_path.exists():
                # Load in background thread
                loader = ThreeDEThumbnailLoader(self, thumb_path)
                loader.signals.loaded.connect(self._on_thumbnail_loaded)
                loader.signals.failed.connect(self._on_thumbnail_failed)
                QThreadPool.globalInstance().start(loader)

                # Also cache it for next time
                cache_loader = ThumbnailCacheLoader(
                    self._cache_manager,
                    thumb_path,
                    self.scene.show,
                    self.scene.sequence,
                    self.scene.shot,
                )
                QThreadPool.globalInstance().start(cache_loader)
            else:
                # No thumbnail available
                self._on_thumbnail_failed(self)

    def _on_thumbnail_loaded(self, widget: "ThreeDEThumbnailWidget", pixmap: QPixmap):
        """Handle loaded thumbnail."""
        if widget == self:
            self._loading_state = LoadingState.LOADED
            self.loading_indicator.stop()
            self._pixmap = pixmap
            self._update_thumbnail()

    def _on_thumbnail_failed(self, widget: "ThreeDEThumbnailWidget"):
        """Handle failed thumbnail loading."""
        if widget == self:
            self._loading_state = LoadingState.FAILED
            self.loading_indicator.stop()
            # Keep the placeholder image

    def _update_thumbnail(self):
        """Update thumbnail display."""
        if self._pixmap:
            scaled = self._pixmap.scaled(
                QSize(self._thumbnail_size, self._thumbnail_size),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.thumbnail_label.setPixmap(scaled)

    def set_size(self, size: int):
        """Set thumbnail size."""
        self._thumbnail_size = size
        self.thumbnail_label.setFixedSize(size, size)
        self.thumbnail_container.setFixedSize(size, size)

        # Reposition loading indicator
        self.loading_indicator.move(
            (size - 40) // 2,  # Center horizontally
            (size - 40) // 2,  # Center vertically
        )

        if self._pixmap:
            self._update_thumbnail()
        else:
            self._set_placeholder()

    def set_selected(self, selected: bool):
        """Set selection state."""
        self._selected = selected
        self._update_style()

    def _update_style(self):
        """Update widget style based on state."""
        if self._selected:
            # Use bright cyan for selection with distinct plate color
            self.setStyleSheet("""
                ThreeDEThumbnailWidget {
                    background-color: #0d7377;
                    border: 3px solid #14ffec;
                    border-radius: 8px;
                }
                QLabel#shot {
                    color: #14ffec;
                    font-weight: bold;
                    background-color: transparent;
                }
                QLabel#user {
                    color: #aaffff;
                    background-color: transparent;
                }
                QLabel#plate {
                    color: #ffff14;
                    font-weight: bold;
                    background-color: #0d7377;
                    padding: 2px 6px;
                    border-radius: 3px;
                }
                QLabel#thumbnail {
                    border: 1px solid #14ffec;
                    border-radius: 4px;
                    padding: 2px;
                    background-color: transparent;
                }
            """)
        else:
            self.setStyleSheet("""
                ThreeDEThumbnailWidget {
                    background-color: #2b2b2b;
                    border: 2px solid #444;
                    border-radius: 6px;
                }
                ThreeDEThumbnailWidget:hover {
                    background-color: #3a3a3a;
                    border: 2px solid #888;
                }
                QLabel#shot {
                    color: white;
                    font-weight: bold;
                    background-color: transparent;
                }
                QLabel#user {
                    color: #ccc;
                    background-color: transparent;
                }
                QLabel#plate {
                    color: #ffd700;
                    font-weight: bold;
                    background-color: #444;
                    padding: 2px 6px;
                    border-radius: 3px;
                }
                QLabel {
                    border: none;
                    background-color: transparent;
                }
            """)

        # Update the widget display
        self.update()

    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.scene)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """Handle double click."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self.scene)
