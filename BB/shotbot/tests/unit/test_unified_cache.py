"""Test unified cache implementation that replaces shot_cache + threede_cache."""

from __future__ import annotations

# Standard library imports
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

# Third-party imports
import pytest

from cache.storage_backend import StorageBackend

# Local application imports
from cache.unified_cache import UnifiedCache, create_shot_cache, create_threede_cache


class MockItem:
    """Mock item with to_dict() method for testing object conversion."""

    def __init__(self, name: str, value: int) -> None:
        self.name = name
        self.value = value

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "value": self.value}


@pytest.fixture
def temp_cache_file():
    """Create a temporary cache file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        temp_path = Path(f.name)
    # Delete the file immediately so tests start with no file
    temp_path.unlink()
    yield temp_path
    # Cleanup
    if temp_path.exists():
        temp_path.unlink()


@pytest.fixture
def storage_backend():
    """Create a storage backend for testing."""
    return StorageBackend()


@pytest.fixture
def shot_cache(temp_cache_file, storage_backend):
    """Create a unified cache configured for shots."""
    return UnifiedCache(
        cache_file=temp_cache_file,
        data_key="shots",
        storage_backend=storage_backend,
        expiry_minutes=30,
        item_count_key="shot_count",
    )


@pytest.fixture
def scene_cache(temp_cache_file, storage_backend):
    """Create a unified cache configured for scenes."""
    return UnifiedCache(
        cache_file=temp_cache_file,
        data_key="scenes",
        storage_backend=storage_backend,
        expiry_minutes=30,
        item_count_key="scene_count",
    )


class TestUnifiedCacheBasics:
    """Test basic unified cache functionality."""

    def test_initialization(self, temp_cache_file, storage_backend) -> None:
        """Test cache initialization with different configurations."""
        cache = UnifiedCache(
            cache_file=temp_cache_file,
            data_key="test_items",
            storage_backend=storage_backend,
            expiry_minutes=60,
        )

        assert cache._cache_file == temp_cache_file
        assert cache._data_key == "test_items"
        assert cache._expiry_minutes == 60
        assert cache._item_count_key == "test_item_count"  # Auto-generated

    def test_set_expiry_minutes(self, shot_cache) -> None:
        """Test setting expiry time."""
        shot_cache.set_expiry_minutes(45)
        assert shot_cache._expiry_minutes == 45

    def test_empty_cache_state(self, shot_cache) -> None:
        """Test behavior when cache file doesn't exist."""
        assert shot_cache.get_cached_data() is None
        assert shot_cache.is_expired() is True
        assert shot_cache.has_valid_cache() is False
        assert shot_cache.get_cache_age() is None
        assert shot_cache.get_cached_count() == 0
        assert shot_cache.get_cache_metadata() is None


class TestUnifiedCacheDataOperations:
    """Test data caching and retrieval operations."""

    def test_cache_and_retrieve_dictionaries(self, shot_cache) -> None:
        """Test caching and retrieving dictionary data."""
        test_data = [
            {"name": "shot_001", "status": "active"},
            {"name": "shot_002", "status": "completed"},
        ]

        # Cache the data
        assert shot_cache.cache_data(test_data) is True

        # Retrieve the data
        cached_data = shot_cache.get_cached_data()
        assert cached_data is not None
        assert len(cached_data) == 2
        assert cached_data == test_data

    def test_cache_and_retrieve_objects(self, shot_cache) -> None:
        """Test caching and retrieving object data."""
        test_objects = [MockItem("item1", 100), MockItem("item2", 200)]

        # Cache the objects
        assert shot_cache.cache_data(test_objects) is True

        # Retrieve as dictionaries
        cached_data = shot_cache.get_cached_data()
        assert cached_data is not None
        assert len(cached_data) == 2
        assert cached_data[0] == {"name": "item1", "value": 100}
        assert cached_data[1] == {"name": "item2", "value": 200}

    def test_cache_with_metadata(self, scene_cache) -> None:
        """Test caching with custom metadata."""
        test_data = [{"scene": "scene001.3de"}]
        custom_metadata = {"scan_type": "full", "user": "test_user"}

        # Cache with metadata
        assert scene_cache.cache_data(test_data, metadata=custom_metadata) is True

        # Check metadata was preserved and enhanced
        metadata = scene_cache.get_cache_metadata()
        assert metadata is not None
        assert metadata["scan_type"] == "full"
        assert metadata["user"] == "test_user"
        assert metadata["scene_count"] == 1
        assert "cached_at" in metadata

    def test_cache_empty_data(self, shot_cache) -> None:
        """Test caching empty data list."""
        assert shot_cache.cache_data([]) is True

        cached_data = shot_cache.get_cached_data()
        assert cached_data == []
        assert shot_cache.get_cached_count() == 0

    def test_cache_none_data(self, shot_cache) -> None:
        """Test attempting to cache None data."""
        assert shot_cache.cache_data(None) is False  # type: ignore[arg-type]

    def test_cache_objects_without_to_dict(self, shot_cache) -> None:
        """Test caching objects that don't have to_dict() method."""
        bad_objects = ["string1", "string2"]  # Strings don't have to_dict()

        assert shot_cache.cache_data(bad_objects) is False


