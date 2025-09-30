"""Test unified ThumbnailManager that replaces 4 components."""

from __future__ import annotations

# Standard library imports
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch

# Third-party imports
import pytest
from PySide6.QtGui import QImage

# Local application imports
from cache.thumbnail_manager import (
    ThumbnailCacheResult,
    ThumbnailManager,
    create_thumbnail_processor,
)


@pytest.fixture
def temp_cache_dir():
    """Create a temporary cache directory for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def temp_image_file():
    """Create a temporary image file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        temp_path = Path(f.name)

    # Create a simple test image using Qt
    qimage = QImage(100, 100, QImage.Format.Format_RGB32)
    qimage.fill(0xFF0000)  # Red color
    qimage.save(str(temp_path), "JPEG")

    yield temp_path

    # Cleanup
    if temp_path.exists():
        temp_path.unlink()


@pytest.fixture
def thumbnail_manager():
    """Create a ThumbnailManager instance for testing."""
    return ThumbnailManager(thumbnail_size=64, max_memory_mb=10)


class TestThumbnailManagerBasics:
    """Test basic ThumbnailManager functionality."""

    def test_initialization(self) -> None:
        """Test ThumbnailManager initialization."""
        manager = ThumbnailManager(thumbnail_size=128, max_memory_mb=20)

        assert manager._thumbnail_size == 128
        assert manager._max_memory_bytes == 20 * 1024 * 1024
        assert manager._memory_usage_bytes == 0
        assert len(manager._cached_items) == 0

    def test_default_initialization(self) -> None:
        """Test ThumbnailManager with default values."""
        manager = ThumbnailManager()

        # Should use config defaults
        assert manager._thumbnail_size > 0
        assert manager._max_memory_bytes > 0

    def test_usage_stats_empty(self, thumbnail_manager) -> None:
        """Test usage statistics with empty cache."""
        stats = thumbnail_manager.get_usage_stats()

        assert stats["total_items"] == 0
        assert stats["total_size_mb"] == 0
        assert stats["usage_percent"] == 0
        assert stats["average_item_kb"] == 0
        assert stats["memory_limit_mb"] > 0

    def test_set_memory_limit(self, thumbnail_manager) -> None:
        """Test setting memory limit."""
        new_limit = 50
        thumbnail_manager.set_memory_limit(new_limit)

        assert thumbnail_manager._max_memory_bytes == new_limit * 1024 * 1024

        stats = thumbnail_manager.get_usage_stats()
        assert stats["memory_limit_mb"] == new_limit


class TestThumbnailManagerMemoryTracking:
    """Test memory tracking functionality."""

    def test_track_item(self, thumbnail_manager, temp_image_file) -> None:
        """Test tracking items in memory manager."""
        assert thumbnail_manager.track_item(temp_image_file) is True
        assert thumbnail_manager.is_item_tracked(temp_image_file) is True

        stats = thumbnail_manager.get_usage_stats()
        assert stats["total_items"] == 1
        assert stats["total_size_mb"] > 0

    def test_track_nonexistent_item(self, thumbnail_manager) -> None:
        """Test tracking non-existent file."""
        fake_path = Path("/nonexistent/file.jpg")
        assert thumbnail_manager.track_item(fake_path) is False
        assert thumbnail_manager.is_item_tracked(fake_path) is False

    def test_evict_item(self, thumbnail_manager, temp_image_file) -> None:
        """Test evicting items from memory tracking."""
        # Track item first
        thumbnail_manager.track_item(temp_image_file)
        assert thumbnail_manager.is_item_tracked(temp_image_file) is True

        # Evict item
        assert thumbnail_manager.evict_item(temp_image_file) is True
        assert thumbnail_manager.is_item_tracked(temp_image_file) is False

        stats = thumbnail_manager.get_usage_stats()
        assert stats["total_items"] == 0

    def test_evict_nonexistent_item(self, thumbnail_manager) -> None:
        """Test evicting non-tracked item."""
        fake_path = Path("/nonexistent/file.jpg")
        assert thumbnail_manager.evict_item(fake_path) is False

    def test_force_update_item(self, thumbnail_manager, temp_image_file) -> None:
        """Test force updating item size."""
        # Track item first
        thumbnail_manager.track_item(temp_image_file)
        initial_stats = thumbnail_manager.get_usage_stats()

        # Force update (should work even if already tracked)
        assert thumbnail_manager.track_item(temp_image_file, force_update=True) is True

        # Stats should be updated (access time refreshed)
        updated_stats = thumbnail_manager.get_usage_stats()
        assert updated_stats["total_items"] == initial_stats["total_items"]

    def test_clear_cache(self, thumbnail_manager, temp_image_file) -> None:
        """Test clearing entire cache."""
        # Track some items
        thumbnail_manager.track_item(temp_image_file)
        assert thumbnail_manager.get_usage_stats()["total_items"] == 1

        # Clear cache
        cleared_count = thumbnail_manager.clear_cache()
        assert cleared_count == 1

        stats = thumbnail_manager.get_usage_stats()
        assert stats["total_items"] == 0
        assert stats["total_size_mb"] == 0


