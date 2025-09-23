"""Command launcher for executing applications in shot context."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal

from config import Config
from logging_mixin import LoggingMixin

if TYPE_CHECKING:
    from maya_latest_finder import MayaLatestFinder as MayaLatestFinderType
    from nuke_script_generator import NukeScriptGenerator as NukeScriptGeneratorType
    from persistent_terminal_manager import PersistentTerminalManager
    from raw_plate_finder import RawPlateFinder as RawPlateFinderType
    from shot_model import Shot
    from threede_latest_finder import ThreeDELatestFinder as ThreeDELatestFinderType
    from threede_scene_model import ThreeDEScene
    from undistortion_finder import UndistortionFinder as UndistortionFinderType
else:
    # Import at runtime to avoid circular imports
    from shot_model import Shot  # noqa: TC001
    from threede_scene_model import ThreeDEScene  # noqa: TC001


class CommandLauncher(LoggingMixin, QObject):
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
        threede_latest_finder: type[ThreeDELatestFinderType] | None = None,
        maya_latest_finder: type[MayaLatestFinderType] | None = None,
        persistent_terminal: PersistentTerminalManager | None = None,
    ) -> None:
        """Initialize CommandLauncher with optional dependencies.

        Args:
            raw_plate_finder: Class for finding raw plates (defaults to RawPlateFinder)
            undistortion_finder: Class for finding undistortion files (defaults to UndistortionFinder)
            nuke_script_generator: Class for generating Nuke scripts (defaults to NukeScriptGenerator)
            threede_latest_finder: Class for finding latest 3DE scenes (defaults to ThreeDELatestFinder)
            maya_latest_finder: Class for finding latest Maya scenes (defaults to MayaLatestFinder)
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

        if threede_latest_finder is None:
            from threede_latest_finder import ThreeDELatestFinder

            self._threede_latest_finder = ThreeDELatestFinder
        else:
            self._threede_latest_finder = threede_latest_finder

        if maya_latest_finder is None:
            from maya_latest_finder import MayaLatestFinder

            self._maya_latest_finder = MayaLatestFinder
        else:
            self._maya_latest_finder = maya_latest_finder

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
                ["which", "rez"], capture_output=True, text=True, timeout=2
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

    def _get_nuke_environment_fixes(self) -> str:
        """Generate environment variable exports to fix Nuke OCIO crashes.

        Returns:
            String containing bash export statements for environment fixes
        """
        if not Config.NUKE_FIX_OCIO_CRASH:
            return ""

        env_exports: list[str] = []

        # Skip problematic plugin paths by modifying NUKE_PATH at runtime
        if (
            Config.NUKE_SKIP_PROBLEMATIC_PLUGINS
            and Config.NUKE_PROBLEMATIC_PLUGIN_PATHS
        ):
            self.logger.info(
                f"Setting up runtime filter for {len(Config.NUKE_PROBLEMATIC_PLUGIN_PATHS)} problematic "
                f"plugin paths in NUKE_PATH"
            )

            # Build grep patterns for all problematic paths
            # Each path needs to be escaped for use in grep
            grep_patterns: list[str] = []
            for problematic_path in Config.NUKE_PROBLEMATIC_PLUGIN_PATHS:
                # Escape special characters for grep
                escaped_path = problematic_path.replace(".", r"\.")
                grep_patterns.append(f'-e "{escaped_path}"')

            grep_pattern_str = " ".join(grep_patterns)

            # Create a bash command that filters NUKE_PATH at runtime
            # This runs AFTER rez has set up the environment
            filter_command = (
                f'FILTERED_NUKE_PATH=$(echo "$NUKE_PATH" | tr ":" "\\n" | '
                f'grep -v {grep_pattern_str} | tr "\\n" ":" | sed "s/:$//") && '
                f'export NUKE_PATH="$FILTERED_NUKE_PATH"'
            )

            env_exports.append(filter_command)

            self.logger.debug(f"Generated runtime NUKE_PATH filter: {filter_command}")

        # Set fallback OCIO configuration if the default one might be problematic
        if Config.NUKE_OCIO_FALLBACK_CONFIG:
            # Check if a fallback config exists
            fallback_config = Config.NUKE_OCIO_FALLBACK_CONFIG
            if os.path.exists(fallback_config):
                env_exports.append(f'export OCIO="{fallback_config}"')
                self.logger.info(f"Using fallback OCIO config: {fallback_config}")
            else:
                # Unset OCIO to use Nuke's built-in default
                env_exports.append("unset OCIO")
                self.logger.info("Unsetting OCIO to use Nuke's built-in configuration")

        # Additional stability environment variables
        env_exports.extend(
            [
                "export NUKE_DISABLE_CRASH_REPORTING=1",  # Disable crash reporting to avoid hang
                'export NUKE_TEMP_DIR="/tmp"',  # Ensure temp directory is accessible
                'export NUKE_DISK_CACHE="/tmp/nuke_cache"',  # Set disk cache location
            ]
        )

        if env_exports:
            env_string = " && ".join(env_exports)
            self.logger.debug(f"Generated Nuke environment fixes: {env_string}")
            return env_string + " && "

        return ""

    def launch_app(
        self,
        app_name: str,
        include_undistortion: bool = False,
        include_raw_plate: bool = False,
        open_latest_threede: bool = False,
        open_latest_maya: bool = False,
        open_latest_scene: bool = False,
        create_new_file: bool = False,
    ) -> bool:
        """Launch an application in the current shot context.

        Args:
            app_name: Name of the application to launch
            include_undistortion: Whether to include undistortion nodes (Nuke only)
            include_raw_plate: Whether to include raw plate Read node (Nuke only)
            open_latest_threede: Whether to open the latest 3DE scene file (3DE only)
            open_latest_maya: Whether to open the latest Maya scene file (Maya only)
            open_latest_scene: Whether to open the latest Nuke script (Nuke only)
            create_new_file: Whether to create a new version (Nuke only)

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

        # Apply Nuke-specific environment fixes to prevent crashes
        if app_name == "nuke" and Config.NUKE_FIX_OCIO_CRASH:
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.command_executed.emit(
                timestamp,
                "Applying Nuke environment fixes to prevent OCIO plugin crashes...",
            )

        # Handle Nuke workspace scripts (open latest or create new)
        if app_name == "nuke" and (open_latest_scene or create_new_file):
            from nuke_workspace_manager import NukeWorkspaceManager

            manager = NukeWorkspaceManager()

            # Note: open_latest_scene takes priority if both are checked
            if open_latest_scene and create_new_file:
                create_new_file = False

            if open_latest_scene:
                # Try to find existing script
                script_dir = manager.get_workspace_script_directory(
                    self.current_shot.workspace_path
                )
                latest_script = manager.find_latest_nuke_script(
                    script_dir, self.current_shot.full_name
                )

                if latest_script:
                    # Open existing script
                    safe_script_path = self._validate_path_for_shell(str(latest_script))
                    command = f"{command} {safe_script_path}"
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    self.command_executed.emit(
                        timestamp,
                        f"Opening existing Nuke script: {latest_script.name}",
                    )
                else:
                    # No existing script, create v001
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    self.command_executed.emit(
                        timestamp,
                        "No existing Nuke scripts found, creating v001...",
                    )

                    saved_path = None
                    # Create a basic script or with plate if requested
                    if include_raw_plate:
                        raw_plate_path = self._raw_plate_finder.find_latest_raw_plate(
                            self.current_shot.workspace_path,
                            self.current_shot.full_name,
                        )
                        if (
                            raw_plate_path
                            and self._raw_plate_finder.verify_plate_exists(
                                raw_plate_path
                            )
                        ):
                            saved_path = self._nuke_script_generator.create_workspace_plate_script(
                                raw_plate_path,
                                self.current_shot.workspace_path,
                                self.current_shot.full_name,
                                version=1,
                            )
                        else:
                            # Create empty script
                            script_content = (
                                self._nuke_script_generator.create_plate_script(
                                    "", self.current_shot.full_name
                                )
                            )
                            if script_content:
                                with open(script_content, encoding="utf-8") as f:
                                    content = f.read()
                                saved_path = (
                                    self._nuke_script_generator.save_workspace_script(
                                        content,
                                        self.current_shot.workspace_path,
                                        self.current_shot.full_name,
                                        version=1,
                                    )
                                )
                    else:
                        # Create empty script
                        script_content = (
                            self._nuke_script_generator.create_plate_script(
                                "", self.current_shot.full_name
                            )
                        )
                        if script_content:
                            with open(script_content, encoding="utf-8") as f:
                                content = f.read()
                            saved_path = (
                                self._nuke_script_generator.save_workspace_script(
                                    content,
                                    self.current_shot.workspace_path,
                                    self.current_shot.full_name,
                                    version=1,
                                )
                            )

                    if saved_path:
                        safe_script_path = self._validate_path_for_shell(saved_path)
                        command = f"{command} {safe_script_path}"
                        self.command_executed.emit(
                            timestamp,
                            "Created and opening new Nuke script: v001",
                        )
                    else:
                        self._emit_error("Failed to create Nuke script")
                        return False

            elif create_new_file:
                # Always create new version
                script_dir = manager.get_workspace_script_directory(
                    self.current_shot.workspace_path
                )
                _, version = manager.get_next_script_path(
                    script_dir, self.current_shot.full_name
                )

                timestamp = datetime.now().strftime("%H:%M:%S")
                self.command_executed.emit(
                    timestamp,
                    f"Creating new Nuke script version: v{version:03d}",
                )

                saved_path = None
                # Create script with plate if requested
                if include_raw_plate:
                    raw_plate_path = self._raw_plate_finder.find_latest_raw_plate(
                        self.current_shot.workspace_path,
                        self.current_shot.full_name,
                    )
                    if raw_plate_path and self._raw_plate_finder.verify_plate_exists(
                        raw_plate_path
                    ):
                        saved_path = (
                            self._nuke_script_generator.create_workspace_plate_script(
                                raw_plate_path,
                                self.current_shot.workspace_path,
                                self.current_shot.full_name,
                                version=version,
                            )
                        )
                    else:
                        # Create empty script
                        script_content = (
                            self._nuke_script_generator.create_plate_script(
                                "", self.current_shot.full_name
                            )
                        )
                        if script_content:
                            with open(script_content, encoding="utf-8") as f:
                                content = f.read()
                            saved_path = (
                                self._nuke_script_generator.save_workspace_script(
                                    content,
                                    self.current_shot.workspace_path,
                                    self.current_shot.full_name,
                                    version=version,
                                )
                            )
                else:
                    # Create empty script
                    script_content = self._nuke_script_generator.create_plate_script(
                        "", self.current_shot.full_name
                    )
                    if script_content:
                        with open(script_content, encoding="utf-8") as f:
                            content = f.read()
                        saved_path = self._nuke_script_generator.save_workspace_script(
                            content,
                            self.current_shot.workspace_path,
                            self.current_shot.full_name,
                            version=version,
                        )

                if saved_path:
                    safe_script_path = self._validate_path_for_shell(saved_path)
                    command = f"{command} {safe_script_path}"
                    self.command_executed.emit(
                        timestamp,
                        f"Created and opening new Nuke script: v{version:03d}",
                    )
                else:
                    self._emit_error("Failed to create Nuke script")
                    return False

            # Skip the normal raw plate/undistortion handling if we've already handled it
            # in workspace script creation

        # Handle raw plate and undistortion for Nuke (integrated approach) - only if not using workspace scripts
        elif app_name == "nuke" and (include_raw_plate or include_undistortion):
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
                if (
                    Config.NUKE_UNDISTORTION_MODE == "direct"
                    and undistortion_path
                    and not raw_plate_path
                ):
                    # Direct mode: Open undistortion file directly (no plate)
                    safe_undist_path = self._validate_path_for_shell(
                        str(undistortion_path)
                    )
                    command = f"{command} {safe_undist_path}"
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    version = self._undistortion_finder.get_version_from_path(
                        undistortion_path
                    )
                    self.command_executed.emit(
                        timestamp,
                        f"Opening undistortion file directly: {version}",
                    )
                elif (
                    raw_plate_path
                    and undistortion_path
                    and Config.NUKE_USE_LOADER_SCRIPT
                ):
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
                        plate_version = self._raw_plate_finder.get_version_from_path(
                            raw_plate_path
                        )
                        undist_version = (
                            self._undistortion_finder.get_version_from_path(
                                undistortion_path
                            )
                        )
                        self.command_executed.emit(
                            timestamp,
                            f"Created loader script with plate ({plate_version}) and undistortion ({undist_version})",
                        )
                    else:
                        # Fallback to old parsing method if loader script fails
                        script_path = self._nuke_script_generator.create_plate_script_with_undistortion(
                            raw_plate_path,
                            str(undistortion_path),
                            self.current_shot.full_name,
                        )
                        if script_path:
                            safe_script_path = self._validate_path_for_shell(
                                script_path
                            )
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
                        version = self._raw_plate_finder.get_version_from_path(
                            raw_plate_path
                        )
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
                    script_path = self._nuke_script_generator.create_plate_script_with_undistortion(
                        "",
                        str(undistortion_path),
                        self.current_shot.full_name,
                    )
                    if script_path:
                        safe_script_path = self._validate_path_for_shell(script_path)
                        command = f"{command} {safe_script_path}"
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        version = self._undistortion_finder.get_version_from_path(
                            undistortion_path
                        )
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

        # Handle 3DE with latest scene file
        if app_name == "3de" and open_latest_threede:
            latest_scene = self._threede_latest_finder.find_latest_threede_scene(
                self.current_shot.workspace_path,
                self.current_shot.full_name,
            )
            if latest_scene:
                # Add the scene file to the command
                try:
                    safe_scene_path = self._validate_path_for_shell(str(latest_scene))
                    command = f"{command} -open {safe_scene_path}"
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    self.command_executed.emit(
                        timestamp,
                        f"Opening latest 3DE scene: {latest_scene.name}",
                    )
                except ValueError as e:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    self.command_executed.emit(
                        timestamp,
                        f"Warning: Invalid 3DE scene path: {str(e)}",
                    )
            else:
                timestamp = datetime.now().strftime("%H:%M:%S")
                self.command_executed.emit(
                    timestamp,
                    "Info: No 3DE scene files found in workspace",
                )

        # Handle Maya with latest scene file
        if app_name == "maya" and open_latest_maya:
            latest_scene = self._maya_latest_finder.find_latest_maya_scene(
                self.current_shot.workspace_path,
                self.current_shot.full_name,
            )
            if latest_scene:
                # Add the scene file to the command
                try:
                    safe_scene_path = self._validate_path_for_shell(str(latest_scene))
                    command = f"{command} -file {safe_scene_path}"
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    self.command_executed.emit(
                        timestamp,
                        f"Opening latest Maya scene: {latest_scene.name}",
                    )
                except ValueError as e:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    self.command_executed.emit(
                        timestamp,
                        f"Warning: Invalid Maya scene path: {str(e)}",
                    )
            else:
                timestamp = datetime.now().strftime("%H:%M:%S")
                self.command_executed.emit(
                    timestamp,
                    "Info: No Maya scene files found in workspace",
                )

        # Build full command with ws (workspace setup)
        # Validate and escape workspace path to prevent injection
        try:
            safe_workspace_path = self._validate_path_for_shell(
                self.current_shot.workspace_path
            )

            # Apply Nuke environment fixes if needed
            env_fixes = ""
            if app_name == "nuke":
                env_fixes = self._get_nuke_environment_fixes()
                if env_fixes:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    fix_details: list[str] = []
                    if Config.NUKE_SKIP_PROBLEMATIC_PLUGINS:
                        fix_details.append("runtime NUKE_PATH filtering")
                    if Config.NUKE_OCIO_FALLBACK_CONFIG:
                        fix_details.append("OCIO fallback")
                    fix_details.append("crash reporting disabled")

                    self.command_executed.emit(
                        timestamp,
                        f"Applied environment fixes to prevent Nuke crashes: {', '.join(fix_details)}",
                    )

            # Build base command WITHOUT background operator
            # We'll add & only when actually sending to persistent terminal
            ws_command = f"ws {safe_workspace_path} && {env_fixes}{command}"
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
                self.logger.debug(
                    f"Constructed rez command with bash -ilc: {full_command}"
                )
                timestamp = datetime.now().strftime("%H:%M:%S")
                self.command_executed.emit(
                    timestamp, f"Using rez environment with packages: {packages_str}"
                )
            else:
                full_command = ws_command
        else:
            full_command = ws_command

        # Log the command
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.command_executed.emit(timestamp, full_command)

        # Use persistent terminal if available and enabled
        if (
            self.persistent_terminal
            and Config.PERSISTENT_TERMINAL_ENABLED
            and Config.USE_PERSISTENT_TERMINAL
        ):
            # Add & for GUI apps when using persistent terminal
            command_to_send = full_command
            if Config.AUTO_BACKGROUND_GUI_APPS and self._is_gui_app(app_name):
                # For rez commands, add & inside the quoted bash command
                if "bash -ilc" in full_command:
                    # Command is like: rez env nuke -- bash -ilc "ws /path && nuke"
                    # We need to add & inside the quotes
                    command_to_send = full_command.rstrip('"') + ' &"'
                else:
                    command_to_send = full_command + " &"
                self.logger.debug(
                    f"Added & for GUI app {app_name} in persistent terminal"
                )

            self.logger.info(
                f"Sending command to persistent terminal: {command_to_send}"
            )
            self.logger.debug(
                f"Is GUI app: {self._is_gui_app(app_name)}, Auto-background: {Config.AUTO_BACKGROUND_GUI_APPS}"
            )

            success = self.persistent_terminal.send_command(command_to_send)
            if success:
                self.logger.debug("Command successfully sent to persistent terminal")
                return True
            else:
                self.logger.warning(
                    "Failed to send command to persistent terminal, falling back to new terminal"
                )
                # Emit user-friendly message about fallback
                timestamp = datetime.now().strftime("%H:%M:%S")
                self.command_executed.emit(
                    timestamp,
                    "⚠ Persistent terminal not available, launching in new terminal...",
                )
                # Fall through to launch new terminal - WITHOUT the & operator

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

            # Apply Nuke environment fixes if needed (same as regular launch)
            env_fixes = ""
            if app_name == "nuke":
                env_fixes = self._get_nuke_environment_fixes()
                if env_fixes:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    fix_details: list[str] = []
                    if Config.NUKE_SKIP_PROBLEMATIC_PLUGINS:
                        fix_details.append("runtime NUKE_PATH filtering")
                    if Config.NUKE_OCIO_FALLBACK_CONFIG:
                        fix_details.append("OCIO fallback")
                    fix_details.append("crash reporting disabled")

                    self.command_executed.emit(
                        timestamp,
                        f"Applied environment fixes for Nuke scene launch: {', '.join(fix_details)}",
                    )

            # Build base command WITHOUT background operator
            # We'll add & only when actually sending to persistent terminal
            ws_command = f"ws {safe_workspace_path} && {env_fixes}{command}"
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
                self.logger.debug(
                    f"Constructed rez scene command with bash -ilc: {full_command}"
                )
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
        if (
            self.persistent_terminal
            and Config.PERSISTENT_TERMINAL_ENABLED
            and Config.USE_PERSISTENT_TERMINAL
        ):
            # Add & for GUI apps when using persistent terminal
            command_to_send = full_command
            if Config.AUTO_BACKGROUND_GUI_APPS and self._is_gui_app(app_name):
                # For rez commands, add & inside the quoted bash command
                if "bash -ilc" in full_command:
                    # Command is like: rez env 3de -- bash -ilc "ws /path && 3de /file"
                    # We need to add & inside the quotes
                    command_to_send = full_command.rstrip('"') + ' &"'
                else:
                    command_to_send = full_command + " &"
                self.logger.debug(
                    f"Added & for GUI app {app_name} in persistent terminal"
                )

            self.logger.info(
                f"Sending scene command to persistent terminal: {command_to_send}"
            )
            self.logger.debug(
                f"Is GUI app: {self._is_gui_app(app_name)}, Auto-background: {Config.AUTO_BACKGROUND_GUI_APPS}"
            )

            success = self.persistent_terminal.send_command(command_to_send)
            if success:
                self.logger.debug(
                    "Scene command successfully sent to persistent terminal"
                )
                return True
            else:
                self.logger.warning(
                    "Failed to send command to persistent terminal, falling back to new terminal"
                )
                # Emit user-friendly message about fallback
                timestamp = datetime.now().strftime("%H:%M:%S")
                self.command_executed.emit(
                    timestamp,
                    "⚠ Persistent terminal not available, launching in new terminal...",
                )
                # Fall through to launch new terminal - WITHOUT the & operator

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
                        version = self._raw_plate_finder.get_version_from_path(
                            raw_plate_path
                        )
                        self.command_executed.emit(
                            timestamp,
                            f"Created Nuke script with plate: {version}/{raw_plate_path.split('/')[-1]}",
                        )
                    else:
                        # Fallback to just passing the path (safely escaped)
                        safe_plate_path = self._validate_path_for_shell(raw_plate_path)
                        command = f"{command} {safe_plate_path}"
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        version = self._raw_plate_finder.get_version_from_path(
                            raw_plate_path
                        )
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
                version = self._undistortion_finder.get_version_from_path(
                    undistortion_path
                )
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

    def _is_gui_app(self, app_name: str) -> bool:
        """Check if an application is a GUI application.

        Args:
            app_name: Name of the application

        Returns:
            True if the app is a GUI application, False otherwise
        """
        # List of known GUI applications that should run in background
        gui_apps = {
            "3de",
            "nuke",
            "maya",
            "rv",
            "houdini",
            "mari",
            "katana",
            "clarisse",
        }
        return app_name.lower() in gui_apps

    def _emit_error(self, error: str) -> None:
        """Emit error with timestamp."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.command_error.emit(timestamp, error)
