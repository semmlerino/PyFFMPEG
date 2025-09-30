"""Unified thumbnail management combining processing, loading, memory management, and failure tracking.

This module consolidates the functionality of:
- ThumbnailProcessor: Multi-format image processing (Qt/PIL/OpenEXR)
- ThumbnailLoader: Async QRunnable-based loading
- MemoryManager: LRU cache with memory limits
- FailureTracker: Simplified failure tracking with exponential backoff

The unified ThumbnailManager provides a single interface for all thumbnail operations
while maintaining full Qt threading support and signal emissions.
"""

from __future__ import annotations

# Standard library imports
import gc
import heapq
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

# Third-party imports
from PySide6.QtCore import (
    QMutex,
    QMutexLocker,
    QObject,
    QRunnable,
    Qt,
    QThreadPool,
    QWaitCondition,
    Signal,
)
from PySide6.QtGui import QImage

# Local application imports
from config import Config, ThreadingConfig
from error_handling_mixin import ErrorHandlingMixin
from logging_mixin import LoggingMixin
from runnable_tracker import get_tracker

# Import sip at module level to avoid threading issues
try:
    # Third-party imports
    import sip

    SIP_AVAILABLE = True
except ImportError:
    SIP_AVAILABLE = False
    sip = None

if TYPE_CHECKING:
    # Third-party imports
    from PIL import Image as PIL


@dataclass
class CacheEntry:
    """Entry for cache eviction heap with LRU tracking."""

    access_time: float
    path: str
    size_bytes: int

    def __lt__(self, other: CacheEntry) -> bool:
        """Compare by access time for heap ordering (oldest first)."""
        return self.access_time < other.access_time


@dataclass
class FailureRecord:
    """Record of thumbnail processing failures for backoff tracking."""

    path: str
    failure_count: int
    last_failure_time: float
    next_retry_time: float
    error_message: str = ""


class ThumbnailCacheResult:
    """Result container for async thumbnail caching operations.

    This class provides thread-safe result handling for background
    thumbnail processing with synchronization support.
    """

    def __init__(self) -> None:
        """Initialize result container."""
        super().__init__()
        self.future: Future[Path | None] = Future()
        self.cache_path: Path | None = None
        self.error: str | None = None
        self._complete_condition = QWaitCondition()
        self._completed_mutex = QMutex()
        self._is_complete = False

    def set_result(self, cache_path: Path) -> None:
        """Set successful result (thread-safe, prevents multiple completions).

        Args:
            cache_path: Path to the cached thumbnail
        """
        with QMutexLocker(self._completed_mutex):
            if self._is_complete:
                return  # Already completed, ignore
            self._is_complete = True

        self.cache_path = cache_path
        try:
            self.future.set_result(cache_path)
        except Exception:
            pass  # Future already completed
        self._complete_condition.wakeAll()

    def set_error(self, error: str) -> None:
        """Set error result (thread-safe, prevents multiple completions).

        Args:
            error: Error message describing the failure
        """
        with QMutexLocker(self._completed_mutex):
            if self._is_complete:
                return  # Already completed, ignore
            self._is_complete = True

        self.error = error
        try:
            self.future.set_exception(RuntimeError(error))
        except Exception:
            pass  # Future already completed
        self._complete_condition.wakeAll()

    def wait_for_completion(self, timeout_ms: int = 30000) -> bool:
        """Wait for completion with timeout.

        Args:
            timeout_ms: Timeout in milliseconds

        Returns:
            True if completed within timeout
        """
        with QMutexLocker(self._completed_mutex):
            if self._is_complete:
                return True
            return self._complete_condition.wait(self._completed_mutex, timeout_ms)

    @property
    def is_complete(self) -> bool:
        """Check if result is complete."""
        with QMutexLocker(self._completed_mutex):
            return self._is_complete


class ThumbnailTask(QRunnable):
    """QRunnable task for background thumbnail processing."""

    def __init__(
        self,
        source_path: Path,
        cache_path: Path,
        result: ThumbnailCacheResult,
        manager: ThumbnailManager,
    ) -> None:
        """Initialize thumbnail task.

        Args:
            source_path: Source image path
            cache_path: Target cache path
            result: Result container for async communication
            manager: ThumbnailManager instance for processing
        """
        super().__init__()
        self.source_path = source_path
        self.cache_path = cache_path
        self.result = result
        self.manager = manager

    def run(self) -> None:
        """Execute thumbnail processing task."""
        # Register task with tracker
        tracker = get_tracker()
        tracker.register(
            self,
            metadata={
                "type": "thumbnail_processing",
                "source": str(self.source_path),
                "cache": str(self.cache_path),
            },
        )

        try:
            # Process thumbnail using manager's processing logic
            success = self.manager._process_thumbnail_sync(
                self.source_path, self.cache_path
            )

            if success and self.cache_path.exists():
                self.result.set_result(self.cache_path)
            else:
                self.result.set_error(
                    f"Failed to process thumbnail: {self.source_path}"
                )

        except Exception as e:
            self.result.set_error(f"Thumbnail processing error: {e}")


