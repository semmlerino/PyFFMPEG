"""Validation logic for launcher system.

This module handles all validation of launcher configurations and commands,
extracted from the original launcher_manager.py for better separation of concerns.
"""

from __future__ import annotations

import logging
import re
import shlex
import string
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from launcher.models import CustomLauncher, LauncherEnvironment, LauncherValidation

# Set up logger for this module
logger = logging.getLogger(__name__)


class LauncherValidator:
    """Validates launcher configurations and commands."""

    def __init__(self):
        """Initialize the validator with security patterns."""
        # Define valid placeholder variables
        self.valid_variables = {
            # Shot context variables
            "show",
            "sequence",
            "shot",
            "full_name",
            "workspace_path",
            # Environment variables
            "HOME",
            "USER",
            "SHOTBOT_VERSION",
        }
        
        # Security patterns that should be forbidden
        self.security_patterns = [
            "rm -rf",
            "sudo rm",
            "rm /",
            "format c:",
            "del /s",
            "> /dev/sda",
            "dd if=",
            "mkfs.",
            "fdisk",
        ]

    def validate_launcher_data(
        self,
        name: str,
        command: str,
        existing_launchers: Dict[str, CustomLauncher],
        exclude_id: Optional[str] = None,
    ) -> List[str]:
        """Validate launcher data and return list of errors.
        
        Args:
            name: Launcher name
            command: Launcher command
            existing_launchers: Dictionary of existing launchers for uniqueness check
            exclude_id: ID to exclude from uniqueness check (for updates)
            
        Returns:
            List of validation error messages
        """
        errors = []

        # Validate name
        if not name or not name.strip():
            errors.append("Name cannot be empty")
        elif len(name.strip()) > 100:
            errors.append("Name cannot exceed 100 characters")
        else:
            # Check name uniqueness
            for launcher_id, launcher in existing_launchers.items():
                if launcher_id != exclude_id and launcher.name == name.strip():
                    errors.append(f"Name '{name.strip()}' already exists")
                    break

        # Validate command
        if not command or not command.strip():
            errors.append("Command cannot be empty")
        else:
            # Check for security patterns
            security_errors = self._validate_security(command)
            errors.extend(security_errors)

        return errors

    def _validate_security(self, command: str) -> List[str]:
        """Check command for security risks.
        
        Args:
            command: Command string to check
            
        Returns:
            List of security-related error messages
        """
        errors = []
        cmd_lower = command.lower()
        
        for pattern in self.security_patterns:
            if pattern in cmd_lower:
                errors.append(
                    f"Command contains potentially dangerous pattern: {pattern}",
                )
                break
                
        return errors

    def validate_command_syntax(self, command: str) -> Tuple[bool, Optional[str]]:
        """Validate command syntax for variable substitutions.

        Args:
            command: Command string to validate

        Returns:
            Tuple of (is_valid, error_message). If valid, error_message is None.
        """
        if not command:
            return False, "Command cannot be empty"

        try:
            # Use string.Template to validate syntax
            template = string.Template(command)

            # Extract all placeholders from the command
            placeholders = set()

            # Find all $identifier and ${identifier} patterns
            for match in re.finditer(r"\$(?:(\w+)|\{(\w+)\})", command):
                placeholder = match.group(1) or match.group(2)
                if placeholder:
                    placeholders.add(placeholder)

            # Check for invalid variable names
            invalid_vars = placeholders - self.valid_variables
            if invalid_vars:
                invalid_list = ", ".join(sorted(invalid_vars))
                valid_list = ", ".join(sorted(self.valid_variables))
                return (
                    False,
                    f"Invalid variables: {invalid_list}. Valid variables are: {valid_list}",
                )

            # Try to perform a safe substitution to catch syntax errors
            # Use empty context to catch any malformed patterns
            try:
                template.safe_substitute({})
            except ValueError as e:
                return False, f"Invalid template syntax: {e}"

            return True, None

        except Exception as e:
            return False, f"Command validation failed: {e}"

    def validate_launcher_paths(
        self,
        launcher: CustomLauncher,
        shot_context: Optional[Dict[str, str]] = None,
    ) -> Tuple[bool, List[str]]:
        """Validate that required paths exist for the launcher.

        Args:
            launcher: The launcher to validate
            shot_context: Optional shot context for path substitution

        Returns:
            Tuple of (all_valid, list_of_missing_paths)
        """
        missing_paths = []

        # Check required files from validation settings
        if launcher.validation.required_files:
            for file_pattern in launcher.validation.required_files:
                # Substitute variables if shot context provided
                if shot_context:
                    try:
                        template = string.Template(file_pattern)
                        file_path = template.safe_substitute(**shot_context)
                    except (KeyError, ValueError):
                        file_path = file_pattern
                else:
                    file_path = file_pattern

                # Check if path exists
                path = Path(file_path).expanduser()
                if not path.exists():
                    missing_paths.append(str(path))

        # Check source files from environment settings
        if launcher.environment.source_files:
            for source_file in launcher.environment.source_files:
                # Substitute variables if shot context provided
                if shot_context:
                    try:
                        template = string.Template(source_file)
                        file_path = template.safe_substitute(**shot_context)
                    except (KeyError, ValueError):
                        file_path = source_file
                else:
                    file_path = source_file

                # Check if path exists
                path = Path(file_path).expanduser()
                if not path.exists():
                    missing_paths.append(str(path))

        return len(missing_paths) == 0, missing_paths

    def validate_environment(self, env: LauncherEnvironment) -> Tuple[bool, str]:
        """Validate environment configuration.
        
        Args:
            env: LauncherEnvironment to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        valid_env_types = ["bash", "rez", "conda"]
        
        if env.type not in valid_env_types:
            return False, f"Invalid environment type: {env.type}. Must be one of: {', '.join(valid_env_types)}"
        
        # Check for rez if specified
        if env.type == "rez" and env.packages:
            try:
                result = subprocess.run(
                    ["which", "rez"],
                    capture_output=True,
                    text=True,
                    timeout=1,
                )
                if result.returncode != 0:
                    return False, "Rez environment specified but rez command not found"
            except Exception:
                return False, "Could not verify rez installation"
        
        # Check for conda if specified
        if env.type == "conda":
            try:
                result = subprocess.run(
                    ["which", "conda"],
                    capture_output=True,
                    text=True,
                    timeout=1,
                )
                if result.returncode != 0:
                    return False, "Conda environment specified but conda command not found"
            except Exception:
                return False, "Could not verify conda installation"
        
        return True, ""

    def validate_launcher_config(
        self,
        launcher: CustomLauncher,
        existing_launchers: Optional[Dict[str, CustomLauncher]] = None,
    ) -> Tuple[bool, List[str]]:
        """Comprehensive validation of a launcher configuration.
        
        Args:
            launcher: The launcher to validate
            existing_launchers: Optional dictionary of existing launchers
            
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        # Validate basic data
        if existing_launchers:
            data_errors = self.validate_launcher_data(
                launcher.name,
                launcher.command,
                existing_launchers,
                exclude_id=launcher.id,
            )
            errors.extend(data_errors)
        
        # Validate command syntax
        valid, error = self.validate_command_syntax(launcher.command)
        if not valid and error:
            errors.append(error)
        
        # Validate environment
        valid, error = self.validate_environment(launcher.environment)
        if not valid and error:
            errors.append(error)
        
        # Check forbidden patterns in validation config
        if launcher.validation.forbidden_patterns:
            cmd_lower = launcher.command.lower()
            for pattern in launcher.validation.forbidden_patterns:
                try:
                    if re.search(pattern, cmd_lower):
                        errors.append(f"Command matches forbidden pattern: {pattern}")
                        break
                except re.error:
                    # Invalid regex pattern
                    logger.warning(f"Invalid regex pattern in forbidden_patterns: {pattern}")
        
        return len(errors) == 0, errors

    def validate_process_startup(self, process: subprocess.Popen[Any]) -> bool:
        """Validate that a process has started successfully.
        
        Args:
            process: The subprocess to validate
            
        Returns:
            True if process is running, False if it has already terminated
        """
        try:
            # Check if process has already terminated
            return_code = process.poll()
            if return_code is not None:
                # Process has already exited
                logger.warning(f"Process {process.pid} terminated with code {return_code}")
                return False
            return True
        except Exception as e:
            logger.error(f"Failed to validate process startup: {e}")
            return False