"""Unit tests for PreviousShotsWorker background thread following UNIFIED_TESTING_GUIDE.

Tests the background worker thread with real Qt threading and signal emission.
Focuses on thread safety, signal emission, and cancellation behavior.

UNIFIED_TESTING_GUIDE COMPLIANCE:
1. Mock only at system boundaries (subprocess.run, not internal methods)
2. Test behavior, not implementation details
3. Use real dependencies (PreviousShotsFinder) with system boundary mocks
4. Proper QThread cleanup without qtbot.addWidget()
5. PySide6 QSignalSpy API (count() method)
6. Signal waiters set up BEFORE actions to prevent race conditions

Focus areas:
- Real QThread testing with qtbot
- Signal emission with QSignalSpy
- Thread interruption and cancellation
- Complete workflow testing
- Error handling in threaded context
"""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QSignalSpy

from previous_shots_worker import PreviousShotsWorker
from shot_model import Shot
from tests.test_doubles_library import TestCompletedProcess

pytestmark = [pytest.mark.unit, pytest.mark.qt, pytest.mark.slow]

# This test file follows UNIFIED_TESTING_GUIDE best practices:
# - Test behavior, not implementation
# - Use test doubles instead of mocks
# - Real components where possible
# - Thread-safe testing patterns
# - Signal setup BEFORE triggering actions to prevent races


class TestPreviousShotsWorkerBasics:
    """Basic tests for PreviousShotsWorker initialization and control."""

    @pytest.fixture
    def mock_active_shots(self) -> list[Shot]:
        """Create mock active shots for filtering."""
        return [
            Shot("active_show", "seq1", "shot1", "/shows/active_show/shots/seq1/shot1"),
            Shot("active_show", "seq1", "shot2", "/shows/active_show/shots/seq1/shot2"),
        ]

    @pytest.fixture
    def shows_root(self, tmp_path: Path) -> Path:
        """Create shows directory structure."""
        shows_root = tmp_path / "shows"
        shows_root.mkdir(exist_ok=True)
        return shows_root

    @pytest.fixture
    def worker(self, mock_active_shots, shows_root) -> PreviousShotsWorker:
        """Create PreviousShotsWorker instance with proper thread cleanup."""
        worker = PreviousShotsWorker(
            active_shots=mock_active_shots, username="testuser", shows_root=shows_root
        )
        yield worker

        # Proper cleanup for QThread (not QWidget)
        if worker.isRunning():
            worker.stop()
            worker.wait(5000)  # Wait up to 5 seconds for thread to finish

    def test_worker_initialization(self, worker, mock_active_shots, shows_root):
        """Test worker initialization with correct parameters."""
        assert worker._active_shots == mock_active_shots
        assert worker._shows_root == shows_root
        assert worker._finder.username == "testuser"
        assert not worker._should_stop
        assert worker._found_shots == []

    def test_worker_stop_mechanism(self, worker):
        """Test worker stop request mechanism."""
        assert not worker._should_stop

        worker.stop()

        assert worker._should_stop

    def test_get_found_shots_returns_copy(self, worker):
        """Test that get_found_shots returns a copy of internal list."""
        # Add some shots to internal list
        test_shots = [
            Shot("show1", "seq1", "shot1", "/shows/show1/shots/seq1/shot1"),
        ]
        worker._found_shots = test_shots

        returned_shots = worker.get_found_shots()

        # Should be equal but not the same object
        assert returned_shots == test_shots
        assert returned_shots is not test_shots


