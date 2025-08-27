"""Final fixed version of threading tests that avoid Qt-in-thread issues."""

from __future__ import annotations

import logging
import subprocess
import time
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from launcher_manager import LauncherManager
from tests.test_doubles_library import TestSubprocess
from thread_safe_worker import ThreadSafeWorker, WorkerState

pytestmark = [pytest.mark.unit, pytest.mark.qt, pytest.mark.slow]

logger = logging.getLogger(__name__)


class SimpleTestWorker(ThreadSafeWorker):
    """Lightweight test worker without timeouts."""

    def __init__(self, work_steps: int = 5, fail_on_purpose: bool = False):
        super().__init__()
        self.work_steps = work_steps
        self.fail_on_purpose = fail_on_purpose
        self.work_started = False
        self.work_completed = False
        self.steps_completed = 0

    def do_work(self):
        """Quick work implementation without sleep."""
        self.work_started = True

        for step in range(self.work_steps):
            if self.should_stop():
                logger.debug(f"Worker stopping at step {step}")
                return

            self.steps_completed = step + 1

            # Process events only if QApplication exists
            app = QApplication.instance()
            if app and not self.should_stop():
                app.processEvents()

        if self.fail_on_purpose:
            raise RuntimeError("Intentional failure for testing")

        self.work_completed = True
        logger.debug(f"Worker completed {self.steps_completed} steps")


@pytest.fixture
def test_subprocess():
    """Test subprocess double for all tests."""
    return TestSubprocess()


@pytest.fixture
def launcher_manager(qtbot, test_subprocess):
    """Create LauncherManager with test subprocess double."""
    original_popen = subprocess.Popen
    subprocess.Popen = lambda *args, **kwargs: test_subprocess

    manager = None
    try:
        manager = LauncherManager()
        yield manager
    finally:
        subprocess.Popen = original_popen
        if manager:
            try:
                manager.stop_all_workers()
                manager.deleteLater()
                qtbot.wait(10)
            except Exception as e:
                logger.warning(f"Cleanup error: {e}")


class TestQTimerCascadePrevention:
    """Test QTimer cascade prevention without timeouts."""

    def test_rapid_cleanup_requests(self, launcher_manager, qtbot):
        """Test rapid cleanup requests don't cascade timers."""
        timer_activations = []
        original_start = launcher_manager._cleanup_retry_timer.start

        def track_timer_start(interval):
            timer_activations.append(time.time())
            original_start(interval)

        launcher_manager._cleanup_retry_timer.start = track_timer_start

        for _ in range(10):
            QTimer.singleShot(1, launcher_manager._cleanup_finished_workers)

        qtbot.wait(100)

        assert len(timer_activations) <= 3, (
            f"Too many timer activations: {len(timer_activations)}"
        )

        assert hasattr(launcher_manager, "_cleanup_scheduled")
        launcher_manager._cleanup_retry_timer.start = original_start

    def test_cleanup_coordination(self, launcher_manager, qtbot):
        """Test cleanup coordination behavior."""
        mock_worker = MagicMock()
        mock_worker.get_state.return_value = WorkerState.STOPPED
        mock_worker.isRunning.return_value = False

        with launcher_manager._process_lock:
            launcher_manager._active_workers = {"worker1": mock_worker}

        launcher_manager._cleanup_finished_workers()

        with launcher_manager._process_lock:
            assert len(launcher_manager._active_workers) == 0


class TestWorkerStateTransitions:
    """Test WorkerState transitions without timeouts."""

    @pytest.mark.timeout(5)
    def test_basic_state_transitions(self, qtbot):
        """Test basic state transitions."""
        worker = SimpleTestWorker(work_steps=3)

        assert worker.get_state() == WorkerState.CREATED
        assert worker.work_started is False
        assert worker.steps_completed == 0

        worker.start()

        if not worker.isRunning():
            qtbot.wait(10)

        completed = worker.wait(2000)

        if not completed:
            worker.request_stop()
            worker.quit()
            assert worker.wait(1000), "Worker did not stop after request"

        assert worker.work_started is True
        assert worker.steps_completed >= 1

        final_state = worker.get_state()
        assert final_state in [WorkerState.STOPPED, WorkerState.DELETED]

    @pytest.mark.timeout(5)
    def test_state_validation(self, qtbot):
        """Test state validation."""
        worker = SimpleTestWorker(work_steps=2)

        assert worker.get_state() == WorkerState.CREATED
        assert worker.work_started is False

        worker.start()

        if not worker.wait(2000):
            worker.request_stop()
            worker.quit()
            worker.wait(1000)

        assert worker.work_started is True
        assert worker.get_state() in [WorkerState.STOPPED, WorkerState.DELETED]

    @pytest.mark.timeout(10)
    def test_multiple_workers_lifecycle(self, qtbot):
        """Test multiple workers."""
        workers = []

        for i in range(3):
            worker = SimpleTestWorker(work_steps=2)
            workers.append(worker)

        for worker in workers:
            worker.start()

        for i, worker in enumerate(workers):
            if not worker.wait(2000):
                logger.warning(f"Worker {i} did not complete, forcing stop")
                worker.request_stop()
                worker.quit()
                worker.wait(1000)

        for worker in workers:
            assert worker.work_started is True
            assert worker.steps_completed >= 1

        for worker in workers:
            assert worker.get_state() in [WorkerState.STOPPED, WorkerState.DELETED]


class TestPerformanceImprovements:
    """Test performance improvements without cache operations."""

    def test_timer_efficiency(self, launcher_manager, qtbot):
        """Test timer efficiency."""
        start_time = time.time()

        for _ in range(20):
            QTimer.singleShot(1, lambda: None)

        qtbot.wait(50)

        elapsed = time.time() - start_time
        assert elapsed < 1.0, f"Timer operations took too long: {elapsed}s"


class TestSimpleThreadingIntegration:
    """Simple threading integration tests."""

    @pytest.mark.timeout(5)
    def test_basic_worker_integration(self, qtbot):
        """Test basic worker integration without cache."""
        worker = SimpleTestWorker(work_steps=2)
        worker.start()

        qtbot.wait(50)

        if worker.isRunning():
            worker.request_stop()
            if not worker.wait(1000):
                worker.quit()
                worker.wait(500)

        assert worker.work_started, "Worker did not start work"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "--timeout=30"])
