"""Application launching logic for MainWindow.

This module extracts application launching functionality from MainWindow,
providing centralized management of VFX application launches with proper
error handling and status tracking.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal, Slot

if TYPE_CHECKING:
    from command_launcher import CommandLauncher
    from launcher_manager import LauncherManager
    from shot_model import Shot
    from threede_scene_model import ThreeDEScene

logger = logging.getLogger(__name__)


class AppLauncherManager(QObject):
    """Centralized application launching management.
    
    This class handles all application launching logic, including:
    - VFX application launches (3DE, Nuke, Maya, etc.)
    - Shot-based context launching
    - Scene-based context launching
    - Error handling and status reporting
    """
    
    # Signals for launcher events
    launch_started = Signal(str, str)  # app_name, context
    launch_finished = Signal(str, bool)  # app_name, success
    launch_error = Signal(str, str)  # app_name, error_message
    status_update = Signal(str)  # status_message
    
    def __init__(
        self,
        command_launcher: CommandLauncher,
        launcher_manager: LauncherManager,
    ) -> None:
        """Initialize application launcher manager.
        
        Args:
            command_launcher: Command execution handler
            launcher_manager: Custom launcher management
        """
        super().__init__()
        
        self.command_launcher = command_launcher
        self.launcher_manager = launcher_manager
        
        # Connect launcher manager signals
        self.launcher_manager.command_started.connect(self._on_launcher_started)
        self.launcher_manager.command_finished.connect(self._on_launcher_finished)
        self.command_launcher.command_error.connect(self._on_command_error)
        
        logger.debug("AppLauncherManager initialized")
    
    def launch_app_with_shot(self, app_name: str, shot: Shot | None = None) -> bool:
        """Launch VFX application with shot context.
        
        Args:
            app_name: Name of application to launch (3de, nuke, maya, etc.)
            shot: Optional shot to provide context
            
        Returns:
            True if launch initiated successfully, False otherwise
        """
        if not shot:
            logger.warning(f"Cannot launch {app_name}: No shot selected")
            self.status_update.emit(f"No shot selected for {app_name} launch")
            return False
            
        try:
            # Validate shot has required paths
            if not hasattr(shot, 'workspace_path') or not shot.workspace_path:
                logger.error(f"Shot {shot.full_name} missing workspace path")
                self.launch_error.emit(app_name, "Shot missing workspace path")
                return False
                
            # Build context information
            context = f"{shot.show}/{shot.sequence}/{shot.shot}"
            
            # Emit launch started signal
            self.launch_started.emit(app_name, context)
            self.status_update.emit(f"Launching {app_name} for shot {shot.full_name}...")
            
            # Execute launch command
            success = self._execute_app_launch(app_name, shot, None)
            
            if success:
                logger.info(f"Successfully launched {app_name} for shot {shot.full_name}")
                self.status_update.emit(f"{app_name} launched for {shot.full_name}")
            else:
                logger.error(f"Failed to launch {app_name} for shot {shot.full_name}")
                self.launch_error.emit(app_name, "Launch command failed")
                
            return success
            
        except Exception as e:
            logger.exception(f"Error launching {app_name} with shot {shot.full_name if shot else 'None'}: {e}")
            self.launch_error.emit(app_name, str(e))
            return False
    
    def launch_app_with_scene(self, app_name: str, scene: ThreeDEScene) -> bool:
        """Launch VFX application with 3DE scene context.
        
        Args:
            app_name: Name of application to launch
            scene: 3DE scene to provide context
            
        Returns:
            True if launch initiated successfully, False otherwise
        """
        try:
            # Validate scene has required paths
            if not scene.scene_path or not scene.scene_path.exists():
                logger.error(f"3DE scene path invalid: {scene.scene_path}")
                self.launch_error.emit(app_name, "Invalid scene path")
                return False
                
            # Build context information
            context = f"3DE Scene: {scene.scene_path.name}"
            
            # Emit launch started signal
            self.launch_started.emit(app_name, context)
            self.status_update.emit(f"Launching {app_name} with 3DE scene {scene.scene_path.name}...")
            
            # For 3DE scenes, we need to get the associated shot
            shot = self._get_shot_for_scene(scene)
            
            # Execute launch command
            success = self._execute_app_launch(app_name, shot, scene)
            
            if success:
                logger.info(f"Successfully launched {app_name} with 3DE scene {scene.scene_path.name}")
                self.status_update.emit(f"{app_name} launched with {scene.scene_path.name}")
            else:
                logger.error(f"Failed to launch {app_name} with 3DE scene {scene.scene_path.name}")
                self.launch_error.emit(app_name, "Launch command failed")
                
            return success
            
        except Exception as e:
            logger.exception(f"Error launching {app_name} with scene {scene.scene_path}: {e}")
            self.launch_error.emit(app_name, str(e))
            return False
    
    def _execute_app_launch(
        self, 
        app_name: str, 
        shot: Shot | None, 
        scene: ThreeDEScene | None
    ) -> bool:
        """Execute the actual application launch.
        
        Args:
            app_name: Name of application to launch
            shot: Optional shot context
            scene: Optional scene context
            
        Returns:
            True if launch successful, False otherwise
        """
        try:
            # For 3DE applications, handle scene-specific launching
            if app_name == "3de" and scene:
                return self._launch_threede_with_scene(scene)
            
            # For other applications, use shot-based launching
            if shot:
                return self._launch_app_with_shot_context(app_name, shot)
            
            # Fallback: launch application without specific context
            return self._launch_app_basic(app_name)
            
        except Exception as e:
            logger.exception(f"Error executing {app_name} launch: {e}")
            return False
    
    def _launch_threede_with_scene(self, scene: ThreeDEScene) -> bool:
        """Launch 3DE with specific scene file.
        
        Args:
            scene: 3DE scene to open
            
        Returns:
            True if launch successful, False otherwise
        """
        try:
            # Use command launcher to launch 3DE with scene
            return self.command_launcher.launch_app_with_scene("3de", scene)
            
        except Exception as e:
            logger.error(f"Failed to launch 3DE with scene {scene.scene_path}: {e}")
            return False
    
    def _launch_app_with_shot_context(self, app_name: str, shot: Shot) -> bool:
        """Launch application with shot workspace context.
        
        Args:
            app_name: Name of application to launch
            shot: Shot providing context
            
        Returns:
            True if launch successful, False otherwise
        """
        try:
            # Set current shot in command launcher
            self.command_launcher.set_current_shot(shot)
            
            # Launch application via command launcher
            return self.command_launcher.launch_app(app_name)
            
        except Exception as e:
            logger.error(f"Failed to launch {app_name} with shot context: {e}")
            return False
    
    def _launch_app_basic(self, app_name: str) -> bool:
        """Launch application without specific context.
        
        Args:
            app_name: Name of application to launch
            
        Returns:
            True if launch successful, False otherwise
        """
        try:
            # Clear current shot context
            self.command_launcher.set_current_shot(None)
            
            # Launch application via command launcher
            return self.command_launcher.launch_app(app_name)
            
        except Exception as e:
            logger.error(f"Failed to launch {app_name}: {e}")
            return False
    
    def _get_shot_for_scene(self, scene: ThreeDEScene) -> Shot | None:
        """Extract shot information from 3DE scene path.
        
        Args:
            scene: 3DE scene to analyze
            
        Returns:
            Associated Shot object or None if not found
        """
        try:
            # Parse shot information from scene path
            # Typical path: /shows/show/shots/sequence/shot/user/3de/scene.3de
            path_parts = scene.scene_path.parts
            
            if "shots" in path_parts:
                shots_idx = path_parts.index("shots")
                if shots_idx + 2 < len(path_parts):
                    show = path_parts[shots_idx - 1]
                    sequence = path_parts[shots_idx + 1]
                    shot_dir = path_parts[shots_idx + 2]
                    
                    # Extract shot from directory name
                    if shot_dir.startswith(f"{sequence}_"):
                        shot = shot_dir[len(sequence) + 1:]
                    else:
                        shot = shot_dir
                    
                    # Create Shot object
                    from shot_model import Shot
                    workspace_path = "/".join(path_parts[:shots_idx + 3])
                    
                    return Shot(
                        show=show,
                        sequence=sequence,
                        shot=shot,
                        workspace_path=workspace_path,
                    )
            
            return None
            
        except Exception as e:
            logger.debug(f"Could not extract shot from scene path {scene.scene_path}: {e}")
            return None
    
    @Slot(str)
    def _on_launcher_started(self, launcher_id: str) -> None:
        """Handle launcher started event.
        
        Args:
            launcher_id: ID of started launcher
        """
        self.status_update.emit(f"Launcher {launcher_id} started")
        logger.debug(f"Launcher started: {launcher_id}")
    
    @Slot(str, bool)
    def _on_launcher_finished(self, launcher_id: str, success: bool) -> None:
        """Handle launcher finished event.
        
        Args:
            launcher_id: ID of finished launcher
            success: Whether launcher completed successfully
        """
        if success:
            self.status_update.emit(f"Launcher {launcher_id} completed successfully")
            logger.info(f"Launcher completed: {launcher_id}")
        else:
            self.status_update.emit(f"Launcher {launcher_id} failed")
            logger.warning(f"Launcher failed: {launcher_id}")
    
    @Slot(str, str)
    def _on_command_error(self, timestamp: str, error: str) -> None:
        """Handle command execution error.
        
        Args:
            timestamp: Error timestamp
            error: Error message
        """
        self.status_update.emit(f"Command error: {error}")
        logger.error(f"Command error at {timestamp}: {error}")
    
    def get_available_applications(self) -> list[str]:
        """Get list of available applications for launching.
        
        Returns:
            List of available application names
        """
        try:
            # Get from config
            from config import Config
            return list(Config.APPS.keys())
        except Exception:
            # Fallback list
            return ["3de", "nuke", "maya", "rv"]
    
    def is_application_available(self, app_name: str) -> bool:
        """Check if application is available for launching.
        
        Args:
            app_name: Name of application to check
            
        Returns:
            True if application is available, False otherwise
        """
        available_apps = self.get_available_applications()
        return app_name.lower() in [app.lower() for app in available_apps]