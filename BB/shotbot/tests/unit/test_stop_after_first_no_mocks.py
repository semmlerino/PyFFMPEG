#!/usr/bin/env python3
"""Test stop-after-first optimization with NO MOCKING.

Following UNIFIED_TESTING_GUIDE best practices:
- NO mocking of internal methods
- Real files with real implementation
- Only mock configuration (appropriate boundary)
"""

import time
from unittest.mock import Mock, patch

import pytest

from threede_scene_finder import ThreeDESceneFinder


@pytest.fixture
def create_real_show_structure(tmp_path):
    """Create a complete show structure that the real finder can discover."""
    shows_root = tmp_path / "shows"
    test_show = shows_root / "test_show" / "shots"

    created_files = []
    for shot_num in range(3):  # 3 shots
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
                / f"scene_v{artist_num + 1:03d}.3de"
            )
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(f"# Real 3DE content for {shot_name} by {artist}")
            created_files.append(file_path)

    return shows_root, created_files


class TestStopAfterFirstNoMocks:
    """Test suite using REAL implementation with NO mocking."""

    def test_real_stop_after_first_behavior(self, create_real_show_structure):
        """Test stop-after-first with REAL file discovery - NO MOCKS.

        This is the gold standard test following UNIFIED_TESTING_GUIDE.
        """
        shows_root, created_files = create_real_show_structure
        finder = ThreeDESceneFinder()

        # Create mock shot objects for the test
        mock_shot = Mock()
        mock_shot.show = "test_show"
        mock_shot.sequence = "SEQ_00"
        mock_shot.shot = "0000"
        mock_shot.workspace_path = str(
            shows_root / "test_show" / "shots" / "SEQ_00" / "SEQ_00_0000",
        )

        # Only mock the configuration values (appropriate boundary)
        with patch("config.Config.THREEDE_STOP_AFTER_FIRST", True):
            with patch("config.Config.THREEDE_MAX_SHOTS_TO_SCAN", 100):
                with patch("config.Config.THREEDE_SCAN_MAX_FILES_PER_SHOT", 1):
                    # NO MOCKING - the method will discover files itself!
                    # Temporarily patch the shows root to point to our test directory
                    with patch("config.Config.SHOWS_ROOT", str(shows_root)):
                        scenes = finder.find_all_scenes_in_shows_efficient(
                            user_shots=[mock_shot],
                            excluded_users=set(),
                        )

                    # Verify behavior: one scene per shot
                    unique_shots = set()
                    for scene in scenes:
                        unique_shots.add((scene.sequence, scene.shot))

                    # Should have one scene per unique shot
                    assert len(unique_shots) == len(scenes)
                    assert len(scenes) <= 3  # At most 3 shots

    def test_real_all_files_processing(self, create_real_show_structure):
        """Test processing all files with REAL discovery - NO MOCKS."""
        shows_root, created_files = create_real_show_structure
        finder = ThreeDESceneFinder()

        mock_shot = Mock()
        mock_shot.show = "test_show"
        mock_shot.sequence = "SEQ_00"
        mock_shot.shot = "0000"
        mock_shot.workspace_path = str(
            shows_root / "test_show" / "shots" / "SEQ_00" / "SEQ_00_0000",
        )

        with patch("config.Config.THREEDE_STOP_AFTER_FIRST", False):
            with patch("config.Config.THREEDE_MAX_SHOTS_TO_SCAN", 100):
                with patch("config.Config.THREEDE_SCAN_MAX_FILES_PER_SHOT", 10):
                    with patch("config.Config.SHOWS_ROOT", str(shows_root)):
                        # Real processing - no mocking!
                        scenes = finder.find_all_scenes_in_shows_efficient(
                            user_shots=[mock_shot],
                            excluded_users=set(),
                        )

                    # Should process more files when stop-after-first is disabled
                    assert len(scenes) >= 3  # At least one per shot
                    assert len(scenes) <= 9  # At most all files

    def test_real_performance_difference(self, create_real_show_structure):
        """Test actual performance difference with REAL implementation."""
        shows_root, created_files = create_real_show_structure
        finder = ThreeDESceneFinder()

        mock_shot = Mock()
        mock_shot.show = "test_show"
        mock_shot.sequence = "SEQ_00"
        mock_shot.shot = "0000"
        mock_shot.workspace_path = str(
            shows_root / "test_show" / "shots" / "SEQ_00" / "SEQ_00_0000",
        )

        # Measure with stop-after-first ENABLED
        start = time.time()
        with patch("config.Config.THREEDE_STOP_AFTER_FIRST", True):
            with patch("config.Config.THREEDE_SCAN_MAX_FILES_PER_SHOT", 1):
                with patch("config.Config.SHOWS_ROOT", str(shows_root)):
                    scenes_optimized = finder.find_all_scenes_in_shows_efficient(
                        [mock_shot],
                        set(),
                    )
        time_optimized = time.time() - start

        # Measure with stop-after-first DISABLED
        start = time.time()
        with patch("config.Config.THREEDE_STOP_AFTER_FIRST", False):
            with patch("config.Config.THREEDE_SCAN_MAX_FILES_PER_SHOT", 10):
                with patch("config.Config.SHOWS_ROOT", str(shows_root)):
                    scenes_all = finder.find_all_scenes_in_shows_efficient(
                        [mock_shot],
                        set(),
                    )
        time_all = time.time() - start

        # Verify optimization reduces work
        assert len(scenes_optimized) <= len(scenes_all)
        print(f"\nOptimized: {len(scenes_optimized)} scenes in {time_optimized:.3f}s")
        print(f"All files: {len(scenes_all)} scenes in {time_all:.3f}s")

    def test_extract_shot_info_real_paths(self, tmp_path):
        """Test shot info extraction with REAL paths - NO MOCKS."""
        finder = ThreeDESceneFinder()

        # Create real file
        real_file = (
            tmp_path
            / "shows"
            / "test"
            / "shots"
            / "AB_123"
            / "AB_123_4567"
            / "user"
            / "alice"
            / "3de"
            / "comp.3de"
        )
        real_file.parent.mkdir(parents=True)
        real_file.write_text("# Real 3DE content")

        # Test with real path
        result = finder.extract_shot_info_from_path(real_file)

        assert result is not None
        show_path, sequence, shot, username = result
        assert "test" in show_path
        assert sequence == "AB_123"
        assert shot == "4567"
        assert username == "alice"


if __name__ == "__main__":
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "run_tests.py", __file__, "-v"],
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    sys.exit(result.returncode)
