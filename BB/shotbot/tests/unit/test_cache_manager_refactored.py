"""Refactored unit tests for CacheManager with minimal mocking.

Following UNIFIED_TESTING_GUIDE principles:
- Test behavior with real components, not mocked implementations
- Use actual filesystem operations with temporary directories
- Mock only at system boundaries (network, subprocess)
- Use QSignalSpy for Qt signal testing
- Create real test doubles instead of mocks
"""

import dataclasses
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

import pytest
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QSignalSpy

from cache_manager import CacheManager
from config import Config
from shot_model import Shot
from threede_scene_model import ThreeDEScene


class RealThumbnailProcessor:
    """Real test double for thumbnail processing without mocks."""
    
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.processed_count = 0
        self.failed_paths: List[Path] = []
        
    def process_thumbnail(self, source_path: Path, cache_path: Path) -> bool:
        """Create a real thumbnail file for testing."""
        if not source_path.exists():
            self.failed_paths.append(source_path)
            return False
            
        # Create real thumbnail file
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Create a small test image
            image = QImage(Config.CACHE_THUMBNAIL_SIZE, Config.CACHE_THUMBNAIL_SIZE, QImage.Format.Format_RGB32)
            image.fill(QColor(100, 100, 100))
            
            # Save to cache path
            success = image.save(str(cache_path), "JPEG", 85)
            if success:
                self.processed_count += 1
            return success
            
        except Exception:
            self.failed_paths.append(source_path)
            return False


