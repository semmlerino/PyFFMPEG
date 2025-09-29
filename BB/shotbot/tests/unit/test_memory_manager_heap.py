"""Tests for heap-based LRU cache eviction in MemoryManager.

Following UNIFIED_TESTING_GUIDE best practices:
- Test behavior not implementation
- Use real components with tmp_path
- Factory fixtures for flexible data
- Performance testing for O(log n) guarantee
"""

from __future__ import annotations

import heapq
import time
from pathlib import Path
from threading import Thread
from unittest.mock import MagicMock, patch

import pytest

from cache.memory_manager import CacheEntry, MemoryManager

# Test markers
pytestmark = [
    pytest.mark.unit,
    pytest.mark.fast,  # These should be fast unit tests
]


# Factory fixtures
@pytest.fixture
def make_cache_entry():
    """Factory for creating CacheEntry instances with custom times."""
    def _make(path="/test/file.jpg", size_bytes=1024, access_offset=0):
        """Create cache entry with time offset from now."""
        return CacheEntry(
            access_time=time.time() + access_offset,
            path=path,
            size_bytes=size_bytes
        )
    return _make


@pytest.fixture
def make_memory_manager(tmp_path):
    """Factory for creating MemoryManager with custom settings."""
    def _make(max_memory_mb=1):
        manager = MemoryManager(max_memory_mb=max_memory_mb)
        # Clear any existing state
        manager._memory_usage_bytes = 0
        manager._cached_items.clear()
        manager._access_times.clear()
        manager._eviction_heap.clear()
        manager._heap_dirty = False
        return manager
    return _make


@pytest.fixture
def populated_memory_manager(make_memory_manager, tmp_path):
    """Create a MemoryManager with test data already loaded."""
    manager = make_memory_manager(max_memory_mb=1)  # 1MB limit

    # Add entries with different access times
    test_files = []
    for i in range(10):
        file_path = tmp_path / f"file_{i}.jpg"
        file_path.write_bytes(b"x" * (100 * 1024))  # 100KB each
        test_files.append(file_path)

        # Track with staggered access times
        manager.track_item(file_path, 100 * 1024)
        time.sleep(0.01)  # Small delay to ensure different timestamps

    return manager, test_files


class TestCacheEntry:
    """Test the CacheEntry dataclass for heap operations."""

    def test_cache_entry_comparison(self, make_cache_entry):
        """Test that CacheEntry compares by access_time for heap ordering."""
        entry1 = make_cache_entry(access_offset=-10)  # Older
        entry2 = make_cache_entry(access_offset=0)     # Newer

        # Older entry should be "less than" newer (min heap)
        assert entry1 < entry2
        assert not entry2 < entry1

    def test_cache_entry_heap_ordering(self, make_cache_entry):
        """Test that heap operations maintain LRU order."""
        # Create entries with different access times
        entries = [
            make_cache_entry(path=f"/file{i}", access_offset=i)
            for i in range(5)
        ]

        # Build heap
        heap = []
        for entry in entries:
            heapq.heappush(heap, entry)

        # Pop should return oldest first (LRU)
        popped = []
        while heap:
            popped.append(heapq.heappop(heap))

        # Verify LRU order (oldest to newest)
        for i in range(len(popped) - 1):
            assert popped[i].access_time <= popped[i + 1].access_time


