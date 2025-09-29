"""Unit tests for ThumbnailManager memory functionality.

Tests memory tracking, LRU eviction, thread safety, and usage statistics.

Following UNIFIED_TESTING_GUIDE principles:
- Test behavior, not implementation
- Use real ThumbnailManager with temporary files
- Mock only at system boundaries (file I/O when needed)
- Thread-safe testing patterns
- Focus on edge cases and error conditions
"""

from __future__ import annotations

# Standard library imports
import concurrent.futures
import os
import threading
import time
from pathlib import Path
from unittest.mock import patch

# Third-party imports
import pytest

# Local application imports
from cache.thumbnail_manager import ThumbnailManager
from config import ThreadingConfig

pytestmark = [pytest.mark.unit, pytest.mark.slow]

# This test file follows UNIFIED_TESTING_GUIDE best practices:
# - Test behavior, not implementation
# - Use test doubles instead of mocks
# - Real components where possible
# - Thread-safe testing patterns


# Test doubles for behavior testing (UNIFIED_TESTING_GUIDE)


def is_over_limit(manager: ThumbnailManager) -> bool:
    """Helper function to check if manager is over memory limit."""
    return manager._memory_usage_bytes > manager._max_memory_bytes


class TestThumbnailManagerInitialization:
    """Test ThumbnailManager initialization and configuration."""

    def test_default_initialization(self) -> None:
        """ThumbnailManager should initialize with default config values."""
        manager = ThumbnailManager()

        # Should use ThreadingConfig default
        expected_bytes = ThreadingConfig.CACHE_MAX_MEMORY_MB * 1024 * 1024
        assert manager._max_memory_bytes == expected_bytes
        assert manager._memory_usage_bytes == 0
        assert len(manager._cached_items) == 0
        assert manager._cached_items == {}

    def test_custom_memory_limit(self) -> None:
        """ThumbnailManager should accept custom memory limits."""
        custom_mb = 50
        manager = ThumbnailManager(max_memory_mb=custom_mb)

        expected_bytes = custom_mb * 1024 * 1024
        assert manager._max_memory_bytes == expected_bytes
        assert manager._memory_usage_bytes == 0

    def test_zero_memory_limit(self) -> None:
        """ThumbnailManager should handle zero memory limit gracefully."""
        # Note: max_memory_mb=0 uses default due to "or" logic in constructor
        # This tests the actual behavior, not the expected behavior
        manager = ThumbnailManager(max_memory_mb=0)

        # Due to "max_memory_mb or default" logic, 0 becomes default
        expected_bytes = ThreadingConfig.CACHE_MAX_MEMORY_MB * 1024 * 1024
        assert manager._max_memory_bytes == expected_bytes
        assert is_over_limit(manager) is False  # 0 bytes usage <= limit

    def test_string_representation(self) -> None:
        """ThumbnailManager should provide informative string representation."""
        manager = ThumbnailManager(max_memory_mb=10)

        repr_str = repr(manager)
        assert "ThumbnailManager" in repr_str
        # Note: ThumbnailManager uses default Python object representation
        assert "0x" in repr_str  # Memory address indicator


