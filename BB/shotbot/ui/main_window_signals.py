"""Signal connections and event handlers for MainWindow.

This module manages all Qt signal-slot connections and event handling logic,
separated from UI setup and business logic for better maintainability.
"""

import logging
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QMessageBox

from shot_model import Shot
from threede_scene_model import ThreeDEScene

logger = logging.getLogger(__name__)


class MainWindowSignals:
    """Signal connection helper for MainWindow."""
    
    def __init__(self, parent):
        """Initialize signal helper.
        
        Args:
            parent: MainWindow instance
        """
        self.parent = parent
        self.connect_signals()
        
    def connect_signals(self) -> None:
        """Connect all signals to their handlers."""
        # Shot model signals
        self.connect_shot_model_signals()
        
        # 3DE model signals
        self.connect_threede_model_signals()
        
        # Previous shots model signals
        self.connect_previous_shots_signals()
        
        # UI control signals
        self.connect_ui_control_signals()
        
        # Grid view signals
        self.connect_grid_signals()
        
        # Launcher signals
        self.connect_launcher_signals()
        
        # Timer signals
        self.setup_timers()
        
    def connect_shot_model_signals(self) -> None:
        """Connect shot model signals."""
        self.parent.shot_model.shots_loaded.connect(self._on_shots_loaded)
        self.parent.shot_model.shots_changed.connect(self._on_shots_changed)
        self.parent.shot_model.refresh_started.connect(self._on_refresh_started)
        self.parent.shot_model.refresh_finished.connect(self._on_refresh_finished)
        self.parent.shot_model.error.connect(self._on_shot_error)
        self.parent.shot_model.shot_selected.connect(self._on_model_shot_selected)
        
    def connect_threede_model_signals(self) -> None:
        """Connect 3DE scene model signals."""
        # Worker thread signals
        if hasattr(self.parent, 'threede_worker'):
            self.parent.threede_worker.discovery_started.connect(
                self._on_threede_discovery_started
            )
            self.parent.threede_worker.discovery_progress.connect(
                self._on_threede_discovery_progress
            )
            self.parent.threede_worker.discovery_finished.connect(
                self._on_threede_discovery_finished
            )
            self.parent.threede_worker.discovery_error.connect(
                self._on_threede_discovery_error
            )
            self.parent.threede_worker.batch_ready.connect(
                self._on_threede_batch_ready
            )
            self.parent.threede_worker.scan_progress.connect(
                self._on_threede_scan_progress
            )
            self.parent.threede_worker.discovery_paused.connect(
                self._on_threede_discovery_paused
            )
            self.parent.threede_worker.discovery_resumed.connect(
                self._on_threede_discovery_resumed
            )
            
    def connect_previous_shots_signals(self) -> None:
        """Connect previous shots model signals."""
        # Model refresh signals
        self.parent.previous_shots_model.refresh_started.connect(
            lambda: self.parent._update_status("Refreshing previous shots...")
        )
        self.parent.previous_shots_model.refresh_finished.connect(
            lambda success, count: self.parent._update_status(
                f"Found {count} previous shots" if success else "Failed to refresh previous shots"
            )
        )
        
        # Grid selection signals
        if hasattr(self.parent, 'previous_shots_grid'):
            self.parent.previous_shots_grid.shot_selected.connect(
                self._on_previous_shot_selected
            )
            self.parent.previous_shots_grid.shot_double_clicked.connect(
                self._on_previous_shot_double_clicked
            )
            
    def connect_ui_control_signals(self) -> None:
        """Connect UI control signals."""
        # Button signals
        self.parent.refresh_button.clicked.connect(self.parent._refresh_shots)
        self.parent.launcher_button.clicked.connect(self.parent._show_launcher_manager)
        self.parent.increase_size_button.clicked.connect(self.parent._increase_thumbnail_size)
        self.parent.decrease_size_button.clicked.connect(self.parent._decrease_thumbnail_size)
        
        # Menu action signals
        if hasattr(self.parent, 'refresh_action'):
            self.parent.refresh_action.triggered.connect(self.parent._refresh_shots)
            
    def connect_grid_signals(self) -> None:
        """Connect grid view signals."""
        # Shot grid signals (Model/View)
        if hasattr(self.parent, 'shot_grid_view'):
            self.parent.shot_grid_view.shot_selected.connect(self._on_shot_selected)
            self.parent.shot_grid_view.shot_double_clicked.connect(
                self._on_shot_double_clicked
            )
            
        # 3DE grid signals
        if hasattr(self.parent, 'threede_grid'):
            self.parent.threede_grid.scene_selected.connect(self._on_scene_selected)
            self.parent.threede_grid.scene_double_clicked.connect(
                self._on_scene_double_clicked
            )
            
    def connect_launcher_signals(self) -> None:
        """Connect launcher manager signals."""
        launcher_mgr = self.parent.launcher_manager
        launcher_mgr.launcher_created.connect(self.parent._update_launcher_menu)
        launcher_mgr.launcher_updated.connect(self.parent._update_launcher_menu)
        launcher_mgr.launcher_deleted.connect(self.parent._update_launcher_menu)
        launcher_mgr.command_started.connect(self._on_launcher_started)
        launcher_mgr.command_finished.connect(self._on_launcher_finished)
        launcher_mgr.command_error.connect(self._on_command_error)
        
    def setup_timers(self) -> None:
        """Set up periodic timers."""
        # Cache update timer
        self.parent.cache_timer = QTimer()
        self.parent.cache_timer.timeout.connect(self._on_cache_updated)
        self.parent.cache_timer.start(30000)  # 30 seconds
        
        # Auto-refresh timer (if enabled)
        if hasattr(self.parent, 'settings_manager'):
            auto_refresh = self.parent.settings_manager.get_setting(
                'general/auto_refresh', False
            )
            if auto_refresh:
                self.parent.auto_refresh_timer = QTimer()
                self.parent.auto_refresh_timer.timeout.connect(self.parent._refresh_shots)
                interval = self.parent.settings_manager.get_setting(
                    'general/auto_refresh_interval', 300
                ) * 1000
                self.parent.auto_refresh_timer.start(interval)
                
    # Event handlers
    def _on_shots_loaded(self, shots: list) -> None:
        """Handle shots loaded signal."""
        logger.info(f"Loaded {len(shots)} shots")
        self.parent._update_status(f"Loaded {len(shots)} shots")
        self.parent.shot_count_label.setText(f"Shots: {len(shots)}")
        
    def _on_shots_changed(self, shots: list) -> None:
        """Handle shots changed signal."""
        logger.info(f"Shots changed: {len(shots)} shots")
        self.parent._update_status(f"Updated {len(shots)} shots")
        self.parent.shot_count_label.setText(f"Shots: {len(shots)}")
        
    def _on_refresh_started(self) -> None:
        """Handle refresh started signal."""
        self.parent._update_status("Refreshing shots...")
        self.parent.refresh_button.setEnabled(False)
        if hasattr(self.parent, 'refresh_action'):
            self.parent.refresh_action.setEnabled(False)
            
    def _on_refresh_finished(self, success: bool, has_changes: bool) -> None:
        """Handle refresh finished signal."""
        self.parent.refresh_button.setEnabled(True)
        if hasattr(self.parent, 'refresh_action'):
            self.parent.refresh_action.setEnabled(True)
            
        if success:
            if has_changes:
                self.parent._update_status("Shots refreshed with updates")
            else:
                self.parent._update_status("Shots refreshed (no changes)")
        else:
            self.parent._update_status("Failed to refresh shots")
            
    def _on_shot_error(self, error_msg: str) -> None:
        """Handle shot error signal."""
        logger.error(f"Shot error: {error_msg}")
        self.parent._update_status(f"Error: {error_msg}")
        
    def _on_model_shot_selected(self, shot: Optional[Shot]) -> None:
        """Handle model shot selection."""
        if shot:
            self.parent.shot_info_panel.set_shot(shot)
            
    def _on_cache_updated(self) -> None:
        """Handle cache update timer."""
        if self.parent.cache_manager:
            stats = self.parent.cache_manager.get_memory_usage()
            self.parent.cache_status_label.setText(
                f"Cache: {stats['current_mb']:.1f}MB"
            )
            
    def _on_shot_selected(self, shot: Optional[Shot]) -> None:
        """Handle shot selection from grid."""
        self.parent.shot_model.set_current_shot(shot)
        if shot:
            self.parent.shot_info_panel.set_shot(shot)
            self.parent._update_launcher_menu_availability(True)
            self.parent._update_custom_launcher_buttons()
            self.parent._enable_custom_launcher_buttons(True)
        else:
            self.parent._update_launcher_menu_availability(False)
            self.parent._enable_custom_launcher_buttons(False)
            
    def _on_shot_double_clicked(self, shot: Shot) -> None:
        """Handle shot double-click."""
        self.parent._launch_app(Config.DEFAULT_DOUBLE_CLICK_APP)
        
    def _on_scene_selected(self, scene: ThreeDEScene) -> None:
        """Handle 3DE scene selection."""
        info_text = f"3DE Scene: {scene.shot_name}\n"
        info_text += f"Plate: {scene.plate_name}\n"
        info_text += f"User: {scene.username}\n"
        info_text += f"Modified: {scene.modified.strftime('%Y-%m-%d %H:%M')}"
        self.parent.shot_info_panel.set_info_text(info_text)
        
        # Enable launchers
        self.parent._update_launcher_menu_availability(True)
        self.parent._update_custom_launcher_buttons()
        self.parent._enable_custom_launcher_buttons(True)
        
    def _on_scene_double_clicked(self, scene: ThreeDEScene) -> None:
        """Handle 3DE scene double-click."""
        if self.parent._launch_app_with_scene("3de", scene):
            logger.info(f"Launched 3de for scene: {scene.path}")
            
    def _on_previous_shot_selected(self, shot: Shot) -> None:
        """Handle previous shot selection."""
        self._on_shot_selected(shot)
        
    def _on_previous_shot_double_clicked(self, shot: Shot) -> None:
        """Handle previous shot double-click."""
        self._on_shot_double_clicked(shot)
        
    def _on_threede_discovery_started(self) -> None:
        """Handle 3DE discovery started."""
        self.parent._update_status("Starting 3DE scene discovery...")
        
    def _on_threede_discovery_progress(
        self, current: int, total: int, current_dir: str
    ) -> None:
        """Handle 3DE discovery progress."""
        progress = (current / total * 100) if total > 0 else 0
        self.parent._update_status(
            f"Scanning 3DE scenes: {progress:.0f}% - {current_dir}"
        )
        
    def _on_threede_discovery_finished(self, scenes: list) -> None:
        """Handle 3DE discovery finished."""
        logger.info(f"3DE discovery completed: {len(scenes)} scenes found")
        self.parent._update_status(f"Found {len(scenes)} 3DE scenes")
        
        # Update the model
        self.parent.threede_model.update_scenes(scenes)
        
    def _on_threede_discovery_error(self, error_message: str) -> None:
        """Handle 3DE discovery error."""
        logger.error(f"3DE discovery error: {error_message}")
        self.parent._update_status(f"3DE discovery error: {error_message}")
        
    def _on_threede_batch_ready(self, scene_batch: list) -> None:
        """Handle batch of 3DE scenes ready."""
        logger.debug(f"Batch of {len(scene_batch)} scenes ready")
        # Could update model incrementally here if needed
        
    def _on_threede_scan_progress(
        self, directories_scanned: int, files_found: int, current_path: str
    ) -> None:
        """Handle 3DE scan progress."""
        logger.debug(
            f"Scan progress: {directories_scanned} dirs, {files_found} files, "
            f"current: {current_path}"
        )
        
    def _on_threede_discovery_paused(self) -> None:
        """Handle 3DE discovery paused."""
        self.parent._update_status("3DE discovery paused")
        
    def _on_threede_discovery_resumed(self) -> None:
        """Handle 3DE discovery resumed."""
        self.parent._update_status("3DE discovery resumed")
        
    def _on_launcher_started(self, launcher_id: str) -> None:
        """Handle launcher started."""
        logger.info(f"Launcher started: {launcher_id}")
        self.parent._update_status(f"Running launcher: {launcher_id}")
        
    def _on_launcher_finished(self, launcher_id: str, success: bool) -> None:
        """Handle launcher finished."""
        if success:
            logger.info(f"Launcher completed: {launcher_id}")
            self.parent._update_status(f"Launcher completed: {launcher_id}")
        else:
            logger.warning(f"Launcher failed: {launcher_id}")
            self.parent._update_status(f"Launcher failed: {launcher_id}")
            
    def _on_command_error(self, timestamp: str, error: str) -> None:
        """Handle command error."""
        logger.error(f"Command error at {timestamp}: {error}")
        QMessageBox.warning(
            self.parent,
            "Command Error",
            f"Error executing command:\n{error}"
        )