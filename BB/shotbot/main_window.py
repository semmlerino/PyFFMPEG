"""Main window for ShotBot application.

This module contains the MainWindow class, which serves as the primary user interface
for the ShotBot VFX shot browsing and launcher application. The MainWindow integrates
all core components including shot grids, 3DE scene discovery, custom launchers,
and application management.

The MainWindow follows a tabbed interface design with:
- My Shots: Visual grid of user's assigned shots with thumbnails
- Other 3DE scenes: Grid of discovered 3DE scenes from user directories
- Shot Info: Details panel showing current shot information
- Custom Launchers: Management interface for creating custom application launchers

Key Features:
    - Real-time shot data refresh with caching
    - Background 3DE scene discovery with progress reporting
    - Thread-safe custom launcher management with race condition protection
    - Persistent UI state and settings storage
    - Memory-optimized thumbnail loading and caching
    - Cross-platform file system operations

Architecture:
    The MainWindow uses Qt's signal-slot mechanism for loose coupling between
    components. It maintains a single CacheManager instance shared across all
    thumbnail widgets and data models for memory efficiency. Thread safety is
    ensured through proper mutex usage and state management.

Examples:
    Basic usage:
        >>> from main_window import MainWindow
        >>> from cache_manager import CacheManager
        >>> cache = CacheManager()
        >>> window = MainWindow(cache_manager=cache)
        >>> window.show()

    With custom configuration:
        >>> from config import Config
        >>> Config.DEFAULT_THUMBNAIL_SIZE = 250
        >>> window = MainWindow()
        >>> window.resize(1600, 1000)
        >>> window.show()

Type Safety:
    This module uses comprehensive type annotations with Optional types for
    nullable Qt widgets and proper signal type declarations. All public methods
    include full type hints for parameters and return values.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QMutex, QMutexLocker, Qt, QThread, QTimer, Slot
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

# Use typing_extensions for override (compatible with Python 3.11)
from typing_extensions import override

if TYPE_CHECKING:
    from base_shot_model import BaseShotModel
    from cache_manager import CacheManager
    from command_launcher import CommandLauncher
    from launcher_dialog import LauncherManagerDialog
    from launcher_manager import LauncherManager

# Runtime imports (needed at runtime)
from base_shot_model import BaseShotModel  # Need at runtime for isinstance checks
from cache_manager import CacheManager  # Need at runtime for instantiation
from command_launcher import CommandLauncher  # Need at runtime
from config import Config
from launcher.models import CustomLauncher  # Need for type annotations
from launcher_dialog import LauncherManagerDialog  # Need at runtime for dialogs
from launcher_manager import LauncherManager  # Need at runtime
from log_viewer import LogViewer
from notification_manager import NotificationManager, NotificationType
from persistent_terminal_manager import PersistentTerminalManager
from previous_shots_grid import PreviousShotsGrid
from previous_shots_model import PreviousShotsModel
from process_pool_manager import ProcessPoolManager
from progress_manager import ProgressManager
from settings_dialog import SettingsDialog
from settings_manager import SettingsManager
from shot_grid_view import ShotGridView  # Model/View implementation
from shot_info_panel import ShotInfoPanel
from shot_item_model import ShotItemModel  # Model/View data model
from shot_model import Shot, ShotModel
from shot_model_optimized import OptimizedShotModel  # Performance-optimized model
from threede_scene_model import ThreeDEScene, ThreeDESceneModel
from threede_scene_worker import ThreeDESceneWorker
from threede_shot_grid import ThreeDEShotGrid

# Set up logger for this module
logger = logging.getLogger(__name__)


class SessionWarmer(QThread):
    """Background thread for pre-warming bash sessions without blocking UI.

    This thread runs during idle time after the UI is displayed, initializing
    the bash environment and 'ws' function in the background. This prevents
    the ~8 second freeze that would occur if this initialization happened
    on the main thread during the first actual command execution.
    """

    @Slot()
    @override
    def run(self) -> None:
        """Pre-warm bash sessions in background thread."""
        try:
            # Check for interruption before starting
            if self.isInterruptionRequested():
                return

            logger.debug("Starting background session pre-warming")
            # Get the process pool instance and warm it up
            pool = ProcessPoolManager.get_instance()

            # Check for interruption before executing
            if self.isInterruptionRequested():
                return

            _ = pool.execute_workspace_command(
                "echo warming",
                cache_ttl=1,  # Short TTL since this is just for warming
                timeout=15,  # Give enough time for first initialization
            )
            logger.info("Bash session pre-warming completed successfully")
        except Exception as e:
            # Don't fail the app if pre-warming fails
            logger.warning(f"Session pre-warming failed (non-critical): {e}")


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self, cache_manager: CacheManager | None = None) -> None:
        super().__init__()

        # Initialize shot_model attribute (will be set later based on feature flag)

        # Initialize ProcessPoolManager singleton on main thread first
        # This prevents race conditions if SessionWarmer tries to create it from a thread
        ProcessPoolManager.get_instance()

        # Create single cache manager for the application
        self.cache_manager = cache_manager or CacheManager()

        # Initialize settings manager
        self.settings_manager = SettingsManager()

        # Store reference to settings dialog
        self._settings_dialog: SettingsDialog | None = None

        # Configure 3DE thumbnail widgets to use our cache manager
        # TODO: Convert threede_shot_grid to Model/View architecture
        from threede_thumbnail_widget import ThreeDEThumbnailWidget

        ThreeDEThumbnailWidget.set_cache_manager(self.cache_manager)

        # Check feature flag - now defaults to True for optimized model
        # Set SHOTBOT_USE_LEGACY_MODEL=1 to use old implementation if issues arise
        try:
            use_legacy = os.environ.get("SHOTBOT_USE_LEGACY_MODEL", "").lower() in (
                "1",
                "true",
                "yes",
            )
        except Exception as e:
            logger.warning(
                f"Failed to read SHOTBOT_USE_LEGACY_MODEL environment variable: {e}"
            )
            use_legacy = False

        # Pass to models - OptimizedShotModel is now the default
        if use_legacy:
            logger.info("Using legacy ShotModel (SHOTBOT_USE_LEGACY_MODEL=1)")
            # ShotModel inherits from BaseShotModel
            shot_model_instance = cast("BaseShotModel", ShotModel(self.cache_manager))
            self.shot_model = shot_model_instance
        else:
            logger.info("Using OptimizedShotModel with 366x faster startup")
            # OptimizedShotModel inherits from BaseShotModel
            optimized_model = OptimizedShotModel(self.cache_manager)
            self.shot_model = cast("BaseShotModel", optimized_model)
            # Initialize async loading for immediate UI display
            init_result = optimized_model.initialize_async()
            if init_result.success:
                logger.debug(
                    f"Optimized model initialized with {len(self.shot_model.shots)} cached shots"
                )
        self.threede_scene_model = ThreeDESceneModel(self.cache_manager)
        # At this point shot_model is guaranteed to be set
        assert self.shot_model is not None, "shot_model must be initialized"
        self.previous_shots_model = PreviousShotsModel(
            self.shot_model, self.cache_manager
        )
        # Create persistent terminal manager if enabled
        self.persistent_terminal: PersistentTerminalManager | None = None
        if Config.USE_PERSISTENT_TERMINAL:
            self.persistent_terminal = PersistentTerminalManager(
                fifo_path=Config.PERSISTENT_TERMINAL_FIFO
            )

        self.command_launcher = CommandLauncher(
            persistent_terminal=self.persistent_terminal
        )
        self.launcher_manager = LauncherManager()
        self._current_scene: ThreeDEScene | None = None
        self._threede_worker: ThreeDESceneWorker | None = None
        self._worker_mutex = QMutex()  # Protect worker access
        self._closing = False  # Track shutdown state
        self._launcher_dialog: LauncherManagerDialog | None = None
        self._setup_ui()
        self._setup_menu()
        self._setup_accessibility()  # Add accessibility support
        self._connect_signals()
        self._load_settings()

        # Initial shot load - immediately, no delay
        self._initial_load()

        # No longer need background refresh for shots - they use signals now
        # Only keep background refresh for 3DE scenes if needed
        logger.info(
            "Shot model now uses reactive signals - background polling disabled for shots"
        )

    def _setup_ui(self) -> None:
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
        # Always use Model/View architecture for maximum efficiency
        self.shot_item_model = ShotItemModel(cache_manager=self.cache_manager)
        self.shot_item_model.set_shots(self.shot_model.shots)
        self.shot_grid = ShotGridView(model=self.shot_item_model)
        _ = self.tab_widget.addTab(self.shot_grid, "My Shots")

        # Tab 2: Other 3DE scenes
        self.threede_shot_grid = ThreeDEShotGrid(self.threede_scene_model)
        _ = self.tab_widget.addTab(self.threede_shot_grid, "Other 3DE scenes")

        # Tab 3: Previous Shots (approved/completed)
        self.previous_shots_grid = PreviousShotsGrid(
            self.previous_shots_model, self.cache_manager
        )
        _ = self.tab_widget.addTab(self.previous_shots_grid, "Previous Shots")

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
        info_label.setStyleSheet(
            "QLabel { color: #888; font-style: italic; padding: 5px; }",
        )
        launcher_layout.addWidget(info_label)
        self.launcher_info_label = info_label

        for app_name, command in Config.APPS.items():
            button = QPushButton(app_name.upper())
            button.setObjectName("builtInLauncherButton")
            _ = button.clicked.connect(
                lambda checked=False, app=app_name: self._launch_app(app)
            )
            button.setEnabled(False)  # Disabled until shot selected

            # Add tooltip with keyboard shortcut
            shortcut = app_shortcuts.get(app_name, "")
            if shortcut:
                button.setToolTip(f"Launch {app_name.upper()} (Shortcut: {shortcut})")

            # Apply styling to built-in launchers
            button.setStyleSheet("""
                QPushButton#builtInLauncherButton {
                    background-color: #2b3e50;
                    color: #ecf0f1;
                    border: 1px solid #34495e;
                    border-radius: 4px;
                    padding: 6px;
                    font-weight: bold;
                }
                QPushButton#builtInLauncherButton:hover {
                    background-color: #34495e;
                    border-color: #4e6d8c;
                }
                QPushButton#builtInLauncherButton:pressed {
                    background-color: #1a252f;
                    border-color: #2b3e50;
                }
                QPushButton#builtInLauncherButton:disabled {
                    background-color: #1e2a35;
                    color: #666;
                    border-color: #1e2a35;
                }
            """)

            launcher_layout.addWidget(button)
            self.app_buttons[app_name] = button

        # Add undistortion checkbox
        self.undistortion_checkbox = QCheckBox("Include undistortion nodes (Nuke)")
        self.undistortion_checkbox.setToolTip(
            "When launching Nuke, automatically include the latest undistortion .nk file",
        )
        launcher_layout.addWidget(self.undistortion_checkbox)

        # Add raw plate checkbox
        self.raw_plate_checkbox = QCheckBox("Include raw plate (Nuke)")
        self.raw_plate_checkbox.setToolTip(
            "When launching Nuke, automatically create a Read node for the raw plate",
        )
        launcher_layout.addWidget(self.raw_plate_checkbox)

        # Add custom launchers section
        self._add_custom_launchers_section(launcher_layout)

        # Ensure launcher group has minimum height and doesn't get hidden
        self.launcher_group.setMinimumHeight(
            350,
        )  # Increased to accommodate custom launchers
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

        # Initialize notification manager
        _ = NotificationManager.initialize(self, self.status_bar)

        # Initialize progress manager
        _ = ProgressManager.initialize(self.status_bar)

        self._update_status("Ready")

    def _setup_menu(self) -> None:
        """Set up menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        self.refresh_action = QAction("&Refresh Shots", self)
        self.refresh_action.setShortcut(QKeySequence.StandardKey.Refresh)
        _ = self.refresh_action.triggered.connect(self._refresh_shots)
        file_menu.addAction(self.refresh_action)

        _ = file_menu.addSeparator()

        # Settings import/export
        import_settings_action = QAction("&Import Settings...", self)
        _ = import_settings_action.triggered.connect(self._import_settings)
        file_menu.addAction(import_settings_action)

        export_settings_action = QAction("&Export Settings...", self)
        _ = export_settings_action.triggered.connect(self._export_settings)
        file_menu.addAction(export_settings_action)

        _ = file_menu.addSeparator()

        exit_action = QAction("&Exit", self)
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        _ = exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # View menu
        view_menu = menubar.addMenu("&View")

        increase_size_action = QAction("&Increase Thumbnail Size", self)
        increase_size_action.setShortcut(QKeySequence.StandardKey.ZoomIn)
        _ = increase_size_action.triggered.connect(self._increase_thumbnail_size)
        view_menu.addAction(increase_size_action)

        decrease_size_action = QAction("&Decrease Thumbnail Size", self)
        decrease_size_action.setShortcut(QKeySequence.StandardKey.ZoomOut)
        _ = decrease_size_action.triggered.connect(self._decrease_thumbnail_size)
        view_menu.addAction(decrease_size_action)

        _ = view_menu.addSeparator()

        # Reset layout action
        reset_layout_action = QAction("&Reset Layout", self)
        _ = reset_layout_action.triggered.connect(self._reset_layout)
        view_menu.addAction(reset_layout_action)

        # Edit menu
        edit_menu = menubar.addMenu("&Edit")

        preferences_action = QAction("&Preferences...", self)
        preferences_action.setShortcut("Ctrl+,")  # Standard preferences shortcut
        _ = preferences_action.triggered.connect(self._show_preferences)
        edit_menu.addAction(preferences_action)

        # Tools menu
        tools_menu = menubar.addMenu("&Tools")

        # Launcher manager
        self.launcher_manager_action = QAction("&Manage Custom Launchers...", self)
        self.launcher_manager_action.setShortcut("Ctrl+L")
        _ = self.launcher_manager_action.triggered.connect(self._show_launcher_manager)
        tools_menu.addAction(self.launcher_manager_action)

        _ = tools_menu.addSeparator()

        # Custom launchers submenu
        self.custom_launcher_menu = tools_menu.addMenu("Custom &Launchers")
        self._update_launcher_menu()

        # Help menu
        help_menu = menubar.addMenu("&Help")

        shortcuts_action = QAction("&Keyboard Shortcuts", self)
        shortcuts_action.setShortcut(QKeySequence.StandardKey.HelpContents)
        _ = shortcuts_action.triggered.connect(self._show_shortcuts)
        help_menu.addAction(shortcuts_action)

        _ = help_menu.addSeparator()

        about_action = QAction("&About", self)
        _ = about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_accessibility(self) -> None:
        """Set up accessibility features for screen readers and keyboard navigation."""
        from accessibility_manager import AccessibilityManager

        # Set up main window accessibility
        AccessibilityManager.setup_main_window_accessibility(self)

        # Set up shot grid accessibility
        AccessibilityManager.setup_shot_grid_accessibility(self.shot_grid, "shots")
        AccessibilityManager.setup_shot_grid_accessibility(
            self.threede_shot_grid, "3de"
        )
        AccessibilityManager.setup_shot_grid_accessibility(
            self.previous_shots_grid, "previous"
        )

        # Set up launcher buttons
        AccessibilityManager.setup_launcher_buttons_accessibility(self.app_buttons)

        # Set up tab widget
        AccessibilityManager.setup_tab_widget_accessibility(self.tab_widget)

        # Add comprehensive tooltips
        AccessibilityManager.setup_comprehensive_tooltips(self)

        # Set up keyboard navigation tab order
        AccessibilityManager.setup_keyboard_navigation(self)

        # Apply focus indicator stylesheet
        existing_style = self.styleSheet() or ""
        focus_style = AccessibilityManager.add_focus_indicators_stylesheet()
        self.setStyleSheet(existing_style + focus_style)

    def _connect_signals(self) -> None:
        """Connect signals."""
        # Connect to shot model signals for reactive updates
        _ = self.shot_model.shots_loaded.connect(self._on_shots_loaded)
        _ = self.shot_model.shots_changed.connect(self._on_shots_changed)
        _ = self.shot_model.refresh_started.connect(self._on_refresh_started)
        _ = self.shot_model.refresh_finished.connect(self._on_refresh_finished)
        _ = self.shot_model.error_occurred.connect(self._on_shot_error)
        _ = self.shot_model.shot_selected.connect(self._on_model_shot_selected)
        _ = self.shot_model.cache_updated.connect(self._on_cache_updated)

        # Shot selection
        _ = self.shot_grid.shot_selected.connect(self._on_shot_selected)
        _ = self.shot_grid.shot_double_clicked.connect(self._on_shot_double_clicked)
        _ = self.shot_grid.app_launch_requested.connect(self._launch_app)

        # 3DE scene selection
        _ = self.threede_shot_grid.scene_selected.connect(self._on_scene_selected)
        _ = self.threede_shot_grid.scene_double_clicked.connect(
            self._on_scene_double_clicked,
        )
        _ = self.threede_shot_grid.app_launch_requested.connect(self._launch_app)

        # Previous shots selection
        _ = self.previous_shots_grid.shot_selected.connect(self._on_shot_selected)
        _ = self.previous_shots_grid.shot_double_clicked.connect(
            self._on_shot_double_clicked
        )

        # Command launcher
        _ = self.command_launcher.command_executed.connect(self.log_viewer.add_command)
        _ = self.command_launcher.command_error.connect(self.log_viewer.add_error)
        _ = self.command_launcher.command_error.connect(self._on_command_error)

        # Custom launcher manager
        _ = self.launcher_manager.launchers_changed.connect(self._update_launcher_menu)
        _ = self.launcher_manager.launchers_changed.connect(
            self._update_custom_launcher_buttons,
        )
        _ = self.launcher_manager.execution_started.connect(self._on_launcher_started)
        _ = self.launcher_manager.execution_finished.connect(self._on_launcher_finished)

        # Synchronize thumbnail sizes between tabs
        _ = self.shot_grid.size_slider.valueChanged.connect(self._sync_thumbnail_sizes)
        _ = self.threede_shot_grid.size_slider.valueChanged.connect(
            self._sync_thumbnail_sizes,
        )

    def _initial_load(self) -> None:
        """Initial shot loading - instant from cache or async."""
        # Check if we're using OptimizedShotModel
        if isinstance(self.shot_model, OptimizedShotModel):
            # Async initialization was already called in __init__, just pre-warm sessions
            logger.info("Using async initialization (already started in __init__)")
            # Pre-warm sessions in background thread to avoid UI freeze
            self._session_warmer = SessionWarmer()
            self._session_warmer.start()
            logger.debug("Session warmer thread started in background")

        has_cached_shots = bool(self.shot_model.shots)
        has_cached_scenes = bool(self.threede_scene_model.scenes)

        # Show cached shots immediately if available
        if has_cached_shots:
            self._refresh_shot_display()

            # Restore last selected shot if available
            if hasattr(self, "_last_selected_shot_name") and isinstance(
                self._last_selected_shot_name,
                str,
            ):
                shot = self.shot_model.find_shot_by_name(self._last_selected_shot_name)
                if shot:
                    self.shot_grid.select_shot_by_name(shot.full_name)

        # Show cached 3DE scenes immediately if available
        if has_cached_scenes:
            self.threede_shot_grid.refresh_scenes()

        # Update status with what was loaded from cache
        if has_cached_shots and has_cached_scenes:
            self._update_status(
                f"Loaded {len(self.shot_model.shots)} shots and "
                + f"{len(self.threede_scene_model.scenes)} 3DE scenes from cache",
            )
        elif has_cached_shots:
            self._update_status(f"Loaded {len(self.shot_model.shots)} shots from cache")
        elif has_cached_scenes:
            self._update_status(
                f"Loaded {len(self.threede_scene_model.scenes)} 3DE scenes from cache",
            )
        else:
            self._update_status("Loading shots and scenes...")
            # No cache exists - the background worker will fetch in 2 seconds
            logger.info(
                "No cached data found - background worker will fetch shots shortly",
            )

        # Start auto-refresh for previous shots
        self.previous_shots_model.start_auto_refresh()
        # Trigger initial refresh for previous shots ONLY after shots are loaded
        # This prevents the "No target shows found" warning when shots haven't loaded yet
        _ = self.shot_model.shots_loaded.connect(self._trigger_previous_shots_refresh)

        # If shots are already loaded from cache, trigger refresh immediately
        if self.shot_model.shots:
            logger.info(
                "Shots already loaded from cache, triggering previous shots refresh immediately"
            )
            QTimer.singleShot(100, self.previous_shots_model.refresh_shots)

        # Only start 3DE discovery if we have shots AND cache is invalid/expired
        # This avoids unnecessary scans when we already know there are no scenes
        if has_cached_shots:
            # Check if we have a valid cache (including valid empty results)
            if not self.cache_manager.has_valid_threede_cache():  # type: ignore[attr-defined]
                logger.info("3DE cache invalid/expired - starting discovery")
                QTimer.singleShot(100, self._refresh_threede_scenes)
            else:
                logger.info("3DE cache is valid - skipping initial scan")
                # Cache is valid but might be empty - that's OK, we cached the "no scenes" state

    def _refresh_shots(self) -> None:
        """Refresh shot list with progress indication."""
        # Start progress operation for shot refresh
        with ProgressManager.operation(
            "Refreshing shots", cancelable=False
        ) as progress:
            progress.set_indeterminate()

            # Simply call refresh_shots on the model
            # The model will emit signals that trigger the appropriate handlers
            # which will handle UI updates, notifications, and 3DE refresh
            _ = self.shot_model.refresh_shots()

    def _refresh_threede_scenes(self) -> None:
        """Thread-safe refresh of 3DE scene list using background worker."""
        # First check if we're closing without holding mutex
        if self._closing:
            logger.debug("Ignoring refresh request during shutdown")
            return

        # Store worker reference for cleanup outside mutex
        worker_to_stop = None

        # Use mutex only for critical section
        with QMutexLocker(self._worker_mutex):
            # Double-check closing state with mutex held
            if self._closing:
                return

            # Check existing worker state
            if self._threede_worker and not self._threede_worker.isFinished():
                logger.debug(
                    "3DE worker still running, will stop before starting new one",
                )
                worker_to_stop = self._threede_worker
                self._threede_worker = None

        # Stop old worker outside of mutex to avoid deadlock
        if worker_to_stop:
            worker_to_stop.stop()
            if not worker_to_stop.wait(1000):  # Wait up to 1 second
                logger.warning(
                    "Failed to stop 3DE worker gracefully, using safe termination",
                )
                # Use safe_terminate which avoids dangerous terminate() call
                worker_to_stop.safe_terminate()
            worker_to_stop.deleteLater()

        # Check once more if closing (could have changed while stopping worker)
        if self._closing:
            return

        # Now create new worker with mutex protection
        with QMutexLocker(self._worker_mutex):
            # Final check before creating new worker
            if self._closing or self._threede_worker:
                return

            # Show loading state
            self.threede_shot_grid.set_loading(True)
            self._update_status("Starting enhanced 3DE scene discovery...")

            # Create enhanced worker with progressive scanning enabled
            # Pass user's shots so the worker knows which shows to scan
            # The worker will scan ALL shots in those shows, not just the user's shots
            self._threede_worker = ThreeDESceneWorker(
                shots=self.shot_model.shots,  # Used to determine which shows to scan
                enable_progressive=True,  # Enable progressive scanning for better UI responsiveness
                batch_size=None,  # Use config default
                scan_all_shots=True,  # Scan ALL shots in the shows, not just user's shots
            )

        # Connect worker signals outside of mutex (signals are thread-safe)
        # Connect enhanced worker signals using safe_connect method for proper cleanup
        _ = self._threede_worker.safe_connect(
            self._threede_worker.started,
            self._on_threede_discovery_started,
            Qt.ConnectionType.QueuedConnection,
        )
        _ = self._threede_worker.safe_connect(
            self._threede_worker.batch_ready,
            self._on_threede_batch_ready,
            Qt.ConnectionType.QueuedConnection,
        )
        _ = self._threede_worker.safe_connect(
            self._threede_worker.progress,
            self._on_threede_discovery_progress,
            Qt.ConnectionType.QueuedConnection,
        )
        _ = self._threede_worker.safe_connect(
            self._threede_worker.scan_progress,
            self._on_threede_scan_progress,
            Qt.ConnectionType.QueuedConnection,
        )
        _ = self._threede_worker.safe_connect(
            self._threede_worker.finished,
            self._on_threede_discovery_finished,
            Qt.ConnectionType.QueuedConnection,
        )
        _ = self._threede_worker.safe_connect(
            self._threede_worker.error,
            self._on_threede_discovery_error,
            Qt.ConnectionType.QueuedConnection,
        )
        _ = self._threede_worker.safe_connect(
            self._threede_worker.paused,
            self._on_threede_discovery_paused,
            Qt.ConnectionType.QueuedConnection,
        )
        _ = self._threede_worker.safe_connect(
            self._threede_worker.resumed,
            self._on_threede_discovery_resumed,
            Qt.ConnectionType.QueuedConnection,
        )

        # Start the worker
        self._threede_worker.start()

    def _on_threede_discovery_started(self) -> None:
        """Handle 3DE discovery worker started signal."""
        # Check if we're closing to avoid accessing deleted widgets
        if hasattr(self, "_closing") and self._closing:
            return

        # Start progress for 3DE discovery
        _ = ProgressManager.start_operation("Scanning for 3DE scenes")

    def _on_threede_discovery_progress(
        self,
        current: int,
        total: int,
        percentage: float,
        description: str,
        eta: str,
    ) -> None:
        """Handle enhanced 3DE discovery progress updates.

        Args:
            current: Current progress value
            total: Total progress value
            percentage: Completion percentage (0.0-100.0)
            description: Progress description
            eta: Estimated time to completion
        """
        # Check if we're closing to avoid accessing deleted widgets
        if hasattr(self, "_closing") and self._closing:
            return

        # Update progress operation if active
        operation = ProgressManager.get_current_operation()
        if operation:
            operation.set_total(total)
            operation.update(current, description)

    def _on_threede_discovery_finished(self, scenes: list[ThreeDEScene]) -> None:
        """Handle 3DE discovery worker completion.

        Args:
            scenes: List of discovered ThreeDEScene objects
        """
        # Check if we're closing to avoid accessing deleted widgets
        if hasattr(self, "_closing") and self._closing:
            return

        # Finish progress operation
        ProgressManager.finish_operation(success=True)

        # Hide loading state
        if self.threede_shot_grid is not None:
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
            # Update the model with new scenes (deduplication happens in model)
            self.threede_scene_model.scenes = (
                self.threede_scene_model._deduplicate_scenes_by_shot(scenes)  # type: ignore[private-usage]
            )
            # Sort deduplicated scenes
            self.threede_scene_model.scenes.sort(key=lambda s: (s.full_name, s.user))

            # ALWAYS cache results, even if empty, to avoid re-scanning
            try:
                self.threede_scene_model.cache_manager.cache_threede_scenes(
                    self.threede_scene_model.to_dict(),
                )
            except Exception as e:
                logger.warning(f"Failed to cache 3DE scenes after scan: {e}")

            # Update UI
            self.threede_shot_grid.refresh_scenes()

            # Update status
            scene_count = len(scenes)
            if scene_count > 0:
                self._update_status(f"Found {scene_count} 3DE scenes from other users")
            else:
                self._update_status("No 3DE scenes found from other users")
        else:
            # No changes, but still cache the current state to refresh TTL
            # This ensures cache persists across restarts
            try:
                self.threede_scene_model.cache_manager.cache_threede_scenes(
                    self.threede_scene_model.to_dict(),
                )
            except Exception as e:
                logger.warning(f"Failed to refresh 3DE scene cache TTL: {e}")

            # Ensure UI is populated if this is the first load
            # (scenes might have been loaded from cache but UI not yet updated)
            if (
                not self.threede_shot_grid.thumbnails
                and self.threede_scene_model.scenes
            ):
                self.threede_shot_grid.refresh_scenes()
            self._update_status("3DE scene discovery complete (no changes)")

    def _on_threede_discovery_error(self, error_message: str) -> None:
        """Handle 3DE discovery worker error.

        Args:
            error_message: Error message from worker
        """
        # Finish progress operation with error
        ProgressManager.finish_operation(success=False, error_message=error_message)

        # Hide loading state
        self.threede_shot_grid.set_loading(False)

        # Show error notification for serious issues
        NotificationManager.warning(
            "3DE Discovery Error",
            f"Failed to discover 3DE scenes: {error_message}",
            "Check that you have read permissions for the scan directories.",
        )

    def _on_threede_batch_ready(self, scene_batch: list[ThreeDEScene]) -> None:
        """Handle batch of scenes ready from progressive scanning.

        Args:
            scene_batch: List of ThreeDEScene objects in this batch
        """
        if scene_batch:
            # Don't directly add to model - let _on_threede_discovery_finished handle deduplication
            # Just log the progress for now
            logger.debug(f"Processed batch of {len(scene_batch)} scenes")

            # Note: The scenes are accumulated in the worker itself
            # and will be deduplicated when discovery finishes

    def _on_threede_scan_progress(
        self,
        current_shot: int,
        total_shots: int,
        status: str,
    ) -> None:
        """Handle fine-grained scan progress updates.

        Args:
            current_shot: Current shot being processed
            total_shots: Total number of shots
            status: Current status message
        """
        # This provides more frequent updates than the main progress signal
        # Useful for showing which specific shot/user is being scanned
        self._update_status(f"Scanning ({current_shot}/{total_shots}): {status}")

    def _on_threede_discovery_paused(self) -> None:
        """Handle worker pause signal."""
        self._update_status("3DE scene discovery paused")

    def _on_threede_discovery_resumed(self) -> None:
        """Handle worker resume signal."""
        self._update_status("3DE scene discovery resumed")

    # Note: Background refresh methods removed - now handled by reactive signals

    def _refresh_shot_display(self) -> None:
        """Refresh the shot display using Model/View implementation."""
        # Always use Model/View implementation
        if hasattr(self, "shot_item_model"):
            self.shot_item_model.set_shots(self.shot_model.shots)

    def _on_shots_loaded(self, shots: list[Shot]) -> None:
        """Handle shots loaded signal from model.

        Args:
            shots: List of loaded Shot objects
        """
        logger.info(f"Shots loaded signal received: {len(shots)} shots")
        self._refresh_shot_display()
        self._update_status(f"Loaded {len(shots)} shots")
        NotificationManager.info(f"{len(shots)} shots loaded from cache")

    def _on_shots_changed(self, shots: list[Shot]) -> None:
        """Handle shots changed signal from model.

        Args:
            shots: List of updated Shot objects
        """
        logger.info(f"Shots changed signal received: {len(shots)} shots")
        self._refresh_shot_display()
        self._update_status(f"Shot list updated: {len(shots)} shots")
        NotificationManager.success(f"Refreshed {len(shots)} shots")

    def _on_refresh_started(self) -> None:
        """Handle refresh started signal from model."""
        # Progress is already shown by _refresh_shots context manager
        pass

    def _on_refresh_finished(self, success: bool, has_changes: bool) -> None:
        """Handle refresh finished signal from model.

        Args:
            success: Whether the refresh was successful
            has_changes: Whether the shot list changed
        """
        if success:
            if has_changes:
                # UI update already handled by shots_changed signal
                logger.debug("Refresh completed with changes")
            else:
                self._update_status(f"{len(self.shot_model.shots)} shots (no changes)")
                NotificationManager.info(
                    f"{len(self.shot_model.shots)} shots (no changes)"
                )
                logger.debug("Refresh completed without changes")

            # Restore last selected shot if available
            if hasattr(self, "_last_selected_shot_name") and isinstance(
                self._last_selected_shot_name,
                str,
            ):
                shot = self.shot_model.find_shot_by_name(self._last_selected_shot_name)
                if shot:
                    self.shot_grid.select_shot_by_name(shot.full_name)

            # Also refresh 3DE scenes when shots are refreshed
            if self.shot_model.shots:
                self._refresh_threede_scenes()
        else:
            self._update_status("Failed to refresh shots")
            NotificationManager.error(
                "Failed to Load Shots",
                "Unable to retrieve shot data from the workspace.",
                "Make sure the 'ws -sg' command is available and you're in a valid workspace.",
            )

    def _on_shot_error(self, error_msg: str) -> None:
        """Handle error signal from model.

        Args:
            error_msg: The error message
        """
        logger.error(f"Shot model error: {error_msg}")
        self._update_status(f"Error: {error_msg}")

    def _trigger_previous_shots_refresh(self, shots: list[Shot]) -> None:
        """Trigger previous shots refresh only after shots are loaded.

        This method is connected to the shot model's shots_loaded signal to ensure
        that previous shots scanning only starts when active shots are available.
        This prevents the "No target shows found" warning.

        Args:
            shots: The loaded shots (from signal)
        """
        if shots:  # Only refresh if we actually have shots
            logger.info(
                f"Triggering previous shots refresh after loading {len(shots)} active shots"
            )
            self.previous_shots_model.refresh_shots()
        else:
            logger.debug("No active shots loaded, skipping previous shots refresh")

    def _on_model_shot_selected(self, shot: Shot | None) -> None:
        """Handle shot selected signal from model.

        Args:
            shot: The selected Shot object or None
        """
        if shot:
            logger.debug(f"Model shot selected: {shot.full_name}")
        else:
            logger.debug("Model shot selection cleared")

    def _on_cache_updated(self) -> None:
        """Handle cache updated signal from model."""
        logger.debug("Shot cache updated")

    def _on_shot_selected(self, shot: Shot | None) -> None:
        """Handle shot selection or deselection.

        Args:
            shot: Shot object or None to clear selection
        """
        # Clear any 3DE scene context when selecting a regular shot
        self._current_scene = None

        if shot is None:
            # Handle deselection
            self.command_launcher.set_current_shot(None)
            self.shot_info_panel.set_shot(None)

            # Disable app buttons and show info label
            for button in self.app_buttons.values():
                button.setEnabled(False)
            self.launcher_info_label.show()

            # Update custom launcher menu availability
            self._update_launcher_menu_availability(False)

            # Disable custom launcher buttons
            self._enable_custom_launcher_buttons(False)

            # Reset window title
            self.setWindowTitle(Config.APP_NAME)

            # Update status
            self._update_status("No shot selected")

            # Clear saved selection
            self._last_selected_shot_name = None
            self._save_settings()
        else:
            # Handle selection
            self.command_launcher.set_current_shot(shot)

            # Update shot info panel
            self.shot_info_panel.set_shot(shot)

            # Enable app buttons and hide info label
            for button in self.app_buttons.values():
                button.setEnabled(True)
            self.launcher_info_label.hide()

            # Update custom launcher menu availability
            self._update_launcher_menu_availability(True)

            # Enable custom launcher buttons
            self._enable_custom_launcher_buttons(True)

            # Update window title
            self.setWindowTitle(f"{Config.APP_NAME} - {shot.full_name} ({shot.show})")

            # Update status
            self._update_status(f"Selected: {shot.full_name} ({shot.show})")

            # Save selection
            self._last_selected_shot_name = shot.full_name
            self._save_settings()

    def _on_shot_double_clicked(self, shot: Shot) -> None:
        """Handle shot double click - launch default app."""
        self._launch_app(Config.DEFAULT_APP)

    def _on_scene_selected(self, scene: ThreeDEScene) -> None:
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

        # Update custom launcher menu availability
        self._update_launcher_menu_availability(True)

        # Enable custom launcher buttons
        self._enable_custom_launcher_buttons(True)

        # Update window title with scene info
        self.setWindowTitle(
            f"{Config.APP_NAME} - {scene.full_name} ({scene.user} - {scene.plate})",
        )

        # Update status
        self._update_status(
            f"Selected: {scene.full_name} - {scene.user} ({scene.plate})",
        )

    def _on_scene_double_clicked(self, scene: ThreeDEScene) -> None:
        """Handle 3DE scene double click - launch 3de with the scene."""
        # Set the current scene first, then launch
        self._current_scene = scene
        self._launch_app("3de")

    def _launch_app(self, app_name: str) -> None:
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
                    app_name,
                    self._current_scene,
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
                app_name,
                include_undistortion,
                include_raw_plate,
            )

        if success:
            self._update_status(f"Launched {app_name}")
            NotificationManager.toast(
                f"Launched {app_name} successfully", NotificationType.SUCCESS
            )
        else:
            self._update_status(f"Failed to launch {app_name}")
            # Error details are handled by _on_command_error

    def _launch_app_with_scene(self, app_name: str, scene: ThreeDEScene) -> bool:
        """Launch an application with a specific 3DE scene."""
        if self.command_launcher.launch_app_with_scene(app_name, scene):
            self._update_status(f"Launched {app_name} with {scene.user}'s scene")
            return True
        self._update_status(f"Failed to launch {app_name} with scene")
        return False

    def _launch_app_with_scene_context(
        self, app_name: str, scene: ThreeDEScene
    ) -> bool:
        """Launch an application in the context of a 3DE scene (without the scene file itself)."""
        # Check if we should include undistortion and/or raw plate for Nuke
        include_undistortion = (
            app_name == "nuke" and self.undistortion_checkbox.isChecked()
        )
        include_raw_plate = app_name == "nuke" and self.raw_plate_checkbox.isChecked()

        if self.command_launcher.launch_app_with_scene_context(
            app_name,
            scene,
            include_undistortion,
            include_raw_plate,
        ):
            return True
        return False

    def _increase_thumbnail_size(self) -> None:
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

    def _decrease_thumbnail_size(self) -> None:
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

    def _sync_thumbnail_sizes(self, value: int) -> None:
        """Synchronize thumbnail sizes between both tabs."""
        # Use signal blocking instead of disconnection to prevent race conditions
        # This is thread-safe and guaranteed to work

        # Block signals temporarily to prevent recursion
        shot_grid_was_blocked = self.shot_grid.size_slider.blockSignals(True)
        threede_grid_was_blocked = self.threede_shot_grid.size_slider.blockSignals(True)

        try:
            # Update both sliders without triggering signals
            self.shot_grid.size_slider.setValue(value)
            self.threede_shot_grid.size_slider.setValue(value)

            # Update internal thumbnail sizes directly since signals are blocked
            self.shot_grid._thumbnail_size = value  # type: ignore[attr-defined]
            self.threede_shot_grid._thumbnail_size = value  # type: ignore[attr-defined]
            self.previous_shots_grid._thumbnail_size = value  # type: ignore[attr-defined]

            # Update size labels
            self.shot_grid.size_label.setText(f"{value}px")
            self.threede_shot_grid.size_label.setText(f"{value}px")
        finally:
            # Always restore signal state, even if an exception occurs
            # This prevents leaving signals permanently blocked
            _ = self.shot_grid.size_slider.blockSignals(shot_grid_was_blocked)
            _ = self.threede_shot_grid.size_slider.blockSignals(
                threede_grid_was_blocked
            )

    def _update_status(self, message: str) -> None:
        """Update status bar."""
        self.status_bar.showMessage(message)

    def _on_command_error(self, timestamp: str, error: str) -> None:
        """Handle command launcher errors with notifications."""
        # Extract error details for better user feedback
        if "not found" in error.lower() or "no such file" in error.lower():
            NotificationManager.error(
                "Application Not Found",
                "The requested application could not be found.",
                f"Details: {error}",
            )
        elif "permission" in error.lower():
            NotificationManager.error(
                "Permission Denied",
                "You don't have permission to run this application.",
                f"Details: {error}",
            )
        elif "no shot selected" in error.lower():
            NotificationManager.warning(
                "No Shot Selected",
                "Please select a shot before launching an application.",
            )
        else:
            NotificationManager.error(
                "Launch Failed", "Failed to launch application.", f"Details: {error}"
            )

        # Also show in status bar briefly
        NotificationManager.info(f"Error: {error}", 5000)

    def _on_launcher_started(self, launcher_id: str) -> None:
        """Handle custom launcher start with progress indication."""
        launcher = self.launcher_manager.get_launcher(launcher_id)
        launcher_name = launcher.name if launcher else "Custom command"
        _ = ProgressManager.start_operation(f"Launching {launcher_name}")

    def _on_launcher_finished(self, launcher_id: str, success: bool) -> None:
        """Handle custom launcher completion with notifications."""
        ProgressManager.finish_operation(success=success)

        if success:
            NotificationManager.toast(
                "Custom command completed successfully", NotificationType.SUCCESS
            )
        else:
            NotificationManager.toast("Custom command failed", NotificationType.ERROR)

    def _show_shortcuts(self) -> None:
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

        _ = QMessageBox.information(self, "Keyboard Shortcuts", shortcuts_text)

    def _show_about(self) -> None:
        """Show about dialog."""
        _ = QMessageBox.about(
            self,
            f"About {Config.APP_NAME}",
            f"{Config.APP_NAME} v{Config.APP_VERSION}\n\n"
            + "VFX Shot Launcher\n\n"
            + "A tool for browsing and launching applications in shot context.",
        )

    def _show_launcher_manager(self) -> None:
        """Show the launcher manager dialog."""
        if self._launcher_dialog is None:
            self._launcher_dialog = LauncherManagerDialog(self.launcher_manager, self)

        self._launcher_dialog.show()
        self._launcher_dialog.raise_()
        self._launcher_dialog.activateWindow()

    def _update_launcher_menu(self) -> None:
        """Update the custom launcher menu with available launchers."""
        # Clear existing menu items
        self.custom_launcher_menu.clear()

        # Get all launchers grouped by category
        launchers = self.launcher_manager.list_launchers()

        if not launchers:
            # Add disabled placeholder
            no_launchers_action = QAction("No custom launchers", self)
            no_launchers_action.setEnabled(False)
            self.custom_launcher_menu.addAction(no_launchers_action)
            return

        # Group by category
        categories: dict[str, list[CustomLauncher]] = {}
        for launcher in launchers:
            category = launcher.category or "custom"
            if category not in categories:
                categories[category] = []
            categories[category].append(launcher)

        # Add menu items
        for category in sorted(categories.keys()):
            category_launchers = categories[category]

            if len(categories) > 1:
                # Add category as submenu if multiple categories
                category_menu = self.custom_launcher_menu.addMenu(category.title())
                for launcher in category_launchers:
                    action = QAction(launcher.name, self)
                    action.setToolTip(launcher.description)
                    action.setData(launcher.id)
                    _ = action.triggered.connect(
                        lambda checked, lid=launcher.id: self._execute_custom_launcher(
                            lid,
                        ),
                    )
                    _ = category_menu.addAction(action)
            else:
                # Add directly to main menu if only one category
                for launcher in category_launchers:
                    action = QAction(launcher.name, self)
                    action.setToolTip(launcher.description)
                    action.setData(launcher.id)
                    _ = action.triggered.connect(
                        lambda checked, lid=launcher.id: self._execute_custom_launcher(
                            lid,
                        ),
                    )
                    _ = self.custom_launcher_menu.addAction(action)

        # Update menu availability
        has_shot_or_scene = (
            hasattr(self, "_last_selected_shot_name") or self._current_scene is not None
        )
        self._update_launcher_menu_availability(has_shot_or_scene)

    def _update_launcher_menu_availability(self, has_context: bool) -> None:
        """Update custom launcher menu item availability based on context."""
        for action in self.custom_launcher_menu.actions():
            menu = action.menu()
            if menu and isinstance(menu, QMenu):
                # It's a submenu, update its actions
                for sub_action in menu.actions():
                    sub_action.setEnabled(has_context)
            else:
                # Regular action
                action.setEnabled(has_context)

    def _execute_custom_launcher(self, launcher_id: str) -> None:
        """Execute a custom launcher."""
        launcher = self.launcher_manager.get_launcher(launcher_id)
        if not launcher:
            self._update_status(f"Launcher not found: {launcher_id}")
            return

        # Check if we have a current scene selected
        if self._current_scene:
            # Create a Shot object from the scene for context
            shot = Shot(
                show=self._current_scene.show,
                sequence=self._current_scene.sequence,
                shot=self._current_scene.shot,
                workspace_path=self._current_scene.workspace_path,
            )
        else:
            # Get current shot
            current_shot = self.command_launcher.current_shot
            if not current_shot:
                self._update_status("No shot or scene selected")
                NotificationManager.warning(
                    "No Context Selected",
                    "Please select a shot or 3DE scene before launching custom commands.",
                )
                return
            shot = current_shot

        # Execute the launcher
        success = self.launcher_manager.execute_in_shot_context(launcher_id, shot)

        if success:
            self._update_status(f"Launched '{launcher.name}'")
            # Log the execution
            from datetime import datetime

            timestamp = datetime.now().strftime("%H:%M:%S")
            self.log_viewer.add_command(timestamp, f"Custom launcher: {launcher.name}")
        else:
            self._update_status(f"Failed to launch '{launcher.name}'")
            from datetime import datetime

            timestamp = datetime.now().strftime("%H:%M:%S")
            self.log_viewer.add_error(
                timestamp,
                f"Failed to launch custom launcher: {launcher.name}",
            )

    def _load_settings(self) -> None:
        """Load settings from settings manager."""
        try:
            # Restore window geometry and state
            geometry = self.settings_manager.get_window_geometry()
            if not geometry.isEmpty():
                _ = self.restoreGeometry(geometry)

            state = self.settings_manager.get_window_state()
            if not state.isEmpty():
                _ = self.restoreState(state)

            # Restore splitter states
            main_splitter_state = self.settings_manager.get_splitter_state("main")
            if not main_splitter_state.isEmpty():
                _ = self.splitter.restoreState(main_splitter_state)

            # Apply window maximized state
            if self.settings_manager.is_window_maximized():
                self.showMaximized()

            # Restore current tab
            self.tab_widget.setCurrentIndex(self.settings_manager.get_current_tab())

            # Apply thumbnail size
            thumbnail_size = self.settings_manager.get_thumbnail_size()
            if hasattr(self.shot_grid, "size_slider"):
                self.shot_grid.size_slider.setValue(thumbnail_size)
            if hasattr(self.threede_shot_grid, "size_slider"):
                self.threede_shot_grid.size_slider.setValue(thumbnail_size)

            # Apply UI preferences
            self._apply_ui_settings()

            # Apply cache settings
            self._apply_cache_settings()

            logger.info("Settings loaded successfully")

        except Exception as e:
            logger.error(f"Error loading settings: {e}")
            # Fallback to default window size
            self.resize(self.settings_manager.get_window_size())

    def _save_settings(self) -> None:
        """Save settings to settings manager."""
        try:
            # Save window geometry and state
            self.settings_manager.set_window_geometry(self.saveGeometry())
            self.settings_manager.set_window_state(self.saveState())
            self.settings_manager.set_window_maximized(self.isMaximized())

            # Save splitter states
            self.settings_manager.set_splitter_state("main", self.splitter.saveState())

            # Save current tab
            self.settings_manager.set_current_tab(self.tab_widget.currentIndex())

            # Save thumbnail size
            if hasattr(self.shot_grid, "size_slider"):
                self.settings_manager.set_thumbnail_size(
                    self.shot_grid.size_slider.value()
                )

            # Sync to disk
            self.settings_manager.sync()

            logger.info("Settings saved successfully")

        except Exception as e:
            logger.error(f"Error saving settings: {e}")

    def _add_custom_launchers_section(self, parent_layout: QVBoxLayout) -> None:
        """Add custom launchers section to the launcher panel."""
        # Add separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setStyleSheet("QFrame { color: #555; margin: 10px 0; }")
        parent_layout.addWidget(separator)

        # Add custom launchers label
        custom_label = QLabel("Custom Launchers")
        custom_label.setObjectName("customLaunchersLabel")
        custom_label.setStyleSheet("""
            QLabel#customLaunchersLabel {
                color: #aaa;
                font-size: 11px;
                font-weight: bold;
                padding: 5px 0 2px 0;
            }
        """)
        parent_layout.addWidget(custom_label)

        # Container for custom launcher buttons
        self.custom_launcher_container = QVBoxLayout()
        self.custom_launcher_container.setSpacing(5)
        parent_layout.addLayout(self.custom_launcher_container)

        # Dictionary to store custom launcher buttons
        self.custom_launcher_buttons: dict[str, QPushButton] = {}

        # Initial update
        self._update_custom_launcher_buttons()

    def _update_custom_launcher_buttons(self) -> None:
        """Update the custom launcher buttons based on available launchers."""
        # Clear existing buttons with immediate deletion to prevent memory leaks
        while self.custom_launcher_container.count():
            item = self.custom_launcher_container.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)  # Remove from parent immediately
                widget.deleteLater()  # Schedule for deletion
        self.custom_launcher_buttons.clear()

        # Get all launchers
        launchers = self.launcher_manager.list_launchers()

        if not launchers:
            # Add placeholder text
            no_launchers_label = QLabel("No custom launchers configured")
            no_launchers_label.setStyleSheet("""
                QLabel {
                    color: #666;
                    font-style: italic;
                    padding: 10px;
                }
            """)
            self.custom_launcher_container.addWidget(no_launchers_label)
            return

        # Group by category
        categories: dict[str, list[CustomLauncher]] = {}
        for launcher in launchers:
            category = launcher.category or "custom"
            if category not in categories:
                categories[category] = []
            categories[category].append(launcher)

        # Add buttons for each launcher
        for category in sorted(categories.keys()):
            category_launchers = categories[category]

            # Add category header if multiple categories
            if len(categories) > 1:
                category_label = QLabel(category.title())
                category_label.setStyleSheet("""
                    QLabel {
                        color: #888;
                        font-size: 10px;
                        padding: 5px 0 2px 0;
                    }
                """)
                self.custom_launcher_container.addWidget(category_label)

            for launcher in category_launchers:
                button = QPushButton(f"🚀 {launcher.name}")
                button.setObjectName("customLauncherButton")
                button.setToolTip(launcher.description or f"Launch {launcher.name}")
                _ = button.clicked.connect(
                    lambda checked, lid=launcher.id: self._execute_custom_launcher(lid),
                )

                # Apply custom styling
                button.setStyleSheet("""
                    QPushButton#customLauncherButton {
                        background-color: #1a4d2e;
                        color: #e0e0e0;
                        border: 1px solid #245938;
                        border-radius: 4px;
                        padding: 6px;
                        text-align: left;
                        font-weight: normal;
                    }
                    QPushButton#customLauncherButton:hover {
                        background-color: #245938;
                        border-color: #2d6b47;
                    }
                    QPushButton#customLauncherButton:pressed {
                        background-color: #0f3620;
                        border-color: #1a4d2e;
                    }
                    QPushButton#customLauncherButton:disabled {
                        background-color: #1a2e20;
                        color: #666;
                        border-color: #1a2e20;
                    }
                """)

                # Initially disabled until shot selected
                button.setEnabled(False)

                self.custom_launcher_container.addWidget(button)
                self.custom_launcher_buttons[launcher.id] = button

        # Update button states based on current selection
        has_selection = (
            hasattr(self, "_last_selected_shot_name") or self._current_scene is not None
        )
        self._enable_custom_launcher_buttons(has_selection)

    def _enable_custom_launcher_buttons(self, enabled: bool) -> None:
        """Enable or disable all custom launcher buttons."""
        for button in self.custom_launcher_buttons.values():
            button.setEnabled(enabled)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Thread-safe close event handler.

        Ensures proper cleanup without double termination of workers.
        """
        # No background refresh worker needed anymore - using signals

        # Mark that we're closing to prevent new operations
        # Extract worker reference safely while holding lock
        worker_to_cleanup = None

        with QMutexLocker(self._worker_mutex):
            self._closing = True

            # Extract worker reference and clear it atomically
            if self._threede_worker:
                worker_to_cleanup = self._threede_worker
                self._threede_worker = None

        # Handle worker cleanup outside of mutex to avoid deadlock
        if worker_to_cleanup:
            # Check if it's a real worker (not a Mock in tests)
            # Use isinstance check for better type safety
            from threede_scene_worker import ThreeDESceneWorker

            if isinstance(worker_to_cleanup, ThreeDESceneWorker):
                # Disconnect all signals first to prevent callbacks on deleted widgets
                try:
                    worker_to_cleanup.started.disconnect()
                    worker_to_cleanup.batch_ready.disconnect()
                    worker_to_cleanup.progress.disconnect()
                    worker_to_cleanup.scan_progress.disconnect()
                    worker_to_cleanup.finished.disconnect()
                    worker_to_cleanup.error.disconnect()
                    worker_to_cleanup.paused.disconnect()
                    worker_to_cleanup.resumed.disconnect()
                except (RuntimeError, TypeError):
                    # Signals may already be disconnected or deleted
                    pass

                # Only stop if not already finished
                if not worker_to_cleanup.isFinished():
                    logger.debug("Stopping 3DE worker during shutdown")
                    worker_to_cleanup.stop()

                    # Wait for worker to finish without holding mutex
                    if not worker_to_cleanup.wait(3000):  # Wait up to 3 seconds
                        logger.warning(
                            "3DE worker didn't stop gracefully, using safe termination",
                        )
                        # Use safe_terminate which avoids dangerous terminate() call
                        worker_to_cleanup.safe_terminate()

                # Clean up the worker
                worker_to_cleanup.deleteLater()

            # Clean up session warmer if it exists
            if hasattr(self, "_session_warmer") and self._session_warmer:
                if not self._session_warmer.isFinished():
                    logger.debug("Requesting session warmer to stop")
                    # Use safe interruption instead of dangerous terminate()
                    self._session_warmer.requestInterruption()
                    # Session warming is non-critical, give it max 2 seconds
                    if not self._session_warmer.wait(2000):
                        logger.warning("Session warmer didn't finish gracefully")
                        # DO NOT use terminate() - just abandon the thread
                        # Qt will clean it up on exit
                self._session_warmer.deleteLater()
                self._session_warmer = None

        # Shutdown launcher manager to stop all worker threads
        if hasattr(self.launcher_manager, "shutdown"):
            self.launcher_manager.shutdown()

        # Clean up OptimizedShotModel if using it
        if isinstance(self.shot_model, OptimizedShotModel):
            logger.debug("Cleaning up OptimizedShotModel background threads")
            self.shot_model.cleanup()

        # Shutdown cache manager
        self.cache_manager.shutdown()

        # Clean up persistent terminal if it exists
        if hasattr(self, "persistent_terminal") and self.persistent_terminal:
            logger.debug("Cleaning up persistent terminal")
            # Check if we should keep terminal open after exit
            if not getattr(Config, "KEEP_TERMINAL_ON_EXIT", False):
                self.persistent_terminal.cleanup()
            else:
                # Just cleanup FIFO but leave terminal running
                logger.info("Keeping terminal open after application exit")
                if hasattr(self.persistent_terminal, "cleanup_fifo_only"):
                    self.persistent_terminal.cleanup_fifo_only()

        self._save_settings()
        event.accept()

    # Settings Management Methods
    def _apply_ui_settings(self) -> None:
        """Apply UI settings from settings manager."""
        try:
            # Apply grid settings
            # grid_columns = self.settings_manager.get_grid_columns()
            # TODO: Apply grid columns to grids when they support it

            # Apply tooltip settings
            # show_tooltips = self.settings_manager.get_show_tooltips()
            # TODO: Apply tooltip settings

            # Apply theme settings
            dark_theme = self.settings_manager.get_dark_theme()
            if dark_theme:
                self._apply_dark_theme()

            logger.debug("UI settings applied")

        except Exception as e:
            logger.error(f"Error applying UI settings: {e}")

    def _apply_cache_settings(self) -> None:
        """Apply cache settings from settings manager."""
        try:
            # Apply cache memory limit
            max_memory = self.settings_manager.get_max_cache_memory_mb()
            if hasattr(self.cache_manager, "set_memory_limit"):
                self.cache_manager.set_memory_limit(max_memory)

            # Apply cache expiry
            expiry_minutes = self.settings_manager.get_cache_expiry_minutes()
            if hasattr(self.cache_manager, "set_expiry_minutes"):
                self.cache_manager.set_expiry_minutes(expiry_minutes)

            logger.debug("Cache settings applied")

        except Exception as e:
            logger.error(f"Error applying cache settings: {e}")

    def _apply_dark_theme(self) -> None:
        """Apply dark theme to the application."""
        # TODO: Implement dark theme application
        # This would involve setting stylesheets or using a dark palette
        pass

    def _show_preferences(self) -> None:
        """Show the preferences dialog."""
        if self._settings_dialog is None:
            self._settings_dialog = SettingsDialog(self.settings_manager, self)
            _ = self._settings_dialog.settings_applied.connect(
                self._on_settings_applied
            )

        self._settings_dialog.load_current_settings()
        self._settings_dialog.show()
        self._settings_dialog.raise_()
        self._settings_dialog.activateWindow()

    def _on_settings_applied(self) -> None:
        """Handle settings being applied from preferences dialog."""
        # Reload and apply all settings
        self._apply_ui_settings()
        self._apply_cache_settings()

        # Update thumbnail sizes in grids
        thumbnail_size = self.settings_manager.get_thumbnail_size()
        if hasattr(self.shot_grid, "size_slider"):
            self.shot_grid.size_slider.setValue(thumbnail_size)
        if hasattr(self.threede_shot_grid, "size_slider"):
            self.threede_shot_grid.size_slider.setValue(thumbnail_size)

        logger.info("Settings applied successfully")

    def _import_settings(self) -> None:
        """Import settings from file."""
        from PySide6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import Settings", "", "JSON Files (*.json);;All Files (*)"
        )

        if file_path:
            if self.settings_manager.import_settings(file_path):
                # Reload settings
                self._apply_ui_settings()
                self._apply_cache_settings()
                _ = QMessageBox.information(
                    self, "Import Success", "Settings imported successfully."
                )
            else:
                _ = QMessageBox.warning(
                    self,
                    "Import Error",
                    "Failed to import settings. Check the file format.",
                )

    def _export_settings(self) -> None:
        """Export settings to file."""
        from PySide6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Settings",
            "shotbot_settings.json",
            "JSON Files (*.json);;All Files (*)",
        )

        if file_path:
            if self.settings_manager.export_settings(file_path):
                _ = QMessageBox.information(
                    self, "Export Success", f"Settings exported to:\n{file_path}"
                )
            else:
                _ = QMessageBox.warning(
                    self, "Export Error", "Failed to export settings."
                )

    def _reset_layout(self) -> None:
        """Reset window layout to defaults."""
        reply = QMessageBox.question(
            self,
            "Reset Layout",
            "Reset window layout to defaults?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Reset window size
            self.resize(Config.DEFAULT_WINDOW_WIDTH, Config.DEFAULT_WINDOW_HEIGHT)

            # Reset splitter
            self.splitter.setSizes([840, 360])  # 70/30 split

            # Reset to first tab
            self.tab_widget.setCurrentIndex(0)

            # Reset window state
            self.settings_manager.set_window_maximized(False)
            self.showNormal()

            logger.info("Layout reset to defaults")


# Background refresh methods and BackgroundRefreshWorker removed - ShotModel now uses reactive signals instead of polling
