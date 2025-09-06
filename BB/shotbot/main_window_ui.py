"""UI setup and layout management for MainWindow.

This module extracts UI setup logic from MainWindow to improve maintainability
and reduce complexity. Handles widget creation, layout setup, and menu configuration.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QMainWindow,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from base_shot_model import BaseShotModel
    from cache_manager import CacheManager
    from launcher_manager import LauncherManager
    from log_viewer import LogViewer
    from previous_shots_item_model import PreviousShotsItemModel
    from threede_item_model import ThreeDEItemModel

logger = logging.getLogger(__name__)


class MainWindowUI:
    """UI setup and layout management for MainWindow.
    
    This class encapsulates all UI creation logic, keeping the main window
    focused on coordination and business logic.
    """
    
    def __init__(self, main_window: QMainWindow) -> None:
        """Initialize UI manager for the given main window.
        
        Args:
            main_window: The QMainWindow instance to set up
        """
        self.main_window = main_window
        
        # UI components will be created during setup
        self.central_widget: QWidget | None = None
        self.main_splitter: QSplitter | None = None
        self.left_panel: QWidget | None = None
        self.right_panel: QWidget | None = None
        self.tab_widget: QTabWidget | None = None
        self.status_bar: QStatusBar | None = None
        
        # Checkbox references for external access
        self.delete_source_checkbox: QCheckBox | None = None
        self.hardware_decode_checkbox: QCheckBox | None = None
        
    def setup_ui(
        self,
        cache_manager: CacheManager,
        shot_model: BaseShotModel,
        threede_item_model: ThreeDEItemModel,
        previous_shots_model: PreviousShotsItemModel,
        launcher_manager: LauncherManager,
        log_viewer: LogViewer,
    ) -> dict[str, QWidget]:
        """Set up the complete UI layout and create all widgets.
        
        Args:
            cache_manager: Cache manager instance
            shot_model: Shot data model
            threede_item_model: 3DE scene model
            previous_shots_model: Previous shots model
            launcher_manager: Launcher management
            log_viewer: Log viewer widget
            
        Returns:
            Dictionary mapping component names to widget instances
        """
        logger.debug("Setting up main window UI")
        
        # Create central widget and main layout
        self.central_widget = QWidget()
        self.main_window.setCentralWidget(self.central_widget)
        
        # Create main horizontal splitter
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout = QHBoxLayout(self.central_widget)
        main_layout.addWidget(self.main_splitter)
        
        # Create left and right panels
        self.left_panel = self._create_left_panel(
            cache_manager, shot_model, threede_item_model
        )
        self.right_panel = self._create_right_panel(
            previous_shots_model, launcher_manager, log_viewer
        )
        
        # Add panels to splitter
        self.main_splitter.addWidget(self.left_panel)
        self.main_splitter.addWidget(self.right_panel)
        
        # Set initial splitter proportions (60% left, 40% right)
        self.main_splitter.setSizes([600, 400])
        
        # Create menu and status bar
        self._setup_menu()
        self._setup_status_bar()
        self._setup_accessibility()
        
        # Collect widget references for external access
        widgets = self._collect_widget_references()
        
        logger.info("Main window UI setup complete")
        return widgets
    
    def _create_left_panel(
        self,
        cache_manager: CacheManager,
        shot_model: BaseShotModel,
        threede_item_model: ThreeDEItemModel,
    ) -> QWidget:
        """Create the left panel containing shot grids and info panel.
        
        Args:
            cache_manager: Cache manager instance
            shot_model: Shot data model
            threede_item_model: 3DE scene model
            
        Returns:
            Left panel widget
        """
        from shot_grid_view import ShotGridView
        from shot_info_panel import ShotInfoPanel
        from threede_grid_view import ThreeDEGridView
        
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        # Create tab widget for shot grids
        tab_widget = QTabWidget()
        
        # My Shots tab
        shot_grid_view = ShotGridView(model=shot_model.shot_item_model, cache_manager=cache_manager)
        tab_widget.addTab(shot_grid_view, "My Shots")
        
        # 3DE Scenes tab  
        threede_grid_view = ThreeDEGridView(threede_item_model, cache_manager)
        tab_widget.addTab(threede_grid_view, "Other 3DE Scenes")
        
        # Create shot info panel
        info_panel = ShotInfoPanel(cache_manager)
        
        # Create vertical splitter for tabs and info panel
        vertical_splitter = QSplitter(Qt.Orientation.Vertical)
        vertical_splitter.addWidget(tab_widget)
        vertical_splitter.addWidget(info_panel)
        vertical_splitter.setSizes([700, 300])  # 70% tabs, 30% info
        
        left_layout.addWidget(vertical_splitter)
        
        return left_panel
    
    def _create_right_panel(
        self,
        previous_shots_model: PreviousShotsItemModel,
        launcher_manager: LauncherManager,
        log_viewer: LogViewer,
    ) -> QWidget:
        """Create the right panel with previous shots and log viewer.
        
        Args:
            previous_shots_model: Previous shots model
            launcher_manager: Launcher management
            log_viewer: Log viewer widget
            
        Returns:
            Right panel widget
        """
        from previous_shots_view import PreviousShotsView
        
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        # Create tab widget for right panel
        self.tab_widget = QTabWidget()
        
        # Previous Shots tab
        previous_shots_view = PreviousShotsView(
            model=previous_shots_model,
            launcher_manager=launcher_manager
        )
        self.tab_widget.addTab(previous_shots_view, "Previous Shots")
        
        # Log Viewer tab
        self.tab_widget.addTab(log_viewer, "Logs")
        
        # Options panel
        options_panel = self._create_options_panel()
        
        # Add components to layout
        right_layout.addWidget(self.tab_widget)
        right_layout.addWidget(options_panel)
        
        return right_panel
    
    def _create_options_panel(self) -> QWidget:
        """Create options panel with checkboxes and controls.
        
        Returns:
            Options panel widget
        """
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout(options_group)
        
        # Delete source files checkbox
        self.delete_source_checkbox = QCheckBox("Delete source files after launch")
        self.delete_source_checkbox.setToolTip(
            "When launching applications, delete source files that have been processed"
        )
        options_layout.addWidget(self.delete_source_checkbox)
        
        # Hardware decode checkbox
        self.hardware_decode_checkbox = QCheckBox("Use hardware decode when available")
        self.hardware_decode_checkbox.setChecked(True)
        self.hardware_decode_checkbox.setToolTip(
            "Use GPU acceleration for video decoding when supported"
        )
        options_layout.addWidget(self.hardware_decode_checkbox)
        
        return options_group
    
    def _setup_menu(self) -> None:
        """Set up the application menu bar."""
        menubar = self.main_window.menuBar()
        if not menubar:
            return
            
        # File menu
        file_menu = menubar.addMenu("&File")
        
        # Refresh action
        refresh_action = QAction("&Refresh", self.main_window)
        refresh_action.setShortcut(QKeySequence("F5"))
        refresh_action.setToolTip("Refresh shot data (F5)")
        file_menu.addAction(refresh_action)
        
        file_menu.addSeparator()
        
        # Settings action
        settings_action = QAction("&Settings...", self.main_window)
        settings_action.setShortcut(QKeySequence.StandardKey.Preferences)
        settings_action.setToolTip("Open application settings")
        file_menu.addAction(settings_action)
        
        file_menu.addSeparator()
        
        # Exit action
        exit_action = QAction("E&xit", self.main_window)
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.setToolTip("Exit application")
        file_menu.addAction(exit_action)
        
        # View menu
        view_menu = menubar.addMenu("&View")
        
        # Thumbnail size actions
        increase_size_action = QAction("&Increase Thumbnail Size", self.main_window)
        increase_size_action.setShortcut(QKeySequence("Ctrl++"))
        view_menu.addAction(increase_size_action)
        
        decrease_size_action = QAction("&Decrease Thumbnail Size", self.main_window)
        decrease_size_action.setShortcut(QKeySequence("Ctrl+-"))
        view_menu.addAction(decrease_size_action)
        
        # Help menu
        help_menu = menubar.addMenu("&Help")
        
        # About action
        about_action = QAction("&About ShotBot", self.main_window)
        about_action.setToolTip("About this application")
        help_menu.addAction(about_action)
        
        # Store references for signal connection
        self.main_window.refresh_action = refresh_action
        self.main_window.settings_action = settings_action
        self.main_window.exit_action = exit_action
        self.main_window.increase_size_action = increase_size_action
        self.main_window.decrease_size_action = decrease_size_action
        self.main_window.about_action = about_action
    
    def _setup_status_bar(self) -> None:
        """Set up the status bar."""
        self.status_bar = QStatusBar()
        self.main_window.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")
        
    def _setup_accessibility(self) -> None:
        """Set up accessibility features."""
        self.main_window.setWindowTitle("ShotBot - VFX Shot Browser")
        
        # Set window properties
        self.main_window.resize(1400, 900)
        self.main_window.setMinimumSize(800, 600)
        
        # Set object names for testing/styling
        if self.central_widget:
            self.central_widget.setObjectName("central_widget")
        if self.main_splitter:
            self.main_splitter.setObjectName("main_splitter")
        if self.left_panel:
            self.left_panel.setObjectName("left_panel")
        if self.right_panel:
            self.right_panel.setObjectName("right_panel")
    
    def _collect_widget_references(self) -> dict[str, QWidget]:
        """Collect references to created widgets for external access.
        
        Returns:
            Dictionary mapping widget names to instances
        """
        # Find widgets by traversing the UI tree
        widgets = {}
        
        if self.central_widget:
            # Find shot grid view
            shot_grid_view = self.central_widget.findChild(QWidget, "shot_grid_view")
            if shot_grid_view:
                widgets["shot_grid_view"] = shot_grid_view
                
            # Find 3DE grid view
            threede_grid_view = self.central_widget.findChild(QWidget, "threede_grid_view")
            if threede_grid_view:
                widgets["threede_grid_view"] = threede_grid_view
                
            # Find info panel
            info_panel = self.central_widget.findChild(QWidget, "info_panel")
            if info_panel:
                widgets["info_panel"] = info_panel
                
            # Find previous shots view
            previous_shots_view = self.central_widget.findChild(QWidget, "previous_shots_view")
            if previous_shots_view:
                widgets["previous_shots_view"] = previous_shots_view
        
        # Add direct references
        if self.tab_widget:
            widgets["tab_widget"] = self.tab_widget
        if self.delete_source_checkbox:
            widgets["delete_source_checkbox"] = self.delete_source_checkbox
        if self.hardware_decode_checkbox:
            widgets["hardware_decode_checkbox"] = self.hardware_decode_checkbox
            
        return widgets
    
    def update_status(self, message: str) -> None:
        """Update status bar message.
        
        Args:
            message: Status message to display
        """
        if self.status_bar:
            self.status_bar.showMessage(message)
    
    def get_main_splitter_sizes(self) -> list[int]:
        """Get current splitter sizes for saving state.
        
        Returns:
            List of splitter sizes
        """
        if self.main_splitter:
            return self.main_splitter.sizes()
        return []
    
    def set_main_splitter_sizes(self, sizes: list[int]) -> None:
        """Restore splitter sizes from saved state.
        
        Args:
            sizes: List of splitter sizes to restore
        """
        if self.main_splitter and sizes:
            self.main_splitter.setSizes(sizes)