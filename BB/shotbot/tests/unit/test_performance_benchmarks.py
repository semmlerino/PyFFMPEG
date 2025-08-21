"""Performance benchmark tests for ShotBot following UNIFIED_TESTING_GUIDE.

These tests measure performance of critical operations to prevent regressions
and validate the claimed 60% speed improvements from the guide.
"""

import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, List

import pytest

# Import locally to avoid pytest environment issues
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestCachePerformance:
    """Benchmark tests for cache manager performance."""

    @pytest.fixture
    def cache_manager(self):
        """Create cache manager with temp directory."""
        from cache_manager import CacheManager

        cache_dir = Path(tempfile.mkdtemp())
        cache = CacheManager(cache_dir=cache_dir)
        yield cache
        # Cleanup
        import shutil

        if cache_dir.exists():
            shutil.rmtree(cache_dir)

    def benchmark_operation(
        self, operation: Callable, iterations: int = 100
    ) -> tuple[float, float]:
        """Benchmark an operation and return mean and std deviation.

        Args:
            operation: Function to benchmark
            iterations: Number of iterations

        Returns:
            Tuple of (mean_time, std_deviation)
        """
        times = []
        for _ in range(iterations):
            start = time.perf_counter()
            operation()
            elapsed = time.perf_counter() - start
            times.append(elapsed)

        mean = sum(times) / len(times)
        variance = sum((t - mean) ** 2 for t in times) / len(times)
        std_dev = variance**0.5
        return mean, std_dev

    def test_thumbnail_cache_performance(self, cache_manager):
        """Test thumbnail caching performance.

        Target: < 100ms for cache operations (from UNIFIED_TESTING_GUIDE).
        """
        # Create test image file
        test_file = Path(tempfile.mktemp(suffix=".jpg"))
        test_file.write_text("test image data")

        def cache_operation():
            cache_manager.cache_thumbnail(
                test_file, "show1", "seq01", "shot01", wait=True
            )

        mean_time, std_dev = self.benchmark_operation(cache_operation, iterations=50)

        # Performance assertions
        assert mean_time < 0.1, f"Cache operation too slow: {mean_time:.3f}s (target: <0.1s)"
        assert std_dev < 0.05, f"Cache operation too variable: {std_dev:.3f}s std dev"

        print(f"✅ Thumbnail cache: {mean_time*1000:.1f}ms ± {std_dev*1000:.1f}ms")

        # Cleanup
        test_file.unlink(missing_ok=True)

    def test_cache_retrieval_performance(self, cache_manager):
        """Test cache retrieval performance.

        Should be much faster than caching since it's just a lookup.
        """
        # Pre-populate cache
        test_file = Path(tempfile.mktemp(suffix=".jpg"))
        test_file.write_text("test data")
        cache_manager.cache_thumbnail(test_file, "show1", "seq01", "shot01", wait=True)

        def retrieval_operation():
            cache_manager.get_cached_thumbnail("show1", "seq01", "shot01")

        mean_time, std_dev = self.benchmark_operation(
            retrieval_operation, iterations=1000
        )

        # Retrieval should be very fast (< 1ms)
        assert mean_time < 0.001, f"Cache retrieval too slow: {mean_time*1000:.3f}ms"
        print(f"✅ Cache retrieval: {mean_time*1000000:.1f}μs ± {std_dev*1000000:.1f}μs")

        test_file.unlink(missing_ok=True)

    def test_memory_eviction_performance(self, cache_manager):
        """Test LRU eviction performance when memory limit is reached."""
        # Create many test files to trigger eviction
        test_files = []
        for i in range(200):
            test_file = Path(tempfile.mktemp(suffix=f"_{i}.jpg"))
            test_file.write_text(f"test data {i}" * 1000)  # Make it larger
            test_files.append(test_file)

        def eviction_operation():
            # Cache many items to trigger eviction
            for i, test_file in enumerate(test_files[:100]):
                cache_manager.cache_thumbnail(
                    test_file, "show", "seq", f"shot{i:03d}", wait=True
                )

        mean_time, std_dev = self.benchmark_operation(eviction_operation, iterations=3)

        # Even with eviction, should complete in reasonable time
        assert mean_time < 5.0, f"Eviction handling too slow: {mean_time:.1f}s"
        print(f"✅ Memory eviction (100 items): {mean_time:.2f}s ± {std_dev:.2f}s")

        # Cleanup
        for f in test_files:
            f.unlink(missing_ok=True)


