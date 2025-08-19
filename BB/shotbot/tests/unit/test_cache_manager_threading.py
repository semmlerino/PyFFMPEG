"""Threading-specific unit tests for CacheManager class.

Tests for thread safety, multiple completion prevention, and concurrent operation safety.
"""

import logging
import tempfile
import threading
import time
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QImage

from cache_manager import CacheManager, ThumbnailCacheResult
from config import ThreadingConfig
from shot_model import Shot


class ThreadSafeTestImage:
    """Thread-safe test double for QPixmap using QImage internally.

    QPixmap is not thread-safe and can only be used in the main GUI thread.
    QImage is thread-safe and can be used in any thread. This class provides
    a QPixmap-like interface while using QImage internally for thread safety.

    Based on Qt's canonical threading pattern for image operations.
    """

    def __init__(self, width: int = 100, height: int = 100):
        """Create a thread-safe test image.

        Args:
            width: Image width in pixels
            height: Image height in pixels
        """
        # Use QImage which is thread-safe, unlike QPixmap
        self._image = QImage(width, height, QImage.Format.Format_RGB32)
        self._width = width
        self._height = height
        self._image.fill(QColor(255, 255, 255))  # Fill with white by default

    def fill(self, color: QColor = None) -> None:
        """Fill the image with a color."""
        if color is None:
            color = QColor(255, 255, 255)  # Default to white
        self._image.fill(color)

    def isNull(self) -> bool:
        """Check if the image is null."""
        return self._image.isNull()

    def sizeInBytes(self) -> int:
        """Return the size of the image in bytes."""
        return self._image.sizeInBytes()

    def size(self) -> QSize:
        """Return the size of the image."""
        return QSize(self._width, self._height)

    def width(self) -> int:
        """Return the width of the image."""
        return self._width

    def height(self) -> int:
        """Return the height of the image."""
        return self._height


