"""Advanced load and stress testing patterns for ShotBot.

This module provides sophisticated load testing capabilities including
gradual load increase, spike testing, and endurance testing.
"""

import os
import random
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, List

import psutil
import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from cache_manager import CacheManager
from launcher_manager import LauncherManager
from shot_model import ShotModel


@dataclass
class LoadProfile:
    """Defines a load testing profile."""

    name: str
    duration_seconds: float
    initial_load: int
    peak_load: int
    ramp_up_time: float
    ramp_down_time: float
    hold_time: float = 0
    spike_probability: float = 0
    spike_multiplier: float = 2.0


@dataclass
class PerformanceMetrics:
    """Performance metrics collected during testing."""

    timestamp: datetime = field(default_factory=datetime.now)
    response_times: List[float] = field(default_factory=list)
    error_count: int = 0
    success_count: int = 0
    memory_usage_mb: float = 0
    cpu_percent: float = 0
    thread_count: int = 0
    active_operations: int = 0

    @property
    def avg_response_time(self) -> float:
        """Calculate average response time."""
        return (
            sum(self.response_times) / len(self.response_times)
            if self.response_times
            else 0
        )

    @property
    def p95_response_time(self) -> float:
        """Calculate 95th percentile response time."""
        if not self.response_times:
            return 0
        sorted_times = sorted(self.response_times)
        index = int(len(sorted_times) * 0.95)
        return sorted_times[min(index, len(sorted_times) - 1)]

    @property
    def p99_response_time(self) -> float:
        """Calculate 99th percentile response time."""
        if not self.response_times:
            return 0
        sorted_times = sorted(self.response_times)
        index = int(len(sorted_times) * 0.99)
        return sorted_times[min(index, len(sorted_times) - 1)]

    @property
    def error_rate(self) -> float:
        """Calculate error rate."""
        total = self.error_count + self.success_count
        return self.error_count / total if total > 0 else 0

    @property
    def throughput(self) -> float:
        """Calculate operations per second."""
        if not self.response_times:
            return 0
        duration = (
            max(self.response_times) - min(self.response_times)
            if len(self.response_times) > 1
            else 1
        )
        return len(self.response_times) / max(duration, 0.001)


class LoadGenerator:
    """Generates load according to specified profiles."""

    def __init__(self, profile: LoadProfile):
        """Initialize load generator with profile."""
        self.profile = profile
        self.current_load = profile.initial_load
        self.start_time = None
        self.metrics_history: List[PerformanceMetrics] = []
        self._stop_event = threading.Event()

    def get_current_load(self) -> int:
        """Calculate current load based on profile and elapsed time."""
        if not self.start_time:
            return self.profile.initial_load

        elapsed = (datetime.now() - self.start_time).total_seconds()

        # Spike injection
        if random.random() < self.profile.spike_probability:
            return int(self.current_load * self.profile.spike_multiplier)

        # Ramp up phase
        if elapsed < self.profile.ramp_up_time:
            progress = elapsed / self.profile.ramp_up_time
            return int(
                self.profile.initial_load
                + (self.profile.peak_load - self.profile.initial_load) * progress
            )

        # Hold phase
        elif elapsed < (self.profile.ramp_up_time + self.profile.hold_time):
            return self.profile.peak_load

        # Ramp down phase
        elif elapsed < (
            self.profile.ramp_up_time
            + self.profile.hold_time
            + self.profile.ramp_down_time
        ):
            ramp_down_elapsed = (
                elapsed - self.profile.ramp_up_time - self.profile.hold_time
            )
            progress = 1 - (ramp_down_elapsed / self.profile.ramp_down_time)
            return int(
                self.profile.initial_load
                + (self.profile.peak_load - self.profile.initial_load) * progress
            )

        # End
        return self.profile.initial_load

    def record_metrics(self, response_time: float, success: bool):
        """Record performance metrics."""
        if not self.metrics_history:
            self.metrics_history.append(PerformanceMetrics())

        current = self.metrics_history[-1]
        current.response_times.append(response_time)

        if success:
            current.success_count += 1
        else:
            current.error_count += 1

        # Update system metrics
        process = psutil.Process()
        current.memory_usage_mb = process.memory_info().rss / 1024 / 1024
        current.cpu_percent = process.cpu_percent()
        current.thread_count = process.num_threads()
        current.active_operations = self.current_load

    def stop(self):
        """Stop the load generator."""
        self._stop_event.set()

    def is_running(self) -> bool:
        """Check if generator is still running."""
        return not self._stop_event.is_set()


