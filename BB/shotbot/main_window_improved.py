"""Improved main window with enhanced UI/UX design for ShotBot.

This module demonstrates the redesigned main window addressing all identified
UI/UX issues including consistency, accessibility, responsiveness, and user feedback.
"""

import json
import logging
from typing import Optional

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QDockWidget,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

# Import existing components (these would be updated with design system)
from cache_manager import CacheManager
from config import Config

# Import improved components
from design_system import design_system
from shot_model import ShotModel
from ui_components import (
    EmptyStateWidget,
    FloatingActionButton,
    ModernButton,
    NotificationBanner,
    ProgressOverlay,
)

logger = logging.getLogger(__name__)


class ImprovedMainWindow(QMainWindow):
    """Redesigned main window with modern UI/UX patterns."""

    def __init__(self, cache_manager: Optional[CacheManager] = None):
        super().__init__()

        # Initialize core components
        self.cache_manager = cache_manager or CacheManager()
        self.shot_model = ShotModel(self.cache_manager)

        # Apply design system stylesheet
        self.setStyleSheet(design_system.get_stylesheet())

        # Setup UI components
        self._setup_window()
        self._setup_central_widget()
        self._setup_toolbar()
        self._setup_dock_widgets()
        self._setup_status_bar()
        self._setup_menu_bar()
        self._setup_overlays()
        self._connect_signals()
        self._load_settings()

        # Initial load with proper feedback
        self._initial_load()

    def _setup_window(self):
        """Configure main window properties."""
        self.setWindowTitle(f"{Config.APP_NAME} v{Config.APP_VERSION}")
        self.resize(Config.DEFAULT_WINDOW_WIDTH, Config.DEFAULT_WINDOW_HEIGHT)
        self.setMinimumSize(Config.MIN_WINDOW_WIDTH, Config.MIN_WINDOW_HEIGHT)

        # Set window icon
        self.setWindowIcon(QIcon.fromTheme("applications-multimedia"))

    def _setup_central_widget(self):
        """Set up the central widget with responsive layout."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main layout with proper spacing
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Add notification banner at top
        self.notification_banner = NotificationBanner(central_widget)
        main_layout.addWidget(self.notification_banner)

        # Content area with splitter
        content_widget = QWidget()
        content_layout = QHBoxLayout(content_widget)
        content_layout.setContentsMargins(
            design_system.spacing.md,
            design_system.spacing.md,
            design_system.spacing.md,
            design_system.spacing.md,
        )

        # Responsive splitter
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setChildrenCollapsible(False)

        # Left panel - Shot grids with tabs
        self._setup_left_panel()

        # Right panel - Controls and info
        self._setup_right_panel()

        # Add panels to splitter with proportional sizes
        self.main_splitter.addWidget(self.left_panel)
        self.main_splitter.addWidget(self.right_panel)
        self.main_splitter.setStretchFactor(0, 7)  # 70% for left panel
        self.main_splitter.setStretchFactor(1, 3)  # 30% for right panel

        content_layout.addWidget(self.main_splitter)
        main_layout.addWidget(content_widget)

        # Add floating action button
        self.fab = FloatingActionButton("+", central_widget)
        self.fab.setToolTip("Quick Actions (Ctrl+N)")
        self.fab.clicked.connect(self._show_quick_actions)

    def _setup_left_panel(self):
        """Set up the left panel with shot grids."""
        self.left_panel = QWidget()
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Tab widget with consistent styling
        self.tab_widget = QTabWidget()
        self.tab_widget.setDocumentMode(True)
        self.tab_widget.setMovable(True)

        # Tab 1: My Shots (placeholder for actual grid)
        self.my_shots_tab = QWidget()
        my_shots_layout = QVBoxLayout(self.my_shots_tab)

        # Add empty state for demonstration
        self.shots_empty_state = EmptyStateWidget(
            icon="📷",
            title="No Shots Available",
            description="Shots will appear here once loaded from the workspace",
            action_text="Refresh Shots",
        )
        self.shots_empty_state.action_clicked.connect(self._refresh_shots)
        my_shots_layout.addWidget(self.shots_empty_state)

        self.tab_widget.addTab(self.my_shots_tab, "My Shots")

        # Tab 2: 3DE Scenes
        self.scenes_tab = QWidget()
        scenes_layout = QVBoxLayout(self.scenes_tab)

        self.scenes_empty_state = EmptyStateWidget(
            icon="🎬",
            title="No 3DE Scenes Found",
            description="3DE scenes from other users will appear here",
            action_text="Scan for Scenes",
        )
        self.scenes_empty_state.action_clicked.connect(self._scan_3de_scenes)
        scenes_layout.addWidget(self.scenes_empty_state)

        self.tab_widget.addTab(self.scenes_tab, "Other 3DE Scenes")

        # Tab 3: Recent/Favorites (new feature)
        self.favorites_tab = QWidget()
        self.tab_widget.addTab(self.favorites_tab, "⭐ Favorites")

        left_layout.addWidget(self.tab_widget)

    def _setup_right_panel(self):
        """Set up the right panel with controls."""
        self.right_panel = QWidget()
        self.right_panel.setMinimumWidth(300)

        # Make it scrollable for small screens
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        scroll_content = QWidget()
        right_layout = QVBoxLayout(scroll_content)
        right_layout.setSpacing(design_system.spacing.md)

        # Shot info card
        info_card = self._create_card("Current Shot")
        info_layout = QVBoxLayout(info_card)

        self.shot_info_label = QLabel("No shot selected")
        self.shot_info_label.setObjectName("heading3")
        info_layout.addWidget(self.shot_info_label)

        self.shot_details_label = QLabel("")
        self.shot_details_label.setObjectName("hint")
        self.shot_details_label.setWordWrap(True)
        info_layout.addWidget(self.shot_details_label)

        right_layout.addWidget(info_card)

        # Application launchers card
        launcher_card = self._create_card("Launch Applications")
        launcher_layout = QVBoxLayout(launcher_card)

        # Info message
        self.launcher_hint = QLabel("💡 Select a shot to enable launchers")
        self.launcher_hint.setObjectName("hint")
        launcher_layout.addWidget(self.launcher_hint)

        # Built-in launchers with icons and keyboard hints
        apps_layout = QVBoxLayout()
        apps_layout.setSpacing(design_system.spacing.sm)

        app_configs = [
            ("3DE", "3de", "3", "🎥"),
            ("Nuke", "nuke", "N", "🎨"),
            ("Maya", "maya", "M", "🎭"),
            ("RV", "rv", "R", "▶"),
            ("Publish", "publish", "P", "📤"),
        ]

        self.app_buttons = {}
        for display_name, app_id, shortcut, icon in app_configs:
            button = ModernButton(f"{icon} {display_name}")
            button.setEnabled(False)
            button.setToolTip(f"Launch {display_name} (Shortcut: {shortcut})")
            button.clicked.connect(lambda checked, app=app_id: self._launch_app(app))

            # Add accessible name
            button.setAccessibleName(f"Launch {display_name} application")
            button.setAccessibleDescription(
                f"Opens {display_name} in the selected shot context",
            )

            apps_layout.addWidget(button)
            self.app_buttons[app_id] = button

        launcher_layout.addLayout(apps_layout)

        # Options section
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout(options_group)

        self.undistortion_check = QCheckBox("Include undistortion nodes")
        self.undistortion_check.setToolTip(
            "Automatically include undistortion setup when launching Nuke",
        )
        options_layout.addWidget(self.undistortion_check)

        self.raw_plate_check = QCheckBox("Include raw plate")
        self.raw_plate_check.setToolTip(
            "Automatically create Read node for raw plate in Nuke",
        )
        options_layout.addWidget(self.raw_plate_check)

        launcher_layout.addWidget(options_group)

        # Custom launchers section
        custom_section = QGroupBox("Custom Launchers")
        custom_layout = QVBoxLayout(custom_section)

        manage_button = ModernButton("⚙ Manage Launchers", variant="primary")
        manage_button.clicked.connect(self._show_launcher_manager)
        custom_layout.addWidget(manage_button)

        launcher_layout.addWidget(custom_section)

        right_layout.addWidget(launcher_card)

        # Command log card (collapsible)
        log_card = self._create_card("Command History", collapsible=True)
        log_layout = QVBoxLayout(log_card)

        self.log_placeholder = QLabel("Command history will appear here")
        self.log_placeholder.setObjectName("hint")
        log_layout.addWidget(self.log_placeholder)

        right_layout.addWidget(log_card)

        right_layout.addStretch()

        scroll_area.setWidget(scroll_content)

        # Add scroll area to panel
        panel_layout = QVBoxLayout(self.right_panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.addWidget(scroll_area)

    def _create_card(self, title: str, collapsible: bool = False) -> QWidget:
        """Create a styled card widget."""
        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet(f"""
            #card {{
                background-color: {design_system.colors.bg_secondary};
                border: 1px solid {design_system.colors.border_default};
                border-radius: {design_system.borders.radius_lg}px;
                padding: {design_system.spacing.card_padding}px;
            }}
        """)

        layout = QVBoxLayout(card)

        # Card header
        header_layout = QHBoxLayout()

        title_label = QLabel(title)
        title_label.setObjectName("heading3")
        title_label.setStyleSheet(f"""
            font-weight: {design_system.typography.weight_medium};
            color: {design_system.colors.text_primary};
        """)
        header_layout.addWidget(title_label)

        if collapsible:
            collapse_button = QPushButton("▼")
            collapse_button.setFixedSize(24, 24)
            collapse_button.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border: none;
                    color: #888;
                }
                QPushButton:hover {
                    color: #aaa;
                }
            """)
            header_layout.addWidget(collapse_button)

        header_layout.addStretch()
        layout.addLayout(header_layout)

        return card

    def _setup_toolbar(self):
        """Set up the main toolbar with common actions."""
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        toolbar.setIconSize(QSize(24, 24))

        # Refresh action
        refresh_action = QAction("🔄", self)
        refresh_action.setText("Refresh")
        refresh_action.setToolTip("Refresh shots (F5)")
        refresh_action.setShortcut(QKeySequence.StandardKey.Refresh)
        refresh_action.triggered.connect(self._refresh_shots)
        toolbar.addAction(refresh_action)

        toolbar.addSeparator()

        # View size actions
        increase_size_action = QAction("🔍+", self)
        increase_size_action.setText("Larger")
        increase_size_action.setToolTip("Increase thumbnail size (Ctrl++)")
        increase_size_action.setShortcut(QKeySequence.StandardKey.ZoomIn)
        increase_size_action.triggered.connect(self._increase_thumbnail_size)
        toolbar.addAction(increase_size_action)

        decrease_size_action = QAction("🔍-", self)
        decrease_size_action.setText("Smaller")
        decrease_size_action.setToolTip("Decrease thumbnail size (Ctrl+-)")
        decrease_size_action.setShortcut(QKeySequence.StandardKey.ZoomOut)
        decrease_size_action.triggered.connect(self._decrease_thumbnail_size)
        toolbar.addAction(decrease_size_action)

        toolbar.addSeparator()

        # Settings action
        settings_action = QAction("⚙", self)
        settings_action.setText("Settings")
        settings_action.setToolTip("Application settings")
        settings_action.triggered.connect(self._show_settings)
        toolbar.addAction(settings_action)

        self.addToolBar(toolbar)

    def _setup_dock_widgets(self):
        """Set up dockable widgets for flexible layout."""
        # Quick launch dock
        quick_dock = QDockWidget("Quick Launch", self)
        quick_dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)

        quick_widget = QWidget()
        quick_layout = QVBoxLayout(quick_widget)

        quick_label = QLabel("Frequently used commands")
        quick_label.setObjectName("hint")
        quick_layout.addWidget(quick_label)

        quick_dock.setWidget(quick_widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, quick_dock)
        quick_dock.hide()  # Hidden by default

    def _setup_status_bar(self):
        """Set up an enhanced status bar."""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # Main status label
        self.status_label = QLabel("Ready")
        self.status_bar.addWidget(self.status_label)

        # Separator
        self.status_bar.addPermanentWidget(QFrame())

        # Shot count label
        self.shot_count_label = QLabel("0 shots")
        self.shot_count_label.setObjectName("hint")
        self.status_bar.addPermanentWidget(self.shot_count_label)

        # Connection status
        self.connection_label = QLabel("● Connected")
        self.connection_label.setStyleSheet(f"color: {design_system.colors.success};")
        self.status_bar.addPermanentWidget(self.connection_label)

    def _setup_menu_bar(self):
        """Set up the menu bar with organized menus."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        refresh_action = QAction("&Refresh Shots", self)
        refresh_action.setShortcut(QKeySequence.StandardKey.Refresh)
        refresh_action.triggered.connect(self._refresh_shots)
        file_menu.addAction(refresh_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Edit menu
        edit_menu = menubar.addMenu("&Edit")

        settings_action = QAction("&Preferences...", self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self._show_settings)
        edit_menu.addAction(settings_action)

        # View menu
        view_menu = menubar.addMenu("&View")

        # Add view options
        view_menu.addAction("Show Toolbar").setCheckable(True)
        view_menu.addAction("Show Status Bar").setCheckable(True)
        view_menu.addSeparator()

        # Thumbnail size submenu
        size_menu = view_menu.addMenu("Thumbnail Size")
        size_menu.addAction("Small (100px)")
        size_menu.addAction("Medium (200px)")
        size_menu.addAction("Large (300px)")
        size_menu.addAction("Extra Large (400px)")

        # Tools menu
        tools_menu = menubar.addMenu("&Tools")

        launcher_action = QAction("&Manage Launchers...", self)
        launcher_action.setShortcut("Ctrl+L")
        launcher_action.triggered.connect(self._show_launcher_manager)
        tools_menu.addAction(launcher_action)

        tools_menu.addSeparator()

        scan_action = QAction("&Scan for 3DE Scenes", self)
        scan_action.triggered.connect(self._scan_3de_scenes)
        tools_menu.addAction(scan_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")

        shortcuts_action = QAction("&Keyboard Shortcuts", self)
        shortcuts_action.setShortcut(QKeySequence.StandardKey.HelpContents)
        shortcuts_action.triggered.connect(self._show_shortcuts)
        help_menu.addAction(shortcuts_action)

        help_menu.addSeparator()

        about_action = QAction("&About ShotBot", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_overlays(self):
        """Set up overlay widgets for progress and notifications."""
        # Progress overlay for long operations
        self.progress_overlay = ProgressOverlay(self.centralWidget())
        self.progress_overlay.canceled.connect(self._cancel_operation)

    def _connect_signals(self):
        """Connect signals and slots."""
        # Shot model signals
        self.shot_model.shots_updated.connect(self._on_shots_updated)

        # Tab widget signals
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

    def _load_settings(self):
        """Load persisted settings."""
        settings_file = Config.SETTINGS_FILE
        if settings_file.exists():
            try:
                with open(settings_file, "r") as f:
                    settings = json.load(f)

                # Restore window geometry
                if "geometry" in settings:
                    self.restoreGeometry(bytes.fromhex(settings["geometry"]))

                # Restore splitter state
                if "splitter" in settings:
                    self.main_splitter.restoreState(bytes.fromhex(settings["splitter"]))

                # Restore checkboxes
                if "undistortion" in settings:
                    self.undistortion_check.setChecked(settings["undistortion"])
                if "raw_plate" in settings:
                    self.raw_plate_check.setChecked(settings["raw_plate"])

            except Exception as e:
                logger.error(f"Failed to load settings: {e}")

    def _save_settings(self):
        """Save current settings."""
        settings = {
            "geometry": self.saveGeometry().toHex().data().decode("ascii"),
            "splitter": self.main_splitter.saveState().toHex().data().decode("ascii"),
            "undistortion": self.undistortion_check.isChecked(),
            "raw_plate": self.raw_plate_check.isChecked(),
        }

        Config.SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(Config.SETTINGS_FILE, "w") as f:
                json.dump(settings, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")

    # Action handlers
    def _initial_load(self):
        """Perform initial data load with proper feedback."""
        # Show loading state
        self.status_label.setText("Loading shots...")

        # Simulate async load with timer
        QTimer.singleShot(100, self._load_shots)

    def _load_shots(self):
        """Load shots from workspace."""
        # This would actually load shots
        success, has_changes = self.shot_model.refresh_shots()

        if success:
            shot_count = len(self.shot_model.shots)
            self.shot_count_label.setText(f"{shot_count} shots")

            if shot_count > 0:
                # Hide empty state and show actual grid
                self.shots_empty_state.hide()
                # Would show actual shot grid here

            self.notification_banner.show_message(
                f"Loaded {shot_count} shots successfully",
                msg_type="success",
                duration=3000,
            )
            self.status_label.setText("Ready")
        else:
            self.notification_banner.show_message(
                "Failed to load shots. Check workspace connection.",
                msg_type="error",
                duration=5000,
            )
            self.status_label.setText("Error loading shots")

    def _refresh_shots(self):
        """Refresh shot list with progress feedback."""
        self.progress_overlay.show_progress("Refreshing Shots", can_cancel=True)

        # Simulate progress updates
        for i in range(101):
            QTimer.singleShot(i * 20, lambda v=i: self._update_refresh_progress(v))

    def _update_refresh_progress(self, value: int):
        """Update refresh progress."""
        self.progress_overlay.update_progress(
            value,
            f"Loading shot {value} of 100..." if value < 100 else "Complete!",
        )

        if value >= 100:
            self.progress_overlay.hide_progress()
            self._load_shots()

    def _scan_3de_scenes(self):
        """Scan for 3DE scenes with progress."""
        self.progress_overlay.show_progress("Scanning for 3DE Scenes", can_cancel=True)
        self.progress_overlay.update_progress(0, "Initializing scan...")

        # Would actually scan here
        QTimer.singleShot(2000, self._complete_3de_scan)

    def _complete_3de_scan(self):
        """Complete 3DE scan."""
        self.progress_overlay.hide_progress()
        self.scenes_empty_state.hide()

        self.notification_banner.show_message(
            "Found 15 3DE scenes from other users",
            msg_type="info",
            duration=4000,
        )

    def _cancel_operation(self):
        """Cancel current operation."""
        self.progress_overlay.hide_progress()
        self.notification_banner.show_message(
            "Operation canceled",
            msg_type="warning",
            duration=2000,
        )

    def _launch_app(self, app_id: str):
        """Launch application with feedback."""
        self.notification_banner.show_message(
            f"Launching {app_id}...",
            msg_type="info",
            duration=2000,
        )

    def _show_quick_actions(self):
        """Show quick actions menu."""
        menu = QMenu(self)
        menu.addAction("📷 Create New Shot")
        menu.addAction("⭐ Add to Favorites")
        menu.addAction("🔄 Refresh All")
        menu.addAction("⚙ Settings")

        # Position menu at FAB
        menu.exec(self.fab.mapToGlobal(self.fab.rect().center()))

    def _show_launcher_manager(self):
        """Show launcher manager dialog."""
        self.notification_banner.show_message(
            "Launcher manager would open here",
            msg_type="info",
        )

    def _show_settings(self):
        """Show settings dialog."""
        self.notification_banner.show_message(
            "Settings dialog would open here",
            msg_type="info",
        )

    def _show_shortcuts(self):
        """Show keyboard shortcuts."""
        # Would show actual shortcuts dialog
        pass

    def _show_about(self):
        """Show about dialog."""
        # Would show actual about dialog
        pass

    def _increase_thumbnail_size(self):
        """Increase thumbnail size."""
        self.notification_banner.show_message(
            "Thumbnail size increased",
            msg_type="info",
            duration=1000,
        )

    def _decrease_thumbnail_size(self):
        """Decrease thumbnail size."""
        self.notification_banner.show_message(
            "Thumbnail size decreased",
            msg_type="info",
            duration=1000,
        )

    def _on_shots_updated(self):
        """Handle shots updated signal."""
        shot_count = len(self.shot_model.shots)
        self.shot_count_label.setText(f"{shot_count} shots")

    def _on_tab_changed(self, index: int):
        """Handle tab change."""
        tab_names = ["My Shots", "Other 3DE Scenes", "Favorites"]
        if 0 <= index < len(tab_names):
            self.status_label.setText(f"Viewing: {tab_names[index]}")

    def closeEvent(self, event):
        """Handle window close."""
        self._save_settings()
        event.accept()


# Example usage
if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    # Set application style
    app.setStyle("Fusion")

    window = ImprovedMainWindow()
    window.show()

    sys.exit(app.exec())