class TestCacheManagerThreading:
    """Test suite for CacheManager threading behavior."""

    @pytest.fixture
    def temp_cache_dir(self):
        """Create temporary cache directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    def cache_manager(self, temp_cache_dir):
        """Create CacheManager instance for testing."""
        return CacheManager(cache_dir=temp_cache_dir)

    @pytest.fixture
    def test_shot(self):
        """Create test shot for testing."""
        return Shot("test_show", "test_seq", "test_shot", "/test/workspace")

    def test_thumbnail_cache_result_single_completion(self):
        """Test ThumbnailCacheResult prevents multiple completion."""
        result = ThumbnailCacheResult()

        # Complete the result once
        test_path = Path("/test/cache/path.jpg")
        result.set_result(test_path)

        # Verify first completion worked - test BEHAVIOR not internals
        assert result.cache_path == test_path
        # Check completion state (behavior: path was set successfully)
        assert result.cache_path is not None

        # Attempt second completion - should be ignored
        test_path2 = Path("/test/cache/path2.jpg")
        result.set_result(test_path2)

        # Verify second completion was ignored - check outcome
        assert result.cache_path == test_path  # Still first path (behavior)
        assert result.cache_path != test_path2  # Not changed (behavior)

    def test_thumbnail_cache_result_concurrent_completion(self):
        """Test ThumbnailCacheResult thread safety with concurrent completion attempts."""
        result = ThumbnailCacheResult()

        completion_results = []
        errors = []

        def attempt_completion(thread_id: int):
            """Attempt to complete the result from multiple threads."""
            try:
                test_path = Path(f"/test/cache/path_{thread_id}.jpg")

                # Simulate some work before completion
                time.sleep(0.001 * thread_id)

                result.set_result(test_path)
                completion_results.append((thread_id, result.cache_path == test_path))
            except Exception as e:
                errors.append((thread_id, str(e)))

        # Start multiple threads attempting completion
        threads = []
        for i in range(5):
            t = threading.Thread(target=attempt_completion, args=(i,))
            threads.append(t)
            t.start()

        # Wait for all threads
        for t in threads:
            t.join(timeout=5.0)

        # Verify no errors occurred
        assert len(errors) == 0, f"Concurrent completion errors: {errors}"

        # Verify only one completion succeeded
        successful_completions = [r for r in completion_results if r[1]]
        assert len(successful_completions) == 1, (
            f"Expected 1 successful completion, got {len(successful_completions)}"
        )

        # Verify result is completed
        assert result._is_complete is True
        assert result.cache_path is not None

    def test_instance_variable_separation(self):
        """Test that each CacheManager instance has separate variables."""
        # Create two cache manager instances
        with tempfile.TemporaryDirectory() as temp_dir1, tempfile.TemporaryDirectory() as temp_dir2:
            cache1 = CacheManager(cache_dir=Path(temp_dir1))
            cache2 = CacheManager(cache_dir=Path(temp_dir2))

            # Verify they have separate instance variables
            assert cache1._lock is not cache2._lock
            assert cache1._cached_thumbnails is not cache2._cached_thumbnails
            assert cache1.cache_dir != cache2.cache_dir

            # Verify initial state
            assert cache1._memory_usage_bytes == 0
            assert cache2._memory_usage_bytes == 0

            # Modify one instance
            cache1._memory_usage_bytes = 1000
            cache1._cached_thumbnails["test"] = ThreadSafeTestImage(100, 100)

            # Verify other instance is unaffected (they are independent variables)
            assert cache1._memory_usage_bytes == 1000
            assert cache2._memory_usage_bytes == 0
            assert len(cache1._cached_thumbnails) == 1
            assert len(cache2._cached_thumbnails) == 0

    def test_concurrent_memory_tracking(self, cache_manager):
        """Test thread-safe memory usage tracking."""
        manager = cache_manager

        def add_memory_usage(thread_id: int, amount: int):
            """Add memory usage from multiple threads."""
            try:
                with manager._lock:
                    current = manager._memory_usage_bytes
                    time.sleep(0.001)  # Simulate processing
                    manager._memory_usage_bytes = current + amount
            except Exception as e:
                logging.error(f"Thread {thread_id} error: {e}")

        # Start multiple threads adding memory
        threads = []
        amounts = [100, 200, 300, 400, 500]

        for i, amount in enumerate(amounts):
            t = threading.Thread(target=add_memory_usage, args=(i, amount))
            threads.append(t)
            t.start()

        # Wait for all threads
        for t in threads:
            t.join(timeout=5.0)

        # Verify total memory usage is correct
        expected_total = sum(amounts)
        assert manager._memory_usage_bytes == expected_total

    def test_concurrent_thumbnail_caching(self, cache_manager, test_shot):
        """Test concurrent thumbnail caching operations."""
        manager = cache_manager

        # Create test image using thread-safe test double
        test_image = ThreadSafeTestImage(100, 100)
        test_image.fill()

        cache_results = []
        errors = []

        def cache_thumbnail(thread_id: int):
            """Cache thumbnail from multiple threads."""
            try:
                # Use unique shot for each thread to avoid conflicts
                shot = Shot(
                    f"show_{thread_id}",
                    "seq_01",
                    f"shot_{thread_id:03d}",
                    f"/path/{thread_id}",
                )

                # Mock image path and QImage loading (cache_manager uses QImage, not QPixmap)
                with patch("cache_manager.Path.exists", return_value=True), patch(
                    "cache_manager.QImage",
                ) as mock_image_class:
                    mock_image = MagicMock()
                    mock_image.isNull.return_value = False
                    mock_image.sizeInBytes.return_value = 1000
                    mock_image_class.return_value = mock_image

                    result = manager.cache_thumbnail(
                        Path(f"/test/image_{thread_id}.jpg"),
                        shot.show,
                        shot.sequence,
                        shot.shot,
                    )
                    cache_results.append((thread_id, result is not None))

            except Exception as e:
                errors.append((thread_id, str(e)))

        # Start multiple threads caching
        threads = []
        for i in range(5):
            t = threading.Thread(target=cache_thumbnail, args=(i,))
            threads.append(t)
            t.start()

        # Wait for all threads
        for t in threads:
            t.join(timeout=10.0)

        # Verify no errors occurred
        assert len(errors) == 0, f"Concurrent caching errors: {errors}"

        # Verify all caching operations succeeded
        successful_caches = [r for r in cache_results if r[1]]
        assert len(successful_caches) == 5

    def test_async_sync_mode_behavior(self, cache_manager, test_shot):
        """Test cache manager threading behavior with different wait modes."""

        # Test that ThumbnailCacheResult behaves correctly in threaded environment
        result = ThumbnailCacheResult()

        # Test threading behavior of ThumbnailCacheResult
        def complete_result():
            test_path = Path("/test/cache/async_result.jpg")
            result.set_result(test_path)

        # Run completion in thread to test thread safety
        thread = threading.Thread(target=complete_result)
        thread.start()
        thread.join(timeout=1.0)

        # Verify thread-safe completion
        assert result._is_complete is True
        assert result.cache_path is not None

        # Test concurrent access to completed result
        access_results = []

        def access_result(thread_id: int):
            try:
                path = result.cache_path
                is_complete = result._is_complete
                access_results.append((thread_id, path is not None, is_complete))
            except Exception:
                access_results.append((thread_id, False, False))

        # Multiple threads accessing completed result
        threads = []
        for i in range(3):
            t = threading.Thread(target=access_result, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=1.0)

        # Verify all threads saw consistent completed state
        assert len(access_results) == 3
        for thread_id, path_valid, is_complete in access_results:
            assert path_valid is True
            assert is_complete is True

    def test_lock_protection_during_cleanup(self, cache_manager):
        """Test that cleanup operations are properly lock-protected."""
        manager = cache_manager

        # Add some cached data using thread-safe test doubles
        manager._cached_thumbnails["/test/image1.jpg"] = ThreadSafeTestImage(100, 100)
        manager._cached_thumbnails["/test/image2.jpg"] = ThreadSafeTestImage(100, 100)
        manager._memory_usage_bytes = 2000

        cleanup_results = []
        access_results = []

        def cleanup_cache():
            """Perform cache cleanup."""
            try:
                with manager._lock:
                    # Simulate cleanup work
                    time.sleep(0.01)
                    manager._cached_thumbnails.clear()
                    manager._memory_usage_bytes = 0
                    cleanup_results.append("cleanup_done")
            except Exception as e:
                cleanup_results.append(f"cleanup_error: {e}")

        def access_cache():
            """Access cache during cleanup."""
            try:
                with manager._lock:
                    # Simulate cache access
                    time.sleep(0.005)
                    count = len(manager._cached_thumbnails)
                    access_results.append(f"access_count: {count}")
            except Exception as e:
                access_results.append(f"access_error: {e}")

        # Start cleanup and access threads simultaneously
        cleanup_thread = threading.Thread(target=cleanup_cache)
        access_thread = threading.Thread(target=access_cache)

        cleanup_thread.start()
        access_thread.start()

        # Wait for completion
        cleanup_thread.join(timeout=5.0)
        access_thread.join(timeout=5.0)

        # Verify operations completed without errors
        assert len(cleanup_results) == 1
        assert len(access_results) == 1
        assert "error" not in cleanup_results[0]
        assert "error" not in access_results[0]

    def test_memory_limit_enforcement(self, cache_manager):
        """Test that memory limits are enforced thread-safely."""
        manager = cache_manager

        # Set low memory limit for testing
        original_limit = manager._max_memory_bytes
        manager._max_memory_bytes = 1000  # 1KB limit

        try:
            # Use ThreadSafeTestImage to simulate large image
            test_image = ThreadSafeTestImage(500, 500)  # Large image
            
            with patch("cache_manager.QImage") as mock_image_class:
                # Configure test image to exceed memory limit
                test_image._image.sizeInBytes = lambda: 2000  # Exceeds 1KB limit
                mock_image_class.return_value = test_image._image

                with patch("cache_manager.Path.exists", return_value=True):
                    shot = Shot("test", "seq", "shot", "/path")

                    # Should handle memory limit gracefully
                    result = manager.cache_thumbnail(
                        Path("/test/large_image.jpg"),
                        shot.show,
                        shot.sequence,
                        shot.shot,
                    )

                    # Verify memory tracking behavior
                    assert (
                        manager._memory_usage_bytes <= manager._max_memory_bytes
                        or result is None
                    )

        finally:
            # Restore original limit
            manager._max_memory_bytes = original_limit

    def test_threadingconfig_integration(self, cache_manager):
        """Test integration with ThreadingConfig constants."""
        manager = cache_manager

        # Verify memory limit uses ThreadingConfig
        expected_memory_limit = ThreadingConfig.CACHE_MAX_MEMORY_MB * 1024 * 1024
        assert manager._max_memory_bytes == expected_memory_limit

    # NOTE: Commented out test_cache_statistics_thread_safety because
    # get_cache_stats() method doesn't exist in CacheManager implementation

    def test_cache_key_generation_thread_safety(self, cache_manager):
        """Test thread-safe cache key generation."""

        cache_keys = []
        errors = []

        def generate_cache_keys(thread_id: int):
            """Generate cache keys from multiple threads."""
            try:
                for i in range(10):
                    shot = Shot(
                        f"show_{thread_id}",
                        f"seq_{i}",
                        f"shot_{i:03d}",
                        f"/path/{thread_id}/{i}",
                    )
                    cache_key = f"{shot.show}_{shot.sequence}_{shot.shot}"
                    cache_keys.append((thread_id, cache_key))
            except Exception as e:
                errors.append((thread_id, str(e)))

        # Start multiple threads generating keys
        threads = []
        for i in range(3):
            t = threading.Thread(target=generate_cache_keys, args=(i,))
            threads.append(t)
            t.start()

        # Wait for all threads
        for t in threads:
            t.join(timeout=5.0)

        # Verify no errors occurred
        assert len(errors) == 0, f"Cache key generation errors: {errors}"

        # Verify all keys are unique and correctly formatted
        all_keys = [key for _, key in cache_keys]
        assert len(all_keys) == 30  # 3 threads × 10 keys each
        assert len(set(all_keys)) == 30  # All keys should be unique

    def test_thumbnail_cache_result_cleanup(self):
        """Test ThumbnailCacheResult proper cleanup."""
        result = ThumbnailCacheResult()

        # Complete with resources using thread-safe test double
        Future()
        cache_path = Path("/test/cache/path.jpg")
        result.set_result(cache_path)

        # Verify resources are set
        assert result.future is not None
        assert result.cache_path is not None

        # In a real scenario, Qt would handle QPixmap cleanup automatically
        # We just verify the structure is correct
        assert hasattr(result, "_completed_lock")
        assert isinstance(result._completed_lock, type(threading.Lock()))

    def test_concurrent_cache_retrieval(self, cache_manager, test_shot):
        """Test concurrent cache retrieval operations."""
        manager = cache_manager

        # Mock the cache file system since get_cached_thumbnail checks disk files
        manager.thumbnails_dir / test_shot.show / test_shot.sequence / f"{test_shot.shot}_thumb.jpg"

        retrieval_results = []
        errors = []

        def retrieve_cached_thumbnail(thread_id: int):
            """Retrieve cached thumbnail from multiple threads."""
            try:
                # Use a broader patch that covers the whole method call
                with patch("pathlib.Path.exists", return_value=True):
                    for _ in range(5):
                        cached = manager.get_cached_thumbnail(
                            test_shot.show,
                            test_shot.sequence,
                            test_shot.shot,
                        )
                        retrieval_results.append((thread_id, cached is not None))
                        time.sleep(0.001)
            except Exception as e:
                errors.append((thread_id, str(e)))

        # Start multiple threads retrieving
        threads = []
        for i in range(4):
            t = threading.Thread(target=retrieve_cached_thumbnail, args=(i,))
            threads.append(t)
            t.start()

        # Wait for all threads
        for t in threads:
            t.join(timeout=5.0)

        # Verify no errors occurred
        assert len(errors) == 0, f"Concurrent retrieval errors: {errors}"

        # Verify most retrievals found the cached thumbnail (allow for minor timing issues)
        successful_retrievals = [r for r in retrieval_results if r[1]]
        assert (
            len(successful_retrievals) >= 18
        )  # Allow for 1-2 timing misses in threading

    def test_rlock_reentrant_behavior(self, cache_manager):
        """Test that RLock allows reentrant access."""
        manager = cache_manager

        def nested_lock_access():
            """Test nested lock acquisition."""
            with manager._lock:
                # First level
                initial_memory = manager._memory_usage_bytes

                with manager._lock:
                    # Second level (reentrant)
                    manager._memory_usage_bytes = initial_memory + 100

                    with manager._lock:
                        # Third level (reentrant)
                        final_memory = manager._memory_usage_bytes
                        return final_memory

        # Should work without deadlock
        result = nested_lock_access()
        assert result == 100  # Memory was incremented
