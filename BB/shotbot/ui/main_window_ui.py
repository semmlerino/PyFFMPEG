"""UI setup and layout for MainWindow.

This module handles the visual structure and widget creation for the main window,
separated from business logic and signal handling for better maintainability.
"""

import logging
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from config import Config
from previous_shots_grid import PreviousShotsGrid
from shot_grid_view import ShotGridView
from shot_info_panel import ShotInfoPanel
from shot_item_model import ShotItemModel
from threede_shot_grid import ThreeDEShotGrid

logger = logging.getLogger(__name__)


class MainWindowUI:
    """UI setup helper for MainWindow."""
    
    def __init__(self, parent):
        """Initialize UI helper.
        
        Args:
            parent: MainWindow instance
        """
        self.parent = parent
        self.setup_ui()
        
    def setup_ui(self) -> None:
        """Set up the main UI components."""
        # Main widget and layout
        main_widget = QWidget()
        self.parent.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Create main horizontal splitter
        self.parent.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.parent.main_splitter)
        
        # Left panel (tabbed interface)
        self.setup_left_panel()
        
        # Right panel (shot info)
        self.setup_right_panel()
        
        # Set initial splitter sizes (2:1 ratio)
        self.parent.main_splitter.setSizes([800, 400])
        
        # Status bar
        self.setup_status_bar()
        
        # Window properties
        self.parent.setWindowTitle(f"ShotBot v{Config.APP_VERSION}")
        self.parent.resize(Config.DEFAULT_WINDOW_WIDTH, Config.DEFAULT_WINDOW_HEIGHT)
        
    def setup_left_panel(self) -> None:
        """Set up the left panel with tabs."""
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        
        # Tab widget
        self.parent.tab_widget = QTabWidget()
        left_layout.addWidget(self.parent.tab_widget)
        
        # My Shots tab with Model/View architecture
        self.setup_shots_tab()
        
        # Other 3DE scenes tab
        self.setup_threede_tab()
        
        # Previous/Approved Shots tab
        self.setup_previous_shots_tab()
        
        # Control buttons
        self.setup_control_buttons(left_layout)
        
        self.parent.main_splitter.addWidget(left_widget)
        
    def setup_shots_tab(self) -> None:
        """Set up the My Shots tab using Model/View architecture."""
        # Create Model/View components
        self.parent.shot_item_model = ShotItemModel(
            cache_manager=self.parent.cache_manager
        )
        self.parent.shot_item_model.set_shot_model(self.parent.shot_model)
        
        # Create the view
        self.parent.shot_grid_view = ShotGridView(
            cache_manager=self.parent.cache_manager
        )
        self.parent.shot_grid_view.setModel(self.parent.shot_item_model)
        
        # Add to tab widget
        self.parent.tab_widget.addTab(self.parent.shot_grid_view, "My Shots")
        
        # Store reference for backward compatibility
        self.parent.shot_grid = self.parent.shot_grid_view
        
    def setup_threede_tab(self) -> None:
        """Set up the 3DE scenes tab."""
        self.parent.threede_grid = ThreeDEShotGrid(
            self.parent.threede_model,
            self.parent.cache_manager,
        )
        self.parent.tab_widget.addTab(self.parent.threede_grid, "Other 3DE scenes")
        
    def setup_previous_shots_tab(self) -> None:
        """Set up the Previous/Approved shots tab."""
        self.parent.previous_shots_grid = PreviousShotsGrid(
            self.parent.previous_shots_model,
            self.parent.cache_manager,
        )
        self.parent.tab_widget.addTab(
            self.parent.previous_shots_grid, 
            "Previous/Approved Shots"
        )
        
    def setup_control_buttons(self, layout: QVBoxLayout) -> None:
        """Set up control buttons below tabs."""
        # Control buttons
        controls_layout = QHBoxLayout()
        
        self.parent.refresh_button = QPushButton("Refresh")
        self.parent.refresh_button.setToolTip("Refresh shot list (F5)")
        controls_layout.addWidget(self.parent.refresh_button)
        
        self.parent.launcher_button = QPushButton("Manage Launchers...")
        self.parent.launcher_button.setToolTip("Create and manage custom launchers")
        controls_layout.addWidget(self.parent.launcher_button)
        
        controls_layout.addStretch()
        
        # Thumbnail size controls
        size_label = QLabel("Thumbnail:")
        controls_layout.addWidget(size_label)
        
        self.parent.decrease_size_button = QPushButton("-")
        self.parent.decrease_size_button.setMaximumWidth(30)
        self.parent.decrease_size_button.setToolTip("Decrease thumbnail size")
        controls_layout.addWidget(self.parent.decrease_size_button)
        
        self.parent.increase_size_button = QPushButton("+")
        self.parent.increase_size_button.setMaximumWidth(30)
        self.parent.increase_size_button.setToolTip("Increase thumbnail size")
        controls_layout.addWidget(self.parent.increase_size_button)
        
        layout.addLayout(controls_layout)
        
    def setup_right_panel(self) -> None:
        """Set up the right panel with shot info."""
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
        # Shot info panel
        self.parent.shot_info_panel = ShotInfoPanel(self.parent.cache_manager)
        right_layout.addWidget(self.parent.shot_info_panel)
        
        # Custom launcher buttons section
        launcher_section = QFrame()
        launcher_section.setFrameStyle(QFrame.Shape.Box)
        launcher_layout = QVBoxLayout(launcher_section)
        
        launcher_label = QLabel("Custom Launchers:")
        launcher_label.setStyleSheet("font-weight: bold;")
        launcher_layout.addWidget(launcher_label)
        
        # Container for dynamic launcher buttons
        self.parent.launcher_buttons_container = QWidget()
        self.parent.launcher_buttons_layout = QVBoxLayout(
            self.parent.launcher_buttons_container
        )
        self.parent.launcher_buttons_layout.setSpacing(5)
        launcher_layout.addWidget(self.parent.launcher_buttons_container)
        
        # Add stretch to push buttons to top
        launcher_layout.addStretch()
        
        right_layout.addWidget(launcher_section)
        right_layout.addStretch()
        
        self.parent.main_splitter.addWidget(right_widget)
        
    def setup_status_bar(self) -> None:
        """Set up the status bar."""
        self.parent.status_bar = QStatusBar()
        self.parent.setStatusBar(self.parent.status_bar)
        
        # Create status labels
        self.parent.status_label = QLabel("Ready")
        self.parent.status_bar.addWidget(self.parent.status_label)
        
        # Create permanent widgets for the right side
        self.parent.shot_count_label = QLabel("")
        self.parent.status_bar.addPermanentWidget(self.parent.shot_count_label)
        
        separator = QFrame()
        separator.setFrameStyle(QFrame.Shape.VLine | QFrame.Shadow.Sunken)
        self.parent.status_bar.addPermanentWidget(separator)
        
        self.parent.cache_status_label = QLabel("")
        self.parent.status_bar.addPermanentWidget(self.parent.cache_status_label)