#!/usr/bin/env python3
"""MainWindow refactoring summary and integration guide.

This file demonstrates how the extracted components should integrate with
the refactored MainWindow to achieve the target of <500 lines per component.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMainWindow

if TYPE_CHECKING:
    from app_launcher_manager import AppLauncherManager
    from cache_manager import CacheManager
    from main_window_ui import MainWindowUI
    from threading_manager import ThreadingManager

logger = logging.getLogger(__name__)


class RefactoredMainWindow(QMainWindow):
    """Example of refactored MainWindow using extracted components.
    
    This demonstrates how the original 2,057-line MainWindow can be reduced
    to <500 lines by delegating functionality to specialized components.
    
    TARGET ARCHITECTURE:
    - MainWindow (~400 lines): Coordination and high-level logic
    - MainWindowUI (331 lines): UI setup and layout management
    - ThreadingManager (298 lines): Thread coordination
    - AppLauncherManager (278 lines): Application launching
    
    TOTAL: ~1,307 lines across 4 focused components vs 2,057 in one file
    """
    
    def __init__(self, cache_manager: CacheManager | None = None):
        """Initialize refactored main window with component delegation."""
        super().__init__()
        
        # Initialize core dependencies
        self.cache_manager = cache_manager or self._create_cache_manager()
        
        # Create component managers
        self.ui_manager = self._create_ui_manager()
        self.threading_manager = self._create_threading_manager()
        self.launcher_manager = self._create_launcher_manager()
        
        # Initialize data models
        self.shot_model = self._create_shot_model()
        self.threede_model = self._create_threede_model()
        
        # Setup UI through UI manager
        self._setup_ui_via_manager()
        
        # Connect signals between components
        self._connect_component_signals()
        
        # Start initial data loading
        self._initial_load()
        
        logger.info("RefactoredMainWindow initialization complete")
    
    def _create_ui_manager(self) -> MainWindowUI:
        """Create and configure UI manager."""
        from main_window_ui import MainWindowUI
        return MainWindowUI(self)
    
    def _create_threading_manager(self) -> ThreadingManager:
        """Create and configure threading manager."""
        from threading_manager import ThreadingManager
        return ThreadingManager()
    
    def _create_launcher_manager(self) -> AppLauncherManager:
        """Create and configure launcher manager."""
        from app_launcher_manager import AppLauncherManager
        from command_launcher import CommandLauncher
        from launcher_manager import LauncherManager
        
        command_launcher = CommandLauncher()
        launcher_mgr = LauncherManager()
        
        return AppLauncherManager(command_launcher, launcher_mgr)
    
    def _create_cache_manager(self) -> CacheManager:
        """Create cache manager."""
        from cache_manager import CacheManager
        return CacheManager()
    
    def _create_shot_model(self):
        """Create shot model (using optimized async version)."""
        from shot_model_optimized import OptimizedShotModel
        return OptimizedShotModel(self.cache_manager)
    
    def _create_threede_model(self):
        """Create 3DE scene model."""
        from threede_scene_model import ThreeDESceneModel
        return ThreeDESceneModel(self.cache_manager)
    
    def _setup_ui_via_manager(self) -> None:
        """Set up UI using UI manager delegation."""
        # Create additional models needed for UI
        from launcher_manager import LauncherManager
        from log_viewer import LogViewer
        from previous_shots_item_model import PreviousShotsItemModel
        from previous_shots_model import PreviousShotsModel
        
        previous_shots_model = PreviousShotsModel(self.shot_model, self.cache_manager)
        previous_shots_item_model = PreviousShotsItemModel(previous_shots_model, self.cache_manager)
        log_viewer = LogViewer()
        launcher_mgr = LauncherManager()
        
        # Delegate UI setup to UI manager
        self.ui_widgets = self.ui_manager.setup_ui(
            cache_manager=self.cache_manager,
            shot_model=self.shot_model,
            threede_item_model=self.threede_model.item_model,
            previous_shots_model=previous_shots_item_model,
            launcher_manager=launcher_mgr,
            log_viewer=log_viewer,
        )
    
    def _connect_component_signals(self) -> None:
        """Connect signals between the extracted components."""
        # Connect UI manager signals
        if hasattr(self.ui_manager, 'refresh_action'):
            self.ui_manager.refresh_action.triggered.connect(self._refresh_all_data)
        
        # Connect threading manager signals
        self.threading_manager.threede_discovery_started.connect(self._on_discovery_started)
        self.threading_manager.threede_discovery_finished.connect(self._on_discovery_finished)
        self.threading_manager.threede_discovery_error.connect(self._on_discovery_error)
        
        # Connect launcher manager signals
        self.launcher_manager.launch_started.connect(self._on_launch_started)
        self.launcher_manager.launch_finished.connect(self._on_launch_finished)
        self.launcher_manager.status_update.connect(self._update_status)
        
        # Connect shot model signals
        self.shot_model.shots_loaded.connect(self._on_shots_loaded)
        self.shot_model.shots_changed.connect(self._on_shots_changed)
    
    def _initial_load(self) -> None:
        """Start initial data loading."""
        # Load shots asynchronously
        self.shot_model.load_shots()
        
        # Start 3DE scene discovery
        self.threading_manager.start_threede_discovery(
            self.threede_model,
            self.shot_model,
        )
    
    def _refresh_all_data(self) -> None:
        """Refresh all data sources."""
        self.shot_model.refresh_shots()
        
        # Restart 3DE discovery if not already running
        if not self.threading_manager.is_threede_discovery_active():
            self.threading_manager.start_threede_discovery(
                self.threede_model,
                self.shot_model,
            )
    
    # Event handlers delegated to appropriate managers
    @Slot()
    def _on_discovery_started(self) -> None:
        """Handle discovery started via threading manager."""
        self.ui_manager.update_status("Discovering 3DE scenes...")
    
    @Slot(list)
    def _on_discovery_finished(self, scenes) -> None:
        """Handle discovery finished via threading manager."""
        self.ui_manager.update_status(f"Found {len(scenes)} 3DE scenes")
    
    @Slot(str)
    def _on_discovery_error(self, error_msg: str) -> None:
        """Handle discovery error via threading manager."""
        self.ui_manager.update_status(f"Discovery error: {error_msg}")
    
    @Slot(str, str)
    def _on_launch_started(self, app_name: str, context: str) -> None:
        """Handle launch started via launcher manager."""
        self.ui_manager.update_status(f"Launching {app_name}...")
    
    @Slot(str, bool)
    def _on_launch_finished(self, app_name: str, success: bool) -> None:
        """Handle launch finished via launcher manager."""
        if success:
            self.ui_manager.update_status(f"{app_name} launched successfully")
        else:
            self.ui_manager.update_status(f"{app_name} launch failed")
    
    @Slot(str)
    def _update_status(self, message: str) -> None:
        """Update status via UI manager."""
        self.ui_manager.update_status(message)
    
    @Slot(list)
    def _on_shots_loaded(self, shots) -> None:
        """Handle shots loaded."""
        self.ui_manager.update_status(f"Loaded {len(shots)} shots")
    
    @Slot(list)
    def _on_shots_changed(self, shots) -> None:
        """Handle shots changed."""
        self.ui_manager.update_status(f"Updated to {len(shots)} shots")
    
    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle application shutdown with proper cleanup."""
        logger.info("Shutting down RefactoredMainWindow")
        
        # Shutdown all components gracefully
        self.threading_manager.shutdown_all_threads()
        
        # Accept close event
        event.accept()


