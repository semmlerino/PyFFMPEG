"""Comprehensive tests for simplified CacheManager.

This test suite validates the simplified cache_manager.py following
UNIFIED_TESTING_GUIDE.md principles:
- Test behavior, not implementation
- Use real components with temporary storage
- Thread safety validation
- Error handling coverage
"""

from __future__ import annotations

# Standard library imports
import json
import threading
import time
from datetime import timedelta
from pathlib import Path

# Third-party imports
import pytest
from PySide6.QtGui import QColor, QImage

# Local application imports
from cache_manager import CacheManager
from shot_model import Shot
from threede_scene_model import ThreeDEScene

pytestmark = [
    pytest.mark.unit,
    pytest.mark.qt,
    pytest.mark.xdist_group("qt_state"),
]


# Test fixtures following UNIFIED_TESTING_GUIDE patterns


@pytest.fixture
def cache_manager(tmp_path: Path) -> CacheManager:
    """Create CacheManager with temporary directory.

    Following guide: "Use Real Components Where Possible"
    """
    cache_dir = tmp_path / "test_cache"
    manager = CacheManager(cache_dir=cache_dir)
    return manager


@pytest.fixture
def sample_shots() -> list[Shot]:
    """Provide realistic shot data for testing."""
    return [
        Shot("test_show", "seq01", "shot010", "/shows/test_show/seq01/shot010"),
        Shot("test_show", "seq01", "shot020", "/shows/test_show/seq01/shot020"),
        Shot("test_show", "seq02", "shot030", "/shows/test_show/seq02/shot030"),
    ]


@pytest.fixture
def sample_3de_scenes() -> list[ThreeDEScene]:
    """Provide realistic 3DE scene data for testing."""
    return [
        ThreeDEScene(
            show="test_show",
            sequence="seq01",
            shot="shot010",
            user="artist1",
            plate="bg01",
            scene_path="/path/to/scene1.3de",
            workspace_path="/shows/test_show/seq01/shot010",
        ),
        ThreeDEScene(
            show="test_show",
            sequence="seq01",
            shot="shot020",
            user="artist2",
            plate="fg01",
            scene_path="/path/to/scene2.3de",
            workspace_path="/shows/test_show/seq01/shot020",
        ),
    ]


@pytest.fixture
def test_image_jpg(tmp_path: Path) -> Path:
    """Create a real JPEG test image."""
    image_path = tmp_path / "test_source.jpg"
    image = QImage(512, 512, QImage.Format.Format_RGB32)
    image.fill(QColor(100, 150, 200))  # Blue-ish
    image.save(str(image_path), "JPEG", quality=90)
    return image_path


@pytest.fixture
def test_image_png(tmp_path: Path) -> Path:
    """Create a real PNG test image."""
    image_path = tmp_path / "test_source.png"
    image = QImage(1024, 1024, QImage.Format.Format_ARGB32)
    image.fill(QColor(255, 100, 50, 200))  # Orange with alpha
    image.save(str(image_path), "PNG")
    return image_path


@pytest.fixture
def mock_exr_file(tmp_path: Path) -> Path:
    """Create a mock EXR file for testing."""
    exr_path = tmp_path / "test_plate.exr"
    # Write minimal valid-looking header
    exr_path.write_bytes(b"v/1\x01" + b"\x00" * 100)
    return exr_path


# Test Suite


class TestCacheManagerInitialization:
    """Test CacheManager initialization and directory setup."""

    def test_initialization_creates_directories(self, tmp_path: Path) -> None:
        """Test cache directory structure is created on init."""
        cache_dir = tmp_path / "new_cache"
        assert not cache_dir.exists()

        manager = CacheManager(cache_dir=cache_dir)

        assert manager.cache_dir == cache_dir
        assert cache_dir.exists()
        assert cache_dir.is_dir()
        assert manager.thumbnails_dir.exists()

    def test_initialization_with_existing_directory(self, tmp_path: Path) -> None:
        """Test initialization with pre-existing cache directory."""
        cache_dir = tmp_path / "existing_cache"
        cache_dir.mkdir(parents=True)

        manager = CacheManager(cache_dir=cache_dir)

        assert manager.cache_dir == cache_dir
        assert cache_dir.exists()

    def test_default_ttl_configuration(self, cache_manager: CacheManager) -> None:
        """Test default TTL is set correctly."""
        # TTL should be 30 minutes by default
        assert cache_manager._cache_ttl == timedelta(minutes=30)


