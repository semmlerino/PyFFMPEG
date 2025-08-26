"""Integration tests for cache manager modular architecture."""

# This test file follows UNIFIED_TESTING_GUIDE best practices:
# - Test behavior, not implementation
# - Use test doubles instead of mocks
# - Real components where possible
# - Thread-safe testing patterns


from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
import traceback
from pathlib import Path

import pytest

try:
    from PIL import Image
except ImportError:
    Image = None  # type: ignore[assignment]

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from cache_manager import CacheManager

pytestmark = pytest.mark.integration



# Test doubles for behavior testing (UNIFIED_TESTING_GUIDE)
from tests.test_doubles_library import TestSubprocess


class TestCacheIntegration:
    """Integration tests for cache manager modular components following UNIFIED_TESTING_GUIDE."""

    def setup_method(self):
        # Use test double for subprocess (UNIFIED_TESTING_GUIDE)
        self.test_subprocess = TestSubprocess()
        """Minimal setup to avoid pytest fixture overhead."""
        self.temp_dir = Path(tempfile.mkdtemp(prefix="shotbot_cache_integration_"))
        self.cache_dir = self.temp_dir / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir = self.temp_dir / "images"
        self.images_dir.mkdir(parents=True, exist_ok=True)

        # Create test image files
        self.test_images = []
        try:
            if Image is not None:
                for i in range(3):
                    img_path = self.images_dir / f"test_image_{i}.jpg"
                    # Create a small test image
                    img = Image.new("RGB", (100, 100), color=(255, i * 50, 0))
                    img.save(img_path, "JPEG")
                    self.test_images.append(img_path)
            else:
                raise ImportError("PIL not available")
        except ImportError:
            # Fallback if PIL not available - create simple files
            for i in range(3):
                img_path = self.images_dir / f"test_image_{i}.txt"
                img_path.write_text(f"Test image {i}")
                self.test_images.append(img_path)

    def teardown_method(self):
        """Direct cleanup without fixture dependencies."""
        try:
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:
            pass  # Ignore cleanup errors

    def test_cache_manager_thumbnail_workflow_integration(self):
        """Test complete thumbnail caching workflow with modular components."""
        # Import locally to avoid pytest environment issues

        sys.path.insert(0, str(Path(__file__).parent.parent.parent))

        # Create cache manager with real components
        cache_manager = CacheManager(cache_dir=self.cache_dir)

        # Test thumbnail caching
        source_path = str(self.test_images[0])
        cached_path = cache_manager.cache_thumbnail(
            source_path, "test_show", "seq01", "0010", wait=True
        )

        # Verify thumbnail was cached
        assert cached_path is not None
        assert Path(cached_path).exists()

        # Verify cache directory structure
        thumbnail_dir = Path(self.cache_dir) / "thumbnails"
        assert thumbnail_dir.exists()

        # Test thumbnail retrieval
        retrieved_path = cache_manager.get_cached_thumbnail(
            "test_show", "seq01", "0010"
        )
        assert retrieved_path == cached_path

        # Test memory usage tracking
        usage_stats = cache_manager.get_memory_usage()
        assert "total_mb" in usage_stats  # API uses total_mb, not total_size_mb
        assert "thumbnail_count" in usage_stats
        assert usage_stats["thumbnail_count"] > 0

    def test_cache_manager_storage_backend_integration(self):
        """Test storage backend atomic operations integration."""

        sys.path.insert(0, str(Path(__file__).parent.parent.parent))

        cache_manager = CacheManager(cache_dir=self.cache_dir)

        # Test atomic JSON write/read
        test_data = {
            "test_key": "test_value",
            "nested": {"data": [1, 2, 3]},
            "timestamp": 1234567890,
        }

        test_file = self.cache_dir / "test_storage.json"

        # Write data atomically
        cache_manager._storage_backend.write_json(test_file, test_data)

        # Verify file exists
        assert test_file.exists()

        # Read data back
        loaded_data = cache_manager._storage_backend.read_json(test_file)

        # Verify data integrity
        assert loaded_data == test_data
        assert loaded_data["test_key"] == "test_value"
        assert loaded_data["nested"]["data"] == [1, 2, 3]

        # Test atomic update (should not corrupt existing data)
        updated_data = test_data.copy()
        updated_data["new_key"] = "new_value"

        cache_manager._storage_backend.write_json(test_file, updated_data)

        # Verify update worked
        final_data = cache_manager._storage_backend.read_json(test_file)
        assert final_data["new_key"] == "new_value"
        assert final_data["test_key"] == "test_value"  # Original data preserved

    def test_cache_manager_failure_tracking_integration(self):
        """Test failure tracking with exponential backoff integration."""

        sys.path.insert(0, str(Path(__file__).parent.parent.parent))

        cache_manager = CacheManager(cache_dir=self.cache_dir)

        # Test operation key
        operation_key = "test_thumbnail_operation"

        # Initially should allow retry (no failures)
        should_retry, reason = cache_manager._failure_tracker.should_retry(
            operation_key
        )
        assert should_retry is True
        assert "No previous failures" in reason

        # Record multiple failures
        for i in range(3):
            cache_manager._failure_tracker.record_failure(
                operation_key, f"Test failure {i}"
            )

        # Should now be blocked due to exponential backoff
        should_retry, reason = cache_manager._failure_tracker.should_retry(
            operation_key
        )
        assert should_retry is False
        assert "retry in" in reason  # Message includes retry time

        # Get failure status - returns dict of all failures
        all_failures = cache_manager._failure_tracker.get_failure_status()
        assert operation_key in all_failures
        failure_info = all_failures[operation_key]
        assert failure_info["attempts"] == 3
        assert "timestamp" in failure_info  # Last failure timestamp
        assert "next_retry" in failure_info
        assert "error" in failure_info  # Last error message

        # Clear failures
        cache_manager._failure_tracker.clear_failures(operation_key)

        # Should allow retry again
        should_retry, reason = cache_manager._failure_tracker.should_retry(
            operation_key
        )
        assert should_retry is True

    def test_cache_manager_memory_management_integration(self):
        """Test memory management with LRU eviction integration."""

        sys.path.insert(0, str(Path(__file__).parent.parent.parent))

        cache_manager = CacheManager(cache_dir=self.cache_dir)

        # Mock the memory limit to be very small for testing
        original_limit = cache_manager._memory_manager._max_memory_bytes
        cache_manager._memory_manager._max_memory_bytes = (
            1024 * 1024
        )  # 1MB limit in bytes

        try:
            # Create test files and track them
            for i in range(5):
                test_file = self.cache_dir / f"test_{i}.jpg"
                # Create a file with known size (500KB each)
                test_file.write_bytes(b"x" * (500 * 1024))
                # Track the file
                cache_manager._memory_manager.track_item(test_file)

            # Get memory usage stats
            stats = cache_manager._memory_manager.get_usage_stats()

            # Should show memory usage
            assert stats["total_mb"] > 0
            assert stats["tracked_items"] > 0

            # Test LRU eviction (should trigger automatically)
            evicted_count = cache_manager._memory_manager.evict_if_needed()

            # Should have evicted some items
            assert evicted_count > 0

            # Get updated stats
            updated_stats = cache_manager._memory_manager.get_usage_stats()

            # Should have reduced memory usage through eviction
            assert updated_stats["total_mb"] <= 1.0  # Should be under limit

        finally:
            # Restore original limit
            cache_manager._memory_manager._max_memory_bytes = original_limit

    def test_cache_manager_shot_cache_integration(self):
        """Test shot cache TTL validation and storage integration."""

        sys.path.insert(0, str(Path(__file__).parent.parent.parent))

        cache_manager = CacheManager(cache_dir=self.cache_dir)

        # Create test shot data
        test_shots = [
            {
                "show": "test_show",
                "sequence": "seq01",
                "shot": "0010",
                "workspace_path": "/shows/test_show/shots/seq01/seq01_0010",
                "name": "seq01_0010",
            },
            {
                "show": "test_show",
                "sequence": "seq01",
                "shot": "0020",
                "workspace_path": "/shows/test_show/shots/seq01/seq01_0020",
                "name": "seq01_0020",
            },
        ]

        # Store shots in cache using correct method
        success = cache_manager._shot_cache.cache_shots(test_shots)
        assert success is True

        # Verify cache file was created
        cache_file = self.cache_dir / "shots.json"
        assert cache_file.exists()

        # Read cache file directly
        with open(cache_file, "r") as f:
            cache_data = json.load(f)

        assert "shots" in cache_data
        assert "timestamp" in cache_data
        assert len(cache_data["shots"]) == 2

        # Retrieve shots from cache
        cached_shots = cache_manager._shot_cache.get_cached_shots()
        assert len(cached_shots) == 2
        assert cached_shots[0]["show"] == "test_show"

        # Test TTL expiration with mocked datetime
        from datetime import datetime, timedelta
        from unittest.mock import patch
        
        original_ttl = cache_manager._shot_cache._expiry_minutes
        cache_manager._shot_cache._expiry_minutes = 0.001  # Very short TTL (0.06 seconds)

        try:
            # Mock datetime to simulate TTL expiration
            with patch('cache.shot_cache.datetime') as mock_datetime:
                # Set current time to be after TTL expiration
                mock_datetime.now.return_value = datetime.now() + timedelta(seconds=1)
                mock_datetime.fromisoformat = datetime.fromisoformat
                
                # Should return None or empty list due to TTL expiration
                expired_shots = cache_manager._shot_cache.get_cached_shots()
                assert expired_shots is None or len(expired_shots) == 0

        finally:
            # Restore original TTL
            cache_manager._shot_cache._expiry_minutes = original_ttl

    def test_cache_manager_validation_and_repair_integration(self):
        """Test cache validation and repair workflow integration."""

        sys.path.insert(0, str(Path(__file__).parent.parent.parent))

        cache_manager = CacheManager(cache_dir=self.cache_dir)

        # Create some cache files
        thumbnail_dir = self.cache_dir / "thumbnails"
        thumbnail_dir.mkdir(exist_ok=True)

        # Create valid thumbnail file
        valid_thumbnail = thumbnail_dir / "valid_thumbnail.jpg"
        valid_thumbnail.write_bytes(b"JPEG_DATA" * 100)

        # Create orphaned cache file (no corresponding thumbnail)
        orphaned_file = thumbnail_dir / "orphaned_file.txt"
        orphaned_file.write_text("This is an orphaned file")

        # Create invalid JSON cache
        invalid_json = self.cache_dir / "invalid_cache.json"
        invalid_json.write_text("{ invalid json content")

        # Run cache validation
        validation_result = cache_manager.validate_cache()

        # Verify validation results
        assert "valid" in validation_result
        assert "orphaned_files" in validation_result
        assert "missing_files" in validation_result
        assert "invalid_entries" in validation_result

        # Should return validation status
        assert isinstance(validation_result["valid"], bool)
        assert isinstance(validation_result["orphaned_files"], int)
        assert isinstance(validation_result["missing_files"], int)

        # Test issues detection
        assert "issues_found" in validation_result
        assert "issues_fixed" in validation_result
        assert validation_result["issues_found"] >= 0

    def test_cache_manager_concurrent_access_integration(self):
        """Test cache manager handling concurrent access safely."""

        sys.path.insert(0, str(Path(__file__).parent.parent.parent))

        cache_manager = CacheManager(cache_dir=self.cache_dir)

        # Test concurrent thumbnail caching
        results = []
        errors = []

        def cache_thumbnail_worker(worker_id):
            try:
                source_path = str(self.test_images[worker_id % len(self.test_images)])
                cached_path = cache_manager.cache_thumbnail(
                    source_path,
                    f"show_{worker_id}",
                    "seq01",
                    f"{worker_id:04d}",
                    wait=True,
                )
                results.append((worker_id, cached_path))
            except Exception as e:
                errors.append((worker_id, str(e)))

        # Create multiple threads
        threads = []
        for i in range(3):
            thread = threading.Thread(target=cache_thumbnail_worker, args=(i,))
            threads.append(thread)

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join(timeout=5.0)  # 5 second timeout

        # Verify results
        assert len(errors) == 0, f"Concurrent access errors: {errors}"
        assert len(results) == 3

        # Verify all thumbnails were cached
        for worker_id, cached_path in results:
            assert cached_path is not None
            assert Path(cached_path).exists()

    def test_cache_manager_backward_compatibility_integration(self):
        """Test cache manager maintains backward compatibility with existing API."""

        sys.path.insert(0, str(Path(__file__).parent.parent.parent))

        # Create cache manager using old API style
        cache_manager = CacheManager(cache_dir=self.cache_dir)

        # Test all original API methods still work

        # 1. Thumbnail caching
        source_path = str(self.test_images[0])
        cached_path = cache_manager.cache_thumbnail(
            source_path, "compat_show", "seq01", "0010", wait=True
        )
        assert cached_path is not None

        # 2. Thumbnail retrieval
        retrieved_path = cache_manager.get_cached_thumbnail(
            "compat_show", "seq01", "0010"
        )
        assert retrieved_path == cached_path

        # 3. Shot caching
        test_shots = [{"show": "compat_show", "sequence": "seq01", "shot": "0010"}]
        cache_manager.cache_shots(test_shots)
        cached_shots = cache_manager.get_cached_shots()
        assert len(cached_shots) == 1

        # 4. 3DE scene caching
        test_scenes = [{"file_path": "/path/to/scene.3de", "plate_name": "test_plate"}]
        cache_manager.cache_threede_scenes(test_scenes)
        cached_scenes = cache_manager.get_cached_threede_scenes()
        assert len(cached_scenes) == 1

        # 5. Memory usage reporting
        memory_stats = cache_manager.get_memory_usage()
        assert "total_mb" in memory_stats  # API uses total_mb

        # 6. Cache validation
        validation_result = cache_manager.validate_cache()
        assert "valid" in validation_result  # API uses valid, not health_status

        # 7. Cache clearing
        cache_manager.clear_cache()

        # Verify cache was cleared
        after_clear_shots = cache_manager.get_cached_shots()
        assert after_clear_shots is None or len(after_clear_shots) == 0


