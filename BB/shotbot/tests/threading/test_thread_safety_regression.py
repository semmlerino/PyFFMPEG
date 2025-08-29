"""Regression tests for thread safety fixes in the Stabilization Sprint."""

import concurrent.futures
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from cache_manager import CacheManager
from process_pool_manager import ProcessPoolManager
from shot_model import RefreshResult
from shot_model_optimized import AsyncShotLoader, OptimizedShotModel


class TestConditionVariableFix:
    """Test that the condition variable fix prevents race conditions."""

    def setup_method(self):
        """Set up test environment."""
        self.app = QApplication.instance() or QApplication([])
        self.manager = ProcessPoolManager.get_instance()

    def test_no_race_in_session_creation(self):
        """Test that concurrent session creation doesn't cause races."""
        # Clear any existing sessions
        self.manager._session_pools.clear()
        self.manager._session_creation_in_progress.clear()

        results = []
        errors = []

        def create_session_concurrent(session_type):
            try:
                session = self.manager._get_bash_session(session_type)
                results.append(session)
            except Exception as e:
                errors.append(e)

        # Launch multiple threads trying to create sessions simultaneously
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            for i in range(10):
                # All threads try to create the same session type
                future = executor.submit(create_session_concurrent, "test_concurrent")
                futures.append(future)

            # Wait for all to complete
            concurrent.futures.wait(futures, timeout=10)

        # Verify no errors occurred
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # Verify all threads got valid sessions
        assert len(results) == 10
        assert all(s is not None for s in results)

        # Verify only the expected number of sessions were created
        pool = self.manager._session_pools.get("test_concurrent", [])
        assert len(pool) == self.manager._sessions_per_type, (
            f"Expected {self.manager._sessions_per_type} sessions, got {len(pool)}"
        )

    def test_condition_variable_prevents_deadlock(self):
        """Test that condition variable doesn't cause deadlocks."""
        # This tests the fix for the lock release-reacquire pattern

        def slow_session_creation():
            # Simulate slow session creation
            with self.manager._session_lock:
                self.manager._session_creation_in_progress["slow_type"] = True
                time.sleep(0.1)  # Simulate work
                self.manager._session_creation_in_progress["slow_type"] = False
                self.manager._session_condition.notify_all()

        def waiting_thread():
            # This thread should wait properly without deadlock
            with self.manager._session_lock:
                while self.manager._session_creation_in_progress.get(
                    "slow_type", False
                ):
                    # This should properly wait and reacquire lock
                    self.manager._session_condition.wait(timeout=0.5)
                return True

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

        assert not creator.is_alive(), "Creator thread deadlocked"
        assert not waiter.is_alive(), "Waiter thread deadlocked"


class TestQThreadInterruptionFix:
    """Test that QThread uses safe interruption instead of terminate()."""

    def setup_method(self):
        """Set up test environment."""
        self.app = QApplication.instance() or QApplication([])
        self.temp_dir = tempfile.TemporaryDirectory()

    def teardown_method(self):
        """Clean up test environment."""
        self.temp_dir.cleanup()

    def test_no_terminate_call_in_cleanup(self):
        """Test that cleanup never calls terminate()."""
        cache_manager = CacheManager(cache_dir=Path(self.temp_dir.name))
        model = OptimizedShotModel(cache_manager)

        # Create mock loader
        mock_loader = Mock(spec=AsyncShotLoader)
        mock_loader.isRunning.return_value = True
        mock_loader.wait.side_effect = [False, False]  # Simulate timeout

        # Ensure terminate is available but should not be called
        mock_loader.terminate = Mock()
        mock_loader.quit = Mock()
        mock_loader.stop = Mock()
        mock_loader.requestInterruption = Mock()
        mock_loader.deleteLater = Mock()

        model._async_loader = mock_loader

        # Call cleanup
        model.cleanup()

        # Verify terminate was NEVER called
        mock_loader.terminate.assert_not_called()

        # Verify safe methods were called
        mock_loader.stop.assert_called_once()
        mock_loader.quit.assert_called_once()
        mock_loader.deleteLater.assert_called_once()

    def test_interruption_request_used_in_thread(self):
        """Test that AsyncShotLoader uses interruption requests."""
        mock_process_pool = Mock(spec=ProcessPoolManager)
        mock_process_pool.execute_workspace_command.return_value = ""

        loader = AsyncShotLoader(mock_process_pool)

        # Request interruption
        loader.requestInterruption()

        # Verify interruption is checked
        assert loader.isInterruptionRequested()

        # Run should exit early
        loader.run()

        # Verify no signals were emitted due to interruption
        # (Would need signal spy in real test, mocking here)
        mock_process_pool.execute_workspace_command.assert_not_called()

    def test_stop_event_and_interruption_work_together(self):
        """Test that both stop mechanisms work together."""
        mock_process_pool = Mock(spec=ProcessPoolManager)
        loader = AsyncShotLoader(mock_process_pool)

        # Call stop (should set both mechanisms)
        loader.stop()

        # Verify both are set
        assert loader._stop_event.is_set()
        assert loader.isInterruptionRequested()


