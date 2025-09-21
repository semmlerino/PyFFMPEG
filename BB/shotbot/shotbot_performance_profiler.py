#!/usr/bin/env python3
"""
ShotBot Performance Profiler

Comprehensive performance analysis script targeting:
1. UI Rendering Bottlenecks (ShotGridView painting, thumbnail loading)
2. Memory Usage Patterns (cache_manager 100MB limit, QPixmap retention)
3. I/O Operations (filesystem scanning, subprocess communication)
4. Database/Cache Performance (ShotCache/ThreeDECache TTL efficiency)
5. Thread Pool Optimization (ThreadPoolExecutor, QThreadPool configuration)

Measures specific operations:
- Shot grid population with 432 shots
- 3DE scene scanning across network paths
- Thumbnail generation pipeline
"""

import cProfile
import io
import os
import pstats
import sys
import time
import tracemalloc
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

# Set up environment for mock mode
os.environ["SHOTBOT_MOCK"] = "1"

# Ensure Qt can run in headless mode for profiling
os.environ["QT_QPA_PLATFORM"] = "offscreen"

# Import ShotBot components after environment setup
sys.path.insert(0, str(Path(__file__).parent))

from PySide6.QtCore import QThreadPool
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from cache.memory_manager import MemoryManager
from cache.shot_cache import ShotCache
from cache.threede_cache import ThreeDECache
from cache.thumbnail_processor import ThumbnailProcessor
from cache_manager import CacheManager
from config import ThreadingConfig
from previous_shots_finder import PreviousShotsFinder
from shot_grid_view import ShotGridView
from shot_item_model import ShotItemModel
from shot_model import Shot, ShotModel