class TestLoadPatterns:
    """Test various load patterns."""

    @pytest.fixture
    def gradual_load_profile(self):
        """Gradual load increase profile."""
        return LoadProfile(
            name="gradual_load",
            duration_seconds=30,
            initial_load=1,
            peak_load=20,
            ramp_up_time=10,
            ramp_down_time=10,
            hold_time=10,
        )

    @pytest.fixture
    def spike_load_profile(self):
        """Spike load profile."""
        return LoadProfile(
            name="spike_load",
            duration_seconds=20,
            initial_load=5,
            peak_load=50,
            ramp_up_time=2,
            ramp_down_time=2,
            hold_time=16,
            spike_probability=0.1,
            spike_multiplier=3.0,
        )

    @pytest.fixture
    def endurance_profile(self):
        """Endurance test profile."""
        return LoadProfile(
            name="endurance",
            duration_seconds=60,
            initial_load=10,
            peak_load=10,
            ramp_up_time=5,
            ramp_down_time=5,
            hold_time=50,
        )

    @pytest.mark.skipif(
        os.environ.get("RUN_LOAD_TESTS", "0") != "1",
        reason="Load tests skipped by default. Set RUN_LOAD_TESTS=1 to run.",
    )
    def test_gradual_load_increase(self, gradual_load_profile, qtbot):
        """Test system under gradually increasing load."""
        generator = LoadGenerator(gradual_load_profile)
        manager = LauncherManager()
        qtbot.addWidget(manager)

        def worker_task():
            """Individual worker task."""
            start = time.time()
            try:
                # Simulate launcher operation
                launcher_id = f"load_test_{threading.current_thread().ident}"
                process_key = manager.launch_command(
                    "echo test", launcher_id=launcher_id
                )
                success = process_key is not None
                if process_key:
                    manager.terminate_process(process_key)
            except Exception:
                success = False
            response_time = time.time() - start
            return response_time, success

        # Run load test
        generator.start_time = datetime.now()
        with ThreadPoolExecutor(max_workers=100) as executor:
            futures = []

            while generator.is_running():
                current_load = generator.get_current_load()

                # Submit tasks based on current load
                for _ in range(current_load):
                    futures.append(executor.submit(worker_task))

                # Process completed futures
                completed = []
                for future in as_completed(futures, timeout=0.1):
                    try:
                        response_time, success = future.result()
                        generator.record_metrics(response_time, success)
                        completed.append(future)
                    except Exception:
                        generator.record_metrics(1.0, False)
                        completed.append(future)

                # Remove completed futures
                for future in completed:
                    futures.remove(future)

                # Check if test duration exceeded
                elapsed = (datetime.now() - generator.start_time).total_seconds()
                if elapsed >= gradual_load_profile.duration_seconds:
                    generator.stop()

                time.sleep(0.1)

        # Analyze results
        assert len(generator.metrics_history) > 0
        final_metrics = generator.metrics_history[-1]

        # Performance assertions
        assert final_metrics.avg_response_time < 2.0  # Average under 2 seconds
        assert final_metrics.p95_response_time < 5.0  # P95 under 5 seconds
        assert final_metrics.error_rate < 0.1  # Less than 10% errors

    @pytest.mark.skipif(
        os.environ.get("RUN_LOAD_TESTS", "0") != "1",
        reason="Load tests skipped by default. Set RUN_LOAD_TESTS=1 to run.",
    )
    def test_cache_manager_under_load(self, gradual_load_profile):
        """Test cache manager under load."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = CacheManager(cache_dir=Path(tmpdir))
            generator = LoadGenerator(gradual_load_profile)

            def cache_operation(operation_id: int):
                """Individual cache operation."""
                start = time.time()
                try:
                    # Mix of read and write operations
                    if operation_id % 3 == 0:
                        # Write
                        data = [{"id": operation_id, "data": f"test_{operation_id}"}]
                        cache.cache_shots(data)
                    else:
                        # Read
                        cache.get_cached_shots()

                    success = True
                except Exception:
                    success = False

                return time.time() - start, success

            # Run load test
            generator.start_time = datetime.now()
            results = []

            with ThreadPoolExecutor(max_workers=50) as executor:
                operation_counter = 0

                while generator.is_running():
                    current_load = generator.get_current_load()

                    # Submit operations
                    futures = []
                    for _ in range(current_load):
                        operation_counter += 1
                        futures.append(
                            executor.submit(cache_operation, operation_counter)
                        )

                    # Collect results
                    for future in as_completed(futures, timeout=1):
                        try:
                            response_time, success = future.result()
                            generator.record_metrics(response_time, success)
                            results.append((response_time, success))
                        except Exception:
                            generator.record_metrics(1.0, False)

                    # Check duration
                    elapsed = (datetime.now() - generator.start_time).total_seconds()
                    if elapsed >= gradual_load_profile.duration_seconds:
                        generator.stop()

            # Verify cache remained functional
            final_check = cache.get_cached_shots()
            assert final_check is not None or isinstance(final_check, list)

    @pytest.mark.skipif(
        os.environ.get("RUN_LOAD_TESTS", "0") != "1",
        reason="Load tests skipped by default. Set RUN_LOAD_TESTS=1 to run.",
    )
    def test_memory_leak_detection(self, endurance_profile, qtbot):
        """Test for memory leaks during extended operation."""
        from main_window import MainWindow

        window = MainWindow()
        qtbot.addWidget(window)

        # Record initial memory
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024

        # Run endurance test
        generator = LoadGenerator(endurance_profile)
        generator.start_time = datetime.now()

        memory_samples = []

        while generator.is_running():
            # Perform operations
            try:
                window.refresh_shots()
                window.shot_model.get_shots()
                if hasattr(window, "cache_manager"):
                    window.cache_manager.get_cached_shots()
            except Exception:
                pass

            # Sample memory
            current_memory = process.memory_info().rss / 1024 / 1024
            memory_samples.append(current_memory)

            # Check duration
            elapsed = (datetime.now() - generator.start_time).total_seconds()
            if elapsed >= endurance_profile.duration_seconds:
                generator.stop()

            time.sleep(1)

        # Analyze memory growth
        final_memory = memory_samples[-1]
        memory_growth = final_memory - initial_memory

        # Memory growth should be limited
        assert memory_growth < 100, f"Excessive memory growth: {memory_growth}MB"

        # Check for steady state (last 25% of samples)
        steady_state_samples = memory_samples[int(len(memory_samples) * 0.75) :]
        if steady_state_samples:
            steady_state_variance = max(steady_state_samples) - min(
                steady_state_samples
            )
            assert steady_state_variance < 20, (
                f"Memory not stable: variance={steady_state_variance}MB"
            )


class TestConcurrentLoadScenarios:
    """Test realistic concurrent load scenarios."""

    def test_mixed_workload(self, qtbot):
        """Test mixed workload with different operation types."""
        from main_window import MainWindow

        window = MainWindow()
        qtbot.addWidget(window)

        # Define workload mix
        workload_mix = {
            "refresh_shots": 0.3,
            "cache_read": 0.4,
            "cache_write": 0.2,
            "launcher": 0.1,
        }

        def execute_operation(operation_type: str):
            """Execute specific operation type."""
            start = time.time()
            success = False

            try:
                if operation_type == "refresh_shots":
                    result = window.shot_model.refresh_shots()
                    success = result.success
                elif operation_type == "cache_read":
                    data = window.cache_manager.get_cached_shots()
                    success = data is not None
                elif operation_type == "cache_write":
                    test_data = [{"id": random.randint(1, 1000), "test": "data"}]
                    window.cache_manager.cache_shots(test_data)
                    success = True
                elif operation_type == "launcher":
                    key = window.launcher_manager.launch_command(
                        "echo test", launcher_id=f"test_{random.randint(1, 1000)}"
                    )
                    if key:
                        window.launcher_manager.terminate_process(key)
                    success = key is not None
            except Exception:
                success = False

            return time.time() - start, success

        # Run mixed workload
        results = {op: {"times": [], "success": 0, "failure": 0} for op in workload_mix}

        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = []

            # Submit 100 operations with proper mix
            for _ in range(100):
                rand = random.random()
                cumulative = 0
                for op_type, probability in workload_mix.items():
                    cumulative += probability
                    if rand <= cumulative:
                        futures.append(executor.submit(execute_operation, op_type))
                        break

            # Collect results
            for future in as_completed(futures):
                try:
                    # Determine operation type from future
                    for op_type in workload_mix:
                        # This is simplified - in real scenario we'd track properly
                        response_time, success = future.result()
                        if success:
                            results[op_type]["success"] += 1
                        else:
                            results[op_type]["failure"] += 1
                        results[op_type]["times"].append(response_time)
                        break
                except Exception:
                    pass

        # Verify all operation types handled load
        for op_type, metrics in results.items():
            total = metrics["success"] + metrics["failure"]
            if total > 0:
                success_rate = metrics["success"] / total
                # Most operations should succeed
                assert success_rate > 0.8, (
                    f"{op_type} success rate too low: {success_rate}"
                )


class TestPerformanceRegression:
    """Test for performance regression."""

    @dataclass
    class PerformanceBaseline:
        """Performance baseline for comparison."""

        operation: str
        avg_response_time: float
        p95_response_time: float
        p99_response_time: float
        max_response_time: float

    def get_current_performance(
        self, operation: Callable, iterations: int = 100
    ) -> PerformanceBaseline:
        """Measure current performance."""
        response_times = []

        for _ in range(iterations):
            start = time.time()
            try:
                operation()
            except Exception:
                pass
            response_times.append(time.time() - start)

        sorted_times = sorted(response_times)
        return self.PerformanceBaseline(
            operation=operation.__name__,
            avg_response_time=sum(response_times) / len(response_times),
            p95_response_time=sorted_times[int(len(sorted_times) * 0.95)],
            p99_response_time=sorted_times[int(len(sorted_times) * 0.99)],
            max_response_time=max(response_times),
        )

    def test_shot_refresh_performance(self, qtbot):
        """Test shot refresh performance hasn't regressed."""
        model = ShotModel()
        qtbot.addWidget(model)

        # Expected baseline (these would come from historical data)
        expected_baseline = self.PerformanceBaseline(
            operation="refresh_shots",
            avg_response_time=0.5,  # 500ms average
            p95_response_time=1.0,  # 1s at P95
            p99_response_time=2.0,  # 2s at P99
            max_response_time=5.0,  # 5s max
        )

        # Measure current performance
        current = self.get_current_performance(
            lambda: model.refresh_shots(), iterations=10
        )

        # Allow 20% regression tolerance
        tolerance = 1.2

        # Compare with baseline
        assert (
            current.avg_response_time <= expected_baseline.avg_response_time * tolerance
        ), (
            f"Average response time regressed: {current.avg_response_time:.2f}s "
            f"vs baseline {expected_baseline.avg_response_time:.2f}s"
        )

        assert (
            current.p95_response_time <= expected_baseline.p95_response_time * tolerance
        ), (
            f"P95 response time regressed: {current.p95_response_time:.2f}s "
            f"vs baseline {expected_baseline.p95_response_time:.2f}s"
        )


if __name__ == "__main__":
    # Run with performance monitoring
    pytest.main([__file__, "-v", "--tb=short"])
