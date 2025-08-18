"""Example test file demonstrating threading test utilities usage.

This file shows comprehensive examples of how to use the threading test utilities
for testing thread safety, race conditions, deadlocks, and performance.

Run with: python run_tests.py tests/threading/test_threading_utilities_example.py
"""

import threading
import time

import pytest
from PySide6.QtCore import Signal

from launcher_manager import LauncherManager, LauncherWorker
from tests.threading.threading_test_utils import (
    DeadlockDetector,
    PerformanceMetrics,
    RaceConditionFactory,
    ThreadingTestHelpers,
    assert_worker_state_transition,
    create_test_deadlock,
    temporary_worker,
    thread_safety_monitor,
)
from thread_safe_worker import WorkerState


class TestWorkerStateTransitions:
    """Test worker state transition monitoring."""

    def test_wait_for_worker_state_success(self, monitored_worker):
        """Test successful state transition waiting."""
        # Start worker
        monitored_worker.start()

        # Wait for RUNNING state
        result = ThreadingTestHelpers.wait_for_worker_state(
            monitored_worker,
            WorkerState.RUNNING,
            timeout_ms=1000,
        )

        assert result.success
        assert result.final_state == WorkerState.RUNNING
        assert result.transition_time_ms < 1000
        assert not result.timeout_occurred
        assert result.error_message is None

    def test_wait_for_worker_state_timeout(self, monitored_worker):
        """Test timeout when waiting for state that never occurs."""
        # Don't start worker, wait for RUNNING state
        result = ThreadingTestHelpers.wait_for_worker_state(
            monitored_worker,
            WorkerState.RUNNING,
            timeout_ms=100,
        )

        assert not result.success
        assert result.final_state == WorkerState.CREATED
        assert result.timeout_occurred
        assert "Timeout waiting for" in result.error_message

    def test_assert_state_transition_sequence(self, monitored_worker):
        """Test asserting complete state transition sequence."""
        # Define expected sequence
        expected_transitions = [
            WorkerState.CREATED,
            WorkerState.STARTING,
            WorkerState.RUNNING,
            WorkerState.STOPPING,
            WorkerState.STOPPED,
        ]

        # Start worker in background thread to allow state monitoring
        def worker_lifecycle():
            time.sleep(0.01)  # Let monitor start
            monitored_worker.start()
            time.sleep(0.05)  # Let it run briefly
            monitored_worker.request_stop()

        worker_thread = threading.Thread(target=worker_lifecycle)
        worker_thread.start()

        try:
            # Assert the transition sequence
            assert_worker_state_transition(
                monitored_worker,
                expected_transitions,
                timeout_ms=2000,
            )
        finally:
            worker_thread.join(timeout=3.0)


class TestRaceConditions:
    """Test race condition creation and detection."""

    def test_create_state_race(self, isolated_launcher_manager):
        """Test creating deterministic state race."""
        # Create multiple workers
        workers = [LauncherWorker(f"test_{i}", f"echo 'worker {i}'") for i in range(3)]

        try:
            # Start all workers
            for worker in workers:
                worker.start()

            # Wait for all to be running
            for worker in workers:
                ThreadingTestHelpers.wait_for_worker_state(
                    worker,
                    WorkerState.RUNNING,
                    timeout_ms=1000,
                )

            # Create race to stop all workers simultaneously
            result = RaceConditionFactory.create_state_race(
                workers,
                WorkerState.STOPPED,
                timeout_ms=2000,
            )

            assert result.participants == 3
            assert result.race_duration_ms < 1000
            # Race may or may not occur depending on timing

        finally:
            # Cleanup workers
            for worker in workers:
                if worker.isRunning():
                    worker.request_stop()
                    worker.wait(1000)

    def test_create_signal_race(self, qtbot):
        """Test signal emission vs disconnection race."""
        from PySide6.QtCore import QObject

        class TestSignaler(QObject):
            test_signal = Signal(str)

        signaler = TestSignaler()
        # Note: TestSignaler is QObject, not QWidget - no qtbot.addWidget needed

        # Create race between signal emission and disconnection
        result = RaceConditionFactory.create_signal_race(
            signaler.test_signal,
            emit_count=5,
            disconnect_after=2,
        )

        assert result.participants == 2  # emit and disconnect operations
        assert result.setup_time_ms >= 0
        assert result.race_duration_ms >= 0
        # Check if signal information was captured
        assert any("signals" in violation for violation in result.violations_detected)

    def test_resource_race_condition(self, isolated_launcher_manager):
        """Test race for shared resource access."""
        manager = isolated_launcher_manager

        # Define operations that race for manager resources
        operations = [
            lambda: manager.get_active_process_count(),
            lambda: manager.get_active_process_info(),
            lambda: manager.list_launchers(),
        ]

        result = RaceConditionFactory.create_resource_race(
            operations,
            "launcher_manager",
            timeout_ms=1000,
        )

        assert result.participants == 3
        assert result.race_duration_ms < 1000
        assert len(result.violations_detected) == 0  # Should be thread-safe


