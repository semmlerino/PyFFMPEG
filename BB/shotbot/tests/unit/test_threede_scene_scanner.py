"""Unit tests for threede_scene_scanner.py"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from shot_model import Shot
from threede_scene_model import ThreeDEScene
from threede_scene_scanner import ThreeDEScannerManager, ThreeDESceneScanner


class TestThreeDESceneScanner:
    """Test ThreeDESceneScanner functionality."""

    @pytest.fixture
    def test_shots(self):
        """Create test shots."""
        shots = []
        for i in range(3):
            shot = Shot(
                show="testshow",
                sequence=f"seq{i:03d}",
                shot=f"shot{i:03d}",
                workspace_path=f"/test/path/{i}",
            )
            shots.append(shot)
        return shots

    @pytest.fixture
    def test_scenes(self):
        """Create test scenes."""
        scenes = []
        for i in range(3):
            scene = ThreeDEScene(
                show="testshow",
                sequence=f"seq{i:03d}",
                shot=f"shot{i:03d}",
                workspace_path=f"/test/path/{i}",
                user=f"user{i}",
                plate=f"plate{i:04d}",
                scene_path=Path(f"/path/to/scene{i}.3de"),
            )
            scenes.append(scene)
        return scenes

    def test_scanner_initialization(self, test_shots):
        """Test scanner initialization."""
        excluded_users = {"user1", "user2"}
        scanner = ThreeDESceneScanner(test_shots, excluded_users)

        assert scanner.shots == test_shots
        assert scanner.excluded_users == excluded_users
        assert scanner._is_cancelled is False
        assert scanner.signals is not None

    @patch("threede_scene_scanner.ThreeDESceneFinder.find_scenes_for_shot")
    def test_scanner_run_success(self, mock_find_scenes, test_shots, test_scenes):
        """Test successful scanner run."""
        # Setup mock to return scenes
        mock_find_scenes.side_effect = [[scene] for scene in test_scenes]

        scanner = ThreeDESceneScanner(test_shots, set())

        # Track emitted signals
        progress_signals = []
        scene_found_signals = []
        finished_signals = []

        scanner.signals.progress.connect(lambda c, t: progress_signals.append((c, t)))
        scanner.signals.scene_found.connect(lambda s: scene_found_signals.append(s))
        scanner.signals.finished.connect(lambda s: finished_signals.append(s))

        # Run scanner
        scanner.run()

        # Verify progress signals
        assert len(progress_signals) == 4  # One per shot + final
        assert progress_signals[0] == (0, 3)
        assert progress_signals[1] == (1, 3)
        assert progress_signals[2] == (2, 3)
        assert progress_signals[3] == (3, 3)

        # Verify scene found signals
        assert len(scene_found_signals) == 3
        for i, scene in enumerate(scene_found_signals):
            assert scene == test_scenes[i]

        # Verify finished signal
        assert len(finished_signals) == 1
        assert len(finished_signals[0]) == 3
        # Check sorting
        assert all(
            finished_signals[0][i].full_name <= finished_signals[0][i + 1].full_name
            for i in range(len(finished_signals[0]) - 1)
        )

    @patch("threede_scene_scanner.ThreeDESceneFinder.find_scenes_for_shot")
    def test_scanner_run_with_exclusions(self, mock_find_scenes, test_shots):
        """Test scanner with excluded users."""
        excluded_users = {"user1"}
        scanner = ThreeDESceneScanner(test_shots, excluded_users)

        # Run scanner
        scanner.run()

        # Verify excluded users were passed
        assert mock_find_scenes.call_count == 3
        for i, call in enumerate(mock_find_scenes.call_args_list):
            args, kwargs = call
            assert args[4] == excluded_users  # excluded_users parameter

    @patch("threede_scene_scanner.ThreeDESceneFinder.find_scenes_for_shot")
    def test_scanner_cancel(self, mock_find_scenes, test_shots, test_scenes):
        """Test scanner cancellation."""
        mock_find_scenes.return_value = [test_scenes[0]]

        scanner = ThreeDESceneScanner(test_shots, set())
        scene_found_signals = []
        scanner.signals.scene_found.connect(lambda s: scene_found_signals.append(s))

        # Cancel before running
        scanner.cancel()
        assert scanner._is_cancelled is True

        # Run scanner
        scanner.run()

        # Should not process any shots
        assert len(scene_found_signals) == 0

    @patch("threede_scene_scanner.ThreeDESceneFinder.find_scenes_for_shot")
    def test_scanner_error_handling(self, mock_find_scenes, test_shots):
        """Test scanner error handling."""
        mock_find_scenes.side_effect = Exception("Test error")

        scanner = ThreeDESceneScanner(test_shots, set())
        error_signals = []
        scanner.signals.error.connect(lambda e: error_signals.append(e))

        # Run scanner
        scanner.run()

        # Should emit error signal
        assert len(error_signals) == 1
        assert "Test error" in error_signals[0]

    @patch("threede_scene_scanner.ThreeDESceneFinder.find_scenes_for_shot")
    def test_scanner_empty_shots(self, mock_find_scenes):
        """Test scanner with empty shot list."""
        scanner = ThreeDESceneScanner([], set())
        finished_signals = []
        scanner.signals.finished.connect(lambda s: finished_signals.append(s))

        # Run scanner
        scanner.run()

        # Should complete with empty result
        assert len(finished_signals) == 1
        assert finished_signals[0] == []


class TestThreeDEScannerManager:
    """Test ThreeDEScannerManager functionality."""

    @pytest.fixture
    def manager(self):
        """Create scanner manager."""
        return ThreeDEScannerManager()

    @pytest.fixture
    def test_shots(self):
        """Create test shots."""
        return [
            Shot(
                show="testshow",
                sequence="seq001",
                shot="shot001",
                workspace_path="/test/path",
            )
        ]

    def test_manager_initialization(self, manager):
        """Test manager initialization."""
        assert manager._current_scanner is None

    @patch("threede_scene_scanner.QThreadPool.globalInstance")
    @patch("threede_scene_scanner.ThreeDESceneScanner")
    def test_start_scan(
        self, mock_scanner_class, mock_thread_pool, manager, test_shots
    ):
        """Test starting a scan."""
        mock_scanner = MagicMock()
        mock_scanner_class.return_value = mock_scanner
        mock_pool = MagicMock()
        mock_thread_pool.return_value = mock_pool

        # Track signals
        started_signals = []
        manager.scan_started.connect(lambda: started_signals.append(True))

        # Start scan
        excluded_users = {"user1"}
        manager.start_scan(test_shots, excluded_users)

        # Verify scanner created
        mock_scanner_class.assert_called_once_with(test_shots, excluded_users)
        assert manager._current_scanner == mock_scanner

        # Verify signals connected
        mock_scanner.signals.progress.connect.assert_called_once()
        mock_scanner.signals.finished.connect.assert_called_once()
        mock_scanner.signals.error.connect.assert_called_once()

        # Verify started signal emitted
        assert len(started_signals) == 1

        # Verify scanner started in thread pool
        mock_pool.start.assert_called_once_with(mock_scanner)

    @patch("threede_scene_scanner.QThreadPool.globalInstance")
    def test_cancel_existing_scan(self, mock_thread_pool, manager, test_shots):
        """Test cancelling existing scan when starting new one."""
        # Create mock for existing scanner
        existing_scanner = MagicMock()
        manager._current_scanner = existing_scanner

        # Start new scan
        manager.start_scan(test_shots, set())

        # Verify existing scanner was cancelled
        existing_scanner.cancel.assert_called_once()

    def test_scan_finished_handling(self, manager):
        """Test handling scan completion."""
        # Setup
        manager._current_scanner = MagicMock()
        finished_signals = []
        manager.scan_finished.connect(lambda s: finished_signals.append(s))

        test_scenes = [MagicMock(), MagicMock()]

        # Handle finished
        manager._on_scan_finished(test_scenes)

        # Verify
        assert manager._current_scanner is None
        assert len(finished_signals) == 1
        assert finished_signals[0] == test_scenes

    def test_cancel_scan(self, manager):
        """Test cancelling current scan."""
        # Setup with current scanner
        mock_scanner = MagicMock()
        manager._current_scanner = mock_scanner

        # Cancel scan
        manager.cancel_scan()

        # Verify
        mock_scanner.cancel.assert_called_once()
        assert manager._current_scanner is None

    def test_cancel_scan_no_current(self, manager):
        """Test cancelling when no scan active."""
        # Should not raise error
        manager.cancel_scan()
        assert manager._current_scanner is None

    @patch("threede_scene_scanner.QThreadPool.globalInstance")
    @patch("threede_scene_scanner.ThreeDESceneScanner")
    def test_signal_propagation(
        self, mock_scanner_class, mock_thread_pool, manager, test_shots
    ):
        """Test signal propagation from scanner to manager."""
        mock_scanner = MagicMock()
        mock_scanner_class.return_value = mock_scanner

        # Track manager signals
        progress_signals = []
        error_signals = []
        manager.scan_progress.connect(lambda c, t: progress_signals.append((c, t)))
        manager.scan_error.connect(lambda e: error_signals.append(e))

        # Start scan
        manager.start_scan(test_shots, set())

        # Get connected callbacks
        progress_callback = mock_scanner.signals.progress.connect.call_args[0][0]
        error_callback = mock_scanner.signals.error.connect.call_args[0][0]

        # Simulate scanner signals
        progress_callback(5, 10)
        error_callback("Test error")

        # Verify propagation
        assert progress_signals == [(5, 10)]
        assert error_signals == ["Test error"]
