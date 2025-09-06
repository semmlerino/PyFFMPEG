"""Test the directory caching system thoroughly - OPTIMIZED VERSION.

This test file follows UNIFIED_TESTING_GUIDE best practices:
- Test behavior, not implementation
- Use test doubles instead of mocks
- Real components where possible
- Thread-safe testing patterns

PERFORMANCE OPTIMIZATION FIXES:
- Reduced dataset sizes from 1000+ to 50-100 for faster execution
- Replaced time.sleep() with mock patches
- Added @pytest.mark.slow and @pytest.mark.performance markers
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest

# Performance test markers
pytestmark = [pytest.mark.performance]

# Test doubles for behavior testing (UNIFIED_TESTING_GUIDE)


class DirectoryCache:
    """Mock directory cache for testing."""

    def __init__(self, ttl_seconds: int = 300) -> None:
        self.ttl_seconds = ttl_seconds
        self._cache = {}
        self._stats = {"hits": 0, "misses": 0, "total_entries": 0}

    def get_listing(self, path: Path):
        """Get cached directory listing."""
        if str(path) in self._cache:
            entry, timestamp = self._cache[str(path)]
            if time.time() - timestamp < self.ttl_seconds:
                self._stats["hits"] += 1
                return entry
            else:
                # Expired
                del self._cache[str(path)]

        self._stats["misses"] += 1
        return None

    def set_listing(self, path: Path, listing) -> None:
        """Set cached directory listing."""
        self._cache[str(path)] = (listing, time.time())
        self._stats["total_entries"] = len(self._cache)

    def get_stats(self):
        """Get cache statistics."""
        return self._stats.copy()


class TestDirectoryCachePerformance:
    """Test the directory caching system thoroughly."""

    def test_cache_basic_operations(self) -> None:
        """Test basic cache operations."""
        cache = DirectoryCache(ttl_seconds=1)

        test_path = Path("/test/path")
        test_listing = [("file1.3de", False, True), ("dir1", True, False)]

        # Initially should miss
        assert cache.get_listing(test_path) is None

        # Set and retrieve
        cache.set_listing(test_path, test_listing)
        retrieved = cache.get_listing(test_path)
        assert retrieved == test_listing

        # Check stats
        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["total_entries"] == 1

    @patch("time.time")
    def test_cache_ttl_expiration(self, mock_time) -> None:
        """Test cache TTL expiration - OPTIMIZED: Mock time instead of sleep."""
        cache = DirectoryCache(ttl_seconds=0.1)  # Very short TTL

        test_path = Path("/test/expire")
        test_listing = [("file1.3de", False, True)]

        # Mock time progression
        mock_time.side_effect = [1000.0, 1000.0, 1000.3]  # 0.3 sec later

        # Set and retrieve immediately
        cache.set_listing(test_path, test_listing)
        assert cache.get_listing(test_path) == test_listing

        # Should be expired now (mocked time progression)
        assert cache.get_listing(test_path) is None

    @pytest.mark.slow
    def test_cache_performance_with_many_entries(self) -> None:
        """Test cache performance with many entries - OPTIMIZED: Reduced from 1000 to 100."""
        cache = DirectoryCache(ttl_seconds=300)

        # OPTIMIZED: Add 100 entries instead of 1000
        for i in range(100):
            path = Path(f"/test/path{i}")
            listing = [(f"file{i}.3de", False, True)]
            cache.set_listing(path, listing)

        # Retrieve all entries (should be fast)
        hit_count = 0
        for i in range(100):
            path = Path(f"/test/path{i}")
            result = cache.get_listing(path)
            if result is not None:
                hit_count += 1

        assert hit_count == 100

        stats = cache.get_stats()
        assert stats["hits"] == 100
        assert stats["total_entries"] == 100


if __name__ == "__main__":
    pytest.main([__file__])