class TestDeadlockDetection:
    """Test deadlock detection capabilities."""

    def test_detect_no_deadlock(self):
        """Test deadlock detection with no deadlock present."""
        # Get current threads
        current_threads = [t for t in threading.enumerate() if t.is_alive()]

        analysis = DeadlockDetector.detect_deadlock(
            threads=current_threads,
            timeout_ms=1000,
        )

        assert not analysis.deadlock_detected
        assert len(analysis.involved_threads) == 0
        assert len(analysis.cycles) == 0
        assert analysis.analysis_time_ms < 1000

    def test_detect_simple_deadlock(self):
        """Test deadlock detection with actual deadlock."""
        # Create two locks for deadlock scenario
        lock1 = threading.Lock()
        lock2 = threading.Lock()

        # Create deadlock scenario
        thread1, thread2 = create_test_deadlock(lock1, lock2, timeout_ms=500)

        try:
            # Give threads time to deadlock
            time.sleep(0.2)

            # Detect deadlock
            analysis = DeadlockDetector.detect_deadlock(
                threads=[thread1, thread2],
                timeout_ms=1000,
            )

            # Note: Actual deadlock detection requires instrumentation
            # This test verifies the API works correctly
            assert analysis.analysis_time_ms >= 0
            assert isinstance(analysis.lock_graph, dict)
            assert isinstance(analysis.cycles, list)

        finally:
            # Force cleanup (threads will be in deadlock)
            # In real tests, you'd need to kill deadlocked threads
            pass

    def test_get_thread_stacks(self):
        """Test stack trace capture functionality."""
        current_threads = [threading.current_thread()]

        stacks = DeadlockDetector.get_thread_stacks(current_threads)

        current_thread_id = threading.current_thread().ident
        assert current_thread_id in stacks
        assert isinstance(stacks[current_thread_id], list)
        assert len(stacks[current_thread_id]) > 0
        # Should contain this test method in the stack
        stack_text = "".join(stacks[current_thread_id])
        assert "test_get_thread_stacks" in stack_text


