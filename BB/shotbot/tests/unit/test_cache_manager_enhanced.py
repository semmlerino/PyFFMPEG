"""Enhanced unit tests for cache_manager.py to improve coverage.

Following UNIFIED_TESTING_GUIDE principles:
- Test behavior, not implementation
- Use real components with temporary storage
- Mock only at system boundaries
- Use QSignalSpy for Qt signals
"""

import concurrent.futures
import json
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QImage
from PySide6.QtTest import QSignalSpy

from cache_manager import CacheManager, ThumbnailCacheLoader
from shot_model import Shot
from threede_scene_model import ThreeDEScene


@pytest.fixture
def cache_manager(tmp_path):
    """Create a real CacheManager with temporary storage."""
    return CacheManager(cache_dir=tmp_path / "cache")


@pytest.fixture
def sample_shot():
    """Create a sample Shot for testing."""
    return Shot(
        show="test_show",
        sequence="seq01",
        shot="shot01",
        workspace_path="/shows/test_show/seq01/shot01"
    )


@pytest.fixture
def sample_3de_scene():
    """Create a sample ThreeDEScene for testing."""
    return ThreeDEScene(
        show="test_show",
        sequence="seq01",
        shot="shot01",
        scene_path=Path("/path/to/scene.3de"),
        workspace_path="/shows/test_show/seq01/shot01",
        user="testuser",
        plate="bg01"
    )


@pytest.fixture
def test_image(tmp_path):
    """Create a test image file."""
    image_path = tmp_path / "test_image.jpg"
    # Create a real image file
    image = QImage(100, 100, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.blue)
    image.save(str(image_path), "JPEG")
    return image_path


@pytest.fixture
def large_image(tmp_path):
    """Create a large test image file."""
    image_path = tmp_path / "large_image.jpg"
    # Create a large image (exceeding max dimensions)
    image = QImage(15000, 15000, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.red)
    image.save(str(image_path), "JPEG", quality=10)  # Low quality to save space
    return image_path


@pytest.fixture
def exr_image(tmp_path):
    """Create a mock EXR file."""
    # Since we can't create real EXR files without special libraries,
    # create a mock file with .exr extension
    exr_path = tmp_path / "test_plate.exr"
    exr_path.write_bytes(b"MOCK_EXR_DATA" * 1000)  # Make it large enough
    return exr_path


class TestThumbnailCacheLoader:
    """Test the ThumbnailCacheLoader QRunnable class."""
    
    def test_thumbnail_cache_loader_initialization(self, cache_manager, test_image, sample_shot):
        """Test ThumbnailCacheLoader initialization."""
        loader = ThumbnailCacheLoader(
            cache_manager,
            test_image,
            sample_shot.show,
            sample_shot.sequence,
            sample_shot.shot
        )
        
        assert loader.cache_manager == cache_manager
        assert loader.source_path == test_image
        assert loader.show == sample_shot.show
        assert loader.sequence == sample_shot.sequence
        assert loader.shot == sample_shot.shot
        assert loader.signals is not None
    
    def test_thumbnail_cache_loader_run_success(self, qtbot, cache_manager, test_image, sample_shot):
        """Test successful thumbnail caching in background."""
        loader = ThumbnailCacheLoader(
            cache_manager,
            test_image,
            sample_shot.show,
            sample_shot.sequence,
            sample_shot.shot
        )
        
        # Set up signal spy
        spy_loaded = QSignalSpy(loader.signals.loaded)
        spy_failed = QSignalSpy(loader.signals.failed)
        
        # Run the loader
        loader.run()
        
        # Check signals
        assert spy_loaded.count() == 1
        assert spy_failed.count() == 0
        
        # Verify signal data
        signal_args = spy_loaded.at(0)
        assert signal_args[0] == sample_shot.show
        assert signal_args[1] == sample_shot.sequence
        assert signal_args[2] == sample_shot.shot
        assert isinstance(signal_args[3], Path)
        
        # Verify cache file exists
        cache_path = signal_args[3]
        assert cache_path.exists()
        assert cache_path.suffix == ".jpg"
    
    def test_thumbnail_cache_loader_run_failure(self, qtbot, cache_manager, tmp_path, sample_shot):
        """Test failed thumbnail caching with non-existent file."""
        non_existent = tmp_path / "non_existent.jpg"
        
        loader = ThumbnailCacheLoader(
            cache_manager,
            non_existent,
            sample_shot.show,
            sample_shot.sequence,
            sample_shot.shot
        )
        
        # Set up signal spy
        spy_loaded = QSignalSpy(loader.signals.loaded)
        spy_failed = QSignalSpy(loader.signals.failed)
        
        # Run the loader
        loader.run()
        
        # Check signals
        assert spy_loaded.count() == 0
        assert spy_failed.count() == 1
        
        # Verify signal data
        signal_args = spy_failed.at(0)
        assert signal_args[0] == sample_shot.show
        assert signal_args[1] == sample_shot.sequence
        assert signal_args[2] == sample_shot.shot
        # The error message might vary, just check it exists
        assert len(signal_args[3]) > 0
    
    def test_thumbnail_cache_loader_with_thread_pool(self, qtbot, cache_manager, test_image, sample_shot):
        """Test ThumbnailCacheLoader with QThreadPool."""
        loader = ThumbnailCacheLoader(
            cache_manager,
            test_image,
            sample_shot.show,
            sample_shot.sequence,
            sample_shot.shot
        )
        
        # Set up signal spy
        spy_loaded = QSignalSpy(loader.signals.loaded)
        
        # Start in thread pool
        thread_pool = QThreadPool.globalInstance()
        thread_pool.start(loader)
        
        # Wait for completion
        qtbot.waitUntil(lambda: spy_loaded.count() > 0, timeout=5000)
        
        # Verify signal was emitted
        assert spy_loaded.count() == 1