class PerformanceProfiler:
    """Comprehensive performance profiler for ShotBot application."""

    def __init__(self):
        self.results = {}
        self.app = None

    def setup_qt_app(self):
        """Initialize Qt application for UI profiling."""
        if not QApplication.instance():
            self.app = QApplication(sys.argv)
        else:
            self.app = QApplication.instance()

    @contextmanager
    def profile_cpu(self, operation_name: str):
        """Profile CPU usage for a specific operation."""
        profiler = cProfile.Profile()
        profiler.enable()
        start_time = time.perf_counter()

        try:
            yield
        finally:
            end_time = time.perf_counter()
            profiler.disable()

            # Capture profiling statistics
            s = io.StringIO()
            ps = pstats.Stats(profiler, stream=s)
            ps.sort_stats("cumulative")
            ps.print_stats(20)  # Top 20 functions

            self.results[f"{operation_name}_cpu"] = {
                "duration": end_time - start_time,
                "profile_stats": s.getvalue(),
            }

    @contextmanager
    def profile_memory(self, operation_name: str):
        """Profile memory usage for a specific operation."""
        tracemalloc.start()

        try:
            yield
        finally:
            current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()

            self.results[f"{operation_name}_memory"] = {
                "current_mb": current / 1024 / 1024,
                "peak_mb": peak / 1024 / 1024,
            }

    def profile_ui_rendering(self):
        """Profile UI rendering bottlenecks."""
        print("=== Profiling UI Rendering Performance ===")

        self.setup_qt_app()

        # Create mock shot data (432 shots as mentioned)
        mock_shots = []
        for i in range(432):
            shot = Shot(
                name=f"shot_{i:04d}",
                sequence="test_seq",
                show="test_show",
                frame_range=(1001, 1100),
                status="active",
                path=Path(f"/mock/shows/test_show/test_seq/shot_{i:04d}"),
            )
            mock_shots.append(shot)

        # Test 1: Shot grid population
        with self.profile_cpu("shot_grid_population"):
            with self.profile_memory("shot_grid_population"):
                shot_model = ShotModel()
                shot_model._shots = mock_shots

                item_model = ShotItemModel()
                item_model.set_shots(mock_shots)

                grid_view = ShotGridView()
                grid_view.setModel(item_model)

                # Force rendering of all items
                grid_view.show()
                self.app.processEvents()

        # Test 2: Thumbnail loading pipeline efficiency
        cache_manager = CacheManager()
        thumbnail_count = 50  # Test with 50 thumbnails

        with self.profile_cpu("thumbnail_loading_pipeline"):
            with self.profile_memory("thumbnail_loading_pipeline"):
                thumbnail_processor = ThumbnailProcessor()

                # Simulate thumbnail processing
                for i in range(thumbnail_count):
                    mock_image_path = Path(f"/mock/thumbnail_{i}.jpg")
                    try:
                        # This would normally process actual images
                        result = thumbnail_processor._create_placeholder_thumbnail()
                        if result:
                            # Simulate memory usage tracking
                            cache_manager._memory_manager.track_item(
                                mock_image_path,
                                50 * 1024,  # 50KB per thumbnail
                            )
                    except Exception as e:
                        print(f"Thumbnail processing error: {e}")

        # Test 3: QPixmap retention and cleanup
        pixmaps = []
        with self.profile_cpu("qpixmap_operations"):
            with self.profile_memory("qpixmap_operations"):
                # Create and manipulate QPixmaps
                for i in range(100):
                    pixmap = QPixmap(200, 200)
                    pixmap.fill()
                    pixmaps.append(pixmap)

                # Test painting operations
                for pixmap in pixmaps:
                    painter = QPainter(pixmap)
                    painter.drawRect(10, 10, 50, 50)
                    painter.end()

                # Cleanup
                pixmaps.clear()

    def profile_memory_patterns(self):
        """Profile memory usage patterns."""
        print("=== Profiling Memory Usage Patterns ===")

        # Test memory manager 100MB limit enforcement
        memory_manager = MemoryManager(max_memory_mb=10)  # Use 10MB for testing

        with self.profile_cpu("memory_limit_enforcement"):
            with self.profile_memory("memory_limit_enforcement"):
                # Simulate adding files until limit is exceeded
                for i in range(200):  # Add items beyond limit
                    mock_path = Path(f"/mock/cache/item_{i}.dat")
                    memory_manager.track_item(mock_path, 100 * 1024)  # 100KB each

                    # Trigger eviction when over limit
                    if memory_manager.is_over_limit():
                        evicted = memory_manager.evict_if_needed()
                        print(f"Evicted {evicted} items")

        # Test cache validation and cleanup
        cache_manager = CacheManager()
        with self.profile_cpu("cache_validation"):
            # Simulate cache operations
            for i in range(100):
                cache_key = f"test_key_{i}"
                cache_manager._shot_cache._cache[cache_key] = {
                    "data": f"test_data_{i}",
                    "timestamp": time.time(),
                }

    def profile_io_operations(self):
        """Profile I/O operations."""
        print("=== Profiling I/O Operations ===")

        # Test filesystem scanning in find_previous_shots
        with self.profile_cpu("filesystem_scanning"):
            with self.profile_memory("filesystem_scanning"):
                finder = PreviousShotsFinder("test_user")
                # In mock mode, this will use mock data
                try:
                    previous_shots = list(finder.find_previous_shots())
                    print(f"Found {len(previous_shots)} previous shots")
                except Exception as e:
                    print(f"Previous shots scanning error: {e}")

        # Test subprocess communication overhead
        with self.profile_cpu("subprocess_communication"):
            # Simulate multiple subprocess calls
            from process_pool_manager import ProcessPoolManager

            pool_manager = ProcessPoolManager()
            try:
                # This will use mock implementation in mock mode
                result = pool_manager.run_workspace_command(["ws", "-sg"])
                print(f"Subprocess result length: {len(result) if result else 0}")
            except Exception as e:
                print(f"Subprocess communication error: {e}")

    def profile_cache_performance(self):
        """Profile cache performance and TTL efficiency."""
        print("=== Profiling Cache Performance ===")

        # Test ShotCache TTL efficiency
        shot_cache = ShotCache(ttl_minutes=1)  # Short TTL for testing

        with self.profile_cpu("shot_cache_operations"):
            # Populate cache
            for i in range(100):
                cache_key = f"shot_{i}"
                shot_data = {
                    "name": f"shot_{i:04d}",
                    "sequence": "test_seq",
                    "show": "test_show",
                }
                shot_cache.set(cache_key, shot_data)

            # Test cache hit rates
            hits = 0
            misses = 0
            for i in range(100):
                cache_key = f"shot_{i}"
                if shot_cache.get(cache_key):
                    hits += 1
                else:
                    misses += 1

            hit_rate = hits / (hits + misses) * 100
            print(f"Cache hit rate: {hit_rate:.1f}%")

        # Test ThreeDECache performance
        threede_cache = ThreeDECache(ttl_minutes=1)

        with self.profile_cpu("threede_cache_operations"):
            # Simulate 3DE scene caching
            for i in range(50):
                scene_key = f"scene_{i}"
                scene_data = {
                    "path": f"/mock/scenes/scene_{i}.3de",
                    "modified": time.time(),
                    "size": 1024 * 1024,  # 1MB
                }
                threede_cache.set(scene_key, scene_data)

    def profile_thread_pool_optimization(self):
        """Profile thread pool optimization."""
        print("=== Profiling Thread Pool Optimization ===")

        # Test ThreadPoolExecutor usage
        with self.profile_cpu("thread_pool_executor"):
            with self.profile_memory("thread_pool_executor"):
                max_workers = ThreadingConfig.MAX_WORKERS

                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    # Simulate I/O bound tasks
                    futures = []
                    for i in range(100):
                        future = executor.submit(self._mock_io_task, i)
                        futures.append(future)

                    # Wait for completion
                    results = []
                    for future in futures:
                        try:
                            result = future.result(timeout=1.0)
                            results.append(result)
                        except Exception as e:
                            print(f"Task error: {e}")

                print(f"Completed {len(results)} tasks")

        # Test QThreadPool configuration
        with self.profile_cpu("qthread_pool"):
            qt_pool = QThreadPool.globalInstance()
            print(f"QThreadPool max threads: {qt_pool.maxThreadCount()}")
            print(f"QThreadPool active threads: {qt_pool.activeThreadCount()}")

    def _mock_io_task(self, task_id: int) -> str:
        """Mock I/O task for thread pool testing."""
        # Simulate some work
        time.sleep(0.01)  # 10ms
        return f"task_{task_id}_complete"

    def run_all_profiles(self):
        """Run all performance profiles."""
        print("Starting ShotBot Performance Analysis...")
        print(f"Timestamp: {datetime.now()}")
        print("-" * 60)

        try:
            self.profile_ui_rendering()
            self.profile_memory_patterns()
            self.profile_io_operations()
            self.profile_cache_performance()
            self.profile_thread_pool_optimization()

        except Exception as e:
            print(f"Profiling error: {e}")
            import traceback

            traceback.print_exc()

        self.print_results()

    def print_results(self):
        """Print performance analysis results."""
        print("\n" + "=" * 60)
        print("PERFORMANCE ANALYSIS RESULTS")
        print("=" * 60)

        for operation, data in self.results.items():
            print(f"\n{operation.upper()}:")
            if "duration" in data:
                print(f"  Duration: {data['duration']:.3f}s")
            if "current_mb" in data:
                print(f"  Memory Usage: {data['current_mb']:.2f}MB")
                print(f"  Peak Memory: {data['peak_mb']:.2f}MB")
            if "profile_stats" in data:
                print("  CPU Profile (top functions):")
                # Print first few lines of profile stats
                lines = data["profile_stats"].split("\n")[:10]
                for line in lines:
                    if line.strip():
                        print(f"    {line}")


if __name__ == "__main__":
    profiler = PerformanceProfiler()
    profiler.run_all_profiles()
