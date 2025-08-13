#!/usr/bin/env python3
"""Stress tests for cache manager to identify edge cases and race conditions.

This test suite puts extreme pressure on the cache manager to ensure
it handles concurrent operations, memory limits, and rapid changes correctly.
"""

import multiprocessing
import os
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest
from PySide6.QtGui import QImage

from cache_manager import CacheManager


class TestCacheStress:
    """Stress tests for cache manager under extreme conditions."""

    def create_test_image(self, path: Path, size: int = 100) -> Path:
        """Create a test image of specified size."""
        image = QImage(size, size, QImage.Format.Format_RGB32)
        # Fill with random color based on hash of path
        color = hash(str(path)) & 0xFFFFFF
        image.fill(color)
        image.save(str(path), "JPEG", 95)  # High quality for larger size
        return path

    def test_rapid_cache_deletion_and_recreation(self, tmp_path):
        """Test rapid deletion and recreation of cache directory."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        manager = CacheManager(cache_dir=cache_dir)

        # Create some initial test images
        images = []
        for i in range(10):
            img_path = tmp_path / f"test{i}.jpg"
            self.create_test_image(img_path)
            images.append(img_path)

        # Rapidly delete and recreate cache while caching
        errors = []
        successes = 0

        def stress_operation(iteration):
            try:
                # Every 3rd operation, delete the cache directory
                if iteration % 3 == 0 and manager.thumbnails_dir.exists():
                    shutil.rmtree(manager.thumbnails_dir)
                    # Wait for directory to be deleted before continuing
                    from tests.helpers.synchronization import wait_for_file_operation

                    wait_for_file_operation(
                        manager.thumbnails_dir, "not_exists", timeout_ms=100
                    )

                # Try to cache an image
                img = images[iteration % len(images)]
                result = manager.cache_thumbnail(
                    img, f"show{iteration}", f"seq{iteration}", f"shot{iteration}"
                )

                if result and result.exists():
                    nonlocal successes
                    successes += 1

            except Exception as e:
                errors.append(str(e))

        # Run stress test with multiple threads
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(stress_operation, i) for i in range(100)]
            for future in as_completed(futures):
                future.result()

        # Should handle most operations successfully
        assert len(errors) == 0, f"Errors occurred: {errors[:5]}"  # Show first 5 errors
        assert successes > 50  # At least half should succeed
        # Directory should exist at the end
        assert manager.thumbnails_dir.exists()

    def test_memory_limit_enforcement_under_stress(self, tmp_path):
        """Test memory limit enforcement with rapid concurrent operations."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        manager = CacheManager(cache_dir=cache_dir)

        # Set very small memory limit (10KB)
        manager._max_memory_bytes = 10 * 1024

        # Create larger test images
        images = []
        for i in range(20):
            img_path = tmp_path / f"large{i}.jpg"
            self.create_test_image(img_path, size=200)  # Larger images
            images.append(img_path)

        def cache_worker(index):
            """Worker that continuously caches images."""
            for _ in range(5):  # Each worker caches 5 images
                img = images[index % len(images)]
                manager.cache_thumbnail(
                    img, f"show{index}", f"seq{index}", f"shot{index}_{_}"
                )
                # Small delay between cache operations to avoid overwhelming system
                from tests.helpers.synchronization import simulate_work_without_sleep

                simulate_work_without_sleep(10)

        # Launch multiple workers
        threads = []
        for i in range(10):  # 10 concurrent workers
            t = threading.Thread(target=cache_worker, args=(i,))
            threads.append(t)
            t.start()

        # Wait for all workers
        for t in threads:
            t.join()

        # Verify memory limit was enforced
        memory_usage = manager.get_memory_usage()
        assert (
            memory_usage["total_bytes"] <= manager._max_memory_bytes * 1.1
        )  # 10% tolerance

        # Verify some thumbnails were evicted
        actual_files = list(manager.thumbnails_dir.rglob("*.jpg"))
        assert len(actual_files) < 50  # Should have evicted many

    def test_concurrent_validation_and_modification(self, tmp_path):
        """Test cache validation while cache is being modified."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        manager = CacheManager(cache_dir=cache_dir)

        # Create test images
        images = []
        for i in range(10):
            img_path = tmp_path / f"test{i}.jpg"
            self.create_test_image(img_path)
            images.append(img_path)

        validation_results = []
        cache_results = []
        errors = []

        def validator():
            """Continuously validate cache."""
            for _ in range(20):
                try:
                    result = manager.validate_cache()
                    validation_results.append(result)
                    # Brief pause between validation cycles
                    from tests.helpers.synchronization import (
                        simulate_work_without_sleep,
                    )

                    simulate_work_without_sleep(50)
                except Exception as e:
                    errors.append(f"Validation error: {e}")

        def modifier():
            """Continuously modify cache."""
            for i in range(30):
                try:
                    # Cache new thumbnails
                    img = images[i % len(images)]
                    result = manager.cache_thumbnail(
                        img, f"show{i}", f"seq{i}", f"shot{i}"
                    )
                    cache_results.append(result)

                    # Sometimes clear cache
                    if i % 10 == 0:
                        manager.clear_cache()

                    # Brief pause between modifications
                    from tests.helpers.synchronization import (
                        simulate_work_without_sleep,
                    )

                    simulate_work_without_sleep(30)
                except Exception as e:
                    errors.append(f"Modification error: {e}")

        # Run validation and modification concurrently
        validator_thread = threading.Thread(target=validator)
        modifier_thread = threading.Thread(target=modifier)

        validator_thread.start()
        modifier_thread.start()

        validator_thread.join()
        modifier_thread.join()

        # Should complete without errors
        assert len(errors) == 0, f"Errors occurred: {errors[:5]}"
        # Should have successful validations
        assert len(validation_results) > 0
        # Should have successful cache operations
        successful_caches = [r for r in cache_results if r is not None]
        assert len(successful_caches) > 0

    def test_memory_tracking_accuracy(self, tmp_path):
        """Test that memory tracking remains accurate under stress."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        manager = CacheManager(cache_dir=cache_dir)

        # Create various sized images
        images = []
        for i in range(10):
            img_path = tmp_path / f"size{i}.jpg"
            # Create images of different sizes
            size = 50 + i * 20  # 50, 70, 90, ... pixels
            self.create_test_image(img_path, size=size)
            images.append(img_path)

        # Cache all images
        for i, img in enumerate(images):
            manager.cache_thumbnail(img, "show1", f"seq{i}", f"shot{i}")

        # Get reported memory usage
        reported_usage = manager.get_memory_usage()["total_bytes"]

        # Calculate actual disk usage
        actual_usage = 0
        for path in manager.thumbnails_dir.rglob("*.jpg"):
            if path.exists():
                actual_usage += path.stat().st_size

        # Memory tracking should be accurate (within 5% tolerance)
        if actual_usage > 0:
            accuracy = abs(reported_usage - actual_usage) / actual_usage
            assert accuracy < 0.05, (
                f"Memory tracking inaccurate: reported={reported_usage}, actual={actual_usage}"
            )

    def test_cache_with_corrupted_files(self, tmp_path):
        """Test cache behavior when files become corrupted during operation."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        manager = CacheManager(cache_dir=cache_dir)

        # Create and cache some images
        for i in range(5):
            img_path = tmp_path / f"test{i}.jpg"
            self.create_test_image(img_path)
            manager.cache_thumbnail(img_path, "show1", f"seq{i}", f"shot{i}")

        # Corrupt some cached files
        for thumb_file in list(manager.thumbnails_dir.rglob("*.jpg"))[:2]:
            thumb_file.write_text("CORRUPTED DATA")

        # Validation should detect and fix issues
        result = manager.validate_cache()
        assert result["issues_fixed"] > 0

        # Should still be able to cache new images
        new_img = tmp_path / "new.jpg"
        self.create_test_image(new_img)
        cache_result = manager.cache_thumbnail(new_img, "show2", "seq1", "shot1")
        assert cache_result is not None
        assert cache_result.exists()

    def test_cache_manager_shutdown_during_operations(self, tmp_path):
        """Test shutdown while operations are in progress."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        manager = CacheManager(cache_dir=cache_dir)

        # Create test images
        images = []
        for i in range(10):
            img_path = tmp_path / f"test{i}.jpg"
            self.create_test_image(img_path)
            images.append(img_path)

        shutdown_called = threading.Event()
        operations_complete = threading.Event()

        def continuous_operations():
            """Continuously perform cache operations."""
            for i in range(50):
                if shutdown_called.is_set():
                    break
                try:
                    img = images[i % len(images)]
                    manager.cache_thumbnail(img, f"show{i}", f"seq{i}", f"shot{i}")
                    # Small pause between operations
                    from tests.helpers.synchronization import (
                        simulate_work_without_sleep,
                    )

                    simulate_work_without_sleep(10)
                except Exception:
                    pass  # Ignore errors during shutdown
            operations_complete.set()

        # Start continuous operations
        op_thread = threading.Thread(target=continuous_operations)
        op_thread.start()

        # Let it run briefly using thread wait
        from tests.helpers.synchronization import wait_for_threads_to_start

        with wait_for_threads_to_start(max_wait_ms=100):
            pass  # Thread already started, just wait for it to be active

        # Call shutdown while operations are running
        shutdown_called.set()
        manager.shutdown()

        # Wait for operations to complete
        operations_complete.wait(timeout=2)

        # Thread should have stopped
        op_thread.join(timeout=1)
        assert not op_thread.is_alive()

        # Memory should be cleared
        assert manager._memory_usage_bytes == 0
        assert len(manager._cached_thumbnails) == 0

    def test_extreme_concurrency(self, tmp_path):
        """Test with extreme number of concurrent operations."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        manager = CacheManager(cache_dir=cache_dir)

        # Create a single test image
        test_img = tmp_path / "test.jpg"
        self.create_test_image(test_img)

        errors = []
        successes = []

        def extreme_operation(index):
            """Single operation for extreme concurrency test."""
            try:
                operation = index % 4
                if operation == 0:
                    # Cache thumbnail
                    result = manager.cache_thumbnail(
                        test_img, f"show{index}", f"seq{index}", f"shot{index}"
                    )
                    if result:
                        successes.append("cache")
                elif operation == 1:
                    # Get cached thumbnail
                    result = manager.get_cached_thumbnail(
                        f"show{index - 1}", f"seq{index - 1}", f"shot{index - 1}"
                    )
                    if result:
                        successes.append("get")
                elif operation == 2:
                    # Validate cache
                    result = manager.validate_cache()
                    if result:
                        successes.append("validate")
                else:
                    # Get memory usage
                    result = manager.get_memory_usage()
                    if result:
                        successes.append("memory")
            except Exception as e:
                errors.append(str(e))

        # Launch extreme number of concurrent operations
        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(extreme_operation, i) for i in range(500)]
            for future in as_completed(futures):
                future.result()

        # Should handle without crashes
        assert len(errors) < 50, f"Too many errors: {len(errors)}"
        assert len(successes) > 400, f"Too few successes: {len(successes)}"

    @pytest.mark.skipif(
        os.cpu_count() < 4, reason="Multi-process test requires at least 4 CPU cores"
    )
    def test_multi_process_cache_access(self, tmp_path):
        """Test multiple processes accessing the same cache."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()

        def worker_process(process_id: int, cache_path: Path):
            """Worker process that accesses cache."""
            # Each process creates its own cache manager
            manager = CacheManager(cache_dir=cache_path)

            # Create and cache an image
            img_path = cache_path.parent / f"process_{process_id}.jpg"
            image = QImage(100, 100, QImage.Format.Format_RGB32)
            image.fill(0xFF0000 + process_id * 100)
            image.save(str(img_path), "JPEG")

            # Cache the image
            result = manager.cache_thumbnail(
                img_path, f"proc{process_id}", "seq1", "shot1"
            )

            return result is not None

        # Launch multiple processes
        with multiprocessing.Pool(processes=4) as pool:
            results = []
            for i in range(4):
                result = pool.apply_async(worker_process, (i, cache_dir))
                results.append(result)

            # Get results
            successes = [r.get(timeout=5) for r in results]

        # All processes should succeed
        assert all(successes), "Some processes failed to cache"

        # Verify files were created by all processes
        cached_files = list(cache_dir.rglob("*.jpg"))
        assert len(cached_files) >= 4  # At least one per process


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
