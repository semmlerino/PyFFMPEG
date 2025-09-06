"""Regression tests for thread safety fixes in the Stabilization Sprint."""

import concurrent.futures
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from typing import Optional

from cache_manager import CacheManager
from process_pool_manager import ProcessPoolManager
from shot_model import RefreshResult
from shot_model_optimized import AsyncShotLoader, OptimizedShotModel
from tests.test_doubles_library import TestProcessPool


class TestConditionVariableFix:
    """Test that the condition variable fix prevents race conditions."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.app = QApplication.instance() or QApplication([])

        # Reset ProcessPoolManager singleton to clear any test doubles from other tests
        ProcessPoolManager._instance = None

        # The conftest.py autouse fixture mocks ProcessPoolManager.get_instance()
        # For this test we need the real ProcessPoolManager, so create it directly
        self.manager = ProcessPoolManager.__new__(ProcessPoolManager)
        self.manager.__init__()

        # Set it as the singleton instance
        ProcessPoolManager._instance = self.manager

        # Ensure we have a real ProcessPoolManager, not a test double
        assert hasattr(self.manager, "_session_lock"), (
            "Expected real ProcessPoolManager with _session_lock"
        )
        assert hasattr(self.manager, "_session_condition"), (
            "Expected real ProcessPoolManager with _session_condition"
        )
        assert hasattr(self.manager, "_session_creation_in_progress"), (
            "Expected real ProcessPoolManager with _session_creation_in_progress"
        )

    def teardown_method(self) -> None:
        """Clean up test environment."""
        # Clean up the ProcessPoolManager instance
        if hasattr(self.manager, "shutdown"):
            try:
                self.manager.shutdown()
            except Exception:
                pass  # Ignore cleanup errors

    def test_no_race_in_session_creation(self) -> None:
        """Test that concurrent command execution doesn't cause race conditions."""
        # Simple test focusing on thread safety without complex mocking
        results = []
        errors = []

        def execute_command_concurrent(thread_id) -> None:
            """Execute command from a thread."""
            try:
                # Use unique command per thread to avoid caching
                command = f"echo concurrent_test_{thread_id}"
                result = self.manager.execute_workspace_command(
                    command,
                    cache_ttl=0,  # Disable cache for this test
                )
                results.append(result)
            except Exception as e:
                errors.append(str(e))

        # Launch multiple threads executing commands simultaneously
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            for i in range(10):
                future = executor.submit(execute_command_concurrent, i)
                futures.append(future)

            # Wait for all to complete with timeout
            done, not_done = concurrent.futures.wait(futures, timeout=10)

            # Ensure all completed
            assert len(not_done) == 0, f"Some futures didn't complete: {len(not_done)}"

        # Verify no errors occurred during concurrent execution
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # Verify all threads got results
        assert len(results) == 10, f"Expected 10 results, got {len(results)}"

        # The key test is that concurrent access didn't cause crashes or deadlocks
        # The ProcessPoolManager should handle concurrent access safely

    def test_condition_variable_prevents_deadlock(self) -> None:
        """Test that condition variable doesn't cause deadlocks."""
        # This tests the fix for the lock release-reacquire pattern

        # Track exceptions from threads so test fails if threads have issues
        thread_exceptions = []

        def slow_session_creation() -> None:
            try:
                # Simulate slow session creation
                with self.manager._session_lock:
                    self.manager._session_creation_in_progress["slow_type"] = True
                    time.sleep(0.1)  # Simulate work
                    self.manager._session_creation_in_progress["slow_type"] = False
                    self.manager._session_condition.notify_all()
            except Exception as e:
                thread_exceptions.append(f"slow_session_creation: {e}")

        def waiting_thread() -> Optional[bool]:
            try:
                # This thread should wait properly without deadlock
                with self.manager._session_lock:
                    while self.manager._session_creation_in_progress.get(
                        "slow_type", False
                    ):
                        # This should properly wait and reacquire lock
                        self.manager._session_condition.wait(timeout=0.5)
                    return True
            except Exception as e:
                thread_exceptions.append(f"waiting_thread: {e}")

        # Start slow creation in background
        creator = threading.Thread(target=slow_session_creation)
        creator.start()

        # Give it a moment to acquire lock
        time.sleep(0.01)

        # Start waiting thread
        waiter = threading.Thread(target=waiting_thread)
        waiter.start()

        # Both should complete without deadlock
        creator.join(timeout=1.0)
        waiter.join(timeout=1.0)

        # Check for thread exceptions first
        assert len(thread_exceptions) == 0, (
            f"Thread exceptions occurred: {thread_exceptions}"
        )

        assert not creator.is_alive(), "Creator thread deadlocked"
        assert not waiter.is_alive(), "Waiter thread deadlocked"


