"""Protocol definitions for ShotBot application.

This module defines Protocol classes for better type safety and
interface design throughout the application.
"""

from __future__ import annotations

# Standard library imports
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    # Standard library imports
    from pathlib import Path


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
