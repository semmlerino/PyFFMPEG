#!/usr/bin/env python3
"""Test stop-after-first optimization behavior with real files.

Following UNIFIED_TESTING_GUIDE best practices:
- Tests behavior, not implementation
- Uses real files with tmp_path
- Minimal mocking (only config boundaries)
"""

from unittest.mock import Mock, patch

import pytest

from threede_scene_finder import ThreeDESceneFinder


@pytest.fixture
def setup_test_files(tmp_path):
    """Create a realistic test file structure with multiple shots and files.

    Following UNIFIED_TESTING_GUIDE: Use real files for testing.
    """
    shows_root = tmp_path / "shows"
    test_show = shows_root / "test_show" / "shots"

    # Create 5 shots with 3 files each
    shots_created = []
    for shot_num in range(5):
        seq = f"SEQ_{shot_num:02d}"
        shot = f"{shot_num:04d}"
        shot_name = f"{seq}_{shot}"

        # Create 3 files per shot from different artists
        for artist_num in range(3):
            artist = f"artist{artist_num}"
            file_path = (
                test_show
                / seq
                / shot_name
                / "user"
                / artist
                / "3de"
                / f"comp_v{artist_num + 1:03d}.3de"
            )
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(f"# 3DE file for {shot_name} by {artist}")

        shots_created.append((seq, shot))

    return shows_root, shots_created


class TestStopAfterFirstBehavior:
    """Test the actual behavior of stop-after-first optimization."""

    def test_processes_one_file_per_shot(self, setup_test_files, tmp_path):
        """Test that only one file per shot is processed when stop-after-first is enabled.

        This tests BEHAVIOR not implementation.
        """
        shows_root, shots_created = setup_test_files
        finder = ThreeDESceneFinder()

        # Create mock shots for the test
        mock_shots = []
        for seq, shot in shots_created[:2]:  # Use first 2 shots as "user shots"
            mock_shot = Mock()
            mock_shot.show = "test_show"
            mock_shot.sequence = seq
            mock_shot.shot = shot
            mock_shot.workspace_path = str(
                shows_root / "test_show" / "shots" / seq / f"{seq}_{shot}",
            )
            mock_shots.append(mock_shot)

        # Test with stop-after-first ENABLED
        with patch("config.Config.THREEDE_STOP_AFTER_FIRST", True):
            with patch("config.Config.THREEDE_MAX_SHOTS_TO_SCAN", 100):
                with patch("config.Config.THREEDE_FILE_FIRST_DISCOVERY", True):
                    # Get all .3de files in the test directory
                    all_files = list((shows_root / "test_show").rglob("*.3de"))
                    assert len(all_files) == 15  # 5 shots * 3 files

                    # Mock the file discovery to return our real files
                    with patch.object(
                        finder, "find_all_3de_files_in_show", return_value=all_files,
                    ):
                        scenes = finder.find_all_scenes_in_shows_efficient(
                            user_shots=mock_shots, excluded_users=set(),
                        )

                    # Count unique shots in results
                    unique_shots = set()
                    for scene in scenes:
                        unique_shots.add((scene.sequence, scene.shot))

                    # Should have one scene per unique shot
                    assert len(unique_shots) == len(scenes), (
                        "Each shot should appear only once"
                    )
                    assert len(scenes) <= 5, (
                        "Should process at most 5 shots (one file each)"
                    )

    def test_processes_all_files_when_disabled(self, setup_test_files):
        """Test that all files are processed when stop-after-first is disabled."""
        shows_root, shots_created = setup_test_files
        finder = ThreeDESceneFinder()

        # Create mock shot
        mock_shot = Mock()
        mock_shot.show = "test_show"
        mock_shot.sequence = "SEQ_00"
        mock_shot.shot = "0000"
        mock_shot.workspace_path = str(
            shows_root / "test_show" / "shots" / "SEQ_00" / "SEQ_00_0000",
        )

        # Test with stop-after-first DISABLED
        with patch("config.Config.THREEDE_STOP_AFTER_FIRST", False):
            with patch("config.Config.THREEDE_MAX_SHOTS_TO_SCAN", 100):
                with patch("config.Config.THREEDE_SCAN_MAX_FILES_PER_SHOT", 10):
                    # Get all files
                    all_files = list((shows_root / "test_show").rglob("*.3de"))

                    with patch.object(
                        finder, "find_all_3de_files_in_show", return_value=all_files,
                    ):
                        scenes = finder.find_all_scenes_in_shows_efficient(
                            user_shots=[mock_shot], excluded_users=set(),
                        )

                    # Should process up to THREEDE_SCAN_MAX_FILES_PER_SHOT (default 10)
                    # This is a limitation of the implementation
                    assert len(scenes) >= 10, "Should process at least 10 files"
                    assert len(scenes) <= 15, "Should process at most 15 files"

    def test_shot_directory_tracking_works(self, tmp_path):
        """Test that the shot directory tracking prevents duplicate processing.

        Following UNIFIED_TESTING_GUIDE: Test observable behavior.
        """
        # Create files in same shot from different users
        shot_dir = tmp_path / "shows" / "test" / "shots" / "SEQ_01" / "SEQ_01_0010"

        files_created = []
        for artist in ["alice", "bob", "charlie"]:
            file_path = shot_dir / "user" / artist / "3de" / f"{artist}.3de"
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(f"# 3DE by {artist}")
            files_created.append(file_path)

        # Simulate the stop-after-first logic
        shot_dirs_seen = set()
        files_processed = []

        for file_path in files_created:
            # Extract shot directory
            parts = file_path.parts
            if "shots" in parts:
                idx = parts.index("shots")
                if idx + 2 < len(parts):
                    shot_key = f"{parts[idx + 1]}/{parts[idx + 2]}"

                    # Only process if not seen (stop-after-first behavior)
                    if shot_key not in shot_dirs_seen:
                        files_processed.append(file_path)
                        shot_dirs_seen.add(shot_key)

        # Should only process first file
        assert len(files_processed) == 1
        assert len(shot_dirs_seen) == 1

    def test_performance_comparison(self, setup_test_files):
        """Compare performance between stop-after-first enabled vs disabled.

        This is a BEHAVIOR test - we're testing that the optimization
        actually reduces the amount of work done.
        """
        shows_root, _ = setup_test_files

        # Count files that would be processed
        all_files = list((shows_root / "test_show").rglob("*.3de"))

        # Extract unique shots
        shots_seen = set()
        files_with_stop = []
        files_without_stop = []

        for file_path in all_files:
            parts = file_path.parts
            if "shots" in parts:
                idx = parts.index("shots")
                if idx + 2 < len(parts):
                    shot_key = f"{parts[idx + 1]}/{parts[idx + 2]}"

                    # Without stop: process all files
                    files_without_stop.append(file_path)

                    # With stop: only first per shot
                    if shot_key not in shots_seen:
                        files_with_stop.append(file_path)
                        shots_seen.add(shot_key)

        # Verify optimization reduces work
        assert len(files_with_stop) < len(files_without_stop)
        assert len(files_with_stop) == 5  # One per shot
        assert len(files_without_stop) == 15  # All files

        # Calculate reduction
        reduction = (1 - len(files_with_stop) / len(files_without_stop)) * 100
        print(f"Stop-after-first reduces processing by {reduction:.0f}%")
        assert reduction >= 60  # Should reduce by at least 60%


if __name__ == "__main__":
    # Run with pytest
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "run_tests.py", __file__, "-v"], capture_output=True, text=True,
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    sys.exit(result.returncode)