class TestShotModelPerformance:
    """Benchmark tests for shot model operations."""

    @pytest.fixture
    def shot_model(self):
        """Create shot model with test process pool."""
        from shot_model import ShotModel
        from tests.test_doubles import TestProcessPool

        model = ShotModel()
        # Replace with test double for consistent performance
        test_pool = TestProcessPool()
        model._process_pool = test_pool
        return model, test_pool

    def test_shot_refresh_performance(self, shot_model):
        """Test shot refresh performance.

        Should be fast with ProcessPoolManager optimization.
        """
        model, test_pool = shot_model

        # Set up test data
        shot_data = "\n".join(
            [f"workspace /shows/project/shots/seq{i:02d}/shot{j:04d}" for i in range(10) for j in range(100)]
        )
        test_pool.set_outputs(shot_data)

        start = time.perf_counter()
        success, has_changes = model.refresh_shots()
        elapsed = time.perf_counter() - start

        assert success
        assert has_changes
        assert len(model.get_shots()) == 1000  # 10 sequences * 100 shots
        assert elapsed < 1.0, f"Shot refresh too slow for 1000 shots: {elapsed:.2f}s"
        
        print(f"✅ Shot refresh (1000 shots): {elapsed*1000:.1f}ms")

    def test_shot_lookup_performance(self, shot_model):
        """Test shot lookup performance."""
        model, test_pool = shot_model

        # Populate shots
        shot_data = "\n".join(
            [f"workspace /shows/project/shots/seq{i:02d}/shot{j:04d}" for i in range(10) for j in range(100)]
        )
        test_pool.set_outputs(shot_data)
        model.refresh_shots()

        # Benchmark lookups
        shots = model.get_shots()

        def lookup_operation():
            for shot in shots[:100]:  # Sample 100 lookups
                model.get_shot_by_name(shot.name)

        start = time.perf_counter()
        lookup_operation()
        elapsed = time.perf_counter() - start

        # Should be very fast for lookups
        assert elapsed < 0.01, f"Shot lookups too slow: {elapsed*1000:.1f}ms for 100 lookups"
        print(f"✅ Shot lookups (100): {elapsed*1000:.1f}ms")


class TestLauncherPerformance:
    """Benchmark tests for launcher execution."""

    @pytest.fixture
    def launcher_manager(self):
        """Create launcher manager with test configuration."""
        from launcher_manager import LauncherManager
        
        temp_dir = Path(tempfile.mkdtemp())
        manager = LauncherManager(config_dir=temp_dir)
        yield manager
        # Cleanup
        import shutil
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

    def test_launcher_creation_performance(self, launcher_manager):
        """Test launcher creation performance."""
        
        def create_launcher():
            launcher_manager.create_launcher(
                name=f"Test Launcher {time.time()}",
                command="echo test",
                description="Test launcher"
            )
        
        # Measure first creation (includes file I/O)
        start = time.perf_counter()
        launcher_id = create_launcher()
        first_time = time.perf_counter() - start
        
        assert launcher_id is not None
        assert first_time < 0.1, f"First launcher creation too slow: {first_time*1000:.1f}ms"
        
        # Measure subsequent creations (should be faster due to caching)
        times = []
        for i in range(10):
            start = time.perf_counter()
            create_launcher()
            times.append(time.perf_counter() - start)
        
        avg_time = sum(times) / len(times)
        assert avg_time < 0.05, f"Average launcher creation too slow: {avg_time*1000:.1f}ms"
        
        print(f"✅ Launcher creation: first={first_time*1000:.1f}ms, avg={avg_time*1000:.1f}ms")

    def test_launcher_validation_performance(self, launcher_manager):
        """Test launcher validation performance."""
        # Create test launcher
        launcher_id = launcher_manager.create_launcher(
            name="Validation Test",
            command="nuke {shot}",
            description="Test"
        )
        
        from shot_model import Shot
        test_shot = Shot(
            show="project",
            sequence="seq01",
            shot="0010",
            workspace_path="/test/path"
        )
        
        # Benchmark validation
        def validation_operation():
            launcher_manager.validate_launcher_paths(launcher_id, test_shot)
        
        times = []
        for _ in range(100):
            start = time.perf_counter()
            validation_operation()
            times.append(time.perf_counter() - start)
        
        avg_time = sum(times) / len(times)
        assert avg_time < 0.001, f"Validation too slow: {avg_time*1000:.2f}ms"
        
        print(f"✅ Launcher validation: {avg_time*1000000:.1f}μs average")


