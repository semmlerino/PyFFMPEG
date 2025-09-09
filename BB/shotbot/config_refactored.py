"""Refactored configuration system with focused modules.

This demonstrates how to split the monolithic config.py into
focused, cohesive configuration classes.
"""

from __future__ import annotations

import multiprocessing
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar


@dataclass
class ApplicationConfig:
    """Core application settings."""

    APP_NAME: ClassVar[str] = "ShotBot"
    APP_VERSION: ClassVar[str] = "1.0.2"
    SETTINGS_FILE: Path = field(
        default_factory=lambda: Path.home() / ".shotbot" / "settings.json"
    )
    DEFAULT_USERNAME: str = "gabriel-h"


@dataclass
class WindowConfig:
    """Window and UI layout configuration."""

    # Window dimensions
    DEFAULT_WIDTH: int = 1200
    DEFAULT_HEIGHT: int = 800
    MIN_WIDTH: int = 800
    MIN_HEIGHT: int = 600

    # Grid layout
    GRID_COLUMNS: int = 4

    # Log settings
    LOG_MAX_LINES: int = 1000

    # Notification timings (ms)
    TOAST_DURATION: int = 4000
    SUCCESS_TIMEOUT: int = 3000
    ERROR_TIMEOUT: int = 5000
    MAX_TOASTS: int = 5


@dataclass
class ThumbnailConfig:
    """Thumbnail display and processing settings."""

    # Size constraints
    DEFAULT_SIZE: int = 200
    MIN_SIZE: int = 100
    MAX_SIZE: int = 400
    SPACING: int = 20
    CACHE_SIZE: int = 512

    # Visual settings
    PLACEHOLDER_COLOR: str = "#444444"

    # Performance limits
    MAX_DIMENSION_PX: int = 4096
    MAX_MEMORY_MB: int = 50
    MAX_THREADS: int = 4
    UNLOAD_DELAY_MS: int = 5000

    # File extensions (order matters for priority)
    EXTENSIONS: list[str] = field(default_factory=lambda: [".jpg", ".jpeg", ".png"])
    FALLBACK_EXTENSIONS: list[str] = field(
        default_factory=lambda: [".exr", ".dpx", ".tiff"]
    )


@dataclass
class PathConfig:
    """File system paths and patterns."""

    # Root directories (configurable via environment)
    SHOWS_ROOT: str = field(
        default_factory=lambda: os.environ.get("SHOWS_ROOT", "/shows")
    )

    # Path patterns for thumbnails
    THUMBNAIL_PATTERN: str = "{shows_root}/{show}/shots/{sequence}/{shot}/publish/editorial/cutref/v001/jpg/1920x1080/"
    UNDISTORTION_SUBPATH: str = "mm"

    @property
    def shows_path(self) -> Path:
        """Get shows root as Path object."""
        return Path(self.SHOWS_ROOT)

    def validate(self) -> bool:
        """Validate that configured paths exist."""
        return self.shows_path.exists()


@dataclass
class VFXApplicationConfig:
    """VFX application commands and settings."""

    # Application executables
    APPS: dict[str, str] = field(
        default_factory=lambda: {
            "3de": "3de",
            "nuke": "nuke",
            "maya": "maya",
            "rv": "rv",
            "publish": "publish_standalone",
        }
    )

    DEFAULT_APP: str = "nuke"

    # Rez environment settings
    USE_REZ: bool = True
    REZ_AUTO_DETECT: bool = True
    REZ_PACKAGES: dict[str, list[str]] = field(
        default_factory=lambda: {
            "nuke": ["nuke"],
            "maya": ["maya"],
            "3de": ["3de"],
        }
    )

    # Nuke-specific settings
    NUKE_UNDISTORTION_MODE: str = "direct"  # "direct" or "parse"
    NUKE_USE_LOADER_SCRIPT: bool = True

    # Terminal settings
    USE_PERSISTENT_TERMINAL: bool = True
    PERSISTENT_TERMINAL_FIFO: str = "/tmp/shotbot_commands.fifo"
    PERSISTENT_TERMINAL_TITLE: str = "ShotBot Terminal"
    AUTO_BACKGROUND_GUI_APPS: bool = True
    KEEP_TERMINAL_ON_EXIT: bool = False
    CLEAR_TERMINAL_BEFORE_COMMAND: bool = False


@dataclass
class PerformanceConfig:
    """Performance tuning and resource limits."""

    # CPU settings
    CPU_COUNT: int = field(default_factory=multiprocessing.cpu_count)

    # Process timeouts (seconds)
    SUBPROCESS_TIMEOUT: int = 10
    WS_COMMAND_TIMEOUT: int = 10

    # Memory limits (MB)
    MAX_FILE_SIZE_MB: int = 100
    MAX_CACHE_DIMENSION_PX: int = 10000
    MAX_INFO_PANEL_DIMENSION_PX: int = 2048

    # Performance monitoring
    ENABLE_MONITORING: bool = True
    STATS_LOG_INTERVAL: int = 300  # seconds