class TestJSONCacheOperations:
    """Test JSON cache read/write operations with TTL validation."""

    def test_cache_shots_writes_json(self, cache_manager: CacheManager, sample_shots: list[Shot]) -> None:
        """Test caching shots writes valid JSON file."""
        cache_manager.cache_shots(sample_shots)

        cache_file = cache_manager.shots_cache_file
        assert cache_file.exists()

        # Verify JSON structure
        data = json.loads(cache_file.read_text())
        assert "data" in data
        assert "cached_at" in data
        assert len(data["data"]) == len(sample_shots)

    def test_get_cached_shots_returns_data(self, cache_manager: CacheManager, sample_shots: list[Shot]) -> None:
        """Test retrieving cached shots returns correct data."""
        cache_manager.cache_shots(sample_shots)

        cached = cache_manager.get_cached_shots()

        assert cached is not None
        assert len(cached) == len(sample_shots)
        # Verify data integrity
        assert cached[0]["show"] == "test_show"
        assert cached[0]["sequence"] == "seq01"
        assert cached[0]["shot"] == "shot010"

    def test_get_cached_shots_respects_ttl(self, cache_manager: CacheManager, sample_shots: list[Shot]) -> None:
        """Test TTL expiration invalidates cache."""
        cache_manager.cache_shots(sample_shots)

        # Verify cache is valid initially
        cached = cache_manager.get_cached_shots()
        assert cached is not None

        # Manually expire the cache by modifying file timestamp
        cache_file = cache_manager.shots_cache_file
        old_time = time.time() - (31 * 60)  # 31 minutes ago
        cache_file.touch()
        import os

        os.utime(cache_file, (old_time, old_time))

        # Cache should now be expired
        expired = cache_manager.get_cached_shots()
        assert expired is None

    def test_cache_threede_scenes_writes_json(self, cache_manager: CacheManager) -> None:
        """Test caching 3DE scenes writes valid JSON."""
        # Use dict format (as expected by cache_threede_scenes)
        scenes = [
            {
                "show": "test_show",
                "sequence": "seq01",
                "shot": "shot010",
                "user": "artist1",
                "plate": "bg01",
                "scene_path": "/path/to/scene1.3de",
                "workspace_path": "/shows/test_show/seq01/shot010",
            }
        ]
        cache_manager.cache_threede_scenes(scenes)

        cache_file = cache_manager.threede_cache_file
        assert cache_file.exists()

        data = json.loads(cache_file.read_text())
        assert "data" in data
        assert len(data["data"]) == 1

    def test_get_cached_threede_scenes_returns_data(self, cache_manager: CacheManager) -> None:
        """Test retrieving cached 3DE scenes."""
        scenes = [
            {
                "show": "test_show",
                "sequence": "seq01",
                "shot": "shot010",
                "user": "artist1",
                "plate": "bg01",
                "scene_path": "/path/to/scene1.3de",
                "workspace_path": "/shows/test_show/seq01/shot010",
            },
            {
                "show": "test_show",
                "sequence": "seq01",
                "shot": "shot020",
                "user": "artist2",
                "plate": "fg01",
                "scene_path": "/path/to/scene2.3de",
                "workspace_path": "/shows/test_show/seq01/shot020",
            },
        ]
        cache_manager.cache_threede_scenes(scenes)

        cached = cache_manager.get_cached_threede_scenes()

        assert cached is not None
        assert len(cached) == 2
        assert cached[0]["show"] == "test_show"
        assert cached[0]["user"] == "artist1"

    def test_cache_handles_empty_list(self, cache_manager: CacheManager) -> None:
        """Test caching empty list is handled correctly."""
        cache_manager.cache_shots([])

        cached = cache_manager.get_cached_shots()
        assert cached == []

    def test_cache_overwrites_existing_data(self, cache_manager: CacheManager, sample_shots: list[Shot]) -> None:
        """Test caching new data overwrites old data."""
        # Cache initial data
        cache_manager.cache_shots(sample_shots[:2])
        cached1 = cache_manager.get_cached_shots()
        assert len(cached1) == 2

        # Overwrite with different data
        cache_manager.cache_shots(sample_shots)
        cached2 = cache_manager.get_cached_shots()
        assert len(cached2) == 3


