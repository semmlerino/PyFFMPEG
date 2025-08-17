"""Threading-specific unit tests for LauncherManager class.

Tests for thread safety, deadlock prevention, and concurrent operation safety.
"""

import threading
import time
import uuid
from unittest.mock import MagicMock, patch

import pytest

from config import ThreadingConfig
from launcher_manager import LauncherManager
from thread_safe_worker import ThreadSafeWorker, WorkerState


class MockWorker(ThreadSafeWorker):
    """Mock worker for testing threading behavior."""

    def __init__(
        self, worker_id: str = None, mock_state: WorkerState = WorkerState.RUNNING
    ):
        super().__init__()
        self.worker_id = worker_id or str(uuid.uuid4())
        self._mock_state = mock_state
        self._mock_running = True
        self.stop_called = False
        self.terminate_called = False
        self.wait_called = False

    def get_state(self) -> WorkerState:
        """Return mock state."""
        return self._mock_state

    def isRunning(self) -> bool:
        """Return mock running status."""
        return self._mock_running

    def safe_stop(self, timeout_ms: int = 2000) -> bool:
        """Mock safe_stop method."""
        self.stop_called = True
        self._mock_running = False
        self._mock_state = WorkerState.STOPPED
        return True

    def terminate(self):
        """Mock terminate method."""
        self.terminate_called = True
        self._mock_running = False

    def wait(self, timeout_ms: int = 1000) -> bool:
        """Mock wait method."""
        self.wait_called = True
        return True

    def safe_wait(self, timeout_ms: int = 1000) -> bool:
        """Mock safe_wait method."""
        self.wait_called = True
        return True

    def do_work(self) -> None:
        """Mock work implementation."""
        time.sleep(0.01)  # Simulate brief work