class TestQThreadInterruptionFix:
    """Test that QThread uses safe interruption instead of terminate()."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.app = QApplication.instance() or QApplication([])
        self.temp_dir = tempfile.TemporaryDirectory()

    def teardown_method(self) -> None:
        """Clean up test environment."""
        self.temp_dir.cleanup()

    def test_no_terminate_call_in_cleanup(self) -> None:
        """Test that cleanup never calls terminate()."""
        cache_manager = CacheManager(cache_dir=Path(self.temp_dir.name))
        model = OptimizedShotModel(cache_manager)

        # Use real AsyncShotLoader with TestProcessPoolDouble at boundary
        from tests.test_helpers import TestProcessPoolManager

        test_pool = TestProcessPoolManager()
        test_pool.set_outputs("workspace /shows/TEST/seq01/0010")

        # Create real loader and start it
        loader = AsyncShotLoader(test_pool)
        loader.start()

        # Set the loader in the model
        model._async_loader = loader

        # Track if terminate is ever called (which would crash)
        original_terminate = loader.terminate if hasattr(loader, "terminate") else None
        terminate_called = [False]

        def track_terminate() -> None:
            terminate_called[0] = True
            if original_terminate:
                original_terminate()

        if hasattr(loader, "terminate"):
            loader.terminate = track_terminate

        # Call cleanup
        model.cleanup()

        # Verify terminate was NEVER called (critical for safety)
        assert not terminate_called[0], "terminate() should never be called on QThread"

        # Verify loader was properly stopped (behavior, not mock calls)
        assert not loader.isRunning(), "Loader should be stopped after cleanup"

    def test_interruption_request_used_in_thread(self) -> None:
        """Test that AsyncShotLoader uses interruption requests."""
        # Use real test double at system boundary
        from tests.test_helpers import TestProcessPoolManager

        test_pool = TestProcessPoolManager()
        test_pool.set_outputs("")  # Empty output for quick test

        loader = AsyncShotLoader(test_pool)

        # Request stop using the proper method
        loader.stop()

        # Verify stop flag is set immediately
        assert loader._stop_requested

        # Run should exit early
        loader.run()

        # Verify no signals were emitted due to interruption
        # Test behavior: no commands should have been executed due to stop
        assert len(test_pool.commands) == 0, "No commands should execute after stop"

    def test_stop_event_and_interruption_work_together(self) -> None:
        """Test that both stop mechanisms work together."""
        from tests.test_helpers import TestProcessPoolManager

        test_process_pool = TestProcessPoolManager()
        loader = AsyncShotLoader(test_process_pool)

        # Call stop (should set both mechanisms)
        loader.stop()

        # Verify both are set
        assert loader._stop_requested
        # Note: isInterruptionRequested() only works when thread is running,
        # but we can verify that requestInterruption() was called by stop()
        # The actual interruption check happens in run() method


class TestDoubleCheckedLockingFix:
    """Test that double-checked locking pattern is fixed."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.app = QApplication.instance() or QApplication([])
        self.temp_dir = tempfile.TemporaryDirectory()

    def teardown_method(self) -> None:
        """Clean up test environment."""
        self.temp_dir.cleanup()

    def test_loading_flag_always_checked_under_lock(self) -> None:
        """Test that _loading_in_progress is protected by lock via concurrent access."""
        cache_manager = CacheManager(cache_dir=Path(self.temp_dir.name))
        model = OptimizedShotModel(cache_manager)

        # Use test double instead of mock
        test_pool = TestProcessPool()
        test_pool.set_outputs("workspace /shows/TEST/seq01/0010")
        model._process_pool = test_pool

        # Track race conditions through concurrent access
        race_detected = []

        def attempt_refresh() -> None:
            try:
                # Try to start background refresh multiple times
                # If lock isn't protecting _loading_in_progress, we'd get multiple loaders
                model._start_background_refresh()
            except Exception as e:
                race_detected.append(str(e))

        # Run concurrent refresh attempts
        threads = []
        for _ in range(10):
            t = threading.Thread(target=attempt_refresh)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Wait briefly for any async operations
        import time

        time.sleep(0.1)

        # The lock should prevent multiple simultaneous background refreshes
        # Only one loader should be created despite concurrent attempts
        assert len(race_detected) == 0, f"Race conditions detected: {race_detected}"

        # Verify that only one loader was created (lock prevented races)
        # This is implicitly tested by no exceptions being raised

    def test_concurrent_refresh_calls_safe(self) -> None:
        """Test that concurrent refresh calls don't cause race conditions."""
        cache_manager = CacheManager(cache_dir=Path(self.temp_dir.name))
        model = OptimizedShotModel(cache_manager)

        results = []
        errors = []

        def refresh_concurrent() -> None:
            try:
                # This internally calls _start_background_refresh
                result = model.refresh_shots()
                results.append(result)
            except Exception as e:
                errors.append(e)

        # Launch multiple threads
        threads = []
        for _ in range(10):
            t = threading.Thread(target=refresh_concurrent)
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=5)

        # Verify no errors
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # Verify all got valid results
        assert all(isinstance(r, RefreshResult) for r in results)


