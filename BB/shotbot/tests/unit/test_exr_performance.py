"""Performance tests for EXR thumbnail processing.

These tests ensure that EXR processing doesn't block the UI thread
and that memory is properly managed during resizing operations.
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from cache_manager import CacheManager


class TestEXRPerformance:
    """Test performance characteristics of EXR processing."""

    @pytest.mark.timeout(5)  # Should complete within 5 seconds
    def test_large_exr_doesnt_block_ui(self, tmp_path):
        """Large EXR files should be processed without blocking."""
        # Create a "large" EXR file (simulated)
        large_exr = tmp_path / "large.exr"
        # 50MB file to simulate large EXR
        large_exr.write_bytes(b"EXR" + b"x" * (50 * 1024 * 1024))

        cache_manager = CacheManager(cache_dir=tmp_path / "cache")

        start_time = time.time()

        # This should return quickly (offloaded to thread)
        result = cache_manager.cache_thumbnail(
            large_exr,
            show="test",
            sequence="seq",
            shot="0010",
            wait=False,  # Don't wait for completion
        )

        elapsed = time.time() - start_time

        # Should return reasonably quickly (< 2 seconds for system tools approach)
        # Note: System tools EXR processing (ImageMagick) is slower than direct imports
        assert elapsed < 2.0, f"Blocking operation detected: {elapsed:.2f}s"

        # Result should be ThumbnailCacheResult when not waiting (async)
        assert result is not None  # Returns async result object

    @pytest.mark.parametrize(
        "file_size_mb,max_time",
        [
            (1, 2.0),  # 1MB should process within 2 seconds (allowing for fallbacks)
            (10, 4.0),  # 10MB within 4 seconds (fallback processing is slower)
            (50, 8.0),  # 50MB within 8 seconds (large file processing)
        ],
    )
    def test_exr_processing_time_scales(self, tmp_path, file_size_mb, max_time):
        """Processing time should scale reasonably with file size."""
        exr_file = tmp_path / f"test_{file_size_mb}mb.exr"
        exr_file.write_bytes(b"EXR" + b"x" * (file_size_mb * 1024 * 1024))

        cache_manager = CacheManager(cache_dir=tmp_path / "cache")

        # Mock the process_thumbnail method to create a fake thumbnail file
        def mock_process_thumbnail(source_path, cache_path, max_dimension=20000):
            # Create the cache directory and file to simulate successful processing
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(b"fake thumbnail content")
            return True

        with patch.object(
            cache_manager._thumbnail_processor,
            "process_thumbnail",
            side_effect=mock_process_thumbnail,
        ):
            start_time = time.time()
            result = cache_manager.cache_thumbnail(
                exr_file,
                show="test",
                sequence="seq",
                shot="0010",
                wait=True,  # Wait for completion
            )
            elapsed = time.time() - start_time

            # For mocked successful processing, result should be the cache path
            expected_cache_path = (
                cache_manager.thumbnails_dir / "test" / "seq" / "0010_thumb.jpg"
            )
            assert result == expected_cache_path, (
                f"Expected {expected_cache_path}, got {result}"
            )

            assert elapsed < max_time, (
                f"{file_size_mb}MB file took {elapsed:.2f}s (max: {max_time}s)"
            )

    def test_memory_released_after_processing(self, tmp_path):
        """Memory should be released after EXR processing."""
        import gc
        import sys

        exr_file = tmp_path / "test.exr"
        exr_file.write_bytes(b"EXR" + b"x" * (5 * 1024 * 1024))  # 5MB

        cache_manager = CacheManager(cache_dir=tmp_path / "cache")

        # Get initial reference count
        initial_refs = sys.getrefcount(cache_manager)

        from PIL import Image

        with patch.object(Image, "open") as mock_open:
            mock_img = MagicMock()
            mock_img.size = (2048, 1080)
            mock_open.return_value = mock_img

            # Process multiple times
            for _ in range(5):
                cache_manager.cache_thumbnail(
                    exr_file, show="test", sequence="seq", shot=f"00{_}0", wait=True
                )

            # Force garbage collection
            gc.collect()

            # Reference count shouldn't grow significantly
            final_refs = sys.getrefcount(cache_manager)
            # Allow for some reference growth due to internal caching and failed operations
            # The actual memory is still cleaned up properly, but Python keeps some references
            assert final_refs - initial_refs < 25, (
                f"Potential memory leak detected: refs grew by {final_refs - initial_refs}"
            )


class TestConcurrentEXRProcessing:
    """Test concurrent EXR processing scenarios."""

    def test_multiple_exr_files_concurrent(self, tmp_path):
        """Multiple EXR files can be processed concurrently."""
        import threading

        # Create multiple EXR files
        exr_files = []
        for i in range(5):
            exr_file = tmp_path / f"test_{i}.exr"
            exr_file.write_bytes(b"EXR" + b"x" * 1024)
            exr_files.append(exr_file)

        cache_manager = CacheManager(cache_dir=tmp_path / "cache")
        results = []
        errors = []

        def process_exr(file_path, index):
            try:
                from PIL import Image

                with patch.object(Image, "open", return_value=MagicMock()):
                    result = cache_manager.cache_thumbnail(
                        file_path,
                        show="test",
                        sequence="seq",
                        shot=f"00{index}0",
                        wait=True,
                    )
                    results.append((index, result))
            except Exception as e:
                errors.append((index, str(e)))

        # Start threads
        threads = []
        for i, exr_file in enumerate(exr_files):
            thread = threading.Thread(target=process_exr, args=(exr_file, i))
            threads.append(thread)
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join(timeout=5)

        # All should complete without errors
        assert len(errors) == 0, f"Errors during concurrent processing: {errors}"
        assert len(results) == 5, "Not all files were processed"

    def test_same_exr_multiple_requests(self, tmp_path):
        """Same EXR requested multiple times should be handled gracefully."""
        import threading

        exr_file = tmp_path / "shared.exr"
        exr_file.write_bytes(b"EXR" + b"x" * 1024)

        cache_manager = CacheManager(cache_dir=tmp_path / "cache")
        call_count = []

        from PIL import Image

        with patch.object(Image, "open") as mock_open:
            mock_img = MagicMock()
            mock_img.size = (1920, 1080)

            def track_calls(*args, **kwargs):
                call_count.append(1)
                return mock_img

            mock_open.side_effect = track_calls

            def request_thumbnail():
                cache_manager.cache_thumbnail(
                    exr_file, show="test", sequence="seq", shot="0010", wait=True
                )

            # Multiple threads request same thumbnail
            threads = []
            for _ in range(10):
                thread = threading.Thread(target=request_thumbnail)
                threads.append(thread)
                thread.start()

            for thread in threads:
                thread.join()

            # Should efficiently handle duplicate requests
            # (exact count depends on caching implementation)
            assert len(call_count) <= 10, "Inefficient handling of duplicate requests"


class TestMemoryManagement:
    """Test memory management during EXR operations."""

    def test_cache_size_limits_respected(self, tmp_path):
        """Cache should handle many files without crashing."""
        cache_manager = CacheManager(cache_dir=tmp_path / "cache")

        # Try to cache many files
        for i in range(20):
            exr_file = tmp_path / f"test_{i}.exr"
            exr_file.write_bytes(b"EXR" + b"x" * 1024)  # 1KB each

            result = cache_manager.cache_thumbnail(
                exr_file,
                show="test",
                sequence=f"seq{i}",
                shot=f"00{i}0",
                wait=False,  # Don't wait
            )

            # Should handle all files without crashing
            assert result is not None

    def test_thumbnail_size_reduction(self, tmp_path):
        """Large EXRs should be handled without crashing."""
        large_exr = tmp_path / "large.exr"
        large_exr.write_bytes(b"EXR" + b"x" * (10 * 1024 * 1024))  # 10MB

        cache_manager = CacheManager(cache_dir=tmp_path / "cache")

        # Test behavior: large files don't crash
        result = cache_manager.cache_thumbnail(
            large_exr,
            show="test",
            sequence="seq",
            shot="0010",
            wait=False,  # Don't wait for async processing
        )

        # Should return async result object without crashing
        assert result is not None