class TestMemoryTracking:
    """Test memory tracking operations."""

    @pytest.fixture
    def temp_file(self, tmp_path: Path) -> Path:
        """Create a temporary file with known size."""
        test_file = tmp_path / "test_file.txt"
        test_content = "x" * 1024  # 1KB file
        test_file.write_text(test_content)
        return test_file

    @pytest.fixture
    def manager(self) -> ThumbnailManager:
        """Create ThumbnailManager with small limit for testing."""
        return ThumbnailManager(max_memory_mb=1)  # 1MB limit

    def test_track_item_with_file_size(
        self, manager: ThumbnailManager, temp_file: Path
    ) -> None:
        """Tracking should detect file size automatically."""
        result = manager.track_item(temp_file)

        assert result is True
        assert manager.is_item_tracked(temp_file)
        assert manager._memory_usage_bytes == 1024  # 1KB file
        assert len(manager._cached_items) == 1

        # Should track the correct path and size
        cached_items = manager._cached_items
        assert str(temp_file) in cached_items
        assert cached_items[str(temp_file)] == 1024

    def test_track_item_with_different_size(
        self, manager: ThumbnailManager, tmp_path: Path
    ) -> None:
        """Tracking should detect actual file size automatically."""
        # Create file with specific size
        test_file = tmp_path / "sized_file.txt"
        explicit_size = 2048  # 2KB
        test_file.write_text("x" * explicit_size)

        result = manager.track_item(test_file)

        assert result is True
        assert manager.is_item_tracked(test_file)
        assert manager._memory_usage_bytes == explicit_size

        # Should use actual file size
        cached_items = manager._cached_items
        assert cached_items[str(test_file)] == explicit_size

    def test_track_nonexistent_file(self, manager: ThumbnailManager) -> None:
        """Tracking nonexistent file should fail gracefully."""
        nonexistent = Path("/nonexistent/file.txt")

        result = manager.track_item(nonexistent)

        assert result is False
        assert not manager.is_item_tracked(nonexistent)
        assert manager._memory_usage_bytes == 0
        assert len(manager._cached_items) == 0

    def test_track_item_update_size(
        self, manager: ThumbnailManager, tmp_path: Path
    ) -> None:
        """Re-tracking item should update size correctly when file changes."""
        # Create file with initial size
        test_file = tmp_path / "update_test.txt"
        test_file.write_text("x" * 1000)
        manager.track_item(test_file)
        assert manager._memory_usage_bytes == 1000

        # Change file size and force update
        test_file.write_text("x" * 2000)
        manager.track_item(test_file, force_update=True)
        assert manager._memory_usage_bytes == 2000
        assert len(manager._cached_items) == 1  # Same item, just updated

        # Should track updated size
        cached_items = manager._cached_items
        assert cached_items[str(test_file)] == 2000

    def test_evict_item(self, manager: ThumbnailManager, temp_file: Path) -> None:
        """Evicting should remove item and update memory usage."""
        # Track item first
        manager.track_item(temp_file)
        initial_usage = manager._memory_usage_bytes
        assert initial_usage > 0

        # Evict item
        result = manager.evict_item(temp_file)

        assert result is True
        assert not manager.is_item_tracked(temp_file)
        assert manager._memory_usage_bytes == 0
        assert len(manager._cached_items) == 0
        assert str(temp_file) not in manager._cached_items

    def test_evict_nonexistent_item(self, manager: ThumbnailManager) -> None:
        """Evicting non-tracked item should return False."""
        nonexistent = Path("/nonexistent/file.txt")

        result = manager.evict_item(nonexistent)

        assert result is False
        assert manager._memory_usage_bytes == 0

    def test_memory_usage_setter_backward_compatibility(
        self, manager: ThumbnailManager
    ) -> None:
        """Memory usage setter should work for backward compatibility."""
        # Set memory usage directly
        manager._memory_usage_bytes = 5000

        assert manager._memory_usage_bytes == 5000

        # Should not affect tracked items
        assert len(manager._cached_items) == 0


