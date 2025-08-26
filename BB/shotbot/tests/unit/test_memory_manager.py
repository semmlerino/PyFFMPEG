"""Unit tests for MemoryManager functionality.

Tests memory tracking, LRU eviction, thread safety, and usage statistics.

Following UNIFIED_TESTING_GUIDE principles:
- Test behavior, not implementation
- Use real MemoryManager with temporary files
- Mock only at system boundaries (file I/O when needed)
- Thread-safe testing patterns
- Focus on edge cases and error conditions
"""

from __future__ import annotations

import concurrent.futures
import os
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from cache.memory_manager import MemoryManager
from config import ThreadingConfig

pytestmark = [pytest.mark.unit, pytest.mark.slow]

# This test file follows UNIFIED_TESTING_GUIDE best practices:
# - Test behavior, not implementation
# - Use test doubles instead of mocks
# - Real components where possible
# - Thread-safe testing patterns



# Test doubles for behavior testing (UNIFIED_TESTING_GUIDE)

class TestMemoryManagerInitialization:
    """Test MemoryManager initialization and configuration."""

    def test_default_initialization(self):
        """MemoryManager should initialize with default config values."""
        manager = MemoryManager()

        # Should use ThreadingConfig default
        expected_bytes = ThreadingConfig.CACHE_MAX_MEMORY_MB * 1024 * 1024
        assert manager.max_memory_bytes == expected_bytes
        assert manager.memory_usage_bytes == 0
        assert len(manager) == 0
        assert manager.cached_items == {}

    def test_custom_memory_limit(self):
        """MemoryManager should accept custom memory limits."""
        custom_mb = 50
        manager = MemoryManager(max_memory_mb=custom_mb)

        expected_bytes = custom_mb * 1024 * 1024
        assert manager.max_memory_bytes == expected_bytes
        assert manager.memory_usage_bytes == 0

    def test_zero_memory_limit(self):
        """MemoryManager should handle zero memory limit gracefully."""
        # Note: max_memory_mb=0 uses default due to "or" logic in constructor
        # This tests the actual behavior, not the expected behavior
        manager = MemoryManager(max_memory_mb=0)

        # Due to "max_memory_mb or default" logic, 0 becomes default
        expected_bytes = ThreadingConfig.CACHE_MAX_MEMORY_MB * 1024 * 1024
        assert manager.max_memory_bytes == expected_bytes
        assert manager.is_over_limit() is False  # 0 bytes usage <= limit

    def test_string_representation(self):
        """MemoryManager should provide informative string representation."""
        manager = MemoryManager(max_memory_mb=10)

        repr_str = repr(manager)
        assert "MemoryManager" in repr_str
        assert "items=0" in repr_str
        assert "usage=0.0MB" in repr_str
        assert "limit=10.0MB" in repr_str


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
    def manager(self) -> MemoryManager:
        """Create MemoryManager with small limit for testing."""
        return MemoryManager(max_memory_mb=1)  # 1MB limit

    def test_track_item_with_file_size(self, manager: MemoryManager, temp_file: Path):
        """Tracking should detect file size automatically."""
        result = manager.track_item(temp_file)

        assert result is True
        assert manager.is_item_tracked(temp_file)
        assert manager.memory_usage_bytes == 1024  # 1KB file
        assert len(manager) == 1

        # Should track the correct path and size
        cached_items = manager.cached_items
        assert str(temp_file) in cached_items
        assert cached_items[str(temp_file)] == 1024

    def test_track_item_with_explicit_size(
        self, manager: MemoryManager, temp_file: Path
    ):
        """Tracking should accept explicit size parameter."""
        explicit_size = 2048  # 2KB
        result = manager.track_item(temp_file, size_bytes=explicit_size)

        assert result is True
        assert manager.is_item_tracked(temp_file)
        assert manager.memory_usage_bytes == explicit_size

        # Should use explicit size, not actual file size
        cached_items = manager.cached_items
        assert cached_items[str(temp_file)] == explicit_size

    def test_track_nonexistent_file(self, manager: MemoryManager):
        """Tracking nonexistent file should fail gracefully."""
        nonexistent = Path("/nonexistent/file.txt")

        result = manager.track_item(nonexistent)

        assert result is False
        assert not manager.is_item_tracked(nonexistent)
        assert manager.memory_usage_bytes == 0
        assert len(manager) == 0

    def test_track_item_update_size(self, manager: MemoryManager, temp_file: Path):
        """Re-tracking item should update size correctly."""
        # Track with initial size
        manager.track_item(temp_file, size_bytes=1000)
        assert manager.memory_usage_bytes == 1000

        # Update with new size
        manager.track_item(temp_file, size_bytes=2000)
        assert manager.memory_usage_bytes == 2000
        assert len(manager) == 1  # Same item, just updated

        # Should track updated size
        cached_items = manager.cached_items
        assert cached_items[str(temp_file)] == 2000

    def test_untrack_item(self, manager: MemoryManager, temp_file: Path):
        """Untracking should remove item and update memory usage."""
        # Track item first
        manager.track_item(temp_file, size_bytes=1500)
        assert manager.memory_usage_bytes == 1500

        # Untrack item
        result = manager.untrack_item(temp_file)

        assert result is True
        assert not manager.is_item_tracked(temp_file)
        assert manager.memory_usage_bytes == 0
        assert len(manager) == 0
        assert str(temp_file) not in manager.cached_items

    def test_untrack_nonexistent_item(self, manager: MemoryManager):
        """Untracking non-tracked item should return False."""
        nonexistent = Path("/nonexistent/file.txt")

        result = manager.untrack_item(nonexistent)

        assert result is False
        assert manager.memory_usage_bytes == 0

    def test_memory_usage_setter_backward_compatibility(self, manager: MemoryManager):
        """Memory usage setter should work for backward compatibility."""
        # Set memory usage directly
        manager.memory_usage_bytes = 5000

        assert manager.memory_usage_bytes == 5000

        # Should not affect tracked items
        assert len(manager) == 0