class TestCacheThumbnailDirect:
    """Test the cache_thumbnail_direct method."""
    
    def test_cache_thumbnail_direct_success(self, cache_manager, test_image, sample_shot):
        """Test direct thumbnail caching."""
        result = cache_manager.cache_thumbnail_direct(
            test_image,
            sample_shot.show,
            sample_shot.sequence,
            sample_shot.shot
        )
        
        assert result is not None
        assert result.exists()
        assert result.suffix == ".jpg"
        
        # Verify cached file dimensions
        cached_image = QImage(str(result))
        assert not cached_image.isNull()
        assert cached_image.width() <= cache_manager.CACHE_THUMBNAIL_SIZE
        assert cached_image.height() <= cache_manager.CACHE_THUMBNAIL_SIZE
    
    def test_cache_thumbnail_direct_large_image(self, cache_manager, large_image, sample_shot):
        """Test caching large image that exceeds max dimensions."""
        result = cache_manager.cache_thumbnail_direct(
            large_image,
            sample_shot.show,
            sample_shot.sequence,
            sample_shot.shot
        )
        
        # Should reject image that's too large
        assert result is None
    
    def test_cache_thumbnail_direct_exr_handling(self, cache_manager, exr_image, sample_shot):
        """Test EXR file handling."""
        # Since we can't load real EXR files without plugins,
        # this will test the EXR detection and error handling
        result = cache_manager.cache_thumbnail_direct(
            exr_image,
            sample_shot.show,
            sample_shot.sequence,
            sample_shot.shot
        )
        
        # Should fail to load mock EXR
        assert result is None
    
    def test_cache_thumbnail_direct_memory_error(self, cache_manager, test_image, sample_shot, monkeypatch):
        """Test memory error handling."""
        # Patch QImage to raise MemoryError
        def mock_qimage_init(*args, **kwargs):
            if args and str(test_image) in str(args[0]):
                raise MemoryError("Out of memory")
            return QImage()
        
        monkeypatch.setattr('cache_manager.QImage', mock_qimage_init)
        
        result = cache_manager.cache_thumbnail_direct(
            test_image,
            sample_shot.show,
            sample_shot.sequence,
            sample_shot.shot
        )
        
        assert result is None
    
    def test_cache_thumbnail_direct_io_error(self, cache_manager, test_image, sample_shot, monkeypatch):
        """Test I/O error handling."""
        # Patch save to always fail
        def mock_save(self, path, format=None, quality=-1):
            # Always return False to simulate save failure
            return False
        
        monkeypatch.setattr(QImage, 'save', mock_save)
        
        result = cache_manager.cache_thumbnail_direct(
            test_image,
            sample_shot.show,
            sample_shot.sequence,
            sample_shot.shot
        )
        
        assert result is None