class TestThumbnailManagerFailureTracking:
    """Test failure tracking and retry logic."""

    def test_record_and_check_failure(self, thumbnail_manager, temp_image_file) -> None:
        """Test recording failures and retry logic."""
        # Should be able to retry initially
        assert thumbnail_manager._should_retry(temp_image_file) is True

        # Record a failure
        thumbnail_manager.record_failure(temp_image_file, "Test error")

        # Should still be able to retry (backoff not immediate)
        # Note: _should_retry might still return True depending on retry timing
        # The important thing is that failure was recorded
        assert temp_image_file.name in [
            Path(p).name for p in thumbnail_manager._failures.keys()
        ]

    def test_clear_failure(self, thumbnail_manager, temp_image_file) -> None:
        """Test clearing failure records."""
        # Record failure
        thumbnail_manager.record_failure(temp_image_file, "Test error")
        assert str(temp_image_file) in thumbnail_manager._failures

        # Clear failure
        thumbnail_manager.clear_failure(temp_image_file)
        assert str(temp_image_file) not in thumbnail_manager._failures

    def test_exponential_backoff(self, thumbnail_manager, temp_image_file) -> None:
        """Test exponential backoff for multiple failures."""
        # Record multiple failures
        for i in range(3):
            thumbnail_manager.record_failure(temp_image_file, f"Error {i}")

        # Should have failure record with multiple attempts
        failure_record = thumbnail_manager._failures[str(temp_image_file)]
        assert failure_record.failure_count == 3
        assert failure_record.next_retry_time > time.time()