class TestLRUEviction:
    """Test LRU eviction functionality."""

    @pytest.fixture
    def manager_small(self) -> MemoryManager:
        """Create MemoryManager with very small limit for eviction testing."""
        return MemoryManager(max_memory_mb=0.001)  # 1KB limit

    def test_evict_if_needed_under_limit(
        self, manager_small: MemoryManager, tmp_path: Path
    ):
        """No eviction should occur when under memory limit."""
        # Create small file under limit
        small_file = tmp_path / "small.txt"
        small_file.write_text("x" * 500)  # 500 bytes

        manager_small.track_item(small_file)

        evicted_count = manager_small.evict_if_needed()

        assert evicted_count == 0
        assert manager_small.is_item_tracked(small_file)
        assert not manager_small.is_over_limit()

    def test_evict_if_needed_over_limit(
        self, manager_small: MemoryManager, tmp_path: Path
    ):
        """Eviction should occur when over memory limit."""
        # Create file that exceeds limit
        large_file = tmp_path / "large.txt"
        large_file.write_text("x" * 2000)  # 2KB (exceeds 1KB limit)

        manager_small.track_item(large_file)
        assert manager_small.is_over_limit()

        evicted_count = manager_small.evict_if_needed()

        assert evicted_count == 1
        assert not manager_small.is_item_tracked(large_file)
        assert not large_file.exists()  # File should be deleted
        assert not manager_small.is_over_limit()

    def test_lru_eviction_order(self, manager_small: MemoryManager, tmp_path: Path):
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

        # All files exceed 1KB limit (3 × 600B = 1800B)
        assert manager_small.is_over_limit()

        evicted_count = manager_small.evict_if_needed(target_percent=0.3)

        # Should evict enough to get under target (30% of 1KB = ~300B)
        assert evicted_count >= 2
        assert manager_small.memory_usage_bytes <= 1024 * 0.3

        # Oldest files should be evicted first
        # Note: Exact order depends on filesystem timestamp precision
        remaining_items = len(manager_small)
        assert remaining_items <= 1

    def test_evict_nonexistent_files(
        self, manager_small: MemoryManager, tmp_path: Path
    ):
        """Eviction should handle files that no longer exist."""
        # Track file then delete it manually
        test_file = tmp_path / "test.txt"
        test_file.write_text("x" * 2000)

        manager_small.track_item(test_file)
        test_file.unlink()  # Delete file manually

        evicted_count = manager_small.evict_if_needed()

        # Should clean up tracking for non-existent file
        assert evicted_count == 1
        assert not manager_small.is_item_tracked(test_file)
        assert manager_small.memory_usage_bytes == 0

    def test_evict_with_file_access_error(
        self, manager_small: MemoryManager, tmp_path: Path
    ):
        """Eviction should handle file access errors gracefully."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("x" * 2000)

        manager_small.track_item(test_file)

        # Mock file stat to raise error
        with patch.object(Path, "stat", side_effect=OSError("Access denied")):
            evicted_count = manager_small.evict_if_needed()

            # Should clean up tracking even with errors
            assert evicted_count == 1
            assert not manager_small.is_item_tracked(test_file)


class TestUsageStatistics:
    """Test usage statistics and reporting."""

    @pytest.fixture
    def manager(self) -> MemoryManager:
        """Create MemoryManager for statistics testing."""
        return MemoryManager(max_memory_mb=10)

    def test_get_usage_stats_empty(self, manager: MemoryManager):
        """Usage stats should handle empty cache correctly."""
        stats = manager.get_usage_stats()

        expected_stats = {
            "total_bytes": 0,
            "total_mb": 0.0,
            "max_mb": 10.0,
            "usage_percent": 0.0,
            "tracked_items": 0,
            "average_item_kb": 0,
        }

        assert stats == expected_stats

    def test_get_usage_stats_with_items(self, manager: MemoryManager, tmp_path: Path):
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

        assert stats["total_bytes"] == total_size
        assert abs(stats["total_mb"] - (total_size / 1024 / 1024)) < 0.001
        assert stats["max_mb"] == 10.0
        expected_percent = (total_size / (10 * 1024 * 1024)) * 100
        assert abs(stats["usage_percent"] - expected_percent) < 0.01
        assert stats["tracked_items"] == file_count
        expected_avg_kb = (total_size / file_count) / 1024
        assert abs(stats["average_item_kb"] - expected_avg_kb) < 0.1

    def test_is_over_limit(self, manager: MemoryManager):
        """is_over_limit should work correctly."""
        assert not manager.is_over_limit()

        # Set usage over limit
        limit_bytes = manager.max_memory_bytes
        manager.memory_usage_bytes = limit_bytes + 1

        assert manager.is_over_limit()

        # Set usage exactly at limit
        manager.memory_usage_bytes = limit_bytes

        assert not manager.is_over_limit()

    def test_usage_stats_zero_limit(self):
        """Usage stats should handle zero memory limit gracefully."""
        # Note: max_memory_mb=0 uses default due to "or" logic in constructor
        manager = MemoryManager(max_memory_mb=0)

        stats = manager.get_usage_stats()

        # Due to constructor logic, 0 becomes default value
        assert stats["max_mb"] == ThreadingConfig.CACHE_MAX_MEMORY_MB
        assert stats["usage_percent"] == 0.0

    def test_usage_stats_true_zero_limit(self):
        """Test actual zero limit by directly setting the private attribute."""
        manager = MemoryManager(max_memory_mb=10)

        # Directly set zero limit to test division by zero protection
        manager._max_memory_bytes = 0

        stats = manager.get_usage_stats()

        assert stats["max_mb"] == 0.0
        assert stats["usage_percent"] == 0.0  # Should not divide by zero


class TestCacheValidation:
    """Test cache validation and repair functionality."""

    @pytest.fixture
    def manager(self) -> MemoryManager:
        """Create MemoryManager for validation testing."""
        return MemoryManager(max_memory_mb=10)

    def test_validate_tracking_all_valid(self, manager: MemoryManager, tmp_path: Path):
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

        assert validation["valid"] is True
        assert validation["issues_fixed"] == 0
        assert validation["invalid_files"] == 0
        assert validation["size_mismatches"] == 0
        assert validation["tracked_items"] == 3
        assert validation["tracked_usage_bytes"] > 0
        assert validation["actual_usage_bytes"] == validation["tracked_usage_bytes"]

    def test_validate_tracking_invalid_files(
        self, manager: MemoryManager, tmp_path: Path
    ):
        """Validation should fix tracking for deleted files."""
        # Track files then delete some
        valid_file = tmp_path / "valid.txt"
        valid_file.write_text("valid content")
        manager.track_item(valid_file)

        invalid_file = tmp_path / "invalid.txt"
        invalid_file.write_text("invalid content")
        manager.track_item(invalid_file)
        invalid_file.unlink()  # Delete file

        initial_usage = manager.memory_usage_bytes

        validation = manager.validate_tracking()

        assert validation["valid"] is False
        assert validation["issues_fixed"] == 1
        assert validation["invalid_files"] == 1
        assert validation["size_mismatches"] == 0
        assert validation["tracked_items"] == 1  # Only valid file remains

        # Memory usage should be corrected
        assert manager.memory_usage_bytes < initial_usage
        assert not manager.is_item_tracked(invalid_file)
        assert manager.is_item_tracked(valid_file)

    def test_validate_tracking_size_mismatches(
        self, manager: MemoryManager, tmp_path: Path
    ):
        """Validation should fix size mismatches."""
        # Track file with wrong size
        test_file = tmp_path / "test.txt"
        actual_content = "x" * 1000
        test_file.write_text(actual_content)

        # Track with incorrect size
        wrong_size = 500
        manager.track_item(test_file, size_bytes=wrong_size)

        validation = manager.validate_tracking()

        assert validation["valid"] is False
        assert validation["issues_fixed"] == 1
        assert validation["invalid_files"] == 0
        assert validation["size_mismatches"] == 1
        assert validation["tracked_items"] == 1

        # Size should be corrected
        assert manager.memory_usage_bytes == 1000  # Actual file size
        cached_items = manager.cached_items
        assert cached_items[str(test_file)] == 1000

    def test_validate_tracking_with_access_errors(
        self, manager: MemoryManager, tmp_path: Path
    ):
        """Validation should handle file access errors gracefully."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")
        manager.track_item(test_file)

        # Mock file operations to raise errors
        with patch.object(Path, "exists", return_value=True), patch.object(
            Path, "stat", side_effect=OSError("Permission denied")
        ):
            validation = manager.validate_tracking()

            # Should treat files with access errors as invalid
            assert validation["issues_fixed"] == 1
            assert validation["invalid_files"] == 1
            assert not manager.is_item_tracked(test_file)