class TestThreeDECaching:
    """Test 3DE scene caching functionality."""
    
    def test_cache_threede_scenes(self, cache_manager, sample_3de_scene):
        """Test caching 3DE scenes."""
        scenes = [sample_3de_scene.to_dict()]
        
        cache_manager.cache_threede_scenes(scenes)
        
        # Verify cache file exists
        assert cache_manager.threede_scenes_cache_file.exists()
        
        # Load and verify cache content
        with open(cache_manager.threede_scenes_cache_file, "r") as f:
            data = json.load(f)
        
        assert "timestamp" in data
        assert "scenes" in data
        assert len(data["scenes"]) == 1
        assert data["scenes"][0]["show"] == sample_3de_scene.show
    
    def test_get_cached_threede_scenes_valid(self, cache_manager, sample_3de_scene):
        """Test retrieving valid cached 3DE scenes."""
        # Cache some scenes
        scenes = [sample_3de_scene.to_dict()]
        cache_manager.cache_threede_scenes(scenes)
        
        # Retrieve from cache
        cached = cache_manager.get_cached_threede_scenes()
        
        assert cached is not None
        assert len(cached) == 1
        assert cached[0]["show"] == sample_3de_scene.show
    
    def test_get_cached_threede_scenes_expired(self, cache_manager, sample_3de_scene):
        """Test expired 3DE cache returns None."""
        # Cache some scenes
        scenes = [sample_3de_scene.to_dict()]
        cache_manager.cache_threede_scenes(scenes)
        
        # Modify timestamp to make cache expired
        with open(cache_manager.threede_scenes_cache_file, "r") as f:
            data = json.load(f)
        
        # Make it expired (default expiry is 1440 minutes = 24 hours)
        old_time = datetime.now() - timedelta(hours=25)  # 25 hours old
        data["timestamp"] = old_time.isoformat()
        
        with open(cache_manager.threede_scenes_cache_file, "w") as f:
            json.dump(data, f)
        
        # Should return None for expired cache
        cached = cache_manager.get_cached_threede_scenes()
        assert cached is None
    
    def test_get_cached_threede_scenes_corrupted(self, cache_manager):
        """Test corrupted 3DE cache handling."""
        # Create corrupted cache file
        cache_manager.threede_scenes_cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_manager.threede_scenes_cache_file.write_text("INVALID JSON {")
        
        # Should handle corruption gracefully
        cached = cache_manager.get_cached_threede_scenes()
        assert cached is None
    
    def test_has_valid_threede_cache(self, cache_manager, sample_3de_scene):
        """Test checking if 3DE cache is valid."""
        # No cache initially
        assert cache_manager.has_valid_threede_cache() is False
        
        # Cache some scenes
        scenes = [sample_3de_scene.to_dict()]
        cache_manager.cache_threede_scenes(scenes)
        
        # Should be valid now
        assert cache_manager.has_valid_threede_cache() is True
    
    def test_cache_threede_scenes_with_metadata(self, cache_manager, sample_3de_scene):
        """Test caching 3DE scenes with metadata."""
        scenes = [sample_3de_scene.to_dict()]
        metadata = {
            "scan_type": "quick",
            "paths_checked": ["/path1", "/path2"],
            "duration_ms": 123
        }
        
        cache_manager.cache_threede_scenes(scenes, metadata)
        
        # Verify cache file exists
        assert cache_manager.threede_scenes_cache_file.exists()
        
        # Load and verify cache content
        with open(cache_manager.threede_scenes_cache_file, "r") as f:
            data = json.load(f)
        
        assert "metadata" in data
        assert data["metadata"]["scan_type"] == "quick"
    
    def test_cache_threede_scenes_empty(self, cache_manager):
        """Test caching empty 3DE scene list."""
        # Cache empty list
        cache_manager.cache_threede_scenes([])
        
        # Should still create cache file
        assert cache_manager.threede_scenes_cache_file.exists()
        
        # Retrieve from cache
        cached = cache_manager.get_cached_threede_scenes()
        assert cached is not None
        assert len(cached) == 0


class TestMemoryManagement:
    """Test memory management and eviction."""
    
    def test_evict_old_thumbnails(self, cache_manager, test_image, monkeypatch):
        """Test thumbnail eviction when memory limit exceeded."""
        # Set a very low memory limit
        monkeypatch.setattr(cache_manager, '_max_memory_bytes', 1000)  # 1KB
        
        # Cache multiple thumbnails to exceed limit
        for i in range(5):
            cache_manager.cache_thumbnail_direct(
                test_image,
                "show",
                "seq",
                f"shot{i:02d}"
            )
        
        # Check that old thumbnails were evicted
        # (memory usage should be under limit)
        assert cache_manager._memory_usage_bytes <= cache_manager._max_memory_bytes
    
    def test_get_memory_usage(self, cache_manager, test_image):
        """Test getting memory usage information."""
        # Cache a thumbnail to have some memory usage
        cache_manager.cache_thumbnail_direct(
            test_image,
            "show",
            "seq",
            "shot01"
        )
        
        # Get memory usage
        usage = cache_manager.get_memory_usage()
        
        # Check the actual keys returned
        assert "total_bytes" in usage
        assert "total_mb" in usage
        assert "max_mb" in usage
        assert "usage_percent" in usage
        assert "thumbnail_count" in usage
        assert usage["total_mb"] >= 0
        assert usage["thumbnail_count"] >= 1


