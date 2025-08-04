"""Main window for ShotBot application."""

import json
from typing import Any, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from cache_manager import CacheManager
from command_launcher import CommandLauncher
from config import Config
from log_viewer import LogViewer
from shot_grid import ShotGrid
from shot_grid_optimized import ShotGridOptimized
from shot_info_panel import ShotInfoPanel
from shot_model import Shot, ShotModel
from threede_scene_model import ThreeDEScene, ThreeDESceneModel
from threede_scene_worker import ThreeDESceneWorker
from threede_shot_grid import ThreeDEShotGrid


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self, cache_manager: Optional[CacheManager] = None):
        super().__init__()
        # Create single cache manager for the application
        self.cache_manager = cache_manager or CacheManager()

        # Configure thumbnail widgets to use our cache manager
        from threede_thumbnail_widget import ThreeDEThumbnailWidget
        from thumbnail_widget import ThumbnailWidget

        ThumbnailWidget.set_cache_manager(self.cache_manager)
        ThreeDEThumbnailWidget.set_cache_manager(self.cache_manager)

        # Pass to models
        self.shot_model = ShotModel(self.cache_manager)
        self.threede_scene_model = ThreeDESceneModel(self.cache_manager)
        self.command_launcher = CommandLauncher()
        self._current_scene: Optional[ThreeDEScene] = None
        self._threede_worker: Optional[ThreeDESceneWorker] = None
        self._setup_ui()
        self._setup_menu()
        self._connect_signals()
        self._load_settings()

        # Initial shot load
        QTimer.singleShot(100, self._initial_load)

        # Set up background refresh timer (every 5 minutes)
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self._background_refresh)
        self.refresh_timer.start(5 * 60 * 1000)  # 5 minutes in milliseconds

    def _setup_ui(self):
        """Set up the main UI."""
        self.setWindowTitle(f"{Config.APP_NAME} v{Config.APP_VERSION}")
        self.resize(Config.DEFAULT_WINDOW_WIDTH, Config.DEFAULT_WINDOW_HEIGHT)

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main layout
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)

        # Splitter
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.splitter)

        # Left side - Tab widget for different views
        self.tab_widget = QTabWidget()
        self.splitter.addWidget(self.tab_widget)

        # Tab 1: My Shots
        # Use optimized grid if enabled in config
        if Config.USE_MEMORY_OPTIMIZED_GRID:
            self.shot_grid = ShotGridOptimized(self.shot_model)
        else:
            self.shot_grid = ShotGrid(self.shot_model)
        self.tab_widget.addTab(self.shot_grid, "My Shots")

        # Tab 2: Other 3DE scenes
        self.threede_shot_grid = ThreeDEShotGrid(self.threede_scene_model)
        self.tab_widget.addTab(self.threede_shot_grid, "Other 3DE scenes")

        # Right side - Controls and log
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Shot info panel
        self.shot_info_panel = ShotInfoPanel(self.cache_manager)
        right_layout.addWidget(self.shot_info_panel)

        # App launcher buttons
        self.launcher_group = QGroupBox("Launch Applications")
        launcher_layout = QVBoxLayout(self.launcher_group)
        
        # Style the launcher group to make it more visible
        self.launcher_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #444;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)

        self.app_buttons: dict[str, QPushButton] = {}
        # Keyboard shortcuts for each app
        app_shortcuts = {
            "3de": "3",
            "nuke": "N",
            "maya": "M",
            "rv": "R",
            "publish": "P",
        }

        # Add informational label at the top
        info_label = QLabel("Select a shot to enable app launching")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("QLabel { color: #888; font-style: italic; padding: 5px; }")
        launcher_layout.addWidget(info_label)
        self.launcher_info_label = info_label
        
        for app_name, command in Config.APPS.items():
            button = QPushButton(app_name.upper())
            button.clicked.connect(lambda checked, app=app_name: self._launch_app(app))
            button.setEnabled(False)  # Disabled until shot selected

            # Add tooltip with keyboard shortcut
            shortcut = app_shortcuts.get(app_name, "")
            if shortcut:
                button.setToolTip(f"Launch {app_name.upper()} (Shortcut: {shortcut})")

            launcher_layout.addWidget(button)
            self.app_buttons[app_name] = button

        # Add undistortion checkbox
        self.undistortion_checkbox = QCheckBox("Include undistortion nodes (Nuke)")
        self.undistortion_checkbox.setToolTip(
            "When launching Nuke, automatically include the latest undistortion .nk file"
        )
        launcher_layout.addWidget(self.undistortion_checkbox)

        # Add raw plate checkbox
        self.raw_plate_checkbox = QCheckBox("Include raw plate (Nuke)")
        self.raw_plate_checkbox.setToolTip(
            "When launching Nuke, automatically create a Read node for the raw plate"
        )
        launcher_layout.addWidget(self.raw_plate_checkbox)

        # Ensure launcher group has minimum height and doesn't get hidden
        self.launcher_group.setMinimumHeight(250)
        right_layout.addWidget(self.launcher_group)

        # Log viewer
        log_group = QGroupBox("Command Log")
        log_layout = QVBoxLayout(log_group)
        self.log_viewer = LogViewer()
        log_layout.addWidget(self.log_viewer)

        right_layout.addWidget(log_group)

        self.splitter.addWidget(right_widget)

        # Set splitter sizes (70/30 split)
        self.splitter.setSizes([840, 360])

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self._update_status("Ready")

    def _setup_menu(self):
        """Set up menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        refresh_action = QAction("&Refresh Shots", self)
        refresh_action.setShortcut(QKeySequence.StandardKey.Refresh)
        refresh_action.triggered.connect(self._refresh_shots)
        file_menu.addAction(refresh_action)

        file_menu.addSeparator()

        exit_action = QAction("&Exit", self)
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # View menu
        view_menu = menubar.addMenu("&View")

        increase_size_action = QAction("&Increase Thumbnail Size", self)
        increase_size_action.setShortcut(QKeySequence.StandardKey.ZoomIn)
        increase_size_action.triggered.connect(self._increase_thumbnail_size)
        view_menu.addAction(increase_size_action)

        decrease_size_action = QAction("&Decrease Thumbnail Size", self)
        decrease_size_action.setShortcut(QKeySequence.StandardKey.ZoomOut)
        decrease_size_action.triggered.connect(self._decrease_thumbnail_size)
        view_menu.addAction(decrease_size_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")

        shortcuts_action = QAction("&Keyboard Shortcuts", self)
        shortcuts_action.setShortcut(QKeySequence.StandardKey.HelpContents)
        shortcuts_action.triggered.connect(self._show_shortcuts)
        help_menu.addAction(shortcuts_action)

        help_menu.addSeparator()

        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _connect_signals(self):
        """Connect signals."""
        # Shot selection
        self.shot_grid.shot_selected.connect(self._on_shot_selected)
        self.shot_grid.shot_double_clicked.connect(self._on_shot_double_clicked)
        self.shot_grid.app_launch_requested.connect(self._launch_app)

        # 3DE scene selection
        self.threede_shot_grid.scene_selected.connect(self._on_scene_selected)
        self.threede_shot_grid.scene_double_clicked.connect(
            self._on_scene_double_clicked
        )
        self.threede_shot_grid.app_launch_requested.connect(self._launch_app)

        # Command launcher
        self.command_launcher.command_executed.connect(self.log_viewer.add_command)
        self.command_launcher.command_error.connect(self.log_viewer.add_error)

        # Synchronize thumbnail sizes between tabs
        self.shot_grid.size_slider.valueChanged.connect(self._sync_thumbnail_sizes)
        self.threede_shot_grid.size_slider.valueChanged.connect(
            self._sync_thumbnail_sizes
        )

    def _initial_load(self):
        """Initial shot loading."""
        # First, show cached shots immediately if available
        if self.shot_model.shots:
            self.shot_grid.refresh_shots()
            self._update_status(
                f"Loaded {len(self.shot_model.shots)} shots (from cache)"
            )

            # Restore last selected shot if available
            if hasattr(self, "_last_selected_shot_name"):
                shot = self.shot_model.find_shot_by_name(self._last_selected_shot_name)
                if shot:
                    self.shot_grid.select_shot(shot)

        # Also show cached 3DE scenes immediately if available
        if self.threede_scene_model.scenes:
            self.threede_shot_grid.refresh_scenes()
            self._update_status(
                f"Loaded {len(self.shot_model.shots)} shots and {len(self.threede_scene_model.scenes)} 3DE scenes (from cache)"
            )

        # Then refresh in background
        QTimer.singleShot(500, self._refresh_shots)

    def _refresh_shots(self):
        """Refresh shot list."""
        self._update_status("Refreshing shots...")

        success, has_changes = self.shot_model.refresh_shots()

        if success:
            if has_changes:
                self.shot_grid.refresh_shots()
                self._update_status(f"Loaded {len(self.shot_model.shots)} shots")
            else:
                self._update_status(f"{len(self.shot_model.shots)} shots (no changes)")

            # Restore last selected shot if available
            if hasattr(self, "_last_selected_shot_name"):
                shot = self.shot_model.find_shot_by_name(self._last_selected_shot_name)
                if shot:
                    self.shot_grid.select_shot(shot)

            # Also refresh 3DE scenes
            self._refresh_threede_scenes()
        else:
            self._update_status("Failed to load shots")
            QMessageBox.warning(
                self,
                "Error",
                "Failed to load shots. Make sure 'ws -sg' command is available.",
            )

    def _refresh_threede_scenes(self):
        """Refresh 3DE scene list using background worker."""
        # Check if worker is already running
        if self._threede_worker and not self._threede_worker.isFinished():
            self._update_status("3DE scene discovery already in progress...")
            return

        # Show loading state
        self.threede_shot_grid.set_loading(True)
        self._update_status("Starting 3DE scene discovery...")

        # Create and start worker
        self._threede_worker = ThreeDESceneWorker(self.shot_model.shots)

        # Connect worker signals
        self._threede_worker.started.connect(self._on_threede_discovery_started)
        self._threede_worker.progress.connect(self._on_threede_discovery_progress)
        self._threede_worker.finished.connect(self._on_threede_discovery_finished)
        self._threede_worker.error.connect(self._on_threede_discovery_error)

        # Start the worker
        self._threede_worker.start()

    def _on_threede_discovery_started(self):
        """Handle 3DE discovery worker started signal."""
        self._update_status("3DE scene discovery started...")

    def _on_threede_discovery_progress(
        self, current: int, total: int, description: str
    ):
        """Handle 3DE discovery progress updates.

        Args:
            current: Current progress value
            total: Total progress value
            description: Progress description
        """
        self._update_status(f"3DE discovery: {description} ({current}/{total})")

    def _on_threede_discovery_finished(self, scenes: list):
        """Handle 3DE discovery worker completion.

        Args:
            scenes: List of discovered ThreeDEScene objects
        """
        # Hide loading state
        self.threede_shot_grid.set_loading(False)

        # Update model with discovered scenes (compare with existing)
        old_scene_data = {
            (scene.full_name, scene.user, scene.plate, str(scene.scene_path))
            for scene in self.threede_scene_model.scenes
        }

        new_scene_data = {
            (scene.full_name, scene.user, scene.plate, str(scene.scene_path))
            for scene in scenes
        }

        has_changes = old_scene_data != new_scene_data

        if has_changes:
            # Update the model with new scenes
            self.threede_scene_model.scenes = scenes
            # Sort by shot name, then user, then plate
            self.threede_scene_model.scenes.sort(
                key=lambda s: (s.full_name, s.user, s.plate)
            )

            # Cache the results
            if self.threede_scene_model.scenes:
                self.threede_scene_model.cache_manager.cache_threede_scenes(
                    self.threede_scene_model.to_dict()
                )

            # Update UI
            self.threede_shot_grid.refresh_scenes()

            # Update status
            scene_count = len(scenes)
            if scene_count > 0:
                self._update_status(f"Found {scene_count} 3DE scenes from other users")
            else:
                self._update_status("No 3DE scenes found from other users")
        else:
            # No changes, but ensure UI is populated if this is the first load
            # (scenes might have been loaded from cache but UI not yet updated)
            if (
                not self.threede_shot_grid.thumbnails
                and self.threede_scene_model.scenes
            ):
                self.threede_shot_grid.refresh_scenes()
            self._update_status("3DE scene discovery complete (no changes)")

    def _on_threede_discovery_error(self, error_message: str):
        """Handle 3DE discovery worker error.

        Args:
            error_message: Error message from worker
        """
        # Hide loading state
        self.threede_shot_grid.set_loading(False)

        # Update status with error
        self._update_status(f"3DE discovery error: {error_message}")

        # Show error dialog for serious issues
        QMessageBox.warning(
            self,
            "3DE Discovery Error",
            f"Failed to discover 3DE scenes:\n{error_message}",
        )

    def _background_refresh(self):
        """Refresh shots in background without interrupting user."""
        # Save current selection
        current_shot_name = None
        if hasattr(self, "_last_selected_shot_name"):
            current_shot_name = self._last_selected_shot_name

        # Refresh quietly
        success, has_changes = self.shot_model.refresh_shots()

        if success and has_changes:
            # Only update UI if there were actual changes
            self.shot_grid.refresh_shots()
            self._update_status(
                f"Updated: {len(self.shot_model.shots)} shots (new changes)"
            )

            # Restore selection if possible
            if current_shot_name:
                shot = self.shot_model.find_shot_by_name(current_shot_name)
                if shot:
                    self.shot_grid.select_shot(shot)

        # Also refresh 3DE scenes if shots were successful
        if success:
            scene_success, scene_changes = self.threede_scene_model.refresh_scenes(
                self.shot_model.shots
            )
            if scene_success and scene_changes:
                self.threede_shot_grid.refresh_scenes()

    def _on_shot_selected(self, shot: Shot):
        """Handle shot selection."""
        self.command_launcher.set_current_shot(shot)

        # Update shot info panel
        self.shot_info_panel.set_shot(shot)

        # Enable app buttons and hide info label
        for button in self.app_buttons.values():
            button.setEnabled(True)
        self.launcher_info_label.hide()

        # Update window title
        self.setWindowTitle(f"{Config.APP_NAME} - {shot.full_name} ({shot.show})")

        # Update status
        self._update_status(f"Selected: {shot.full_name} ({shot.show})")

        # Save selection
        self._last_selected_shot_name = shot.full_name
        self._save_settings()

    def _on_shot_double_clicked(self, shot: Shot):
        """Handle shot double click - launch default app."""
        self._launch_app(Config.DEFAULT_APP)

    def _on_scene_selected(self, scene: ThreeDEScene):
        """Handle 3DE scene selection."""
        self._current_scene = scene
        self.command_launcher.set_current_shot(None)  # Clear regular shot

        # Create a Shot object from the scene for compatibility
        shot = Shot(
            show=scene.show,
            sequence=scene.sequence,
            shot=scene.shot,
            workspace_path=scene.workspace_path,
        )

        # Update shot info panel
        self.shot_info_panel.set_shot(shot)

        # Enable all app buttons (not just 3de) and hide info label
        for button in self.app_buttons.values():
            button.setEnabled(True)
        self.launcher_info_label.hide()

        # Update window title with scene info
        self.setWindowTitle(
            f"{Config.APP_NAME} - {scene.full_name} ({scene.user} - {scene.plate})"
        )

        # Update status
        self._update_status(
            f"Selected: {scene.full_name} - {scene.user} ({scene.plate})"
        )

    def _on_scene_double_clicked(self, scene: ThreeDEScene):
        """Handle 3DE scene double click - launch 3de with the scene."""
        # Set the current scene first, then launch
        self._current_scene = scene
        self._launch_app("3de")

    def _launch_app(self, app_name: str):
        """Launch an application."""
        # Check if we have a current 3DE scene selected
        if self._current_scene:
            # Launch with scene context
            if app_name == "3de":
                # For 3DE, use the scene file directly
                success = self._launch_app_with_scene(app_name, self._current_scene)
            else:
                # For other apps, launch in shot context with undistortion/raw plate support
                success = self._launch_app_with_scene_context(
                    app_name, self._current_scene
                )
        else:
            # Regular shot launch
            # Check if we should include undistortion and/or raw plate for Nuke
            include_undistortion = (
                app_name == "nuke" and self.undistortion_checkbox.isChecked()
            )
            include_raw_plate = (
                app_name == "nuke" and self.raw_plate_checkbox.isChecked()
            )

            success = self.command_launcher.launch_app(
                app_name, include_undistortion, include_raw_plate
            )

        if success:
            self._update_status(f"Launched {app_name}")
        else:
            self._update_status(f"Failed to launch {app_name}")

    def _launch_app_with_scene(self, app_name: str, scene: ThreeDEScene):
        """Launch an application with a specific 3DE scene."""
        if self.command_launcher.launch_app_with_scene(app_name, scene):
            self._update_status(f"Launched {app_name} with {scene.user}'s scene")
            return True
        else:
            self._update_status(f"Failed to launch {app_name} with scene")
            return False

    def _launch_app_with_scene_context(self, app_name: str, scene: ThreeDEScene):
        """Launch an application in the context of a 3DE scene (without the scene file itself)."""
        # Check if we should include undistortion and/or raw plate for Nuke
        include_undistortion = (
            app_name == "nuke" and self.undistortion_checkbox.isChecked()
        )
        include_raw_plate = app_name == "nuke" and self.raw_plate_checkbox.isChecked()

        if self.command_launcher.launch_app_with_scene_context(
            app_name, scene, include_undistortion, include_raw_plate
        ):
            return True
        else:
            return False

    def _increase_thumbnail_size(self):
        """Increase thumbnail size."""
        # Get current size from active tab
        if self.tab_widget.currentIndex() == 0:
            current = self.shot_grid.size_slider.value()
        else:
            current = self.threede_shot_grid.size_slider.value()

        new_size = min(current + 20, Config.MAX_THUMBNAIL_SIZE)
        # This will trigger _sync_thumbnail_sizes to update both
        if self.tab_widget.currentIndex() == 0:
            self.shot_grid.size_slider.setValue(new_size)
        else:
            self.threede_shot_grid.size_slider.setValue(new_size)

    def _decrease_thumbnail_size(self):
        """Decrease thumbnail size."""
        # Get current size from active tab
        if self.tab_widget.currentIndex() == 0:
            current = self.shot_grid.size_slider.value()
        else:
            current = self.threede_shot_grid.size_slider.value()

        new_size = max(current - 20, Config.MIN_THUMBNAIL_SIZE)
        # This will trigger _sync_thumbnail_sizes to update both
        if self.tab_widget.currentIndex() == 0:
            self.shot_grid.size_slider.setValue(new_size)
        else:
            self.threede_shot_grid.size_slider.setValue(new_size)

    def _sync_thumbnail_sizes(self, value: int):
        """Synchronize thumbnail sizes between both tabs."""
        # Prevent recursive calls by temporarily disconnecting signals
        self.shot_grid.size_slider.valueChanged.disconnect(self._sync_thumbnail_sizes)
        self.threede_shot_grid.size_slider.valueChanged.disconnect(
            self._sync_thumbnail_sizes
        )

        # Update both sliders
        self.shot_grid.size_slider.setValue(value)
        self.threede_shot_grid.size_slider.setValue(value)

        # Reconnect signals
        self.shot_grid.size_slider.valueChanged.connect(self._sync_thumbnail_sizes)
        self.threede_shot_grid.size_slider.valueChanged.connect(
            self._sync_thumbnail_sizes
        )

    def _update_status(self, message: str):
        """Update status bar."""
        self.status_bar.showMessage(message)

    def _show_shortcuts(self):
        """Show keyboard shortcuts dialog."""
        shortcuts_text = """<h3>Keyboard Shortcuts</h3>
        <table cellpadding="5">
        <tr><td><b>Navigation:</b></td><td></td></tr>
        <tr><td>Arrow Keys</td><td>Navigate through shots/scenes</td></tr>
        <tr><td>Home/End</td><td>Jump to first/last shot</td></tr>
        <tr><td>Enter</td><td>Launch default app (3de)</td></tr>
        <tr><td>Ctrl+Wheel</td><td>Adjust thumbnail size</td></tr>
        <tr><td>&nbsp;</td><td></td></tr>
        <tr><td><b>Applications:</b></td><td></td></tr>
        <tr><td>3</td><td>Launch 3de</td></tr>
        <tr><td>N</td><td>Launch Nuke</td></tr>
        <tr><td>M</td><td>Launch Maya</td></tr>
        <tr><td>R</td><td>Launch RV</td></tr>
        <tr><td>P</td><td>Launch Publish</td></tr>
        <tr><td>&nbsp;</td><td></td></tr>
        <tr><td><b>View:</b></td><td></td></tr>
        <tr><td>Ctrl++</td><td>Increase thumbnail size</td></tr>
        <tr><td>Ctrl+-</td><td>Decrease thumbnail size</td></tr>
        <tr><td>&nbsp;</td><td></td></tr>
        <tr><td><b>General:</b></td><td></td></tr>
        <tr><td>F5</td><td>Refresh shots</td></tr>
        <tr><td>F1</td><td>Show this help</td></tr>
        </table>
        """

        QMessageBox.information(self, "Keyboard Shortcuts", shortcuts_text)

    def _show_about(self):
        """Show about dialog."""
        QMessageBox.about(
            self,
            f"About {Config.APP_NAME}",
            f"{Config.APP_NAME} v{Config.APP_VERSION}\n\n"
            "VFX Shot Launcher\n\n"
            "A tool for browsing and launching applications in shot context.",
        )

    def _load_settings(self):
        """Load settings from file."""
        if Config.SETTINGS_FILE.exists():
            try:
                with open(Config.SETTINGS_FILE, "r") as f:
                    settings = json.load(f)

                # Restore window geometry
                if "geometry" in settings:
                    self.restoreGeometry(bytes.fromhex(settings["geometry"]))

                # Restore splitter state
                if "splitter" in settings:
                    self.splitter.restoreState(bytes.fromhex(settings["splitter"]))

                # Restore last selected shot
                if "last_shot" in settings:
                    self._last_selected_shot_name = settings["last_shot"]

                # Restore thumbnail size
                if "thumbnail_size" in settings:
                    self.shot_grid.size_slider.setValue(settings["thumbnail_size"])
                    self.threede_shot_grid.size_slider.setValue(
                        settings["thumbnail_size"]
                    )

                # Restore undistortion checkbox state
                if "include_undistortion" in settings:
                    self.undistortion_checkbox.setChecked(
                        settings["include_undistortion"]
                    )

                # Restore raw plate checkbox state
                if "include_raw_plate" in settings:
                    self.raw_plate_checkbox.setChecked(settings["include_raw_plate"])

                # Restore active tab
                if "active_tab" in settings:
                    self.tab_widget.setCurrentIndex(settings["active_tab"])

            except Exception as e:
                print(f"Error loading settings: {e}")

    def _save_settings(self):
        """Save settings to file."""
        # Convert QByteArray to string for JSON serialization
        geometry_hex = self.saveGeometry().toHex()
        splitter_hex = self.splitter.saveState().toHex()

        # Convert QByteArray to string
        settings: dict[str, Any] = {
            "geometry": str(geometry_hex.data(), "ascii"),
            "splitter": str(splitter_hex.data(), "ascii"),
            "thumbnail_size": self.shot_grid.size_slider.value(),
            "include_undistortion": self.undistortion_checkbox.isChecked(),
            "include_raw_plate": self.raw_plate_checkbox.isChecked(),
            "active_tab": self.tab_widget.currentIndex(),
        }

        # Save last selected shot
        if hasattr(self, "_last_selected_shot_name"):
            settings["last_shot"] = self._last_selected_shot_name

        # Create settings directory
        Config.SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Save to file
        try:
            with open(Config.SETTINGS_FILE, "w") as f:
                json.dump(settings, f, indent=2)
        except Exception as e:
            print(f"Error saving settings: {e}")

    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle close event."""
        # Stop and cleanup worker if running
        if self._threede_worker and not self._threede_worker.isFinished():
            self._threede_worker.stop()
            if not self._threede_worker.wait(3000):  # Wait up to 3 seconds
                self._threede_worker.terminate()
                self._threede_worker.wait()

        self._save_settings()
        event.accept()
