"""Unit tests for ThreadSafeWorker class.

Tests for thread-safe state transitions, signal emission, and proper lifecycle management.
"""

import threading
import time
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QMutex, QMutexLocker

from config import ThreadingConfig
from thread_safe_worker import ThreadSafeWorker, WorkerState


class WorkerTestHelper(ThreadSafeWorker):
    """Test implementation of ThreadSafeWorker for testing."""
    
    def __init__(self, work_duration: float = 0.1, should_fail: bool = False):
        super().__init__()
        self.work_duration = work_duration
        self.should_fail = should_fail
        self.work_started = False
        self.work_completed = False
        
    def do_work(self) -> None:
        """Simple work implementation for testing."""
        self.work_started = True
        
        start_time = time.time()
        while time.time() - start_time < self.work_duration:
            if self.should_stop():
                return  # Return early, don't set work_completed
            time.sleep(0.01)  # Small sleep to allow interruption
            
        if self.should_fail:
            raise RuntimeError("Test worker failure")
            
        self.work_completed = True


class TestThreadSafeWorker:
    """Test suite for ThreadSafeWorker class."""
    
    def test_initial_state(self):
        """Test worker starts in CREATED state."""
        worker = WorkerTestHelper()
        assert worker.get_state() == WorkerState.CREATED
        assert not worker.is_stop_requested()
        
    def test_valid_state_transitions(self):
        """Test valid state transitions work correctly."""
        worker = WorkerTestHelper()
        
        # CREATED -> STARTING
        assert worker.set_state(WorkerState.STARTING) is True
        assert worker.get_state() == WorkerState.STARTING
        
        # STARTING -> RUNNING
        assert worker.set_state(WorkerState.RUNNING) is True
        assert worker.get_state() == WorkerState.RUNNING
        
        # RUNNING -> STOPPING
        assert worker.set_state(WorkerState.STOPPING) is True
        assert worker.get_state() == WorkerState.STOPPING
        
        # STOPPING -> STOPPED
        assert worker.set_state(WorkerState.STOPPED) is True
        assert worker.get_state() == WorkerState.STOPPED
        
        # STOPPED -> DELETED
        assert worker.set_state(WorkerState.DELETED) is True
        assert worker.get_state() == WorkerState.DELETED
        
    def test_invalid_state_transitions(self):
        """Test invalid state transitions are rejected."""
        worker = WorkerTestHelper()
        
        # Can't go directly from CREATED to RUNNING
        assert worker.set_state(WorkerState.RUNNING) is False
        assert worker.get_state() == WorkerState.CREATED
        
        # Can't go backwards from STOPPING to RUNNING
        worker.set_state(WorkerState.STARTING)
        worker.set_state(WorkerState.RUNNING)
        worker.set_state(WorkerState.STOPPING)
        assert worker.set_state(WorkerState.RUNNING) is False
        assert worker.get_state() == WorkerState.STOPPING
        
    def test_force_parameter(self):
        """Test force parameter allows invalid transitions."""
        worker = WorkerTestHelper()
        
        # Force invalid transition
        assert worker.set_state(WorkerState.STOPPED, force=True) is True
        assert worker.get_state() == WorkerState.STOPPED
        
        # Force from terminal state
        worker.set_state(WorkerState.DELETED)
        assert worker.set_state(WorkerState.RUNNING, force=True) is True
        assert worker.get_state() == WorkerState.RUNNING
        
    def test_signal_emission_outside_mutex(self, qtbot):
        """Test that signals are emitted outside of mutex locks."""
        worker = WorkerTestHelper()
        
        # Use qtbot to wait for the signal to be emitted
        with qtbot.waitSignal(worker.worker_stopped, timeout=1000):
            # State transition that triggers signal
            worker.set_state(WorkerState.STOPPED)
            
    def test_request_stop_from_created(self, qtbot):
        """Test request_stop from CREATED state."""
        worker = WorkerTestHelper()
        
        # Use qtbot to wait for the signal to be emitted
        with qtbot.waitSignal(worker.worker_stopped, timeout=1000):
            result = worker.request_stop()
            
            assert result is True
            assert worker.get_state() == WorkerState.STOPPED
            assert worker.is_stop_requested() is True
            
    def test_request_stop_from_running(self, qtbot):
        """Test request_stop from RUNNING state."""
        worker = WorkerTestHelper()
        worker.set_state(WorkerState.STARTING)
        worker.set_state(WorkerState.RUNNING)
        
        # Use qtbot to wait for the signal to be emitted
        with qtbot.waitSignal(worker.worker_stopping, timeout=1000):
            result = worker.request_stop()
            
            assert result is True
            assert worker.get_state() == WorkerState.STOPPING
            assert worker.is_stop_requested() is True
            
    def test_request_stop_already_stopped(self):
        """Test request_stop when already stopped."""
        worker = WorkerTestHelper()
        worker.set_state(WorkerState.STOPPED, force=True)
        
        result = worker.request_stop()
        assert result is False  # Already stopped
        
    def test_should_stop_functionality(self):
        """Test should_stop method combines stop request and interruption."""
        worker = WorkerTestHelper()
        
        # Initially should not stop
        assert worker.should_stop() is False
        
        # After stop request, should stop
        worker.request_stop()
        assert worker.should_stop() is True
        
    def test_safe_connect_and_disconnect(self):
        """Test signal connection tracking and cleanup."""
        worker = WorkerTestHelper()
        
        # Create mock signal and slot
        mock_signal = MagicMock()
        mock_slot = MagicMock()
        
        # Connect signal
        worker.safe_connect(mock_signal, mock_slot)
        
        # Verify signal was connected
        mock_signal.connect.assert_called_once()
        
        # Disconnect all
        worker.disconnect_all()
        
        # Verify signal was disconnected
        mock_signal.disconnect.assert_called_once_with(mock_slot)
        
    def test_safe_wait_timeout(self):
        """Test safe_wait with timeout."""
        worker = WorkerTestHelper(work_duration=0.01)  # Very short work
        
        # For stopped worker, should return immediately
        worker.set_state(WorkerState.STOPPED, force=True)
        start_time = time.time()
        result = worker.safe_wait(ThreadingConfig.WORKER_STOP_TIMEOUT_MS)
        elapsed = time.time() - start_time
        
        assert result is True
        assert elapsed < 0.1  # Should return quickly
        
    def test_worker_lifecycle_complete(self, qtbot):
        """Test complete worker lifecycle with proper Qt signal handling."""
        worker = WorkerTestHelper(work_duration=0.05)
        
        # Track signal emissions
        signals_emitted = []
        worker.worker_started.connect(lambda: signals_emitted.append('started'))
        worker.worker_stopped.connect(lambda: signals_emitted.append('stopped'))
        
        # Start worker
        worker.start()
        
        # Wait for the QThread finished signal to be processed
        # This is the KEY fix - wait for the actual finished signal
        with qtbot.waitSignal(worker.finished, timeout=5000):
            pass
        
        # Give the _on_finished slot time to execute and transition to DELETED
        qtbot.wait(100)  # Small delay for state transition
        
        # Verify worker completed work
        assert worker.work_started is True
        assert worker.work_completed is True
        assert worker.get_state() == WorkerState.DELETED
        
    def test_worker_error_handling(self, qtbot):
        """Test worker error handling and state transitions."""
        worker = WorkerTestHelper(work_duration=0.05, should_fail=True)
        
        # Track error signal
        error_messages = []
        worker.worker_error.connect(lambda msg: error_messages.append(msg))
        
        # Start worker
        worker.start()
        
        # Wait for error signal to be emitted
        with qtbot.waitSignal(worker.worker_error, timeout=5000):
            pass
        
        # For error case, wait for the thread to actually finish
        # The thread should finish after the error
        worker.wait(5000)  # Use QThread.wait() directly
        
        # Process events to ensure _on_finished is called
        qtbot.wait(100)
        
        # Verify error was handled
        assert len(error_messages) > 0
        assert worker.work_started is True
        assert worker.work_completed is False  # Failed before completion
        assert worker.get_state() == WorkerState.DELETED
        
    def test_worker_stop_during_work(self, qtbot):
        """Test stopping worker during work execution."""
        worker = WorkerTestHelper(work_duration=1.0)  # Long running work
        
        # Start worker and wait for it to actually start
        with qtbot.waitSignal(worker.worker_started, timeout=5000):
            worker.start()
        
        # Verify work has started
        assert worker.work_started is True
        
        # Stop the worker
        result = worker.request_stop()
        assert result is True
        
        # Wait for worker to finish
        with qtbot.waitSignal(worker.finished, timeout=5000):
            pass
        
        # Give time for _on_finished to execute
        qtbot.wait(100)
        
        # Verify worker was stopped before completing all work
        assert worker.work_completed is False  # Stopped before completion
        assert worker.get_state() == WorkerState.DELETED
        
    def test_safe_stop_timeout(self, qtbot):
        """Test safe_stop with timeout configuration."""
        worker = WorkerTestHelper(work_duration=0.5)  # Shorter duration for faster test
        
        # Start worker and wait for it to be running
        worker.start()
        
        # Wait a bit for the worker to start
        qtbot.wait(100)
        
        # Verify worker is running
        assert worker.get_state() in [WorkerState.STARTING, WorkerState.RUNNING]
        
        # Test safe_stop
        result = worker.safe_stop(timeout_ms=ThreadingConfig.WORKER_STOP_TIMEOUT_MS)
        assert result is True
        
        # Verify worker stopped
        assert worker.get_state() in [WorkerState.STOPPED, WorkerState.DELETED]
        
    def test_safe_terminate_graceful(self):
        """Test safe_terminate with graceful shutdown."""
        worker = WorkerTestHelper(work_duration=0.05)
        
        # Start worker
        worker.start()
        
        # Wait a bit for work to start
        time.sleep(0.02)
        
        # Test safe_terminate (should be graceful for short work)
        worker.safe_terminate()
        
        # Verify worker is stopped
        final_state = worker.get_state()
        assert final_state in [WorkerState.STOPPED, WorkerState.DELETED]
        
    def test_concurrent_state_access(self):
        """Test thread-safe state access from multiple threads."""
        worker = WorkerTestHelper()
        
        results = []
        errors = []
        
        def state_accessor(thread_id: int):
            """Access worker state from multiple threads."""
            try:
                for i in range(10):
                    state = worker.get_state()
                    results.append((thread_id, i, state))
                    time.sleep(0.001)  # Small delay
            except Exception as e:
                errors.append((thread_id, str(e)))
                
        # Start multiple threads
        threads = []
        for i in range(3):
            t = threading.Thread(target=state_accessor, args=(i,))
            threads.append(t)
            t.start()
            
        # Wait for all threads
        for t in threads:
            t.join(timeout=5.0)
            
        # Verify no errors occurred
        assert len(errors) == 0, f"Thread safety errors: {errors}"
        assert len(results) == 30  # 3 threads × 10 iterations
        
    def test_threading_config_integration(self):
        """Test integration with ThreadingConfig constants."""
        worker = WorkerTestHelper()
        
        # Test default timeout parameters use ThreadingConfig
        assert hasattr(worker, 'safe_wait')
        assert hasattr(worker, 'safe_stop')
        
        # Verify we can use ThreadingConfig values
        result = worker.safe_wait(ThreadingConfig.WORKER_STOP_TIMEOUT_MS)
        assert result is True  # Worker not started, should return immediately
        
    def test_mutex_protection(self):
        """Test that state changes are properly mutex-protected."""
        worker = WorkerTestHelper()
        
        # Verify mutex exists and is accessible
        assert hasattr(worker, '_state_mutex')
        assert isinstance(worker._state_mutex, QMutex)
        
        # Test mutex protection during state change
        with QMutexLocker(worker._state_mutex):
            original_state = worker._state
            # State should be accessible within mutex
            assert original_state == WorkerState.CREATED
            
    @pytest.mark.parametrize("initial_state,target_state,expected_result", [
        (WorkerState.CREATED, WorkerState.STARTING, True),
        (WorkerState.CREATED, WorkerState.STOPPED, True),
        (WorkerState.STARTING, WorkerState.RUNNING, True),
        (WorkerState.STARTING, WorkerState.ERROR, True),
        (WorkerState.RUNNING, WorkerState.STOPPING, True),
        (WorkerState.STOPPING, WorkerState.STOPPED, True),
        (WorkerState.STOPPED, WorkerState.DELETED, True),
        (WorkerState.ERROR, WorkerState.STOPPED, True),
        # Invalid transitions
        (WorkerState.CREATED, WorkerState.RUNNING, False),
        (WorkerState.RUNNING, WorkerState.CREATED, False),
        (WorkerState.DELETED, WorkerState.RUNNING, False),
    ])
    def test_state_transition_matrix(self, initial_state, target_state, expected_result):
        """Test all valid and invalid state transitions systematically."""
        worker = WorkerTestHelper()
        
        # Set initial state (may require force for some states)
        if initial_state != WorkerState.CREATED:
            worker.set_state(initial_state, force=True)
            
        # Test transition
        result = worker.set_state(target_state)
        assert result == expected_result
        
        if expected_result:
            assert worker.get_state() == target_state
        else:
            assert worker.get_state() == initial_state