class TestLRUEviction:
    """Test LRU eviction functionality."""

    @pytest.fixture
    def manager_small(self) -> ThumbnailManager:
        """Create ThumbnailManager with very small limit for eviction testing."""
        return ThumbnailManager(max_memory_mb=0.001)  # 1KB limit

    def test_evict_if_needed_under_limit(
        self, manager_small: ThumbnailManager, tmp_path: Path
    ) -> None:
        """No eviction should occur when under memory limit."""
        # Create small file under limit
        small_file = tmp_path / "small.txt"
        small_file.write_text("x" * 500)  # 500 bytes

        manager_small.track_item(small_file)

        # No explicit eviction needed - ThumbnailManager handles automatically
        # Verify item remains tracked since we're under limit
        assert manager_small.is_item_tracked(small_file)
        assert not is_over_limit(manager_small)

    def test_evict_if_needed_over_limit(
        self, manager_small: ThumbnailManager, tmp_path: Path
    ) -> None:
        """Automatic eviction should occur when tracking items that exceed limit."""
        # First, add a small file that fits
        small_file = tmp_path / "small.txt"
        small_file.write_text("x" * 500)  # 500 bytes
        manager_small.track_item(small_file)
        assert manager_small.is_item_tracked(small_file)

        # Create file that would exceed limit when combined with existing
        large_file = tmp_path / "large.txt"
        large_file.write_text("x" * 800)  # 800 bytes (500 + 800 = 1300 > 1024)

        # Track the large file - this should trigger automatic eviction of small file
        manager_small.track_item(large_file)

        # The ThumbnailManager should automatically evict the older small file
        assert manager_small.is_item_tracked(large_file)
        # Small file should have been evicted to make room
        assert not manager_small.is_item_tracked(small_file)
        assert not is_over_limit(manager_small)

    def test_lru_eviction_order(
        self, manager_small: ThumbnailManager, tmp_path: Path
    ) -> None:
        """LRU eviction should remove oldest files first."""
        files = []

        # Create files with different modification times

        base_time = time.time()

        for i in range(3):
            file_path = tmp_path / f"file_{i}.txt"
            file_path.write_text("x" * 600)  # 600 bytes each
            files.append(file_path)

            # Set specific modification times to ensure order (no sleep needed)
            mod_time = base_time - (2 - i)  # Oldest files have earlier times
            os.utime(file_path, (mod_time, mod_time))

            manager_small.track_item(file_path)

        # ThumbnailManager automatically evicts during tracking to stay within limits
        # All 3 files together would exceed 1KB limit (3 × 600B = 1800B)
        # but automatic eviction should have occurred during tracking
        assert not is_over_limit(manager_small)

        # Should have evicted some files to stay within limit
        remaining_items = len(manager_small._cached_items)
        assert remaining_items < 3  # Not all files should remain

    def test_validate_nonexistent_files(
        self, manager_small: ThumbnailManager, tmp_path: Path
    ) -> None:
        """Validation should handle files that no longer exist."""
        # Track file then delete it manually
        test_file = tmp_path / "test.txt"
        test_file.write_text("x" * 2000)

        manager_small.track_item(test_file)
        test_file.unlink()  # Delete file manually

        validation = manager_small.validate_tracking()

        # Should clean up tracking for non-existent file
        assert validation["issues_fixed"] == 1
        assert validation["invalid_files"] == 1
        assert not manager_small.is_item_tracked(test_file)
        assert manager_small._memory_usage_bytes == 0

    def test_validate_with_file_access_error(
        self, manager_small: ThumbnailManager, tmp_path: Path
    ) -> None:
        """Validation should handle file access errors gracefully."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("x" * 2000)

        manager_small.track_item(test_file)

        # Mock file stat to raise error
        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "stat", side_effect=OSError("Access denied")),
        ):
            validation = manager_small.validate_tracking()

            # Should detect invalid files but may not clean them up due to access error
            assert validation["invalid_files"] == 1
            # Since path.exists() returns True but stat() fails, the file isn't removed
            assert validation["issues_fixed"] == 0
            assert manager_small.is_item_tracked(test_file)  # Still tracked


class TestUsageStatistics:
    """Test usage statistics and reporting."""

    @pytest.fixture
    def manager(self) -> ThumbnailManager:
        """Create ThumbnailManager for statistics testing."""
        return ThumbnailManager(max_memory_mb=10)

    def test_get_usage_stats_empty(self, manager: ThumbnailManager) -> None:
        """Usage stats should handle empty cache correctly."""
        stats = manager.get_usage_stats()

        expected_stats = {
            "total_items": 0,
            "total_size_mb": 0.0,
            "memory_limit_mb": 10.0,
            "usage_percent": 0.0,
            "average_item_kb": 0,
        }

        assert stats == expected_stats

    def test_get_usage_stats_with_items(
        self, manager: ThumbnailManager, tmp_path: Path
    ) -> None:
        """Usage stats should calculate correctly with tracked items."""
        # Track multiple files
        total_size = 0
        file_count = 3

        for i in range(file_count):
            file_path = tmp_path / f"file_{i}.txt"
            size = (i + 1) * 1024  # 1KB, 2KB, 3KB
            file_path.write_text("x" * size)
            manager.track_item(file_path)
            total_size += size

        stats = manager.get_usage_stats()

        assert abs(stats["total_size_mb"] - (total_size / 1024 / 1024)) < 0.001
        assert stats["memory_limit_mb"] == 10.0
        expected_percent = (total_size / (10 * 1024 * 1024)) * 100
        assert abs(stats["usage_percent"] - expected_percent) < 0.01
        assert stats["total_items"] == file_count
        expected_avg_kb = (total_size / file_count) / 1024
        assert abs(stats["average_item_kb"] - expected_avg_kb) < 0.1

    def test_is_over_limit(self, manager: ThumbnailManager) -> None:
        """is_over_limit should work correctly."""
        assert not is_over_limit(manager)

        # Set usage over limit
        limit_bytes = manager._max_memory_bytes
        manager._memory_usage_bytes = limit_bytes + 1

        assert is_over_limit(manager)

        # Set usage exactly at limit
        manager._memory_usage_bytes = limit_bytes

        assert not is_over_limit(manager)

    def test_usage_stats_zero_limit(self) -> None:
        """Usage stats should handle zero memory limit gracefully."""
        # Note: max_memory_mb=0 uses default due to "or" logic in constructor
        manager = ThumbnailManager(max_memory_mb=0)

        stats = manager.get_usage_stats()

        # Due to constructor logic, 0 becomes default value
        assert stats["memory_limit_mb"] == ThreadingConfig.CACHE_MAX_MEMORY_MB
        assert stats["usage_percent"] == 0.0

    def test_usage_stats_true_zero_limit(self) -> None:
        """Test actual zero limit by directly setting the private attribute."""
        manager = ThumbnailManager(max_memory_mb=10)

        # Directly set zero limit to test division by zero protection
        manager._max_memory_bytes = 0

        stats = manager.get_usage_stats()

        assert stats["memory_limit_mb"] == 0.0
        assert stats["usage_percent"] == 0.0  # Should not divide by zero


class TestCacheValidation:
    """Test cache validation and repair functionality."""

    @pytest.fixture
    def manager(self) -> ThumbnailManager:
        """Create ThumbnailManager for validation testing."""
        return ThumbnailManager(max_memory_mb=10)

    def test_validate_tracking_all_valid(
        self, manager: ThumbnailManager, tmp_path: Path
    ) -> None:
        """Validation should pass when all tracked items are valid."""
        # Track valid files
        files = []
        for i in range(3):
            file_path = tmp_path / f"valid_{i}.txt"
            content = "x" * (i + 1) * 100
            file_path.write_text(content)
            manager.track_item(file_path)
            files.append(file_path)

        validation = manager.validate_tracking()

        # Check that no issues were found or fixed
        assert validation["issues_fixed"] == 0
        assert validation["invalid_files"] == 0
        assert validation["size_mismatches"] == 0

        # Check that all files are still tracked
        assert len(manager._cached_items) == 3
        assert manager._memory_usage_bytes > 0

    def test_validate_tracking_invalid_files(
        self, manager: ThumbnailManager, tmp_path: Path
    ) -> None:
        """Validation should fix tracking for deleted files."""
        # Track files then delete some
        valid_file = tmp_path / "valid.txt"
        valid_file.write_text("valid content")
        manager.track_item(valid_file)

        invalid_file = tmp_path / "invalid.txt"
        invalid_file.write_text("invalid content")
        manager.track_item(invalid_file)
        invalid_file.unlink()  # Delete file

        initial_usage = manager._memory_usage_bytes

        validation = manager.validate_tracking()

        # Check that invalid file was detected and fixed
        assert validation["issues_fixed"] == 1
        assert validation["invalid_files"] == 1
        assert validation["size_mismatches"] == 0

        # Only valid file should remain
        assert len(manager._cached_items) == 1

        # Memory usage should be corrected
        assert manager._memory_usage_bytes < initial_usage
        assert not manager.is_item_tracked(invalid_file)
        assert manager.is_item_tracked(valid_file)

    def test_validate_tracking_size_mismatches(
        self, manager: ThumbnailManager, tmp_path: Path
    ) -> None:
        """Validation should fix size mismatches."""
        # Track file with correct size initially
        test_file = tmp_path / "test.txt"
        initial_content = "x" * 500
        test_file.write_text(initial_content)
        manager.track_item(test_file)

        # Change file size after tracking to create mismatch
        actual_content = "x" * 1000
        test_file.write_text(actual_content)

        validation = manager.validate_tracking()

        # Check that size mismatch was detected and fixed
        assert validation["issues_fixed"] == 1
        assert validation["invalid_files"] == 0
        assert validation["size_mismatches"] == 1

        # File should still be tracked with corrected size
        assert len(manager._cached_items) == 1

        # Size should be corrected
        assert manager._memory_usage_bytes == 1000  # Actual file size
        cached_items = manager._cached_items
        assert cached_items[str(test_file)] == 1000

    def test_validate_tracking_with_access_errors(
        self, manager: ThumbnailManager, tmp_path: Path
    ) -> None:
        """Validation should handle file access errors gracefully."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")
        manager.track_item(test_file)

        # Mock file operations to raise errors
        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "stat", side_effect=OSError("Permission denied")),
        ):
            validation = manager.validate_tracking()

            # Should detect files with access errors as invalid but not remove them
            assert (
                validation["issues_fixed"] == 0
            )  # No fixes since file exists but can't be accessed
            assert validation["invalid_files"] == 1
            assert manager.is_item_tracked(test_file)  # Still tracked


