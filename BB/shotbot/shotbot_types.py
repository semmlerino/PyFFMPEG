"""Type definitions for ShotBot application.

This module provides additional type definitions that extend those in
type_definitions.py. Duplicate definitions have been removed and imported
from the primary type_definitions module.
"""

from __future__ import annotations

from typing import Any, TypedDict

# Import common types from primary definitions to avoid duplication

# ==============================================================================
# Additional TypedDict Definitions
# ==============================================================================


class ThreeDESceneData(TypedDict):
    """Type definition for 3DE scene data dictionary.
    
    Note: This differs from ThreeDESceneDict in type_definitions.py
    by having different fields (plate, scene_path instead of filepath, etc.)
    """

    show: str
    sequence: str
    shot: str
    workspace_path: str
    user: str
    plate: str
    scene_path: str


class CacheEntry(TypedDict):
    """Type definition for cache entry data."""

    value: Any
    timestamp: float
    access_count: int
    size_bytes: int | None


# RefreshResult is defined as NamedTuple in shot_model.py
# Removed duplicate TypedDict definition to avoid import conflicts