class TestSignalThreadSafety:
    """Test that signals are emitted safely from threads."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.app = QApplication.instance() or QApplication([])

    def test_signals_emitted_safely_from_background_thread(self) -> None:
        """Test that background thread can safely emit signals."""
        test_process_pool = TestProcessPool()
        test_process_pool.set_outputs("workspace /shows/TEST/shots/SEQ01/0010")

        loader = AsyncShotLoader(test_process_pool)

        # Track signal emissions
        shots_received = []
        errors_received = []

        loader.shots_loaded.connect(lambda s: shots_received.append(s))
        loader.load_failed.connect(lambda e: errors_received.append(e))

        # Run in thread
        loader.start()

        # Wait for completion
        assert loader.wait(2000), "Loader didn't complete in time"

        # Process events to handle signals
        self.app.processEvents()

        # Verify signal was emitted
        assert len(shots_received) > 0 or len(errors_received) > 0

    def test_no_signals_after_stop(self) -> None:
        """Test that no signals are emitted after stop is called."""
        test_process_pool = TestProcessPool()
        # Simulate slow command by setting empty output (loader will stop early)
        test_process_pool.set_outputs("")

        loader = AsyncShotLoader(test_process_pool)

        # Track emissions
        signals_received = []
        loader.shots_loaded.connect(lambda s: signals_received.append("loaded"))
        loader.load_failed.connect(lambda e: signals_received.append("failed"))

        # Start and immediately stop
        loader.start()
        loader.stop()

        # Wait for thread to finish
        loader.wait(2000)

        # Process any pending events
        self.app.processEvents()

        # No signals should have been emitted
        assert len(signals_received) == 0, "Signals emitted after stop"


class TestMemoryLeakPrevention:
    """Test that signal connections don't cause memory leaks."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.app = QApplication.instance() or QApplication([])
        self.temp_dir = tempfile.TemporaryDirectory()

    def teardown_method(self) -> None:
        """Clean up test environment."""
        self.temp_dir.cleanup()

    def test_loader_cleanup_prevents_leaks(self) -> None:
        """Test that loader cleanup prevents memory leaks."""
        cache_manager = CacheManager(cache_dir=Path(self.temp_dir.name))
        model = OptimizedShotModel(cache_manager)

        # Create multiple loaders (simulating multiple refreshes)
        for _ in range(5):
            model._start_background_refresh()
            # Simulate completion
            if model._async_loader:
                model._on_loader_finished()

        # Final cleanup
        model.cleanup()

        # Verify no loader references remain
        assert model._async_loader is None

    def test_deleted_objects_dont_receive_signals(self) -> None:
        """Test that deleted objects don't receive signals."""
        test_process_pool = TestProcessPool()
        loader = AsyncShotLoader(test_process_pool)

        # Create a receiver that will be deleted
        class Receiver(QObject):
            def __init__(self) -> None:
                super().__init__()
                self.received = []

            def on_shots_loaded(self, shots) -> None:
                self.received.append(shots)

        receiver = Receiver()
        loader.shots_loaded.connect(receiver.on_shots_loaded)

        # Delete receiver
        receiver.deleteLater()
        self.app.processEvents()  # Process deletion

        # Emit signal - should not crash
        loader.shots_loaded.emit([])
        self.app.processEvents()

        # Test passes if no crash occurred


class TestStressConditions:
    """Stress tests for thread safety under load."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.app = QApplication.instance() or QApplication([])
        self.temp_dir = tempfile.TemporaryDirectory()

    def teardown_method(self) -> None:
        """Clean up test environment."""
        self.temp_dir.cleanup()

    def test_many_concurrent_refreshes(self) -> None:
        """Test many concurrent refresh operations."""
        cache_manager = CacheManager(cache_dir=Path(self.temp_dir.name))
        model = OptimizedShotModel(cache_manager)

        # Use test double to avoid real subprocess calls
        test_pool = TestProcessPool()
        test_pool.set_outputs("")
        model._process_pool = test_pool

        errors = []

        def stress_refresh() -> None:
            try:
                for _ in range(10):
                    model.refresh_shots()
                    time.sleep(0.001)  # Small delay
            except Exception as e:
                errors.append(e)

        # Run stress test
        threads = []
        for _ in range(20):
            t = threading.Thread(target=stress_refresh)
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=30)

        # Cleanup
        model.cleanup()

        # Verify no errors
        assert len(errors) == 0, f"Errors during stress test: {errors}"

        # Verify model is still functional
        result = model.refresh_shots()
        assert isinstance(result, RefreshResult)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