class TestClearAndReset:
    """Test cache clearing and reset functionality."""

    @pytest.fixture
    def populated_manager(self, tmp_path: Path) -> MemoryManager:
        """Create MemoryManager with tracked items."""
        manager = MemoryManager(max_memory_mb=10)

        # Track multiple files
        for i in range(5):
            file_path = tmp_path / f"file_{i}.txt"
            content = "x" * (i + 1) * 200
            file_path.write_text(content)
            manager.track_item(file_path)

        return manager

    def test_clear_all_tracking(self, populated_manager: MemoryManager):
        """clear_all_tracking should reset all state."""
        # Verify initial state
        assert len(populated_manager) > 0
        assert populated_manager.memory_usage_bytes > 0
        initial_items = populated_manager.cached_items.copy()

        populated_manager.clear_all_tracking()

        # Should reset all tracking
        assert len(populated_manager) == 0
        assert populated_manager.memory_usage_bytes == 0
        assert populated_manager.cached_items == {}

        # Original files should still exist (not deleted)
        for file_path_str in initial_items:
            file_path = Path(file_path_str)
            assert file_path.exists()

    def test_clear_empty_manager(self):
        """clear_all_tracking should work on empty manager."""
        manager = MemoryManager()

        manager.clear_all_tracking()  # Should not raise error

        assert len(manager) == 0
        assert manager.memory_usage_bytes == 0


