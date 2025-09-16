"""Type stubs for utils module."""

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

# Cache globals
_path_cache: dict[str, tuple[bool, float]]
_PATH_CACHE_TTL: float
_cache_disabled: bool

def clear_all_caches() -> None: ...
def get_cache_stats() -> dict[str, Any]: ...
def disable_caching() -> None: ...
def enable_caching() -> None: ...

class CacheIsolation:
    """Context manager for cache isolation in tests."""

    def __init__(self) -> None: ...
    def __enter__(self) -> CacheIsolation: ...
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None: ...

class PathUtils:
    """Utilities for path construction and validation."""

    @staticmethod
    def build_path(base_path: str | Path, *segments: str) -> Path: ...
    @staticmethod
    def build_thumbnail_path(
        shows_root: str,
        show: str,
        sequence: str,
        shot: str,
    ) -> Path: ...
    @staticmethod
    def find_turnover_plate_thumbnail(
        shows_root: str,
        show: str,
        sequence: str,
        shot: str,
    ) -> Path | None: ...
    @staticmethod
    def find_any_publish_thumbnail(
        shows_root: str,
        show: str,
        sequence: str,
        shot: str,
        max_depth: int = 5,
    ) -> Path | None: ...
    @staticmethod
    def build_raw_plate_path(workspace_path: str) -> Path: ...
    @staticmethod
    def build_undistortion_path(workspace_path: str, username: str) -> Path: ...
    @staticmethod
    def build_threede_scene_path(workspace_path: str, username: str) -> Path: ...
    @staticmethod
    def validate_path_exists(
        path: str | Path,
        description: str = ...,
    ) -> bool: ...
    @staticmethod
    def _cleanup_path_cache() -> None: ...
    @staticmethod
    def batch_validate_paths(paths: list[str | Path]) -> dict[str, bool]: ...
    @staticmethod
    def safe_mkdir(path: str | Path, description: str = ...) -> bool: ...
    @staticmethod
    def discover_plate_directories(
        base_path: str | Path,
    ) -> list[tuple[str, int]]: ...

class VersionUtils:
    """Utilities for handling versioned directories and files."""

    VERSION_PATTERN: re.Pattern[str]
    _version_cache: dict[str, tuple[list[tuple[int, str]], float]]

    @staticmethod
    def find_version_directories(
        base_path: str | Path,
    ) -> list[tuple[int, str]]: ...
    @staticmethod
    def _cleanup_version_cache() -> None: ...
    @staticmethod
    def get_latest_version(base_path: str | Path) -> str | None: ...
    @staticmethod
    @lru_cache(maxsize=256)
    def extract_version_from_path(path: str | Path) -> str | None: ...
    @staticmethod
    def get_next_version_number(directory: str | Path, pattern: str) -> int: ...

class FileUtils:
    """Utilities for file operations and validation."""

    @staticmethod
    def find_files_by_extension(
        directory: str | Path,
        extensions: str | list[str],
        limit: int | None = ...,
    ) -> list[Path]: ...
    @staticmethod
    def get_first_image_file(directory: str | Path) -> Path | None: ...
    @staticmethod
    def validate_file_size(
        file_path: str | Path,
        max_size_mb: int | None = ...,
    ) -> bool: ...

class ImageUtils:
    """Utilities for image validation and processing."""

    @staticmethod
    def validate_image_dimensions(
        width: int,
        height: int,
        max_dimension: int | None = ...,
        max_memory_mb: int | None = ...,
    ) -> bool: ...
    @staticmethod
    def get_safe_dimensions_for_thumbnail(
        max_size: int | None = ...,
    ) -> tuple[int, int]: ...

class ValidationUtils:
    """Common validation utilities."""

    @staticmethod
    def validate_not_empty(
        *values: str | None,
        names: list[str] | None = ...,
    ) -> bool: ...
    @staticmethod
    def validate_shot_components(show: str, sequence: str, shot: str) -> bool: ...
    @staticmethod
    def get_current_username() -> str: ...
    @staticmethod
    def get_excluded_users(additional_users: set[str] | None = ...) -> set[str]: ...
