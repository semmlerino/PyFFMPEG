"""Final fixed version of threading tests that avoid Qt-in-thread issues."""

from __future__ import annotations

# Standard library imports
import logging
import time

# Third-party imports
import pytest

# Local application imports
from thread_safe_worker import ThreadSafeWorker, WorkerState


# Mark Qt tests for serial execution in same worker (prevents Qt crashes)
pytestmark = [
    pytest.mark.unit,
    pytest.mark.qt,
    pytest.mark.slow,
    pytest.mark.thread_safety,  # CRITICAL for parallel safety
]

logger = logging.getLogger(__name__)


class SimpleTestWorker(ThreadSafeWorker):
    """Lightweight test worker without timeouts."""

    def __init__(self, work_steps: int = 5, fail_on_purpose: bool = False) -> None:
        super().__init__()
        self.work_steps = work_steps
        self.fail_on_purpose = fail_on_purpose
        self.work_started = False
        self.work_completed = False
        self.steps_completed = 0

    def do_work(self) -> None:
        """Quick work implementation without sleep."""
        self.work_started = True

        for step in range(self.work_steps):
            if self.should_stop():
                logger.debug(f"Worker stopping at step {step}")
                return

            self.steps_completed = step + 1

            # REMOVED: Never call app.processEvents() in a worker thread!
            # This causes deadlocks and undefined behavior
            # Qt events should only be processed in the main thread

            # Simulate work without blocking (non-Qt worker thread context)
            # Note: time.sleep() acceptable here as this is a test double simulating external work
            time.sleep(0.001)  # 1ms per step

        if self.fail_on_purpose:
            raise RuntimeError("Intentional failure for testing")

        self.work_completed = True
        logger.debug(f"Worker completed {self.steps_completed} steps")


class TestWorkerStateTransitions:
    """Test WorkerState transitions without timeouts."""

    @pytest.mark.timeout(5)
    def test_basic_state_transitions(self, qtbot) -> None:
        """Test basic state transitions."""
        worker = SimpleTestWorker(work_steps=3)

        assert worker.get_state() == WorkerState.CREATED
        assert worker.work_started is False
        assert worker.steps_completed == 0

        worker.start()

        if not worker.isRunning():
            qtbot.wait(1)  # Minimal event processing

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
    def test_state_validation(self, qtbot) -> None:
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
    def test_multiple_workers_lifecycle(self, qtbot) -> None:
        """Test multiple workers."""
        workers = []

        for _ in range(3):
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


class TestSimpleThreadingIntegration:
    """Simple threading integration tests."""

    @pytest.mark.timeout(5)
    def test_basic_worker_integration(self, qtbot) -> None:
        """Test basic worker integration without cache."""
        worker = SimpleTestWorker(work_steps=2)

        try:
            worker.start()

            # Wait for worker to start work
            qtbot.waitUntil(lambda: worker.work_started, timeout=1000)

            if worker.isRunning():
                worker.request_stop()
                if not worker.wait(1000):
                    worker.quit()
                    worker.wait(500)

            assert worker.work_started, "Worker did not start work"
        finally:
            # Clean up worker to prevent Qt resource leaks in parallel execution
            if worker is not None:
                # Ensure worker is stopped
                if worker.isRunning():
                    worker.request_stop()
                    if not worker.wait(1000):
                        worker.terminate()
                        worker.wait(100)

                # Schedule for deletion (let Qt handle signal cleanup)
                worker.deleteLater()

            # Process Qt events to ensure cleanup is executed
            qtbot.wait(1)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "--timeout=30"])
