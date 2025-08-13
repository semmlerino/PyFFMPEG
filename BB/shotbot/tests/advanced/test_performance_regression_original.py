from tests.helpers.synchronization import simulate_work_without_sleep

"""Performance regression testing for ShotBot.

This module provides automated performance baselines, benchmarking,
and memory leak detection to catch performance regressions early.
"""

import gc
import time
import tracemalloc
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import pytest

try:
    import psutil
except ImportError:
    pytest.skip("psutil not installed", allow_module_level=True)


@dataclass
class PerformanceMetric:
    """Represents a performance measurement."""

    name: str
    value: float
    unit: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PerformanceBaseline:
    """Performance baseline for comparison."""

    test_name: str
    metrics: Dict[str, PerformanceMetric]
    threshold_percentages: Dict[str, float] = field(default_factory=dict)

    def is_regression(self, metric_name: str, value: float) -> bool:
        """Check if a value represents a performance regression.

        Args:
            metric_name: Name of the metric
            value: Current value to check

        Returns:
            True if value is a regression
        """
        if metric_name not in self.metrics:
            return False

        baseline_value = self.metrics[metric_name].value
        threshold = self.threshold_percentages.get(metric_name, 20.0)  # 20% default

        # For time/memory metrics, higher is worse
        max_allowed = baseline_value * (1 + threshold / 100)
        return value > max_allowed