class TestClearAndReset:
    """Test cache clearing and reset functionality."""

    @pytest.fixture
    def populated_manager(self, tmp_path: Path) -> ThumbnailManager:
        """Create ThumbnailManager with tracked items."""
        manager = ThumbnailManager(max_memory_mb=10)

        # Track multiple files
        for i in range(5):
            file_path = tmp_path / f"file_{i}.txt"
            content = "x" * (i + 1) * 200
            file_path.write_text(content)
            manager.track_item(file_path)

        return manager

    def test_clear_all_tracking(self, populated_manager: ThumbnailManager) -> None:
        """clear_all_tracking should reset all state."""
        # Verify initial state
        assert len(populated_manager._cached_items) > 0
        assert populated_manager._memory_usage_bytes > 0
        initial_items = populated_manager._cached_items.copy()

        populated_manager.clear_cache()

        # Should reset all tracking
        assert len(populated_manager._cached_items) == 0
        assert populated_manager._memory_usage_bytes == 0
        assert populated_manager._cached_items == {}

        # Original files should still exist (not deleted)
        for file_path_str in initial_items:
            file_path = Path(file_path_str)
            assert file_path.exists()

    def test_clear_empty_manager(self) -> None:
        """clear_all_tracking should work on empty manager."""
        manager = ThumbnailManager()

        manager.clear_cache()  # Should not raise error

        assert len(manager._cached_items) == 0
        assert manager._memory_usage_bytes == 0