class TestUnifiedCacheTTL:
    """Test TTL (Time To Live) functionality."""

    def test_cache_expiry_check(self, shot_cache) -> None:
        """Test cache expiry detection."""
        test_data = [{"name": "test"}]

        # Cache data
        shot_cache.cache_data(test_data)

        # Should not be expired immediately
        assert shot_cache.is_expired() is False
        assert shot_cache.has_valid_cache() is True

        # Mock an old timestamp to simulate expiry
        with patch.object(shot_cache._storage, "read_json") as mock_read:
            old_time = datetime.now() - timedelta(hours=2)
            mock_read.return_value = {
                "timestamp": old_time.isoformat(),
                "shots": test_data,
                "metadata": {"shot_count": 1},
            }

            assert shot_cache.is_expired() is True
            assert shot_cache.has_valid_cache() is False

    def test_manual_refresh_mode(self, shot_cache) -> None:
        """Test cache with expiry_minutes=0 (manual refresh only)."""
        shot_cache.set_expiry_minutes(0)
        test_data = [{"name": "test"}]

        # Cache data
        shot_cache.cache_data(test_data)

        # Mock very old timestamp - should still not expire
        with patch.object(shot_cache._storage, "read_json") as mock_read:
            old_time = datetime.now() - timedelta(days=365)
            mock_read.return_value = {
                "timestamp": old_time.isoformat(),
                "shots": test_data,
                "metadata": {"shot_count": 1},
            }

            assert shot_cache.is_expired() is False
            assert shot_cache.has_valid_cache() is True

    def test_force_refresh_needed(self, shot_cache) -> None:
        """Test force refresh logic."""
        test_data = [{"name": "test"}]
        shot_cache.cache_data(test_data)

        # Fresh cache shouldn't need force refresh
        assert shot_cache.force_refresh_needed() is False

        # Test with custom max age
        assert shot_cache.force_refresh_needed(max_age_minutes=0) is True


class TestUnifiedCacheInfo:
    """Test cache information and metadata operations."""

    def test_get_cache_info_no_file(self, shot_cache) -> None:
        """Test cache info when file doesn't exist."""
        info = shot_cache.get_cache_info()

        assert info["exists"] is False
        assert info["valid"] is False
        assert info["expired"] is True
        assert info["shot_count"] == 0
        assert info["age_seconds"] is None

    def test_get_cache_info_valid_cache(self, shot_cache) -> None:
        """Test cache info with valid cache."""
        test_data = [{"name": "shot1"}, {"name": "shot2"}]
        shot_cache.cache_data(test_data)

        info = shot_cache.get_cache_info()

        assert info["exists"] is True
        assert info["valid"] is True
        assert info["expired"] is False
        assert info["shot_count"] == 2
        assert info["age_seconds"] is not None
        assert info["age_seconds"] < 60  # Should be very recent
        assert info["expiry_minutes"] == 30

    def test_get_cache_age(self, shot_cache) -> None:
        """Test cache age calculation."""
        test_data = [{"name": "test"}]
        shot_cache.cache_data(test_data)

        age = shot_cache.get_cache_age()
        assert age is not None
        assert age.total_seconds() < 60  # Should be very recent

    def test_get_cached_count(self, shot_cache) -> None:
        """Test getting count without loading full data."""
        test_data = [{"name": f"shot_{i}"} for i in range(5)]
        shot_cache.cache_data(test_data)

        assert shot_cache.get_cached_count() == 5

    def test_clear_cache(self, shot_cache) -> None:
        """Test cache clearing."""
        test_data = [{"name": "test"}]
        shot_cache.cache_data(test_data)

        assert shot_cache.has_valid_cache() is True
        assert shot_cache.clear_cache() is True
        assert shot_cache.has_valid_cache() is False