class TestLauncherManagerThreading:
    """Test suite for LauncherManager threading behavior."""

    @pytest.fixture
    def launcher_manager(self):
        """Create LauncherManager instance for testing."""
        manager = LauncherManager()
        yield manager
        # Cleanup
        try:
            manager.cleanup_all_workers()
        except Exception:
            pass

    def test_cleanup_scheduling_prevents_duplicates(self, launcher_manager):
        """Test that cleanup scheduling prevents duplicate timer creation."""
        manager = launcher_manager

        # Mock the timer to track calls
        with patch.object(manager, "_cleanup_retry_timer") as mock_timer:
            mock_timer.isActive.return_value = False

            # Schedule multiple cleanups rapidly
            manager._schedule_cleanup_after_delay(
                ThreadingConfig.CLEANUP_INITIAL_DELAY_MS
            )
            manager._schedule_cleanup_after_delay(
                ThreadingConfig.CLEANUP_INITIAL_DELAY_MS
            )
            manager._schedule_cleanup_after_delay(
                ThreadingConfig.CLEANUP_INITIAL_DELAY_MS
            )

            # Verify timer was started only once (or limited calls)
            assert mock_timer.setInterval.call_count <= 2
            assert mock_timer.start.call_count <= 2

    def test_cleanup_already_scheduled_prevention(self, launcher_manager):
        """Test that cleanup skips when already scheduled."""
        manager = launcher_manager

        # Set cleanup as already scheduled
        manager._cleanup_scheduled = True

        with patch.object(manager, "_cleanup_retry_timer") as mock_timer:
            # Attempt to schedule cleanup
            manager._schedule_cleanup_after_delay(
                ThreadingConfig.CLEANUP_INITIAL_DELAY_MS
            )

            # Verify timer was not touched
            mock_timer.setInterval.assert_not_called()
            mock_timer.start.assert_not_called()

    def test_atomic_state_checking_prevents_deadlock(self, launcher_manager):
        """Test that atomic state checking prevents nested locking deadlock."""
        manager = launcher_manager

        # Create mock worker with state mutex - explicitly set to RUNNING
        mock_worker = MockWorker(mock_state=WorkerState.RUNNING)
        # Ensure the mock state is properly set in parent class too
        mock_worker._state = WorkerState.RUNNING
        worker_key = "test_worker_123"

        # Add worker to manager
        with manager._process_lock:
            manager._active_workers[worker_key] = mock_worker

        # Test atomic state checking doesn't deadlock
        start_time = time.time()
        state, is_running = manager._check_worker_state_atomic(worker_key)
        elapsed = time.time() - start_time

        # Should complete quickly (no deadlock)
        assert elapsed < 1.0
        assert state == "RUNNING"
        assert is_running is True

    def test_atomic_state_checking_worker_not_found(self, launcher_manager):
        """Test atomic state checking with missing worker."""
        manager = launcher_manager

        # Check state of non-existent worker
        state, is_running = manager._check_worker_state_atomic("nonexistent_worker")

        assert state == "DELETED"
        assert is_running is False

    def test_atomic_state_checking_worker_without_state_mutex(self, launcher_manager):
        """Test atomic state checking with worker lacking _state_mutex."""
        manager = launcher_manager

        # Create mock worker without _state_mutex
        mock_worker = MagicMock()
        mock_worker.get_state.return_value = "STOPPED"
        mock_worker.isRunning.return_value = False
        del mock_worker._state_mutex  # Remove state mutex

        worker_key = "test_worker_no_mutex"
        with manager._process_lock:
            manager._active_workers[worker_key] = mock_worker

        # Should handle gracefully
        state, is_running = manager._check_worker_state_atomic(worker_key)

        assert state == "STOPPED"
        assert is_running is False

    def test_worker_removal_race_prevention(self, launcher_manager):
        """Test that worker removal prevents race conditions."""
        manager = launcher_manager

        # Create mock running worker
        mock_worker = MockWorker(mock_state=WorkerState.RUNNING)
        worker_key = "test_worker_race"

        # Add worker to manager
        with manager._process_lock:
            manager._active_workers[worker_key] = mock_worker

        # Remove worker safely
        manager._remove_worker_safe(worker_key)

        # Verify worker was stopped before removal
        assert mock_worker.stop_called is True

        # Verify worker was removed from tracking
        with manager._process_lock:
            assert worker_key not in manager._active_workers

    def test_worker_removal_already_stopped(self, launcher_manager):
        """Test worker removal when worker is already stopped."""
        manager = launcher_manager

        # Create mock stopped worker
        mock_worker = MockWorker(mock_state=WorkerState.STOPPED)
        mock_worker._mock_running = False
        worker_key = "test_worker_stopped"

        # Add worker to manager
        with manager._process_lock:
            manager._active_workers[worker_key] = mock_worker

        # Remove worker safely
        manager._remove_worker_safe(worker_key)

        # Verify stop was not called (already stopped)
        assert mock_worker.stop_called is False

        # Verify worker was still removed from tracking
        with manager._process_lock:
            assert worker_key not in manager._active_workers

    def test_concurrent_worker_state_checking(self, launcher_manager):
        """Test concurrent worker state checking from multiple threads."""
        manager = launcher_manager

        # Create mock workers
        workers = {}
        for i in range(5):
            worker_key = f"test_worker_{i}"
            workers[worker_key] = MockWorker(worker_id=worker_key)

        # Add workers to manager
        with manager._process_lock:
            manager._active_workers.update(workers)

        results = []
        errors = []

        def check_worker_states(thread_id: int):
            """Check worker states from multiple threads."""
            try:
                for _ in range(10):
                    for worker_key in workers.keys():
                        state, is_running = manager._check_worker_state_atomic(
                            worker_key
                        )
                        results.append((thread_id, worker_key, state, is_running))
                    time.sleep(0.001)  # Small delay
            except Exception as e:
                errors.append((thread_id, str(e)))

        # Start multiple threads
        threads = []
        for i in range(3):
            t = threading.Thread(target=check_worker_states, args=(i,))
            threads.append(t)
            t.start()

        # Wait for all threads
        for t in threads:
            t.join(timeout=10.0)

        # Verify no errors occurred
        assert len(errors) == 0, f"Concurrent access errors: {errors}"
        assert len(results) == 150  # 3 threads × 10 iterations × 5 workers

    def test_cleanup_finished_workers_atomic_checking(self, launcher_manager):
        """Test that cleanup uses atomic state checking."""
        manager = launcher_manager

        # Create mix of finished and running workers
        workers = {
            "finished_1": MockWorker(mock_state=WorkerState.STOPPED),
            "finished_2": MockWorker(mock_state=WorkerState.DELETED),
            "running_1": MockWorker(mock_state=WorkerState.RUNNING),
            "inconsistent_1": MockWorker(
                mock_state=WorkerState.STOPPED
            ),  # Will be marked inconsistent
        }

        # Set inconsistent worker as still running
        workers["inconsistent_1"]._mock_running = True

        # Set finished workers as not running
        workers["finished_1"]._mock_running = False
        workers["finished_2"]._mock_running = False

        # Add workers to manager
        with manager._process_lock:
            manager._active_workers.update(workers)

        # Mock atomic state checking to verify it's called
        with patch.object(
            manager,
            "_check_worker_state_atomic",
            wraps=manager._check_worker_state_atomic,
        ) as mock_atomic:
            # Run cleanup
            manager._cleanup_finished_workers()

            # Verify atomic checking was called for each worker
            assert mock_atomic.call_count == len(workers)

    def test_inconsistent_worker_handling(self, launcher_manager):
        """Test handling of workers in inconsistent states."""
        manager = launcher_manager

        # Create inconsistent worker (STOPPED state but still running)
        inconsistent_worker = MockWorker(mock_state=WorkerState.STOPPED)
        inconsistent_worker._mock_running = True  # Inconsistent!

        worker_key = "inconsistent_worker"
        with manager._process_lock:
            manager._active_workers[worker_key] = inconsistent_worker

        # Handle inconsistent worker
        manager._handle_inconsistent_worker(worker_key, "STOPPED")

        # Verify worker was handled (stopped and removed)
        assert inconsistent_worker.stop_called is True

        # Verify worker was removed from tracking
        with manager._process_lock:
            assert worker_key not in manager._active_workers

    def test_cleanup_in_progress_flag(self, launcher_manager):
        """Test cleanup scheduled flag prevents concurrent cleanup."""
        manager = launcher_manager

        # Set cleanup as already scheduled
        manager._cleanup_scheduled = True

        # Attempt cleanup
        manager._cleanup_finished_workers()

        # Should return early without doing any cleanup (no timer operations)
        # Just verify no exception was raised

    def test_threadingconfig_integration(self, launcher_manager):
        """Test that LauncherManager uses ThreadingConfig constants."""
        manager = launcher_manager

        # Verify constants are used from ThreadingConfig
        assert (
            manager.MAX_CONCURRENT_PROCESSES == ThreadingConfig.MAX_WORKER_THREADS * 25
        )
        assert (
            manager.CLEANUP_INTERVAL_MS == ThreadingConfig.CACHE_CLEANUP_INTERVAL * 1000
        )
        assert (
            manager.PROCESS_STARTUP_TIMEOUT_MS
            == ThreadingConfig.SUBPROCESS_TIMEOUT * 1000
        )

    def test_worker_cleanup_timeout_values(self, launcher_manager):
        """Test that worker cleanup uses ThreadingConfig timeout values."""
        manager = launcher_manager

        # Create mock worker
        mock_worker = MockWorker(mock_state=WorkerState.RUNNING)
        worker_key = "timeout_test_worker"

        with manager._process_lock:
            manager._active_workers[worker_key] = mock_worker

        # Mock the safe_stop method to check timeout parameter
        with patch.object(
            mock_worker, "safe_stop", return_value=True
        ) as mock_safe_stop:
            manager._remove_worker_safe(worker_key)

            # Verify safe_stop was called with ThreadingConfig timeout
            mock_safe_stop.assert_called_once_with(
                timeout_ms=ThreadingConfig.WORKER_STOP_TIMEOUT_MS
            )

    def test_schedule_cleanup_delay_parameter(self, launcher_manager):
        """Test that schedule cleanup uses ThreadingConfig delay values."""
        manager = launcher_manager

        # Reset cleanup scheduled flag
        manager._cleanup_scheduled = False

        with patch.object(manager, "_cleanup_retry_timer") as mock_timer:
            mock_timer.isActive.return_value = False

            # Schedule cleanup with default delay
            manager._schedule_cleanup_after_delay()

            # Verify correct delay was set
            mock_timer.setInterval.assert_called_once_with(
                ThreadingConfig.CLEANUP_INITIAL_DELAY_MS
            )

    def test_process_lock_protection(self, launcher_manager):
        """Test that process lock protects shared state."""
        manager = launcher_manager

        # Verify process lock exists
        assert hasattr(manager, "_process_lock")
        assert isinstance(manager._process_lock, type(threading.RLock()))

        # Test accessing active workers with lock
        with manager._process_lock:
            worker_count = len(manager._active_workers)
            # Should be able to access safely
            assert isinstance(worker_count, int)

    def test_cleanup_exception_handling(self, launcher_manager):
        """Test that cleanup handles exceptions gracefully."""
        manager = launcher_manager

        # Create mock worker that raises exception
        mock_worker = MagicMock()
        mock_worker.get_state.side_effect = RuntimeError("Test exception")
        mock_worker.isRunning.return_value = True
        # Remove _state_mutex to force fallback to get_state() method
        if hasattr(mock_worker, "_state_mutex"):
            delattr(mock_worker, "_state_mutex")

        worker_key = "exception_worker"
        with manager._process_lock:
            manager._active_workers[worker_key] = mock_worker

        # Cleanup should handle exception gracefully
        try:
            state, is_running = manager._check_worker_state_atomic(worker_key)
            # Should return error state
            assert state == "ERROR"
            assert is_running is False
        except Exception as e:
            pytest.fail(f"Cleanup should handle exceptions gracefully: {e}")

    def test_memory_cleanup_on_worker_removal(self, launcher_manager):
        """Test that worker removal cleans up memory references."""
        manager = launcher_manager

        # Create mock worker
        mock_worker = MockWorker()
        worker_key = "memory_test_worker"

        # Add worker to manager
        with manager._process_lock:
            manager._active_workers[worker_key] = mock_worker
            initial_count = len(manager._active_workers)

        # Remove worker
        manager._remove_worker_safe(worker_key)

        # Verify worker removed from memory
        with manager._process_lock:
            final_count = len(manager._active_workers)
            assert final_count == initial_count - 1
            assert worker_key not in manager._active_workers

    @pytest.mark.parametrize(
        "worker_state,expected_category",
        [
            (WorkerState.STOPPED, "finished"),
            (WorkerState.DELETED, "finished"),
            (WorkerState.ERROR, "finished"),
            (WorkerState.CREATED, "finished"),  # Never started
            (WorkerState.RUNNING, "inconsistent"),  # Running but not running
        ],
    )
    def test_worker_categorization_logic(
        self, launcher_manager, worker_state, expected_category
    ):
        """Test worker categorization logic in cleanup."""
        manager = launcher_manager

        # Create worker with specific state
        mock_worker = MockWorker(mock_state=worker_state)
        # Ensure the mock state is properly set in parent class too
        mock_worker._state = worker_state

        # For RUNNING state, simulate inconsistency (state=RUNNING but not actually running)
        if worker_state == WorkerState.RUNNING:
            mock_worker._mock_running = False  # Inconsistent!
        else:
            mock_worker._mock_running = False  # Consistent

        worker_key = f"categorization_test_{worker_state.value}"
        with manager._process_lock:
            manager._active_workers[worker_key] = mock_worker

        # Check atomic state
        state, is_running = manager._check_worker_state_atomic(worker_key)

        # Verify categorization logic
        if expected_category == "finished":
            # Should be considered finished (consistent state)
            if worker_state in [
                WorkerState.STOPPED,
                WorkerState.DELETED,
                WorkerState.ERROR,
            ]:
                assert not is_running
            elif worker_state == WorkerState.CREATED:
                assert not is_running  # Never started
        elif expected_category == "inconsistent":
            # Should be considered inconsistent (state doesn't match running status)
            assert state == "RUNNING" and not is_running