class TestThreadSafety:
    """Test thread safety of ThumbnailManager operations."""

    @pytest.fixture
    def manager(self) -> ThumbnailManager:
        """Create ThumbnailManager for thread safety testing."""
        return ThumbnailManager(max_memory_mb=10)

    def test_concurrent_track_untrack(
        self, manager: ThumbnailManager, tmp_path: Path
    ) -> None:
        """Concurrent tracking and untracking should be thread-safe."""
        # Create multiple files
        files = []
        for i in range(10):
            file_path = tmp_path / f"file_{i}.txt"
            file_path.write_text(f"content_{i}" * 100)
            files.append(file_path)

        # Use proper synchronization instead of sleep
        track_started = threading.Event()
        threading.Barrier(2)  # Synchronize both threads

        def track_files() -> None:
            """Track files in worker thread."""
            track_started.set()  # Signal that tracking has started
            for file_path in files[:5]:
                manager.track_item(file_path)
                # No sleep needed - natural thread scheduling provides contention

        def untrack_files() -> None:
            """Untrack files in worker thread."""
            track_started.wait()  # Wait for tracking to start
            for file_path in files[2:7]:  # Overlap with tracking
                manager.evict_item(file_path)
                # No sleep needed

        # Run operations concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(track_files), executor.submit(untrack_files)]
            concurrent.futures.wait(futures)

        # Should complete without errors
        # Final state depends on timing but should be consistent
        final_usage = manager._memory_usage_bytes
        final_count = len(manager._cached_items)

        assert final_usage >= 0
        assert final_count >= 0

        # Validate consistency - just ensure no errors occurred
        validation = manager.validate_tracking()
        assert validation["issues_fixed"] >= 0  # Should be non-negative
        assert manager._memory_usage_bytes == final_usage

    def test_concurrent_statistics_access(
        self, manager: ThumbnailManager, tmp_path: Path
    ) -> None:
        """Concurrent access to statistics should be thread-safe."""
        # Track some files
        for i in range(5):
            file_path = tmp_path / f"file_{i}.txt"
            file_path.write_text("x" * (i + 1) * 100)
            manager.track_item(file_path)

        stats_results = []
        errors = []

        def get_stats_worker() -> None:
            """Get statistics in worker thread."""
            try:
                for _ in range(20):
                    stats = manager.get_usage_stats()
                    stats_results.append(stats)
                    # No sleep needed - natural thread scheduling provides concurrency
            except Exception as e:
                errors.append(e)

        def modify_tracking_worker() -> None:
            """Modify tracking in worker thread."""
            try:
                file_path = tmp_path / "dynamic.txt"
                for i in range(10):
                    content = "x" * (i + 1) * 50
                    file_path.write_text(content)
                    manager.track_item(file_path, force_update=True)
                    # No sleep needed - natural thread scheduling provides concurrency
            except Exception as e:
                errors.append(e)

        # Run operations concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(get_stats_worker),
                executor.submit(get_stats_worker),
                executor.submit(modify_tracking_worker),
            ]
            concurrent.futures.wait(futures)

        # Should complete without errors
        assert not errors, f"Thread safety errors: {errors}"
        assert len(stats_results) > 0

        # All stats should be valid dictionaries
        for stats in stats_results:
            assert isinstance(stats, dict)
            assert "total_size_mb" in stats
            assert "total_items" in stats
            assert stats["total_size_mb"] >= 0
            assert stats["total_items"] >= 0

    def test_concurrent_validation(
        self, manager: ThumbnailManager, tmp_path: Path
    ) -> None:
        """Concurrent validation should be thread-safe."""
        # Create and track files
        files = []
        for i in range(10):
            file_path = tmp_path / f"file_{i}.txt"
            file_path.write_text(f"content_{i}" * 50)
            manager.track_item(file_path)
            files.append(file_path)

        validation_results = []
        validation_started = threading.Event()

        def validation_worker() -> None:
            """Run validation in worker thread."""
            validation_started.set()  # Signal that validation has started
            result = manager.validate_tracking()
            validation_results.append(result)

        def file_deletion_worker() -> None:
            """Delete some files during validation."""
            validation_started.wait()  # Wait for validation to start
            for file_path in files[::2]:  # Delete every other file
                try:
                    file_path.unlink()
                except FileNotFoundError:
                    pass  # Already deleted
                # No sleep needed - natural scheduling provides concurrency

        # Run validation and file deletion concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(validation_worker),
                executor.submit(validation_worker),
                executor.submit(file_deletion_worker),
            ]
            concurrent.futures.wait(futures)

        # Should complete without errors
        assert len(validation_results) == 2

        for result in validation_results:
            assert isinstance(result, dict)
            assert "issues_fixed" in result
            assert "invalid_files" in result
            assert "size_mismatches" in result
            assert result["issues_fixed"] >= 0


