"""Cache system for ShotBot VFX application.

This package provides a unified cache architecture with 3 focused components.

Unified Architecture:
    - StorageBackend: Atomic file I/O operations with validation methods
    - ThumbnailManager: Unified thumbnail processing, memory management, failure tracking
    - UnifiedCache: Generic TTL cache replacing shot_cache and threede_cache

The main CacheManager acts as a facade maintaining backward compatibility.
"""

from .storage_backend import StorageBackend
from .thumbnail_manager import ThumbnailCacheResult, ThumbnailManager
from .unified_cache import UnifiedCache, create_shot_cache, create_threede_cache

# Import components for public API

__all__ = [
    "StorageBackend",
    "ThumbnailManager",
    "ThumbnailCacheResult",
    "UnifiedCache",
    "create_shot_cache",
    "create_threede_cache",
]

# Version info for the cache system
__version__ = "3.0.0"
__description__ = "Unified cache system for ShotBot"
