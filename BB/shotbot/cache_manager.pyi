"""Type stubs for cache_manager module."""

import threading
from pathlib import Path
from typing import Any, Sequence

from PySide6.QtCore import QObject, QRunnable, Signal

from shot_model import Shot

class CacheManager(QObject):
    """Manages caching of shot data and thumbnails with thread safety and memory monitoring."""

    # Signals
    cache_updated: Signal

    # Thread safety
    _lock: threading.RLock

    # Memory tracking
    _memory_usage_bytes: int
    _max_memory_bytes: int

    # Cache directories
    cache_dir: Path
    thumbnails_dir: Path
    shots_cache_file: Path
    threede_scenes_cache_file: Path

    # Track cached thumbnails
    _cached_thumbnails: dict[str, int]

    # Properties
    @property
    def CACHE_THUMBNAIL_SIZE(self) -> int: ...
    @property
    def CACHE_EXPIRY_MINUTES(self) -> int: ...
    def __init__(self, cache_dir: Path | None = ...) -> None: ...
    def _ensure_cache_dirs(self) -> None: ...
    def get_cached_thumbnail(
        self,
        show: str,
        sequence: str,
        shot: str,
    ) -> Path | None: ...
    def cache_thumbnail(
        self,
        source_path: str | Path,
        show: str,
        sequence: str,
        shot: str,
        wait: bool = True,
        timeout: float | None = None,
    ) -> Path | Any | None: ...
    def get_cached_shots(self) -> list[dict[str, Any]] | None: ...
    def cache_shots(self, shots: Sequence[Shot]) -> None: ...
    def get_cached_threede_scenes(self) -> list[dict[str, Any]] | None: ...
    def cache_threede_scenes(self, scenes: list[dict[str, Any]]) -> None: ...
    def _evict_old_thumbnails(self) -> None: ...
    def get_memory_usage(self) -> dict[str, Any]: ...
    def clear_cache(self) -> None: ...
    def set_memory_limit(self, max_memory_mb: int) -> None: ...
    def set_expiry_minutes(self, expiry_minutes: int) -> None: ...
    def ensure_cache_directory(self) -> bool: ...
    def get_cached_previous_shots(self) -> list[dict[str, Any]] | None: ...
    def cache_previous_shots(
        self, shots: Sequence[Shot] | Sequence[dict[str, str]]
    ) -> None: ...
    def cache_data(self, key: str, data: Any) -> None: ...
    def get_cached_data(self, key: str) -> Any | None: ...
    def clear_cached_data(self, key: str) -> None: ...
    def validate_cache(self) -> dict[str, Any]: ...
    def clear_failed_attempts(self, cache_key: str | None = ...) -> None: ...
    def get_failed_attempts_status(self) -> dict[str, dict[str, Any]]: ...
    def shutdown(self) -> None: ...

class ThumbnailCacheLoader(QRunnable):
    """Background thumbnail cache loader."""

    class Signals(QObject):
        loaded: Signal

    cache_manager: CacheManager
    source_path: Path
    show: str
    sequence: str
    shot: str
    signals: Signals

    def __init__(
        self,
        cache_manager: CacheManager,
        source_path: Path,
        show: str,
        sequence: str,
        shot: str,
    ) -> None: ...
    def run(self) -> None: ...