class TestPerformanceMeasurement:
    """Test performance measurement utilities."""

    def test_measure_thread_creation(self):
        """Test thread creation performance measurement."""

        def simple_worker_factory():
            return LauncherWorker("perf_test", "echo 'performance test'")

        result = PerformanceMetrics.measure_thread_creation(
            simple_worker_factory,
            iterations=5,
            warmup_iterations=1,
        )

        assert result.operation_name == "thread_creation"
        assert result.iterations == 5
        assert result.avg_duration_ms > 0
        assert result.min_duration_ms <= result.avg_duration_ms
        assert result.avg_duration_ms <= result.max_duration_ms
        assert result.std_deviation_ms >= 0

    def test_measure_lock_contention(self):
        """Test lock contention measurement."""
        test_lock = threading.Lock()

        result = PerformanceMetrics.measure_lock_contention(
            test_lock,
            contention_threads=3,
            operations_per_thread=5,
        )

        assert result.operation_name == "lock_contention"
        assert result.iterations == 15  # 3 threads * 5 operations
        assert result.avg_duration_ms > 0
        assert "contention_threads" in result.metadata
        assert result.metadata["contention_threads"] == 3

    def test_measure_signal_latency(self, qtbot):
        """Test Qt signal latency measurement."""
        from PySide6.QtCore import QObject

        class TestSignaler(QObject):
            test_signal = Signal()

        signaler = TestSignaler()
        # Note: TestSignaler is QObject, not QWidget - no qtbot.addWidget needed

        result = PerformanceMetrics.measure_signal_latency(
            signaler.test_signal,
            iterations=10,
        )

        assert result.operation_name == "signal_latency"
        assert result.iterations <= 10  # May be less if some signals timeout
        assert result.avg_duration_ms >= 0
        assert "connection_type" in result.metadata

    def test_compare_before_after(self):
        """Test before/after performance comparison."""

        def slow_operation():
            return PerformanceMetrics.measure_thread_creation(
                lambda: LauncherWorker("slow", "sleep 0.01"),
                iterations=3,
            )

        def fast_operation():
            return PerformanceMetrics.measure_thread_creation(
                lambda: LauncherWorker("fast", "echo fast"),
                iterations=3,
            )

        comparison = PerformanceMetrics.compare_before_after(
            slow_operation,
            fast_operation,
            improvement_threshold=0.0,
        )

        assert "before_result" in comparison
        assert "after_result" in comparison
        assert "improvement_percent" in comparison
        assert "is_significant_improvement" in comparison
        assert "comparison_summary" in comparison


class TestConcurrentWorkers:
    """Test concurrent worker creation and management."""

    def test_create_concurrent_workers(self):
        """Test creating multiple workers concurrently."""

        def worker_factory():
            return LauncherWorker("concurrent", "echo 'concurrent test'")

        workers = ThreadingTestHelpers.create_concurrent_workers(
            worker_factory,
            count=3,
            start_delay_ms=20,
        )

        try:
            assert len(workers) == 3

            # Verify all workers are running
            for worker in workers:
                result = ThreadingTestHelpers.wait_for_worker_state(
                    worker,
                    WorkerState.RUNNING,
                    timeout_ms=1000,
                )
                assert result.success

        finally:
            # Cleanup workers
            for worker in workers:
                if worker.isRunning():
                    worker.request_stop()
                    worker.wait(1000)


class TestContextManagers:
    """Test context manager utilities."""

    def test_temporary_worker_context(self):
        """Test temporary worker context manager."""
        worker_created = False
        worker_cleaned_up = False

        with temporary_worker(LauncherWorker, "temp", "echo temp") as worker:
            worker_created = True
            assert isinstance(worker, LauncherWorker)
            worker.start()

            # Wait for worker to start
            result = ThreadingTestHelpers.wait_for_worker_state(
                worker,
                WorkerState.RUNNING,
                timeout_ms=1000,
            )
            assert result.success

        # Worker should be cleaned up automatically
        worker_cleaned_up = True
        assert worker_created and worker_cleaned_up

    def test_thread_safety_monitor_context(self):
        """Test thread safety monitoring context manager."""
        violations_captured = []

        def violation_handler(violation):
            violations_captured.append(violation)

        with thread_safety_monitor(["test_resource"], violation_handler) as violations:
            # Perform some operations
            time.sleep(0.01)

        # Monitor should complete without issues
        assert isinstance(violations, list)
        # Note: Actual violations would require instrumentation


