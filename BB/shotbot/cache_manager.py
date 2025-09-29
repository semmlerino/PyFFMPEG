"""Cache manager facade for shot data and thumbnails (refactored architecture).

This module provides a backward-compatible interface to the new modular cache
architecture while maintaining the exact same public API as the original
monolithic CacheManager.
"""

from __future__ import annotations

# Standard library imports
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, cast

# Third-party imports
from PySide6.QtCore import (
    QMutex,
    QMutexLocker,
    QObject,
    QRunnable,
    QThread,
    QThreadPool,
    Signal,
)
from PySide6.QtWidgets import QApplication

# Use typing_extensions for override (available in venv)
from typing_extensions import override

# Import new unified components
from cache.storage_backend import StorageBackend
from cache.thumbnail_manager import (
    ThumbnailCacheResult,
    ThumbnailManager,
)
from cache.unified_cache import (
    CacheableData,
    UnifiedCache,
    create_shot_cache,
    create_threede_cache,
)

# Import cache configuration (now includes unified config)
from cache_config import UnifiedCacheConfig, create_unified_cache_config
from config import Config
from exceptions import CacheError, ThumbnailError
from logging_mixin import LoggingMixin

if TYPE_CHECKING:
    # Standard library imports
    from collections.abc import Sequence

    # Local application imports
    from settings_manager import SettingsManager
    from shot_model import Shot
    from type_definitions import (
        ShotDict,
        ThreeDESceneDict,
    )

# Logger now provided by LoggingMixin


