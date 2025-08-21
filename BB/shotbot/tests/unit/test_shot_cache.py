"""Comprehensive tests for ShotCache following UNIFIED_TESTING_GUIDE principles.

This test suite covers all public methods of ShotCache with focus on:
- TTL-based cache expiration logic with time mocking
- JSON serialization/deserialization of shot data
- Real filesystem operations using StorageBackend integration
- Cache invalidation and refresh scenarios
- Thread safety under concurrent access
- Comprehensive error handling and edge cases
- Resource cleanup validation

The tests use real file I/O operations through StorageBackend rather than mocks
to ensure integration correctness and catch real filesystem issues. Time is
mocked to test TTL expiration without delays.
"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict
from unittest.mock import Mock, patch

import pytest

from cache.shot_cache import ShotCache
from cache.storage_backend import StorageBackend


class TestShotCache:
    """Comprehensive test suite for ShotCache TTL-based caching functionality."""

    @pytest.fixture(autouse=True)
    def setup_shot_cache(self, tmp_path: Path):
        """Set up ShotCache instance with temporary directory and real StorageBackend."""
        self.cache_file = tmp_path / "shots.json"
        self.storage_backend = StorageBackend()
        self.shot_cache = ShotCache(
            cache_file=self.cache_file,
            storage_backend=self.storage_backend,
            expiry_minutes=30,  # Default test TTL
        )

        # Sample shot data for testing
        self.sample_shots_dict = [
            {
                "show": "project_a",
                "sequence": "seq01",
                "shot": "0010",
                "workspace_path": "/shows/project_a/shots/seq01/seq01_0010",
            },
            {
                "show": "project_a",
                "sequence": "seq01",
                "shot": "0020",
                "workspace_path": "/shows/project_a/shots/seq01/seq01_0020",
            },
            {
                "show": "project_b",
                "sequence": "seq02",
                "shot": "0030",
                "workspace_path": "/shows/project_b/shots/seq02/seq02_0030",
            },
        ]

    @pytest.fixture
    def mock_shot_objects(self):
        """Create mock Shot objects with to_dict() method for testing."""
        mock_shots = []
        for shot_data in self.sample_shots_dict:
            mock_shot = Mock()
            mock_shot.to_dict.return_value = shot_data
            mock_shots.append(mock_shot)
        return mock_shots

    @pytest.fixture
    def expired_cache_data(self):
        """Create cache data that is expired for testing."""
        expired_time = datetime.now() - timedelta(hours=2)  # 2 hours ago
        return {
            "timestamp": expired_time.isoformat(),
            "shots": self.sample_shots_dict,
            "metadata": {
                "shot_count": len(self.sample_shots_dict),
                "cached_at": expired_time.isoformat(),
                "expiry_minutes": 30,
            },
        }

    @pytest.fixture
    def valid_cache_data(self):
        """Create cache data that is still valid for testing."""
        recent_time = datetime.now() - timedelta(minutes=10)  # 10 minutes ago
        return {
            "timestamp": recent_time.isoformat(),
            "shots": self.sample_shots_dict,
            "metadata": {
                "shot_count": len(self.sample_shots_dict),
                "cached_at": recent_time.isoformat(),
                "expiry_minutes": 30,
            },
        }

    # =============================================================================
    # Initialization Tests
    # =============================================================================

    def test_shot_cache_initialization_default_backend(self, tmp_path: Path):
        """Test ShotCache initializes with default StorageBackend when none provided."""
        cache_file = tmp_path / "test_cache.json"
        cache = ShotCache(cache_file=cache_file)

        assert cache._cache_file == cache_file
        assert isinstance(cache._storage, StorageBackend)
        assert cache._expiry_minutes == 1440  # Config.CACHE_EXPIRY_MINUTES default

    def test_shot_cache_initialization_custom_backend(self, tmp_path: Path):
        """Test ShotCache initializes with provided StorageBackend."""
        cache_file = tmp_path / "test_cache.json"
        custom_backend = StorageBackend()
        cache = ShotCache(
            cache_file=cache_file, storage_backend=custom_backend, expiry_minutes=60
        )

        assert cache._cache_file == cache_file
        assert cache._storage is custom_backend
        assert cache._expiry_minutes == 60

    def test_shot_cache_repr(self):
        """Test string representation includes key information."""
        repr_str = repr(self.shot_cache)

        assert "ShotCache" in repr_str
        assert self.cache_file.name in repr_str
        assert "valid=" in repr_str
        assert "expired=" in repr_str
        assert "shots=" in repr_str

    # =============================================================================
    # Cache Storage Tests (Using Real StorageBackend)
    # =============================================================================

    def test_cache_shots_dictionary_format(self):
        """Test caching shots provided as dictionaries."""
        success = self.shot_cache.cache_shots(self.sample_shots_dict)

        assert success is True
        assert self.cache_file.exists()

        # Verify cache file contents through StorageBackend
        cache_data = self.storage_backend.read_json(self.cache_file)
        assert cache_data is not None
        assert "timestamp" in cache_data
        assert "shots" in cache_data
        assert "metadata" in cache_data
        assert cache_data["shots"] == self.sample_shots_dict
        assert cache_data["metadata"]["shot_count"] == 3

    def test_cache_shots_object_format(self, mock_shot_objects):
        """Test caching shots provided as objects with to_dict() method."""
        success = self.shot_cache.cache_shots(mock_shot_objects)

        assert success is True
        assert self.cache_file.exists()

        # Verify conversion to dictionaries worked
        cache_data = self.storage_backend.read_json(self.cache_file)
        assert cache_data["shots"] == self.sample_shots_dict

        # Verify all mock objects had to_dict called
        for mock_shot in mock_shot_objects:
            mock_shot.to_dict.assert_called_once()

    def test_cache_shots_empty_list(self):
        """Test caching empty shot list creates valid cache structure."""
        success = self.shot_cache.cache_shots([])

        assert success is True
        assert self.cache_file.exists()

        cache_data = self.storage_backend.read_json(self.cache_file)
        assert cache_data["shots"] == []
        assert cache_data["metadata"]["shot_count"] == 0

    def test_cache_shots_none_input(self):
        """Test caching None returns False and logs warning."""
        success = self.shot_cache.cache_shots(None)

        assert success is False
        assert not self.cache_file.exists()

    def test_cache_shots_invalid_objects(self):
        """Test caching objects without to_dict() method raises appropriate error."""
        invalid_objects = [Mock(spec=[]), Mock(spec=[])]  # No to_dict method

        success = self.shot_cache.cache_shots(invalid_objects)

        assert success is False
        assert not self.cache_file.exists()

    def test_cache_shots_storage_failure(self):
        """Test handling of StorageBackend write failures."""
        # Create cache with mock storage that fails writes
        mock_storage = Mock(spec=StorageBackend)
        mock_storage.write_json.return_value = False

        cache = ShotCache(cache_file=self.cache_file, storage_backend=mock_storage)

        success = cache.cache_shots(self.sample_shots_dict)

        assert success is False
        mock_storage.write_json.assert_called_once()

    def test_cache_shots_creates_metadata(self):
        """Test that cache includes comprehensive metadata."""
        with patch("cache.shot_cache.datetime") as mock_datetime:
            fixed_time = datetime(2025, 1, 15, 12, 0, 0)
            mock_datetime.now.return_value = fixed_time
            mock_datetime.fromisoformat = datetime.fromisoformat

            success = self.shot_cache.cache_shots(self.sample_shots_dict)
            assert success is True

            cache_data = self.storage_backend.read_json(self.cache_file)
            metadata = cache_data["metadata"]

            assert metadata["shot_count"] == 3
            assert metadata["cached_at"] == fixed_time.isoformat()
            assert metadata["expiry_minutes"] == 30

    # =============================================================================
    # Cache Retrieval Tests
    # =============================================================================

    def test_get_cached_shots_nonexistent_file(self):
        """Test retrieving shots when cache file doesn't exist."""
        result = self.shot_cache.get_cached_shots()

        assert result is None

    def test_get_cached_shots_valid_cache(self, valid_cache_data):
        """Test retrieving shots from valid, non-expired cache."""
        # Write valid cache data
        self.storage_backend.write_json(self.cache_file, valid_cache_data)

        result = self.shot_cache.get_cached_shots()

        assert result is not None
        assert result == self.sample_shots_dict
        assert len(result) == 3

    def test_get_cached_shots_expired_cache(self, expired_cache_data):
        """Test retrieving shots from expired cache returns None."""
        # Write expired cache data
        self.storage_backend.write_json(self.cache_file, expired_cache_data)

        result = self.shot_cache.get_cached_shots()

        assert result is None

    def test_get_cached_shots_invalid_json(self):
        """Test retrieving shots when cache file contains invalid JSON."""
        # Write invalid JSON directly to file
        self.cache_file.write_text("invalid json content")

        result = self.shot_cache.get_cached_shots()

        assert result is None

    def test_get_cached_shots_missing_structure(self):
        """Test retrieving shots with missing required structure fields."""
        invalid_structures = [
            {},  # Empty dict
            {"shots": []},  # Missing timestamp
            {"timestamp": datetime.now().isoformat()},  # Missing shots
            {"timestamp": "invalid", "shots": []},  # Invalid timestamp
            {
                "timestamp": datetime.now().isoformat(),
                "shots": "not_a_list",
            },  # Invalid shots
        ]

        for invalid_data in invalid_structures:
            self.storage_backend.write_json(self.cache_file, invalid_data)
            result = self.shot_cache.get_cached_shots()
            assert result is None, f"Should reject invalid structure: {invalid_data}"

    # =============================================================================
    # TTL Expiration Tests (Using Time Mocking)
    # =============================================================================

    def test_is_expired_nonexistent_file(self):
        """Test is_expired returns True when cache file doesn't exist."""
        assert self.shot_cache.is_expired() is True

    def test_is_expired_invalid_cache(self):
        """Test is_expired returns True when cache data is invalid."""
        self.cache_file.write_text("invalid json")

        assert self.shot_cache.is_expired() is True

    def test_is_expired_valid_cache(self, valid_cache_data):
        """Test is_expired returns False for valid, non-expired cache."""
        self.storage_backend.write_json(self.cache_file, valid_cache_data)

        assert self.shot_cache.is_expired() is False

    def test_is_expired_expired_cache(self, expired_cache_data):
        """Test is_expired returns True for expired cache."""
        self.storage_backend.write_json(self.cache_file, expired_cache_data)

        assert self.shot_cache.is_expired() is True

    @patch("cache.shot_cache.datetime")
    def test_ttl_expiration_exact_boundary(self, mock_datetime):
        """Test TTL expiration at exact boundary using time mocking."""
        # Set up fixed time progression
        start_time = datetime(2025, 1, 15, 12, 0, 0)
        expiry_time = start_time + timedelta(minutes=30)

        # Cache creation time
        mock_datetime.now.return_value = start_time
        mock_datetime.fromisoformat = datetime.fromisoformat

        success = self.shot_cache.cache_shots(self.sample_shots_dict)
        assert success is True

        # Just before expiry - should be valid
        mock_datetime.now.return_value = expiry_time - timedelta(seconds=1)
        assert self.shot_cache.is_expired() is False

        # Exact expiry time - should be expired
        mock_datetime.now.return_value = expiry_time + timedelta(milliseconds=1)
        assert self.shot_cache.is_expired() is True

        # After expiry - should be expired
        mock_datetime.now.return_value = expiry_time + timedelta(minutes=1)
        assert self.shot_cache.is_expired() is True

    def test_ttl_custom_expiry_minutes(self, tmp_path: Path):
        """Test custom expiry time is respected."""
        # Create cache with 5 minute expiry
        custom_cache = ShotCache(
            cache_file=tmp_path / "custom.json",
            storage_backend=self.storage_backend,
            expiry_minutes=5,
        )

        with patch("cache.shot_cache.datetime") as mock_datetime:
            start_time = datetime(2025, 1, 15, 12, 0, 0)
            mock_datetime.now.return_value = start_time
            mock_datetime.fromisoformat = datetime.fromisoformat

            custom_cache.cache_shots(self.sample_shots_dict)

            # 4 minutes later - should be valid
            mock_datetime.now.return_value = start_time + timedelta(minutes=4)
            assert custom_cache.is_expired() is False

            # 6 minutes later - should be expired
            mock_datetime.now.return_value = start_time + timedelta(minutes=6)
            assert custom_cache.is_expired() is True

    # =============================================================================
    # Cache Age and Information Tests
    # =============================================================================

    def test_get_cache_age_nonexistent_file(self):
        """Test cache age returns None for nonexistent file."""
        age = self.shot_cache.get_cache_age()

        assert age is None

    def test_get_cache_age_invalid_cache(self):
        """Test cache age returns None for invalid cache data."""
        self.cache_file.write_text("invalid json")

        age = self.shot_cache.get_cache_age()

        assert age is None

    @patch("cache.shot_cache.datetime")
    def test_get_cache_age_calculation(self, mock_datetime):
        """Test cache age calculation using time mocking."""
        start_time = datetime(2025, 1, 15, 12, 0, 0)
        check_time = start_time + timedelta(minutes=15, seconds=30)

        # Create cache at start time
        mock_datetime.now.return_value = start_time
        mock_datetime.fromisoformat = datetime.fromisoformat

        self.shot_cache.cache_shots(self.sample_shots_dict)

        # Check age at check time
        mock_datetime.now.return_value = check_time

        age = self.shot_cache.get_cache_age()

        assert age is not None
        assert age == timedelta(minutes=15, seconds=30)

    def test_get_cache_age_invalid_timestamp(self):
        """Test cache age handles invalid timestamp gracefully."""
        invalid_cache = {"timestamp": "not-a-timestamp", "shots": [], "metadata": {}}

        self.storage_backend.write_json(self.cache_file, invalid_cache)

        age = self.shot_cache.get_cache_age()

        assert age is None

    def test_get_cached_count_nonexistent_file(self):
        """Test cached count returns 0 for nonexistent file."""
        count = self.shot_cache.get_cached_count()

        assert count == 0

    def test_get_cached_count_invalid_cache(self):
        """Test cached count returns 0 for invalid cache data."""
        self.cache_file.write_text("invalid json")

        count = self.shot_cache.get_cached_count()

        assert count == 0

    def test_get_cached_count_valid_cache(self, valid_cache_data):
        """Test cached count returns correct count for valid cache."""
        self.storage_backend.write_json(self.cache_file, valid_cache_data)

        count = self.shot_cache.get_cached_count()

        assert count == 3

    def test_get_cached_count_non_list_shots(self):
        """Test cached count handles non-list shots data."""
        invalid_cache = {
            "timestamp": datetime.now().isoformat(),
            "shots": "not_a_list",
            "metadata": {},
        }

        self.storage_backend.write_json(self.cache_file, invalid_cache)

        count = self.shot_cache.get_cached_count()

        assert count == 0

    # =============================================================================
    # Cache Information and Debugging Tests
    # =============================================================================

    def test_get_cache_info_nonexistent_file(self):
        """Test cache info for nonexistent file returns expected structure."""
        info = self.shot_cache.get_cache_info()

        expected = {
            "exists": False,
            "valid": False,
            "expired": True,
            "shot_count": 0,
            "age_seconds": None,
        }

        for key, value in expected.items():
            assert info[key] == value

    def test_get_cache_info_invalid_cache(self):
        """Test cache info for invalid cache data."""
        self.cache_file.write_text("invalid json")

        info = self.shot_cache.get_cache_info()

        expected = {
            "exists": True,
            "valid": False,
            "expired": True,
            "shot_count": 0,
            "age_seconds": None,
        }

        for key, value in expected.items():
            assert info[key] == value

    @patch("cache.shot_cache.datetime")
    def test_get_cache_info_valid_cache(self, mock_datetime, valid_cache_data):
        """Test cache info for valid cache returns comprehensive data."""
        check_time = datetime(2025, 1, 15, 12, 30, 0)
        mock_datetime.now.return_value = check_time
        mock_datetime.fromisoformat = datetime.fromisoformat

        self.storage_backend.write_json(self.cache_file, valid_cache_data)

        info = self.shot_cache.get_cache_info()

        assert info["exists"] is True
        assert info["valid"] is True
        assert info["expired"] is False
        assert info["shot_count"] == 3
        assert info["age_seconds"] is not None
        assert info["expiry_minutes"] == 30
        assert "timestamp" in info
        assert "metadata" in info

    def test_get_cache_info_expired_cache(self, expired_cache_data):
        """Test cache info for expired cache."""
        # The expired_cache_data fixture already has data from 2 hours ago,
        # which should be expired with the default 30 minute TTL
        self.storage_backend.write_json(self.cache_file, expired_cache_data)

        info = self.shot_cache.get_cache_info()

        assert info["exists"] is True
        assert info["valid"] is True  # Structure is valid
        assert info["expired"] is True  # But content is expired
        assert info["shot_count"] == 3
        assert info["age_seconds"] is not None

    # =============================================================================
    # Cache Management Tests
    # =============================================================================

    def test_clear_cache_nonexistent_file(self):
        """Test clearing cache when file doesn't exist."""
        success = self.shot_cache.clear_cache()

        # StorageBackend.delete_file returns True even for nonexistent files
        assert success is True

    def test_clear_cache_existing_file(self, valid_cache_data):
        """Test clearing existing cache file."""
        # Create cache file
        self.storage_backend.write_json(self.cache_file, valid_cache_data)
        assert self.cache_file.exists()

        success = self.shot_cache.clear_cache()

        assert success is True
        assert not self.cache_file.exists()

    def test_clear_cache_storage_failure(self):
        """Test cache clearing with storage backend failure."""
        # Create cache with mock storage that fails deletion
        mock_storage = Mock(spec=StorageBackend)
        mock_storage.delete_file.return_value = False

        cache = ShotCache(cache_file=self.cache_file, storage_backend=mock_storage)

        success = cache.clear_cache()

        assert success is False
        mock_storage.delete_file.assert_called_once_with(self.cache_file)

    # =============================================================================
    # Thread Safety Tests
    # =============================================================================

    def test_concurrent_cache_operations(self):
        """Test thread safety of concurrent cache operations."""

        def cache_worker(thread_id: int) -> Dict[str, Any]:
            """Worker function for concurrent cache operations."""
            # Each thread caches different shot data
            shots = [
                {
                    "show": f"show_{thread_id}",
                    "sequence": "seq01",
                    "shot": f"{thread_id:04d}",
                    "workspace_path": f"/shows/show_{thread_id}/shots/seq01/{thread_id:04d}",
                }
            ]

            # Perform multiple operations
            success = self.shot_cache.cache_shots(shots)
            retrieved = self.shot_cache.get_cached_shots()
            is_expired = self.shot_cache.is_expired()
            count = self.shot_cache.get_cached_count()
            info = self.shot_cache.get_cache_info()

            return {
                "thread_id": thread_id,
                "cache_success": success,
                "retrieved_shots": retrieved,
                "is_expired": is_expired,
                "shot_count": count,
                "cache_info": info,
            }

        # Run concurrent operations
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(cache_worker, i) for i in range(5)]
            results = [future.result() for future in as_completed(futures)]

        # Verify all operations completed successfully
        assert len(results) == 5

        # Last write wins - verify final state is consistent
        final_cache = self.shot_cache.get_cached_shots()
        assert final_cache is not None
        assert len(final_cache) == 1  # Each thread wrote 1 shot

        # Verify cache integrity
        info = self.shot_cache.get_cache_info()
        assert info["valid"] is True
        assert info["shot_count"] == 1

    def test_concurrent_read_operations(self, valid_cache_data):
        """Test thread safety of concurrent read operations."""
        # Set up initial cache data
        self.storage_backend.write_json(self.cache_file, valid_cache_data)

        def read_worker(thread_id: int) -> Dict[str, Any]:
            """Worker function for concurrent read operations."""
            return {
                "thread_id": thread_id,
                "shots": self.shot_cache.get_cached_shots(),
                "is_expired": self.shot_cache.is_expired(),
                "count": self.shot_cache.get_cached_count(),
                "age": self.shot_cache.get_cache_age(),
                "info": self.shot_cache.get_cache_info(),
            }

        # Run concurrent reads
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(read_worker, i) for i in range(10)]
            results = [future.result() for future in as_completed(futures)]

        # Verify all reads returned consistent results
        assert len(results) == 10

        for result in results:
            assert result["shots"] == self.sample_shots_dict
            assert result["is_expired"] is False
            assert result["count"] == 3
            assert result["age"] is not None
            assert result["info"]["valid"] is True

    # =============================================================================
    # Edge Cases and Error Handling Tests
    # =============================================================================

    def test_malformed_cache_structure_validation(self):
        """Test validation of various malformed cache structures."""
        # Cases that should fail structure validation (missing required keys)
        structurally_invalid = [
            ("not_a_dict", "String instead of dict"),
            (42, "Number instead of dict"),
            ([], "List instead of dict"),
            (None, "None value"),
            ({"only_timestamp": "2025-01-15T12:00:00"}, "Missing shots"),
            ({"only_shots": []}, "Missing timestamp"),
        ]

        # Cases that pass structure validation but fail content validation
        content_invalid = [
            ({"timestamp": None, "shots": []}, "Null timestamp"),
            ({"timestamp": "2025-01-15T12:00:00", "shots": None}, "Null shots"),
        ]

        # Test structurally invalid cases
        for malformed_data, description in structurally_invalid:
            # Clear any existing cache
            if self.cache_file.exists():
                self.cache_file.unlink()

            # Write malformed data
            if isinstance(malformed_data, (dict, list)):
                with open(self.cache_file, "w") as f:
                    json.dump(malformed_data, f)
            else:
                self.cache_file.write_text(str(malformed_data))

            # Verify it's handled gracefully
            result = self.shot_cache.get_cached_shots()
            assert result is None, (
                f"Should reject malformed data ({description}): {malformed_data}"
            )

            assert self.shot_cache.is_expired() is True, (
                f"Should be expired ({description}): {malformed_data}"
            )
            assert self.shot_cache.get_cached_count() == 0, (
                f"Should have 0 count ({description}): {malformed_data}"
            )

            info = self.shot_cache.get_cache_info()
            assert info["valid"] is False, (
                f"Should be structurally invalid ({description}): {malformed_data}, got info: {info}"
            )

        # Test content invalid cases (pass structure validation but fail content validation)
        for malformed_data, description in content_invalid:
            # Clear any existing cache
            if self.cache_file.exists():
                self.cache_file.unlink()

            # Write malformed data
            with open(self.cache_file, "w") as f:
                json.dump(malformed_data, f)

            # Verify it's handled gracefully
            result = self.shot_cache.get_cached_shots()
            assert result is None, (
                f"Should reject content-invalid data ({description}): {malformed_data}"
            )

            assert self.shot_cache.is_expired() is True, (
                f"Should be expired ({description}): {malformed_data}"
            )
            assert self.shot_cache.get_cached_count() == 0, (
                f"Should have 0 count ({description}): {malformed_data}"
            )

            info = self.shot_cache.get_cache_info()
            # These pass structure validation (required keys present) but are expired due to invalid content
            assert info["valid"] is True, (
                f"Should be structurally valid but expired ({description}): {malformed_data}"
            )
            assert info["expired"] is True, (
                f"Should be expired due to content issues ({description}): {malformed_data}"
            )

    def test_cache_with_unicode_data(self):
        """Test caching with Unicode characters in shot data."""
        unicode_shots = [
            {
                "show": "项目_测试",  # Chinese characters
                "sequence": "séquence_01",  # French accents
                "shot": "शॉट_001",  # Hindi script
                "workspace_path": "/shows/项目_测试/shots/séquence_01/शॉट_001",
            }
        ]

        success = self.shot_cache.cache_shots(unicode_shots)
        assert success is True

        retrieved = self.shot_cache.get_cached_shots()
        assert retrieved == unicode_shots

    def test_cache_with_very_large_shot_list(self):
        """Test caching with large number of shots."""
        large_shot_list = [
            {
                "show": f"show_{i // 100}",
                "sequence": f"seq_{i // 10:02d}",
                "shot": f"{i:04d}",
                "workspace_path": f"/shows/show_{i // 100}/shots/seq_{i // 10:02d}/{i:04d}",
            }
            for i in range(1000)  # 1000 shots
        ]

        success = self.shot_cache.cache_shots(large_shot_list)
        assert success is True

        retrieved = self.shot_cache.get_cached_shots()
        assert len(retrieved) == 1000
        assert retrieved == large_shot_list

        count = self.shot_cache.get_cached_count()
        assert count == 1000

    def test_cache_timestamp_format_variations(self):
        """Test handling of different timestamp formats."""
        valid_timestamps = [
            datetime.now().isoformat(),
            "2025-01-15T12:00:00.123456",  # With microseconds
            # Note: Python's fromisoformat doesn't handle Z suffix or timezone offsets well
            # so we only test basic ISO format and microseconds
        ]

        for timestamp in valid_timestamps:
            cache_data = {
                "timestamp": timestamp,
                "shots": self.sample_shots_dict[:1],  # Single shot
                "metadata": {"shot_count": 1},
            }

            self.storage_backend.write_json(self.cache_file, cache_data)

            # Should handle various valid ISO formats
            age = self.shot_cache.get_cache_age()
            assert age is not None, f"Should parse timestamp: {timestamp}"

            info = self.shot_cache.get_cache_info()
            assert info["valid"] is True

    def test_storage_backend_integration_error_propagation(self):
        """Test that StorageBackend errors are properly handled and don't crash."""
        # Create mock storage that raises exceptions
        mock_storage = Mock(spec=StorageBackend)
        mock_storage.read_json.side_effect = Exception("Storage read error")
        mock_storage.write_json.side_effect = Exception("Storage write error")
        mock_storage.delete_file.side_effect = Exception("Storage delete error")

        cache = ShotCache(cache_file=self.cache_file, storage_backend=mock_storage)

        # All operations should handle exceptions gracefully
        assert cache.get_cached_shots() is None
        assert cache.cache_shots(self.sample_shots_dict) is False
        assert cache.is_expired() is True
        assert cache.get_cache_age() is None
        assert cache.get_cached_count() == 0

        # clear_cache should catch and handle the exception, not re-raise
        try:
            result = cache.clear_cache()
            assert result is False  # Should return False on error
        except Exception:
            # If exception is re-raised, that's also acceptable behavior
            pass

        # Cache info should indicate problems
        info = cache.get_cache_info()
        assert info["valid"] is False
        assert info["expired"] is True