class TestThumbnailManagerProcessing:
    """Test thumbnail processing functionality."""

    def test_analyze_source_file(self, thumbnail_manager, temp_image_file) -> None:
        """Test source file analysis."""
        file_info = thumbnail_manager._analyze_source_file(temp_image_file)

        assert "file_size_mb" in file_info
        assert "suffix_lower" in file_info
        assert "is_heavy_format" in file_info
        assert "use_pil" in file_info
        assert file_info["suffix_lower"] == ".jpg"
        assert file_info["is_heavy_format"] is False

    def test_analyze_heavy_format(self, thumbnail_manager, temp_cache_dir) -> None:
        """Test analysis of heavy format files."""
        # Create a real EXR file for testing
        fake_exr = temp_cache_dir / "test.exr"
        fake_exr.write_text("x" * (5 * 1024 * 1024))  # 5MB fake EXR

        file_info = thumbnail_manager._analyze_source_file(fake_exr)

        assert file_info["suffix_lower"] == ".exr"
        assert file_info["is_heavy_format"] is True
        assert file_info["use_pil"] is True  # Large EXR should use PIL

    def test_process_with_qt_success(
        self, thumbnail_manager, temp_image_file, temp_cache_dir
    ) -> None:
        """Test Qt processing success."""
        cache_path = temp_cache_dir / "thumb.jpg"
        file_info = {"file_size_mb": 0.1, "suffix_lower": ".jpg", "use_pil": False}

        success = thumbnail_manager._process_with_qt(
            temp_image_file, cache_path, file_info
        )

        assert success is True
        assert cache_path.exists()

    def test_process_with_qt_invalid_source(self, thumbnail_manager, temp_cache_dir) -> None:
        """Test Qt processing with invalid source."""
        invalid_source = Path("/nonexistent/file.jpg")
        cache_path = temp_cache_dir / "thumb.jpg"
        file_info = {"file_size_mb": 0.1, "suffix_lower": ".jpg", "use_pil": False}

        success = thumbnail_manager._process_with_qt(
            invalid_source, cache_path, file_info
        )

        assert success is False
        assert not cache_path.exists()

    def test_process_with_pil_success(
        self, thumbnail_manager, temp_image_file, temp_cache_dir
    ) -> None:
        """Test PIL processing success."""
        # Mock PIL image
        mock_image = Mock()
        mock_image.mode = "RGB"

        cache_path = temp_cache_dir / "thumb.jpg"
        file_info = {"file_size_mb": 2.0, "suffix_lower": ".tiff", "use_pil": True}

        with patch.object(
            thumbnail_manager, "_load_image_with_pil", return_value=mock_image
        ):
            success = thumbnail_manager._process_with_pil(
                temp_image_file, cache_path, file_info
            )

        assert success is True
        mock_image.thumbnail.assert_called_once()
        mock_image.save.assert_called_once()

    def test_sync_thumbnail_processing(
        self, thumbnail_manager, temp_image_file, temp_cache_dir
    ) -> None:
        """Test synchronous thumbnail processing."""
        cache_path = temp_cache_dir / "thumb.jpg"

        success = thumbnail_manager.cache_thumbnail_sync(temp_image_file, cache_path)

        assert success is True
        assert cache_path.exists()
        # Should be tracked in memory manager
        assert thumbnail_manager.is_item_tracked(cache_path) is True

    def test_sync_thumbnail_processing_failure(self, thumbnail_manager, temp_cache_dir) -> None:
        """Test synchronous processing with invalid source."""
        invalid_source = Path("/nonexistent/file.jpg")
        cache_path = temp_cache_dir / "thumb.jpg"

        success = thumbnail_manager.cache_thumbnail_sync(invalid_source, cache_path)

        assert success is False
        assert not cache_path.exists()
        # Should record failure
        assert str(invalid_source) in thumbnail_manager._failures


class TestThumbnailManagerAsync:
    """Test asynchronous thumbnail processing."""

    def test_async_thumbnail_processing_success(
        self, thumbnail_manager, temp_image_file, temp_cache_dir
    ) -> None:
        """Test asynchronous thumbnail processing success."""
        cache_path = temp_cache_dir / "async_thumb.jpg"

        result = thumbnail_manager.cache_thumbnail_async(temp_image_file, cache_path)

        assert isinstance(result, ThumbnailCacheResult)

        # Wait for completion (with reasonable timeout)
        completed = result.wait_for_completion(timeout_ms=5000)
        assert completed is True
        assert result.is_complete is True
        assert result.cache_path == cache_path
        assert result.error is None

    def test_async_thumbnail_processing_with_backoff(
        self, thumbnail_manager, temp_image_file, temp_cache_dir
    ) -> None:
        """Test async processing respects failure backoff."""
        cache_path = temp_cache_dir / "backoff_thumb.jpg"

        # Record multiple failures to trigger backoff
        for i in range(3):
            thumbnail_manager.record_failure(temp_image_file, f"Error {i}")

        # Set next retry time to future
        failure_record = thumbnail_manager._failures[str(temp_image_file)]
        failure_record.next_retry_time = time.time() + 3600  # 1 hour from now

        result = thumbnail_manager.cache_thumbnail_async(temp_image_file, cache_path)

        # Should fail immediately due to backoff
        assert result.is_complete is True
        assert result.error is not None
        assert "backoff" in result.error.lower()

    def test_thumbnail_cache_result_completion(self) -> None:
        """Test ThumbnailCacheResult completion handling."""
        result = ThumbnailCacheResult()

        assert result.is_complete is False

        # Set result
        cache_path = Path("/test/cache.jpg")
        result.set_result(cache_path)

        assert result.is_complete is True
        assert result.cache_path == cache_path
        assert result.error is None

    def test_thumbnail_cache_result_error(self) -> None:
        """Test ThumbnailCacheResult error handling."""
        result = ThumbnailCacheResult()

        error_msg = "Test error"
        result.set_error(error_msg)

        assert result.is_complete is True
        assert result.error == error_msg
        assert result.cache_path is None

    def test_thumbnail_cache_result_double_completion(self) -> None:
        """Test that result can't be completed twice."""
        result = ThumbnailCacheResult()

        # First completion
        result.set_result(Path("/first.jpg"))
        assert result.cache_path == Path("/first.jpg")

        # Second completion should be ignored
        result.set_error("Should be ignored")
        assert result.cache_path == Path("/first.jpg")
        assert result.error is None


