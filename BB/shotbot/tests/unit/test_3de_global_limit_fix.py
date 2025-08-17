#!/usr/bin/env python3
"""Test that the 3DE finder correctly handles max_files limit.

This test verifies the fix for the bug where THREEDE_SCAN_MAX_FILES_PER_SHOT
was being used as a global file limit instead of a per-shot limit.
"""

from unittest.mock import patch

from threede_scene_finder import ThreeDESceneFinder


class TestThreeDEGlobalLimitFix:
    """Test that 3DE discovery finds 1 file per shot, not 1 file globally."""

    def test_finds_one_file_per_shot_not_one_global(self, tmp_path):
        """Test that stop_after_first finds 1 file per shot for multiple shots.

        Bug: When THREEDE_SCAN_MAX_FILES_PER_SHOT=1 and THREEDE_STOP_AFTER_FIRST=True,
        the finder was stopping after finding 1 file GLOBALLY instead of 1 per shot.

        Fix: Changed max_files calculation in find_all_3de_files_in_show_python to use
        THREEDE_MAX_SHOTS_TO_SCAN when stop_after_first is True.
        """
        # Create test show structure with 5 shots, 3 files each
        shows_root = tmp_path / "shows"
        test_show = shows_root / "test_show" / "shots"

        # Create 5 shots with 3 .3de files each
        shot_names = []
        for seq_num in range(2):  # 2 sequences
            seq_name = f"seq{seq_num:02d}"
            for shot_num in range(3):  # 3 shots per sequence (6 total)
                shot_name = f"{seq_name}_00{shot_num}0"
                shot_names.append(shot_name)

                shot_path = test_show / seq_name / shot_name / "mm"
                shot_path.mkdir(parents=True)

                # Create 3 .3de files per shot
                for file_num in range(3):
                    file_path = shot_path / f"scene_v{file_num:03d}.3de"
                    file_path.write_text(f"# 3DE file {file_num}")

        # Mock config with the problematic settings
        with patch("config.Config.SHOWS_ROOT", str(shows_root)), patch(
            "config.Config.THREEDE_SCAN_MAX_FILES_PER_SHOT", 1
        ), patch("config.Config.THREEDE_STOP_AFTER_FIRST", True), patch(
            "config.Config.THREEDE_MAX_SHOTS_TO_SCAN", 1000
        ):
            # Test Python pathlib implementation
            files = ThreeDESceneFinder.find_all_3de_files_in_show_python(
                show_root=str(shows_root),
                show="test_show",
                sequences=None,
                timeout_seconds=30,
            )

            # Extract unique shots from the found files
            unique_shots = set()
            for file_path in files:
                parts = file_path.parts
                if "shots" in parts:
                    shots_idx = parts.index("shots")
                    if shots_idx + 2 < len(parts):
                        shot_name = parts[shots_idx + 2]
                        unique_shots.add(shot_name)

            # CRITICAL ASSERTION: Should find 1 file per shot for MULTIPLE shots
            # Before the fix: Would find only 1 file total (bug)
            # After the fix: Should find 1 file per shot (6 files for 6 shots)
            assert len(files) >= 6, (
                f"Should find at least 6 files (1 per shot), found {len(files)}"
            )
            assert len(unique_shots) >= 6, (
                f"Should find files from at least 6 shots, found {len(unique_shots)}"
            )

            # Verify stop_after_first works: no shot should have more than 1 file
            shot_file_counts = {}
            for file_path in files:
                parts = file_path.parts
                if "shots" in parts:
                    shots_idx = parts.index("shots")
                    if shots_idx + 2 < len(parts):
                        shot_name = parts[shots_idx + 2]
                        shot_file_counts[shot_name] = (
                            shot_file_counts.get(shot_name, 0) + 1
                        )

            for shot, count in shot_file_counts.items():
                assert count == 1, (
                    f"Shot {shot} should have exactly 1 file, has {count}"
                )

    def test_respects_max_shots_limit(self, tmp_path):
        """Test that the finder respects THREEDE_MAX_SHOTS_TO_SCAN limit."""
        # Create test show with 10 shots
        shows_root = tmp_path / "shows"
        test_show = shows_root / "test_show" / "shots"

        for i in range(10):
            shot_path = test_show / f"seq{i:02d}" / f"seq{i:02d}_0010" / "mm"
            shot_path.mkdir(parents=True)
            (shot_path / "scene.3de").write_text("# 3DE file")

        # Test with max_shots limit of 5
        with patch("config.Config.SHOWS_ROOT", str(shows_root)), patch(
            "config.Config.THREEDE_STOP_AFTER_FIRST", True
        ), patch("config.Config.THREEDE_MAX_SHOTS_TO_SCAN", 5):
            files = ThreeDESceneFinder.find_all_3de_files_in_show_python(
                show_root=str(shows_root),
                show="test_show",
                sequences=None,
                timeout_seconds=30,
            )

            # Should find at most 5 files (1 per shot, max 5 shots)
            assert len(files) <= 5, f"Should find at most 5 files, found {len(files)}"


if __name__ == "__main__":
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "run_tests.py", __file__, "-v"], capture_output=True, text=True
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    sys.exit(result.returncode)
