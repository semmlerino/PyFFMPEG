"""Cache manager facade for shot data and thumbnails (refactored architecture).

This module provides a backward-compatible interface to the new modular cache
architecture while maintaining the exact same public API as the original
monolithic CacheManager.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence

# Use typing_extensions for override (available in venv)
from typing_extensions import override

from PySide6.QtCore import QObject, QRunnable, QThread, QThreadPool, Signal
from PySide6.QtWidgets import QApplication

from cache.cache_validator import CacheValidator
from cache.failure_tracker import FailureTracker
from cache.memory_manager import MemoryManager
from cache.shot_cache import ShotCache

# Import new modular components
from cache.storage_backend import StorageBackend
from cache.threede_cache import ThreeDECache
from cache.thumbnail_loader import ThumbnailCacheResult, ThumbnailLoader
from cache.thumbnail_processor import ThumbnailProcessor
from config import Config
from exceptions import CacheError, ThumbnailError
from type_definitions import (
    ShotDict,
    ThreeDESceneDict,
)

if TYPE_CHECKING:
    from shot_model import Shot

# Set up logger for this module
logger = logging.getLogger(__name__)


class CacheManager(QObject):
    """Manages caching of shot data and thumbnails with thread safety and memory monitoring.

    This is a facade that delegates to specialized components while maintaining
    full backward compatibility with the original monolithic implementation.

    New Architecture:
        - StorageBackend: Atomic file operations
        - FailureTracker: Exponential backoff for failed operations
        - MemoryManager: Memory usage tracking and eviction
        - ThumbnailProcessor: Multi-format image processing
        - ShotCache/ThreeDECache: Data caching with TTL
        - CacheValidator: Consistency validation and repair
        - ThumbnailLoader: Async background processing
    """

    # Signals - maintain backward compatibility
    cache_updated = Signal()

    def __init__(self, cache_dir: Path | None = None):
        """Initialize cache manager facade with modular components.

        Args:
            cache_dir: Cache directory path. If None, uses default ~/.shotbot/cache
        """
        super().__init__()

        # Thread safety for coordination
        self._lock: threading.RLock = threading.RLock()

        # Set up cache directory structure
        self.cache_dir = cache_dir or (Path.home() / ".shotbot" / "cache")
        self.thumbnails_dir = self.cache_dir / "thumbnails"
        self.shots_cache_file = self.cache_dir / "shots.json"
        self.threede_scenes_cache_file = self.cache_dir / "threede_scenes.json"
        self.previous_shots_cache_file = self.cache_dir / "previous_shots.json"

        # Initialize modular components
        self._storage_backend = StorageBackend()
        self._failure_tracker = FailureTracker()
        self._memory_manager = MemoryManager()
        self._thumbnail_processor = ThumbnailProcessor()

        # Initialize data caches
        self._shot_cache = ShotCache(self.shots_cache_file, self._storage_backend)
        self._threede_cache = ThreeDECache(
            self.threede_scenes_cache_file, self._storage_backend
        )
        self._previous_shots_cache = ShotCache(
            self.previous_shots_cache_file, self._storage_backend
        )

        # Initialize validator (will be created after directory setup)
        self._cache_validator: CacheValidator | None = None

        # Track active async loaders for synchronization
        self._active_loaders: dict[str, ThumbnailCacheResult] = {}

        # Track last validation time for periodic validation
        self._last_validation_time = datetime.now()
        self._validation_interval_minutes = 30

        # Ensure cache directories exist
        self._ensure_cache_dirs()

        # Initialize validator after directories are set up
        self._cache_validator = CacheValidator(
            self.thumbnails_dir, self._memory_manager, self._storage_backend
        )

        logger.debug("CacheManager facade initialized with modular architecture")

    # Backward compatibility properties for internal test access
    @property
    def _cached_thumbnails(self) -> dict[str, int]:
        """Backward compatibility property for memory tracking."""
        # Return direct reference for backward compatibility with tests
        # Note: In production code, use get_memory_usage() for read-only access
        return self._memory_manager._cached_items

    @property
    def _memory_usage_bytes(self) -> int:
        """Backward compatibility property for memory usage."""
        return self._memory_manager.memory_usage_bytes

    @_memory_usage_bytes.setter
    def _memory_usage_bytes(self, value: int):
        """Backward compatibility setter for memory usage."""
        self._memory_manager.memory_usage_bytes = value

    @property
    def _max_memory_bytes(self) -> int:
        """Backward compatibility property for memory limit."""
        return self._memory_manager.max_memory_bytes

    @_max_memory_bytes.setter
    def _max_memory_bytes(self, value: int):
        """Backward compatibility setter for memory limit (test use only)."""
        # Note: In production, memory limit should be set via constructor
        # This setter exists only for backward compatibility with existing tests
        self._memory_manager._max_memory_bytes = value

    @property
    def _failed_attempts(self) -> dict[str, dict[str, Any]]:
        """Backward compatibility property for failure tracking."""
        return self._failure_tracker.get_failure_status()

    # Configuration properties - maintain backward compatibility
    @property
    def CACHE_THUMBNAIL_SIZE(self) -> int:
        """Get the cached thumbnail size from configuration."""
        return Config.CACHE_THUMBNAIL_SIZE

    @property
    def CACHE_EXPIRY_MINUTES(self) -> int:
        """Get cache expiry time in minutes from configuration."""
        return Config.CACHE_EXPIRY_MINUTES

    def _ensure_cache_dirs(self) -> None:
        """Ensure cache directories exist using storage backend."""
        if not self._storage_backend.ensure_directory(self.thumbnails_dir):
            # If normal directory creation fails, try fallback
            logger.warning("Using fallback cache directory setup")
            # The storage backend handles fallback internally
        logger.debug(f"Ensured cache directory exists: {self.thumbnails_dir}")

    def ensure_cache_directory(self) -> bool:
        """Ensure cache directory exists, creating if necessary."""
        return self._storage_backend.ensure_directory(self.thumbnails_dir)

    # Thumbnail caching methods - backward compatible interface
    def get_cached_thumbnail(self, show: str, sequence: str, shot: str) -> Path | None:
        """Get path to cached thumbnail if it exists (thread-safe)."""
        with self._lock:
            # Periodic validation
            self._run_periodic_validation()

            cache_path = self.thumbnails_dir / show / sequence / f"{shot}_thumb.jpg"
            if cache_path.exists():
                # Track in memory manager if not already tracked
                _ = self._memory_manager.track_item(cache_path)
                return cache_path
            return None

    def cache_thumbnail(
        self,
        source_path: str | Path,
        show: str,
        sequence: str,
        shot: str,
        wait: bool = True,
        timeout: float | None = None,
    ) -> Path | ThumbnailCacheResult | None:
        """Cache a thumbnail from source path with optional synchronization."""
        # Convert source_path to Path object for consistent handling
        source_path_obj = (
            Path(source_path) if isinstance(source_path, str) else source_path
        )
        if not source_path_obj or not source_path_obj.exists():
            logger.warning(f"Source thumbnail path does not exist: {source_path_obj}")
            return None

        # Validate parameters
        if not all([show, sequence, shot]):
            error_msg = "Missing required parameters for thumbnail caching"
            logger.error(error_msg)
            raise ThumbnailError(
                error_msg,
                details={
                    "source_path": source_path,
                    "show": show,
                    "sequence": sequence,
                    "shot": shot,
                },
            )

        cache_key = f"{show}_{sequence}_{shot}"

        with self._lock:
            # Check if already being loaded
            if cache_key in self._active_loaders:
                result = self._active_loaders[cache_key]
                if wait:
                    return result.get_result(timeout)
                return result

            # Check if already cached
            cache_path = self.thumbnails_dir / show / sequence / f"{shot}_thumb.jpg"
            if cache_path.exists():
                logger.debug(f"Thumbnail already cached: {cache_path}")
                _ = self._memory_manager.track_item(cache_path)
                return cache_path

            # Check failure tracker
            should_retry, reason = self._failure_tracker.should_retry(
                cache_key, source_path_obj
            )
            if not should_retry:
                logger.debug(reason)
                return None if wait else None

            # Create result container and track loading
            result = ThumbnailCacheResult()
            self._active_loaders[cache_key] = result

        # Determine processing approach
        app = QApplication.instance()
        is_main_thread = app is not None and QThread.currentThread() == app.thread()

        if not is_main_thread:
            # Background thread - use ThumbnailLoader
            loader: ThumbnailLoader = ThumbnailLoader(
                self._thumbnail_processor,
                self._failure_tracker,
                source_path_obj,
                cache_path,
                show,
                sequence,
                shot,
                result,
            )

            # Connect cleanup
            # Use proper typed functions instead of lambdas to avoid type issues
            def on_loaded(show: str, sequence: str, shot: str, path: Path) -> None:
                self._on_thumbnail_loaded(cache_key, cache_path)
            
            def on_failed(show: str, sequence: str, shot: str, error: str) -> None:
                self._cleanup_loader(cache_key)
                
            _ = loader.signals.loaded.connect(on_loaded)
            _ = loader.signals.failed.connect(on_failed)

            pool = QThreadPool.globalInstance()
            pool.start(loader)  # type: ignore[arg-type]

            if wait:
                return result.get_result(timeout)
            return result
        else:
            # Main thread - process directly
            success = self._thumbnail_processor.process_thumbnail(
                source_path_obj, cache_path
            )

            if success and cache_path.exists():
                result.set_result(cache_path)
                self._on_thumbnail_loaded(cache_key, cache_path)
                self._cleanup_loader(cache_key)
                return cache_path if wait else result
            else:
                error_msg = "Failed to cache thumbnail"
                result.set_error(error_msg)
                self._failure_tracker.record_failure(
                    cache_key, error_msg, source_path_obj
                )
                self._cleanup_loader(cache_key)
                return None if wait else result

    def cache_thumbnail_direct(
        self, source_path: Path, show: str, sequence: str, shot: str
    ) -> Path | None:
        """Direct thumbnail caching implementation (backward compatibility)."""
        cache_path = self.thumbnails_dir / show / sequence / f"{shot}_thumb.jpg"

        if self._thumbnail_processor.process_thumbnail(source_path, cache_path):
            _ = self._memory_manager.track_item(cache_path)
            # Trigger eviction if memory limit exceeded
            _ = self._memory_manager.evict_if_needed()
            return cache_path
        return None

    def _on_thumbnail_loaded(self, cache_key: str, cache_path: Path):
        """Handle successful thumbnail loading."""
        # Track in memory manager
        _ = self._memory_manager.track_item(cache_path)
        # Trigger eviction if memory limit exceeded
        _ = self._memory_manager.evict_if_needed()

    def _cleanup_loader(self, cache_key: str) -> None:
        """Remove completed loader from tracking."""
        with self._lock:
            _ = self._active_loaders.pop(cache_key, None)

    def _run_periodic_validation(self) -> None:
        """Run periodic cache validation."""
        time_since_validation = datetime.now() - self._last_validation_time
        if time_since_validation > timedelta(minutes=self._validation_interval_minutes):
            if self._cache_validator:
                logger.debug("Running periodic cache validation")
                _ = self._cache_validator.validate_cache(fix_issues=True)
            self._last_validation_time = datetime.now()

    # Shot caching methods - delegate to ShotCache
    def get_cached_shots(self) -> list[ShotDict] | None:
        """Get cached shot list if valid."""
        return self._shot_cache.get_cached_shots()

    def cache_shots(self, shots: Sequence["Shot"] | Sequence[ShotDict]):
        """Cache shot list to file."""
        _ = self._shot_cache.cache_shots(shots)

    # Previous shots caching methods - delegate to ShotCache
    def get_cached_previous_shots(self) -> list[ShotDict] | None:
        """Get cached previous/approved shot list if valid."""
        return self._previous_shots_cache.get_cached_shots()

    def cache_previous_shots(self, shots: Sequence["Shot"] | Sequence[ShotDict]):
        """Cache previous/approved shot list to file."""
        _ = self._previous_shots_cache.cache_shots(shots)

    # 3DE scene caching methods - delegate to ThreeDECache
    def get_cached_threede_scenes(self) -> list[ThreeDESceneDict] | None:
        """Get cached 3DE scene list if valid."""
        return self._threede_cache.get_cached_scenes()

    def has_valid_threede_cache(self) -> bool:
        """Check if we have a valid 3DE cache (including valid empty results)."""
        return self._threede_cache.has_valid_cache()

    def cache_threede_scenes(
        self, scenes: list[ThreeDESceneDict], metadata: dict[str, Any] | None = None
    ):
        """Cache 3DE scene list to file with optional metadata."""
        _ = self._threede_cache.cache_scenes(scenes, metadata)

    # Generic data caching methods for backward compatibility
    def cache_data(self, key: str, data: Any) -> None:
        """Cache generic data with a key (for backward compatibility).

        Args:
            key: Cache key identifier
            data: Data to cache
        """
        if key == "previous_shots":
            self.cache_previous_shots(data)
        else:
            # For other generic data, use storage backend directly
            cache_file = self.cache_dir / f"{key}.json"
            _ = self._storage_backend.write_json(cache_file, data)

    def get_cached_data(self, key: str) -> Any | None:
        """Get cached generic data by key (for backward compatibility).

        Args:
            key: Cache key identifier

        Returns:
            Cached data or None if not found/expired
        """
        if key == "previous_shots":
            return self.get_cached_previous_shots()
        else:
            # For other generic data, use storage backend directly
            cache_file = self.cache_dir / f"{key}.json"
            return self._storage_backend.read_json(cache_file)

    def clear_cached_data(self, key: str) -> None:
        """Clear cached generic data by key (for backward compatibility).

        Args:
            key: Cache key identifier
        """
        if key == "previous_shots":
            # Clear the previous shots cache file
            if self.previous_shots_cache_file.exists():
                self.previous_shots_cache_file.unlink()
        else:
            # For other generic data
            cache_file = self.cache_dir / f"{key}.json"
            if cache_file.exists():
                cache_file.unlink()

    # Memory and validation methods - delegate to appropriate components
    def get_memory_usage(self) -> dict[str, Any]:
        """Get current cache memory usage statistics (backward compatible)."""
        stats = self._memory_manager.get_usage_stats()
        total_bytes = stats.get("total_bytes", 0)
        max_bytes = self._memory_manager._max_memory_bytes
        
        # Return old format for backward compatibility
        return {
            "total_bytes": total_bytes,
            "total_mb": total_bytes / (1024 * 1024),
            "max_mb": max_bytes / (1024 * 1024),
            "usage_percent": stats.get("usage_percent", 0.0),
            "thumbnail_count": stats.get("tracked_items", 0),
        }

    def validate_cache(self) -> dict[str, Any]:
        """Validate cache consistency and fix issues (backward compatible)."""
        if self._cache_validator:
            result = self._cache_validator.validate_cache()
            # Return old format for backward compatibility with all expected fields
            return {
                "valid": result.get("valid", False),
                "issues_found": result.get("issues_found", 0),
                "issues_fixed": result.get("issues_fixed", 0),
                "orphaned_files": result.get("orphaned_files", 0),
                "missing_files": result.get("missing_files", 0),
                "invalid_entries": [],  # Not tracked in new implementation
                "size_mismatches": result.get("size_mismatches", 0),
                "memory_usage_corrected": result.get("memory_usage_corrected", False),
                "details": result.get("details", []),
            }
        return {
            "valid": False,
            "issues_found": 0,
            "issues_fixed": 0,
            "orphaned_files": 0,
            "missing_files": 0,
            "invalid_entries": [],
            "size_mismatches": 0,
            "memory_usage_corrected": False,
            "details": [],
        }

    def clear_cache(self):
        """Clear all cached data."""
        with self._lock:
            # Clear memory tracking
            self._memory_manager.clear_all_tracking()

            # Clear failure tracking
            self._failure_tracker.clear_failures()

            # Clear data caches
            _ = self._shot_cache.clear_cache()
            _ = self._threede_cache.clear_cache()

            # Clear active loaders
            self._active_loaders.clear()

            # Remove thumbnail directory
            import shutil

            if self.thumbnails_dir.exists():
                try:
                    shutil.rmtree(self.thumbnails_dir, ignore_errors=True)
                    logger.info("Cleared thumbnail cache directory")
                except (OSError, IOError) as e:
                    # Log but don't raise - clearing cache is not critical
                    logger.error(f"Failed to clear thumbnail directory: {e}")

            # Recreate directory
            self._ensure_cache_dirs()

            logger.info("Cache cleared successfully")

    # Failure tracking methods - delegate to FailureTracker
    def clear_failed_attempts(self, cache_key: str | None = None):
        """Clear failed attempts to allow immediate retry."""
        self._failure_tracker.clear_failures(cache_key)

    def get_failed_attempts_status(self) -> dict[str, dict[str, Any]]:
        """Get current status of failed attempts for debugging."""
        return self._failure_tracker.get_failure_status()

    def _evict_old_thumbnails(self) -> int:
        """Backward compatibility method for evicting old thumbnails."""
        return self._memory_manager.evict_if_needed()

    # Shutdown method for graceful cleanup
    def shutdown(self) -> None:
        """Gracefully shutdown the cache manager."""
        logger.info("CacheManager shutting down...")

        with self._lock:
            try:
                # Validate and fix any cache inconsistencies
                if self._cache_validator:
                    validation_result = self._cache_validator.validate_cache(
                        fix_issues=True
                    )
                    if not validation_result.get("valid", False):
                        logger.info(
                            f"Fixed {validation_result.get('issues_fixed', 0)} cache issues during shutdown"
                        )

                # Clear memory tracking
                self._memory_manager.clear_all_tracking()

                # Clear failure tracking
                failed_count = self._failure_tracker.get_failure_count()
                self._failure_tracker.clear_failures()
                if failed_count > 0:
                    logger.debug(
                        f"Cleared {failed_count} failed attempts during shutdown"
                    )

                # Clear active loaders
                self._active_loaders.clear()

                logger.info("CacheManager shutdown complete")

            except (OSError, IOError, CacheError) as e:
                logger.error(f"Error during cache manager shutdown: {e}")

    def set_memory_limit(self, max_memory_mb: int) -> None:
        """Set maximum memory limit for cache in megabytes.

        Args:
            max_memory_mb: Maximum memory in megabytes
        """
        # Use the public method to set memory limit
        self._memory_manager.set_memory_limit(max_memory_mb)
        logger.info(f"Cache memory limit set to {max_memory_mb} MB")

    def set_expiry_minutes(self, expiry_minutes: int) -> None:
        """Set cache expiry time in minutes.

        Args:
            expiry_minutes: Cache expiry time in minutes
        """
        # Update expiry for both shot and 3DE caches using their public methods
        self._shot_cache.set_expiry_minutes(expiry_minutes)
        self._threede_cache.set_expiry_minutes(expiry_minutes)

        logger.info(f"Cache expiry set to {expiry_minutes} minutes")

    # ================================================================
    # Test-Specific Accessor Methods
    # ================================================================
    # WARNING: These methods are for testing purposes ONLY.
    # They provide controlled access to private attributes for tests.
    # DO NOT use these methods in production code.

    @property
    def test_storage_backend(self) -> "StorageBackend":
        """Test-only access to storage backend."""
        return self._storage_backend

    @property
    def test_failure_tracker(self) -> "FailureTracker":
        """Test-only access to failure tracker."""
        return self._failure_tracker

    @property
    def test_memory_manager(self) -> "MemoryManager":
        """Test-only access to memory manager."""
        return self._memory_manager

    @property
    def test_shot_cache(self) -> "ShotCache":
        """Test-only access to shot cache."""
        return self._shot_cache

    @property
    def test_threede_cache(self) -> "ThreeDECache":
        """Test-only access to 3DE cache."""
        return self._threede_cache

    @property
    def test_cached_thumbnails(self) -> dict[str, int]:
        """Test-only access to cached thumbnails dictionary.

        Returns:
            Dictionary mapping thumbnail path to size in bytes.
            This is for test access only - production code should use
            get_memory_usage() for memory statistics.

        Note:
            The return type is dict[str, int] where:
            - key: thumbnail file path (str)
            - value: memory usage in bytes (int)
        """
        return self._cached_thumbnails

    @property
    def test_memory_usage_bytes(self) -> int:
        """Test-only access to memory usage counter.

        Returns:
            Current memory usage in bytes.
        """
        return self._memory_usage_bytes

    @test_memory_usage_bytes.setter
    def test_memory_usage_bytes(self, value: int) -> None:
        """Test-only setter for memory usage counter.

        Args:
            value: Memory usage value in bytes.

        Warning:
            This setter is for testing only. Production code should
            not directly manipulate memory usage counters.
        """
        self._memory_usage_bytes = value

    @property
    def test_max_memory_bytes(self) -> int:
        """Test-only access to max memory limit.

        Returns:
            Maximum memory limit in bytes.
        """
        return self._max_memory_bytes

    @property
    def test_lock(self) -> threading.RLock:
        """Test-only access to the coordination lock.

        Returns:
            The RLock used for thread-safe coordination.

        Warning:
            This is for testing thread safety only. Production code
            should not access internal locking mechanisms.
        """
        return self._lock


# Backward compatibility wrapper for ThumbnailCacheLoader
class ThumbnailCacheLoader(QRunnable):
    """Backward compatibility wrapper for the original ThumbnailCacheLoader API."""

    def __init__(
        self,
        cache_manager: "CacheManager",
        source_path: Path | str,
        show: str,
        sequence: str,
        shot: str,
        result: dict[str, Any] | None = None,
    ):
        """Initialize with original constructor signature."""
        super().__init__()
        from cache.thumbnail_loader import ThumbnailLoader

        # Map to new constructor
        cache_path = (
            cache_manager.thumbnails_dir / show / sequence / f"{shot}_thumb.jpg"
        )
        
        # Ensure source_path is a Path object
        source_path_obj = Path(source_path) if isinstance(source_path, str) else source_path
        
        # Convert dict result to ThumbnailCacheResult if needed
        result_obj = None
        if result is not None:
            if isinstance(result, dict):
                result_obj = ThumbnailCacheResult()
                # Copy any existing data from dict to result object
            else:
                result_obj = result

        self._loader = ThumbnailLoader(
            cache_manager._thumbnail_processor,
            cache_manager._failure_tracker,
            source_path_obj,
            cache_path,
            show,
            sequence,
            shot,
            result_obj,
        )

        # Expose the same interface
        self.cache_manager = cache_manager
        self.source_path = source_path
        self.show = show
        self.sequence = sequence
        self.shot = shot
        self.signals = self._loader.signals
        self.result = self._loader.result

    @override
    def run(self):
        """Run the thumbnail processing."""
        return self._loader.run()

    @override
    def setAutoDelete(self, autoDelete: bool) -> None:
        """Set auto delete flag."""
        super().setAutoDelete(autoDelete)
        self._loader.setAutoDelete(autoDelete)


# Maintain backward compatibility by re-exporting classes
__all__ = ["CacheManager", "ThumbnailCacheResult", "ThumbnailCacheLoader"]