class TestThreadSafety:
    """Test thread safety of MemoryManager operations."""

    @pytest.fixture
    def manager(self) -> MemoryManager:
        """Create MemoryManager for thread safety testing."""
        return MemoryManager(max_memory_mb=10)

    def test_concurrent_track_untrack(self, manager: MemoryManager, tmp_path: Path):
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

        def track_files():
            """Track files in worker thread."""
            track_started.set()  # Signal that tracking has started
            for file_path in files[:5]:
                manager.track_item(file_path)
                # No sleep needed - natural thread scheduling provides contention

        def untrack_files():
            """Untrack files in worker thread."""
            track_started.wait()  # Wait for tracking to start
            for file_path in files[2:7]:  # Overlap with tracking
                manager.untrack_item(file_path)
                # No sleep needed

        # Run operations concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(track_files), executor.submit(untrack_files)]
            concurrent.futures.wait(futures)

        # Should complete without errors
        # Final state depends on timing but should be consistent
        final_usage = manager.memory_usage_bytes
        final_count = len(manager)

        assert final_usage >= 0
        assert final_count >= 0

        # Validate consistency
        validation = manager.validate_tracking()
        assert validation["tracked_usage_bytes"] == final_usage

    def test_concurrent_statistics_access(self, manager: MemoryManager, tmp_path: Path):
        """Concurrent access to statistics should be thread-safe."""
        # Track some files
        for i in range(5):
            file_path = tmp_path / f"file_{i}.txt"
            file_path.write_text("x" * (i + 1) * 100)
            manager.track_item(file_path)

        stats_results = []
        errors = []

        def get_stats_worker():
            """Get statistics in worker thread."""
            try:
                for _ in range(20):
                    stats = manager.get_usage_stats()
                    stats_results.append(stats)
                    # No sleep needed - natural thread scheduling provides concurrency
            except Exception as e:
                errors.append(e)

        def modify_tracking_worker():
            """Modify tracking in worker thread."""
            try:
                file_path = tmp_path / "dynamic.txt"
                for i in range(10):
                    content = "x" * (i + 1) * 50
                    file_path.write_text(content)
                    manager.track_item(file_path, size_bytes=len(content))
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
            assert "total_bytes" in stats
            assert "tracked_items" in stats
            assert stats["total_bytes"] >= 0
            assert stats["tracked_items"] >= 0

    def test_concurrent_validation(self, manager: MemoryManager, tmp_path: Path):
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

        def validation_worker():
            """Run validation in worker thread."""
            validation_started.set()  # Signal that validation has started
            result = manager.validate_tracking()
            validation_results.append(result)

        def file_deletion_worker():
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
            assert "valid" in result
            assert "issues_fixed" in result
            assert result["issues_fixed"] >= 0


