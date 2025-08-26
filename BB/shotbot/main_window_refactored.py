"""Refactored MainWindow for ShotBot application.

This refactored version uses modular components for better maintainability and
implements lazy loading to improve import performance. The MainWindow coordinates
between UI setup, signal handling, menu creation, and business logic modules.
"""

import logging
from typing import Optional, Dict, Any

from PySide6.QtCore import QMutex, QMutexLocker, Qt, QTimer
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QMainWindow,
    QMessageBox,
    QMenu,
)

from cache_manager import CacheManager
from config import Config
from shot_model import Shot, ShotModel
from threede_scene_model import ThreeDEScene, ThreeDESceneModel

# Lazy imports - loaded on demand
_CommandLauncher = None
_LauncherManager = None
_LauncherManagerDialog = None
_LogViewer = None
_NotificationManager = None
_NotificationType = None
_PreviousShotsModel = None
_ProgressManager = None
_SettingsDialog = None
_SettingsManager = None
_ThreeDESceneWorker = None

# UI modules
from ui.main_window_ui import MainWindowUI
from ui.main_window_menus import MainWindowMenus
from ui.main_window_signals import MainWindowSignals

logger = logging.getLogger(__name__)


def _lazy_import_command_launcher():
    """Lazy import CommandLauncher."""
    global _CommandLauncher
    if _CommandLauncher is None:
        from command_launcher import CommandLauncher
        _CommandLauncher = CommandLauncher
    return _CommandLauncher


def _lazy_import_launcher_manager():
    """Lazy import LauncherManager."""
    global _LauncherManager
    if _LauncherManager is None:
        from launcher_manager import LauncherManager
        _LauncherManager = LauncherManager
    return _LauncherManager


def _lazy_import_launcher_dialog():
    """Lazy import LauncherManagerDialog."""
    global _LauncherManagerDialog
    if _LauncherManagerDialog is None:
        from launcher_dialog import LauncherManagerDialog
        _LauncherManagerDialog = LauncherManagerDialog
    return _LauncherManagerDialog


def _lazy_import_notification():
    """Lazy import notification components."""
    global _NotificationManager, _NotificationType
    if _NotificationManager is None:
        from notification_manager import NotificationManager, NotificationType
        _NotificationManager = NotificationManager
        _NotificationType = NotificationType
    return _NotificationManager, _NotificationType


def _lazy_import_progress():
    """Lazy import ProgressManager."""
    global _ProgressManager
    if _ProgressManager is None:
        from progress_manager import ProgressManager
        _ProgressManager = ProgressManager
    return _ProgressManager


def _lazy_import_settings():
    """Lazy import settings components."""
    global _SettingsManager, _SettingsDialog
    if _SettingsManager is None:
        from settings_manager import SettingsManager
        from settings_dialog import SettingsDialog
        _SettingsManager = SettingsManager
        _SettingsDialog = SettingsDialog
    return _SettingsManager, _SettingsDialog


def _lazy_import_previous_shots():
    """Lazy import PreviousShotsModel."""
    global _PreviousShotsModel
    if _PreviousShotsModel is None:
        from previous_shots_model import PreviousShotsModel
        _PreviousShotsModel = PreviousShotsModel
    return _PreviousShotsModel


def _lazy_import_threede_worker():
    """Lazy import ThreeDESceneWorker."""
    global _ThreeDESceneWorker
    if _ThreeDESceneWorker is None:
        from threede_scene_worker import ThreeDESceneWorker
        _ThreeDESceneWorker = ThreeDESceneWorker
    return _ThreeDESceneWorker


def _lazy_import_log_viewer():
    """Lazy import LogViewer."""
    global _LogViewer
    if _LogViewer is None:
        from log_viewer import LogViewer
        _LogViewer = LogViewer
    return _LogViewer