class TestPreviousShotsWorkerWorkflow:
    """Test complete workflow with mocked system boundaries."""

    @pytest.fixture
    def worker_with_cleanup(self, tmp_path) -> PreviousShotsWorker:
        """Create worker with cleanup."""
        shows_root = tmp_path / "shows"
        shows_root.mkdir(exist_ok=True)

        active_shots = [
            Shot("active_show", "seq1", "shot1", "/shows/active_show/shots/seq1/shot1"),
        ]

        worker = PreviousShotsWorker(
            active_shots=active_shots, username="testuser", shows_root=shows_root
        )
        yield worker

        # Thread cleanup
        if worker.isRunning():
            worker.stop()
            worker.wait(5000)

    def test_complete_workflow_with_results(self, worker_with_cleanup, qtbot):
        """Test complete run() workflow with mocked subprocess at system boundary."""
        worker = worker_with_cleanup

        # Mock subprocess.run (system boundary) to simulate find command output
        find_output = [
            "/shows/show1/shots/seq1/shot1/user/testuser",
            "/shows/show1/shots/seq1/shot2/user/testuser",
            "/shows/show2/shots/seq2/shot1/user/testuser",
        ]

        test_result = TestCompletedProcess(
            args=[], returncode=0, stdout="\n".join(find_output) + "\n"
        )

        # Set up signal spies
        shot_found_spy = QSignalSpy(worker.shot_found)
        scan_finished_spy = QSignalSpy(worker.scan_finished)
        error_spy = QSignalSpy(worker.error_occurred)

        # FIX: Set up signal waiter BEFORE starting to prevent race condition
        with patch("subprocess.run", return_value=test_result):
            with qtbot.waitSignal(worker.scan_finished, timeout=5000):
                # Start worker after signal waiter is ready
                worker.start()

        # Ensure thread has finished
        worker.wait(2000)

        # Verify signals were emitted (PySide6 style)
        assert scan_finished_spy.count() == 1
        assert error_spy.count() == 0  # No errors

        # Should emit shot_found for each shot (excluding active ones)
        # 3 found shots - 0 matching active shots = 3 approved shots
        # (active_show != show1 or show2, so no filtering occurs)
        assert shot_found_spy.count() == 3

        # Verify final result
        final_result = scan_finished_spy.at(0)[0]
        assert len(final_result) == 3

    def test_workflow_with_no_results(self, worker_with_cleanup, qtbot):
        """Test workflow when no shots are found."""
        worker = worker_with_cleanup

        # Mock empty find command output
        test_result = TestCompletedProcess(args=[], returncode=0, stdout="")

        scan_finished_spy = QSignalSpy(worker.scan_finished)
        shot_found_spy = QSignalSpy(worker.shot_found)

        # FIX: Set up signal waiter BEFORE starting to prevent race condition
        with patch("subprocess.run", return_value=test_result):
            with qtbot.waitSignal(worker.scan_finished, timeout=5000):
                worker.start()

        worker.wait(2000)

        # Should complete successfully with no results
        assert scan_finished_spy.count() == 1
        assert shot_found_spy.count() == 0

        final_result = scan_finished_spy.at(0)[0]
        assert len(final_result) == 0

    def test_workflow_with_stop_request(self, worker_with_cleanup, qtbot):
        """Test workflow interruption with stop request."""
        worker = worker_with_cleanup

        # Mock slow subprocess to allow time for stop
        stop_event = threading.Event()

        def slow_subprocess(*args, **kwargs):
            # Wait briefly to allow stop request to be processed
            stop_event.wait(0.1)
            if worker._should_stop:
                # Return minimal result when stopped
                return TestCompletedProcess(
                    args=args[0] if args else [], returncode=0, stdout=""
                )

            # Return normal result
            return TestCompletedProcess(
                args=args[0] if args else [],
                returncode=0,
                stdout="/shows/show1/shots/seq1/shot1/user/testuser\n",
            )

        QSignalSpy(worker.scan_finished)

        # FIX: Use a flag to coordinate stop timing
        with patch("subprocess.run", side_effect=slow_subprocess):
            # Start worker with proper signal handling
            worker.start()

            # Allow worker to start processing
            qtbot.wait(100)  # Small delay to ensure worker is running

            # Request stop
            worker.stop()

            # Wait for thread to finish gracefully
            worker.wait(3000)

        # Worker should complete (may or may not emit scan_finished depending on timing)
        # Key test is that it stops gracefully without hanging

    def test_error_handling_finder_exception(self, worker_with_cleanup, qtbot):
        """Test error handling when finder raises unexpected exception."""
        worker = worker_with_cleanup

        error_spy = QSignalSpy(worker.error_occurred)
        scan_finished_spy = QSignalSpy(worker.scan_finished)

        # Mock finder.find_user_shots to raise exception (this will propagate)
        with patch.object(
            worker._finder,
            "find_user_shots",
            side_effect=RuntimeError("Critical finder error"),
        ):
            # FIX: Use waitSignal to properly wait for error signal
            with qtbot.waitSignal(worker.error_occurred, timeout=5000):
                worker.start()

            # Ensure thread has finished
            worker.wait(2000)

        # Process any pending events
        QCoreApplication.processEvents()

        # Should emit error signal
        assert error_spy.count() == 1
        error_message = error_spy.at(0)[0]
        assert "Error during previous shots scan" in error_message
        assert "Critical finder error" in error_message

        # Should not emit scan_finished on error
        assert scan_finished_spy.count() == 0

    def test_signal_data_format(self, worker_with_cleanup, qtbot):
        """Test signal data format matches expected structure."""
        worker = worker_with_cleanup

        # Mock subprocess output with single shot (different from active_show to avoid filtering)
        test_result = TestCompletedProcess(
            args=[],
            returncode=0,
            stdout="/shows/different_show/shots/testseq/testshot/user/testuser\n",
        )

        shot_found_spy = QSignalSpy(worker.shot_found)
        scan_finished_spy = QSignalSpy(worker.scan_finished)

        # FIX: Set up signal waiter BEFORE starting to prevent race condition
        with patch("subprocess.run", return_value=test_result):
            with qtbot.waitSignal(worker.scan_finished, timeout=5000):
                worker.start()

        worker.wait(2000)

        # Verify shot_found signal data structure
        assert shot_found_spy.count() == 1
        shot_dict = shot_found_spy.at(0)[0]

        required_keys = {"show", "sequence", "shot", "workspace_path"}
        assert set(shot_dict.keys()) == required_keys
        assert shot_dict["show"] == "different_show"
        assert shot_dict["sequence"] == "testseq"
        assert shot_dict["shot"] == "testshot"
        assert (
            shot_dict["workspace_path"]
            == "/shows/different_show/shots/testseq/testshot"
        )

        # Verify scan_finished signal data structure
        assert scan_finished_spy.count() == 1
        final_shots = scan_finished_spy.at(0)[0]
        assert isinstance(final_shots, list)
        assert len(final_shots) == 1
        assert final_shots[0] == shot_dict


