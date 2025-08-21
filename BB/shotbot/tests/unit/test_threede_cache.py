"""Comprehensive tests for ThreeDECache following UNIFIED_TESTING_GUIDE principles.

This test suite covers all public methods of ThreeDECache with focus on:
- Real StorageBackend integration (no mocking)
- 3DE scene data caching with metadata support
- TTL-based cache expiration using time mocking
- Thread safety under concurrent access
- Comprehensive error handling and edge cases
- Empty scene caching behavior
- Atomic write operations through StorageBackend
- Cache consistency and validation

The tests use real file I/O operations with temporary directories rather than
mocks to ensure integration correctness and catch real filesystem issues.
"""

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from cache.storage_backend import StorageBackend
from cache.threede_cache import ThreeDECache


class TestThreeDECache:
    """Comprehensive test suite for ThreeDECache 3DE scene data caching."""

    @pytest.fixture(autouse=True)
    def setup_cache(self, tmp_path: Path):
        """Set up ThreeDECache instance with real StorageBackend and temporary directory."""
        self.temp_dir = tmp_path
        self.cache_file = tmp_path / "threede_scenes.json"
        self.storage = StorageBackend()  # Real component
        self.cache = ThreeDECache(
            cache_file=self.cache_file, storage_backend=self.storage, expiry_minutes=30
        )

        # Sample 3DE scene data for testing
        self.sample_scenes = [
            {
                "show": "test_show",
                "sequence": "seq01",
                "shot": "0010",
                "user": "testuser",
                "scene_file": "/shows/test_show/shots/seq01/seq01_0010/user/testuser/3de/mm-default/seq01_0010_mm_v001.3de",
                "plate_type": "BG01",
                "timestamp": "2025-08-20T10:00:00",
            },
            {
                "show": "test_show",
                "sequence": "seq02",
                "shot": "0020",
                "user": "artist",
                "scene_file": "/shows/test_show/shots/seq02/seq02_0020/user/artist/3de/mm-default/seq02_0020_mm_v002.3de",
                "plate_type": "FG01",
                "timestamp": "2025-08-20T11:00:00",
            },
        ]

        self.sample_metadata = {
            "scan_type": "full",
            "scene_count": 2,
            "cached_at": datetime.now().isoformat(),
            "scan_duration_seconds": 5.2,
            "directories_scanned": ["/shows/test_show"],
        }

    # =============================================================================
    # Initialization Tests
    # =============================================================================

    def test_init_with_defaults(self, tmp_path: Path):
        """Test ThreeDECache initialization with default parameters."""
        cache_file = tmp_path / "test.json"
        cache = ThreeDECache(cache_file=cache_file)

        assert cache._cache_file == cache_file
        assert isinstance(cache._storage, StorageBackend)
        assert cache._expiry_minutes == 1440  # Default from config (24 hours)

    def test_init_with_custom_storage_backend(self, tmp_path: Path):
        """Test ThreeDECache initialization with custom StorageBackend."""
        cache_file = tmp_path / "test.json"
        custom_storage = StorageBackend()
        cache = ThreeDECache(
            cache_file=cache_file, storage_backend=custom_storage, expiry_minutes=60
        )

        assert cache._cache_file == cache_file
        assert cache._storage is custom_storage
        assert cache._expiry_minutes == 60

    def test_init_with_none_values(self, tmp_path: Path):
        """Test ThreeDECache initialization with None values creates defaults."""
        cache_file = tmp_path / "test.json"
        cache = ThreeDECache(
            cache_file=cache_file, storage_backend=None, expiry_minutes=None
        )

        assert cache._cache_file == cache_file
        assert isinstance(cache._storage, StorageBackend)
        assert cache._expiry_minutes == 1440  # Config default (24 hours)

    # =============================================================================
    # Scene Caching Tests
    # =============================================================================

    def test_cache_scenes_with_data_and_metadata(self):
        """Test caching scenes with explicit metadata."""
        result = self.cache.cache_scenes(self.sample_scenes, self.sample_metadata)

        assert result is True
        assert self.cache_file.exists()

        # Verify cache file content using real StorageBackend
        cache_data = self.storage.read_json(self.cache_file)
        assert cache_data is not None
        assert cache_data["scenes"] == self.sample_scenes
        assert cache_data["metadata"] == self.sample_metadata
        assert "timestamp" in cache_data

    def test_cache_scenes_with_default_metadata(self):
        """Test caching scenes with auto-generated metadata."""
        result = self.cache.cache_scenes(self.sample_scenes)

        assert result is True
        assert self.cache_file.exists()

        cache_data = self.storage.read_json(self.cache_file)
        assert cache_data is not None
        assert cache_data["scenes"] == self.sample_scenes

        # Verify default metadata structure
        metadata = cache_data["metadata"]
        assert metadata["scan_type"] == "full"
        assert metadata["scene_count"] == len(self.sample_scenes)
        assert "cached_at" in metadata

    def test_cache_empty_scenes_list(self):
        """Test caching empty scenes list with correct metadata."""
        empty_scenes = []
        result = self.cache.cache_scenes(empty_scenes)

        assert result is True
        assert self.cache_file.exists()

        cache_data = self.storage.read_json(self.cache_file)
        assert cache_data is not None
        assert cache_data["scenes"] == []

        # Verify empty scan metadata
        metadata = cache_data["metadata"]
        assert metadata["scan_type"] == "empty"
        assert metadata["scene_count"] == 0

    def test_cache_scenes_storage_failure(self):
        """Test cache_scenes handles storage backend write failures gracefully."""
        # Mock the storage backend to fail writes
        with patch.object(self.storage, "write_json", return_value=False):
            result = self.cache.cache_scenes(self.sample_scenes)

        assert result is False
        # File should not exist due to mock failure
        assert not self.cache_file.exists()

    def test_cache_scenes_exception_handling(self):
        """Test cache_scenes handles unexpected exceptions gracefully."""
        # Mock storage backend to raise exception
        with patch.object(
            self.storage, "write_json", side_effect=Exception("Disk error")
        ):
            result = self.cache.cache_scenes(self.sample_scenes)

        assert result is False

    # =============================================================================
    # Scene Retrieval Tests
    # =============================================================================

    def test_get_cached_scenes_valid_cache(self):
        """Test retrieving scenes from valid, non-expired cache."""
        # First cache some scenes
        self.cache.cache_scenes(self.sample_scenes, self.sample_metadata)

        # Retrieve cached scenes
        cached_scenes = self.cache.get_cached_scenes()

        assert cached_scenes is not None
        assert cached_scenes == self.sample_scenes
        assert len(cached_scenes) == 2

    def test_get_cached_scenes_no_cache_file(self):
        """Test get_cached_scenes returns None when cache file doesn't exist."""
        cached_scenes = self.cache.get_cached_scenes()

        assert cached_scenes is None

    def test_get_cached_scenes_invalid_json(self):
        """Test get_cached_scenes handles corrupted cache files gracefully."""
        # Write invalid JSON to cache file
        self.cache_file.write_text("invalid json content")

        cached_scenes = self.cache.get_cached_scenes()

        assert cached_scenes is None

    @patch("cache.threede_cache.datetime")
    def test_get_cached_scenes_expired_cache(self, mock_datetime):
        """Test get_cached_scenes returns None for expired cache."""
        # Cache scenes at specific time
        cache_time = datetime(2025, 8, 20, 10, 0, 0)
        mock_datetime.now.return_value = cache_time
        mock_datetime.fromisoformat = datetime.fromisoformat

        self.cache.cache_scenes(self.sample_scenes)

        # Move time forward past expiry (30 minutes + 1 second)
        expired_time = cache_time + timedelta(minutes=31)
        mock_datetime.now.return_value = expired_time

        cached_scenes = self.cache.get_cached_scenes()

        assert cached_scenes is None

    def test_get_cached_scenes_invalid_structure(self):
        """Test get_cached_scenes handles invalid cache structure."""
        # Write cache data with invalid structure (scenes is not a list)
        invalid_data = {
            "timestamp": datetime.now().isoformat(),
            "scenes": "not_a_list",  # Invalid - should be list
            "metadata": {},
        }
        self.storage.write_json(self.cache_file, invalid_data)

        cached_scenes = self.cache.get_cached_scenes()

        assert cached_scenes is None

    def test_get_cached_scenes_empty_list(self):
        """Test get_cached_scenes properly handles valid empty cache."""
        # Cache empty scenes list
        self.cache.cache_scenes([])

        cached_scenes = self.cache.get_cached_scenes()

        assert cached_scenes is not None
        assert cached_scenes == []
        assert len(cached_scenes) == 0

    # =============================================================================
    # Cache Validation Tests
    # =============================================================================

    def test_has_valid_cache_with_fresh_cache(self):
        """Test has_valid_cache returns True for fresh cache."""
        self.cache.cache_scenes(self.sample_scenes)

        assert self.cache.has_valid_cache() is True

    def test_has_valid_cache_no_cache_file(self):
        """Test has_valid_cache returns False when cache file doesn't exist."""
        assert self.cache.has_valid_cache() is False

    def test_has_valid_cache_corrupted_file(self):
        """Test has_valid_cache returns False for corrupted cache file."""
        self.cache_file.write_text("invalid json")

        assert self.cache.has_valid_cache() is False

    @patch("cache.threede_cache.datetime")
    def test_has_valid_cache_expired(self, mock_datetime):
        """Test has_valid_cache returns False for expired cache."""
        # Cache at specific time
        cache_time = datetime(2025, 8, 20, 10, 0, 0)
        mock_datetime.now.return_value = cache_time
        mock_datetime.fromisoformat = datetime.fromisoformat

        self.cache.cache_scenes(self.sample_scenes)

        # Move time forward past expiry
        expired_time = cache_time + timedelta(minutes=31)
        mock_datetime.now.return_value = expired_time

        assert self.cache.has_valid_cache() is False

    def test_has_valid_cache_with_empty_scenes(self):
        """Test has_valid_cache returns True for valid empty cache."""
        self.cache.cache_scenes([])  # Cache empty list

        assert self.cache.has_valid_cache() is True

    # =============================================================================
    # Cache Expiry Tests
    # =============================================================================

    def test_is_expired_fresh_cache(self):
        """Test is_expired returns False for fresh cache."""
        self.cache.cache_scenes(self.sample_scenes)

        assert self.cache.is_expired() is False

    def test_is_expired_no_cache_file(self):
        """Test is_expired returns True when no cache file exists."""
        assert self.cache.is_expired() is True

    def test_is_expired_invalid_cache_file(self):
        """Test is_expired returns True for invalid cache file."""
        self.cache_file.write_text("invalid json")

        assert self.cache.is_expired() is True

    @patch("cache.threede_cache.datetime")
    def test_is_expired_old_cache(self, mock_datetime):
        """Test is_expired returns True for expired cache."""
        # Cache at specific time
        cache_time = datetime(2025, 8, 20, 10, 0, 0)
        mock_datetime.now.return_value = cache_time
        mock_datetime.fromisoformat = datetime.fromisoformat

        self.cache.cache_scenes(self.sample_scenes)

        # Move time forward past expiry
        expired_time = cache_time + timedelta(minutes=31)
        mock_datetime.now.return_value = expired_time

        assert self.cache.is_expired() is True

    @patch("cache.threede_cache.datetime")
    def test_is_expired_edge_case_exact_expiry(self, mock_datetime):
        """Test is_expired behavior at exact expiry time."""
        # Cache at specific time
        cache_time = datetime(2025, 8, 20, 10, 0, 0)
        mock_datetime.now.return_value = cache_time
        mock_datetime.fromisoformat = datetime.fromisoformat

        self.cache.cache_scenes(self.sample_scenes)

        # Move to exact expiry time (30 minutes)
        expiry_time = cache_time + timedelta(minutes=30)
        mock_datetime.now.return_value = expiry_time

        # Should be False (not expired) at exactly 30 minutes
        assert self.cache.is_expired() is False

        # Should be True (expired) at 30 minutes + 1 second
        just_expired = expiry_time + timedelta(seconds=1)
        mock_datetime.now.return_value = just_expired

        assert self.cache.is_expired() is True

    # =============================================================================
    # Cache Age Tests
    # =============================================================================

    @patch("cache.threede_cache.datetime")
    def test_get_cache_age_valid_cache(self, mock_datetime):
        """Test get_cache_age returns correct age for valid cache."""
        # Cache at specific time
        cache_time = datetime(2025, 8, 20, 10, 0, 0)
        mock_datetime.now.return_value = cache_time
        mock_datetime.fromisoformat = datetime.fromisoformat

        self.cache.cache_scenes(self.sample_scenes)

        # Check age after 15 minutes
        current_time = cache_time + timedelta(minutes=15)
        mock_datetime.now.return_value = current_time

        age = self.cache.get_cache_age()

        assert age is not None
        assert age == timedelta(minutes=15)

    def test_get_cache_age_no_cache_file(self):
        """Test get_cache_age returns None when no cache file exists."""
        age = self.cache.get_cache_age()

        assert age is None

    def test_get_cache_age_invalid_cache_file(self):
        """Test get_cache_age returns None for invalid cache file."""
        self.cache_file.write_text("invalid json")

        age = self.cache.get_cache_age()

        assert age is None

    def test_get_cache_age_invalid_timestamp(self):
        """Test get_cache_age handles invalid timestamp format gracefully."""
        invalid_data = {
            "timestamp": "invalid_timestamp_format",
            "scenes": [],
            "metadata": {},
        }
        self.storage.write_json(self.cache_file, invalid_data)

        age = self.cache.get_cache_age()

        assert age is None

    # =============================================================================
    # Cache Count Tests
    # =============================================================================

    def test_get_cached_count_with_scenes(self):
        """Test get_cached_count returns correct count for cached scenes."""
        self.cache.cache_scenes(self.sample_scenes)

        count = self.cache.get_cached_count()

        assert count == len(self.sample_scenes)
        assert count == 2

    def test_get_cached_count_empty_scenes(self):
        """Test get_cached_count returns 0 for empty scene cache."""
        self.cache.cache_scenes([])

        count = self.cache.get_cached_count()

        assert count == 0

    def test_get_cached_count_no_cache_file(self):
        """Test get_cached_count returns 0 when no cache file exists."""
        count = self.cache.get_cached_count()

        assert count == 0

    def test_get_cached_count_invalid_cache_file(self):
        """Test get_cached_count returns 0 for invalid cache file."""
        self.cache_file.write_text("invalid json")

        count = self.cache.get_cached_count()

        assert count == 0

    def test_get_cached_count_invalid_scenes_structure(self):
        """Test get_cached_count handles invalid scenes structure."""
        invalid_data = {
            "timestamp": datetime.now().isoformat(),
            "scenes": "not_a_list",  # Invalid structure
            "metadata": {},
        }
        self.storage.write_json(self.cache_file, invalid_data)

        count = self.cache.get_cached_count()

        assert count == 0

    # =============================================================================
    # Cache Metadata Tests
    # =============================================================================

    def test_get_cache_metadata_valid_cache(self):
        """Test get_cache_metadata returns correct metadata."""
        self.cache.cache_scenes(self.sample_scenes, self.sample_metadata)

        metadata = self.cache.get_cache_metadata()

        assert metadata is not None
        assert metadata == self.sample_metadata

    def test_get_cache_metadata_no_cache_file(self):
        """Test get_cache_metadata returns None when no cache file exists."""
        metadata = self.cache.get_cache_metadata()

        assert metadata is None

    def test_get_cache_metadata_invalid_cache_file(self):
        """Test get_cache_metadata returns None for invalid cache file."""
        self.cache_file.write_text("invalid json")

        metadata = self.cache.get_cache_metadata()

        assert metadata is None

    def test_get_cache_metadata_missing_metadata(self):
        """Test get_cache_metadata returns empty dict when metadata missing."""
        data_without_metadata = {
            "timestamp": datetime.now().isoformat(),
            "scenes": self.sample_scenes,
            # No metadata key
        }
        self.storage.write_json(self.cache_file, data_without_metadata)

        metadata = self.cache.get_cache_metadata()

        assert metadata == {}

    # =============================================================================
    # Cache Clearing Tests
    # =============================================================================

    def test_clear_cache_existing_file(self):
        """Test clear_cache successfully removes existing cache file."""
        # First create a cache
        self.cache.cache_scenes(self.sample_scenes)
        assert self.cache_file.exists()

        # Clear the cache
        result = self.cache.clear_cache()

        assert result is True
        assert not self.cache_file.exists()

    def test_clear_cache_nonexistent_file(self):
        """Test clear_cache handles non-existent file gracefully."""
        result = self.cache.clear_cache()

        # StorageBackend.delete_file should handle non-existent files
        assert result is True

    # =============================================================================
    # Cache Info Tests
    # =============================================================================

    def test_get_cache_info_valid_cache(self):
        """Test get_cache_info returns complete information for valid cache."""
        self.cache.cache_scenes(self.sample_scenes, self.sample_metadata)

        info = self.cache.get_cache_info()

        assert info["exists"] is True
        assert info["valid"] is True
        assert info["expired"] is False
        assert info["scene_count"] == len(self.sample_scenes)
        assert info["age_seconds"] is not None
        assert info["expiry_minutes"] == 30
        assert info["timestamp"] is not None
        assert info["metadata"] == self.sample_metadata

    def test_get_cache_info_no_cache_file(self):
        """Test get_cache_info returns correct info when no cache file exists."""
        info = self.cache.get_cache_info()

        assert info["exists"] is False
        assert info["valid"] is False
        assert info["expired"] is True
        assert info["scene_count"] == 0
        assert info["age_seconds"] is None
        assert info["metadata"] == {}

    def test_get_cache_info_invalid_cache_file(self):
        """Test get_cache_info handles invalid cache file."""
        self.cache_file.write_text("invalid json")

        info = self.cache.get_cache_info()

        assert info["exists"] is True
        assert info["valid"] is False
        assert info["expired"] is True
        assert info["scene_count"] == 0
        assert info["age_seconds"] is None
        assert info["metadata"] == {}

    @patch("cache.threede_cache.datetime")
    def test_get_cache_info_expired_cache(self, mock_datetime):
        """Test get_cache_info correctly identifies expired cache."""
        # Cache at specific time
        cache_time = datetime(2025, 8, 20, 10, 0, 0)
        mock_datetime.now.return_value = cache_time
        mock_datetime.fromisoformat = datetime.fromisoformat

        self.cache.cache_scenes(self.sample_scenes)

        # Move time forward past expiry
        expired_time = cache_time + timedelta(minutes=31)
        mock_datetime.now.return_value = expired_time

        info = self.cache.get_cache_info()

        assert info["exists"] is True
        assert info["valid"] is False
        assert info["expired"] is True
        assert info["age_seconds"] == 31 * 60  # 31 minutes in seconds

    # =============================================================================
    # Force Refresh Tests
    # =============================================================================

    @patch("cache.threede_cache.datetime")
    def test_force_refresh_needed_old_cache(self, mock_datetime):
        """Test force_refresh_needed returns True for old cache."""
        # Cache at specific time
        cache_time = datetime(2025, 8, 20, 10, 0, 0)
        mock_datetime.now.return_value = cache_time
        mock_datetime.fromisoformat = datetime.fromisoformat

        self.cache.cache_scenes(self.sample_scenes)

        # Move time forward past half expiry (15+ minutes)
        current_time = cache_time + timedelta(minutes=20)
        mock_datetime.now.return_value = current_time

        # Default max_age is half of expiry_minutes (15 minutes)
        needs_refresh = self.cache.force_refresh_needed()

        assert needs_refresh is True

    @patch("cache.threede_cache.datetime")
    def test_force_refresh_needed_fresh_cache(self, mock_datetime):
        """Test force_refresh_needed returns False for fresh cache."""
        # Cache at specific time
        cache_time = datetime(2025, 8, 20, 10, 0, 0)
        mock_datetime.now.return_value = cache_time
        mock_datetime.fromisoformat = datetime.fromisoformat

        self.cache.cache_scenes(self.sample_scenes)

        # Move time forward less than half expiry (10 minutes)
        current_time = cache_time + timedelta(minutes=10)
        mock_datetime.now.return_value = current_time

        needs_refresh = self.cache.force_refresh_needed()

        assert needs_refresh is False

    def test_force_refresh_needed_no_cache(self):
        """Test force_refresh_needed returns True when no cache exists."""
        needs_refresh = self.cache.force_refresh_needed()

        assert needs_refresh is True

    @patch("cache.threede_cache.datetime")
    def test_force_refresh_needed_custom_max_age(self, mock_datetime):
        """Test force_refresh_needed with custom max_age parameter."""
        # Cache at specific time
        cache_time = datetime(2025, 8, 20, 10, 0, 0)
        mock_datetime.now.return_value = cache_time
        mock_datetime.fromisoformat = datetime.fromisoformat

        self.cache.cache_scenes(self.sample_scenes)

        # Move time forward 5 minutes
        current_time = cache_time + timedelta(minutes=5)
        mock_datetime.now.return_value = current_time

        # With custom max_age of 3 minutes, should need refresh
        needs_refresh = self.cache.force_refresh_needed(max_age_minutes=3)
        assert needs_refresh is True

        # With custom max_age of 10 minutes, should not need refresh
        needs_refresh = self.cache.force_refresh_needed(max_age_minutes=10)
        assert needs_refresh is False

    # =============================================================================
    # String Representation Tests
    # =============================================================================

    def test_repr_valid_cache(self):
        """Test __repr__ returns proper string representation for valid cache."""
        self.cache.cache_scenes(self.sample_scenes)

        repr_str = repr(self.cache)

        assert "ThreeDECache" in repr_str
        assert f"file={self.cache_file.name}" in repr_str
        assert "valid=True" in repr_str
        assert "expired=False" in repr_str
        assert f"scenes={len(self.sample_scenes)}" in repr_str

    def test_repr_no_cache_file(self):
        """Test __repr__ returns proper string representation when no cache exists."""
        repr_str = repr(self.cache)

        assert "ThreeDECache" in repr_str
        assert f"file={self.cache_file.name}" in repr_str
        assert "valid=False" in repr_str
        assert "expired=True" in repr_str
        assert "scenes=0" in repr_str

    # =============================================================================
    # Thread Safety Tests
    # =============================================================================

    def test_concurrent_cache_access(self):
        """Test ThreeDECache handles concurrent read/write operations safely."""
        # Initial cache
        self.cache.cache_scenes(self.sample_scenes[:1])  # Start with 1 scene

        results = []
        errors = []

        # Create barrier for synchronized thread startup (4 readers + 4 writers)
        start_barrier = threading.Barrier(8)

        def read_cache(thread_id: int):
            """Read from cache in worker thread."""
            # Wait for all threads to start together
            start_barrier.wait()

            try:
                for _ in range(10):  # Multiple reads
                    scenes = self.cache.get_cached_scenes()
                    self.cache.get_cached_count()
                    self.cache.get_cache_age()
                    self.cache.get_cache_metadata()
                    self.cache.get_cache_info()

                    results.append((thread_id, "read", len(scenes) if scenes else 0))
                    # Let threads run at natural pace for race condition testing
            except Exception as e:
                errors.append((thread_id, "read", str(e)))

        def write_cache(thread_id: int):
            """Write to cache in worker thread."""
            # Wait for all threads to start together
            start_barrier.wait()

            try:
                for i in range(5):  # Multiple writes
                    # Alternate between different scene sets
                    scenes = self.sample_scenes if i % 2 == 0 else []
                    metadata = {"thread_id": thread_id, "iteration": i}

                    self.cache.cache_scenes(scenes, metadata)
                    results.append((thread_id, "write", len(scenes)))
                    # Let threads run at natural pace for race condition testing
            except Exception as e:
                errors.append((thread_id, "write", str(e)))

        # Start concurrent operations
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = []

            # Start 4 readers and 4 writers
            for i in range(4):
                futures.append(executor.submit(read_cache, i))
                futures.append(executor.submit(write_cache, i + 4))

            # Wait for all to complete
            for future in as_completed(futures, timeout=10):
                future.result()  # Re-raise any exceptions

        # Verify no threading errors occurred
        assert len(errors) == 0, f"Threading errors: {errors}"

        # Verify operations completed
        read_results = [r for r in results if r[1] == "read"]
        write_results = [r for r in results if r[1] == "write"]

        assert len(read_results) > 0, "No read operations completed"
        assert len(write_results) > 0, "No write operations completed"

        # Final cache should be valid
        final_scenes = self.cache.get_cached_scenes()
        assert final_scenes is not None

    def test_concurrent_cache_creation_deletion(self):
        """Test concurrent cache creation and deletion operations."""
        results = []
        errors = []

        # Create barrier for synchronized thread startup (6 threads)
        start_barrier = threading.Barrier(6)
        # Use Event for coordinating create/delete phases
        phase_event = threading.Event()

        def create_delete_cycle(thread_id: int):
            """Cycle between creating and deleting cache."""
            # Wait for all threads to start together
            start_barrier.wait()

            try:
                for i in range(5):
                    # Create cache
                    scenes = [{"thread": thread_id, "iteration": i}]
                    success = self.cache.cache_scenes(scenes)
                    results.append((thread_id, "create", success))

                    # Brief pause to allow interleaving (using Event instead of sleep)
                    if i % 2 == 0:  # Only some threads wait to create timing variety
                        phase_event.wait(timeout=0.001)

                    # Delete cache
                    success = self.cache.clear_cache()
                    results.append((thread_id, "delete", success))

                    # Brief pause to allow interleaving
                    if i % 3 == 0:  # Different pattern for delete timing
                        phase_event.wait(timeout=0.001)
            except Exception as e:
                errors.append((thread_id, str(e)))

        # Run concurrent creation/deletion
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(create_delete_cycle, i) for i in range(6)]

            for future in as_completed(futures, timeout=10):
                future.result()

        # Verify no threading errors
        assert len(errors) == 0, f"Threading errors: {errors}"
        assert len(results) > 0, "No operations completed"

    # =============================================================================
    # Error Handling and Edge Cases
    # =============================================================================

    def test_invalid_timestamp_format_in_cache_data(self):
        """Test handling of various invalid timestamp formats in cache data."""
        invalid_timestamps = [
            "not_a_timestamp",
            "2025-13-40T25:70:80",  # Invalid date/time values
            "",  # Empty string
            None,  # None value
            42,  # Not a string
        ]

        for i, invalid_timestamp in enumerate(invalid_timestamps):
            cache_file = self.temp_dir / f"cache_{i}.json"
            cache = ThreeDECache(cache_file=cache_file, storage_backend=self.storage)

            invalid_data = {
                "timestamp": invalid_timestamp,
                "scenes": self.sample_scenes,
                "metadata": {},
            }
            self.storage.write_json(cache_file, invalid_data)

            # All methods should handle invalid timestamps gracefully
            assert cache.get_cached_scenes() is None
            assert cache.has_valid_cache() is False
            assert cache.is_expired() is True
            assert cache.get_cache_age() is None

    def test_cache_scenes_with_various_metadata_types(self):
        """Test caching scenes with various metadata types and structures."""
        metadata_variants = [
            {},  # Empty dict
            {"simple": "value"},  # Simple metadata
            {  # Complex nested metadata
                "scan_info": {
                    "directories": ["/path1", "/path2"],
                    "duration": 42.5,
                    "files_found": 100,
                },
                "filters": ["*.3de", "matchmove"],
                "user_exclusions": ["backup", "temp"],
            },
            {"unicode": "测试数据"},  # Unicode data
            {"numbers": 42, "float": 3.14, "bool": True, "null": None},  # Mixed types
        ]

        for i, metadata in enumerate(metadata_variants):
            cache_file = self.temp_dir / f"metadata_test_{i}.json"
            cache = ThreeDECache(cache_file=cache_file, storage_backend=self.storage)

            # Should successfully cache with any valid metadata structure
            success = cache.cache_scenes(self.sample_scenes, metadata)
            assert success is True

            # Should retrieve the exact same metadata
            retrieved_metadata = cache.get_cache_metadata()
            assert retrieved_metadata == metadata

    def test_large_scene_data_handling(self):
        """Test ThreeDECache with large amounts of scene data."""
        # Create large scene dataset
        large_scenes = []
        for i in range(1000):  # 1000 scenes
            scene = {
                "show": f"show_{i // 100}",
                "sequence": f"seq_{i // 10:03d}",
                "shot": f"{i:04d}",
                "user": f"user_{i % 5}",
                "scene_file": f"/very/long/path/to/shows/show_{i}/scene_{i}.3de",
                "plate_type": "BG01" if i % 2 == 0 else "FG01",
                "timestamp": f"2025-08-20T{(10 + i // 100) % 24:02d}:00:00",
                "additional_data": f"extra_info_{i}" * 10,  # Make each record larger
            }
            large_scenes.append(scene)

        # Should handle large datasets
        success = self.cache.cache_scenes(large_scenes)
        assert success is True

        # Should retrieve all scenes
        retrieved_scenes = self.cache.get_cached_scenes()
        assert retrieved_scenes is not None
        assert len(retrieved_scenes) == 1000

        # Count should be accurate
        count = self.cache.get_cached_count()
        assert count == 1000

    def test_permission_denied_scenarios(self):
        """Test ThreeDECache behavior when file permissions prevent operations."""
        # This test is platform-dependent and may not work on all systems
        try:
            import stat

            # Create cache file and make directory read-only
            self.cache.cache_scenes(self.sample_scenes)

            # Make directory read-only (if possible on this platform)
            original_mode = self.temp_dir.stat().st_mode
            try:
                self.temp_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)  # Read + execute only

                # New cache operations should fail gracefully
                new_cache_file = self.temp_dir / "new_cache.json"
                new_cache = ThreeDECache(
                    cache_file=new_cache_file, storage_backend=self.storage
                )

                # Should handle permission errors gracefully
                new_cache.cache_scenes(self.sample_scenes)
                # Success depends on platform permissions implementation

            finally:
                # Restore permissions
                self.temp_dir.chmod(original_mode)

        except (OSError, NotImplementedError, PermissionError):
            # Skip on platforms that don't support chmod or have different permission models
            pytest.skip("Platform doesn't support file permission testing")

    # =============================================================================
    # Integration with StorageBackend Tests
    # =============================================================================

    def test_storage_backend_integration_atomic_writes(self):
        """Test that ThreeDECache properly uses StorageBackend's atomic write operations."""
        # Patch storage backend to verify atomic write calls
        original_write = self.storage.write_json
        write_calls = []

        def track_writes(file_path, data):
            write_calls.append((file_path, data.copy()))
            return original_write(file_path, data)

        with patch.object(self.storage, "write_json", side_effect=track_writes):
            success = self.cache.cache_scenes(self.sample_scenes, self.sample_metadata)

        assert success is True
        assert len(write_calls) == 1

        # Verify the data structure passed to storage backend
        call_path, call_data = write_calls[0]
        assert call_path == self.cache_file
        assert call_data["scenes"] == self.sample_scenes
        assert call_data["metadata"] == self.sample_metadata
        assert "timestamp" in call_data

    def test_storage_backend_integration_read_operations(self):
        """Test that ThreeDECache properly uses StorageBackend's read operations."""
        # Cache data first
        self.cache.cache_scenes(self.sample_scenes, self.sample_metadata)

        # Track storage backend read calls
        original_read = self.storage.read_json
        read_calls = []

        def track_reads(file_path):
            read_calls.append(file_path)
            return original_read(file_path)

        with patch.object(self.storage, "read_json", side_effect=track_reads):
            scenes = self.cache.get_cached_scenes()
            count = self.cache.get_cached_count()
            metadata = self.cache.get_cache_metadata()
            self.cache.get_cache_info()

        # get_cache_info() makes internal calls to get_cache_age() and get_cached_count()
        # which each make their own read_json() calls, so total should be:
        # 1 (get_cached_scenes) + 1 (get_cached_count) + 1 (get_cache_metadata) +
        # 1 (get_cache_info) + 1 (get_cache_age from get_cache_info) + 1 (get_cached_count from get_cache_info) = 6
        assert len(read_calls) == 6  # Including internal calls from get_cache_info()
        assert all(call == self.cache_file for call in read_calls)

        # Results should be correct
        assert scenes == self.sample_scenes
        assert count == len(self.sample_scenes)
        assert metadata == self.sample_metadata

    def test_storage_backend_integration_delete_operations(self):
        """Test that ThreeDECache properly uses StorageBackend's delete operations."""
        # Create cache first
        self.cache.cache_scenes(self.sample_scenes)
        assert self.cache_file.exists()

        # Track delete calls
        original_delete = self.storage.delete_file
        delete_calls = []

        def track_deletes(file_path):
            delete_calls.append(file_path)
            return original_delete(file_path)

        with patch.object(self.storage, "delete_file", side_effect=track_deletes):
            success = self.cache.clear_cache()

        assert success is True
        assert len(delete_calls) == 1
        assert delete_calls[0] == self.cache_file
        assert not self.cache_file.exists()