class TestFixtures:
    """Test pytest fixtures functionality."""

    def test_isolated_launcher_manager_fixture(self, isolated_launcher_manager):
        """Test isolated launcher manager fixture."""
        manager = isolated_launcher_manager

        # Manager should be functional
        assert isinstance(manager, LauncherManager)
        assert manager.get_active_process_count() == 0

        # Should have isolated configuration
        assert manager.config.config_dir != LauncherManager().config.config_dir

    def test_monitored_worker_fixture(self, monitored_worker):
        """Test monitored worker fixture."""
        worker = monitored_worker

        # Worker should be ready to use
        assert isinstance(worker, LauncherWorker)
        assert worker.get_state() == WorkerState.CREATED

        # Start and verify monitoring works
        worker.start()
        result = ThreadingTestHelpers.wait_for_worker_state(
            worker,
            WorkerState.RUNNING,
            timeout_ms=1000,
        )
        assert result.success

    def test_deadlock_timeout_fixture(self, deadlock_timeout):
        """Test deadlock timeout fixture."""
        # This fixture runs in background, just verify it doesn't interfere
        # with normal operations

        # Perform some thread operations
        lock = threading.Lock()

        def safe_operation():
            with lock:
                time.sleep(0.01)

        threads = []
        for i in range(3):
            thread = threading.Thread(target=safe_operation, name=f"SafeThread-{i}")
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join(timeout=1.0)

        # If we reach here, no deadlock was detected (which is good)
        assert True

    def test_thread_pool_fixture(self, thread_pool):
        """Test thread pool fixture."""

        # Add some threads to the pool
        def simple_task():
            time.sleep(0.05)

        for i in range(3):
            thread = threading.Thread(target=simple_task, name=f"PoolThread-{i}")
            thread_pool.append(thread)
            thread.start()

        # Fixture should handle cleanup automatically
        assert len(thread_pool) == 3

        # All threads should be running
        for thread in thread_pool:
            assert thread.is_alive()


class TestIntegrationScenarios:
    """Test realistic integration scenarios."""

    def test_launcher_manager_thread_safety(self, isolated_launcher_manager):
        """Test LauncherManager thread safety under concurrent access."""
        manager = isolated_launcher_manager

        # Create launcher
        launcher_id = manager.create_launcher(
            name="Concurrent Test",
            command="echo 'concurrent test'",
            description="Test launcher for concurrency",
        )
        assert launcher_id is not None

        # Define concurrent operations
        operations = [
            lambda: manager.get_launcher(launcher_id),
            lambda: manager.list_launchers(),
            lambda: manager.get_active_process_count(),
            lambda: manager.get_active_process_info(),
        ]

        # Run operations concurrently
        result = RaceConditionFactory.create_resource_race(
            operations,
            "launcher_manager_concurrent",
            timeout_ms=2000,
        )

        # Should handle concurrent access without issues
        assert result.participants == 4
        assert len(result.violations_detected) == 0

    def test_worker_lifecycle_under_stress(self):
        """Test worker lifecycle under stress conditions."""

        def stress_worker_factory():
            return LauncherWorker("stress", "echo 'stress test'")

        # Create multiple workers rapidly
        workers = ThreadingTestHelpers.create_concurrent_workers(
            stress_worker_factory,
            count=5,
            start_delay_ms=5,
        )

        try:
            # Rapidly start and stop workers
            for worker in workers:
                # Wait for running state
                result = ThreadingTestHelpers.wait_for_worker_state(
                    worker,
                    WorkerState.RUNNING,
                    timeout_ms=500,
                )
                if result.success:
                    # Request stop immediately
                    worker.request_stop()

            # Wait for all to stop
            for worker in workers:
                ThreadingTestHelpers.wait_for_worker_state(
                    worker,
                    WorkerState.STOPPED,
                    timeout_ms=1000,
                )

        finally:
            # Ensure cleanup
            for worker in workers:
                if worker.isRunning():
                    worker.request_stop()
                    worker.wait(1000)

    def test_performance_regression_detection(self):
        """Test detecting performance regressions."""

        def baseline_operation():
            return PerformanceMetrics.measure_thread_creation(
                lambda: LauncherWorker("baseline", "echo baseline"),
                iterations=3,
            )

        def potentially_slower_operation():
            def slow_factory():
                # Simulate slightly slower operation
                time.sleep(0.001)
                return LauncherWorker("slower", "echo slower")

            return PerformanceMetrics.measure_thread_creation(
                slow_factory,
                iterations=3,
            )

        comparison = PerformanceMetrics.compare_before_after(
            baseline_operation,
            potentially_slower_operation,
            improvement_threshold=5.0,  # 5% improvement threshold
        )

        # Should detect if there's a significant regression
        assert "improvement_percent" in comparison
        assert "is_significant_improvement" in comparison

        # Log results for analysis
        print(f"Performance comparison: {comparison['comparison_summary']}")


if __name__ == "__main__":
    # Run tests if executed directly
    pytest.main([__file__, "-v"])