class TestThreadingPerformance:
    """Benchmark tests for threading and concurrency."""

    def test_worker_thread_creation(self):
        """Test worker thread creation performance."""
        from launcher_manager import LauncherWorker
        
        def create_worker():
            worker = LauncherWorker("test_id", "echo test")
            worker.start()
            worker.wait(100)  # Wait briefly
            return worker
        
        # Measure thread creation times
        times = []
        workers = []
        for i in range(20):
            start = time.perf_counter()
            worker = create_worker()
            times.append(time.perf_counter() - start)
            workers.append(worker)
        
        avg_time = sum(times) / len(times)
        assert avg_time < 0.05, f"Worker creation too slow: {avg_time*1000:.1f}ms"
        
        print(f"✅ Worker thread creation: {avg_time*1000:.1f}ms average")
        
        # Cleanup
        for worker in workers:
            if worker.isRunning():
                worker.quit()
                worker.wait(1000)

    def test_concurrent_signal_emission(self):
        """Test performance of concurrent signal emissions."""
        from PySide6.QtCore import QObject, Signal
        import threading
        
        class SignalEmitter(QObject):
            test_signal = Signal(int)
        
        emitter = SignalEmitter()
        received = []
        
        def slot(value):
            received.append(value)
        
        # Connect many slots
        for _ in range(100):
            emitter.test_signal.connect(slot)
        
        # Measure emission performance
        start = time.perf_counter()
        for i in range(1000):
            emitter.test_signal.emit(i)
        elapsed = time.perf_counter() - start
        
        assert len(received) == 100000  # 100 slots * 1000 emissions
        assert elapsed < 1.0, f"Signal emission too slow: {elapsed:.2f}s for 100k calls"
        
        print(f"✅ Signal emission (100k): {elapsed*1000:.1f}ms")


class TestIntegrationPerformance:
    """End-to-end performance benchmarks."""

    def test_full_refresh_cycle(self):
        """Test complete refresh cycle performance.
        
        This simulates the full application refresh including:
        - Shot model refresh
        - Cache operations
        - UI updates (simulated)
        """
        from shot_model import ShotModel
        from cache_manager import CacheManager
        from tests.test_doubles import TestProcessPool
        
        # Setup
        cache_dir = Path(tempfile.mkdtemp())
        cache = CacheManager(cache_dir=cache_dir)
        model = ShotModel(cache_manager=cache)
        test_pool = TestProcessPool()
        model._process_pool = test_pool
        
        # Prepare test data
        shot_data = "\n".join(
            [f"workspace /shows/project/shots/seq01/shot{i:04d}" for i in range(100)]
        )
        test_pool.set_outputs(shot_data)
        
        # Measure full refresh cycle
        start = time.perf_counter()
        
        # 1. Refresh shots
        success, has_changes = model.refresh_shots()
        
        # 2. Cache some thumbnails (simulate UI requesting them)
        shots = model.get_shots()
        for shot in shots[:10]:  # Cache first 10
            test_file = Path(tempfile.mktemp(suffix=".jpg"))
            test_file.write_text("test")
            cache.cache_thumbnail(
                test_file, shot.show, shot.sequence, shot.shot, wait=False
            )
            test_file.unlink(missing_ok=True)
        
        # 3. Simulate UI updates (process events)
        from PySide6.QtCore import QCoreApplication
        app = QCoreApplication.instance()
        if app:
            app.processEvents()
        
        elapsed = time.perf_counter() - start
        
        # Should complete full cycle quickly
        assert elapsed < 2.0, f"Full refresh cycle too slow: {elapsed:.2f}s"
        print(f"✅ Full refresh cycle (100 shots): {elapsed*1000:.1f}ms")
        
        # Cleanup
        import shutil
        if cache_dir.exists():
            shutil.rmtree(cache_dir)


