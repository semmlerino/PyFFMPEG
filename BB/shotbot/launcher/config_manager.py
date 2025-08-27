"""Configuration management for launcher system.

This module handles persistence of launcher configurations to disk,
extracted from the original launcher_manager.py for better separation of concerns.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Optional, Union

from launcher.models import CustomLauncher, LauncherEnvironment, LauncherTerminal, LauncherValidation

# Set up logger for this module
logger = logging.getLogger(__name__)


class LauncherConfigManager:
    """Manages persistence of custom launcher configurations."""

    def __init__(self, config_dir: Optional[Union[str, Path]] = None):
        if config_dir is not None:
            self.config_dir = Path(config_dir)
        else:
            self.config_dir = Path.home() / ".shotbot"
        self.config_file = self.config_dir / "custom_launchers.json"
        self._ensure_config_dir()

    def _ensure_config_dir(self) -> None:
        """Ensure configuration directory exists."""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error(f"Failed to create config directory {self.config_dir}: {e}")
            raise

    def load_launchers(self) -> Dict[str, CustomLauncher]:
        """Load launchers from configuration file."""
        if not self.config_file.exists():
            logger.debug(f"Config file {self.config_file} does not exist")
            return {}

        try:
            with open(self.config_file, "r") as f:
                data = json.load(f)

            launchers = {}
            for launcher_id, launcher_data in data.get("launchers", {}).items():
                launcher_data["id"] = launcher_id
                launchers[launcher_id] = CustomLauncher.from_dict(launcher_data)

            logger.info(f"Loaded {len(launchers)} launchers from config")
            return launchers

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.error(f"Failed to load launcher config: {e}")
            return {}

    def save_launchers(self, launchers: Dict[str, CustomLauncher]) -> bool:
        """Save launchers to configuration file."""
        try:
            config_data = {
                "version": "1.0",
                "launchers": {},
                "terminal_preferences": ["gnome-terminal", "konsole", "xterm"],
            }

            for launcher_id, launcher in launchers.items():
                launcher_dict = launcher.to_dict()
                # Remove ID from nested dict as it's the key
                launcher_dict.pop("id", None)
                config_data["launchers"][launcher_id] = launcher_dict

            with open(self.config_file, "w") as f:
                json.dump(config_data, f, indent=2)

            logger.info(f"Saved {len(launchers)} launchers to config")
            return True

        except (OSError, TypeError, ValueError) as e:
            logger.error(f"Failed to save launcher config: {e}")
            return False