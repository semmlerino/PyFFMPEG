"""Menu and toolbar setup for MainWindow.

This module handles menu bar creation, action setup, and toolbar configuration,
separated from the main window for better organization.
"""

import logging
from typing import Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMenu

from config import Config

logger = logging.getLogger(__name__)


class MainWindowMenus:
    """Menu and toolbar helper for MainWindow."""
    
    def __init__(self, parent):
        """Initialize menu helper.
        
        Args:
            parent: MainWindow instance
        """
        self.parent = parent
        self.setup_menu()
        
    def setup_menu(self) -> None:
        """Set up the menu bar."""
        menubar = self.parent.menuBar()
        
        # File menu
        self.setup_file_menu(menubar)
        
        # View menu
        self.setup_view_menu(menubar)
        
        # Launch menu
        self.setup_launch_menu(menubar)
        
        # Tools menu
        self.setup_tools_menu(menubar)
        
        # Help menu
        self.setup_help_menu(menubar)
        
    def setup_file_menu(self, menubar) -> None:
        """Set up the File menu."""
        file_menu = menubar.addMenu("&File")
        
        # Refresh action
        self.parent.refresh_action = QAction("&Refresh", self.parent)
        self.parent.refresh_action.setShortcut(QKeySequence.StandardKey.Refresh)
        self.parent.refresh_action.setStatusTip("Refresh shot list")
        file_menu.addAction(self.parent.refresh_action)
        
        file_menu.addSeparator()
        
        # Settings actions
        import_settings_action = QAction("&Import Settings...", self.parent)
        import_settings_action.setStatusTip("Import settings from file")
        import_settings_action.triggered.connect(self.parent._import_settings)
        file_menu.addAction(import_settings_action)
        
        export_settings_action = QAction("&Export Settings...", self.parent)
        export_settings_action.setStatusTip("Export settings to file")
        export_settings_action.triggered.connect(self.parent._export_settings)
        file_menu.addAction(export_settings_action)
        
        file_menu.addSeparator()
        
        # Preferences action
        preferences_action = QAction("&Preferences...", self.parent)
        preferences_action.setShortcut(QKeySequence("Ctrl+,"))
        preferences_action.setStatusTip("Open application preferences")
        preferences_action.triggered.connect(self.parent._show_preferences)
        file_menu.addAction(preferences_action)
        
        file_menu.addSeparator()
        
        # Exit action
        exit_action = QAction("E&xit", self.parent)
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.setStatusTip("Exit application")
        exit_action.triggered.connect(self.parent.close)
        file_menu.addAction(exit_action)
        
    def setup_view_menu(self, menubar) -> None:
        """Set up the View menu."""
        view_menu = menubar.addMenu("&View")
        
        # Thumbnail size actions
        increase_action = QAction("&Increase Thumbnail Size", self.parent)
        increase_action.setShortcut(QKeySequence.StandardKey.ZoomIn)
        increase_action.triggered.connect(self.parent._increase_thumbnail_size)
        view_menu.addAction(increase_action)
        
        decrease_action = QAction("&Decrease Thumbnail Size", self.parent)
        decrease_action.setShortcut(QKeySequence.StandardKey.ZoomOut)
        decrease_action.triggered.connect(self.parent._decrease_thumbnail_size)
        view_menu.addAction(decrease_action)
        
        view_menu.addSeparator()
        
        # Log viewer
        log_action = QAction("&Command History...", self.parent)
        log_action.setShortcut(QKeySequence("Ctrl+L"))
        log_action.setStatusTip("View command execution history")
        log_action.triggered.connect(
            lambda: self.parent.log_viewer.show() if hasattr(self.parent, 'log_viewer') else None
        )
        view_menu.addAction(log_action)
        
        view_menu.addSeparator()
        
        # Reset layout
        reset_layout_action = QAction("&Reset Layout", self.parent)
        reset_layout_action.setStatusTip("Reset window layout to defaults")
        reset_layout_action.triggered.connect(self.parent._reset_layout)
        view_menu.addAction(reset_layout_action)
        
    def setup_launch_menu(self, menubar) -> None:
        """Set up the Launch menu."""
        self.parent.launch_menu = menubar.addMenu("&Launch")
        
        # Standard applications from config
        self.parent.app_actions = {}
        for app_name, app_cmd in Config.APPS.items():
            action = QAction(f"&{app_name.title()}", self.parent)
            action.setStatusTip(f"Launch {app_name}")
            action.triggered.connect(lambda checked, a=app_name: self.parent._launch_app(a))
            self.parent.launch_menu.addAction(action)
            self.parent.app_actions[app_name] = action
            
        # Separator before custom launchers
        self.parent.launch_menu.addSeparator()
        
        # Placeholder for custom launchers (populated dynamically)
        self.parent.custom_launcher_separator = self.parent.launch_menu.addSeparator()
        self.parent.custom_launcher_actions: Dict[str, QAction] = {}
        
        # Manage launchers action
        self.parent.launch_menu.addSeparator()
        manage_action = QAction("&Manage Launchers...", self.parent)
        manage_action.setStatusTip("Create and manage custom launchers")
        manage_action.triggered.connect(self.parent._show_launcher_manager)
        self.parent.launch_menu.addAction(manage_action)
        
    def setup_tools_menu(self, menubar) -> None:
        """Set up the Tools menu."""
        tools_menu = menubar.addMenu("&Tools")
        
        # Cache management
        clear_cache_action = QAction("&Clear Cache", self.parent)
        clear_cache_action.setStatusTip("Clear all cached data")
        clear_cache_action.triggered.connect(
            lambda: self.parent.cache_manager.clear_cache() if self.parent.cache_manager else None
        )
        tools_menu.addAction(clear_cache_action)
        
        validate_cache_action = QAction("&Validate Cache", self.parent)
        validate_cache_action.setStatusTip("Check cache integrity")
        validate_cache_action.triggered.connect(
            lambda: self.parent.cache_manager.validate_cache() if self.parent.cache_manager else None
        )
        tools_menu.addAction(validate_cache_action)
        
        tools_menu.addSeparator()
        
        # Debug actions (only in debug mode)
        if Config.DEBUG_MODE:
            self.add_debug_actions(tools_menu)
            
    def setup_help_menu(self, menubar) -> None:
        """Set up the Help menu."""
        help_menu = menubar.addMenu("&Help")
        
        # Keyboard shortcuts
        shortcuts_action = QAction("&Keyboard Shortcuts", self.parent)
        shortcuts_action.setShortcut(QKeySequence.StandardKey.HelpContents)
        shortcuts_action.triggered.connect(self.parent._show_shortcuts)
        help_menu.addAction(shortcuts_action)
        
        help_menu.addSeparator()
        
        # About action
        about_action = QAction("&About ShotBot", self.parent)
        about_action.triggered.connect(self.parent._show_about)
        help_menu.addAction(about_action)
        
    def add_debug_actions(self, tools_menu: QMenu) -> None:
        """Add debug actions to Tools menu.
        
        Args:
            tools_menu: Tools menu to add actions to
        """
        debug_menu = tools_menu.addMenu("&Debug")
        
        # Force refresh without cache
        force_refresh_action = QAction("Force &Refresh (No Cache)", self.parent)
        force_refresh_action.triggered.connect(
            lambda: self.parent.shot_model.refresh_shots(force=True)
        )
        debug_menu.addAction(force_refresh_action)
        
        # Show cache statistics
        cache_stats_action = QAction("Show Cache &Statistics", self.parent)
        cache_stats_action.triggered.connect(self.show_cache_stats)
        debug_menu.addAction(cache_stats_action)
        
        # Dump model data
        dump_model_action = QAction("&Dump Model Data", self.parent)
        dump_model_action.triggered.connect(self.dump_model_data)
        debug_menu.addAction(dump_model_action)
        
    def show_cache_stats(self) -> None:
        """Show cache statistics in debug mode."""
        if not self.parent.cache_manager:
            return
            
        from PySide6.QtWidgets import QMessageBox
        
        stats = self.parent.cache_manager.get_memory_usage()
        failed = self.parent.cache_manager.get_failed_attempts_status()
        
        message = f"Cache Statistics:\n\n"
        message += f"Memory Usage: {stats['current_mb']:.1f} MB / {stats['max_mb']} MB\n"
        message += f"Cached Items: {stats['cached_count']}\n"
        message += f"Failed Attempts: {len(failed)}\n"
        
        QMessageBox.information(self.parent, "Cache Statistics", message)
        
    def dump_model_data(self) -> None:
        """Dump model data for debugging."""
        logger.debug("=== Model Data Dump ===")
        logger.debug(f"Shot Model: {len(self.parent.shot_model.shots)} shots")
        logger.debug(f"3DE Model: {len(self.parent.threede_model.scenes)} scenes")
        logger.debug(f"Previous Shots Model: {self.parent.previous_shots_model.rowCount()} shots")
        logger.debug("======================")