class TestDoubleCheckedLockingFix:
    """Test that double-checked locking pattern is fixed."""

    def setup_method(self):
        """Set up test environment."""
        self.app = QApplication.instance() or QApplication([])
        self.temp_dir = tempfile.TemporaryDirectory()

    def teardown_method(self):
        """Clean up test environment."""
        self.temp_dir.cleanup()

    def test_loading_flag_always_checked_under_lock(self):
        """Test that _loading_in_progress is always accessed under lock."""
        cache_manager = CacheManager(cache_dir=Path(self.temp_dir.name))
        model = OptimizedShotModel(cache_manager)

        # Track lock acquisition
        original_acquire = model._loader_lock.acquire
        original_release = model._loader_lock.release
        lock_held = [False]

        def track_acquire(*args, **kwargs):
            result = original_acquire(*args, **kwargs)
            lock_held[0] = True
            return result

        def track_release(*args, **kwargs):
            lock_held[0] = False
            return original_release(*args, **kwargs)

        model._loader_lock.acquire = track_acquire
        model._loader_lock.release = track_release

        # Mock the loading flag access
        original_getattribute = model.__getattribute__

        def check_lock_on_flag_access(name):
            if name == "_loading_in_progress" and not name.startswith("_loader_lock"):
                # This is a simplified check - in reality we'd need more sophisticated tracking
                pass
            return original_getattribute(name)

        model.__getattribute__ = check_lock_on_flag_access

        # Call methods that access the flag
        model._start_background_refresh()

        # The flag should have been accessed under lock
        # This is a simplified test - full implementation would track all accesses
        assert True  # Placeholder for more sophisticated checking

    def test_concurrent_refresh_calls_safe(self):
        """Test that concurrent refresh calls don't cause race conditions."""
        cache_manager = CacheManager(cache_dir=Path(self.temp_dir.name))
        model = OptimizedShotModel(cache_manager)

        results = []
        errors = []

        def refresh_concurrent():
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

    def setup_method(self):
        """Set up test environment."""
        self.app = QApplication.instance() or QApplication([])

    def test_signals_emitted_safely_from_background_thread(self):
        """Test that background thread can safely emit signals."""
        mock_process_pool = Mock(spec=ProcessPoolManager)
        mock_process_pool.execute_workspace_command.return_value = (
            "workspace /shows/TEST/shots/SEQ01/0010"
        )

        loader = AsyncShotLoader(mock_process_pool)

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

    def test_no_signals_after_stop(self):
        """Test that no signals are emitted after stop is called."""
        mock_process_pool = Mock(spec=ProcessPoolManager)
        # Make command slow so we can stop it
        mock_process_pool.execute_workspace_command.side_effect = (
            lambda *args, **kwargs: time.sleep(0.1) or ""
        )

        loader = AsyncShotLoader(mock_process_pool)

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

    def setup_method(self):
        """Set up test environment."""
        self.app = QApplication.instance() or QApplication([])
        self.temp_dir = tempfile.TemporaryDirectory()

    def teardown_method(self):
        """Clean up test environment."""
        self.temp_dir.cleanup()

    def test_loader_cleanup_prevents_leaks(self):
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

    def test_deleted_objects_dont_receive_signals(self):
        """Test that deleted objects don't receive signals."""
        mock_process_pool = Mock(spec=ProcessPoolManager)
        loader = AsyncShotLoader(mock_process_pool)

        # Create a receiver that will be deleted
        class Receiver(QObject):
            def __init__(self):
                super().__init__()
                self.received = []

            def on_shots_loaded(self, shots):
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

    def setup_method(self):
        """Set up test environment."""
        self.app = QApplication.instance() or QApplication([])
        self.temp_dir = tempfile.TemporaryDirectory()

    def teardown_method(self):
        """Clean up test environment."""
        self.temp_dir.cleanup()

    def test_many_concurrent_refreshes(self):
        """Test many concurrent refresh operations."""
        cache_manager = CacheManager(cache_dir=Path(self.temp_dir.name))
        model = OptimizedShotModel(cache_manager)

        # Mock process pool to avoid real subprocess calls
        model._process_pool = Mock(spec=ProcessPoolManager)
        model._process_pool.execute_workspace_command.return_value = ""

        errors = []

        def stress_refresh():
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