class TestUnifiedCacheErrorHandling:
    """Test error handling and edge cases."""

    def test_corrupted_cache_file(self, shot_cache) -> None:
        """Test handling corrupted cache files."""
        # Write invalid JSON to cache file
        shot_cache._cache_file.write_text("invalid json content")

        assert shot_cache.get_cached_data() is None
        assert shot_cache.is_expired() is True
        assert shot_cache.has_valid_cache() is False

    def test_invalid_cache_structure(self, shot_cache) -> None:
        """Test handling invalid cache structure."""
        # Write valid JSON but invalid structure
        shot_cache._cache_file.write_text('{"wrong": "structure"}')

        assert shot_cache.get_cached_data() is None

    def test_missing_timestamp(self, shot_cache) -> None:
        """Test handling cache missing timestamp."""
        # Valid structure but missing timestamp
        shot_cache._cache_file.write_text('{"shots": [], "metadata": {}}')

        assert shot_cache.get_cached_data() is None

    def test_invalid_timestamp_format(self, shot_cache) -> None:
        """Test handling invalid timestamp format."""
        with patch.object(shot_cache._storage, "read_json") as mock_read:
            mock_read.return_value = {
                "timestamp": "invalid-timestamp",
                "shots": [],
                "metadata": {},
            }

            assert shot_cache.is_expired() is True


class TestUnifiedCacheFactoryFunctions:
    """Test factory functions for backward compatibility."""

    def test_create_shot_cache(self, temp_cache_file) -> None:
        """Test shot cache factory function."""
        cache = create_shot_cache(temp_cache_file, expiry_minutes=45)

        assert cache._data_key == "shots"
        assert cache._item_count_key == "shot_count"
        assert cache._expiry_minutes == 45

    def test_create_threede_cache(self, temp_cache_file) -> None:
        """Test 3DE scene cache factory function."""
        cache = create_threede_cache(temp_cache_file, expiry_minutes=60)

        assert cache._data_key == "scenes"
        assert cache._item_count_key == "scene_count"
        assert cache._expiry_minutes == 60


class TestUnifiedCacheRepr:
    """Test string representation."""

    def test_repr_empty_cache(self, shot_cache) -> None:
        """Test __repr__ with empty cache."""
        repr_str = repr(shot_cache)
        assert "UnifiedCache[shots]" in repr_str
        assert "valid=False" in repr_str
        assert "expired=True" in repr_str
        assert "items=0" in repr_str

    def test_repr_valid_cache(self, shot_cache) -> None:
        """Test __repr__ with valid cache."""
        test_data = [{"name": "shot1"}]
        shot_cache.cache_data(test_data)

        repr_str = repr(shot_cache)
        assert "UnifiedCache[shots]" in repr_str
        assert "valid=True" in repr_str
        assert "expired=False" in repr_str
        assert "items=1" in repr_str


class TestUnifiedCacheBackwardCompatibility:
    """Test that unified cache can replace shot_cache and threede_cache."""

    def test_shot_cache_methods(self, shot_cache) -> None:
        """Test that shot cache methods work as expected."""
        # This simulates the original ShotCache.get_cached_shots() -> get_cached_data()
        # and ShotCache.cache_shots() -> cache_data()

        test_shots = [{"show": "test_show", "sequence": "010", "shot": "010"}]

        # Equivalent to cache_shots()
        assert shot_cache.cache_data(test_shots) is True

        # Equivalent to get_cached_shots()
        cached_shots = shot_cache.get_cached_data()
        assert cached_shots == test_shots

    def test_threede_cache_methods(self, scene_cache) -> None:
        """Test that 3DE cache methods work as expected."""
        # This simulates the original ThreeDECache.get_cached_scenes() -> get_cached_data()
        # and ThreeDECache.cache_scenes() -> cache_data()

        test_scenes = [
            {"shot": "010", "user": "test_user", "scene_path": "/path/to/scene.3de"}
        ]
        metadata = {"scan_type": "full"}

        # Equivalent to cache_scenes()
        assert scene_cache.cache_data(test_scenes, metadata=metadata) is True

        # Equivalent to get_cached_scenes()
        cached_scenes = scene_cache.get_cached_data()
        assert cached_scenes == test_scenes

        # Equivalent to get_cache_metadata()
        cached_metadata = scene_cache.get_cache_metadata()
        assert cached_metadata["scan_type"] == "full"

    def test_all_original_methods_covered(self) -> None:
        """Verify that all original methods from both caches are covered."""
        # Methods that should exist in unified cache:
        required_methods = [
            "set_expiry_minutes",
            "get_cached_data",  # was get_cached_shots/get_cached_scenes
            "cache_data",  # was cache_shots/cache_scenes
            "is_expired",
            "get_cache_age",
            "get_cached_count",
            "get_cache_metadata",  # from ThreeDECache
            "clear_cache",
            "get_cache_info",
            "force_refresh_needed",  # from ThreeDECache
            "has_valid_cache",  # from ThreeDECache
        ]

        cache = UnifiedCache(Path("/tmp/test"), "test")

        for method_name in required_methods:
            assert hasattr(cache, method_name), f"Missing method: {method_name}"