class PerformanceBenchmark:
    """Benchmark runner for performance tests."""

    def __init__(self, warmup_runs: int = 2, test_runs: int = 10):
        """Initialize benchmark runner.

        Args:
            warmup_runs: Number of warmup iterations
            test_runs: Number of test iterations
        """
        self.warmup_runs = warmup_runs
        self.test_runs = test_runs
        self.results: List[PerformanceMetric] = []

    def benchmark(self, func: Callable, *args, **kwargs) -> Dict[str, float]:
        """Benchmark a function.

        Args:
            func: Function to benchmark
            *args: Positional arguments for function
            **kwargs: Keyword arguments for function

        Returns:
            Dictionary of performance metrics
        """
        # Warmup runs
        for _ in range(self.warmup_runs):
            func(*args, **kwargs)

        # Collect garbage before measurement
        gc.collect()

        # Measure execution times
        times = []
        for _ in range(self.test_runs):
            start = time.perf_counter()
            func(*args, **kwargs)
            end = time.perf_counter()
            times.append(end - start)

        # Calculate statistics
        times.sort()
        metrics = {
            "min_time": min(times),
            "max_time": max(times),
            "mean_time": sum(times) / len(times),
            "median_time": times[len(times) // 2],
            "p95_time": times[int(len(times) * 0.95)],
            "p99_time": times[int(len(times) * 0.99)],
        }

        # Store results
        for name, value in metrics.items():
            self.results.append(PerformanceMetric(name, value, "seconds"))

        return metrics

    def benchmark_memory(self, func: Callable, *args, **kwargs) -> Dict[str, float]:
        """Benchmark memory usage of a function.

        Args:
            func: Function to benchmark
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Dictionary of memory metrics
        """
        gc.collect()

        # Start memory tracing
        tracemalloc.start()

        # Get initial memory
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Run function
        func(*args, **kwargs)

        # Get peak memory
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        final_memory = process.memory_info().rss / 1024 / 1024  # MB

        metrics = {
            "peak_memory_mb": peak / 1024 / 1024,
            "current_memory_mb": current / 1024 / 1024,
            "memory_delta_mb": final_memory - initial_memory,
        }

        # Store results
        for name, value in metrics.items():
            self.results.append(PerformanceMetric(name, value, "MB"))

        return metrics


class MemoryLeakDetector:
    """Detect memory leaks in functions and classes."""

    def __init__(self, threshold_mb: float = 10.0):
        """Initialize memory leak detector.

        Args:
            threshold_mb: Memory increase threshold in MB
        """
        self.threshold_mb = threshold_mb
        self.snapshots: List[Tuple[str, tracemalloc.Snapshot]] = []

    def check_leak(
        self, func: Callable, iterations: int = 100, *args, **kwargs
    ) -> Dict[str, Any]:
        """Check for memory leaks in a function.

        Args:
            func: Function to test
            iterations: Number of iterations
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Dictionary with leak detection results
        """
        gc.collect()
        tracemalloc.start()

        # Take initial snapshot
        snapshot1 = tracemalloc.take_snapshot()

        # Run function multiple times
        for _ in range(iterations):
            func(*args, **kwargs)

        gc.collect()

        # Take final snapshot
        snapshot2 = tracemalloc.take_snapshot()

        # Compare snapshots
        top_stats = snapshot2.compare_to(snapshot1, "lineno")

        # Calculate total memory increase
        total_increase = sum(stat.size_diff for stat in top_stats) / 1024 / 1024  # MB

        # Find top memory increases
        leaks = []
        for stat in top_stats[:10]:
            if stat.size_diff > 0:
                leaks.append(
                    {
                        "file": stat.traceback.format()[0],
                        "size_mb": stat.size_diff / 1024 / 1024,
                        "count_diff": stat.count_diff,
                    }
                )

        tracemalloc.stop()

        return {
            "has_leak": total_increase > self.threshold_mb,
            "total_increase_mb": total_increase,
            "iterations": iterations,
            "top_increases": leaks[:5],
        }

    def monitor_object_lifecycle(
        self,
        obj_factory: Callable,
        operations: List[Callable],
        cleanup: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """Monitor object lifecycle for leaks.

        Args:
            obj_factory: Factory function to create object
            operations: List of operations to perform on object
            cleanup: Optional cleanup function

        Returns:
            Lifecycle analysis results
        """
        gc.collect()

        # Track object count before
        initial_objects = len(gc.get_objects())

        # Create and use object
        obj = obj_factory()

        for operation in operations:
            operation(obj)

        # Cleanup
        if cleanup:
            cleanup(obj)

        del obj
        gc.collect()

        # Check object count after
        final_objects = len(gc.get_objects())

        return {
            "objects_leaked": final_objects - initial_objects,
            "initial_count": initial_objects,
            "final_count": final_objects,
        }


@pytest.fixture
def performance_benchmark():
    """Pytest fixture for performance benchmarking."""
    return PerformanceBenchmark()


@pytest.fixture
def memory_detector():
    """Pytest fixture for memory leak detection."""
    return MemoryLeakDetector()


@pytest.mark.performance
class TestShotModelPerformance:
    """Performance tests for ShotModel."""

    def test_shot_refresh_performance(self, performance_benchmark):
        """Test performance of shot refresh operation."""
        from shot_model import ShotModel

        model = ShotModel()

        # Benchmark refresh operation
        metrics = performance_benchmark.benchmark(model.refresh_shots)

        # Assert performance thresholds
        assert metrics["median_time"] < 2.0, "Shot refresh too slow"
        assert metrics["p95_time"] < 3.0, "Shot refresh P95 too slow"

    def test_shot_model_memory_usage(self, performance_benchmark):
        """Test memory usage of shot model with large dataset."""
        from unittest.mock import patch

        from shot_model import Shot, ShotModel

        model = ShotModel()

        # Mock large shot list with proper Shot objects
        large_shot_list = [
            Shot(
                show="TEST_SHOW",
                sequence=f"SEQ_{i // 100:03d}",
                shot=f"SHOT_{i:04d}",
                workspace_path=f"/shows/TEST_SHOW/SEQ_{i // 100:03d}/SHOT_{i:04d}",
            )
            for i in range(10000)
        ]

        with patch.object(model, "_parse_ws_output", return_value=large_shot_list):
            metrics = performance_benchmark.benchmark_memory(model.refresh_shots)

        # Assert memory thresholds
        assert metrics["peak_memory_mb"] < 100, "Excessive memory usage"

    def test_shot_model_memory_leak(self, memory_detector):
        """Test for memory leaks in shot model operations."""
        from unittest.mock import MagicMock, patch

        from shot_model import Shot, ShotModel

        # Create mock shots for testing
        mock_shots = [
            Shot(
                show="TEST_SHOW",
                sequence=f"SEQ_{i // 10:02d}",
                shot=f"SHOT_{i:03d}",
                workspace_path=f"/shows/TEST_SHOW/SEQ_{i // 10:02d}/SHOT_{i:03d}",
            )
            for i in range(100)
        ]

        def create_and_refresh():
            model = ShotModel()
            # Mock the subprocess call to avoid timeout
            with patch("shot_model.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0, stdout="mock output", stderr=""
                )
                with patch.object(model, "_parse_ws_output", return_value=mock_shots):
                    model.refresh_shots()
            _ = model.shots  # Access shots property, not method
            return model

        # Check for leaks
        result = memory_detector.check_leak(create_and_refresh, iterations=50)

        assert not result["has_leak"], (
            f"Memory leak detected: {result['total_increase_mb']:.2f} MB increase"
        )


@pytest.mark.performance
class TestCachePerformance:
    """Performance tests for cache manager."""

    def test_cache_lookup_performance(self, performance_benchmark):
        """Test cache lookup performance with many entries."""
        from tempfile import TemporaryDirectory

        from cache_manager import CacheManager
        from shot_model import Shot

        with TemporaryDirectory() as temp_dir:
            cache = CacheManager(cache_dir=Path(temp_dir))

            # Create large shot list to cache
            large_shot_list = [
                Shot(
                    show="TEST_SHOW",
                    sequence=f"SEQ_{i // 100:03d}",
                    shot=f"SHOT_{i:04d}",
                    workspace_path=f"/shows/TEST_SHOW/SEQ_{i // 100:03d}/SHOT_{i:04d}",
                )
                for i in range(1000)
            ]

            # Cache the shots
            cache.cache_shots(large_shot_list)

            # Benchmark repeated cache lookups
            def lookup_operations():
                for _ in range(100):
                    result = cache.get_cached_shots()
                    # Verify we got data to ensure cache is working
                    assert result is not None
                    assert len(result) == 1000

            metrics = performance_benchmark.benchmark(lookup_operations)

            # Assert lookup is fast - JSON deserialization should be efficient
            assert metrics["mean_time"] < 0.1, "Cache lookup too slow"

    def test_cache_memory_efficiency(self, performance_benchmark):
        """Test memory efficiency of cache with large shot datasets."""
        from tempfile import TemporaryDirectory

        from cache_manager import CacheManager
        from shot_model import Shot

        with TemporaryDirectory() as temp_dir:
            cache = CacheManager(cache_dir=Path(temp_dir))

            # Create large shot datasets to test memory efficiency
            def create_large_dataset():
                large_shot_lists = []
                for batch in range(10):  # 10 batches of 1000 shots each
                    shot_list = [
                        Shot(
                            show=f"SHOW_{batch:03d}",
                            sequence=f"SEQ_{i // 100:03d}",
                            shot=f"SHOT_{i:04d}",
                            workspace_path=f"/shows/SHOW_{batch:03d}/SEQ_{i // 100:03d}/SHOT_{i:04d}",
                        )
                        for i in range(1000)
                    ]
                    large_shot_lists.append(shot_list)
                    # Cache each batch
                    cache.cache_shots(shot_list)

                return large_shot_lists

            # Test memory usage for large cache operations
            metrics = performance_benchmark.benchmark_memory(create_large_dataset)

            # Verify cache performance by reading back data
            final_result = cache.get_cached_shots()
            assert final_result is not None, "Cache should contain the last shot batch"
            assert len(final_result) == 1000, "Cache should contain 1000 shots"

            # Memory usage should be reasonable even with large datasets
            assert metrics["memory_delta_mb"] < 100, (
                "Cache using too much memory for large datasets"
            )

            # Test that cache files exist and are reasonable sizes
            cache_files = list(Path(temp_dir).rglob("*.json"))
            assert len(cache_files) > 0, "Cache files should be created"

            total_cache_size_mb = (
                sum(f.stat().st_size for f in cache_files) / 1024 / 1024
            )
            assert total_cache_size_mb < 50, (
                f"Cache files too large: {total_cache_size_mb:.2f}MB"
            )

    def test_cache_expiration_performance(self, performance_benchmark):
        """Test performance of cache expiration checks."""
        from datetime import datetime, timedelta
        from tempfile import TemporaryDirectory
        from unittest.mock import patch

        from cache_manager import CacheManager
        from shot_model import Shot

        with TemporaryDirectory() as temp_dir:
            cache = CacheManager(cache_dir=Path(temp_dir))

            # Create test shots to cache
            test_shots = [
                Shot(
                    show="TEST_SHOW",
                    sequence="SEQ_001",
                    shot=f"SHOT_{i:04d}",
                    workspace_path=f"/test/path/SHOT_{i:04d}",
                )
                for i in range(100)
            ]

            # Cache the shots
            cache.cache_shots(test_shots)

            # Mock the cache expiry to make entries appear expired
            expired_time = datetime.now() - timedelta(hours=2)

            with patch("cache_manager.datetime") as mock_datetime:
                mock_datetime.now.return_value = datetime.now()
                mock_datetime.fromisoformat.return_value = expired_time

                # Benchmark expiration checks - should return None for expired cache
                def check_expired_cache():
                    for _ in range(100):
                        result = cache.get_cached_shots()
                        # With expired cache, should return None
                        assert result is None

                metrics = performance_benchmark.benchmark(check_expired_cache)

            # Expiration checks should be fast even with many entries
            assert metrics["mean_time"] < 0.05, "Expiration checks too slow"


@pytest.mark.performance
class TestFinderPerformance:
    """Performance tests for finder components."""

    def test_plate_finder_performance(self, performance_benchmark):
        """Test raw plate finder performance."""
        from unittest.mock import patch

        from raw_plate_finder import RawPlateFinder

        # Mock filesystem operations
        with patch(
            "raw_plate_finder.PathUtils.validate_path_exists", return_value=True
        ):
            with patch(
                "raw_plate_finder.PathUtils.discover_plate_directories",
                return_value=[("FG01", 0), ("BG01", 1)],
            ):
                with patch(
                    "raw_plate_finder.VersionUtils.get_latest_version",
                    return_value="v001",
                ):
                    with patch("pathlib.Path.exists", return_value=True):
                        with patch("pathlib.Path.iterdir", return_value=[]):
                            metrics = performance_benchmark.benchmark(
                                RawPlateFinder.find_latest_raw_plate,
                                "/test/path",
                                "TEST_0001",
                            )

        # Should be very fast with mocked I/O
        assert metrics["mean_time"] < 0.01, "Plate finder too slow"

    def test_threede_finder_performance(self, performance_benchmark):
        """Test 3DE scene finder performance."""
        from pathlib import Path
        from unittest.mock import patch

        from threede_scene_finder import ThreeDESceneFinder

        # Mock filesystem operations for the static method
        with patch(
            "threede_scene_finder.PathUtils.validate_path_exists", return_value=True
        ):
            with patch("pathlib.Path.iterdir", return_value=[]):
                with patch(
                    "threede_scene_finder.PathUtils.build_path",
                    return_value=Path("/test/user"),
                ):
                    metrics = performance_benchmark.benchmark(
                        ThreeDESceneFinder.find_scenes_for_shot,
                        "/test/workspace",
                        "TEST_SHOW",
                        "SEQ_001",
                        "0001",
                    )

        # Should be fast with mocked I/O
        assert metrics["mean_time"] < 0.05, "3DE finder too slow"

    def test_threede_deduplication_performance(self, performance_benchmark):
        """Test performance of 3DE scene deduplication."""
        from pathlib import Path

        from threede_scene_model import ThreeDEScene, ThreeDESceneModel

        model = ThreeDESceneModel()

        # Create many duplicate scenes with correct constructor parameters
        scenes = []
        for i in range(100):
            for j in range(5):  # 5 duplicates each
                scenes.append(
                    ThreeDEScene(
                        show="TEST_SHOW",
                        sequence="SEQ_001",
                        shot=f"SHOT_{i:04d}",
                        workspace_path=f"/test/workspace/SHOT_{i:04d}",
                        user=f"user{j}",
                        plate=f"plate_{i}",
                        scene_path=Path(f"/path/user{j}/scene_{i:03d}.3de"),
                    )
                )

        # Benchmark deduplication using the model's method
        metrics = performance_benchmark.benchmark(
            model._deduplicate_scenes_by_shot, scenes
        )

        # Should handle deduplication efficiently
        assert metrics["mean_time"] < 0.1, "Deduplication too slow"


@pytest.mark.performance
class TestUIPerformance:
    """Performance tests for UI components."""

    def test_grid_widget_scaling(self, qtbot, performance_benchmark):
        """Test grid widget performance with many items."""
        from shot_grid import ShotGrid
        from shot_model import Shot, ShotModel

        # Create a shot model with test data
        shot_model = ShotModel(load_cache=False)
        test_shots = [
            Shot(
                show="TEST_SHOW",
                sequence="SEQ_001",
                shot=f"SHOT_{i:04d}",
                workspace_path=f"/test/path/SHOT_{i:04d}",
            )
            for i in range(100)
        ]
        shot_model.shots = test_shots

        grid = ShotGrid(shot_model)
        qtbot.addWidget(grid)

        # Benchmark refreshing with many shots
        def refresh_many_shots():
            grid.refresh_shots()

        metrics = performance_benchmark.benchmark(refresh_many_shots)

        # Should scale well
        assert metrics["mean_time"] < 1.0, "Grid scaling poor"

    def test_thumbnail_loading_performance(self, qtbot, performance_benchmark):
        """Test thumbnail widget loading performance."""
        from unittest.mock import patch

        from shot_model import Shot
        from thumbnail_widget import ThumbnailWidget

        # Mock image loading
        with patch("PySide6.QtGui.QPixmap.load", return_value=True):

            def create_thumbnails():
                widgets = []
                for i in range(50):
                    # Create proper Shot object for ThumbnailWidget
                    shot = Shot(
                        show="TEST_SHOW",
                        sequence="SEQ_001",
                        shot=f"SHOT_{i:04d}",
                        workspace_path=f"/test/path/SHOT_{i:04d}",
                    )
                    widget = ThumbnailWidget(shot)
                    qtbot.addWidget(widget)
                    widgets.append(widget)
                return widgets

            metrics = performance_benchmark.benchmark(create_thumbnails)

        # Should handle many thumbnails efficiently
        assert metrics["mean_time"] < 0.5, "Thumbnail creation too slow"


class PerformanceReporter:
    """Generate performance test reports."""

    @staticmethod
    def generate_report(
        benchmarks: List[PerformanceBenchmark],
        baselines: Optional[Dict[str, PerformanceBaseline]] = None,
    ) -> str:
        """Generate performance report.

        Args:
            benchmarks: List of benchmark results
            baselines: Optional baselines for comparison

        Returns:
            Formatted report string
        """
        report = ["Performance Test Report", "=" * 50, ""]

        for benchmark in benchmarks:
            report.append("Benchmark Results:")
            report.append("-" * 30)

            for metric in benchmark.results:
                line = f"{metric.name}: {metric.value:.4f} {metric.unit}"

                # Check against baseline if available
                if baselines and metric.name in baselines:
                    baseline = baselines[metric.name]
                    if baseline.is_regression(metric.name, metric.value):
                        line += " ⚠️ REGRESSION"
                    else:
                        line += " ✓"

                report.append(line)

            report.append("")

        return "\n".join(report)

    @staticmethod
    def save_baseline(benchmark: PerformanceBenchmark, filepath: Path):
        """Save benchmark results as baseline.

        Args:
            benchmark: Benchmark with results
            filepath: Path to save baseline
        """
        import json

        baseline_data = {"timestamp": datetime.now().isoformat(), "metrics": {}}

        for metric in benchmark.results:
            baseline_data["metrics"][metric.name] = {
                "value": metric.value,
                "unit": metric.unit,
            }

        with open(filepath, "w") as f:
            json.dump(baseline_data, f, indent=2)


# CI/CD Integration
class CIPerformanceMonitor:
    """Monitor performance in CI/CD pipeline."""

    @staticmethod
    def check_regression(
        current_metrics: Dict[str, float],
        baseline_file: Path,
        threshold_percent: float = 20.0,
    ) -> Tuple[bool, List[str]]:
        """Check for performance regression against baseline.

        Args:
            current_metrics: Current performance metrics
            baseline_file: Path to baseline file
            threshold_percent: Regression threshold percentage

        Returns:
            Tuple of (has_regression, list of regressions)
        """
        import json

        if not baseline_file.exists():
            return False, ["No baseline found"]

        with open(baseline_file, "r") as f:
            baseline_data = json.load(f)

        regressions = []

        for metric_name, current_value in current_metrics.items():
            if metric_name in baseline_data["metrics"]:
                baseline_value = baseline_data["metrics"][metric_name]["value"]

                # Check if regression
                max_allowed = baseline_value * (1 + threshold_percent / 100)
                if current_value > max_allowed:
                    regressions.append(
                        f"{metric_name}: {current_value:.4f} > {max_allowed:.4f} "
                        f"(baseline: {baseline_value:.4f})"
                    )

        return len(regressions) > 0, regressions


if __name__ == "__main__":
    # Example: Run performance benchmarks
    benchmark = PerformanceBenchmark()

    # Example function to benchmark
    def example_operation():
        simulate_work_without_sleep(1)
        data = list(range(1000))
        return sum(data)

    print("Running performance benchmark...")
    metrics = benchmark.benchmark(example_operation)

    print("\nPerformance Metrics:")
    for name, value in metrics.items():
        print(f"  {name}: {value:.6f} seconds")

    # Check for memory leaks
    detector = MemoryLeakDetector()
    leak_result = detector.check_leak(example_operation, iterations=100)

    print("\nMemory Leak Check:")
    print(f"  Has leak: {leak_result['has_leak']}")
    print(f"  Total increase: {leak_result['total_increase_mb']:.2f} MB")
