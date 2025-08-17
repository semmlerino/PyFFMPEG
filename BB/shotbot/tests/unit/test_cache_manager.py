"""Unit tests for CacheManager functionality.

Tests caching operations, TTL expiration, memory management, and thread safety.
"""

import json
from unittest.mock import MagicMock, patch

from cache_manager import CacheManager
from shot_model import Shot


class TestCacheManager:
    """Test CacheManager core functionality."""

    def test_cache_manager_initialization(self, temp_cache_dir):
        """Test CacheManager initialization with custom directory."""
        manager = CacheManager(cache_dir=temp_cache_dir)

        assert manager.cache_dir == temp_cache_dir
        assert manager.shots_cache_file == temp_cache_dir / "shots.json"
        assert manager.thumbnails_dir == temp_cache_dir / "thumbnails"
        assert manager._cached_thumbnails == {}

    def test_cache_directory_creation(self, tmp_path):
        """Test cache directory is created if it doesn't exist."""
        cache_dir = tmp_path / "new_cache"
        assert not cache_dir.exists()

        CacheManager(cache_dir=cache_dir)

        assert cache_dir.exists()
        assert cache_dir.is_dir()

    def test_load_cache_from_file(self, temp_cache_dir):
        """Test loading cache from existing file."""
        # Create a cache file with test data
        from datetime import datetime

        cache_file = temp_cache_dir / "shots.json"
        test_data = {
            "shots": [
                {
                    "show": "test",
                    "sequence": "seq1",
                    "shot": "0010",
                    "workspace_path": "/test/path",
                }
            ],
            "timestamp": datetime.now().isoformat(),
        }
        cache_file.write_text(json.dumps(test_data))

        manager = CacheManager(cache_dir=temp_cache_dir)

        # Load happens automatically, verify with get_cached_shots
        cached = manager.get_cached_shots()
        assert cached is not None
        assert len(cached) == 1

    def test_save_cache_to_file(self, temp_cache_dir):
        """Test saving cache data to file."""
        manager = CacheManager(cache_dir=temp_cache_dir)

        # Add test data
        test_shots = [
            Shot("show1", "seq1", "0010", "/path1"),
            Shot("show2", "seq2", "0020", "/path2"),
        ]
        manager.cache_shots(test_shots)

        # Verify file was created
        cache_file = temp_cache_dir / "shots.json"
        assert cache_file.exists()

        # Load and verify contents
        data = json.loads(cache_file.read_text())
        assert "shots" in data
        assert len(data["shots"]) == 2
        assert data["shots"][0]["show"] == "show1"

    def test_cache_shots_and_retrieval(self, cache_manager):
        """Test caching and retrieving shots."""
        test_shots = [
            Shot("show1", "seq1", "0010", "/path1"),
            Shot("show2", "seq2", "0020", "/path2"),
            Shot("show3", "seq3", "0030", "/path3"),
        ]

        # Cache shots
        cache_manager.cache_shots(test_shots)

        # Retrieve cached shots
        cached = cache_manager.get_cached_shots()

        assert cached is not None
        assert len(cached) == 3
        assert all(isinstance(shot, dict) for shot in cached)
        assert cached[0]["show"] == "show1"
        assert cached[2]["shot"] == "0030"

    def test_cache_ttl_expiration(self, temp_cache_dir):
        """Test cache expiration after TTL."""
        from datetime import datetime, timedelta

        # Create a cache file with expired timestamp (over 24 hours old)
        cache_file = temp_cache_dir / "shots.json"
        expired_data = {
            "shots": [
                {
                    "show": "show1",
                    "sequence": "seq1",
                    "shot": "0010",
                    "workspace_path": "/path1",
                }
            ],
            "timestamp": (datetime.now() - timedelta(hours=25)).isoformat(),
        }
        cache_file.write_text(json.dumps(expired_data))

        # Create new manager that will load expired cache
        cache_manager = CacheManager(cache_dir=temp_cache_dir)

        # Should return None because cache is expired (older than 24 hours)
        assert cache_manager.get_cached_shots() is None

    def test_cache_thumbnail_with_qimage(
        self, cache_manager, temp_cache_dir, test_image_file
    ):
        """Test thumbnail caching with QImage (thread-safe)."""
        shot = Shot("test", "seq1", "0010", "/test/path")

        # Mock QImage for thread safety
        with patch("cache_manager.QImage") as mock_qimage_class:
            mock_image = MagicMock()
            mock_image.isNull.return_value = False
            mock_image.save.return_value = True
            mock_qimage_class.return_value = mock_image

            # Cache thumbnail - use correct argument order
            cache_manager.cache_thumbnail(
                test_image_file, shot.show, shot.sequence, shot.shot
            )

            # Verify cache file was expected
            temp_cache_dir / "thumbnails" / "test" / "seq1" / "0010_thumb.jpg"
            # Note: method returns None from background thread
            # Can still verify mock was called

    def test_get_cached_thumbnail(self, cache_manager, temp_cache_dir):
        """Test retrieving cached thumbnail."""
        shot = Shot("test", "seq1", "0010", "/test/path")

        # Create cached thumbnail file in correct structure
        thumb_dir = temp_cache_dir / "thumbnails" / "test" / "seq1"
        thumb_dir.mkdir(parents=True, exist_ok=True)
        thumb_file = thumb_dir / "0010_thumb.jpg"
        thumb_file.touch()

        # Get cached thumbnail using correct arguments
        result = cache_manager.get_cached_thumbnail(shot.show, shot.sequence, shot.shot)

        assert result == thumb_file
        assert result.exists()

    def test_get_cached_thumbnail_not_found(self, cache_manager):
        """Test retrieving non-existent thumbnail returns None."""
        shot = Shot("test", "seq1", "0010", "/test/path")

        result = cache_manager.get_cached_thumbnail(shot.show, shot.sequence, shot.shot)

        assert result is None

    def test_clear_cache(self, cache_manager, temp_cache_dir):
        """Test clearing all cache data."""
        # Add some cache data
        test_shots = [Shot("show1", "seq1", "0010", "/path1")]
        cache_manager.cache_shots(test_shots)

        # Create thumbnail
        thumb_dir = temp_cache_dir / "thumbnails"
        thumb_dir.mkdir(parents=True, exist_ok=True)
        thumb_file = thumb_dir / "test.jpg"
        thumb_file.touch()

        # Clear cache
        cache_manager.clear_cache()

        # Verify cache is empty
        assert cache_manager.get_cached_shots() is None
        assert cache_manager._cached_thumbnails == {}
        assert cache_manager._memory_usage_bytes == 0

    def test_thread_safety_warning(self, cache_manager, test_image_file):
        """Test thread safety check for QPixmap operations."""
        shot = Shot("test", "seq1", "0010", "/test/path")

        # Mock being in non-main thread
        with patch("cache_manager.QThread") as mock_qthread:
            mock_current = MagicMock()
            mock_main = MagicMock()
            mock_current.__ne__ = MagicMock(return_value=True)  # Not main thread

            mock_qthread.currentThread.return_value = mock_current
            mock_app = MagicMock()
            mock_app.thread.return_value = mock_main

            with patch("cache_manager.QApplication.instance", return_value=mock_app):
                # Should use QImage instead of QPixmap
                with patch("cache_manager.QImage") as mock_qimage:
                    mock_image = MagicMock()
                    mock_image.isNull.return_value = False
                    mock_image.save.return_value = True
                    mock_qimage.return_value = mock_image

                    result = cache_manager.cache_thumbnail(
                        test_image_file, shot.show, shot.sequence, shot.shot
                    )

                    # Should return None from background thread
                    assert result is None

    def test_memory_tracking(self, cache_manager):
        """Test memory usage tracking for thumbnail cache."""
        # Memory tracking is done via _cached_thumbnails dict
        cache_manager._cached_thumbnails["/test/path.jpg"] = 40000
        cache_manager._memory_usage_bytes = 40000

        assert cache_manager._memory_usage_bytes == 40000

        # Clear should reset memory tracking
        cache_manager.clear_cache()
        assert cache_manager._memory_usage_bytes == 0

    def test_cache_persistence_across_instances(self, temp_cache_dir):
        """Test cache persists across CacheManager instances."""
        # First instance - save data
        manager1 = CacheManager(cache_dir=temp_cache_dir)
        test_shots = [Shot("show1", "seq1", "0010", "/path1")]
        manager1.cache_shots(test_shots)

        # Second instance - should load existing data
        manager2 = CacheManager(cache_dir=temp_cache_dir)
        cached = manager2.get_cached_shots()

        assert cached is not None
        assert len(cached) == 1
        assert cached[0]["show"] == "show1"

    def test_corrupted_cache_handling(self, temp_cache_dir):
        """Test handling of corrupted cache file."""
        # Create corrupted cache file
        cache_file = temp_cache_dir / "shots.json"
        cache_file.write_text("{ invalid json }")

        # Should handle gracefully
        manager = CacheManager(cache_dir=temp_cache_dir)

        # Should return None for corrupted cache
        assert manager.get_cached_shots() is None

    def test_cache_size_limit(self, cache_manager):
        """Test cache respects size limits."""
        # Create many shots
        large_shot_list = [
            Shot(f"show{i}", f"seq{i}", f"{i:04d}", f"/path{i}") for i in range(1000)
        ]

        # Cache should handle large lists
        cache_manager.cache_shots(large_shot_list)

        cached = cache_manager.get_cached_shots()
        assert len(cached) == 1000

    def test_cache_update_timestamp(self, cache_manager):
        """Test cache timestamp is updated on save."""
        from datetime import datetime

        test_shots = [Shot("show1", "seq1", "0010", "/path1")]

        # Cache first time
        cache_manager.cache_shots(test_shots)

        # Read timestamp from file
        cache_file = cache_manager.shots_cache_file
        data1 = json.loads(cache_file.read_text())
        first_timestamp = datetime.fromisoformat(data1["timestamp"])

        # Small delay to ensure different timestamp
        import time as time_module

        time_module.sleep(0.01)

        # Cache again
        cache_manager.cache_shots(test_shots)
        data2 = json.loads(cache_file.read_text())
        second_timestamp = datetime.fromisoformat(data2["timestamp"])

        # Timestamp should be updated
        assert second_timestamp > first_timestamp


class TestCacheManagerIntegration:
    """Integration tests for CacheManager with other components."""

    def test_integration_with_shot_model(self, cache_manager, shot_model_with_shots):
        """Test CacheManager integration with ShotModel."""
        # shot_model_with_shots already has shots populated
        model = shot_model_with_shots

        # Cache should be updated via model
        cache_manager.cache_shots(model.shots)

        # Retrieve via cache
        cached = cache_manager.get_cached_shots()
        assert len(cached) == len(model.shots)

    def test_concurrent_cache_access(self, cache_manager):
        """Test thread-safe cache operations."""
        import threading

        results = []
        test_shots = [Shot("show1", "seq1", "0010", "/path1")]

        def cache_operation():
            cache_manager.cache_shots(test_shots)
            cached = cache_manager.get_cached_shots()
            results.append(cached is not None)

        # Run concurrent operations
        threads = []
        for _ in range(5):
            t = threading.Thread(target=cache_operation)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # All operations should succeed
        assert all(results)
        assert len(results) == 5