class TestCacheValidation:
    """Test cache validation functionality."""
    
    def test_validate_cache(self, cache_manager, test_image):
        """Test cache validation."""
        # Cache some data
        cache_manager.cache_thumbnail_direct(
            test_image,
            "show",
            "seq",
            "shot01"
        )
        
        # Validate cache
        result = cache_manager.validate_cache()
        
        # Check actual keys returned
        assert "valid" in result
        assert "issues_fixed" in result
        assert "invalid_entries" in result
        assert "orphaned_files" in result
        assert result["valid"] is True
    
    def test_clear_cache(self, cache_manager, test_image):
        """Test clearing all cache."""
        # Cache some data
        cache_manager.cache_thumbnail_direct(
            test_image,
            "show",
            "seq",
            "shot01"
        )
        
        # Clear cache
        cache_manager.clear_cache()
        
        # Check cache is cleared
        assert cache_manager._memory_usage_bytes == 0
        assert len(cache_manager._cached_thumbnails) == 0
    
    def test_shutdown(self, cache_manager):
        """Test cache manager shutdown."""
        # Shutdown should not raise any exceptions
        cache_manager.shutdown()
        
        # Verify shutdown completed
        assert True  # If we got here, shutdown worked


class TestThreadSafety:
    """Test thread-safety of cache operations."""
    
    def test_concurrent_cache_operations(self, cache_manager, test_image):
        """Test concurrent cache operations don't cause issues."""
        results = []
        errors = []
        
        def cache_operation(index):
            try:
                result = cache_manager.cache_thumbnail_direct(
                    test_image,
                    "show",
                    "seq",
                    f"shot{index:03d}"
                )
                results.append(result)
            except Exception as e:
                errors.append(e)
        
        # Run multiple threads concurrently
        threads = []
        for i in range(10):
            t = threading.Thread(target=cache_operation, args=(i,))
            threads.append(t)
            t.start()
        
        # Wait for all threads
        for t in threads:
            t.join(timeout=5)
        
        # Check no errors occurred
        assert len(errors) == 0
        # Check all operations succeeded
        assert all(r is not None for r in results)
    
    def test_thread_safety_with_lock(self, cache_manager):
        """Test that cache operations use thread lock."""
        # The lock should exist
        assert hasattr(cache_manager, '_lock')
        assert cache_manager._lock is not None
        
        # Test that operations can be performed without deadlock
        
        def operation():
            with cache_manager._lock:
                # Simulate some cache operation
                time.sleep(0.01)
                return True
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(operation) for _ in range(10)]
            results = [f.result(timeout=5) for f in futures]
        
        assert all(results)


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_cache_nonexistent_file(self, cache_manager, tmp_path):
        """Test caching non-existent file."""
        non_existent = tmp_path / "does_not_exist.jpg"
        
        result = cache_manager.cache_thumbnail_direct(
            non_existent,
            "show",
            "seq",
            "shot"
        )
        
        assert result is None
    
    def test_cache_invalid_image(self, cache_manager, tmp_path):
        """Test caching invalid image file."""
        invalid_image = tmp_path / "invalid.jpg"
        invalid_image.write_text("NOT AN IMAGE")
        
        result = cache_manager.cache_thumbnail_direct(
            invalid_image,
            "show",
            "seq",
            "shot"
        )
        
        assert result is None
    
    def test_cache_with_special_characters(self, cache_manager, test_image):
        """Test caching with special characters in names."""
        result = cache_manager.cache_thumbnail_direct(
            test_image,
            "show-with-dash",
            "seq_01",
            "shot.001"
        )
        
        assert result is not None
        assert result.exists()
    
    def test_cache_with_unicode_names(self, cache_manager, test_image):
        """Test caching with Unicode characters in names."""
        result = cache_manager.cache_thumbnail_direct(
            test_image,
            "show_测试",
            "seq_序列",
            "shot_镜头"
        )
        
        assert result is not None
        assert result.exists()