# Allow running as standalone test
if __name__ == "__main__":
    test = TestCacheIntegration()
    test.setup_method()
    try:
        print("Running cache manager thumbnail workflow integration...")
        test.test_cache_manager_thumbnail_workflow_integration()
        print("✓ Cache manager thumbnail workflow passed")

        print("Running cache manager storage backend integration...")
        test.test_cache_manager_storage_backend_integration()
        print("✓ Cache manager storage backend integration passed")

        print("Running cache manager failure tracking integration...")
        test.test_cache_manager_failure_tracking_integration()
        print("✓ Cache manager failure tracking integration passed")

        print("Running cache manager memory management integration...")
        test.test_cache_manager_memory_management_integration()
        print("✓ Cache manager memory management integration passed")

        print("Running cache manager shot cache integration...")
        test.test_cache_manager_shot_cache_integration()
        print("✓ Cache manager shot cache integration passed")

        print("Running cache manager validation and repair integration...")
        test.test_cache_manager_validation_and_repair_integration()
        print("✓ Cache manager validation and repair integration passed")

        print("Running cache manager concurrent access integration...")
        test.test_cache_manager_concurrent_access_integration()
        print("✓ Cache manager concurrent access integration passed")

        print("Running cache manager backward compatibility integration...")
        test.test_cache_manager_backward_compatibility_integration()
        print("✓ Cache manager backward compatibility integration passed")

        print("All cache integration tests passed!")
    except Exception as e:
        print(f"Test failed: {e}")

        traceback.print_exc()
    finally:
        test.teardown_method()
