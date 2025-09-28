"""Unified Nuke launching handler using existing specialized modules."""

from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import TYPE_CHECKING

from config import Config
from logging_mixin import LoggingMixin
from nuke_script_generator import NukeScriptGenerator
from nuke_workspace_manager import NukeWorkspaceManager
from raw_plate_finder import RawPlateFinder
from undistortion_finder import UndistortionFinder

if TYPE_CHECKING:
    from shot_model import Shot


class NukeLaunchHandler(LoggingMixin):
    """Handles all Nuke-specific launching logic.

    This class consolidates Nuke launching functionality that was previously
    duplicated across CommandLauncher and SimplifiedLauncher.
    """

    def __init__(self) -> None:
        """Initialize with all required Nuke modules."""
        super().__init__()
        self.workspace_manager = NukeWorkspaceManager()

        # These are stored as classes since they use static methods
        self.script_generator = NukeScriptGenerator
        self.raw_plate_finder = RawPlateFinder
        self.undistortion_finder = UndistortionFinder

    def prepare_nuke_command(
        self,
        shot: Shot,
        base_command: str,
        options: dict[str, bool]
    ) -> tuple[str, list[str]]:
        """
        Prepare Nuke command with all options.

        Args:
            shot: Current shot context
            base_command: Base Nuke command
            options: Dictionary of launch options:
                - open_latest_scene: Open latest existing script
                - create_new_file: Create new script version
                - include_raw_plate: Include raw plate in script
                - include_undistortion: Include undistortion in script

        Returns:
            Tuple of (command, log_messages)
        """
        log_messages: list[str] = []
        command = base_command

        # Handle mutually exclusive paths
        if options.get("open_latest_scene") or options.get("create_new_file"):
            command, msgs = self._handle_workspace_scripts(
                shot, command, options
            )
            log_messages.extend(msgs)
        elif options.get("include_raw_plate") or options.get("include_undistortion"):
            command, msgs = self._handle_media_loading(
                shot, command, options
            )
            log_messages.extend(msgs)

        # Apply environment fixes
        if Config.NUKE_FIX_OCIO_CRASH:
            log_messages.append("Applying Nuke environment fixes to prevent OCIO plugin crashes...")

        return command, log_messages

    def _handle_workspace_scripts(
        self,
        shot: Shot,
        command: str,
        options: dict[str, bool]
    ) -> tuple[str, list[str]]:
        """Handle workspace script creation/opening.

        Args:
            shot: Current shot context
            command: Current command string
            options: Launch options

        Returns:
            Tuple of (updated_command, log_messages)
        """
        log_messages: list[str] = []

        # Note: open_latest_scene takes priority
        if options.get("open_latest_scene") and options.get("create_new_file"):
            options["create_new_file"] = False

        if options.get("open_latest_scene"):
            # Try to find existing script
            script_dir = self.workspace_manager.get_workspace_script_directory(
                shot.workspace_path
            )
            latest_script = self.workspace_manager.find_latest_nuke_script(
                script_dir, shot.full_name
            )

            if latest_script:
                # Open existing script
                safe_script_path = shlex.quote(str(latest_script))
                command = f"{command} {safe_script_path}"
                log_messages.append(f"Opening existing Nuke script: {latest_script.name}")
            else:
                # No existing script, create v001
                log_messages.append("No existing Nuke scripts found, creating v001...")
                saved_path = self._create_new_workspace_script(
                    shot, version=1, options=options
                )
                if saved_path:
                    command = f"{command} {shlex.quote(saved_path)}"
                    log_messages.append(f"Created new Nuke script: {Path(saved_path).name}")
                else:
                    log_messages.append("Failed to create Nuke script")
                    return command, log_messages

        elif options.get("create_new_file"):
            # Always create new version
            script_dir = self.workspace_manager.get_workspace_script_directory(
                shot.workspace_path
            )
            _, version = self.workspace_manager.get_next_script_path(
                script_dir, shot.full_name
            )

            log_messages.append(f"Creating new Nuke script version: v{version:03d}")

            saved_path = self._create_new_workspace_script(
                shot, version=version, options=options
            )
            if saved_path:
                command = f"{command} {shlex.quote(saved_path)}"
                log_messages.append(f"Created and opening new Nuke script: v{version:03d}")
            else:
                log_messages.append("Failed to create Nuke script")

        return command, log_messages

    def _create_new_workspace_script(
        self,
        shot: Shot,
        version: int,
        options: dict[str, bool]
    ) -> str | None:
        """Create a new workspace script with optional plate.

        Args:
            shot: Current shot context
            version: Version number for the script
            options: Launch options

        Returns:
            Path to created script or None if failed
        """
        if options.get("include_raw_plate"):
            raw_plate_path = self.raw_plate_finder.find_latest_raw_plate(
                shot.workspace_path, shot.full_name
            )
            if raw_plate_path and self.raw_plate_finder.verify_plate_exists(raw_plate_path):
                return self.script_generator.create_workspace_plate_script(
                    raw_plate_path,
                    shot.workspace_path,
                    shot.full_name,
                    version=version
                )

        # Create empty script
        script_path = self.script_generator.create_plate_script(
            "", shot.full_name
        )
        if script_path:
            with open(script_path, encoding="utf-8") as f:
                content = f.read()
            return self.script_generator.save_workspace_script(
                content,
                shot.workspace_path,
                shot.full_name,
                version=version
            )

        return None

    def _handle_media_loading(
        self,
        shot: Shot,
        command: str,
        options: dict[str, bool]
    ) -> tuple[str, list[str]]:
        """Handle raw plate and undistortion loading.

        Args:
            shot: Current shot context
            command: Current command string
            options: Launch options

        Returns:
            Tuple of (updated_command, log_messages)
        """
        log_messages: list[str] = []
        raw_plate_path = None
        undistortion_path = None

        # Get raw plate if requested
        if options.get("include_raw_plate"):
            raw_plate_path = self.raw_plate_finder.find_latest_raw_plate(
                shot.workspace_path,
                shot.full_name,
            )
            # Verify plate exists
            if raw_plate_path and not self.raw_plate_finder.verify_plate_exists(
                raw_plate_path,
            ):
                raw_plate_path = None

        # Get undistortion if requested
        if options.get("include_undistortion"):
            undistortion_path = self.undistortion_finder.find_latest_undistortion(
                shot.workspace_path,
                shot.full_name,
            )

        # Handle different scenarios based on what we have
        if raw_plate_path or undistortion_path:
            if (
                Config.NUKE_UNDISTORTION_MODE == "direct"
                and undistortion_path
                and not raw_plate_path
            ):
                # Direct mode: Open undistortion file directly (no plate)
                safe_undist_path = shlex.quote(str(undistortion_path))
                command = f"{command} {safe_undist_path}"
                version = self.undistortion_finder.get_version_from_path(
                    undistortion_path
                )
                log_messages.append(f"Opening undistortion file directly: {version}")
            elif (
                raw_plate_path
                and undistortion_path
                and Config.NUKE_USE_LOADER_SCRIPT
            ):
                # Both plate and undistortion - create loader script
                script_path = self.script_generator.create_loader_script(
                    raw_plate_path,
                    str(undistortion_path),
                    shot.full_name,
                )
                if script_path:
                    safe_script_path = shlex.quote(script_path)
                    command = f"{command} {safe_script_path}"
                    plate_version = self.raw_plate_finder.get_version_from_path(
                        raw_plate_path
                    )
                    undist_version = self.undistortion_finder.get_version_from_path(
                        undistortion_path
                    )
                    log_messages.append(
                        f"Created loader script with plate ({plate_version}) and undistortion ({undist_version})"
                    )
                else:
                    # Fallback to old parsing method if loader script fails
                    script_path = self.script_generator.create_plate_script_with_undistortion(
                        raw_plate_path,
                        str(undistortion_path),
                        shot.full_name,
                    )
                    if script_path:
                        safe_script_path = shlex.quote(script_path)
                        command = f"{command} {safe_script_path}"
                        log_messages.append("Warning: Using fallback parsing method for undistortion")
                    else:
                        log_messages.append("Error: Failed to generate Nuke script")
            elif raw_plate_path:
                # Plate only
                script_path = self.script_generator.create_plate_script(
                    raw_plate_path,
                    shot.full_name,
                )
                if script_path:
                    safe_script_path = shlex.quote(script_path)
                    command = f"{command} {safe_script_path}"
                    version = self.raw_plate_finder.get_version_from_path(raw_plate_path)
                    log_messages.append(f"Generated Nuke script with plate: {version}")
                else:
                    log_messages.append("Error: Failed to generate plate script")
            elif undistortion_path and Config.NUKE_UNDISTORTION_MODE != "direct":
                # Undistortion only with parse mode (backward compatibility)
                script_path = self.script_generator.create_plate_script_with_undistortion(
                    "",
                    str(undistortion_path),
                    shot.full_name,
                )
                if script_path:
                    safe_script_path = shlex.quote(script_path)
                    command = f"{command} {safe_script_path}"
                    version = self.undistortion_finder.get_version_from_path(
                        undistortion_path
                    )
                    log_messages.append(
                        f"Generated Nuke script with undistortion (parse mode): {version}"
                    )
                else:
                    log_messages.append("Error: Failed to generate undistortion script")
        else:
            # Log warnings for missing files
            if options.get("include_raw_plate"):
                log_messages.append(
                    "Warning: Raw plate not found or no frames exist for this shot"
                )
            if options.get("include_undistortion"):
                log_messages.append("Warning: Undistortion file not found for this shot")

        return command, log_messages

    def get_environment_fixes(self) -> str:
        """Get Nuke-specific environment fixes.

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
            grep_patterns: list[str] = []
            for problematic_path in Config.NUKE_PROBLEMATIC_PLUGIN_PATHS:
                # Escape special characters for grep
                escaped_path = problematic_path.replace(".", r"\.")
                grep_patterns.append(f'-e "{escaped_path}"')

            grep_pattern_str = " ".join(grep_patterns)

            # Create a bash command that filters NUKE_PATH at runtime
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