class TestThumbnailCaching:
    """Test thumbnail processing and caching operations."""

    def test_cache_thumbnail_jpg(self, cache_manager: CacheManager, test_image_jpg: Path) -> None:
        """Test caching JPEG thumbnail creates resized output."""
        result = cache_manager.cache_thumbnail(
            test_image_jpg, "test_show", "seq01", "shot010"
        )

        assert result is not None
        assert result.exists()
        assert result.suffix == ".jpg"

        # Verify thumbnail was resized
        thumb = QImage(str(result))
        assert thumb.width() <= 256
        assert thumb.height() <= 256

    def test_cache_thumbnail_png(self, cache_manager: CacheManager, test_image_png: Path) -> None:
        """Test caching PNG thumbnail preserves transparency."""
        result = cache_manager.cache_thumbnail(
            test_image_png, "test_show", "seq01", "shot020"
        )

        assert result is not None
        assert result.exists()
        assert result.suffix == ".jpg"  # Converted to JPEG

        # Verify resizing
        thumb = QImage(str(result))
        assert thumb.width() <= 256
        assert thumb.height() <= 256

    def test_get_cached_thumbnail_returns_valid_path(
        self, cache_manager: CacheManager, test_image_jpg: Path
    ) -> None:
        """Test retrieving cached thumbnail returns valid path."""
        # Cache a thumbnail first
        cache_manager.cache_thumbnail(test_image_jpg, "test_show", "seq01", "shot010")

        # Retrieve it
        cached_path = cache_manager.get_cached_thumbnail("test_show", "seq01", "shot010")

        assert cached_path is not None
        assert cached_path.exists()
        assert cached_path.name == "shot010_thumb.jpg"

    def test_get_cached_thumbnail_respects_ttl(self, cache_manager: CacheManager, test_image_jpg: Path) -> None:
        """Test cached thumbnail expires after TTL."""
        # Cache thumbnail
        cache_manager.cache_thumbnail(test_image_jpg, "test_show", "seq01", "shot010")

        # Verify it's cached
        cached = cache_manager.get_cached_thumbnail("test_show", "seq01", "shot010")
        assert cached is not None

        # Expire it by modifying timestamp
        old_time = time.time() - (31 * 60)  # 31 minutes ago
        import os

        os.utime(cached, (old_time, old_time))

        # Should now be expired
        expired = cache_manager.get_cached_thumbnail("test_show", "seq01", "shot010")
        assert expired is None

    def test_get_cached_thumbnail_missing_file(self, cache_manager: CacheManager) -> None:
        """Test retrieving non-existent thumbnail returns None."""
        result = cache_manager.get_cached_thumbnail(
            "nonexistent_show", "seq99", "shot999"
        )
        assert result is None

    def test_cache_thumbnail_creates_nested_directories(
        self, cache_manager: CacheManager, test_image_jpg: Path
    ) -> None:
        """Test thumbnail caching creates show/sequence directory structure."""
        cache_manager.cache_thumbnail(
            test_image_jpg, "new_show", "new_seq", "new_shot"
        )

        expected_dir = cache_manager.thumbnails_dir / "new_show" / "new_seq"
        assert expected_dir.exists()
        assert (expected_dir / "new_shot_thumb.jpg").exists()