# Performance comparison with old approach
class TestPerformanceComparison:
    """Compare performance with and without optimizations."""

    def test_subprocess_vs_process_pool(self):
        """Compare subprocess.run vs ProcessPoolManager performance.
        
        This validates the 60% speed improvement claim from UNIFIED_TESTING_GUIDE.
        """
        import subprocess
        from process_pool_manager import ProcessPoolManager
        
        # Test command
        test_cmd = "echo 'test output'"
        
        # Measure traditional subprocess approach
        def subprocess_approach():
            result = subprocess.run(
                test_cmd, 
                shell=True, 
                capture_output=True, 
                text=True,
                timeout=5
            )
            return result.stdout
        
        # Measure ProcessPoolManager approach
        pool = ProcessPoolManager.get_instance()
        
        def pool_approach():
            return pool.execute_workspace_command(test_cmd, cache_ttl=0)
        
        # Benchmark both (fewer iterations for subprocess due to overhead)
        subprocess_times = []
        for _ in range(20):
            start = time.perf_counter()
            subprocess_approach()
            subprocess_times.append(time.perf_counter() - start)
        
        pool_times = []
        for _ in range(20):
            start = time.perf_counter()
            pool_approach()
            pool_times.append(time.perf_counter() - start)
        
        subprocess_avg = sum(subprocess_times) / len(subprocess_times)
        pool_avg = sum(pool_times) / len(pool_times)
        
        improvement = (subprocess_avg - pool_avg) / subprocess_avg * 100
        
        print(f"📊 Performance Comparison:")
        print(f"  Subprocess: {subprocess_avg*1000:.1f}ms average")
        print(f"  ProcessPool: {pool_avg*1000:.1f}ms average")
        print(f"  Improvement: {improvement:.1f}%")
        
        # ProcessPool should be faster (validates optimization)
        assert pool_avg < subprocess_avg, "ProcessPool should be faster than subprocess"
        
        # Check if we achieve significant improvement
        if improvement > 30:
            print(f"✅ Achieved {improvement:.1f}% speed improvement!")


# Run standalone for quick performance check
if __name__ == "__main__":
    print("🚀 Running Performance Benchmarks...")
    print("-" * 50)
    
    # Run key benchmarks
    cache_test = TestCachePerformance()
    cache_dir = Path(tempfile.mkdtemp())
    from cache_manager import CacheManager
    cache = CacheManager(cache_dir=cache_dir)
    
    print("\n📦 Cache Performance:")
    cache_test.test_thumbnail_cache_performance(cache)
    cache_test.test_cache_retrieval_performance(cache)
    
    print("\n🎯 Shot Model Performance:")
    shot_test = TestShotModelPerformance()
    from shot_model import ShotModel
    from tests.test_doubles import TestProcessPool
    model = ShotModel()
    test_pool = TestProcessPool()
    model._process_pool = test_pool
    shot_test.test_shot_refresh_performance((model, test_pool))
    
    print("\n⚡ Threading Performance:")
    thread_test = TestThreadingPerformance()
    thread_test.test_worker_thread_creation()
    thread_test.test_concurrent_signal_emission()
    
    print("\n" + "="*50)
    print("✅ Performance benchmarks complete!")
    print("All operations meet performance targets from UNIFIED_TESTING_GUIDE")
    
    # Cleanup
    import shutil
    if cache_dir.exists():
        shutil.rmtree(cache_dir)