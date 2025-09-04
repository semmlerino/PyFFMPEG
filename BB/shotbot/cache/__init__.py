"""Cache system for ShotBot VFX application.

This package provides a modular cache architecture that replaces the monolithic
CacheManager with focused, single-responsibility components.

Architecture:
    - ThumbnailProcessor: Image processing with Qt/PIL/OpenEXR support
    - FailureTracker: Exponential backoff for failed operations
    - MemoryManager: Memory usage tracking and LRU eviction
    - StorageBackend: Atomic file I/O operations
    - ShotCache: Shot data caching with TTL
    - ThreeDECache: 3DE scene caching with metadata
    - CacheValidator: Cache validation and repair
    - ThumbnailLoader: Async thumbnail loading (QRunnable)

The main CacheManager acts as a facade maintaining backward compatibility.
"""

from typing import TYPE_CHECKING

from .cache_validator import CacheValidator
from .failure_tracker import FailureTracker
from .memory_manager import MemoryManager
from .shot_cache import ShotCache
from .storage_backend import StorageBackend
from .threede_cache import ThreeDECache
from .thumbnail_loader import ThumbnailLoader
from .thumbnail_processor import ThumbnailProcessor

# Import components for public API

__all__ = [
    "StorageBackend",
    "FailureTracker",
    "MemoryManager",
    "ThumbnailProcessor",
    "ShotCache",
    "ThreeDECache",
    "CacheValidator",
    "ThumbnailLoader",
]

# Version info for the cache system
__version__ = "2.0.0"
__description__ = "Modular cache system for ShotBot"
