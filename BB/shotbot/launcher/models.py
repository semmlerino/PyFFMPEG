"""Data models for launcher system.

This module contains all the data structures used by the launcher system,
including parameter validation and command building capabilities.
"""

from __future__ import annotations

# Standard library imports
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Standard library imports
    import subprocess


class ParameterType(Enum):
    """Parameter types for launcher configuration."""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    PATH = "path"
    CHOICE = "choice"
    FILE = "file"
    DIRECTORY = "directory"


@dataclass
class LauncherParameter:
    """Represents a configurable parameter for a launcher."""

    name: str
    param_type: ParameterType
    label: str
    description: str = ""
    default_value: str | int | float | bool | None = None
    required: bool = False
    choices: list[str] = field(default_factory=list)
    min_value: int | float | None = None
    max_value: int | float | None = None
    file_filter: str = ""  # For file/directory parameters
    placeholder: str = ""

    def __post_init__(self) -> None:
        """Validate parameter configuration."""
        if not self.name:
            raise ValueError("Parameter name cannot be empty")

        if not self.name.isidentifier():
            raise ValueError(
                f"Parameter name '{self.name}' must be a valid Python identifier"
            )

        if not self.label:
            raise ValueError("Parameter label cannot be empty")

        # Validate choices for CHOICE type
        if self.param_type == ParameterType.CHOICE:
            if not self.choices:
                raise ValueError("CHOICE parameter must have at least one choice")
            if self.default_value and self.default_value not in self.choices:
                raise ValueError(f"Default value '{self.default_value}' not in choices")

        # Validate numeric ranges
        if self.param_type in (ParameterType.INTEGER, ParameterType.FLOAT):
            if self.min_value is not None and self.max_value is not None:
                if isinstance(self.min_value, int | float) and isinstance(
                    self.max_value, int | float
                ):
                    if self.min_value > self.max_value:
                        raise ValueError("min_value cannot be greater than max_value")

            if self.default_value is not None:
                if (
                    self.min_value is not None
                    and isinstance(self.default_value, int | float)
                    and isinstance(self.min_value, int | float)
                ):
                    if self.default_value < self.min_value:
                        raise ValueError("Default value is below minimum")
                if (
                    self.max_value is not None
                    and isinstance(self.default_value, int | float)
                    and isinstance(self.max_value, int | float)
                ):
                    if self.default_value > self.max_value:
                        raise ValueError("Default value is above maximum")

    def validate_value(self, value: Any) -> bool:
        """Validate a value against this parameter's constraints.

        Args:
            value: Value to validate

        Returns:
            True if value is valid, False otherwise
        """
        if value is None:
            return not self.required

        try:
            if self.param_type == ParameterType.STRING:
                return isinstance(value, str)

            elif self.param_type == ParameterType.INTEGER:
                if not isinstance(value, int):
                    return False
                if self.min_value is not None and value < self.min_value:
                    return False
                if self.max_value is not None and value > self.max_value:
                    return False
                return True

            elif self.param_type == ParameterType.FLOAT:
                if not isinstance(value, int | float):
                    return False
                if self.min_value is not None and value < self.min_value:
                    return False
                if self.max_value is not None and value > self.max_value:
                    return False
                return True

            elif self.param_type == ParameterType.BOOLEAN:
                return isinstance(value, bool)

            elif self.param_type == ParameterType.PATH:
                if not isinstance(value, str):
                    return False
                return True

            elif self.param_type == ParameterType.CHOICE:
                return value in self.choices

            elif self.param_type in (ParameterType.FILE, ParameterType.DIRECTORY):
                if not isinstance(value, str):
                    return False
                return True

            return False

        except Exception:
            return False

    def to_dict(self) -> dict[str, Any]:
        """Convert parameter to dictionary for serialization."""
        data = asdict(self)
        # Convert enum to string
        data["param_type"] = self.param_type.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LauncherParameter:
        """Create parameter from dictionary.

        Args:
            data: Dictionary containing parameter data

        Returns:
            LauncherParameter instance

        Raises:
            ValueError: If data is invalid
        """
        try:
            # Convert param_type string back to enum
            if "param_type" in data:
                data["param_type"] = ParameterType(data["param_type"])

            return cls(**data)

        except (TypeError, ValueError) as e:
            raise ValueError(f"Invalid parameter data: {e}")


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
    def from_dict(cls, data: dict[str, Any]) -> CustomLauncher:
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
    ) -> None:
        self.process = process
        self.launcher_id = launcher_id
        self.launcher_name = launcher_name
        self.command = command
        self.timestamp = timestamp
        self.validated = False  # Whether process startup was validated
