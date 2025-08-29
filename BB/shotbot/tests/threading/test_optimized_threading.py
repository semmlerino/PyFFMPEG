"""Thread safety tests for OptimizedShotModel.

This test suite validates thread safety guarantees and ensures no race conditions
or deadlocks exist in the optimized implementation.
"""

from __future__ import annotations

import concurrent.futures
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest
from PySide6.QtWidgets import QApplication

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from cache_manager import CacheManager
from persistent_bash_session import PersistentBashSession
from process_pool_manager import ProcessPoolManager
from shot_model import RefreshResult, Shot
from shot_model_optimized import AsyncShotLoader, OptimizedShotModel


class TestAsyncShotLoaderThreadSafety:
    """Test thread safety of AsyncShotLoader."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.app = QApplication.instance() or QApplication([])
        self.mock_process_pool = Mock(spec=ProcessPoolManager)
        self.mock_process_pool.execute_workspace_command.return_value = """workspace /shows/TEST/seq01/0010
workspace /shows/TEST/seq01/0020
workspace /shows/TEST/seq02/0030"""

    def test_stop_event_thread_safety(self) -> None:
        """Test that stop event is thread-safe."""
        loader = AsyncShotLoader(self.mock_process_pool)

        # Start multiple threads trying to stop
        def attempt_stop() -> None:
            loader.stop()

        threads = [threading.Thread(target=attempt_stop) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Verify stop event is set
        assert loader._stop_event.is_set()  # pyright: ignore[reportPrivateUsage]

    def test_no_signal_emission_after_stop(self) -> None:
        """Test that signals are not emitted after stop is called."""
        loader = AsyncShotLoader(self.mock_process_pool)

        signals_received: list[str] = []

        # Connect signals with proper typing
        def on_shots_loaded(shots: Any) -> None:
            signals_received.append("loaded")

        def on_load_failed(error: Any) -> None:
            signals_received.append("failed")

        loader.shots_loaded.connect(on_shots_loaded)
        loader.load_failed.connect(on_load_failed)

        # Stop before starting
        loader.stop()

        # Run should exit early without emitting signals
        loader.run()

        assert len(signals_received) == 0, "No signals should be emitted after stop"

    def test_concurrent_stop_during_execution(self) -> None:
        """Test stopping loader while it's executing."""

        # Make execute_workspace_command slow
        def slow_command(*args: Any, **kwargs: Any) -> str:
            time.sleep(0.1)  # Simulate slow command
            return "workspace /shows/TEST/seq01/0010"

        self.mock_process_pool.execute_workspace_command = slow_command
        loader = AsyncShotLoader(self.mock_process_pool)

        # Start loader in thread
        loader.start()

        # Try to stop from multiple threads while running
        def attempt_stop() -> None:
            time.sleep(0.01)  # Let it start
            loader.stop()

        threads = [threading.Thread(target=attempt_stop) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Wait for loader to finish
        assert loader.wait(1000), "Loader should stop within 1 second"
        assert loader._stop_event.is_set()  # pyright: ignore[reportPrivateUsage]


class TestOptimizedShotModelThreadSafety:
    """Test thread safety of OptimizedShotModel."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.app = QApplication.instance() or QApplication([])
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_manager = CacheManager(cache_dir=Path(self.temp_dir.name))
        self.model = OptimizedShotModel(self.cache_manager)

    def teardown_method(self) -> None:
        """Clean up resources."""
        self.model.cleanup()
        self.temp_dir.cleanup()

    def test_concurrent_background_refresh(self) -> None:
        """Test that concurrent calls to _start_background_refresh are safe."""
        called_count = [0]

        def mock_start(*args: Any, **kwargs: Any) -> None:
            called_count[0] += 1

        # Temporarily replace start method
        with patch.object(AsyncShotLoader, "start", mock_start):
            # Try to start refresh from multiple threads
            def attempt_refresh() -> None:
                self.model._start_background_refresh()  # pyright: ignore[reportPrivateUsage]

            threads = [threading.Thread(target=attempt_refresh) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # Only one loader should be created due to lock protection
            assert called_count[0] == 1, "Only one loader should be created"

    def test_cleanup_during_active_loading(self) -> None:
        """Test cleanup while background loading is active."""
        # Mock slow loading
        with patch.object(AsyncShotLoader, "run") as mock_run:

            def slow_run(self: Any) -> None:
                time.sleep(0.5)

            mock_run.side_effect = slow_run

            # Start background load
            self.model.initialize_async()

            # Give it time to start
            time.sleep(0.01)

            # Cleanup should handle running thread
            start_time = time.time()
            self.model.cleanup()
            cleanup_time = time.time() - start_time

            # Should wait up to 2 seconds, then terminate
            assert cleanup_time < 3, "Cleanup should not take more than 3 seconds"
            assert self.model._async_loader is None, "Loader should be cleaned up"  # pyright: ignore[reportPrivateUsage]

    def test_race_condition_protection_in_refresh(self) -> None:
        """Test that rapid refresh calls don't cause race conditions."""
        refresh_count = [0]

        def count_refresh(*args: Any, **kwargs: Any) -> RefreshResult:
            refresh_count[0] += 1
            return RefreshResult(success=True, has_changes=False)

        # Mock the parent refresh_shots
        with patch.object(Shot, "refresh_shots", count_refresh):
            # Rapid concurrent refreshes
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(self.model.refresh_shots) for _ in range(20)]
                results = [f.result() for f in futures]

            # All should succeed
            assert all(r.success for r in results), "All refreshes should succeed"


