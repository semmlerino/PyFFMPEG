"""Unit tests for threede_scene_worker module.

This module tests the ProgressCalculator and ThreeDESceneWorker classes.
Following the testing guide principles:
- Test behavior, not implementation
- Use real components with test doubles for I/O
- Mock only at system boundaries
- Use QSignalSpy for real Qt signals
"""

import time
from collections import deque
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QMutex, QThread, QWaitCondition
from PySide6.QtTest import QSignalSpy

from shot_model import Shot
from threede_scene_finder import ThreeDESceneFinder
from threede_scene_model import ThreeDEScene
from threede_scene_worker import ProgressCalculator, ThreeDESceneWorker


# Test Fixtures
@pytest.fixture
def sample_shots():
    """Create sample Shot objects for testing."""
    return [
        Shot(
            show="test_show",
            sequence="seq01",
            shot="shot01",
            workspace_path="/shows/test_show/seq01/seq01_shot01",
        ),
        Shot(
            show="test_show",
            sequence="seq01",
            shot="shot02",
            workspace_path="/shows/test_show/seq01/seq01_shot02",
        ),
    ]


@pytest.fixture
def sample_scenes():
    """Create sample ThreeDEScene objects for testing."""
    return [
        ThreeDEScene(
            show="test_show",
            sequence="seq01",
            shot="shot01",
            workspace_path="/shows/test_show/seq01/seq01_shot01",
            user="user1",
            plate="FG01",
            scene_path=Path("/test/scene1.3de"),
        ),
        ThreeDEScene(
            show="test_show",
            sequence="seq01",
            shot="shot02",
            workspace_path="/shows/test_show/seq01/seq01_shot02",
            user="user2",
            plate="BG01",
            scene_path=Path("/test/scene2.3de"),
        ),
    ]


@pytest.fixture
def excluded_users():
    """Create a set of excluded users."""
    return {"current_user", "test_user"}


class TestProgressCalculator:
    """Test ProgressCalculator class."""

    def test_initialization(self):
        """Test ProgressCalculator initialization."""
        calc = ProgressCalculator(smoothing_window=10)

        assert calc.smoothing_window == 10
        assert isinstance(calc.processing_times, deque)
        assert calc.processing_times.maxlen == 10
        assert calc.files_processed == 0
        assert calc.total_files_estimate == 0

    def test_initialization_with_defaults(self):
        """Test ProgressCalculator with default smoothing window."""
        calc = ProgressCalculator()

        # Should use Config.PROGRESS_ETA_SMOOTHING_WINDOW
        assert calc.smoothing_window > 0
        assert isinstance(calc.processing_times, deque)

    def test_update_with_progress(self):
        """Test progress update calculation."""
        calc = ProgressCalculator(smoothing_window=5)
        calc.total_files_estimate = 100

        # First update
        progress_pct, eta_str = calc.update(25)

        assert progress_pct == 25.0
        # ETA string might be empty on first update (no rate calculated yet)

    def test_update_with_total_estimate(self):
        """Test updating with new total estimate."""
        calc = ProgressCalculator()

        progress_pct, eta_str = calc.update(10, total_estimate=50)

        assert calc.total_files_estimate == 50
        assert progress_pct == 20.0  # 10/50 = 20%

    def test_progress_percentage_capping(self):
        """Test that progress percentage is capped at 100%."""
        calc = ProgressCalculator()
        calc.total_files_estimate = 10

        # Try to exceed 100%
        progress_pct, eta_str = calc.update(15)

        assert progress_pct == 100.0  # Should be capped

    def test_eta_calculation_with_rate(self):
        """Test ETA calculation with processing rate."""
        calc = ProgressCalculator(smoothing_window=3)
        calc.total_files_estimate = 100

        # Simulate processing with time delays
        calc.update(10)
        time.sleep(0.01)  # Small delay
        calc.update(20)
        time.sleep(0.01)
        progress_pct, eta_str = calc.update(30)

        assert progress_pct == 30.0
        # ETA string should be populated if rate was calculated
        if eta_str:  # May be empty if PROGRESS_ENABLE_ETA is False
            assert "remaining" in eta_str or eta_str == ""

    def test_eta_formatting(self):
        """Test ETA string formatting for different time ranges."""
        calc = ProgressCalculator()

        # Mock the processing times to control rate
        calc.processing_times = deque([10.0], maxlen=5)  # 10 files/sec
        calc.total_files_estimate = 100
        calc.files_processed = 10

        eta_str = calc._calculate_eta()

        if eta_str:  # Only test if ETA is enabled
            # 90 remaining files at 10 files/sec = 9 seconds
            assert "9s" in eta_str or "remaining" in eta_str

    def test_eta_disabled(self):
        """Test that ETA returns empty string when disabled."""
        with patch("threede_scene_worker.Config.PROGRESS_ENABLE_ETA", False):
            calc = ProgressCalculator()
            calc.total_files_estimate = 100
            calc.files_processed = 50
            calc.processing_times = deque([5.0], maxlen=5)

            eta_str = calc._calculate_eta()

            assert eta_str == ""

    def test_eta_with_no_progress(self):
        """Test ETA when no progress has been made."""
        calc = ProgressCalculator()
        calc.total_files_estimate = 100
        calc.files_processed = 100  # Already complete

        eta_str = calc._calculate_eta()

        assert eta_str == ""

    def test_eta_with_zero_rate(self):
        """Test ETA when processing rate is zero."""
        calc = ProgressCalculator()
        calc.processing_times = deque([0.0], maxlen=5)
        calc.total_files_estimate = 100
        calc.files_processed = 50

        eta_str = calc._calculate_eta()

        assert eta_str == ""