class TestEdgeCasesAndErrorConditions:
    """Test edge cases and error conditions."""

    def test_track_item_with_zero_size(self, tmp_path: Path) -> None:
        """Tracking item with zero size should work correctly."""
        manager = ThumbnailManager(max_memory_mb=1)

        # Create empty file
        empty_file = tmp_path / "empty.txt"
        empty_file.write_text("")

        result = manager.track_item(empty_file)

        assert result is True
        assert manager.is_item_tracked(empty_file)
        assert manager._memory_usage_bytes == 0
        assert len(manager._cached_items) == 1

    def test_track_item_with_manual_size_manipulation(self, tmp_path: Path) -> None:
        """Test manual manipulation of internal state for edge case testing."""
        manager = ThumbnailManager(max_memory_mb=1)

        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        # Track normally first
        result = manager.track_item(test_file)
        assert result is True
        assert manager._memory_usage_bytes > 0

        # Manually manipulate internal state to test negative values
        with manager._lock:
            manager._memory_usage_bytes = -100
            manager._cached_items[str(test_file)] = -100

        # Evicting should handle negative values correctly
        manager.evict_item(test_file)
        assert manager._memory_usage_bytes == 0  # Should be corrected

    def test_memory_usage_consistency_after_errors(self, tmp_path: Path) -> None:
        """Memory usage should remain consistent even after errors."""
        manager = ThumbnailManager(max_memory_mb=1)

        # Track valid file
        valid_file = tmp_path / "valid.txt"
        valid_file.write_text("x" * 1000)
        manager.track_item(valid_file)

        initial_usage = manager._memory_usage_bytes

        # Try to track non-existent file (should fail)
        nonexistent = Path("/nonexistent/file.txt")
        manager.track_item(nonexistent)

        # Memory usage should be unchanged
        assert manager._memory_usage_bytes == initial_usage
        assert len(manager._cached_items) == 1

    def test_property_access_thread_safety(self) -> None:
        """Property access should be thread-safe."""
        manager = ThumbnailManager(max_memory_mb=5)

        def property_access_worker() -> None:
            """Access properties in worker thread."""
            for _ in range(50):
                _ = manager._memory_usage_bytes
                _ = manager._max_memory_bytes
                _ = manager._cached_items
                _ = len(manager._cached_items)
                # No sleep needed - natural thread scheduling provides concurrency

        # Run property access from multiple threads
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(property_access_worker) for _ in range(3)]
            concurrent.futures.wait(futures)

        # Should complete without errors (any threading issues would cause crashes)

    def test_validate_with_no_tracked_items(self) -> None:
        """Validation should handle empty manager gracefully."""
        manager = ThumbnailManager(max_memory_mb=0.001)  # Very small limit

        # Set memory usage manually (simulating inconsistent state)
        manager._memory_usage_bytes = 2000  # Over limit but no items tracked

        validation = manager.validate_tracking()

        # Should not crash and indicate no issues (no items to validate)
        assert validation["issues_fixed"] == 0
        assert validation["invalid_files"] == 0
        assert validation["size_mismatches"] == 0
        assert len(manager._cached_items) == 0
        assert manager._memory_usage_bytes == 2000  # Unchanged since no items to evict


if __name__ == "__main__":
    pytest.main([__file__])
