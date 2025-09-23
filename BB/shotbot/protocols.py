"""Protocol definitions for ShotBot application.

This module defines Protocol classes for better type safety and
interface design throughout the application.
"""

from __future__ import annotations

# Import RefreshResult from type_definitions where it's properly defined as NamedTuple
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pathlib import Path

    from type_definitions import RefreshResult


@runtime_checkable
class SceneDataProtocol(Protocol):
    """Common interface for Shot and ThreeDEScene data objects.

    This protocol defines the shared interface between Shot and ThreeDEScene,
    allowing ItemModels to work with either type through a common interface.
    """

    show: str
    sequence: str
    shot: str
    workspace_path: str

    @property
    def full_name(self) -> str:
        """Get full name of the scene/shot."""
        ...

    def get_thumbnail_path(self) -> Path | None:
        """Get path to thumbnail image."""
        ...


@runtime_checkable
class CacheableProtocol(Protocol):
    """Protocol for objects that can be cached."""

    def to_dict(self) -> dict[str, object]:
        """Convert object to dictionary for caching."""
        ...

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> CacheableProtocol:
        """Create object from cached dictionary."""
        ...


@runtime_checkable
class RefreshableProtocol(Protocol):
    """Protocol for objects that support data refreshing."""

    def refresh_data(self) -> RefreshResult:
        """Refresh data from source."""
        ...

    def is_stale(self) -> bool:
        """Check if data needs refreshing."""
        ...


@runtime_checkable
class ThumbnailProviderProtocol(Protocol):
    """Protocol for objects that can provide thumbnail paths."""

    def get_thumbnail_path(self) -> Path | None:
        """Get thumbnail path for the object."""
        ...

    @property
    def thumbnail_dir(self) -> Path:
        """Get thumbnail directory path."""
        ...


@runtime_checkable
class LaunchableProtocol(Protocol):
    """Protocol for objects that can be launched."""

    def launch(self, **kwargs) -> bool:
        """Launch the object."""
        ...

    @property
    def is_available(self) -> bool:
        """Check if the object can be launched."""
        ...


@runtime_checkable
class ValidatableProtocol(Protocol):
    """Protocol for objects that can be validated."""

    def validate(self) -> list[str]:
        """Validate object and return list of errors."""
        ...

    @property
    def is_valid(self) -> bool:
        """Check if object is currently valid."""
        ...


@runtime_checkable
class DataModelProtocol(Protocol):
    """Protocol for data model classes."""

    def get_data(self) -> list[dict[str, object]]:
        """Get all data items."""
        ...

    def refresh_data(self) -> RefreshResult:
        """Refresh data from source."""
        ...

    def find_item_by_name(self, name: str) -> dict[str, object] | None:
        """Find item by name."""
        ...


@runtime_checkable
class WorkerProtocol(Protocol):
    """Protocol for background worker threads."""

    def start_work(self) -> None:
        """Start the worker."""
        ...

    def stop_work(self) -> None:
        """Stop the worker."""
        ...

    @property
    def is_running(self) -> bool:
        """Check if worker is currently running."""
        ...
