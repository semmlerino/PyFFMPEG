"""Data models for launcher system.

This module contains all the data structures used by the launcher system,
extracted from the original launcher_manager.py to improve separation of concerns.
"""

from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class LauncherValidation:
    """Validation settings for a launcher."""

    check_executable: bool = True
    required_files: list[str] = field(default_factory=list)
    forbidden_patterns: list[str] = field(
        default_factory=lambda: [
            r";\s*rm\s",
            r";\s*sudo\s",
            r";\s*su\s",
            r"&&\s*rm\s",
            r"\|\s*rm\s",
            r"`rm\s",
            r"\$\(rm\s",
        ],
    )
    working_directory: str | None = None
    resolve_paths: bool = False


@dataclass
class LauncherTerminal:
    """Terminal settings for a launcher."""

    required: bool = False
    persist: bool = False
    title: str | None = None


@dataclass
class LauncherEnvironment:
    """Environment settings for a launcher."""

    type: str = "bash"  # "bash", "rez", "conda"
    packages: list[str] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)
    command_prefix: str | None = None


@dataclass
class CustomLauncher:
    """Represents a custom application launcher."""

    id: str
    name: str
    description: str
    command: str
    category: str = "custom"
    variables: dict[str, str] = field(default_factory=dict)
    environment: LauncherEnvironment = field(default_factory=LauncherEnvironment)
    terminal: LauncherTerminal = field(default_factory=LauncherTerminal)
    validation: LauncherValidation = field(default_factory=LauncherValidation)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert launcher to dictionary for serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CustomLauncher":
        """Create launcher from dictionary data."""
        # Handle nested objects
        if "environment" in data and isinstance(data["environment"], dict):
            data["environment"] = LauncherEnvironment(**data["environment"])
        if "terminal" in data and isinstance(data["terminal"], dict):
            data["terminal"] = LauncherTerminal(**data["terminal"])
        if "validation" in data and isinstance(data["validation"], dict):
            data["validation"] = LauncherValidation(**data["validation"])

        return cls(**data)


class ProcessInfo:
    """Information about an active process."""

    def __init__(
        self,
        process: subprocess.Popen[Any],
        launcher_id: str,
        launcher_name: str,
        command: str,
        timestamp: float,
    ):
        self.process = process
        self.launcher_id = launcher_id
        self.launcher_name = launcher_name
        self.command = command
        self.timestamp = timestamp
        self.validated = False  # Whether process startup was validated