class MainWindow(QMainWindow):
    """Refactored main application window with lazy loading."""

    def __init__(self, cache_manager: Optional[CacheManager] = None):
        """Initialize main window with lazy loading of heavy components."""
        super().__init__()
        
        # Core components (always needed)
        self.cache_manager = cache_manager or CacheManager()
        self.shot_model = ShotModel(self.cache_manager)
        self.threede_model = ThreeDESceneModel(self.cache_manager)
        
        # Lazy-loaded components (initialized on demand)
        self._command_launcher = None
        self._launcher_manager = None
        self._previous_shots_model = None
        self._settings_manager = None
        self._settings_dialog = None
        self._launcher_dialog = None
        self._threede_worker = None
        self._log_viewer = None
        
        # State management
        self._current_scene: Optional[ThreeDEScene] = None
        self._worker_mutex = QMutex()
        self._closing = False
        
        # Custom launcher UI elements
        self.custom_launcher_buttons: Dict[str, Any] = {}
        self.custom_launcher_actions: Dict[str, QAction] = {}
        
        # Initialize UI and connections
        self._init_ui()
        self._init_menus()
        self._init_signals()
        self._load_settings()
        
        # Initial load
        self._initial_load()
        
        logger.info("MainWindow initialized with lazy loading")
        
    # Properties for lazy-loaded components
    @property
    def command_launcher(self):
        """Lazy-load CommandLauncher."""
        if self._command_launcher is None:
            CommandLauncher = _lazy_import_command_launcher()
            self._command_launcher = CommandLauncher()
        return self._command_launcher
        
    @property
    def launcher_manager(self):
        """Lazy-load LauncherManager."""
        if self._launcher_manager is None:
            LauncherManager = _lazy_import_launcher_manager()
            self._launcher_manager = LauncherManager()
        return self._launcher_manager
        
    @property
    def previous_shots_model(self):
        """Lazy-load PreviousShotsModel."""
        if self._previous_shots_model is None:
            PreviousShotsModel = _lazy_import_previous_shots()
            self._previous_shots_model = PreviousShotsModel(
                self.shot_model, self.cache_manager
            )
        return self._previous_shots_model
        
    @property
    def settings_manager(self):
        """Lazy-load SettingsManager."""
        if self._settings_manager is None:
            SettingsManager, _ = _lazy_import_settings()
            self._settings_manager = SettingsManager()
        return self._settings_manager
        
    @property
    def threede_worker(self):
        """Lazy-load ThreeDESceneWorker."""
        if self._threede_worker is None:
            ThreeDESceneWorker = _lazy_import_threede_worker()
            self._threede_worker = ThreeDESceneWorker(self.threede_model)
        return self._threede_worker
        
    @property
    def log_viewer(self):
        """Lazy-load LogViewer."""
        if self._log_viewer is None:
            LogViewer = _lazy_import_log_viewer()
            self._log_viewer = LogViewer(self)
        return self._log_viewer
        
    def _init_ui(self):
        """Initialize UI using modular helper."""
        # Configure 3DE thumbnail widgets to use our cache manager
        from threede_thumbnail_widget import ThreeDEThumbnailWidget
        ThreeDEThumbnailWidget.set_cache_manager(self.cache_manager)
        
        # Create UI structure
        self.ui_helper = MainWindowUI(self)
        
    def _init_menus(self):
        """Initialize menus using modular helper."""
        self.menu_helper = MainWindowMenus(self)
        
    def _init_signals(self):
        """Initialize signal connections using modular helper."""
        self.signal_helper = MainWindowSignals(self)
        
    def _initial_load(self) -> None:
        """Perform initial data load."""
        self._refresh_shots()
        self._refresh_threede_scenes()
        
    # Core business logic methods
    def _refresh_shots(self) -> None:
        """Refresh shot list with progress indication."""
        ProgressManager = _lazy_import_progress()
        with ProgressManager.operation("Refreshing shots", cancelable=False) as progress:
            progress.set_indeterminate()
            self.shot_model.refresh_shots()
            
    def _refresh_threede_scenes(self) -> None:
        """Thread-safe refresh of 3DE scene list using background worker."""
        if self._closing:
            logger.debug("Ignoring refresh request during shutdown")
            return
            
        worker_to_stop = None
        
        with QMutexLocker(self._worker_mutex):
            if self._closing:
                return
                
            if self._threede_worker and self._threede_worker.isRunning():
                worker_to_stop = self._threede_worker
                self._threede_worker = None
                
        if worker_to_stop:
            logger.debug("Stopping existing 3DE worker before starting new one")
            worker_to_stop.stop()
            worker_to_stop.wait(2000)
            
        cache_valid, cached_scenes = self.threede_model.get_cached_scenes()
        if cache_valid:
            if cached_scenes:
                logger.debug(f"Using cached 3DE scenes: {len(cached_scenes)} scenes")
                self.threede_model.update_scenes(cached_scenes)
                self._update_status(f"Loaded {len(cached_scenes)} cached 3DE scenes")
            else:
                logger.debug("Cache indicates no 3DE scenes found previously")
                self.threede_model.update_scenes([])
                self._update_status("No 3DE scenes (cached)")
        else:
            with QMutexLocker(self._worker_mutex):
                if self._closing:
                    return
                    
                logger.debug("Starting new 3DE scene discovery worker")
                self._threede_worker = self.threede_worker
                self._threede_worker.finished.connect(self._on_worker_finished)
                self._threede_worker.start()
                
    def _on_worker_finished(self) -> None:
        """Handle worker thread completion."""
        with QMutexLocker(self._worker_mutex):
            if self._threede_worker:
                self._threede_worker.deleteLater()
                self._threede_worker = None
                
    # Application launcher methods
    def _launch_app(self, app_name: str) -> None:
        """Launch an application."""
        if self._current_scene:
            if app_name == "3de":
                success = self._launch_app_with_scene(app_name, self._current_scene)
            else:
                success = self._launch_app_with_scene_context(
                    app_name, self._current_scene
                )
                
            if not success:
                self._update_status(f"Failed to launch {app_name} with scene context")
        else:
            shot = self.shot_model.current_shot
            if shot:
                if self.command_launcher.launch_app(app_name, shot):
                    self._update_status(f"Launched {app_name} for {shot.name}")
                else:
                    self._update_status(f"Failed to launch {app_name}")
            else:
                self._update_status(f"No shot selected for {app_name}")
                
    def _launch_app_with_scene(self, app_name: str, scene: ThreeDEScene) -> bool:
        """Launch an application with a specific 3DE scene."""
        if self.command_launcher.launch_app_with_scene(app_name, scene):
            self._update_status(f"Launched {app_name} with {scene.username}'s scene")
            return True
        self._update_status(f"Failed to launch {app_name} with scene")
        return False
        
    def _launch_app_with_scene_context(self, app_name: str, scene: ThreeDEScene) -> bool:
        """Launch an application in the context of a 3DE scene."""
        include_undistortion = (
            app_name == "nuke" and 
            hasattr(self, 'undistortion_checkbox') and 
            self.undistortion_checkbox.isChecked()
        )
        include_raw_plate = (
            app_name == "nuke" and 
            hasattr(self, 'raw_plate_checkbox') and 
            self.raw_plate_checkbox.isChecked()
        )
        
        if self.command_launcher.launch_app_with_scene_context(
            app_name, scene, include_undistortion, include_raw_plate
        ):
            self._update_status(f"Launched {app_name} in {scene.shot_name} context")
            return True
        return False
        
    # Custom launcher methods
    def _show_launcher_manager(self) -> None:
        """Show the launcher manager dialog."""
        if self._launcher_dialog is None:
            LauncherManagerDialog = _lazy_import_launcher_dialog()
            self._launcher_dialog = LauncherManagerDialog(self.launcher_manager, self)
            
        self._launcher_dialog.show()
        self._launcher_dialog.raise_()
        self._launcher_dialog.activateWindow()
        
    def _execute_custom_launcher(self, launcher_id: str) -> None:
        """Execute a custom launcher."""
        launcher = self.launcher_manager.get_launcher(launcher_id)
        if not launcher:
            self._update_status(f"Launcher not found: {launcher_id}")
            return
            
        if self._current_scene:
            shot = Shot(
                name=self._current_scene.shot_name,
                path=str(self._current_scene.path.parent),
                workspace_path=str(self._current_scene.path.parents[4])
                if len(self._current_scene.path.parents) > 4
                else "",
            )
        else:
            shot = self.shot_model.current_shot
            
        if shot:
            self.launcher_manager.execute_in_shot_context(
                launcher.id, shot.name, shot.workspace_path
            )
            self._update_status(f"Executed launcher: {launcher.name}")
        else:
            self._update_status("No shot context available for launcher")
            
    def _update_launcher_menu(self) -> None:
        """Update the custom launcher menu with available launchers."""
        if not hasattr(self, 'launch_menu'):
            return
            
        # Clear existing custom launcher actions
        for action in self.custom_launcher_actions.values():
            self.launch_menu.removeAction(action)
        self.custom_launcher_actions.clear()
        
        # Get all launchers
        launchers = self.launcher_manager.list_launchers()
        
        if launchers:
            # Add separator if needed
            if not hasattr(self, 'custom_launcher_separator'):
                self.custom_launcher_separator = self.launch_menu.addSeparator()
                
            # Add launcher actions
            for launcher in launchers:
                action = QAction(launcher.name, self)
                action.setStatusTip(launcher.command[:50] + "..." if len(launcher.command) > 50 else launcher.command)
                action.triggered.connect(
                    lambda checked, lid=launcher.id: self._execute_custom_launcher(lid)
                )
                self.launch_menu.addAction(action)
                self.custom_launcher_actions[launcher.id] = action
                
        # Update button panel
        self._update_custom_launcher_buttons()
        
    def _update_custom_launcher_buttons(self) -> None:
        """Update the custom launcher buttons based on available launchers."""
        if not hasattr(self, 'launcher_buttons_layout'):
            return
            
        # Clear existing buttons
        while self.launcher_buttons_layout.count():
            item = self.launcher_buttons_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()
        self.custom_launcher_buttons.clear()
        
        # Add new buttons
        launchers = self.launcher_manager.list_launchers()
        for launcher in launchers[:5]:  # Limit to 5 buttons
            from PySide6.QtWidgets import QPushButton
            button = QPushButton(launcher.name)
            button.setToolTip(launcher.command[:100] + "..." if len(launcher.command) > 100 else launcher.command)
            button.clicked.connect(
                lambda checked, lid=launcher.id: self._execute_custom_launcher(lid)
            )
            self.launcher_buttons_layout.addWidget(button)
            self.custom_launcher_buttons[launcher.id] = button
            
        # Update button states
        has_context = self._current_scene is not None or self.shot_model.current_shot is not None
        self._enable_custom_launcher_buttons(has_context)
        
    def _update_launcher_menu_availability(self, has_context: bool) -> None:
        """Update custom launcher menu item availability based on context."""
        for action in self.custom_launcher_actions.values():
            action.setEnabled(has_context)
            
    def _enable_custom_launcher_buttons(self, enabled: bool) -> None:
        """Enable or disable all custom launcher buttons."""
        for button in self.custom_launcher_buttons.values():
            button.setEnabled(enabled)
            
    # UI utility methods
    def _increase_thumbnail_size(self) -> None:
        """Increase thumbnail size."""
        if self.tab_widget.currentIndex() == 0:
            current = self.shot_grid.size_slider.value()
        elif self.tab_widget.currentIndex() == 1:
            current = self.threede_grid.size_slider.value()
        else:
            current = self.previous_shots_grid.size_slider.value()
            
        new_size = min(current + 20, Config.MAX_THUMBNAIL_SIZE)
        self._sync_thumbnail_sizes(new_size)
        
    def _decrease_thumbnail_size(self) -> None:
        """Decrease thumbnail size."""
        if self.tab_widget.currentIndex() == 0:
            current = self.shot_grid.size_slider.value()
        elif self.tab_widget.currentIndex() == 1:
            current = self.threede_grid.size_slider.value()
        else:
            current = self.previous_shots_grid.size_slider.value()
            
        new_size = max(current - 20, Config.MIN_THUMBNAIL_SIZE)
        self._sync_thumbnail_sizes(new_size)
        
    def _sync_thumbnail_sizes(self, value: int) -> None:
        """Synchronize thumbnail sizes between tabs."""
        # Block signals to prevent recursion
        self.shot_grid.size_slider.blockSignals(True)
        self.threede_grid.size_slider.blockSignals(True)
        self.previous_shots_grid.size_slider.blockSignals(True)
        
        try:
            self.shot_grid.size_slider.setValue(value)
            self.shot_grid.set_thumbnail_size(value)
            
            self.threede_grid.size_slider.setValue(value)
            self.threede_grid.set_thumbnail_size(value)
            
            self.previous_shots_grid.size_slider.setValue(value)
            self.previous_shots_grid.set_thumbnail_size(value)
        finally:
            self.shot_grid.size_slider.blockSignals(False)
            self.threede_grid.size_slider.blockSignals(False)
            self.previous_shots_grid.size_slider.blockSignals(False)
            
    def _update_status(self, message: str) -> None:
        """Update status bar."""
        if hasattr(self, 'status_bar'):
            self.status_bar.showMessage(message)
            
    def _on_command_error(self, timestamp: str, error: str) -> None:
        """Handle command launcher errors with notifications."""
        NotificationManager, NotificationType = _lazy_import_notification()
        
        if "not found" in error.lower() or "no such file" in error.lower():
            NotificationManager.error("Application not found", "The requested application could not be found. Check if it's installed and in PATH.")
        elif "permission denied" in error.lower():
            NotificationManager.error("Permission denied", "You don't have permission to execute this command.")
        elif "no space left" in error.lower():
            NotificationManager.critical("Disk full", "No space left on device. Please free up disk space.")
        elif "connection" in error.lower() or "network" in error.lower():
            NotificationManager.warning("Network issue", "Network connection problem detected.")
        else:
            NotificationManager.toast("Custom command failed", NotificationType.ERROR)
            
    # Dialog methods
    def _show_shortcuts(self) -> None:
        """Show keyboard shortcuts dialog."""
        shortcuts_text = """<h3>Keyboard Shortcuts</h3>
        <table cellpadding="5">
        <tr><td><b>Navigation:</b></td><td></td></tr>
        <tr><td>Arrow Keys</td><td>Navigate through shots/scenes</td></tr>
        <tr><td>Home/End</td><td>Jump to first/last shot</td></tr>
        <tr><td>Enter</td><td>Launch default app (3de)</td></tr>
        <tr><td>Ctrl+Wheel</td><td>Adjust thumbnail size</td></tr>
        
        <tr><td><b>View:</b></td><td></td></tr>
        <tr><td>Ctrl++/-</td><td>Zoom in/out thumbnails</td></tr>
        <tr><td>F5</td><td>Refresh shot list</td></tr>
        <tr><td>Ctrl+L</td><td>View command history</td></tr>
        
        <tr><td><b>General:</b></td><td></td></tr>
        <tr><td>Ctrl+,</td><td>Open preferences</td></tr>
        <tr><td>F1</td><td>Show this help</td></tr>
        <tr><td>Ctrl+Q</td><td>Quit application</td></tr>
        </table>"""
        
        QMessageBox.information(self, "Keyboard Shortcuts", shortcuts_text)
        
    def _show_about(self) -> None:
        """Show about dialog."""
        QMessageBox.about(
            self,
            f"About {Config.APP_NAME}",
            f"{Config.APP_NAME} v{Config.APP_VERSION}\n\n"
            + "VFX Shot Launcher\n\n"
            + "A tool for browsing and launching applications in shot context.",
        )
        
    def _show_preferences(self) -> None:
        """Show the preferences dialog."""
        if self._settings_dialog is None:
            _, SettingsDialog = _lazy_import_settings()
            self._settings_dialog = SettingsDialog(self.settings_manager, self)
            self._settings_dialog.settings_applied.connect(self._on_settings_applied)
            
        self._settings_dialog.show()
        self._settings_dialog.raise_()
        self._settings_dialog.activateWindow()
        
    def _on_settings_applied(self) -> None:
        """Handle settings applied signal."""
        self._apply_ui_settings()
        self._apply_cache_settings()
        logger.info("Settings applied successfully")
        
    # Settings management
    def _load_settings(self) -> None:
        """Load settings from settings manager."""
        try:
            geometry = self.settings_manager.get_window_geometry()
            if not geometry.isEmpty():
                self.restoreGeometry(geometry)
                
            state = self.settings_manager.get_window_state()
            if not state.isEmpty():
                self.restoreState(state)
                
            if hasattr(self, 'main_splitter'):
                splitter_state = self.settings_manager.get_splitter_state("main_splitter")
                if not splitter_state.isEmpty():
                    self.main_splitter.restoreState(splitter_state)
                    
            self._apply_ui_settings()
            self._apply_cache_settings()
            
        except Exception as e:
            logger.warning(f"Error loading settings: {e}")
            self.resize(Config.DEFAULT_WINDOW_WIDTH, Config.DEFAULT_WINDOW_HEIGHT)
            
    def _save_settings(self) -> None:
        """Save settings to settings manager."""
        try:
            self.settings_manager.set_window_geometry(self.saveGeometry())
            self.settings_manager.set_window_state(self.saveState())
            self.settings_manager.set_window_size(self.size())
            
            if hasattr(self, 'main_splitter'):
                self.settings_manager.set_splitter_state(
                    "main_splitter", self.main_splitter.saveState()
                )
                
        except Exception as e:
            logger.error(f"Error saving settings: {e}")
            
    def _apply_ui_settings(self) -> None:
        """Apply UI settings from settings manager."""
        try:
            # Apply tooltip settings
            tooltip_enabled = self.settings_manager.get_tooltip_enabled()
            # TODO: Apply tooltip settings to widgets
            
            # Apply dark theme if enabled
            if self.settings_manager.get_dark_theme_enabled():
                self._apply_dark_theme()
                
        except Exception as e:
            logger.error(f"Error applying UI settings: {e}")
            
    def _apply_cache_settings(self) -> None:
        """Apply cache settings from settings manager."""
        try:
            max_memory = self.settings_manager.get_max_cache_memory_mb()
            if hasattr(self.cache_manager, "set_memory_limit"):
                self.cache_manager.set_memory_limit(max_memory * 1024 * 1024)
                
            cache_expiry = self.settings_manager.get_cache_expiry_minutes()
            if hasattr(self.cache_manager, "set_expiry_minutes"):
                self.cache_manager.set_expiry_minutes(cache_expiry)
                
        except Exception as e:
            logger.error(f"Error applying cache settings: {e}")
            
    def _apply_dark_theme(self) -> None:
        """Apply dark theme to application."""
        # TODO: Implement dark theme application
        pass
        
    def _import_settings(self):
        """Import settings from file."""
        from PySide6.QtWidgets import QFileDialog
        
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import Settings", "", "JSON Files (*.json);;All Files (*)"
        )
        
        if file_path:
            try:
                success = self.settings_manager.import_settings(file_path)
                if success:
                    self._load_settings()
                    QMessageBox.information(
                        self, "Import Successful", "Settings imported successfully."
                    )
                else:
                    QMessageBox.warning(
                        self, "Import Failed", "Failed to import settings."
                    )
            except Exception as e:
                logger.error(f"Error importing settings: {e}")
                QMessageBox.critical(
                    self, "Import Error", f"Error importing settings: {str(e)}"
                )
                
    def _export_settings(self):
        """Export settings to file."""
        from PySide6.QtWidgets import QFileDialog
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Settings", "shotbot_settings.json", "JSON Files (*.json);;All Files (*)"
        )
        
        if file_path:
            try:
                success = self.settings_manager.export_settings(file_path)
                if success:
                    QMessageBox.information(
                        self, "Export Successful", "Settings exported successfully."
                    )
                else:
                    QMessageBox.warning(self, "Export Error", "Failed to export settings.")
            except Exception as e:
                logger.error(f"Error exporting settings: {e}")
                QMessageBox.critical(
                    self, "Export Error", f"Error exporting settings: {str(e)}"
                )
                
    def _reset_layout(self):
        """Reset window layout to defaults."""
        reply = QMessageBox.question(
            self,
            "Reset Layout",
            "Reset window layout to defaults?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.resize(Config.DEFAULT_WINDOW_WIDTH, Config.DEFAULT_WINDOW_HEIGHT)
            if hasattr(self, 'main_splitter'):
                self.main_splitter.setSizes([800, 400])
            self._save_settings()
            
    # Lifecycle methods
    def closeEvent(self, event: QCloseEvent) -> None:
        """Thread-safe close event handler."""
        self._closing = True
        
        # Stop any running worker threads
        with QMutexLocker(self._worker_mutex):
            if self._threede_worker and self._threede_worker.isRunning():
                logger.debug("Stopping 3DE worker thread during shutdown")
                self._threede_worker.stop()
                self._threede_worker.wait(2000)
                
        # Save settings
        self._save_settings()
        
        # Cleanup cache if needed
        if self.cache_manager:
            self.cache_manager.shutdown()
            
        # Cleanup launcher manager
        if self._launcher_manager:
            self._launcher_manager.shutdown()
            
        logger.info("MainWindow closed")
        event.accept()