class ThumbnailManagerSignals(QObject):
    """Signal container for ThumbnailManager backward compatibility."""
    loaded = Signal(str, str, str, Path)  # show, sequence, shot, path
    failed = Signal(str, str, str, str)  # show, sequence, shot, error


class ThumbnailManager(QObject, ErrorHandlingMixin, LoggingMixin):
    """Unified thumbnail management system.

    Combines thumbnail processing, async loading, memory management,
    and failure tracking into a single cohesive system with Qt integration.
    """

    # Signals for Qt integration
    thumbnail_ready = Signal(Path, Path)  # source_path, cache_path
    thumbnail_failed = Signal(Path, str)  # source_path, error_message
    memory_pressure = Signal(int)  # usage_percent

    def __init__(
        self,
        thumbnail_size: int | None = None,
        max_memory_mb: int | None = None,
        thread_pool: QThreadPool | None = None,
        base_retry_delay_minutes: int = 5,
        max_retry_delay_minutes: int = 120,
        retry_multiplier: int = 3,
        max_failed_attempts: int = 4,
        cleanup_age_hours: int = 24,
    ) -> None:
        """Initialize unified thumbnail manager.

        Args:
            thumbnail_size: Size in pixels for square thumbnails
            max_memory_mb: Maximum memory limit in MB
            thread_pool: QThreadPool for async operations
            base_retry_delay_minutes: Base delay for failure retry
            max_retry_delay_minutes: Maximum delay for failure retry
            retry_multiplier: Multiplier for exponential backoff
            max_failed_attempts: Maximum failed attempts before max delay
            cleanup_age_hours: Age threshold for cleaning up old failures
        """
        super().__init__()

        # Backward compatibility: Create signals object for old API
        self.signals = ThumbnailManagerSignals()

        # Core configuration
        self._thumbnail_size = thumbnail_size or Config.CACHE_THUMBNAIL_SIZE
        self._max_memory_bytes = (
            (max_memory_mb or ThreadingConfig.CACHE_MAX_MEMORY_MB) * 1024 * 1024
        )
        self._thread_pool = thread_pool or QThreadPool.globalInstance()

        # Memory management (LRU cache)
        self._lock = threading.RLock()
        self._memory_usage_bytes = 0
        self._cached_items: dict[str, int] = {}  # path -> size in bytes
        self._access_times: dict[str, float] = {}  # path -> last access time
        self._eviction_heap: list[CacheEntry] = []  # Heap for O(log n) eviction
        self._heap_dirty = False  # Flag to rebuild heap when needed
        self._auto_evict = True  # Allow disabling auto-eviction for testing

        # Failure tracking (simplified)
        self._failures: dict[str, FailureRecord] = {}
        self._retry_delay_minutes = base_retry_delay_minutes
        self._max_retry_delay_minutes = max_retry_delay_minutes
        self._retry_multiplier = retry_multiplier
        self._max_failed_attempts = max_failed_attempts
        self._cleanup_age_hours = cleanup_age_hours

        # Processing configuration
        self._heavy_formats = getattr(
            Config, "THUMBNAIL_FALLBACK_EXTENSIONS", [".exr", ".tiff", ".tif"]
        )
        self._qt_lock = threading.Lock()

        self.logger.info(
            f"ThumbnailManager initialized: {self._thumbnail_size}px, "
            f"{max_memory_mb or ThreadingConfig.CACHE_MAX_MEMORY_MB}MB limit"
        )

    # ============= Public API =============

    def cache_thumbnail_async(
        self, source_path: Path, cache_path: Path
    ) -> ThumbnailCacheResult:
        """Cache thumbnail asynchronously using QRunnable.

        Args:
            source_path: Source image path
            cache_path: Target cache path

        Returns:
            ThumbnailCacheResult for tracking completion
        """
        # Check if should retry based on failure tracking
        if not self._should_retry(source_path):
            result = ThumbnailCacheResult()
            result.set_error("Too many recent failures - backoff active")
            return result

        # Create task and submit to thread pool
        result = ThumbnailCacheResult()
        task = ThumbnailTask(source_path, cache_path, result, self)

        try:
            self._thread_pool.start(task)  # type: ignore[reportUnknownMemberType]
        except Exception as e:
            result.set_error(f"Failed to start thumbnail task: {e}")

        return result

    def cache_thumbnail_sync(
        self, source_path: Path, cache_path: Path, max_dimension: int | None = None
    ) -> bool:
        """Cache thumbnail synchronously.

        Args:
            source_path: Source image path
            cache_path: Target cache path
            max_dimension: Maximum allowed image dimension (optional)

        Returns:
            True if thumbnail was created successfully
        """
        if not self._should_retry(source_path):
            return False

        return self._process_thumbnail_sync(source_path, cache_path, max_dimension)

    def process_thumbnail(
        self, source_path: Path, cache_path: Path, max_dimension: int | None = None
    ) -> bool:
        """Process thumbnail (backward compatibility alias).

        Args:
            source_path: Source image path
            cache_path: Target cache path
            max_dimension: Maximum allowed image dimension (optional)

        Returns:
            True if successful, False otherwise
        """
        return self.cache_thumbnail_sync(source_path, cache_path, max_dimension)

    def track_item(
        self, file_path: Path, size_bytes: int = None, force_update: bool = False
    ) -> bool:
        """Track item in memory manager.

        Args:
            file_path: Path to file to track
            size_bytes: Size in bytes (if None, read from filesystem)
            force_update: Update size even if already tracked

        Returns:
            True if item was tracked successfully
        """
        with self._lock:
            file_str = str(file_path)

            if file_str in self._cached_items and not force_update:
                # Update access time
                self._access_times[file_str] = time.time()
                return True

            try:
                if size_bytes is None:
                    size_bytes = file_path.stat().st_size
                self._add_item(file_str, size_bytes)
                return True
            except OSError:
                return False

    def is_item_tracked(self, file_path: Path) -> bool:
        """Check if item is being tracked.

        Args:
            file_path: Path to check

        Returns:
            True if item is tracked
        """
        with self._lock:
            return str(file_path) in self._cached_items

    def evict_item(self, file_path: Path) -> bool:
        """Remove item from tracking.

        Args:
            file_path: Path to remove

        Returns:
            True if item was removed
        """
        with self._lock:
            file_str = str(file_path)
            if file_str in self._cached_items:
                size_bytes = self._cached_items.pop(file_str)
                self._access_times.pop(file_str, None)
                self._memory_usage_bytes -= size_bytes
                self._heap_dirty = True
                return True
            return False

    def get_usage_stats(self) -> dict[str, Any]:
        """Get memory usage statistics.

        Returns:
            Dictionary with usage statistics
        """
        with self._lock:
            total_items = len(self._cached_items)
            avg_size_kb = (
                (self._memory_usage_bytes / total_items / 1024)
                if total_items > 0
                else 0
            )
            usage_percent = (
                (self._memory_usage_bytes / self._max_memory_bytes) * 100
                if self._max_memory_bytes > 0
                else 0
            )

            return {
                "total_items": total_items,
                "total_size_mb": self._memory_usage_bytes / (1024 * 1024),
                "usage_percent": min(usage_percent, 100),
                "average_item_kb": avg_size_kb,
                "memory_limit_mb": self._max_memory_bytes / (1024 * 1024),
            }

    def set_memory_limit(self, max_memory_mb: int) -> None:
        """Set memory limit and trigger eviction if needed.

        Args:
            max_memory_mb: New memory limit in MB
        """
        with self._lock:
            self._max_memory_bytes = max_memory_mb * 1024 * 1024
            self._enforce_memory_limit()

    def clear_cache(self) -> int:
        """Clear all tracked items.

        Returns:
            Number of items cleared
        """
        with self._lock:
            count = len(self._cached_items)
            self._cached_items.clear()
            self._access_times.clear()
            self._eviction_heap.clear()
            self._memory_usage_bytes = 0
            self._heap_dirty = False
            return count

    def record_failure(
        self, cache_key: str | Path, error_message: str, source_path: Path | None = None
    ) -> None:
        """Record thumbnail processing failure for backoff tracking.

        Args:
            cache_key: Unique key for this operation (string or Path)
            error_message: Error message describing the failure
            source_path: Optional source path for additional context
        """
        with self._lock:
            # Convert cache_key to string for consistent dictionary keys
            key_str = str(cache_key)
            now = datetime.now().timestamp()

            # If source_path not provided and cache_key is a Path, use it
            if source_path is None and isinstance(cache_key, Path):
                source_path = cache_key

            if key_str in self._failures:
                record = self._failures[key_str]
                record.failure_count += 1
                record.last_failure_time = now
                record.error_message = error_message  # Update error message
            else:
                record = FailureRecord(
                    path=str(source_path) if source_path else cache_key,
                    failure_count=1,
                    last_failure_time=now,
                    next_retry_time=0.0,
                    error_message=error_message,
                )
                self._failures[key_str] = record

            # Calculate next retry time with exponential backoff
            delay_minutes = min(
                self._retry_delay_minutes
                * (self._retry_multiplier ** (record.failure_count - 1)),
                self._max_retry_delay_minutes,
            )
            record.next_retry_time = now + (delay_minutes * 60)

            self.logger.debug(
                f"Recorded failure for {source_path} (count: {record.failure_count}, "
                f"next retry in {delay_minutes}min)"
            )

    def clear_failure(self, source_path: Path) -> None:
        """Clear failure record for successful processing.

        Args:
            source_path: Path that was successfully processed
        """
        with self._lock:
            self._failures.pop(str(source_path), None)

    # ============= FailureTracker Compatibility Methods =============

    def should_retry(
        self, cache_key: str, source_path: Path | None = None
    ) -> tuple[bool, str]:
        """Check if should retry processing based on failure tracking.

        Args:
            cache_key: Cache key for the operation
            source_path: Optional source path for more detailed messaging

        Returns:
            Tuple of (should_retry, reason)
        """
        with self._lock:
            if cache_key not in self._failures:
                return True, "No previous failures recorded"

            failure = self._failures[cache_key]
            current_time = datetime.now().timestamp()

            if current_time < failure.next_retry_time:
                # Still in backoff period
                display_path = source_path.name if source_path else cache_key
                minutes_left = (failure.next_retry_time - current_time) / 60
                return (
                    False,
                    f"Skipping recently failed operation for {display_path} (attempt {failure.failure_count}, retry in {minutes_left:.1f} min)",
                )
            else:
                return (
                    True,
                    f"Retry allowed after {failure.failure_count} previous attempts",
                )

    def clear_failures(self, cache_key: str | None = None) -> None:
        """Clear failure records.

        Args:
            cache_key: Specific key to clear, or None to clear all
        """
        with self._lock:
            if cache_key is None:
                self._failures.clear()
            else:
                self._failures.pop(cache_key, None)

    def cleanup_old_failures(self) -> int:
        """Clean up old failure records based on age threshold.

        Returns:
            Number of records cleaned up
        """
        with self._lock:
            current_time = datetime.now().timestamp()
            cleanup_threshold = (
                self._cleanup_age_hours * 3600
            )  # Convert hours to seconds

            keys_to_remove = []
            for cache_key, failure in self._failures.items():
                age = current_time - failure.last_failure_time
                if age > cleanup_threshold:
                    keys_to_remove.append(cache_key)

            for key in keys_to_remove:
                self._failures.pop(key, None)

            return len(keys_to_remove)

    def get_failure_status(self) -> dict[str, dict[str, Any]]:
        """Get failure status for all tracked items.

        Returns:
            Dictionary mapping cache keys to failure information
        """
        import datetime

        with self._lock:
            status = {}
            for cache_key, failure in self._failures.items():
                status[cache_key] = {
                    "source_path": failure.path,
                    "attempts": failure.failure_count,
                    "last_failure": datetime.datetime.fromtimestamp(
                        failure.last_failure_time
                    ),
                    "next_retry": datetime.datetime.fromtimestamp(
                        failure.next_retry_time
                    ),
                    "error": failure.error_message,
                }
            return status.copy()  # Return copy for thread safety

    def get_failure_count(self) -> int:
        """Get total number of tracked failures.

        Returns:
            Number of failed items being tracked
        """
        with self._lock:
            return len(self._failures)

    def __len__(self) -> int:
        """Return number of tracked failures."""
        return self.get_failure_count()

    def __contains__(self, cache_key: str) -> bool:
        """Check if cache key has recorded failures."""
        with self._lock:
            return cache_key in self._failures

    def __repr__(self) -> str:
        """Return string representation of failure tracker state."""
        with self._lock:
            max_delay_min = self._max_retry_delay_minutes
            failure_count = len(self._failures)
            return f"ThumbnailManager(failures={failure_count}, max_delay={max_delay_min}min)"

    # ============= Internal Processing Methods =============

    def _process_thumbnail_sync(
        self, source_path: Path, cache_path: Path, max_dimension: int | None = None
    ) -> bool:
        """Internal synchronous thumbnail processing.

        Args:
            source_path: Source image path
            cache_path: Target cache path
            max_dimension: Maximum allowed image dimension (optional)

        Returns:
            True if processing succeeded
        """
        try:
            if not source_path or not source_path.exists():
                self.logger.warning(f"Source image does not exist: {source_path}")
                self.record_failure(source_path, "Source file not found")
                return False

            # Validate image dimensions if max_dimension is specified
            if max_dimension is not None:
                try:
                    from PySide6.QtGui import QImageReader

                    reader = QImageReader(str(source_path))
                    size = reader.size()
                    if size.width() > max_dimension or size.height() > max_dimension:
                        self.logger.warning(
                            f"Image {source_path} exceeds max dimension {max_dimension}"
                        )
                        return False
                except Exception as e:
                    self.logger.warning(
                        f"Could not validate dimensions for {source_path}: {e}"
                    )
                    return False

            # Create cache directory
            try:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
            except (OSError, PermissionError) as e:
                error_msg = f"Failed to create cache directory: {e}"
                self.logger.error(error_msg)
                self.record_failure(source_path, error_msg)
                return False

            # Analyze source file and choose processing strategy
            file_info = self._analyze_source_file(source_path)

            success = False
            if file_info["use_pil"]:
                success = self._process_with_pil(source_path, cache_path, file_info)
            else:
                success = self._process_with_qt(source_path, cache_path, file_info)

            if success:
                # Track in memory manager
                self.track_item(cache_path)
                self.clear_failure(source_path)
                self.thumbnail_ready.emit(source_path, cache_path)
                return True
            else:
                self.record_failure(source_path, "Processing failed")
                self.thumbnail_failed.emit(source_path, "Processing failed")
                return False

        except MemoryError:
            error_msg = f"Out of memory processing: {source_path}"
            self.logger.error(error_msg)
            self.record_failure(source_path, error_msg)
            self.thumbnail_failed.emit(source_path, error_msg)
            return False
        except Exception as e:
            error_msg = f"Unexpected error processing {source_path}: {e}"
            self.logger.exception(error_msg)
            self.record_failure(source_path, error_msg)
            self.thumbnail_failed.emit(source_path, error_msg)
            return False
        finally:
            # Force garbage collection for large images
            gc.collect()

    def _analyze_source_file(self, source_path: Path) -> dict[str, Any]:
        """Analyze source file to determine processing strategy.

        Args:
            source_path: Path to source image

        Returns:
            Dictionary with file analysis results
        """
        try:
            file_size_mb = source_path.stat().st_size / (1024 * 1024)
        except OSError:
            file_size_mb = 0

        suffix_lower = source_path.suffix.lower()
        is_heavy_format = suffix_lower in self._heavy_formats

        # Use PIL for heavy formats or large files
        use_pil = is_heavy_format and file_size_mb > 1  # Threshold for PIL usage

        return {
            "file_size_mb": file_size_mb,
            "suffix_lower": suffix_lower,
            "is_heavy_format": is_heavy_format,
            "use_pil": use_pil,
        }

    def _process_with_qt(
        self, source_path: Path, cache_path: Path, file_info: dict[str, Any]
    ) -> bool:
        """Process image using Qt backend.

        Args:
            source_path: Source image path
            cache_path: Output thumbnail path
            file_info: File analysis results

        Returns:
            True if processing succeeded
        """
        with self._qt_lock:
            try:
                # Load image with Qt
                qimage = QImage(str(source_path))
                if qimage.isNull():
                    self.logger.warning(f"Qt failed to load image: {source_path}")
                    return False

                # Scale to thumbnail size
                scaled = qimage.scaled(
                    self._thumbnail_size,
                    self._thumbnail_size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )

                # Save thumbnail
                success = scaled.save(str(cache_path), "JPEG", 85)
                if success:
                    self.logger.debug(f"Qt created thumbnail: {cache_path}")
                    return True
                else:
                    self.logger.warning(f"Qt failed to save thumbnail: {cache_path}")
                    return False

            except Exception as e:
                self.logger.error(f"Qt processing error for {source_path}: {e}")
                return False

    def _process_with_pil(
        self, source_path: Path, cache_path: Path, file_info: dict[str, Any]
    ) -> bool:
        """Process image using PIL backend with multi-format support.

        Args:
            source_path: Source image path
            cache_path: Output thumbnail path
            file_info: File analysis results

        Returns:
            True if processing succeeded
        """
        try:
            pil_image = self._load_image_with_pil(source_path, file_info)
            if pil_image is None:
                return False

            # Create thumbnail
            pil_image.thumbnail((self._thumbnail_size, self._thumbnail_size))

            # Convert to RGB if needed
            if pil_image.mode not in ("RGB", "L"):
                pil_image = pil_image.convert("RGB")

            # Save as JPEG
            pil_image.save(cache_path, "JPEG", quality=85)
            self.logger.debug(f"PIL created thumbnail: {cache_path}")
            return True

        except Exception as e:
            self.logger.error(f"PIL processing error for {source_path}: {e}")
            return False

    def _load_image_with_pil(
        self, source_path: Path, file_info: dict[str, Any]
    ) -> PIL | None:
        """Load image using PIL with format-specific handling.

        Args:
            source_path: Source image path
            file_info: File analysis results

        Returns:
            PIL Image object or None if failed
        """
        try:
            # Try importing PIL
            from PIL import Image as PILImage

            # Handle EXR files specially
            if file_info["suffix_lower"] == ".exr":
                return self._load_exr_with_pil(source_path)
            else:
                return PILImage.open(source_path)

        except ImportError:
            self.logger.warning("PIL not available for heavy format processing")
            return None
        except Exception as e:
            self.logger.error(f"PIL failed to load {source_path}: {e}")
            return None

    def _load_exr_with_pil(self, source_path: Path) -> PIL | None:
        """Load EXR file using specialized handling.

        Args:
            source_path: EXR file path

        Returns:
            PIL Image object or None if failed
        """
        try:
            # Try OpenEXR first, then imageio, then PIL
            try:
                import Imath
                import numpy as np
                import OpenEXR
                from PIL import Image as PILImage

                exr_file = OpenEXR.InputFile(str(source_path))
                header = exr_file.header()

                dw = header["dataWindow"]
                width = dw.max.x - dw.min.x + 1
                height = dw.max.y - dw.min.y + 1

                # Read RGB channels
                FLOAT = Imath.PixelType(Imath.PixelType.FLOAT)
                redstr = exr_file.channel("R", FLOAT)
                greenstr = exr_file.channel("G", FLOAT)
                bluestr = exr_file.channel("B", FLOAT)

                # Convert to numpy arrays
                red = np.frombuffer(redstr, dtype=np.float32).reshape(height, width)
                green = np.frombuffer(greenstr, dtype=np.float32).reshape(height, width)
                blue = np.frombuffer(bluestr, dtype=np.float32).reshape(height, width)

                # Stack and convert to 8-bit
                rgb = np.dstack((red, green, blue))
                rgb = np.clip(rgb * 255, 0, 255).astype(np.uint8)

                return PILImage.fromarray(rgb)

            except ImportError:
                # Fallback to imageio
                import imageio.v3 as iio
                from PIL import Image as PILImage

                image_data = iio.imread(source_path)
                if image_data.dtype != np.uint8:
                    image_data = np.clip(image_data * 255, 0, 255).astype(np.uint8)

                return PILImage.fromarray(image_data)

        except Exception as e:
            self.logger.error(f"Failed to load EXR {source_path}: {e}")
            return None

    def _load_exr_image(self, source_path: Path) -> PIL | None:
        """Load EXR image with fallback through multiple backends.

        Args:
            source_path: EXR file path

        Returns:
            PIL Image object or None if all backends fail
        """
        # Try OpenEXR backend first
        try:
            result = self._load_exr_with_openexr(source_path)
            if result is not None:
                return result
        except Exception:
            pass

        # Try system tools fallback
        try:
            result = self._load_exr_with_system_tools(source_path)
            if result is not None:
                return result
        except Exception:
            pass

        # Try imageio fallback
        try:
            result = self._load_exr_with_imageio(source_path)
            if result is not None:
                return result
        except Exception:
            pass

        return None

    def _load_exr_with_openexr(self, source_path: Path) -> PIL | None:
        """Load EXR using OpenEXR library.

        Args:
            source_path: EXR file path

        Returns:
            PIL Image object or None if failed
        """
        try:
            import Imath
            import numpy as np
            import OpenEXR
            from PIL import Image as PILImage

            exr_file = OpenEXR.InputFile(str(source_path))
            header = exr_file.header()

            dw = header["dataWindow"]
            width = dw.max.x - dw.min.x + 1
            height = dw.max.y - dw.min.y + 1

            # Read RGB channels
            FLOAT = Imath.PixelType(Imath.PixelType.FLOAT)
            redstr = exr_file.channel("R", FLOAT)
            greenstr = exr_file.channel("G", FLOAT)
            bluestr = exr_file.channel("B", FLOAT)

            # Convert to numpy arrays
            red = np.frombuffer(redstr, dtype=np.float32).reshape((height, width))
            green = np.frombuffer(greenstr, dtype=np.float32).reshape((height, width))
            blue = np.frombuffer(bluestr, dtype=np.float32).reshape((height, width))

            # Stack channels and convert to 8-bit
            image_data = np.stack([red, green, blue], axis=2)
            image_data = np.clip(image_data * 255, 0, 255).astype(np.uint8)

            return PILImage.fromarray(image_data)

        except Exception as e:
            self.logger.debug(f"OpenEXR backend failed for {source_path}: {e}")
            raise

    def _load_exr_with_system_tools(self, source_path: Path) -> PIL | None:
        """Load EXR using system tools (ImageMagick).

        Args:
            source_path: EXR file path

        Returns:
            PIL Image object or None if failed
        """
        import subprocess
        import tempfile

        from PIL import Image as PILImage

        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                temp_path = temp_file.name

            # Use ImageMagick convert command
            cmd = ["convert", str(source_path), temp_path]
            result = subprocess.run(cmd, capture_output=True, timeout=30)

            if result.returncode == 0 and Path(temp_path).exists():
                image = PILImage.open(temp_path)
                image.load()  # Ensure image is loaded before temp file cleanup
                try:
                    Path(temp_path).unlink()  # Clean up temp file
                except FileNotFoundError:
                    pass  # File already cleaned up
                return image
            else:
                try:
                    if Path(temp_path).exists():
                        Path(temp_path).unlink()
                except FileNotFoundError:
                    pass
                raise RuntimeError(f"ImageMagick convert failed: {result.stderr}")

        except Exception as e:
            self.logger.debug(f"System tools backend failed for {source_path}: {e}")
            raise

    def _load_exr_with_imageio(self, source_path: Path) -> PIL | None:
        """Load EXR using imageio library.

        Args:
            source_path: EXR file path

        Returns:
            PIL Image object or None if failed
        """
        try:
            import imageio
            import numpy as np
            from PIL import Image as PILImage

            # Read with imageio
            image_data = imageio.imread(str(source_path))

            # Convert to 8-bit
            if image_data.dtype == np.float32:
                image_data = np.clip(image_data * 255, 0, 255).astype(np.uint8)

            return PILImage.fromarray(image_data)

        except Exception as e:
            self.logger.debug(f"Imageio backend failed for {source_path}: {e}")
            raise

    # ============= Memory Management Methods =============

    def _add_item(self, file_path: str, size_bytes: int) -> None:
        """Add item to memory tracking (assumes lock held).

        Args:
            file_path: File path string
            size_bytes: File size in bytes
        """
        # Calculate the memory change this item would cause
        if file_path in self._cached_items:
            old_size = self._cached_items[file_path]
            memory_delta = size_bytes - old_size
        else:
            old_size = 0
            memory_delta = size_bytes

        # If this would exceed the limit, evict items BEFORE adding new one (if auto-eviction enabled)
        projected_memory = self._memory_usage_bytes + memory_delta
        if self._auto_evict and projected_memory > self._max_memory_bytes:
            bytes_to_evict = projected_memory - self._max_memory_bytes
            self._evict_to_make_room(bytes_to_evict, exclude_path=file_path)

        # Now add/update the item
        self._memory_usage_bytes += memory_delta
        self._cached_items[file_path] = size_bytes
        self._access_times[file_path] = time.time()
        self._heap_dirty = True

    def _evict_to_make_room(
        self, bytes_needed: int, exclude_path: str | None = None
    ) -> None:
        """Evict LRU items to make room for new item (assumes lock held).

        Args:
            bytes_needed: Minimum bytes that must be freed
            exclude_path: Path to exclude from eviction (the item being added)
        """
        bytes_evicted = 0

        if self._heap_dirty:
            self._rebuild_heap()

        # Keep evicting until we've freed enough space
        consecutive_skips = 0
        while bytes_evicted < bytes_needed and self._cached_items:
            if not self._eviction_heap:
                break

            # If we've skipped too many consecutive entries, rebuild heap to avoid infinite loop
            if consecutive_skips > len(self._cached_items):
                self._rebuild_heap()
                consecutive_skips = 0
                if not self._eviction_heap:
                    break

            entry = heapq.heappop(self._eviction_heap)

            # Skip if entry is invalid or is the item we're trying to add
            if (
                entry.path not in self._cached_items
                or self._access_times.get(entry.path, 0) != entry.access_time
                or entry.path == exclude_path
            ):
                consecutive_skips += 1
                continue

            consecutive_skips = 0  # Reset counter on successful eviction

            # Valid entry - remove it
            size_bytes = self._cached_items.pop(entry.path)
            self._access_times.pop(entry.path, None)
            self._memory_usage_bytes -= size_bytes
            bytes_evicted += size_bytes

            self.logger.debug(f"Evicted for room: {entry.path} ({size_bytes} bytes)")

    def _enforce_memory_limit(self) -> None:
        """Enforce memory limits through LRU eviction (assumes lock held)."""
        while self._memory_usage_bytes > self._max_memory_bytes and self._cached_items:
            self._evict_lru_item()

        # Emit memory pressure signal if needed (avoid division by zero)
        if self._max_memory_bytes > 0:
            usage_percent = (self._memory_usage_bytes / self._max_memory_bytes) * 100
            if usage_percent > 80:
                self.memory_pressure.emit(int(usage_percent))

    def _evict_lru_item(self) -> None:
        """Evict least recently used item (assumes lock held)."""
        if self._heap_dirty:
            self._rebuild_heap()

        while self._eviction_heap:
            entry = heapq.heappop(self._eviction_heap)

            # Check if entry is still valid
            if (
                entry.path in self._cached_items
                and self._access_times.get(entry.path, 0) == entry.access_time
            ):
                # Valid entry - remove it
                size_bytes = self._cached_items.pop(entry.path)
                self._access_times.pop(entry.path, None)
                self._memory_usage_bytes -= size_bytes

                self.logger.debug(
                    f"Evicted LRU item: {entry.path} ({size_bytes} bytes)"
                )
                break

    def _rebuild_heap(self) -> None:
        """Rebuild eviction heap from current items (assumes lock held)."""
        self._eviction_heap.clear()
        for path, size_bytes in self._cached_items.items():
            access_time = self._access_times.get(path, 0)
            heapq.heappush(
                self._eviction_heap, CacheEntry(access_time, path, size_bytes)
            )
        self._heap_dirty = False

    def _should_retry(self, source_path: Path) -> bool:
        """Check if should retry processing based on failure tracking.

        Args:
            source_path: Path to check

        Returns:
            True if should retry
        """
        with self._lock:
            path_str = str(source_path)
            if path_str not in self._failures:
                return True

            record = self._failures[path_str]
            return time.time() >= record.next_retry_time

    def validate_tracking(self) -> dict[str, Any]:
        """Validate memory tracking accuracy.

        Returns:
            Dictionary with validation results
        """
        with self._lock:
            invalid_files = 0
            size_mismatches = 0
            issues_fixed = 0

            for path_str, tracked_size in list(self._cached_items.items()):
                path = Path(path_str)

                if not path.exists():
                    # File doesn't exist anymore
                    self._cached_items.pop(path_str)
                    self._access_times.pop(path_str, None)
                    self._memory_usage_bytes -= tracked_size
                    invalid_files += 1
                    issues_fixed += 1
                else:
                    # Check size mismatch
                    try:
                        actual_size = path.stat().st_size
                        if actual_size != tracked_size:
                            size_mismatches += 1
                            # Fix the size
                            self._memory_usage_bytes += actual_size - tracked_size
                            self._cached_items[path_str] = actual_size
                            issues_fixed += 1
                    except OSError:
                        # Can't stat file
                        invalid_files += 1

            self._heap_dirty = True

            return {
                "invalid_files": invalid_files,
                "size_mismatches": size_mismatches,
                "issues_fixed": issues_fixed,
            }

    def cleanup(self) -> None:
        """Clean up resources before deletion."""
        with self._lock:
            self.clear_cache()
            self._failures.clear()

        # Disconnect all signals
        try:
            self.thumbnail_ready.disconnect()
            self.thumbnail_failed.disconnect()
            self.memory_pressure.disconnect()
        except (RuntimeError, TypeError):
            pass  # Already disconnected

        self.logger.info("ThumbnailManager cleanup complete")

    # ============= MemoryManager compatibility methods =============

    @property
    def memory_usage_bytes(self) -> int:
        """Get current memory usage in bytes (MemoryManager compatibility)."""
        with self._lock:
            return self._memory_usage_bytes

    @property
    def cached_items(self) -> dict[str, int]:
        """Get cached items dictionary (MemoryManager compatibility)."""
        with self._lock:
            return self._cached_items.copy()

    @property
    def max_memory_bytes(self) -> int:
        """Get maximum memory limit in bytes (MemoryManager compatibility)."""
        with self._lock:
            return self._max_memory_bytes

    def set_auto_evict(self, enabled: bool) -> None:
        """Enable/disable automatic eviction during item addition (MemoryManager compatibility).

        Args:
            enabled: True to automatically evict when adding items that exceed limits
        """
        with self._lock:
            self._auto_evict = enabled

    def evict_if_needed(self, target_percent: float = 0.8) -> int:
        """Evict items if memory usage exceeds limit (MemoryManager compatibility).

        Args:
            target_percent: Target memory usage as fraction of limit (0.0-1.0)

        Returns:
            Number of bytes evicted
        """
        with self._lock:
            if self._memory_usage_bytes <= self._max_memory_bytes:
                return 0  # No eviction needed

            # Calculate target bytes
            target_bytes = int(self._max_memory_bytes * target_percent)
            if self._memory_usage_bytes <= target_bytes:
                return 0  # Already within target

            return self._evict_lru_items(target_percent)

    def _evict_lru_items(self, target_percent: float) -> int:
        """Evict LRU items to reach target percentage (MemoryManager compatibility).

        Args:
            target_percent: Target memory usage as fraction of limit (0.0-1.0)

        Returns:
            Number of bytes evicted
        """
        with self._lock:
            target_bytes = int(self._max_memory_bytes * target_percent)

            if self._heap_dirty:
                self._rebuild_heap()

            bytes_evicted = 0
            consecutive_skips = 0
            while (
                self._memory_usage_bytes > target_bytes
                and self._cached_items
                and self._eviction_heap
            ):
                # If we've skipped too many consecutive entries, rebuild heap to avoid infinite loop
                if consecutive_skips > len(self._cached_items):
                    self._rebuild_heap()
                    consecutive_skips = 0
                    if not self._eviction_heap:
                        break

                entry = heapq.heappop(self._eviction_heap)

                # Skip stale entries
                if (
                    entry.path not in self._cached_items
                    or self._access_times.get(entry.path, 0) != entry.access_time
                ):
                    consecutive_skips += 1
                    continue

                consecutive_skips = 0  # Reset counter on successful eviction

                # Evict this item
                try:
                    Path(entry.path).unlink(missing_ok=True)
                    size_bytes = self._cached_items.pop(entry.path)
                    self._access_times.pop(entry.path, None)
                    self._memory_usage_bytes -= size_bytes
                    bytes_evicted += size_bytes

                    self.logger.debug(
                        f"Evicted LRU item: {entry.path} ({size_bytes} bytes)"
                    )
                except OSError as e:
                    self.logger.warning(f"Failed to delete file {entry.path}: {e}")

            return bytes_evicted


# ============= Factory functions for backward compatibility =============


def create_thumbnail_processor(thumbnail_size: int | None = None) -> ThumbnailManager:
    """Factory function to create a thumbnail processor using unified manager.

    This provides backward compatibility with the original ThumbnailProcessor interface.
    """
    return ThumbnailManager(thumbnail_size=thumbnail_size)


def create_memory_manager(max_memory_mb: int | None = None) -> ThumbnailManager:
    """Factory function to create a memory manager using unified manager.

    This provides backward compatibility with the original MemoryManager interface.
    """
    return ThumbnailManager(max_memory_mb=max_memory_mb)


def create_thumbnail_loader(
    processor: ThumbnailManager | None = None,
    memory_manager: ThumbnailManager | None = None,
) -> ThumbnailManager:
    """Factory function to create a thumbnail loader using unified manager.

    This provides backward compatibility with the original ThumbnailLoader interface.
    Note: Since everything is unified, processor and memory_manager are ignored.
    """
    return ThumbnailManager()
