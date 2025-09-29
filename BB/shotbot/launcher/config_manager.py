"""Configuration management for launcher system.

This module handles persistence of launcher configurations to disk,
extracted from the original launcher_manager.py for better separation of concerns.
"""

from __future__ import annotations

# Standard library imports
import json
from pathlib import Path
from typing import Any

# Local application imports
from launcher.models import CustomLauncher
from logging_mixin import LoggingMixin


class LauncherConfigManager(LoggingMixin):
    """Manages persistence of custom launcher configurations."""

    def __init__(self, config_dir: str | Path | None = None) -> None:
        super().__init__()
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
            self.logger.error(f"Failed to create config directory {self.config_dir}: {e}")
            raise

    def load_launchers(self) -> dict[str, CustomLauncher]:
        """Load launchers from configuration file."""
        if not self.config_file.exists():
            self.logger.debug(f"Config file {self.config_file} does not exist")
            return {}

        try:
            with open(self.config_file) as f:
                data: dict[str, Any] = json.load(f)

            launchers: dict[str, Any] = {}
            for launcher_id, launcher_data in data.get("launchers", {}).items():
                launcher_data["id"] = launcher_id
                launchers[launcher_id] = CustomLauncher.from_dict(launcher_data)

            self.logger.info(f"Loaded {len(launchers)} launchers from config")
            return launchers

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            self.logger.error(f"Failed to load launcher config: {e}")
            return {}

    def save_launchers(self, launchers: dict[str, CustomLauncher]) -> bool:
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

            self.logger.info(f"Saved {len(launchers)} launchers to config")
            return True

        except (OSError, TypeError, ValueError) as e:
            self.logger.error(f"Failed to save launcher config: {e}")
            return False