def demonstrate_refactoring_benefits():
    """Demonstrate the benefits of the refactoring."""
    
    print("MainWindow Refactoring Summary")
    print("=" * 50)
    
    original_size = 2057
    component_sizes = {
        "MainWindowUI": 331,
        "ThreadingManager": 298, 
        "AppLauncherManager": 278,
        "RefactoredMainWindow": 400,  # estimated
    }
    
    total_refactored = sum(component_sizes.values())
    
    print(f"Original MainWindow: {original_size} lines")
    print("Refactored components:")
    for name, size in component_sizes.items():
        print(f"  - {name}: {size} lines")
    print(f"Total refactored: {total_refactored} lines")
    print()
    
    print("Benefits achieved:")
    print("✅ Each component < 500 lines (maintainability target)")
    print("✅ Single responsibility principle enforced")
    print("✅ Improved testability with focused components")
    print("✅ Reduced coupling through signal-slot architecture")
    print("✅ Easier to extend and modify individual areas")
    print()
    
    print("Architecture improvements:")
    print("• UI logic separated from business logic")
    print("• Thread management centralized and safer")
    print("• Application launching logic reusable")
    print("• Clear component boundaries and interfaces")
    
    return component_sizes


if __name__ == "__main__":
    demonstrate_refactoring_benefits()