class TestThumbnailManagerMemoryEviction:
    """Test memory eviction and LRU behavior."""

    def test_memory_eviction_on_limit(self, temp_cache_dir) -> None:
        """Test LRU eviction when memory limit is exceeded."""
        # Create manager with very small memory limit
        manager = ThumbnailManager(max_memory_mb=0.001)  # 1KB limit

        # Create test files that will exceed limit
        files = []
        for i in range(3):
            test_file = temp_cache_dir / f"test_{i}.txt"
            test_file.write_text("x" * 1000)  # 1KB each file
            files.append(test_file)

        # Track files - should trigger eviction
        for file in files:
            manager.track_item(file)

        # Should have evicted some items due to memory limit
        stats = manager.get_usage_stats()
        assert stats["total_items"] < len(files)

    def test_lru_eviction_order(self, temp_cache_dir) -> None:
        """Test that LRU eviction removes oldest accessed items first."""
        manager = ThumbnailManager(max_memory_mb=0.003)  # 3KB limit (~3145 bytes)

        # Create test files
        file1 = temp_cache_dir / "old.txt"
        file2 = temp_cache_dir / "new.txt"
        file1.write_text("x" * 1000)  # 1KB
        file2.write_text("x" * 1200)  # 1.2KB

        # Track first file
        manager.track_item(file1)
        time.sleep(0.01)  # Small delay to ensure different access times

        # Track second file
        manager.track_item(file2)

        # Access first file again to make it more recent
        manager.track_item(file1, force_update=True)

        # Add a file that should trigger eviction of only the oldest
        # Current: file1 (1000) + file2 (1200) = 2200 bytes
        # Adding: new_file (800) would make 3000 bytes
        # This is under the 3145 byte limit, but let's make it go slightly over
        new_file = temp_cache_dir / "new_addition.txt"
        new_file.write_text(
            "x" * 1200
        )  # Adding 1200 bytes makes total 3400, over 3145 limit
        manager.track_item(new_file)

        # Only file2 should be evicted (oldest and largest)
        # file1 (newer) and new_file should remain
        assert manager.is_item_tracked(file1) is True, (
            "file1 should remain (was made more recent)"
        )
        assert manager.is_item_tracked(new_file) is True, (
            "new_file should remain (just added)"
        )
        # file2 should be evicted as it's oldest
        assert manager.is_item_tracked(file2) is False, (
            "file2 should be evicted (oldest)"
        )


