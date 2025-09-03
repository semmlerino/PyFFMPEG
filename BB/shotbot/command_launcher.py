"""Command launcher for executing applications in shot context."""

from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal

from config import Config

if TYPE_CHECKING:
    from nuke_script_generator import NukeScriptGenerator as NukeScriptGeneratorType
    from persistent_terminal_manager import PersistentTerminalManager
    from raw_plate_finder import RawPlateFinder as RawPlateFinderType
    from shot_model import Shot
    from threede_scene_model import ThreeDEScene
    from undistortion_finder import UndistortionFinder as UndistortionFinderType
else:
    # Import at runtime to avoid circular imports
    from shot_model import Shot  # noqa: TC001
    from threede_scene_model import ThreeDEScene  # noqa: TC001

logger = logging.getLogger(__name__)


class CommandLauncher(QObject):
    """Handles launching applications in shot context.
    
    This class uses dependency injection for better testability and following SOLID principles.
    Dependencies are passed as constructor parameters rather than imported directly.
    """

    # Signals
    command_executed = Signal(str, str)  # timestamp, command
    command_error = Signal(str, str)  # timestamp, error

    def __init__(
        self,
        raw_plate_finder: type[RawPlateFinderType] | None = None,
        undistortion_finder: type[UndistortionFinderType] | None = None,
        nuke_script_generator: type[NukeScriptGeneratorType] | None = None,
        persistent_terminal: PersistentTerminalManager | None = None,
    ) -> None:
        """Initialize CommandLauncher with optional dependencies.
        
        Args:
            raw_plate_finder: Class for finding raw plates (defaults to RawPlateFinder)
            undistortion_finder: Class for finding undistortion files (defaults to UndistortionFinder)
            nuke_script_generator: Class for generating Nuke scripts (defaults to NukeScriptGenerator)
            persistent_terminal: Optional persistent terminal manager for single terminal mode
        """
        super().__init__()
        self.current_shot: Shot | None = None
        self.persistent_terminal = persistent_terminal
        
        # Use injected dependencies or fall back to defaults
        if raw_plate_finder is None:
            from raw_plate_finder import RawPlateFinder
            self._raw_plate_finder = RawPlateFinder
        else:
            self._raw_plate_finder = raw_plate_finder
            
        if undistortion_finder is None:
            from undistortion_finder import UndistortionFinder
            self._undistortion_finder = UndistortionFinder
        else:
            self._undistortion_finder = undistortion_finder
            
        if nuke_script_generator is None:
            from nuke_script_generator import NukeScriptGenerator
            self._nuke_script_generator = NukeScriptGenerator
        else:
            self._nuke_script_generator = nuke_script_generator

    def set_current_shot(self, shot: Shot | None) -> None:
        """Set the current shot context."""
        self.current_shot = shot

    def _is_rez_available(self) -> bool:
        """Check if rez environment is available.
        
        Returns:
            True if rez is available and should be used
        """
        if not Config.USE_REZ_ENVIRONMENT:
            return False
            
        # Check for REZ_USED environment variable (indicates we're in a rez env)
        if Config.REZ_AUTO_DETECT and os.environ.get("REZ_USED"):
            return True
            
        # Try to find rez command
        try:
            result = subprocess.run(
                ["which", "rez"], 
                capture_output=True, 
                text=True,
                timeout=2
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
            
    def _get_rez_packages_for_app(self, app_name: str) -> list[str]:
        """Get rez packages for the specified application.
        
        Args:
            app_name: Name of the application
            
        Returns:
            List of rez packages to load
        """
        if app_name == "nuke":
            return Config.REZ_NUKE_PACKAGES
        elif app_name == "maya":
            return Config.REZ_MAYA_PACKAGES
        elif app_name == "3de":
            return Config.REZ_3DE_PACKAGES
        return []

    def _validate_path_for_shell(self, path: str) -> str:
        """Validate and escape a path for safe use in shell commands.

        Args:
            path: Path to validate and escape

        Returns:
            Safely escaped path string

        Raises:
            ValueError: If path contains dangerous characters that cannot be escaped
        """
        import shlex

        # Check for command injection attempts
        dangerous_chars = [
            ";",
            "&&",
            "||",
            "|",  # Command separators
            ">",
            "<",
            ">>",
            ">&",  # Redirections
            "`",
            "$(",  # Command substitution
            "\n",
            "\r",  # Newlines that could break out
            "${",
            "$((",  # Variable/arithmetic expansion
        ]

        for char in dangerous_chars:
            if char in path:
                raise ValueError(
                    f"Path contains dangerous character '{char}' that could allow command injection: {path[:100]}"
                )

        # Additional validation for known dangerous patterns
        dangerous_patterns = [
            "../",  # Path traversal
            "/..",  # Path traversal variant
            "~/.",  # Hidden file access attempts
        ]

        for pattern in dangerous_patterns:
            if pattern in path:
                raise ValueError(
                    f"Path contains dangerous pattern '{pattern}': {path[:100]}"
                )

        # Use shlex.quote for safe shell escaping
        # This adds single quotes around the string and escapes any single quotes within
        return shlex.quote(path)

    def launch_app(
        self,
        app_name: str,
        include_undistortion: bool = False,
        include_raw_plate: bool = False,
    ) -> bool:
        """Launch an application in the current shot context.

        Args:
            app_name: Name of the application to launch
            include_undistortion: Whether to include undistortion nodes (Nuke only)
            include_raw_plate: Whether to include raw plate Read node (Nuke only)

        Returns:
            True if launch was successful, False otherwise
        """
        if not self.current_shot:
            self._emit_error("No shot selected")
            return False

        if app_name not in Config.APPS:
            self._emit_error(f"Unknown application: {app_name}")
            return False

        # Get the command
        command = Config.APPS[app_name]

        # Handle raw plate and undistortion for Nuke (integrated approach)
        if app_name == "nuke" and (include_raw_plate or include_undistortion):
            raw_plate_path = None
            undistortion_path = None

            # Get raw plate if requested
            if include_raw_plate:
                raw_plate_path = self._raw_plate_finder.find_latest_raw_plate(
                    self.current_shot.workspace_path,
                    self.current_shot.full_name,
                )
                # Verify plate exists
                if raw_plate_path and not self._raw_plate_finder.verify_plate_exists(
                    raw_plate_path,
                ):
                    raw_plate_path = None

            # Get undistortion if requested
            if include_undistortion:
                undistortion_path = self._undistortion_finder.find_latest_undistortion(
                    self.current_shot.workspace_path,
                    self.current_shot.full_name,
                )

            # Handle different scenarios based on what we have
            if raw_plate_path or undistortion_path:
                if Config.NUKE_UNDISTORTION_MODE == "direct" and undistortion_path and not raw_plate_path:
                    # Direct mode: Open undistortion file directly (no plate)
                    safe_undist_path = self._validate_path_for_shell(str(undistortion_path))
                    command = f"{command} {safe_undist_path}"
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    version = self._undistortion_finder.get_version_from_path(undistortion_path)
                    self.command_executed.emit(
                        timestamp,
                        f"Opening undistortion file directly: {version}",
                    )
                elif raw_plate_path and undistortion_path and Config.NUKE_USE_LOADER_SCRIPT:
                    # Both plate and undistortion - create loader script
                    script_path = self._nuke_script_generator.create_loader_script(
                        raw_plate_path,
                        str(undistortion_path),
                        self.current_shot.full_name,
                    )
                    if script_path:
                        safe_script_path = self._validate_path_for_shell(script_path)
                        command = f"{command} {safe_script_path}"
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        plate_version = self._raw_plate_finder.get_version_from_path(raw_plate_path)
                        undist_version = self._undistortion_finder.get_version_from_path(undistortion_path)
                        self.command_executed.emit(
                            timestamp,
                            f"Created loader script with plate ({plate_version}) and undistortion ({undist_version})",
                        )
                    else:
                        # Fallback to old parsing method if loader script fails
                        script_path = (
                            self._nuke_script_generator.create_plate_script_with_undistortion(
                                raw_plate_path,
                                str(undistortion_path),
                                self.current_shot.full_name,
                            )
                        )
                        if script_path:
                            safe_script_path = self._validate_path_for_shell(script_path)
                            command = f"{command} {safe_script_path}"
                            timestamp = datetime.now().strftime("%H:%M:%S")
                            self.command_executed.emit(
                                timestamp,
                                "Warning: Using fallback parsing method for undistortion",
                            )
                        else:
                            timestamp = datetime.now().strftime("%H:%M:%S")
                            self.command_executed.emit(
                                timestamp,
                                "Error: Failed to generate Nuke script",
                            )
                elif raw_plate_path:
                    # Plate only
                    script_path = self._nuke_script_generator.create_plate_script(
                        raw_plate_path,
                        self.current_shot.full_name,
                    )
                    if script_path:
                        safe_script_path = self._validate_path_for_shell(script_path)
                        command = f"{command} {safe_script_path}"
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        version = self._raw_plate_finder.get_version_from_path(raw_plate_path)
                        self.command_executed.emit(
                            timestamp,
                            f"Generated Nuke script with plate: {version}",
                        )
                    else:
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        self.command_executed.emit(
                            timestamp,
                            "Error: Failed to generate plate script",
                        )
                elif undistortion_path and Config.NUKE_UNDISTORTION_MODE != "direct":
                    # Undistortion only with parse mode (backward compatibility)
                    script_path = (
                        self._nuke_script_generator.create_plate_script_with_undistortion(
                            "",
                            str(undistortion_path),
                            self.current_shot.full_name,
                        )
                    )
                    if script_path:
                        safe_script_path = self._validate_path_for_shell(script_path)
                        command = f"{command} {safe_script_path}"
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        version = self._undistortion_finder.get_version_from_path(undistortion_path)
                        self.command_executed.emit(
                            timestamp,
                            f"Generated Nuke script with undistortion (parse mode): {version}",
                        )
                    else:
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        self.command_executed.emit(
                            timestamp,
                            "Error: Failed to generate undistortion script",
                        )
            else:
                # Log warnings for missing files
                timestamp = datetime.now().strftime("%H:%M:%S")
                if include_raw_plate:
                    self.command_executed.emit(
                        timestamp,
                        "Warning: Raw plate not found or no frames exist for this shot",
                    )
                if include_undistortion:
                    self.command_executed.emit(
                        timestamp,
                        "Warning: Undistortion file not found for this shot",
                    )

        # Build full command with ws (workspace setup)
        # Validate and escape workspace path to prevent injection
        try:
            safe_workspace_path = self._validate_path_for_shell(
                self.current_shot.workspace_path
            )
            ws_command = f"ws {safe_workspace_path} && {command}"
        except ValueError as e:
            self._emit_error(f"Invalid workspace path: {str(e)}")
            return False

        # Wrap with rez environment if available
        if self._is_rez_available():
            rez_packages = self._get_rez_packages_for_app(app_name)
            if rez_packages:
                packages_str = " ".join(rez_packages)
                # Use bash -ilc for interactive login shell to ensure shell functions like ws are loaded
                # The -i flag is crucial for loading shell functions from configuration files
                full_command = f'rez env {packages_str} -- bash -ilc "{ws_command}"'
                logger.debug(f"Constructed rez command with bash -ilc: {full_command}")
                timestamp = datetime.now().strftime("%H:%M:%S")
                self.command_executed.emit(
                    timestamp, 
                    f"Using rez environment with packages: {packages_str}"
                )
            else:
                full_command = ws_command
        else:
            full_command = ws_command

        # Log the command
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.command_executed.emit(timestamp, full_command)

        # Use persistent terminal if available and enabled
        if self.persistent_terminal and Config.USE_PERSISTENT_TERMINAL:
            logger.info(f"Sending command to persistent terminal: {full_command}")
            success = self.persistent_terminal.send_command(full_command)
            if success:
                logger.debug("Command successfully sent to persistent terminal")
                return True
            else:
                logger.warning("Failed to send command to persistent terminal, falling back to new terminal")
                # Fall through to launch new terminal
        
        # Launch in new terminal (original behavior)
        try:
            # Execute in a new terminal
            # This will work on Linux with common terminal emulators
            terminal_commands = [
                # Try gnome-terminal first with interactive bash
                ["gnome-terminal", "--", "bash", "-i", "-c", full_command],
                # Try xterm as fallback with interactive bash (using list for safety)
                ["xterm", "-e", "bash", "-i", "-c", full_command],
                # Try konsole with interactive bash
                ["konsole", "-e", "bash", "-i", "-c", full_command],
            ]

            for term_cmd in terminal_commands:
                try:
                    subprocess.Popen(term_cmd)
                    return True
                except FileNotFoundError:
                    continue

            # If no terminal worked, try direct execution with interactive bash
            subprocess.Popen(["/bin/bash", "-i", "-c", full_command])
            return True

        except Exception as e:
            self._emit_error(f"Failed to launch {app_name}: {str(e)}")
            return False

    def launch_app_with_scene(self, app_name: str, scene: ThreeDEScene) -> bool:
        """Launch an application with a specific 3DE scene file.

        Args:
            app_name: Name of the application to launch
            scene: The 3DE scene to open

        Returns:
            True if launch was successful, False otherwise
        """
        if app_name not in Config.APPS:
            self._emit_error(f"Unknown application: {app_name}")
            return False

        # Get the command
        command = Config.APPS[app_name]

        # Include the scene file in the command
        # Validate and escape scene path to prevent injection
        try:
            safe_scene_path = self._validate_path_for_shell(str(scene.scene_path))
            command = f"{command} {safe_scene_path}"
        except ValueError as e:
            self._emit_error(f"Invalid scene path: {str(e)}")
            return False

        # Build full command with ws (workspace setup)
        # Validate and escape workspace path to prevent injection
        try:
            safe_workspace_path = self._validate_path_for_shell(scene.workspace_path)
            ws_command = f"ws {safe_workspace_path} && {command}"
        except ValueError as e:
            self._emit_error(f"Invalid workspace path: {str(e)}")
            return False

        # Wrap with rez environment if available
        if self._is_rez_available():
            rez_packages = self._get_rez_packages_for_app(app_name)
            if rez_packages:
                packages_str = " ".join(rez_packages)
                # Use bash -ilc for interactive login shell to ensure shell functions are loaded
                full_command = f'rez env {packages_str} -- bash -ilc "{ws_command}"'
                logger.debug(f"Constructed rez scene command with bash -ilc: {full_command}")
            else:
                full_command = ws_command
        else:
            full_command = ws_command

        # Log the command
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.command_executed.emit(
            timestamp,
            f"{full_command} (Scene by: {scene.user}, Plate: {scene.plate})",
        )

        # Use persistent terminal if available and enabled
        if self.persistent_terminal and Config.USE_PERSISTENT_TERMINAL:
            logger.info(f"Sending scene command to persistent terminal: {full_command}")
            success = self.persistent_terminal.send_command(full_command)
            if success:
                logger.debug("Scene command successfully sent to persistent terminal")
                return True
            else:
                logger.warning("Failed to send command to persistent terminal, falling back to new terminal")
                # Fall through to launch new terminal
        
        # Launch in new terminal (original behavior)
        try:
            # Execute in a new terminal
            terminal_commands = [
                # Try gnome-terminal first with interactive bash
                ["gnome-terminal", "--", "bash", "-i", "-c", full_command],
                # Try xterm as fallback with interactive bash (using list for safety)
                ["xterm", "-e", "bash", "-i", "-c", full_command],
                # Try konsole with interactive bash
                ["konsole", "-e", "bash", "-i", "-c", full_command],
            ]

            for term_cmd in terminal_commands:
                try:
                    subprocess.Popen(term_cmd)
                    return True
                except FileNotFoundError:
                    continue

            # If no terminal worked, try direct execution with interactive bash
            subprocess.Popen(["/bin/bash", "-i", "-c", full_command])
            return True

        except Exception as e:
            self._emit_error(f"Failed to launch {app_name} with scene: {str(e)}")
            return False

    def launch_app_with_scene_context(
        self,
        app_name: str,
        scene: ThreeDEScene,
        include_undistortion: bool = False,
        include_raw_plate: bool = False,
    ) -> bool:
        """Launch an application in the context of a 3DE scene (shot context only, no scene file).

        Args:
            app_name: Name of the application to launch
            scene: The 3DE scene providing shot context
            include_undistortion: Whether to include undistortion nodes (Nuke only)
            include_raw_plate: Whether to include raw plate Read node (Nuke only)

        Returns:
            True if launch was successful, False otherwise
        """
        if app_name not in Config.APPS:
            self._emit_error(f"Unknown application: {app_name}")
            return False

        # Get the command
        command = Config.APPS[app_name]

        # Handle raw plate for Nuke
        if app_name == "nuke" and include_raw_plate:
            raw_plate_path = self._raw_plate_finder.find_latest_raw_plate(
                scene.workspace_path,
                scene.full_name,
            )

            if raw_plate_path:
                # Verify at least one frame exists
                if self._raw_plate_finder.verify_plate_exists(raw_plate_path):
                    # Create a Nuke script with the plate loaded
                    script_path = self._nuke_script_generator.create_plate_script(
                        raw_plate_path,
                        scene.full_name,
                    )

                    if script_path:
                        # Launch Nuke with the generated script
                        command = f"{command} {script_path}"
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        version = self._raw_plate_finder.get_version_from_path(raw_plate_path)
                        self.command_executed.emit(
                            timestamp,
                            f"Created Nuke script with plate: {version}/{raw_plate_path.split('/')[-1]}",
                        )
                    else:
                        # Fallback to just passing the path (safely escaped)
                        safe_plate_path = self._validate_path_for_shell(raw_plate_path)
                        command = f"{command} {safe_plate_path}"
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        version = self._raw_plate_finder.get_version_from_path(raw_plate_path)
                        self.command_executed.emit(
                            timestamp,
                            f"Found raw plate: {version}/{raw_plate_path.split('/')[-1]}",
                        )
                else:
                    # Log warning if plate path found but no frames exist
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    self.command_executed.emit(
                        timestamp,
                        "Warning: Raw plate path found but no frames exist",
                    )
            else:
                # Log warning if raw plate requested but not found
                timestamp = datetime.now().strftime("%H:%M:%S")
                self.command_executed.emit(
                    timestamp,
                    "Warning: Raw plate not found for this shot",
                )

        # Handle undistortion for Nuke
        if app_name == "nuke" and include_undistortion:
            undistortion_path = self._undistortion_finder.find_latest_undistortion(
                scene.workspace_path,
                scene.full_name,
            )

            if undistortion_path:
                # Include the undistortion file in the Nuke command (safely escaped)
                safe_undistortion_path = self._validate_path_for_shell(
                    str(undistortion_path)
                )
                command = f"{command} {safe_undistortion_path}"
                timestamp = datetime.now().strftime("%H:%M:%S")
                version = self._undistortion_finder.get_version_from_path(undistortion_path)
                self.command_executed.emit(
                    timestamp,
                    f"Found undistortion file: {version}/{undistortion_path.name}",
                )
            else:
                # Log warning if undistortion requested but not found
                timestamp = datetime.now().strftime("%H:%M:%S")
                self.command_executed.emit(
                    timestamp,
                    "Warning: Undistortion file not found for this shot",
                )

        # Build full command with ws (workspace setup)
        # Validate and escape workspace path to prevent injection
        try:
            safe_workspace_path = self._validate_path_for_shell(scene.workspace_path)
            full_command = f"ws {safe_workspace_path} && {command}"
        except ValueError as e:
            self._emit_error(f"Invalid workspace path: {str(e)}")
            return False

        # Log the command
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.command_executed.emit(
            timestamp,
            f"{full_command} (Context: {scene.user}'s {scene.plate})",
        )

        try:
            # Execute in a new terminal
            terminal_commands = [
                # Try gnome-terminal first with interactive bash
                ["gnome-terminal", "--", "bash", "-i", "-c", full_command],
                # Try xterm as fallback with interactive bash (using list for safety)
                ["xterm", "-e", "bash", "-i", "-c", full_command],
                # Try konsole with interactive bash
                ["konsole", "-e", "bash", "-i", "-c", full_command],
            ]

            for term_cmd in terminal_commands:
                try:
                    subprocess.Popen(term_cmd)
                    return True
                except FileNotFoundError:
                    continue

            # If no terminal worked, try direct execution with interactive bash
            subprocess.Popen(["/bin/bash", "-i", "-c", full_command])
            return True

        except Exception as e:
            self._emit_error(f"Failed to launch {app_name} in scene context: {str(e)}")
            return False

    def _emit_error(self, error: str) -> None:
        """Emit error with timestamp."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.command_error.emit(timestamp, error)
