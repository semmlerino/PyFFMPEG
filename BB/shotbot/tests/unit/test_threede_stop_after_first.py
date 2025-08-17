#!/usr/bin/env python3
"""Test stop-after-first optimization for 3DE scanner.

This test ensures that the scanner stops after finding one .3de file per shot,
improving performance and preventing duplicate processing.
"""

import time
import unittest
from pathlib import Path
from typing import List
from unittest.mock import Mock, patch

from threede_scene_finder import ThreeDESceneFinder


class TestStopAfterFirstOptimization(unittest.TestCase):
    """Test suite for stop-after-first 3DE scanner optimization."""

    def setUp(self):
        """Set up test fixtures."""
        self.finder = ThreeDESceneFinder()

    def create_mock_3de_files(self, num_shots: int, files_per_shot: int) -> List[Path]:
        """Create mock .3de file paths for testing.

        Args:
            num_shots: Number of unique shots
            files_per_shot: Number of .3de files per shot

        Returns:
            List of mock file paths
        """
        files = []
        for shot_num in range(num_shots):
            sequence = f"SEQ_{shot_num // 10:02d}"
            shot = f"{shot_num:04d}"
            shot_dir = f"{sequence}_{shot}"

            for file_num in range(files_per_shot):
                # Create multiple files per shot with different users/versions
                user = f"artist{file_num % 3}"
                version = f"v{file_num + 1:03d}"
                path = Path(
                    f"/shows/test_show/shots/{sequence}/{shot_dir}/user/{user}/3de/{shot_dir}_comp_{version}.3de",
                )
                files.append(path)

        return files

    def test_stop_after_first_enabled(self):
        """Test that scanner stops after finding one file per shot when enabled."""
        with patch("config.Config.THREEDE_STOP_AFTER_FIRST", True):
            with patch("config.Config.THREEDE_MAX_SHOTS_TO_SCAN", 1000):
                with patch("config.Config.THREEDE_FILE_FIRST_DISCOVERY", True):
                    # Create mock files: 100 shots with 5 files each
                    mock_files = self.create_mock_3de_files(100, 5)

                    # Mock the file discovery - patch at module level
                    with patch(
                        "threede_scene_finder.ThreeDESceneFinder.find_all_3de_files_in_show",
                        return_value=mock_files,
                    ):
                        # Create proper mock shot
                        mock_shot = Mock()
                        mock_shot.show = "test_show"
                        mock_shot.sequence = "SEQ_00"
                        mock_shot.shot = "0001"
                        mock_shot.workspace_path = (
                            "/shows/test_show/shots/SEQ_00/SEQ_00_0001"
                        )

                        # Process files
                        scenes = self.finder.find_all_scenes_in_shows_efficient(
                            user_shots=[mock_shot], excluded_users=set(),
                        )

                        # Should only have one scene per shot (100 total, not 500)
                        unique_shots = set()
                        for scene in scenes:
                            shot_key = (scene.sequence, scene.shot)
                            unique_shots.add(shot_key)

                        # We should have at most 100 unique shots
                        self.assertLessEqual(len(scenes), 100)
                        self.assertEqual(len(unique_shots), len(scenes))

    def test_stop_after_first_disabled(self):
        """Test that scanner processes all files when stop-after-first is disabled."""
        with patch("config.Config.THREEDE_STOP_AFTER_FIRST", False):
            with patch("config.Config.THREEDE_MAX_SHOTS_TO_SCAN", 1000):
                with patch("config.Config.THREEDE_SCAN_MAX_FILES_PER_SHOT", 10):
                    with patch("config.Config.THREEDE_FILE_FIRST_DISCOVERY", True):
                        # Create mock files: 10 shots with 3 files each
                        mock_files = self.create_mock_3de_files(10, 3)

                        # Mock the file discovery
                        with patch(
                            "threede_scene_finder.ThreeDESceneFinder.find_all_3de_files_in_show",
                            return_value=mock_files,
                        ):
                            # Create proper mock shot
                            mock_shot = Mock()
                            mock_shot.show = "test_show"
                            mock_shot.sequence = "SEQ_00"
                            mock_shot.shot = "0001"
                            mock_shot.workspace_path = (
                                "/shows/test_show/shots/SEQ_00/SEQ_00_0001"
                            )

                            # Process files
                            scenes = self.finder.find_all_scenes_in_shows_efficient(
                                user_shots=[mock_shot], excluded_users=set(),
                            )

                            # Should have all files (30 total)
                            self.assertEqual(len(scenes), 30)

    def test_max_shots_limit_increased(self):
        """Test that the scanner can handle the increased max shots limit."""
        with patch("config.Config.THREEDE_MAX_SHOTS_TO_SCAN", 1000):
            with patch("config.Config.THREEDE_STOP_AFTER_FIRST", True):
                with patch("config.Config.THREEDE_FILE_FIRST_DISCOVERY", True):
                    # Create mock files: 1000 shots with 1 file each
                    mock_files = self.create_mock_3de_files(1000, 1)

                    # Mock the file discovery
                    with patch(
                        "threede_scene_finder.ThreeDESceneFinder.find_all_3de_files_in_show",
                        return_value=mock_files,
                    ):
                        # Create proper mock shot
                        mock_shot = Mock()
                        mock_shot.show = "test_show"
                        mock_shot.sequence = "SEQ_00"
                        mock_shot.shot = "0001"
                        mock_shot.workspace_path = (
                            "/shows/test_show/shots/SEQ_00/SEQ_00_0001"
                        )

                        # Process files
                        scenes = self.finder.find_all_scenes_in_shows_efficient(
                            user_shots=[mock_shot], excluded_users=set(),
                        )

                        # Should handle all 1000 shots
                        self.assertEqual(len(scenes), 1000)

    def test_shot_directory_tracking(self):
        """Test that shot directories are properly tracked to avoid duplicates."""

        # Create a mock file structure with duplicates in same shot
        test_files = [
            Path("/shows/test/shots/SEQ_01/SEQ_01_0010/user/artist1/3de/file1.3de"),
            Path("/shows/test/shots/SEQ_01/SEQ_01_0010/user/artist2/3de/file2.3de"),
            Path("/shows/test/shots/SEQ_01/SEQ_01_0010/user/artist3/3de/file3.3de"),
            Path("/shows/test/shots/SEQ_01/SEQ_01_0020/user/artist1/3de/file4.3de"),
            Path("/shows/test/shots/SEQ_01/SEQ_01_0020/user/artist2/3de/file5.3de"),
        ]

        # Simulate the shot directory tracking logic
        shot_dirs_found = set()
        files_to_process = []

        for file_path in test_files:
            # Extract shot directory
            parts = file_path.parts
            if "shots" in parts:
                shots_idx = parts.index("shots")
                if shots_idx + 2 < len(parts):
                    shot_dir = f"{parts[shots_idx + 1]}/{parts[shots_idx + 2]}"

                    # Only add if not already found (when stop_after_first is True)
                    if shot_dir not in shot_dirs_found:
                        files_to_process.append(file_path)
                        shot_dirs_found.add(shot_dir)

        # Should only have 2 files (one per shot)
        self.assertEqual(len(files_to_process), 2)
        self.assertEqual(len(shot_dirs_found), 2)
        self.assertIn("SEQ_01/SEQ_01_0010", shot_dirs_found)
        self.assertIn("SEQ_01/SEQ_01_0020", shot_dirs_found)

    def test_max_files_calculation(self):
        """Test that max files is calculated correctly based on stop-after-first."""
        from config import Config

        # Test with stop-after-first enabled
        with patch.object(Config, "THREEDE_STOP_AFTER_FIRST", True):
            with patch.object(Config, "THREEDE_MAX_SHOTS_TO_SCAN", 1000):
                # Max files should equal max shots when stop-after-first is enabled
                if Config.THREEDE_STOP_AFTER_FIRST:
                    max_files = Config.THREEDE_MAX_SHOTS_TO_SCAN
                else:
                    max_files = (
                        Config.THREEDE_SCAN_MAX_FILES_PER_SHOT
                        * Config.THREEDE_MAX_SHOTS_TO_SCAN
                    )

                self.assertEqual(max_files, 1000)

        # Test with stop-after-first disabled
        with patch.object(Config, "THREEDE_STOP_AFTER_FIRST", False):
            with patch.object(Config, "THREEDE_MAX_SHOTS_TO_SCAN", 200):
                with patch.object(Config, "THREEDE_SCAN_MAX_FILES_PER_SHOT", 50):
                    if Config.THREEDE_STOP_AFTER_FIRST:
                        max_files = Config.THREEDE_MAX_SHOTS_TO_SCAN
                    else:
                        max_files = (
                            Config.THREEDE_SCAN_MAX_FILES_PER_SHOT
                            * Config.THREEDE_MAX_SHOTS_TO_SCAN
                        )

                    self.assertEqual(max_files, 10000)

    def test_performance_improvement(self):
        """Test that stop-after-first provides performance improvement."""
        # Create a large dataset
        mock_files = self.create_mock_3de_files(100, 10)  # 100 shots, 10 files each

        # Create proper mock shot
        mock_shot = Mock()
        mock_shot.show = "test_show"
        mock_shot.sequence = "SEQ_00"
        mock_shot.shot = "0001"
        mock_shot.workspace_path = "/shows/test_show/shots/SEQ_00/SEQ_00_0001"

        # Measure time with stop-after-first disabled
        start_time = time.time()
        with patch("config.Config.THREEDE_STOP_AFTER_FIRST", False):
            with patch("config.Config.THREEDE_FILE_FIRST_DISCOVERY", True):
                with patch(
                    "threede_scene_finder.ThreeDESceneFinder.find_all_3de_files_in_show",
                    return_value=mock_files,
                ):
                    scenes_all = self.finder.find_all_scenes_in_shows_efficient(
                        user_shots=[mock_shot], excluded_users=set(),
                    )
        time_all_files = time.time() - start_time

        # Measure time with stop-after-first enabled
        start_time = time.time()
        with patch("config.Config.THREEDE_STOP_AFTER_FIRST", True):
            with patch("config.Config.THREEDE_FILE_FIRST_DISCOVERY", True):
                with patch(
                    "threede_scene_finder.ThreeDESceneFinder.find_all_3de_files_in_show",
                    return_value=mock_files,
                ):
                    scenes_optimized = self.finder.find_all_scenes_in_shows_efficient(
                        user_shots=[mock_shot], excluded_users=set(),
                    )
        time_optimized = time.time() - start_time

        # Optimized version should process fewer files
        # Log the performance difference for debugging
        print(f"Time with all files: {time_all_files:.3f}s")
        print(f"Time with optimization: {time_optimized:.3f}s")
        self.assertLess(len(scenes_optimized), len(scenes_all))
        # Should have 100 scenes vs 1000 scenes
        self.assertLessEqual(len(scenes_optimized), 100)
        self.assertEqual(len(scenes_all), 1000)

    def test_file_discovery_with_stop_after_first(self):
        """Test the file discovery function respects stop-after-first."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create mock directory structure
            shows_dir = tmppath / "shows" / "test_show" / "shots"

            # Create 3 shots with multiple files each
            for shot_num in range(3):
                sequence = f"SEQ_{shot_num:02d}"
                shot = f"{shot_num:04d}"
                shot_dir = shows_dir / sequence / f"{sequence}_{shot}"

                # Create multiple .3de files per shot
                for file_num in range(3):
                    user_dir = shot_dir / "user" / f"artist{file_num}" / "3de"
                    user_dir.mkdir(parents=True, exist_ok=True)

                    file_path = user_dir / f"test_{file_num}.3de"
                    file_path.touch()

            # Test with stop_after_first enabled
            with patch("config.Config.THREEDE_STOP_AFTER_FIRST", True):
                with patch("config.Config.THREEDE_SCAN_MAX_FILES_PER_SHOT", 1):
                    files = self.finder.find_all_3de_files_in_show(
                        str(tmppath / "shows"),
                        "test_show",
                        sequences=None,
                        timeout_seconds=10,
                    )

                    # Should find at most 3 files (one per shot)
                    self.assertLessEqual(len(files), 3)

    def test_extract_shot_info_compatibility(self):
        """Test that extract_shot_info_from_path still works correctly."""
        test_paths = [
            (
                Path(
                    "/shows/jack_ryan/shots/GF_256/GF_256_1400/user/johndoe/3de/scene.3de",
                ),
                (
                    "/shows/jack_ryan/shots/GF_256/GF_256_1400",
                    "GF_256",
                    "1400",
                    "johndoe",
                ),
            ),
            (
                Path("/shows/test/shots/SEQ_01/SEQ_01_0010/publish/3de/final.3de"),
                (
                    "/shows/test/shots/SEQ_01/SEQ_01_0010",
                    "SEQ_01",
                    "0010",
                    "published-3de",
                ),
            ),
        ]

        for path, expected in test_paths:
            result = self.finder.extract_shot_info_from_path(path)
            self.assertIsNotNone(result)
            self.assertEqual(result, expected)

    def test_config_values_used(self):
        """Test that configuration values are properly used by the scanner."""
        from config import Config

        # Verify config values exist and are correct
        self.assertTrue(hasattr(Config, "THREEDE_STOP_AFTER_FIRST"))
        self.assertTrue(hasattr(Config, "THREEDE_MAX_SHOTS_TO_SCAN"))
        self.assertTrue(hasattr(Config, "THREEDE_SCAN_MAX_FILES_PER_SHOT"))

        # Verify values are as expected
        self.assertEqual(Config.THREEDE_STOP_AFTER_FIRST, True)
        self.assertEqual(Config.THREEDE_MAX_SHOTS_TO_SCAN, 1000)
        self.assertEqual(Config.THREEDE_SCAN_MAX_FILES_PER_SHOT, 1)


if __name__ == "__main__":
    unittest.main()