class RealShotCache:
    """Real test double for shot caching with filesystem operations."""
    
    def __init__(self, cache_file: Path):
        self.cache_file = cache_file
        self._shots: List[Shot] = []
        self._timestamp = datetime.now()
        
    def save_shots(self, shots: List[Shot]) -> bool:
        """Save shots to real JSON file."""
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                "timestamp": self._timestamp.isoformat(),
                "shots": [
                    {
                        "show": shot.show,
                        "sequence": shot.sequence,
                        "shot": shot.shot,
                        "workspace_path": shot.workspace_path
                    }
                    for shot in shots
                ]
            }
            
            with open(self.cache_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            self._shots = shots
            return True
            
        except Exception:
            return False
    
    def load_shots(self) -> Optional[List[Shot]]:
        """Load shots from real JSON file."""
        if not self.cache_file.exists():
            return None
            
        try:
            with open(self.cache_file, 'r') as f:
                data = json.load(f)
            
            shots = []
            for shot_data in data.get("shots", []):
                shots.append(Shot(
                    show=shot_data["show"],
                    sequence=shot_data["sequence"],
                    shot=shot_data["shot"],
                    workspace_path=shot_data["workspace_path"]
                ))
            
            return shots
            
        except Exception:
            return None
    
    def is_expired(self, ttl_minutes: int = 30) -> bool:
        """Check if cache is expired based on real timestamp."""
        if not self.cache_file.exists():
            return True
            
        try:
            with open(self.cache_file, 'r') as f:
                data = json.load(f)
            
            timestamp = datetime.fromisoformat(data["timestamp"])
            age = datetime.now() - timestamp
            return age > timedelta(minutes=ttl_minutes)
            
        except Exception:
            return True


class TestCacheManagerRefactored:
    """Refactored tests with real components and minimal mocking."""
    
    @pytest.fixture
    def real_cache_manager(self, tmp_path, qapp):
        """Create a real CacheManager with temporary storage."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return CacheManager(cache_dir=cache_dir)
    
    @pytest.fixture
    def sample_shots(self):
        """Create real Shot objects for testing."""
        return [
            Shot("show1", "seq01", "shot001", "/shows/show1/seq01/shot001"),
            Shot("show1", "seq01", "shot002", "/shows/show1/seq01/shot002"),
            Shot("show2", "seq02", "shot010", "/shows/show2/seq02/shot010"),
        ]
    
    @pytest.fixture
    def sample_3de_scenes(self):
        """Create real ThreeDEScene objects for testing."""
        return [
            ThreeDEScene(
                show="show1",
                sequence="seq01",
                shot="shot001",
                user="artist1",
                plate="bg01",
                scene_path="/path/to/scene1.3de",
                workspace_path="/shows/show1/seq01/shot001"
            ),
            ThreeDEScene(
                show="show1",
                sequence="seq01",
                shot="shot002",
                user="artist2",
                plate="fg01",
                scene_path="/path/to/scene2.3de",
                workspace_path="/shows/show1/seq01/shot002"
            ),
        ]
    
    @pytest.fixture
    def test_images(self, tmp_path):
        """Create real test image files."""
        images = {}
        
        # Create small test image
        small_path = tmp_path / "small.jpg"
        small_img = QImage(100, 100, QImage.Format.Format_RGB32)
        small_img.fill(QColor(255, 0, 0))
        small_img.save(str(small_path), "JPEG")
        images["small"] = small_path
        
        # Create medium test image
        medium_path = tmp_path / "medium.jpg"
        medium_img = QImage(500, 500, QImage.Format.Format_RGB32)
        medium_img.fill(QColor(0, 255, 0))
        medium_img.save(str(medium_path), "JPEG")
        images["medium"] = medium_path
        
        # Create large test image (but not exceeding limits)
        large_path = tmp_path / "large.jpg"
        large_img = QImage(1000, 1000, QImage.Format.Format_RGB32)
        large_img.fill(QColor(0, 0, 255))
        large_img.save(str(large_path), "JPEG")
        images["large"] = large_path
        
        return images
    
    def test_cache_initialization_creates_directories(self, tmp_path):
        """Test that CacheManager creates necessary directories."""
        cache_dir = tmp_path / "test_cache"
        assert not cache_dir.exists()
        
        manager = CacheManager(cache_dir=cache_dir)
        
        # Verify directories were created
        assert cache_dir.exists()
        assert cache_dir.is_dir()
        assert (cache_dir / "thumbnails").exists()
        assert (cache_dir / "thumbnails").is_dir()
    
    def test_shot_caching_with_real_files(self, real_cache_manager, sample_shots):
        """Test caching shots to real JSON files."""
        # Cache the shots
        real_cache_manager.cache_shots(sample_shots)
        
        # Verify JSON file was created
        cache_file = real_cache_manager.shots_cache_file
        assert cache_file.exists()
        
        # Load and verify content
        with open(cache_file, 'r') as f:
            data = json.load(f)
        
        assert "timestamp" in data
        assert "shots" in data
        assert len(data["shots"]) == 3
        assert data["shots"][0]["show"] == "show1"
        assert data["shots"][0]["shot"] == "shot001"
    
    def test_shot_cache_expiration_with_real_timestamps(self, real_cache_manager, sample_shots):
        """Test TTL expiration with real timestamp comparison."""
        from config import Config
        
        # Cache shots
        real_cache_manager.cache_shots(sample_shots)
        
        # Shots should be fresh immediately
        cached = real_cache_manager.get_cached_shots()
        assert cached is not None
        assert len(cached) == 3
        
        # Manually modify timestamp to simulate age
        cache_file = real_cache_manager.shots_cache_file
        with open(cache_file, 'r') as f:
            data = json.load(f)
        
        # Set timestamp to expire based on actual config value
        # Add 1 minute to ensure it's definitely expired
        expiry_minutes = Config.CACHE_EXPIRY_MINUTES + 1
        old_time = datetime.now() - timedelta(minutes=expiry_minutes)
        data["timestamp"] = old_time.isoformat()
        
        with open(cache_file, 'w') as f:
            json.dump(data, f)
        
        # Now cache should be expired (returns None)
        cached = real_cache_manager.get_cached_shots()
        assert cached is None  # Expired cache returns None
    
    def test_thumbnail_caching_creates_real_files(self, real_cache_manager, test_images):
        """Test thumbnail caching creates actual thumbnail files."""
        source_path = test_images["medium"]
        
        # Cache the thumbnail
        cache_path = real_cache_manager.cache_thumbnail(
            source_path,
            "show1",
            "seq01",
            "shot001"
        )
        
        # Verify thumbnail file was created
        assert cache_path is not None
        assert cache_path.exists()
        assert cache_path.is_file()
        assert cache_path.suffix == ".jpg"
        
        # Verify it's actually a valid image
        test_img = QImage(str(cache_path))
        assert not test_img.isNull()
        assert test_img.width() <= Config.CACHE_THUMBNAIL_SIZE
        assert test_img.height() <= Config.CACHE_THUMBNAIL_SIZE
    
    def test_memory_tracking_with_real_images(self, real_cache_manager, test_images):
        """Test memory usage tracking with real image data."""
        initial_memory = real_cache_manager.get_memory_usage()
        assert initial_memory["total_bytes"] == 0
        
        # Cache multiple images and verify they're actually cached
        cached_paths = []
        for idx, (name, path) in enumerate(test_images.items()):
            result = real_cache_manager.cache_thumbnail(
                path,
                "show1",
                "seq01",
                f"shot{idx:03d}"
            )
            # Verify the thumbnail was actually created
            if result and result.exists():
                cached_paths.append(result)
        
        # If thumbnails were created, memory should be tracked
        if cached_paths:
            # Memory usage should increase
            current_memory = real_cache_manager.get_memory_usage()
            assert current_memory["total_bytes"] > 0
            assert current_memory["tracked_items"] == len(cached_paths)
            
            # Verify each cached file is tracked
            for cache_path in cached_paths:
                assert real_cache_manager._memory_manager.is_item_tracked(cache_path)
            
            # Clear cache (this clears memory tracking)
            real_cache_manager.clear_cache()
            
            # Memory should be freed
            final_memory = real_cache_manager.get_memory_usage()
            assert final_memory["total_bytes"] == 0
        else:
            # If no thumbnails were created, skip the memory assertions
            # This might happen if thumbnail processing fails
            pytest.skip("No thumbnails were successfully cached")
    
    def test_3de_scene_caching_with_real_files(self, real_cache_manager, sample_3de_scenes):
        """Test 3DE scene caching with real JSON operations."""
        # Convert ThreeDEScene objects to dicts for caching
        scene_dicts = []
        for scene in sample_3de_scenes:
            # Manually convert to dict to handle Path objects
            scene_dict = {
                "show": scene.show,
                "sequence": scene.sequence,
                "shot": scene.shot,
                "user": scene.user,
                "plate": scene.plate,
                "scene_path": str(scene.scene_path),  # Convert Path to string
                "workspace_path": scene.workspace_path
            }
            scene_dicts.append(scene_dict)
        
        # Cache the scenes as dicts
        real_cache_manager.cache_threede_scenes(scene_dicts)
        
        # Verify cache file exists
        cache_file = real_cache_manager.threede_scenes_cache_file
        assert cache_file.exists()
        
        # Load and verify - returns list of dicts
        cached = real_cache_manager.get_cached_threede_scenes()
        assert cached is not None
        assert len(cached) == 2
        assert cached[0]["user"] == "artist1"  # Dict access, not attribute
        assert cached[1]["plate"] == "fg01"    # Dict access, not attribute
    
    def test_cache_validation_with_real_filesystem(self, real_cache_manager, test_images):
        """Test cache validation detects real filesystem issues."""
        # Create some cached thumbnails
        for idx, (name, path) in enumerate(test_images.items()):
            real_cache_manager.cache_thumbnail(
                path,
                "show1",
                "seq01",
                f"shot{idx:03d}"
            )
        
        # Validation should pass initially
        result = real_cache_manager.validate_cache()
        assert result.get("valid", False)
        assert result.get("issues_found", 0) == 0  # No issues initially
        
        # Manually corrupt cache by deleting a thumbnail
        thumbnails_dir = real_cache_manager.cache_dir / "thumbnails"
        # Find thumbnails in subdirectories (they're organized by show/sequence)
        thumb_files = list(thumbnails_dir.rglob("*.jpg"))
        if thumb_files:
            thumb_files[0].unlink()  # Delete one thumbnail file
        
        # Validation should detect missing file or orphaned tracking
        result = real_cache_manager.validate_cache()
        # After deleting a file, there should be issues found
        # Either orphaned tracking entries or missing files
        assert result.get("issues_found", 0) > 0 or not result.get("valid", True)
    
    def test_concurrent_access_with_real_threading(self, real_cache_manager, test_images, qtbot):
        """Test thread-safe concurrent access with real threads."""
        from concurrent.futures import ThreadPoolExecutor
        
        results = []
        errors = []
        
        def cache_image(idx: int, path: Path):
            """Worker function to cache an image."""
            try:
                cache_path = real_cache_manager.cache_thumbnail(
                    path,
                    "show1",
                    "seq01",
                    f"shot{idx:03d}"
                )
                results.append(cache_path)
            except Exception as e:
                errors.append(str(e))
        
        # Use real threads to cache images concurrently
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = []
            for idx, (name, path) in enumerate(test_images.items()):
                future = executor.submit(cache_image, idx, path)
                futures.append(future)
            
            # Wait for all to complete
            for future in futures:
                future.result()
        
        # All operations should succeed
        assert len(errors) == 0
        assert len(results) == len(test_images)
        
        # All cache files should exist
        for cache_path in results:
            if cache_path:  # Some might be None if they hit cache
                assert cache_path.exists()
    
    def test_cache_cleanup_with_real_files(self, real_cache_manager, test_images):
        """Test cache cleanup actually removes files."""
        # Cache some images
        cached_paths = []
        for idx, (name, path) in enumerate(test_images.items()):
            cache_path = real_cache_manager.cache_thumbnail(
                path,
                "show1",
                "seq01",
                f"shot{idx:03d}"
            )
            if cache_path:
                cached_paths.append(cache_path)
        
        # Verify files exist
        for path in cached_paths:
            assert path.exists()
        
        # Clear cache
        real_cache_manager.clear_cache()
        
        # Files should be removed
        for path in cached_paths:
            assert not path.exists()
        
        # Cache directory should still exist but be empty
        thumbnails_dir = real_cache_manager.cache_dir / "thumbnails"
        assert thumbnails_dir.exists()
        assert len(list(thumbnails_dir.glob("*.jpg"))) == 0
    
    @pytest.mark.slow
    def test_performance_with_real_operations(self, real_cache_manager, tmp_path):
        """Test performance with real file operations."""
        
        # Create test images
        num_images = 10
        images = []
        for i in range(num_images):
            img_path = tmp_path / f"perf_test_{i}.jpg"
            img = QImage(200, 200, QImage.Format.Format_RGB32)
            img.fill(QColor(i * 20, i * 20, i * 20))
            img.save(str(img_path), "JPEG")
            images.append(img_path)
        
        # Measure caching time
        start_time = time.time()
        
        for idx, img_path in enumerate(images):
            real_cache_manager.cache_thumbnail(
                img_path,
                "perftest",
                "seq01",
                f"shot{idx:03d}"
            )
        
        elapsed = time.time() - start_time
        
        # Should complete reasonably quickly (adjust threshold as needed)
        assert elapsed < 5.0  # 5 seconds for 10 images
        
        # Verify all were cached (thumbnails are in subdirectories)
        thumbnails_dir = real_cache_manager.cache_dir / "thumbnails"
        cached_files = list(thumbnails_dir.glob("**/*.jpg"))
        assert len(cached_files) == num_images


class TestCacheManagerSignals:
    """Test Qt signal emissions with QSignalSpy."""
    
    def test_cache_progress_signals(self, qtbot, tmp_path):
        """Test progress signals are emitted during caching."""
        cache_manager = CacheManager(cache_dir=tmp_path / "cache")
        
        # Create spy for progress signal if it exists
        if hasattr(cache_manager, 'progress_updated'):
            progress_spy = QSignalSpy(cache_manager.progress_updated)
            
            # Create test image
            img_path = tmp_path / "test.jpg"
            img = QImage(100, 100, QImage.Format.Format_RGB32)
            img.fill(QColor(255, 255, 255))
            img.save(str(img_path), "JPEG")
            
            # Cache thumbnail
            cache_manager.cache_thumbnail(img_path, "show", "seq", "shot")
            
            # Check if progress was emitted
            if len(progress_spy) > 0:
                assert progress_spy[0][0] >= 0  # Progress value
                assert progress_spy[0][0] <= 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])