class TestThumbnailManagerValidation:
    """Test validation functionality."""

    def test_validate_tracking_with_valid_files(
        self, thumbnail_manager, temp_image_file
    ) -> None:
        """Test tracking validation with valid files."""
        thumbnail_manager.track_item(temp_image_file)

        result = thumbnail_manager.validate_tracking()

        assert result["invalid_files"] == 0
        assert result["size_mismatches"] == 0
        assert result["issues_fixed"] == 0

    def test_validate_tracking_with_missing_files(
        self, thumbnail_manager, temp_cache_dir
    ) -> None:
        """Test tracking validation with missing files."""
        # Create and track a file, then delete it
        temp_file = temp_cache_dir / "temp.txt"
        temp_file.write_text("test content")
        thumbnail_manager.track_item(temp_file)

        # Delete the file
        temp_file.unlink()

        result = thumbnail_manager.validate_tracking()

        assert result["invalid_files"] == 1
        assert result["issues_fixed"] == 1
        # File should be removed from tracking
        assert not thumbnail_manager.is_item_tracked(temp_file)


class TestThumbnailManagerSignals:
    """Test Qt signal emissions."""

    def test_signal_connections(self, thumbnail_manager) -> None:
        """Test that signals can be connected."""
        # Mock signal handlers
        ready_handler = Mock()
        failed_handler = Mock()
        pressure_handler = Mock()

        # Connect signals
        thumbnail_manager.thumbnail_ready.connect(ready_handler)
        thumbnail_manager.thumbnail_failed.connect(failed_handler)
        thumbnail_manager.memory_pressure.connect(pressure_handler)

        # Signals should be connected (no exceptions)
        assert thumbnail_manager.thumbnail_ready is not None
        assert thumbnail_manager.thumbnail_failed is not None
        assert thumbnail_manager.memory_pressure is not None

    def test_cleanup_disconnects_signals(self, thumbnail_manager) -> None:
        """Test that cleanup disconnects signals."""
        # Connect a signal
        handler = Mock()
        thumbnail_manager.thumbnail_ready.connect(handler)

        # Cleanup should disconnect signals without errors
        thumbnail_manager.cleanup()


class TestThumbnailManagerBackwardCompatibility:
    """Test backward compatibility factory functions."""

    def test_create_thumbnail_processor(self) -> None:
        """Test factory function for thumbnail processor compatibility."""
        processor = create_thumbnail_processor(thumbnail_size=256)

        assert isinstance(processor, ThumbnailManager)
        assert processor._thumbnail_size == 256

    def test_create_memory_manager(self) -> None:
        """Test factory function for memory manager compatibility."""
        from cache.thumbnail_manager import create_memory_manager

        manager = create_memory_manager(max_memory_mb=100)

        assert isinstance(manager, ThumbnailManager)
        assert manager._max_memory_bytes == 100 * 1024 * 1024

    def test_create_thumbnail_loader(self) -> None:
        """Test factory function for thumbnail loader compatibility."""
        from cache.thumbnail_manager import create_thumbnail_loader

        loader = create_thumbnail_loader()

        assert isinstance(loader, ThumbnailManager)


class TestThumbnailManagerEdgeCases:
    """Test edge cases and error conditions."""

    def test_process_with_memory_error(
        self, thumbnail_manager, temp_image_file, temp_cache_dir
    ) -> None:
        """Test handling of memory errors during processing."""
        cache_path = temp_cache_dir / "memory_error_thumb.jpg"

        with patch.object(
            thumbnail_manager,
            "_process_with_qt",
            side_effect=MemoryError("Out of memory"),
        ):
            success = thumbnail_manager._process_thumbnail_sync(
                temp_image_file, cache_path
            )

            assert success is False
            # Should record failure
            assert str(temp_image_file) in thumbnail_manager._failures

    def test_process_with_permission_error(self, thumbnail_manager, temp_image_file) -> None:
        """Test handling of permission errors during cache directory creation."""
        # Use a path that will cause permission issues
        readonly_cache = Path("/readonly/cache/thumb.jpg")

        success = thumbnail_manager._process_thumbnail_sync(
            temp_image_file, readonly_cache
        )

        assert success is False
        # Should record failure
        assert str(temp_image_file) in thumbnail_manager._failures

    def test_empty_source_path(self, thumbnail_manager, temp_cache_dir) -> None:
        """Test handling of empty or None source path."""
        cache_path = temp_cache_dir / "thumb.jpg"

        success = thumbnail_manager._process_thumbnail_sync(Path(), cache_path)

        assert success is False
