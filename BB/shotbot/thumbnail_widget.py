"""Thumbnail widget for displaying shot thumbnails."""

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QMenu

from config import Config
from shot_model import Shot
from thumbnail_widget_base import ThumbnailWidgetBase

# Set up logger for this module
logger = logging.getLogger(__name__)


class ThumbnailWidget(ThumbnailWidgetBase):
    """Widget displaying a shot thumbnail and name."""

    # Signals - maintain backward compatibility
    clicked = Signal(object)  # Shot
    double_clicked = Signal(object)  # Shot

    def __init__(self, shot: Shot, size: int = Config.DEFAULT_THUMBNAIL_SIZE):
        # Store shot reference for backward compatibility
        self.shot = shot
        super().__init__(shot, size)

    def _setup_custom_ui(self):
        """Set up custom UI elements specific to shot thumbnails."""
        # Shot name label
        self.name_label = QLabel(self.shot.full_name)
        self.name_label.setObjectName("name")  # For CSS targeting
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setWordWrap(True)
        font = self.name_label.font()
        font.setPointSize(9)
        self.name_label.setFont(font)
        
        self.layout.addWidget(self.name_label)
        
        # Apply initial style
        self._update_style()





    def _get_selected_style(self) -> str:
        """Get the CSS style for selected state."""
        return """
            ThumbnailWidget {
                background-color: #0d7377;
                border: 3px solid #14ffec;
                border-radius: 8px;
            }
            QLabel#name {
                color: #14ffec;
                font-weight: bold;
            }
            QLabel#thumbnail {
                border: 1px solid #14ffec;
                border-radius: 4px;
                padding: 2px;
            }
            QLabel {
                background-color: transparent;
            }
        """
    
    def _get_unselected_style(self) -> str:
        """Get the CSS style for unselected state."""
        return """
            ThumbnailWidget {
                background-color: #2b2b2b;
                border: 2px solid #444;
                border-radius: 6px;
            }
            ThumbnailWidget:hover {
                background-color: #3a3a3a;
                border: 2px solid #888;
            }
            QLabel {
                border: none;
                background-color: transparent;
            }
        """


    def _create_context_menu(self) -> QMenu:
        """Create and return the context menu for this widget."""
        menu = QMenu(self)
        
        # Add "Open Shot Folder" action
        open_folder_action = menu.addAction("Open Shot Folder")
        open_folder_action.triggered.connect(self._open_shot_folder)
        
        return menu