@dataclass
class CacheConfig:
    """Cache management settings."""

    # Time-based settings (minutes unless specified)
    EXPIRY_MINUTES: int = 1440  # 24 hours
    REFRESH_INTERVAL_MINUTES: int = 60
    ENABLE_BACKGROUND_REFRESH: bool = True

    # TTL settings (seconds, 0 = manual refresh only)
    PATH_TTL: int = 0
    DIR_TTL: int = 0
    SCENE_TTL: int = 0

    # Size limits
    PATH_MAX_SIZE: int = 5000
    DIR_MAX_SIZE: int = 500
    SCENE_MAX_SIZE: int = 2000

    # Memory limits (MB)
    PATH_MAX_MEMORY_MB: float = 1.0
    DIR_MAX_MEMORY_MB: float = 5.0
    SCENE_MAX_MEMORY_MB: float = 5.0
    THUMB_MAX_MEMORY_MB: float = 2.0

    # Memory pressure thresholds (%)
    PRESSURE_NORMAL: float = 70.0
    PRESSURE_MODERATE: float = 85.0
    PRESSURE_HIGH: float = 95.0


@dataclass
class ThreadingConfig:
    """Threading and parallelism configuration."""

    # Parallel workers
    PREVIOUS_SHOTS_PARALLEL_WORKERS: int = 8

    # Scan timeouts (seconds)
    PREVIOUS_SHOTS_SCAN_TIMEOUT: int = 30
    PREVIOUS_SHOTS_CACHE_TTL: int = 300  # 5 minutes


class Config:
    """Composite configuration using focused config objects.

    This maintains backward compatibility while providing
    better organization internally.
    """

    # Initialize sub-configurations
    _app = ApplicationConfig()
    _window = WindowConfig()
    _thumbnail = ThumbnailConfig()
    _paths = PathConfig()
    _vfx = VFXApplicationConfig()
    _performance = PerformanceConfig()
    _cache = CacheConfig()
    _threading = ThreadingConfig()

    # Expose as class attributes for backward compatibility
    # Application
    APP_NAME = _app.APP_NAME
    APP_VERSION = _app.APP_VERSION
    SETTINGS_FILE = _app.SETTINGS_FILE
    DEFAULT_USERNAME = _app.DEFAULT_USERNAME

    # Window
    DEFAULT_WINDOW_WIDTH = _window.DEFAULT_WIDTH
    DEFAULT_WINDOW_HEIGHT = _window.DEFAULT_HEIGHT
    MIN_WINDOW_WIDTH = _window.MIN_WIDTH
    MIN_WINDOW_HEIGHT = _window.MIN_HEIGHT
    GRID_COLUMNS = _window.GRID_COLUMNS
    LOG_MAX_LINES = _window.LOG_MAX_LINES

    # Thumbnails
    DEFAULT_THUMBNAIL_SIZE = _thumbnail.DEFAULT_SIZE
    MIN_THUMBNAIL_SIZE = _thumbnail.MIN_SIZE
    MAX_THUMBNAIL_SIZE = _thumbnail.MAX_SIZE
    THUMBNAIL_SPACING = _thumbnail.SPACING
    PLACEHOLDER_COLOR = _thumbnail.PLACEHOLDER_COLOR
    MAX_THUMBNAIL_THREADS = _thumbnail.MAX_THREADS

    # Paths
    SHOWS_ROOT = _paths.SHOWS_ROOT
    THUMBNAIL_PATH_PATTERN = _paths.THUMBNAIL_PATTERN

    # VFX Apps
    APPS = _vfx.APPS
    DEFAULT_APP = _vfx.DEFAULT_APP

    # Performance
    SUBPROCESS_TIMEOUT_SECONDS = _performance.SUBPROCESS_TIMEOUT
    WS_COMMAND_TIMEOUT_SECONDS = _performance.WS_COMMAND_TIMEOUT
    CPU_COUNT = _performance.CPU_COUNT

    # Cache
    CACHE_EXPIRY_MINUTES = _cache.EXPIRY_MINUTES
    CACHE_REFRESH_INTERVAL_MINUTES = _cache.REFRESH_INTERVAL_MINUTES

    @classmethod
    def get_app_config(cls) -> ApplicationConfig:
        """Get application configuration object."""
        return cls._app

    @classmethod
    def get_window_config(cls) -> WindowConfig:
        """Get window configuration object."""
        return cls._window

    @classmethod
    def get_thumbnail_config(cls) -> ThumbnailConfig:
        """Get thumbnail configuration object."""
        return cls._thumbnail

    @classmethod
    def get_path_config(cls) -> PathConfig:
        """Get path configuration object."""
        return cls._paths

    @classmethod
    def get_vfx_config(cls) -> VFXApplicationConfig:
        """Get VFX application configuration object."""
        return cls._vfx

    @classmethod
    def get_performance_config(cls) -> PerformanceConfig:
        """Get performance configuration object."""
        return cls._performance

    @classmethod
    def get_cache_config(cls) -> CacheConfig:
        """Get cache configuration object."""
        return cls._cache

    @classmethod
    def get_threading_config(cls) -> ThreadingConfig:
        """Get threading configuration object."""
        return cls._threading