class TestThreeDESceneWorker:
    """Test ThreeDESceneWorker class."""

    def test_initialization(self, sample_shots, excluded_users):
        """Test worker initialization."""
        worker = ThreeDESceneWorker(
            shots=sample_shots,
            excluded_users=excluded_users,
            batch_size=10,
            enable_progressive=True,
        )

        assert worker.shots == sample_shots
        assert worker.excluded_users == excluded_users
        assert worker.batch_size == 10
        assert worker.enable_progressive is True
        assert worker._all_scenes == []
        assert worker._files_processed == 0
        assert isinstance(worker._pause_mutex, QMutex)
        assert isinstance(worker._pause_condition, QWaitCondition)

    def test_initialization_with_defaults(self, sample_shots):
        """Test worker initialization with default values."""
        worker = ThreeDESceneWorker(shots=sample_shots)

        assert worker.shots == sample_shots
        assert isinstance(worker.excluded_users, set)
        assert worker.batch_size > 0  # Should use Config default
        # Progressive mode depends on Config

    def test_pause_and_resume(self, qtbot, sample_shots):
        """Test pause and resume functionality."""
        worker = ThreeDESceneWorker(shots=sample_shots)

        # Initially not paused
        assert not worker.is_paused()

        # Set up signal spies
        pause_spy = QSignalSpy(worker.paused)
        resume_spy = QSignalSpy(worker.resumed)

        # Pause the worker
        worker.pause()
        assert worker.is_paused()
        assert pause_spy.count() == 1

        # Pause again (should not emit signal)
        worker.pause()
        assert worker.is_paused()
        assert pause_spy.count() == 1  # Still only 1

        # Resume the worker
        worker.resume()
        assert not worker.is_paused()
        assert resume_spy.count() == 1

        # Resume again (should not emit signal)
        worker.resume()
        assert not worker.is_paused()
        assert resume_spy.count() == 1  # Still only 1

    def test_stop_when_paused(self, sample_shots):
        """Test that stop works even when worker is paused."""
        worker = ThreeDESceneWorker(shots=sample_shots)

        # Pause the worker
        worker.pause()
        assert worker.is_paused()

        # Stop should resume and then stop
        worker.stop()

        # Worker should no longer be paused (resumed during stop)
        assert not worker.is_paused()
        # Stop should be requested
        assert worker.is_stop_requested()

    def test_check_pause_and_cancel_stop_requested(self, sample_shots):
        """Test that check_pause_and_cancel returns False when stop requested."""
        worker = ThreeDESceneWorker(shots=sample_shots)

        # Request stop
        worker.request_stop()

        # Should return False
        assert not worker._check_pause_and_cancel()

    def test_check_pause_and_cancel_continue(self, sample_shots):
        """Test that check_pause_and_cancel returns True when not stopped."""
        worker = ThreeDESceneWorker(shots=sample_shots)

        # Should return True (continue processing)
        assert worker._check_pause_and_cancel()

    def test_do_work_with_no_shots(self, qtbot):
        """Test worker execution with no shots."""
        worker = ThreeDESceneWorker(shots=[])

        # Set up signal spies
        started_spy = QSignalSpy(worker.started)
        finished_spy = QSignalSpy(worker.finished)

        # Run the worker
        worker.do_work()

        # Should emit started and finished with empty list
        assert started_spy.count() == 1
        assert finished_spy.count() == 1
        assert finished_spy.at(0)[0] == []  # Empty scenes list

    def test_do_work_cancelled_early(self, qtbot, sample_shots):
        """Test worker cancellation before processing."""
        worker = ThreeDESceneWorker(shots=sample_shots)

        # Request stop before starting
        worker.request_stop()

        # Set up signal spies
        started_spy = QSignalSpy(worker.started)
        finished_spy = QSignalSpy(worker.finished)

        # Run the worker
        worker.do_work()

        # Should emit started and finished with empty list
        assert started_spy.count() == 1
        assert finished_spy.count() == 1
        assert finished_spy.at(0)[0] == []

    def test_do_work_progressive_mode(self, qtbot, sample_shots, sample_scenes):
        """Test worker in progressive mode."""
        worker = ThreeDESceneWorker(
            shots=sample_shots, enable_progressive=True, batch_size=1,
        )

        # Mock the scene finder at the correct location
        with patch.object(
            ThreeDESceneFinder, "estimate_scan_size", return_value=(2, 10),
        ):
            # Mock progressive discovery - yield scenes one at a time
            def mock_progressive(*args, **kwargs):
                for i, scene in enumerate(sample_scenes):
                    yield (
                        [scene],
                        i + 1,
                        len(sample_scenes),
                        f"Processing shot {i + 1}",
                    )

            with patch.object(
                ThreeDESceneFinder,
                "find_all_scenes_progressive",
                return_value=mock_progressive(),
            ):
                # Set up signal spies
                started_spy = QSignalSpy(worker.started)
                batch_spy = QSignalSpy(worker.batch_ready)
                QSignalSpy(worker.progress)
                finished_spy = QSignalSpy(worker.finished)

                # Run the worker
                worker.do_work()

                # Check signals were emitted
                assert started_spy.count() == 1
                assert batch_spy.count() == len(sample_scenes)  # One batch per scene
                assert finished_spy.count() == 1

                # Check accumulated scenes
                assert len(worker._all_scenes) == len(sample_scenes)

    def test_do_work_traditional_mode(self, qtbot, sample_shots):
        """Test worker in traditional (non-progressive) mode."""
        worker = ThreeDESceneWorker(shots=sample_shots, enable_progressive=False)

        # Mock the scene finder
        mock_discover_result = [
            ("/test/path", "test_show", "seq01", "shot01"),
            ("/test/path", "test_show", "seq01", "shot02"),
        ]

        with patch.object(
            ThreeDESceneFinder,
            "discover_all_shots_in_show",
            return_value=mock_discover_result,
        ):
            with patch.object(
                ThreeDESceneFinder, "find_scenes_for_shot", return_value=[],
            ):
                # Set up signal spies
                started_spy = QSignalSpy(worker.started)
                QSignalSpy(worker.progress)
                finished_spy = QSignalSpy(worker.finished)

                # Run the worker
                worker.do_work()

                # Check signals were emitted
                assert started_spy.count() == 1
                assert finished_spy.count() == 1

    def test_do_work_error_handling(self, qtbot, sample_shots):
        """Test worker error handling."""
        worker = ThreeDESceneWorker(shots=sample_shots, enable_progressive=True)

        # Mock find_all_scenes_progressive to raise an exception during discovery
        # This will trigger the error signal since it's not caught with a fallback
        with patch.object(
            ThreeDESceneFinder, "estimate_scan_size", return_value=(2, 10),
        ):
            with patch.object(
                ThreeDESceneFinder,
                "find_all_scenes_progressive",
                side_effect=Exception("Test error"),
            ):
                # Set up signal spies
                error_spy = QSignalSpy(worker.error)
                started_spy = QSignalSpy(worker.started)

                # Run the worker - exception in discovery will trigger error signal and re-raise
                # The do_work() method emits error signal then re-raises for base class handling
                with pytest.raises(Exception, match="Test error"):
                    worker.do_work()

                # Check that signals were emitted before the exception was re-raised
                assert started_spy.count() == 1  # Started should be emitted
                assert error_spy.count() == 1  # Error should be emitted
                assert "Test error" in error_spy.at(0)[0]

    def test_discover_scenes_progressive_with_pause(self, sample_shots, sample_scenes):
        """Test progressive discovery with pause/resume."""
        worker = ThreeDESceneWorker(
            shots=sample_shots, enable_progressive=True, batch_size=1,
        )

        # Track pause check calls
        pause_check_count = 0
        original_check = worker._check_pause_and_cancel

        def mock_check():
            nonlocal pause_check_count
            pause_check_count += 1
            # Pause on second check
            if pause_check_count == 2:
                worker.pause()
                # Resume after a moment
                worker.resume()
            return original_check()

        worker._check_pause_and_cancel = mock_check

        # Mock the scene finder
        with patch.object(
            ThreeDESceneFinder, "estimate_scan_size", return_value=(2, 10),
        ):

            def mock_progressive(*args, **kwargs):
                for i, scene in enumerate(sample_scenes):
                    yield (
                        [scene],
                        i + 1,
                        len(sample_scenes),
                        f"Processing shot {i + 1}",
                    )

            with patch.object(
                ThreeDESceneFinder,
                "find_all_scenes_progressive",
                return_value=mock_progressive(),
            ):
                # Run discovery
                scenes = worker._discover_scenes_progressive()

                # Should have processed all scenes despite pause
                assert len(scenes) == len(sample_scenes)
                assert pause_check_count > 0

    def test_discover_scenes_progressive_cancelled(self, sample_shots, sample_scenes):
        """Test progressive discovery when cancelled."""
        worker = ThreeDESceneWorker(
            shots=sample_shots, enable_progressive=True, batch_size=1,
        )

        # Track how many batches were yielded
        batches_yielded = 0

        # Mock the scene finder
        with patch.object(
            ThreeDESceneFinder, "estimate_scan_size", return_value=(2, 10),
        ):

            def mock_progressive(*args, **kwargs):
                nonlocal batches_yielded
                for i, scene in enumerate(sample_scenes):
                    batches_yielded += 1
                    yield (
                        [scene],
                        i + 1,
                        len(sample_scenes),
                        f"Processing shot {i + 1}",
                    )
                    # Cancel after first batch
                    if i == 0:
                        worker.request_stop()

            with patch.object(
                ThreeDESceneFinder,
                "find_all_scenes_progressive",
                return_value=mock_progressive(),
            ):
                # Run discovery
                scenes = worker._discover_scenes_progressive()

                # Should have processed at least one scene before cancellation
                assert len(scenes) >= 1
                assert len(scenes) <= len(sample_scenes)
                # The generator should have yielded at least once
                assert batches_yielded >= 1

    def test_discover_scenes_traditional_show_discovery(self, sample_shots):
        """Test traditional discovery with show root extraction."""
        worker = ThreeDESceneWorker(shots=sample_shots, enable_progressive=False)

        # Mock the scene finder to prevent actual file system access
        # Set up mock to prevent actual function calls
        mock_discover = Mock(return_value=[])
        mock_find_scenes = Mock(return_value=[])

        with patch.object(
            ThreeDESceneFinder, "discover_all_shots_in_show", mock_discover,
        ):
            with patch.object(
                ThreeDESceneFinder, "find_scenes_for_shot", mock_find_scenes,
            ):
                # Run discovery
                scenes = worker._discover_scenes_traditional()

                # Should have called discover_all_shots_in_show at least once
                assert mock_discover.called
                assert len(scenes) == 0  # No scenes found

    def test_thread_priority_setting(self, sample_shots):
        """Test that thread priority is set correctly."""
        with patch("threede_scene_worker.Config.WORKER_THREAD_PRIORITY", 1):
            worker = ThreeDESceneWorker(shots=sample_shots)

            # Priority should be set to HighPriority
            assert worker._desired_priority == QThread.Priority.HighPriority

            # Mock the scene finder to prevent actual work
            with patch.object(
                ThreeDESceneFinder,
                "find_all_scenes_in_shows_efficient",
                return_value=[],
            ):
                # Mock setPriority to verify it's called
                with patch.object(worker, "setPriority") as mock_set_priority:
                    worker.do_work()

                    # Should have set the priority
                    mock_set_priority.assert_called_once_with(
                        QThread.Priority.HighPriority,
                    )

    def test_progress_throttling(self, sample_shots, sample_scenes):
        """Test that progress updates are throttled."""
        worker = ThreeDESceneWorker(
            shots=sample_shots, enable_progressive=True, batch_size=1,
        )

        # Set up signal spy to track progress emissions
        progress_spy = QSignalSpy(worker.progress)

        # Mock time to control throttling
        with patch("time.time") as mock_time:
            # Start time
            mock_time.return_value = 1000.0

            # Mock the scene finder
            with patch.object(
                ThreeDESceneFinder, "estimate_scan_size", return_value=(2, 10),
            ):

                def mock_progressive(*args, **kwargs):
                    for i in range(10):  # Many batches
                        # Advance time slightly
                        mock_time.return_value = 1000.0 + (i * 0.01)  # 10ms each
                        yield ([], i + 1, 10, f"Processing {i + 1}")

                with patch.object(
                    ThreeDESceneFinder,
                    "find_all_scenes_progressive",
                    return_value=mock_progressive(),
                ):
                    # Run discovery
                    worker._discover_scenes_progressive()

                    # Progress should be throttled (not emitted for every batch)
                    assert progress_spy.count() < 10  # Less than the number of batches

    def test_scan_progress_signal(self, qtbot, sample_shots, sample_scenes):
        """Test that scan_progress signal is emitted."""
        worker = ThreeDESceneWorker(shots=sample_shots, enable_progressive=True)

        # Set up signal spy
        scan_spy = QSignalSpy(worker.scan_progress)

        # Mock the scene finder
        with patch.object(
            ThreeDESceneFinder, "estimate_scan_size", return_value=(2, 10),
        ):

            def mock_progressive(*args, **kwargs):
                yield (sample_scenes, 1, 1, "Test status")

            with patch.object(
                ThreeDESceneFinder,
                "find_all_scenes_progressive",
                return_value=mock_progressive(),
            ):
                # Run discovery
                worker._discover_scenes_progressive()

                # Should have emitted scan_progress
                assert scan_spy.count() == 1
                # Check the signal arguments (int, int, str)
                signal_args = scan_spy.at(0)
                assert signal_args[0] == 1  # current_shot
                assert signal_args[1] == 1  # total_shots
                assert signal_args[2] == "Test status"  # status_msg