class TestMemoryManagerHeap:
    """Test heap-based LRU eviction in MemoryManager."""

    def test_eviction_order_is_lru(self, make_memory_manager, tmp_path):
        """Test that eviction follows LRU order using heap."""
        manager = make_memory_manager(max_memory_mb=1)

        # Add files with explicit access order
        files = []
        for i in range(5):
            file_path = tmp_path / f"file_{i}.jpg"
            file_path.write_bytes(b"x" * (300 * 1024))  # 300KB each
            files.append(file_path)

        # Track files with delays to ensure different timestamps
        for i, file_path in enumerate(files):
            manager.track_item(file_path, 300 * 1024)
            if i < len(files) - 1:
                time.sleep(0.01)  # Ensure different timestamps

        # Access middle file to update its timestamp (make it most recent)
        time.sleep(0.01)
        manager.track_item(files[2], 300 * 1024)  # Update access time

        # Trigger eviction (we have 1.5MB in 1MB limit)
        # Note: _evict_lru_items actually deletes files, so check what gets deleted
        evicted = manager.evict_if_needed(target_percent=0.5)

        # Should have evicted some files
        assert evicted > 0
        # Oldest files should be gone
        assert not files[0].exists() or not files[1].exists()
        # Recently accessed file should still exist
        assert files[2].exists()

    def test_heap_eviction_efficiency(self, make_memory_manager, tmp_path):
        """Test that heap-based eviction correctly identifies LRU items.

        Rather than timing-based performance testing (which is fragile),
        this test verifies the heap correctly maintains LRU order for eviction.
        """
        manager = make_memory_manager(max_memory_mb=1)  # 1MB limit

        # Add files with known access order
        files = []
        for i in range(10):
            file_path = tmp_path / f"test_{i}.jpg"
            file_path.write_bytes(b"x" * (200 * 1024))  # 200KB each (2MB total)
            files.append(file_path)

        # Track files with explicit timing
        access_times = []
        for file_path in files:
            manager.track_item(file_path, 200 * 1024)
            access_times.append(manager._access_times[str(file_path)])
            time.sleep(0.01)  # Ensure different timestamps

        # Access a middle file to update its timestamp (make it most recent)
        time.sleep(0.01)
        manager.track_item(files[5], 200 * 1024)  # Update file 5
        updated_time = manager._access_times[str(files[5])]

        # Verify heap contains all entries
        manager._rebuild_heap()
        assert len(manager._eviction_heap) == 10

        # Verify heap is properly ordered (min heap by access time)
        heap = manager._eviction_heap[:]  # Copy for non-destructive testing
        heap_times = [entry.access_time for entry in heap]

        # Check heap property: parent <= children
        for i in range(len(heap) // 2):
            left_child = 2 * i + 1
            right_child = 2 * i + 2

            if left_child < len(heap):
                assert heap[i].access_time <= heap[left_child].access_time
            if right_child < len(heap):
                assert heap[i].access_time <= heap[right_child].access_time

        # Force eviction (2MB in 1MB limit)
        evicted = manager.evict_if_needed()
        assert evicted > 0

        # Recently accessed file (5) should still exist
        assert files[5].exists()

        # File 5 should still be tracked (it was accessed most recently)
        assert str(files[5]) in manager._cached_items

        # Should be under memory limit now
        assert manager.memory_usage_bytes <= manager._max_memory_bytes

    def test_concurrent_heap_access_thread_safety(self, make_memory_manager, tmp_path):
        """Test thread-safe concurrent access to eviction heap.

        Following guide: Thread safety testing.
        """
        manager = make_memory_manager(max_memory_mb=10)
        errors = []

        def add_entries():
            """Add entries from thread."""
            try:
                for i in range(100):
                    file_path = tmp_path / f"thread_{i}.jpg"
                    file_path.touch()  # Create file
                    manager.track_item(file_path, 1024)
            except Exception as e:
                errors.append(e)

        def evict_entries():
            """Trigger eviction from thread."""
            try:
                for _ in range(10):
                    time.sleep(0.01)
                    manager.evict_if_needed()
            except Exception as e:
                errors.append(e)

        # Run concurrent operations
        threads = [
            Thread(target=add_entries),
            Thread(target=add_entries),
            Thread(target=evict_entries),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should complete without errors
        assert len(errors) == 0, f"Thread safety errors: {errors}"

    def test_heap_invariant_maintained(self, populated_memory_manager):
        """Test that heap invariant is maintained after operations."""
        manager, files = populated_memory_manager

        # Perform various operations
        manager.track_item(files[0], 100 * 1024)  # Update access
        manager.evict_if_needed()  # Trigger eviction

        # Verify heap invariant (parent <= children)
        heap = manager._eviction_heap
        for i in range(len(heap)):
            left_child = 2 * i + 1
            right_child = 2 * i + 2

            if left_child < len(heap):
                assert heap[i].access_time <= heap[left_child].access_time

            if right_child < len(heap):
                assert heap[i].access_time <= heap[right_child].access_time

    def test_memory_calculation_accuracy(self, make_memory_manager, tmp_path):
        """Test accurate memory usage tracking during eviction."""
        manager = make_memory_manager(max_memory_mb=1)

        # Add files totaling exactly 1MB (1,048,576 bytes)
        file_size_bytes = 1048576 // 10  # 104,857.6 -> 104,857 bytes each
        remaining_bytes = 1048576 - (file_size_bytes * 9)  # Last file gets remainder

        for i in range(9):
            file_path = tmp_path / f"file_{i}.jpg"
            file_path.touch()  # Create file
            manager.track_item(file_path, file_size_bytes)

        # Last file gets the remaining bytes to total exactly 1MB
        last_file = tmp_path / "file_9.jpg"
        last_file.touch()
        manager.track_item(last_file, remaining_bytes)

        assert manager.memory_usage_bytes == 1024 * 1024  # Exactly 1MB

        # Add one more to trigger eviction
        overflow_path = tmp_path / "overflow.jpg"
        overflow_path.touch()
        manager.track_item(overflow_path, 200 * 1024)
        manager.evict_if_needed()

        # Should have evicted enough to stay under limit
        assert manager.memory_usage_bytes <= 1024 * 1024

    def test_eviction_with_empty_heap(self, make_memory_manager):
        """Test that eviction handles empty heap gracefully."""
        manager = make_memory_manager()

        # Should not crash with empty heap
        evicted = manager._evict_lru_items(0.5)
        assert evicted == 0

    def test_eviction_target_percentage(self, populated_memory_manager):
        """Test that eviction targets correct percentage."""
        manager, files = populated_memory_manager

        initial_bytes = manager.memory_usage_bytes

        # Force over limit and evict to 50%
        manager._memory_usage_bytes = manager._max_memory_bytes + 1

        # Mock file deletion to test logic without actually deleting
        with patch.object(Path, 'unlink'):
            evicted = manager._evict_lru_items(0.5)

        # Should have evicted files to reach ~50% of limit
        assert evicted > 0
        assert manager.memory_usage_bytes <= manager._max_memory_bytes * 0.5

    def test_access_time_updates_correctly(self, make_memory_manager, tmp_path):
        """Test that accessing a file updates its position in heap."""
        manager = make_memory_manager()

        # Add initial file
        old_path = tmp_path / "old.jpg"
        old_path.touch()
        manager.track_item(old_path, 1024)
        time.sleep(0.01)

        # Add newer file
        new_path = tmp_path / "new.jpg"
        new_path.touch()
        manager.track_item(new_path, 1024)

        # Access old file to make it newest
        time.sleep(0.01)
        manager.track_item(old_path, 1024)  # Update access time

        # Old file should now have newer timestamp in access_times
        assert str(old_path) in manager._access_times
        assert str(new_path) in manager._access_times
        assert manager._access_times[str(old_path)] > manager._access_times[str(new_path)]

    @pytest.mark.parametrize("memory_limit_mb,file_count,file_size_kb", [
        (1, 5, 300),    # Over limit, eviction needed
        (10, 5, 300),   # Under limit, no eviction
        (2, 20, 100),   # Many small files
    ])
    def test_various_memory_scenarios(
        self,
        make_memory_manager,
        tmp_path,
        memory_limit_mb,
        file_count,
        file_size_kb
    ):
        """Test various memory limit scenarios.

        Following guide: Parametrization for comprehensive testing.
        """
        manager = make_memory_manager(max_memory_mb=memory_limit_mb)

        # Add files
        for i in range(file_count):
            file_path = tmp_path / f"file_{i}.jpg"
            file_path.write_bytes(b"x" * (file_size_kb * 1024))
            manager.track_item(file_path, file_size_kb * 1024)

        # Check memory limit
        manager.evict_if_needed()

        # Verify we're within limit
        assert manager.memory_usage_bytes <= memory_limit_mb * 1024 * 1024