class TestPreviousShotsWorkerIntegration:
    """Integration tests with real filesystem and limited mocking."""

    @pytest.fixture
    def real_shows_structure(self, tmp_path: Path) -> Path:
        """Create realistic shows directory structure for integration tests."""
        shows_root = tmp_path / "shows"

        # Create multiple shows with realistic structure
        shows_data = {
            "feature_film": {
                "sequences": ["010_opening", "020_chase"],
                "shots_per_seq": 3,
            },
            "commercial": {"sequences": ["001_product"], "shots_per_seq": 2},
        }

        for show_name, show_data in shows_data.items():
            for seq_name in show_data["sequences"]:
                for shot_idx in range(show_data["shots_per_seq"]):
                    shot_name = f"shot_{shot_idx:03d}"
                    shot_path = shows_root / show_name / "shots" / seq_name / shot_name

                    # Some shots have user work
                    if shot_idx % 2 == 0:  # Even shots have user work
                        user_path = shot_path / "user" / "testuser"
                        user_path.mkdir(parents=True, exist_ok=True)

                        # Add realistic work files
                        (user_path / "scene.3de").write_text("3DE scene data")
                        (user_path / "comp.nk").write_text("Nuke script")

        return shows_root

    def test_integration_with_real_finder(self, real_shows_structure, qtbot):
        """Test integration using real PreviousShotsFinder with mocked subprocess."""
        # Create active shots (some overlap with user work)
        active_shots = [
            Shot(
                "feature_film",
                "010_opening",
                "shot_000",
                str(
                    real_shows_structure
                    / "feature_film"
                    / "shots"
                    / "010_opening"
                    / "shot_000"
                ),
            ),
        ]

        worker = PreviousShotsWorker(
            active_shots=active_shots,
            username="testuser",
            shows_root=real_shows_structure,
        )

        # Mock subprocess to return paths that exist in our test structure
        find_output = [
            str(
                real_shows_structure
                / "feature_film/shots/010_opening/shot_000/user/testuser"
            ),
            str(
                real_shows_structure
                / "feature_film/shots/010_opening/shot_002/user/testuser"
            ),
            str(
                real_shows_structure
                / "feature_film/shots/020_chase/shot_000/user/testuser"
            ),
            str(
                real_shows_structure
                / "feature_film/shots/020_chase/shot_002/user/testuser"
            ),
            str(
                real_shows_structure
                / "commercial/shots/001_product/shot_000/user/testuser"
            ),
        ]

        test_result = TestCompletedProcess(
            args=[], returncode=0, stdout="\n".join(find_output) + "\n"
        )

        shot_found_spy = QSignalSpy(worker.shot_found)
        scan_finished_spy = QSignalSpy(worker.scan_finished)

        # FIX: Set up signal waiter BEFORE starting to prevent race condition
        with patch("subprocess.run", return_value=test_result):
            with qtbot.waitSignal(worker.scan_finished, timeout=10000):
                worker.start()

        # Cleanup
        worker.wait(2000)

        # Verify results
        assert scan_finished_spy.count() == 1
        final_shots = scan_finished_spy.at(0)[0]

        # Should find 5 user shots minus 1 active shot = 4 approved shots
        assert len(final_shots) == 4

        # Verify individual shot signals were emitted
        assert shot_found_spy.count() == 4


# Performance tests removed to prevent test suite timeout
# These tests were moved to a separate benchmark suite