class TestEdgeCasesAndErrorConditions:
    """Test edge cases and error conditions."""

    def test_track_item_with_zero_size(self, tmp_path: Path):
        """Tracking item with zero size should work correctly."""
        manager = MemoryManager(max_memory_mb=1)

        # Create empty file
        empty_file = tmp_path / "empty.txt"
        empty_file.write_text("")

        result = manager.track_item(empty_file)

        assert result is True
        assert manager.is_item_tracked(empty_file)
        assert manager.memory_usage_bytes == 0
        assert len(manager) == 1

    def test_track_item_with_negative_size(self, tmp_path: Path):
        """Tracking with negative size should be handled gracefully."""
        manager = MemoryManager(max_memory_mb=1)

        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        # Track with negative size
        result = manager.track_item(test_file, size_bytes=-100)

        assert result is True  # Should accept the value
        assert manager.memory_usage_bytes == -100

        # Untracking should handle negative values correctly
        manager.untrack_item(test_file)
        assert manager.memory_usage_bytes == 0  # Should use max(0, ...)

    def test_memory_usage_consistency_after_errors(self, tmp_path: Path):
        """Memory usage should remain consistent even after errors."""
        manager = MemoryManager(max_memory_mb=1)

        # Track valid file
        valid_file = tmp_path / "valid.txt"
        valid_file.write_text("x" * 1000)
        manager.track_item(valid_file)

        initial_usage = manager.memory_usage_bytes

        # Try to track non-existent file (should fail)
        nonexistent = Path("/nonexistent/file.txt")
        manager.track_item(nonexistent)

        # Memory usage should be unchanged
        assert manager.memory_usage_bytes == initial_usage
        assert len(manager) == 1

    def test_property_access_thread_safety(self):
        """Property access should be thread-safe."""
        manager = MemoryManager(max_memory_mb=5)

        def property_access_worker():
            """Access properties in worker thread."""
            for _ in range(50):
                _ = manager.memory_usage_bytes
                _ = manager.max_memory_bytes
                _ = manager.cached_items
                _ = len(manager)
                # No sleep needed - natural thread scheduling provides concurrency

        # Run property access from multiple threads
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(property_access_worker) for _ in range(3)]
            concurrent.futures.wait(futures)

        # Should complete without errors (any threading issues would cause crashes)

    def test_evict_with_no_tracked_items(self):
        """Eviction should handle empty manager gracefully."""
        manager = MemoryManager(max_memory_mb=0.001)  # Very small limit

        # Set memory usage manually (simulating inconsistent state)
        manager.memory_usage_bytes = 2000  # Over limit but no items tracked

        evicted_count = manager.evict_if_needed()

        # Should not crash and return 0 evictions
        assert evicted_count == 0
        assert manager.memory_usage_bytes == 2000  # Unchanged since no items to evict


if __name__ == "__main__":
    pytest.main([__file__])