class CacheManager(LoggingMixin, QObject):
    """Manages caching of shot data and thumbnails with thread safety and memory monitoring.

    This is a facade that delegates to specialized components while maintaining
    full backward compatibility with the original monolithic implementation.

    Unified Architecture (3 Components):
        - StorageBackend: Atomic file operations with validation methods
        - ThumbnailManager: Unified thumbnail processing, memory management, failure tracking
        - UnifiedCache: Generic TTL cache replacing shot_cache and threede_cache
    """

    # Signals - maintain backward compatibility
    cache_updated = Signal()

    def __init__(
        self,
        cache_dir: Path | None = None,
        settings_manager: SettingsManager | None = None,
    ) -> None:
        """Initialize cache manager facade with modular components.

        Args:
            cache_dir: Cache directory path. If None, uses mode-appropriate default
            settings_manager: Settings manager for unified cache configuration
        """
        super().__init__()

        # Thread safety for coordination
        self._lock: QMutex = QMutex()

        # Initialize unified cache configuration if settings manager provided
        self._unified_config: UnifiedCacheConfig | None = None
        if settings_manager:
            try:
                self._unified_config = create_unified_cache_config(settings_manager)
                self.logger.info("CacheManager using unified cache configuration")
            except Exception as e:
                self.logger.warning(f"Failed to initialize unified cache config: {e}")

        # Set up cache directory structure using CacheConfig for mode separation
        if cache_dir is None:
            # Local application imports
            from cache_config import CacheConfig

            self.cache_dir = CacheConfig.get_cache_directory()
            self.logger.debug(f"Using mode-based cache directory: {self.cache_dir}")
        else:
            self.cache_dir = cache_dir
        self.thumbnails_dir = self.cache_dir / "thumbnails"
        self.shots_cache_file = self.cache_dir / "shots.json"
        self.threede_scenes_cache_file = self.cache_dir / "threede_scenes.json"
        self.previous_shots_cache_file = self.cache_dir / "previous_shots.json"

        # Initialize unified components (3-component architecture)
        self._storage_backend = StorageBackend()

        # Use unified config for thumbnail manager if available
        if self._unified_config:
            max_memory_mb = self._unified_config.memory_limit_mb
            # Connect to configuration changes
            self._unified_config.memory_limit_changed.connect(
                self._on_memory_limit_changed
            )
            self._unified_config.expiry_time_changed.connect(
                self._on_expiry_time_changed
            )
        else:
            max_memory_mb = None  # Use default

        self._thumbnail_manager = ThumbnailManager(max_memory_mb=max_memory_mb)

        # Initialize data caches with unified config if available
        expiry_minutes = (
            self._unified_config.expiry_minutes
            if self._unified_config
            else None  # Use config defaults
        )

        self._shot_cache = create_shot_cache(
            self.shots_cache_file, expiry_minutes=expiry_minutes
        )
        self._threede_cache = create_threede_cache(
            self.threede_scenes_cache_file, expiry_minutes=expiry_minutes
        )
        self._previous_shots_cache = create_shot_cache(
            self.previous_shots_cache_file, expiry_minutes=expiry_minutes
        )

        # Track active async loaders for synchronization
        self._active_loaders: dict[str, ThumbnailCacheResult] = {}

        # Track last validation time for periodic validation
        self._last_validation_time = datetime.now()
        self._validation_interval_minutes = 30

        # Ensure cache directories exist
        self._ensure_cache_dirs()

        self.logger.debug("CacheManager facade initialized with unified architecture")

    # Backward compatibility properties for internal test access
    @property
    def _cached_thumbnails(self) -> dict[str, int]:
        """Backward compatibility property for memory tracking."""
        # Return direct reference for backward compatibility with tests
        # Note: In production code, use get_usage_stats() for read-only access
        return self._thumbnail_manager.cached_items

    @property
    def _memory_usage_bytes(self) -> int:
        """Backward compatibility property for memory usage."""
        return self._thumbnail_manager.memory_usage_bytes

    @_memory_usage_bytes.setter
    def _memory_usage_bytes(self, value: int) -> None:
        """Backward compatibility setter for memory usage."""
        # Note: This requires direct access for the setter
        self._thumbnail_manager._memory_usage_bytes = value  # type: ignore[reportPrivateUsage]

    @property
    def _max_memory_bytes(self) -> int:
        """Backward compatibility property for memory limit."""
        return self._thumbnail_manager.max_memory_bytes

    @_max_memory_bytes.setter
    def _max_memory_bytes(self, value: int) -> None:
        """Backward compatibility setter for memory limit (test use only)."""
        # Note: In production, memory limit should be set via constructor
        # This setter exists only for backward compatibility with existing tests
        # Convert bytes to MB, ensuring minimum of 1 MB to avoid zero
        max_mb = max(1, value // (1024 * 1024))
        self._thumbnail_manager.set_memory_limit(max_mb)

    @property
    def _failed_attempts(self) -> dict[str, dict[str, object]]:
        """Backward compatibility property for failure tracking."""
        return self._thumbnail_manager.get_failure_status()

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
            self.logger.warning("Using fallback cache directory setup")
            # The storage backend handles fallback internally
        self.logger.debug(f"Ensured cache directory exists: {self.thumbnails_dir}")

    def ensure_cache_directory(self) -> bool:
        """Ensure cache directory exists, creating if necessary."""
        return self._storage_backend.ensure_directory(self.thumbnails_dir)

    # Thumbnail caching methods - backward compatible interface
    def get_cached_thumbnail(self, show: str, sequence: str, shot: str) -> Path | None:
        """Get path to cached thumbnail if it exists (thread-safe)."""
        with QMutexLocker(self._lock):
            # Periodic validation
            self._run_periodic_validation()

            cache_path = self.thumbnails_dir / show / sequence / f"{shot}_thumb.jpg"
            if cache_path.exists():
                # Track in memory manager if not already tracked
                _ = self._thumbnail_manager.track_item(cache_path)
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
            self.logger.warning(
                f"Source thumbnail path does not exist: {source_path_obj}"
            )
            return None

        # Validate parameters
        if not all([show, sequence, shot]):
            error_msg = "Missing required parameters for thumbnail caching"
            self.logger.error(error_msg)
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

        with QMutexLocker(self._lock):
            # Check if already being loaded
            if cache_key in self._active_loaders:
                result = self._active_loaders[cache_key]
                if wait:
                    return result.future.result(timeout)
                return result

            # Check if already cached
            cache_path = self.thumbnails_dir / show / sequence / f"{shot}_thumb.jpg"
            if cache_path.exists():
                self.logger.debug(f"Thumbnail already cached: {cache_path}")
                _ = self._thumbnail_manager.track_item(cache_path)
                return cache_path

            # Check failure tracker
            should_retry, reason = self._thumbnail_manager.should_retry(
                cache_key, source_path_obj
            )
            if not should_retry:
                self.logger.debug(reason)
                return None if wait else None

            # Create result container and track loading
            result = ThumbnailCacheResult()
            self._active_loaders[cache_key] = result

        # Process thumbnail with proper exception handling to prevent memory leaks
        try:
            # Determine processing approach - check Qt availability defensively
            try:
                app = QApplication.instance()
                is_main_thread = (
                    app is not None and QThread.currentThread() == app.thread()
                )
            except (RuntimeError, AttributeError):
                # Qt not initialized or error accessing - treat as background thread
                is_main_thread = False

            if not is_main_thread:
                # Background thread - use async thumbnail caching
                async_result = self._thumbnail_manager.cache_thumbnail_async(
                    source_path_obj, cache_path
                )

                # Wait for result and handle callbacks
                try:
                    if wait:
                        cached_path = async_result.future.result(timeout)
                        result.set_result(cached_path)
                        self._on_thumbnail_loaded(cache_key, cache_path)
                        self._cleanup_loader(cache_key)
                        return cached_path
                    else:
                        # Non-blocking - return the async result directly
                        # Note: caller is responsible for waiting on the future
                        self._cleanup_loader(cache_key)
                        return async_result
                except Exception as e:
                    result.set_error(str(e))
                    self._cleanup_loader(cache_key)
                    return None if wait else result
            else:
                # Main thread - process directly
                success = self._thumbnail_manager.cache_thumbnail_sync(
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
                    self._thumbnail_manager.record_failure(
                        cache_key, error_msg, source_path_obj
                    )
                    self._cleanup_loader(cache_key)
                    return None if wait else result
        except Exception as e:
            # Ensure cleanup happens even on exception to prevent memory leak
            self.logger.error(f"Exception during thumbnail caching: {e}")
            self._cleanup_loader(cache_key)
            # Record failure for exponential backoff
            self._thumbnail_manager.record_failure(cache_key, str(e), source_path_obj)
            # Re-raise to maintain existing error handling behavior
            raise

    def cache_thumbnail_direct(
        self, source_path: Path, show: str, sequence: str, shot: str
    ) -> Path | None:
        """Direct thumbnail caching implementation (backward compatibility)."""
        cache_path = self.thumbnails_dir / show / sequence / f"{shot}_thumb.jpg"

        if self._thumbnail_manager.cache_thumbnail_sync(source_path, cache_path):
            return cache_path
        return None

    def _on_thumbnail_loaded(self, cache_key: str, cache_path: Path) -> None:
        """Handle successful thumbnail loading."""
        # Track in thumbnail manager
        _ = self._thumbnail_manager.track_item(cache_path)

    def _cleanup_loader(self, cache_key: str) -> None:
        """Remove completed loader from tracking."""
        with QMutexLocker(self._lock):
            _ = self._active_loaders.pop(cache_key, None)

    def _run_periodic_validation(self) -> None:
        """Run periodic cache validation."""
        time_since_validation = datetime.now() - self._last_validation_time
        if time_since_validation > timedelta(minutes=self._validation_interval_minutes):
            if self._cache_validator:  # type: ignore[attr-defined]
                self.logger.debug("Running periodic cache validation")
                _ = self._cache_validator.validate_cache(fix_issues=True)  # type: ignore[attr-defined]
            self._last_validation_time = datetime.now()

    # Shot caching methods - delegate to ShotCache
    def get_cached_shots(self) -> list[ShotDict] | None:
        """Get cached shot list if valid."""
        return self._shot_cache.get_cached_data()  # type: ignore[return-value]

    def cache_shots(self, shots: Sequence[Shot] | Sequence[ShotDict]) -> None:
        """Cache shot list to file."""
        _ = self._shot_cache.cache_data(shots)

    # Previous shots caching methods - delegate to ShotCache
    def get_cached_previous_shots(self) -> list[ShotDict] | None:
        """Get cached previous/approved shot list if valid."""
        return self._previous_shots_cache.get_cached_data()  # type: ignore[return-value]

    def cache_previous_shots(self, shots: Sequence[Shot] | Sequence[ShotDict]) -> None:
        """Cache previous/approved shot list to file."""
        _ = self._previous_shots_cache.cache_data(shots)

    # 3DE scene caching methods - delegate to ThreeDECache
    def get_cached_threede_scenes(self) -> list[ThreeDESceneDict] | None:
        """Get cached 3DE scene list if valid."""
        return self._threede_cache.get_cached_data()  # type: ignore[return-value]

    def has_valid_threede_cache(self) -> bool:
        """Check if we have a valid 3DE cache (including valid empty results)."""
        return self._threede_cache.has_valid_cache()

    def cache_threede_scenes(
        self, scenes: list[ThreeDESceneDict], metadata: dict[str, object] | None = None
    ) -> None:
        """Cache 3DE scene list to file with optional metadata."""
        _ = self._threede_cache.cache_data(scenes, metadata)

    # Generic data caching methods for backward compatibility
    def cache_data(self, key: str, data: object) -> None:
        """Cache generic data with a key (for backward compatibility).

        Args:
            key: Cache key identifier
            data: Data to cache
        """
        if key == "previous_shots":
            # Type-safe casting: assume caller passes correct type for previous_shots
            self.cache_previous_shots(data)  # type: ignore[arg-type]
        else:
            # For other generic data, use storage backend directly
            cache_file = self.cache_dir / f"{key}.json"
            # Type-safe casting: assume data is dict for JSON serialization
            _ = self._storage_backend.write_json(cache_file, data)  # type: ignore[arg-type]

    def get_cached_data(self, key: str) -> object | None:
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
    def cache_exr_thumbnails_batch(
        self,
        exr_files: list[tuple[Path, str, str, str]],
    ) -> dict[str, Path | None]:
        """Process multiple EXR thumbnails asynchronously without blocking UI.

        This method uses AsyncEXRProcessor to handle multiple EXR files in parallel,
        preventing UI freezes that occur with synchronous processing.

        Args:
            exr_files: List of tuples (source_path, show, sequence, shot)

        Returns:
            Dictionary mapping shot keys to cached thumbnail paths
        """
        self.logger.info(f"Starting batch EXR processing for {len(exr_files)} files")

        # Process files individually using thumbnail manager
        results: dict[str, Path | None] = {}

        for source_path, show, sequence, shot in exr_files:
            cache_key = f"{show}_{sequence}_{shot}"
            cache_path = self.thumbnails_dir / show / sequence / f"{shot}_thumb.jpg"

            # Use async processing from thumbnail manager
            thumbnail_result = self._thumbnail_manager.cache_thumbnail_async(
                source_path, cache_path
            )

            if thumbnail_result and thumbnail_result.wait_for_completion(timeout_ms=30000):
                if thumbnail_result.cache_path:
                    results[cache_key] = thumbnail_result.cache_path
                    self.logger.debug(f"Processed EXR thumbnail: {cache_key}")
                else:
                    results[cache_key] = None
                    self.logger.warning(f"Failed to process EXR thumbnail: {cache_key}")
            else:
                results[cache_key] = None
                self.logger.warning(f"Timeout processing EXR thumbnail: {cache_key}")

        self.logger.info("Batch EXR processing completed")
        return results

    def get_memory_usage(self) -> dict[str, float | int]:
        """Get current cache memory usage statistics (backward compatible)."""
        stats = self._thumbnail_manager.get_usage_stats()
        total_bytes = cast("int", stats.get("total_size_mb", 0) * 1024 * 1024)

        # Return old format for backward compatibility
        return {
            "total_bytes": total_bytes,
            "total_mb": stats.get("total_size_mb", 0.0),
            "max_mb": stats.get("memory_limit_mb", 0.0),
            "usage_percent": stats.get("usage_percent", 0.0),
            "thumbnail_count": stats.get("total_items", 0),
        }

    def validate_cache(self) -> dict[str, object]:
        """Validate cache consistency and fix issues (backward compatible)."""
        # Use storage backend validation with thumbnail manager
        result = self._storage_backend.validate_cache(  # type: ignore[call-arg]
            self.thumbnails_dir, memory_manager=self._thumbnail_manager, fix_issues=True
        )
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

    def clear_cache(self) -> None:
        """Clear all cached data."""
        with QMutexLocker(self._lock):
            # Clear thumbnail manager (handles memory and failure tracking)
            self._thumbnail_manager.clear_cache()

            # Clear data caches
            _ = self._shot_cache.clear_cache()
            _ = self._threede_cache.clear_cache()

            # Clear active loaders
            self._active_loaders.clear()

            # Remove thumbnail directory
            # Standard library imports
            import shutil

            if self.thumbnails_dir.exists():
                try:
                    shutil.rmtree(self.thumbnails_dir, ignore_errors=True)
                    self.logger.info("Cleared thumbnail cache directory")
                except OSError as e:
                    # Log but don't raise - clearing cache is not critical
                    self.logger.error(f"Failed to clear thumbnail directory: {e}")

            # Recreate directory
            self._ensure_cache_dirs()

            self.logger.info("Cache cleared successfully")

    # Failure tracking methods - delegate to ThumbnailManager
    def clear_failed_attempts(self, cache_key: str | None = None) -> None:
        """Clear failed attempts to allow immediate retry."""
        self._thumbnail_manager.clear_failure(cache_key)  # type: ignore[arg-type]

    def get_failed_attempts_status(self) -> dict[str, dict[str, object]]:
        """Get current status of failed attempts for debugging."""
        return self._thumbnail_manager.get_failure_status()

    def _evict_old_thumbnails(self) -> int:
        """Backward compatibility method for evicting old thumbnails."""
        # Not applicable - eviction is automatic in ThumbnailManager
        return 0

    # Shutdown method for graceful cleanup
    def shutdown(self) -> None:
        """Gracefully shutdown the cache manager."""
        self.logger.info("CacheManager shutting down...")

        with QMutexLocker(self._lock):
            try:
                # Validate and fix any cache inconsistencies using storage backend
                validation_result = self._storage_backend.validate_cache(  # type: ignore[call-arg]
                    self.thumbnails_dir,
                    memory_manager=self._thumbnail_manager,
                    fix_issues=True,
                )
                if not validation_result.get("valid", False):
                    self.logger.info(
                        f"Fixed {validation_result.get('issues_fixed', 0)} cache issues during shutdown"
                    )

                # Clear thumbnail manager (handles memory and failure tracking)
                failed_count = len(self._thumbnail_manager._failures)  # type: ignore[attr-defined]
                self._thumbnail_manager.clear_cache()
                if failed_count > 0:
                    self.logger.debug(
                        f"Cleared {failed_count} failed attempts during shutdown"
                    )

                # Clear active loaders
                self._active_loaders.clear()

                self.logger.info("CacheManager shutdown complete")

            except (OSError, CacheError) as e:
                self.logger.error(f"Error during cache manager shutdown: {e}")

    def set_memory_limit(self, max_memory_mb: int) -> None:
        """Set maximum memory limit for cache in megabytes.

        Args:
            max_memory_mb: Maximum memory in megabytes
        """
        # Use the public method to set memory limit on thumbnail manager
        self._thumbnail_manager.set_memory_limit(max_memory_mb)
        self.logger.info(f"Cache memory limit set to {max_memory_mb} MB")

    def _on_memory_limit_changed(self, new_limit_mb: int) -> None:
        """Handle unified cache config memory limit changes.

        Args:
            new_limit_mb: New memory limit in MB
        """
        self._thumbnail_manager.set_memory_limit(new_limit_mb)
        self.logger.info(
            f"Cache memory limit updated to {new_limit_mb}MB via unified config"
        )

    def _on_expiry_time_changed(self, new_expiry_minutes: int) -> None:
        """Handle unified cache config expiry time changes.

        Args:
            new_expiry_minutes: New expiry time in minutes
        """
        # Update all cache components with new expiry time
        self._shot_cache.set_expiry_minutes(new_expiry_minutes)
        self._threede_cache.set_expiry_minutes(new_expiry_minutes)
        self._previous_shots_cache.set_expiry_minutes(new_expiry_minutes)
        self.logger.info(
            f"Cache expiry time updated to {new_expiry_minutes} minutes via unified config"
        )

    def set_expiry_minutes(self, expiry_minutes: int) -> None:
        """Set cache expiry time in minutes.

        Args:
            expiry_minutes: Cache expiry time in minutes
        """
        # Update expiry for both shot and 3DE caches using their public methods
        self._shot_cache.set_expiry_minutes(expiry_minutes)
        self._threede_cache.set_expiry_minutes(expiry_minutes)

        self.logger.info(f"Cache expiry set to {expiry_minutes} minutes")

    # ================================================================
    # Test-Specific Accessor Methods
    # ================================================================
    # WARNING: These methods are for testing purposes ONLY.
    # They provide controlled access to private attributes for tests.
    # DO NOT use these methods in production code.

    @property
    def test_storage_backend(self) -> StorageBackend:
        """Test-only access to storage backend."""
        return self._storage_backend

    @property
    def test_thumbnail_manager(self) -> ThumbnailManager:
        """Test-only access to thumbnail manager."""
        return self._thumbnail_manager

    @property
    def test_shot_cache(self) -> UnifiedCache[CacheableData]:
        """Test-only access to shot cache."""
        return self._shot_cache

    @property
    def test_threede_cache(self) -> UnifiedCache[CacheableData]:
        """Test-only access to 3DE cache."""
        return self._threede_cache

    # Legacy test properties for backward compatibility
    @property
    def test_failure_tracker(self) -> ThumbnailManager:
        """Test-only access to failure tracker (now handled by thumbnail manager)."""
        return self._thumbnail_manager

    @property
    def test_thumbnail_processor(self) -> ThumbnailManager:
        """Test-only access to thumbnail processor (now handled by thumbnail manager)."""
        return self._thumbnail_manager

    @property
    def test_memory_manager(self) -> ThumbnailManager:
        """Test-only access to memory manager (now handled by thumbnail manager)."""
        return self._thumbnail_manager

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
    def test_lock(self) -> QMutex:
        """Test-only access to the coordination lock.

        Returns:
            The QMutex used for thread-safe coordination.

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
        cache_manager: CacheManager,
        source_path: Path | str,
        show: str,
        sequence: str,
        shot: str,
        result: dict[str, object] | None = None,
    ) -> None:
        """Initialize with original constructor signature."""
        super().__init__()
        # Local application imports
        from cache.thumbnail_manager import ThumbnailManager

        # Note: The following were computed in the original but not used in this
        # backward compatibility wrapper. They're removed to fix unused variable warnings.
        # - cache_path: Path to cached thumbnail
        # - source_path_obj: Normalized source path
        # - result_obj: Converted result object

        self._loader = ThumbnailManager()

        # Expose the same interface
        self.cache_manager = cache_manager
        self.source_path = source_path
        self.show = show
        self.sequence = sequence
        self.shot = shot
        self.signals = self._loader.signals  # type: ignore[attr-defined]
        self.result = self._loader.result  # type: ignore[attr-defined]

    @override
    def run(self) -> None:
        """Run the thumbnail processing."""
        return self._loader.run()  # type: ignore[attr-defined]

    @override
    def setAutoDelete(self, autoDelete: bool) -> None:
        """Set auto delete flag."""
        super().setAutoDelete(autoDelete)
        self._loader.setAutoDelete(autoDelete)  # type: ignore[attr-defined]


# Maintain backward compatibility by re-exporting classes
__all__ = ["CacheManager", "ThumbnailCacheResult", "ThumbnailCacheLoader"]
