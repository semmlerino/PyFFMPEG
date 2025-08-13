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

import psutil
import pytest


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

        # Create model without loading cache for clean test
        model = ShotModel(load_cache=False)

        # Mock the subprocess to avoid actual ws command
        mock_output = """workspace /shows/ygsk/shots/108_CHV_0001
workspace /shows/ygsk/shots/108_CHV_0002
workspace /shows/ygsk/shots/108_CHV_0003
workspace /shows/ygsk/shots/108_CHV_0004
workspace /shows/ygsk/shots/108_CHV_0005"""

        def mock_run(*args, **kwargs):
            from unittest.mock import Mock

            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = mock_output
            mock_result.stderr = ""
            return mock_result

        from unittest.mock import patch

        with patch("subprocess.run", side_effect=mock_run):
            # Benchmark refresh operation
            metrics = performance_benchmark.benchmark(model.refresh_shots)

        # Assert performance thresholds (more relaxed for mocked operations)
        assert metrics["median_time"] < 0.1, (
            f"Shot refresh too slow: {metrics['median_time']:.3f}s"
        )
        assert metrics["p95_time"] < 0.2, (
            f"Shot refresh P95 too slow: {metrics['p95_time']:.3f}s"
        )

    def test_shot_model_memory_usage(self, performance_benchmark):
        """Test memory usage of shot model with large dataset."""
        from shot_model import Shot, ShotModel

        # Create model without loading cache
        model = ShotModel(load_cache=False)

        # Create many Shot objects to simulate large dataset
        large_shots = []
        for i in range(1000):  # Reduced from 10000 for reasonable test time
            shot = Shot(
                show="ygsk",
                sequence="108",
                shot=f"{i:04d}",
                workspace_path=f"/shows/ygsk/shots/108_CHV_{i:04d}",
            )
            large_shots.append(shot)

        def populate_shots():
            model.shots = large_shots.copy()

        metrics = performance_benchmark.benchmark_memory(populate_shots)

        # Assert memory thresholds (more realistic for 1000 shots)
        assert metrics["peak_memory_mb"] < 50, (
            f"Excessive memory usage: {metrics['peak_memory_mb']:.1f}MB"
        )

    def test_shot_model_memory_leak(self, memory_detector):
        """Test for memory leaks in shot model operations."""
        from shot_model import ShotModel

        def create_and_access():
            model = ShotModel(load_cache=False)
            # Mock a simple refresh that doesn't call subprocess
            mock_output = "workspace /shows/ygsk/shots/108_CHV_0001"
            from unittest.mock import Mock, patch

            with patch("subprocess.run") as mock_run:
                mock_result = Mock()
                mock_result.returncode = 0
                mock_result.stdout = mock_output
                mock_result.stderr = ""
                mock_run.return_value = mock_result

                model.refresh_shots()
                # Access shots attribute (equivalent to get_shots())
                _ = model.shots
            return model

        # Check for leaks with fewer iterations for faster test
        result = memory_detector.check_leak(create_and_access, iterations=20)

        assert not result["has_leak"], (
            f"Memory leak detected: {result['total_increase_mb']:.2f} MB increase"
        )


@pytest.mark.performance
class TestCachePerformance:
    """Performance tests for cache manager."""

    def test_cache_shot_storage_performance(self, performance_benchmark):
        """Test cache storage performance for shot data."""
        from cache_manager import CacheManager
        from shot_model import Shot

        cache = CacheManager()

        # Create test shots
        test_shots = []
        for i in range(100):
            shot = Shot(
                show="ygsk",
                sequence="108",
                shot=f"{i:04d}",
                workspace_path=f"/shows/ygsk/shots/108_CHV_{i:04d}",
            )
            test_shots.append(shot)

        # Benchmark shot caching
        metrics = performance_benchmark.benchmark(cache.cache_shots, test_shots)

        # Assert cache operations are fast
        assert metrics["mean_time"] < 0.1, (
            f"Cache storage too slow: {metrics['mean_time']:.3f}s"
        )

    def test_cache_shot_retrieval_performance(self, performance_benchmark):
        """Test cache retrieval performance for shot data."""
        from cache_manager import CacheManager
        from shot_model import Shot

        cache = CacheManager()

        # Pre-populate cache with test data
        test_shots = []
        for i in range(100):
            shot = Shot(
                show="ygsk",
                sequence="108",
                shot=f"{i:04d}",
                workspace_path=f"/shows/ygsk/shots/108_CHV_{i:04d}",
            )
            test_shots.append(shot)

        cache.cache_shots(test_shots)

        # Benchmark retrieval
        def retrieve_shots():
            return cache.get_cached_shots()

        metrics = performance_benchmark.benchmark(retrieve_shots)

        # Assert retrieval is fast
        assert metrics["mean_time"] < 0.05, (
            f"Cache retrieval too slow: {metrics['mean_time']:.3f}s"
        )

    def test_cache_memory_efficiency(self, performance_benchmark):
        """Test memory efficiency of cache with shot data."""
        from cache_manager import CacheManager
        from shot_model import Shot

        cache = CacheManager()

        # Create moderate number of shots with realistic data
        def populate_cache():
            shots = []
            for i in range(50):  # Reduced for realistic test
                shot = Shot(
                    show="ygsk",
                    sequence="108",
                    shot=f"{i:04d}",
                    workspace_path=f"/shows/ygsk/shots/108_CHV_{i:04d}",
                )
                shots.append(shot)
            cache.cache_shots(shots)

        metrics = performance_benchmark.benchmark_memory(populate_cache)

        # Check memory usage is reasonable for shot caching
        assert metrics["memory_delta_mb"] < 5, (
            f"Cache using too much memory: {metrics['memory_delta_mb']:.1f}MB"
        )