class TestProcessPoolManagerSingleton:
    """Test thread safety of ProcessPoolManager singleton."""

    def test_singleton_thread_safety(self) -> None:
        """Test that only one instance is created in concurrent access."""
        instances: list[int] = []

        def create_instance() -> None:
            instance = ProcessPoolManager.get_instance()
            instances.append(id(instance))

        # Create instances from multiple threads
        threads = [threading.Thread(target=create_instance) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All instances should have the same id
        assert len(set(instances)) == 1, "Should only create one singleton instance"

    def test_session_pool_creation_race(self) -> None:
        """Test that session pool creation is thread-safe."""
        manager = ProcessPoolManager.get_instance()

        # Mock session creation to detect races
        creation_count = [0]
        original_init = PersistentBashSession.__init__

        def counting_init(self: Any, *args: Any, **kwargs: Any) -> None:
            creation_count[0] += 1
            original_init(self, *args, **kwargs)

        with patch.object(PersistentBashSession, "__init__", counting_init):
            # Multiple threads trying to get sessions of same type
            def get_session() -> Any:  # PersistentBashSession
                # Access private method for testing - this tests internal behavior
                return getattr(manager, "_get_bash_session")("test_type")  # pyright: ignore[reportUnknownMemberType]

            # Get expected session count for validation
            expected = getattr(manager, "_sessions_per_type", 2)  # pyright: ignore[reportUnknownMemberType]
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(get_session) for _ in range(10)]
                sessions = [f.result() for f in futures]

            # Verify all sessions were created successfully
            assert all(session is not None for session in sessions), "All sessions should be created"
            # Verify session pooling - all sessions should be the same instances
            assert len(set(id(s) for s in sessions)) <= expected, f"Should have at most {expected} unique session instances"

            # Should create exactly sessions_per_type sessions
            assert creation_count[0] == expected, (
                f"Should create exactly {expected} sessions"
            )


class TestDeadlockDetection:
    """Test for potential deadlocks."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.app = QApplication.instance() or QApplication([])

    def test_no_deadlock_in_cleanup(self) -> None:
        """Test that cleanup doesn't deadlock with running operations."""
        temp_dir = tempfile.TemporaryDirectory()
        cache_manager = CacheManager(cache_dir=Path(temp_dir.name))

        # Create multiple models
        models = [OptimizedShotModel(cache_manager) for _ in range(5)]

        # Start background operations on all
        for model in models:
            model.initialize_async()

        # Cleanup all concurrently
        def cleanup_model(model: OptimizedShotModel) -> None:
            model.cleanup()

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(cleanup_model, m) for m in models]
            # Should complete without deadlock (timeout would indicate deadlock)
            for future in concurrent.futures.as_completed(futures, timeout=5):
                future.result()  # Will raise TimeoutError if deadlocked

        temp_dir.cleanup()

    def test_signal_emission_no_deadlock(self) -> None:
        """Test that signal emission doesn't cause deadlock."""
        temp_dir = tempfile.TemporaryDirectory()
        cache_manager = CacheManager(cache_dir=Path(temp_dir.name))
        model = OptimizedShotModel(cache_manager)

        lock = threading.Lock()
        deadlock_detected = [False]

        def slot_with_lock(shots: list[Any]) -> None:
            # Try to acquire lock in slot
            if not lock.acquire(timeout=0.1):
                deadlock_detected[0] = True
            else:
                lock.release()

        model.shots_loaded.connect(slot_with_lock)

        # Hold lock while triggering signal
        with lock:
            # This should not deadlock as signals are queued
            model.shots_loaded.emit([])
            # Process events to trigger slot
            self.app.processEvents()

        assert not deadlock_detected[0], "Signal emission should not cause deadlock"

        model.cleanup()
        temp_dir.cleanup()


class TestStressAndPerformance:
    """Stress tests for thread safety under load."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.app = QApplication.instance() or QApplication([])

    def test_stress_concurrent_operations(self) -> None:
        """Stress test with many concurrent operations."""
        temp_dir = tempfile.TemporaryDirectory()
        cache_manager = CacheManager(cache_dir=Path(temp_dir.name))
        model = OptimizedShotModel(cache_manager)

        operation_count = [0]
        error_count = [0]
        lock = threading.Lock()

        def perform_operation(op_type: int) -> None:
            try:
                if op_type == 0:
                    model.initialize_async()
                elif op_type == 1:
                    model.refresh_shots()
                elif op_type == 2:
                    model.pre_warm_sessions()
                elif op_type == 3:
                    model.get_performance_metrics()

                with lock:
                    operation_count[0] += 1
            except Exception as e:
                with lock:
                    error_count[0] += 1
                    print(f"Error in operation {op_type}: {e}")

        # Run many operations concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(perform_operation, i % 4) for i in range(100)]
            concurrent.futures.wait(futures, timeout=10)

        model.cleanup()
        temp_dir.cleanup()

        assert error_count[0] == 0, f"Had {error_count[0]} errors during stress test"
        assert operation_count[0] == 100, "All operations should complete"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])