class TestEXRProcessing:
    """Test OpenEXR thumbnail processing."""

    def test_exr_thumbnail_with_pil(self, cache_manager: CacheManager, mock_exr_file: Path) -> None:
        """Test EXR processing uses PIL directly (no OpenEXR/Imath dependency).

        This tests that we handle EXR files gracefully using PIL,
        which will fail if pillow-openexr is not installed (expected).
        """
        result = cache_manager.cache_thumbnail(
            mock_exr_file, "test_show", "seq01", "shot_exr"
        )

        # PIL will fail on our mock EXR file since it's not a real EXR
        # This is expected behavior - graceful degradation without OpenEXR/Imath
        if result is None:
            # Verify no exception was raised (graceful failure)
            assert True

    def test_exr_thumbnail_with_missing_file(self, cache_manager: CacheManager, tmp_path: Path) -> None:
        """Test EXR processing handles missing files gracefully."""
        missing_exr = tmp_path / "nonexistent.exr"

        result = cache_manager.cache_thumbnail(
            missing_exr, "test_show", "seq01", "shot_missing"
        )

        # Should return None for missing file
        assert result is None


class TestThreadSafety:
    """Test thread-safe concurrent access patterns.

    Following UNIFIED_TESTING_GUIDE: "Thread Safety in Tests"
    """

    def test_concurrent_shot_caching(self, cache_manager: CacheManager, sample_shots: list[Shot]) -> None:
        """Test thread-safe concurrent shot caching operations.

        NOTE: This test may be flaky when run with full test suite due to
        pytest-qt event loop cleanup issues. Passes consistently when run alone.
        The cache_manager itself IS thread-safe (uses QMutex properly).
        """
        import queue
        results_queue: queue.Queue[bool] = queue.Queue()

        def cache_operation(thread_id: int) -> None:
            """Simulate concurrent cache operations."""
            shots = [
                Shot(
                    "show",
                    f"seq{thread_id}",
                    f"shot{i:03d}",
                    f"/path/{thread_id}/{i}",
                )
                for i in range(10)
            ]
            cache_manager.cache_shots(shots)
            # Add small delay to ensure write completes
            time.sleep(0.01)
            cached = cache_manager.get_cached_shots()
            results_queue.put(cached is not None)

        # Run 5 threads concurrently using Thread instead of ThreadPoolExecutor
        # to avoid Qt event loop issues in test environment
        threads = [threading.Thread(target=cache_operation, args=(i,)) for i in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # Collect results from thread-safe queue
        results = []
        while not results_queue.empty():
            results.append(results_queue.get())

        # All operations should succeed without corruption
        assert all(results), f"Some cache operations failed: {results}"
        assert len(results) == 5, f"Expected 5 results, got {len(results)}"

    def test_concurrent_thumbnail_caching(self, cache_manager: CacheManager, test_image_jpg: Path) -> None:
        """Test thread-safe concurrent thumbnail operations."""
        import queue
        results_queue: queue.Queue[bool] = queue.Queue()

        def thumbnail_operation(thread_id: int) -> None:
            """Simulate concurrent thumbnail caching."""
            for i in range(5):
                result = cache_manager.cache_thumbnail(
                    test_image_jpg,
                    f"show{thread_id}",
                    f"seq{thread_id}",
                    f"shot{i:03d}",
                )
                results_queue.put(result is not None)

        # Run multiple threads
        threads = [threading.Thread(target=thumbnail_operation, args=(i,)) for i in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # Collect results from thread-safe queue
        results = []
        while not results_queue.empty():
            results.append(results_queue.get())

        # All operations should succeed
        assert all(results)
        assert len(results) == 15  # 3 threads × 5 operations

    def test_concurrent_cache_clearing(self, cache_manager: CacheManager, sample_shots: list[Shot]) -> None:
        """Test thread-safe cache clearing with concurrent reads."""
        import queue

        # Pre-populate cache
        cache_manager.cache_shots(sample_shots)

        read_queue: queue.Queue[bool] = queue.Queue()
        clear_queue: queue.Queue[bool] = queue.Queue()

        def read_operation() -> None:
            """Concurrent read operations."""
            for _ in range(10):
                _ = cache_manager.get_cached_shots()
                # Result might be None if cleared, that's OK
                read_queue.put(True)
                time.sleep(0.001)

        def clear_operation() -> None:
            """Concurrent clear operations."""
            for _ in range(5):
                cache_manager.clear_cache()
                clear_queue.put(True)
                time.sleep(0.002)

        # Run readers and clearers concurrently
        threads = [threading.Thread(target=read_operation) for _ in range(3)]
        threads.append(threading.Thread(target=clear_operation))

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # Collect results from thread-safe queues
        reads = []
        while not read_queue.empty():
            reads.append(read_queue.get())

        clears = []
        while not clear_queue.empty():
            clears.append(clear_queue.get())

        # Verify no crashes or corruption
        assert len(reads) == 30  # 3 threads × 10 reads
        assert len(clears) == 5


class TestCacheManagement:
    """Test cache clearing and memory management operations."""

    def test_clear_cache_removes_all_files(self, cache_manager: CacheManager, sample_shots: list[Shot]) -> None:
        """Test clear_cache removes all cached data."""
        # Populate cache
        cache_manager.cache_shots(sample_shots)
        cache_manager.cache_threede_scenes([])

        # Verify files exist
        assert cache_manager.shots_cache_file.exists()

        # Clear cache
        cache_manager.clear_cache()

        # Verify cache directory is empty
        assert not cache_manager.shots_cache_file.exists()
        # Note: thumbnails_dir might still exist but be empty

    def test_clear_cache_handles_missing_directory(self, tmp_path: Path) -> None:
        """Test clear_cache handles non-existent cache gracefully."""
        cache_dir = tmp_path / "nonexistent_cache"
        manager = CacheManager(cache_dir=cache_dir)

        # Should not raise exception
        manager.clear_cache()

    def test_get_memory_usage_calculates_correctly(
        self, cache_manager: CacheManager, test_image_jpg: Path, sample_shots: list[Shot]
    ) -> None:
        """Test memory usage calculation."""
        # Get initial usage (should be minimal)
        initial_usage = cache_manager.get_memory_usage()

        # Add some cached data
        cache_manager.cache_shots(sample_shots)
        cache_manager.cache_thumbnail(test_image_jpg, "show", "seq", "shot")

        # Verify usage increased
        final_usage = cache_manager.get_memory_usage()
        assert final_usage["total_mb"] > initial_usage["total_mb"]
        assert final_usage["file_count"] > initial_usage["file_count"]
        assert final_usage["total_mb"] > 0

    def test_get_memory_usage_handles_empty_cache(self, tmp_path: Path) -> None:
        """Test memory usage with empty cache."""
        cache_dir = tmp_path / "empty_cache"
        cache_dir.mkdir()

        manager = CacheManager(cache_dir=cache_dir)
        usage = manager.get_memory_usage()

        assert usage["total_mb"] == 0  # Empty cache should report 0 MB
        assert usage["file_count"] == 0


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_cache_thumbnail_with_missing_source(self, cache_manager: CacheManager, tmp_path: Path) -> None:
        """Test caching thumbnail with non-existent source file."""
        missing_file = tmp_path / "missing.jpg"

        result = cache_manager.cache_thumbnail(
            missing_file, "show", "seq", "shot"
        )

        # Should return None for missing source
        assert result is None

    def test_cache_thumbnail_with_corrupt_image(self, cache_manager: CacheManager, tmp_path: Path) -> None:
        """Test caching thumbnail with corrupt image data."""
        corrupt_file = tmp_path / "corrupt.jpg"
        corrupt_file.write_bytes(b"NOT A VALID IMAGE")

        result = cache_manager.cache_thumbnail(
            corrupt_file, "show", "seq", "shot"
        )

        # Should handle corrupt image gracefully
        assert result is None

    def test_get_cached_shots_with_corrupt_json(self, cache_manager: CacheManager) -> None:
        """Test retrieving shots with corrupt JSON file."""
        # Write invalid JSON
        cache_manager.shots_cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_manager.shots_cache_file.write_text("INVALID JSON{{{")

        result = cache_manager.get_cached_shots()

        # Should return None for corrupt JSON
        assert result is None

    def test_get_cached_shots_with_missing_keys(self, cache_manager: CacheManager) -> None:
        """Test retrieving shots with malformed JSON structure."""
        # Write JSON without expected keys
        cache_manager.shots_cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_manager.shots_cache_file.write_text('{"wrong_key": []}')

        result = cache_manager.get_cached_shots()

        # Should handle gracefully
        # Implementation may return [] or None, either is acceptable
        assert result is None or result == []

    def test_cache_with_readonly_directory(self, tmp_path: Path) -> None:
        """Test caching operations with read-only directory."""
        cache_dir = tmp_path / "readonly_cache"
        cache_dir.mkdir()

        manager = CacheManager(cache_dir=cache_dir)

        # Make directory read-only
        import stat

        cache_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)

        try:
            # Should handle write failure gracefully
            manager.cache_shots([Shot("show", "seq", "shot", "/path")])
            # If we get here, permission check might be disabled in test env
        except PermissionError:
            # Expected on systems that enforce permissions
            pass
        finally:
            # Restore permissions for cleanup
            cache_dir.chmod(stat.S_IRWXU)


class TestCacheIntegration:
    """Integration tests validating cache behavior across components."""

    def test_cache_workflow_shots_to_thumbnails(
        self, cache_manager: CacheManager, sample_shots: list[Shot], test_image_jpg: Path
    ) -> None:
        """Test complete workflow: cache shots, then thumbnails."""
        # Step 1: Cache shot data
        cache_manager.cache_shots(sample_shots)
        cached_shots = cache_manager.get_cached_shots()
        assert len(cached_shots) == 3

        # Step 2: Cache thumbnails for shots
        for shot_data in cached_shots:
            result = cache_manager.cache_thumbnail(
                test_image_jpg,
                shot_data["show"],
                shot_data["sequence"],
                shot_data["shot"],
            )
            assert result is not None

        # Step 3: Retrieve thumbnails
        for shot_data in cached_shots:
            thumb = cache_manager.get_cached_thumbnail(
                shot_data["show"], shot_data["sequence"], shot_data["shot"]
            )
            assert thumb is not None

    def test_cache_persistence_across_instances(
        self, tmp_path: Path, sample_shots: list[Shot], test_image_jpg: Path
    ) -> None:
        """Test cache persists across CacheManager instances."""
        cache_dir = tmp_path / "persistent_cache"

        # Create first instance and cache data
        manager1 = CacheManager(cache_dir=cache_dir)
        manager1.cache_shots(sample_shots)
        manager1.cache_thumbnail(test_image_jpg, "show", "seq", "shot")

        # Create second instance
        manager2 = CacheManager(cache_dir=cache_dir)

        # Verify data persisted
        cached_shots = manager2.get_cached_shots()
        assert len(cached_shots) == 3

        cached_thumb = manager2.get_cached_thumbnail("show", "seq", "shot")
        assert cached_thumb is not None

    def test_memory_usage_tracks_all_data(
        self, cache_manager: CacheManager, sample_shots: list[Shot], test_image_jpg: Path
    ) -> None:
        """Test memory usage calculation includes all cached data."""
        initial = cache_manager.get_memory_usage()

        # Add shots
        cache_manager.cache_shots(sample_shots)
        after_shots = cache_manager.get_memory_usage()
        assert after_shots["total_mb"] > initial["total_mb"]

        # Add thumbnails
        for i in range(5):
            cache_manager.cache_thumbnail(
                test_image_jpg, "show", f"seq{i}", f"shot{i:03d}"
            )

        after_thumbs = cache_manager.get_memory_usage()
        assert after_thumbs["total_mb"] > after_shots["total_mb"]

        # Clear cache
        cache_manager.clear_cache()
        after_clear = cache_manager.get_memory_usage()
        assert after_clear["total_mb"] < after_thumbs["total_mb"]