@pytest.mark.performance
class TestFinderPerformance:
    """Performance tests for finder components."""

    def test_plate_finder_performance(self, performance_benchmark):
        """Test raw plate finder performance."""
        from unittest.mock import patch

        from raw_plate_finder import RawPlateFinder

        # Mock all filesystem operations for consistent performance testing
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
        assert metrics["mean_time"] < 0.01, (
            f"Plate finder too slow: {metrics['mean_time']:.3f}s"
        )

    def test_threede_scene_parsing_performance(self, performance_benchmark):
        """Test 3DE scene data parsing performance."""
        from pathlib import Path

        from threede_scene_model import ThreeDEScene

        # Benchmark creating many scene objects
        def create_scenes():
            scenes = []
            for i in range(100):
                scene = ThreeDEScene(
                    show="ygsk",
                    sequence="108",
                    shot=f"{i:04d}",
                    workspace_path=f"/shows/ygsk/shots/108_CHV_{i:04d}",
                    user=f"user{i % 5}",
                    plate=f"FG{i % 3 + 1:02d}",
                    scene_path=Path(f"/path/to/scene_{i:03d}.3de"),
                )
                scenes.append(scene)
            return scenes

        metrics = performance_benchmark.benchmark(create_scenes)

        # Should handle object creation efficiently
        assert metrics["mean_time"] < 0.05, (
            f"Scene creation too slow: {metrics['mean_time']:.3f}s"
        )

    def test_scene_deduplication_performance(self, performance_benchmark):
        """Test performance of 3DE scene deduplication logic."""
        from collections import defaultdict
        from pathlib import Path

        from threede_scene_model import ThreeDEScene

        # Create many duplicate scenes
        all_scenes = []
        for i in range(50):  # Reduced for reasonable test time
            for j in range(3):  # 3 duplicates each
                scene = ThreeDEScene(
                    show="ygsk",
                    sequence="108",
                    shot=f"{i:04d}",
                    workspace_path=f"/shows/ygsk/shots/108_CHV_{i:04d}",
                    user=f"user{j}",
                    plate=f"FG{j + 1:02d}",
                    scene_path=Path(f"/path/user{j}/scene_{i:03d}.3de"),
                )
                all_scenes.append(scene)

        def deduplicate_scenes():
            # Simple deduplication logic similar to what's used in the app
            shot_scenes = defaultdict(list)
            for scene in all_scenes:
                shot_scenes[scene.full_name].append(scene)

            # Keep only one scene per shot (latest modified)
            deduplicated = []
            for scenes_for_shot in shot_scenes.values():
                # Sort by scene_path modification time (simulated)
                latest = max(scenes_for_shot, key=lambda s: hash(str(s.scene_path)))
                deduplicated.append(latest)

            return deduplicated

        metrics = performance_benchmark.benchmark(deduplicate_scenes)

        # Should handle deduplication efficiently
        assert metrics["mean_time"] < 0.1, (
            f"Deduplication too slow: {metrics['mean_time']:.3f}s"
        )


@pytest.mark.performance
class TestUIPerformance:
    """Performance tests for UI components."""

    def test_shot_grid_creation_performance(self, qtbot, performance_benchmark):
        """Test shot grid creation performance."""
        from shot_grid import ShotGrid
        from shot_model import Shot, ShotModel

        # Create a shot model with test data
        model = ShotModel(load_cache=False)
        test_shots = []
        for i in range(20):  # Reduced for UI test performance
            shot = Shot(
                show="ygsk",
                sequence="108",
                shot=f"{i:04d}",
                workspace_path=f"/shows/ygsk/shots/108_CHV_{i:04d}",
            )
            test_shots.append(shot)
        model.shots = test_shots

        def create_grid():
            grid = ShotGrid(model)
            qtbot.addWidget(grid)
            return grid

        metrics = performance_benchmark.benchmark(create_grid)

        # Should create UI efficiently
        assert metrics["mean_time"] < 0.5, (
            f"Grid creation too slow: {metrics['mean_time']:.3f}s"
        )

    def test_thumbnail_widget_creation_performance(self, qtbot, performance_benchmark):
        """Test thumbnail widget creation performance."""
        from shot_model import Shot
        from thumbnail_widget import ThumbnailWidget

        # Create test shot
        test_shot = Shot(
            show="ygsk",
            sequence="108",
            shot="0001",
            workspace_path="/shows/ygsk/shots/108_CHV_0001",
        )

        def create_thumbnails():
            widgets = []
            for i in range(10):  # Reduced for reasonable test time
                widget = ThumbnailWidget(test_shot, size=150)
                qtbot.addWidget(widget)
                widgets.append(widget)
            return widgets

        # Mock image loading to focus on widget creation performance
        from unittest.mock import MagicMock, patch

        with patch("PySide6.QtGui.QPixmap.load", return_value=True):
            with patch("PySide6.QtGui.QPixmap.scaled") as mock_scaled:
                mock_pixmap = MagicMock()
                mock_scaled.return_value = mock_pixmap

                metrics = performance_benchmark.benchmark(create_thumbnails)

        # Should handle widget creation efficiently
        assert metrics["mean_time"] < 0.3, (
            f"Thumbnail creation too slow: {metrics['mean_time']:.3f}s"
        )


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
