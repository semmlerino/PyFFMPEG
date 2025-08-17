"""Integration tests for 3DE scanner with deep nesting support.

This test suite creates real directory structures to test the scanner's ability
to find .3de files in deeply nested VFX pipeline structures.
"""

import os
import subprocess
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from threede_scene_finder import ThreeDESceneFinder


class Test3DEScennerDeepNesting:
    """Test 3DE scanner with realistic deep directory structures."""

    @pytest.fixture
    def deep_shot_structure(self, tmp_path):
        """Create a realistic VFX shot structure with deeply nested .3de files.

        Based on real example:
        /shows/jack_ryan/shots/GF_256/GF_256_0020/user/ryan-p/mm/3de/mm-default/scenes/scene/FG01/GF_256_0020_mm_default_FG01_scene_v001.3de
        """
        show_root = tmp_path / "shows"

        # Test data structure
        test_structure = {
            "jack_ryan": {
                "shots": {
                    "GF_256": {
                        "GF_256_0020": {
                            "user": {
                                "ryan-p": {
                                    # Deep nesting - 6 levels deep from user
                                    "mm/3de/mm-default/scenes/scene/FG01": [
                                        "GF_256_0020_mm_default_FG01_scene_v001.3de",
                                        "GF_256_0020_mm_default_FG01_scene_v002.3de",
                                    ],
                                    "mm/3de/mm-default/scenes/scene/BG01": [
                                        "GF_256_0020_mm_default_BG01_scene_v001.3de",
                                    ],
                                },
                                "kate-b": {
                                    # Different structure - 5 levels deep
                                    "matchmove/3de/scenes/FG01/finals": [
                                        "GF_256_0020_FG01_final.3de",
                                    ],
                                },
                                "john-d": {
                                    # Even deeper - 7 levels
                                    "tracking/3de/projects/2024/november/week3/FG01": [
                                        "GF_256_0020_tracking_v001.3DE",  # Uppercase extension
                                    ],
                                },
                                "excluded-user": {
                                    # This user should be excluded
                                    "mm/3de": [
                                        "should_not_find.3de",
                                    ],
                                },
                                "alice-w": {
                                    # No .3de files - empty directories
                                    "mm/3de/empty": [],
                                },
                            },
                        },
                    },
                    "DB_256": {
                        "DB_256_1200": {
                            "user": {
                                "sarah-m": {
                                    # Moderate nesting - 3 levels
                                    "3de/scenes/hero": [
                                        "DB_256_1200_hero_v001.3de",
                                        "DB_256_1200_hero_v002.3de",
                                    ],
                                },
                            },
                        },
                    },
                },
            },
            "gator": {
                "shots": {
                    "012_DC": {
                        "012_DC_1000": {
                            "user": {
                                "mike-r": {
                                    # Standard nesting
                                    "mm/3de": [
                                        "012_DC_1000_main.3de",
                                    ],
                                },
                            },
                        },
                    },
                },
            },
        }

        # Create the directory structure and files
        def create_structure(base_path: Path, structure: dict):
            """Recursively create directory structure with files."""
            for key, value in structure.items():
                if isinstance(value, dict):
                    # It's a directory - create and recurse
                    dir_path = base_path / key
                    dir_path.mkdir(parents=True, exist_ok=True)
                    create_structure(dir_path, value)
                elif isinstance(value, list):
                    # It's a directory with files
                    dir_path = base_path / key
                    dir_path.mkdir(parents=True, exist_ok=True)
                    for filename in value:
                        file_path = dir_path / filename
                        # Create actual file with some content
                        file_path.write_text(f"3DE scene file: {filename}\n")

        create_structure(show_root, test_structure)

        return {
            "root": show_root,
            "show_root": show_root,
            "jack_ryan_shot": show_root
            / "jack_ryan"
            / "shots"
            / "GF_256"
            / "GF_256_0020",
            "db_shot": show_root / "DB_256" / "DB_256_1200",
            "gator_shot": show_root / "gator" / "shots" / "012_DC" / "012_DC_1000",
        }

    def test_find_deeply_nested_3de_files(self, deep_shot_structure):
        """Test finding .3de files nested 6+ levels deep."""
        shot_path = str(deep_shot_structure["jack_ryan_shot"])

        # Find scenes for the shot (excluding the test user)
        scenes = ThreeDESceneFinder.find_scenes_for_shot(
            shot_workspace_path=shot_path,
            show="jack_ryan",
            sequence="GF_256",
            shot="0020",
            excluded_users={"excluded-user"},
        )

        # Should find files from ryan-p, kate-b, and john-d (not excluded-user or alice-w)
        assert len(scenes) > 0, "Should find at least some .3de files"

        # Check specific users are found
        users_found = {scene.user for scene in scenes}
        assert "ryan-p" in users_found, "Should find ryan-p's deeply nested files"
        assert "kate-b" in users_found, "Should find kate-b's files"
        assert "john-d" in users_found, "Should find john-d's very deep files"
        assert "excluded-user" not in users_found, (
            "Should not find excluded user's files"
        )
        assert "alice-w" not in users_found, "Should not find users with no .3de files"

        # Check ryan-p has multiple files
        ryan_scenes = [s for s in scenes if s.user == "ryan-p"]
        assert len(ryan_scenes) == 3, (
            f"Should find 3 files for ryan-p, found {len(ryan_scenes)}"
        )

        # Check plate extraction works
        plates_found = {s.plate for s in ryan_scenes}
        assert "FG01" in plates_found, "Should extract FG01 plate"
        assert "BG01" in plates_found, "Should extract BG01 plate"

        # Check uppercase extension is found
        john_scenes = [s for s in scenes if s.user == "john-d"]
        assert len(john_scenes) == 1, "Should find .3DE (uppercase) file"

    def test_find_command_performance(self, deep_shot_structure, monkeypatch):
        """Test that find command is used and performs well."""
        shot_path = str(deep_shot_structure["jack_ryan_shot"])

        # Ensure find command is enabled
        monkeypatch.setenv("SHOTBOT_USE_FIND", "true")

        # Time the operation
        start_time = time.time()
        scenes = ThreeDESceneFinder.find_scenes_for_shot(
            shot_workspace_path=shot_path,
            show="jack_ryan",
            sequence="GF_256",
            shot="0020",
            excluded_users=set(),
        )
        elapsed = time.time() - start_time

        # Should be fast even with deep nesting
        assert elapsed < 5.0, f"Should complete in under 5 seconds, took {elapsed:.2f}s"
        assert len(scenes) > 0, "Should find files with find command"

        # Verify all expected files are found
        filenames = {s.scene_path.name for s in scenes}
        expected_files = {
            "GF_256_0020_mm_default_FG01_scene_v001.3de",
            "GF_256_0020_mm_default_FG01_scene_v002.3de",
            "GF_256_0020_mm_default_BG01_scene_v001.3de",
            "GF_256_0020_FG01_final.3de",
            "GF_256_0020_tracking_v001.3DE",
            "should_not_find.3de",  # Not excluded in this test
        }
        assert filenames == expected_files, (
            f"Missing files: {expected_files - filenames}"
        )

    def test_rglob_fallback(self, deep_shot_structure, monkeypatch):
        """Test that rglob fallback works when find command is disabled."""
        shot_path = str(deep_shot_structure["jack_ryan_shot"])

        # Disable find command to force rglob
        monkeypatch.setenv("SHOTBOT_USE_FIND", "false")

        scenes = ThreeDESceneFinder.find_scenes_for_shot(
            shot_workspace_path=shot_path,
            show="jack_ryan",
            sequence="GF_256",
            shot="0020",
            excluded_users={"excluded-user"},
        )

        # Should still find all files with rglob
        assert len(scenes) > 0, "Should find files with rglob fallback"
        users_found = {scene.user for scene in scenes}
        assert "ryan-p" in users_found, "rglob should find deeply nested files"

    def test_common_pattern_optimization(
        self, deep_shot_structure, monkeypatch, caplog,
    ):
        """Test that common patterns are checked first for efficiency."""
        shot_path = str(deep_shot_structure["jack_ryan_shot"])

        # Disable find to test rglob optimization
        monkeypatch.setenv("SHOTBOT_USE_FIND", "false")

        import logging

        caplog.set_level(logging.DEBUG)

        ThreeDESceneFinder.find_scenes_for_shot(
            shot_workspace_path=shot_path,
            show="jack_ryan",
            sequence="GF_256",
            shot="0020",
            excluded_users=set(),
        )

        # Check that common paths were checked
        assert any(
            "Checking common path" in record.message for record in caplog.records
        ), "Should check common paths first"
        assert any(
            "mm/3de" in record.message or "matchmove/3de" in record.message
            for record in caplog.records
        ), "Should check known patterns"

    def test_progressive_scan_batching(self, deep_shot_structure, monkeypatch):
        """Test progressive scanning with batch processing."""
        shot_path = deep_shot_structure["jack_ryan_shot"]
        user_path = shot_path / "user" / "ryan-p"

        # Temporarily reduce minimum batch size for testing
        from config import Config

        monkeypatch.setattr(Config, "PROGRESSIVE_SCAN_MIN_BATCH_SIZE", 1)

        # Use the progressive scanner
        batches_received = []
        total_scenes = 0

        for batch in ThreeDESceneFinder.find_scenes_progressive(
            user_path=user_path,
            show="jack_ryan",
            sequence="GF_256",
            shot="0020",
            user_name="ryan-p",
            batch_size=2,  # Small batch size to test batching
        ):
            batches_received.append(batch)
            total_scenes += len(batch)

        # Should receive multiple batches
        assert len(batches_received) >= 2, (
            f"Should receive multiple batches with batch_size=2, got {len(batches_received)}"
        )
        assert total_scenes == 3, (
            f"Should find 3 total scenes for ryan-p, found {total_scenes}"
        )

        # Each batch should be <= batch_size
        for i, batch in enumerate(batches_received[:-1]):  # All but last batch
            assert len(batch) <= 2, f"Batch {i} size should be <= 2, got {len(batch)}"

    def test_show_wide_discovery(self, deep_shot_structure):
        """Test discovering all shots in a show."""
        show_root = str(deep_shot_structure["show_root"])

        # Discover all shots in jack_ryan show
        shots = ThreeDESceneFinder.discover_all_shots_in_show(
            show_root=show_root, show="jack_ryan",
        )

        # Should find both shots
        assert len(shots) == 2, f"Should find 2 shots in jack_ryan, found {len(shots)}"

        # Check shot details
        shot_names = {(s[2], s[3]) for s in shots}  # (sequence, shot)
        assert ("GF_256", "GF_256_0020") in shot_names
        assert ("DB_256", "DB_256_1200") in shot_names

    def test_multiple_shows(self, deep_shot_structure):
        """Test finding scenes across multiple shows."""
        show_root = str(deep_shot_structure["show_root"])

        # Create list of all shots from both shows
        shots = []
        for show in ["jack_ryan", "gator"]:
            show_shots = ThreeDESceneFinder.discover_all_shots_in_show(
                show_root=show_root, show=show,
            )
            shots.extend(show_shots)

        # Find all scenes
        all_scenes = ThreeDESceneFinder.find_all_scenes(
            shots=shots, excluded_users={"excluded-user"},
        )

        # Should find scenes from both shows
        shows_found = {scene.show for scene in all_scenes}
        assert "jack_ryan" in shows_found
        assert "gator" in shows_found

        # Count total scenes
        assert len(all_scenes) >= 7, (
            f"Should find at least 7 scenes total, found {len(all_scenes)}"
        )

    def test_find_command_timeout(self, deep_shot_structure, monkeypatch):
        """Test that find command respects timeout."""
        shot_path = str(deep_shot_structure["jack_ryan_shot"])

        # Mock subprocess.run to simulate timeout
        original_run = subprocess.run

        def mock_run(*args, **kwargs):
            if "find" in args[0]:
                raise subprocess.TimeoutExpired(args[0], kwargs.get("timeout", 30))
            return original_run(*args, **kwargs)

        with patch("subprocess.run", side_effect=mock_run):
            # Should fall back to rglob and still work
            scenes = ThreeDESceneFinder.find_scenes_for_shot(
                shot_workspace_path=shot_path,
                show="jack_ryan",
                sequence="GF_256",
                shot="0020",
                excluded_users=set(),
            )

            # Should still find files via rglob fallback
            assert len(scenes) > 0, "Should find files even when find times out"

    def test_permission_errors(self, deep_shot_structure, monkeypatch):
        """Test handling of permission errors."""
        shot_path = deep_shot_structure["jack_ryan_shot"]
        restricted_dir = shot_path / "user" / "restricted-user"
        restricted_dir.mkdir(parents=True)

        # Create a file that we'll make inaccessible
        restricted_file = restricted_dir / "mm" / "3de" / "test.3de"
        restricted_file.parent.mkdir(parents=True)
        restricted_file.write_text("restricted")

        # Make directory inaccessible (Unix-like systems only)
        if os.name != "nt":  # Skip on Windows
            os.chmod(restricted_dir, 0o000)

            try:
                # Should handle permission error gracefully
                scenes = ThreeDESceneFinder.find_scenes_for_shot(
                    shot_workspace_path=str(shot_path),
                    show="jack_ryan",
                    sequence="GF_256",
                    shot="0020",
                    excluded_users=set(),
                )

                # Should still find other users' files
                users_found = {scene.user for scene in scenes}
                assert "ryan-p" in users_found
                assert "restricted-user" not in users_found

            finally:
                # Restore permissions for cleanup
                os.chmod(restricted_dir, 0o755)

    def test_empty_directories(self, deep_shot_structure):
        """Test handling of users with deep directory structures but no .3de files."""
        shot_path = str(deep_shot_structure["jack_ryan_shot"])

        # alice-w has directory structure but no files
        scenes = ThreeDESceneFinder.find_scenes_for_shot(
            shot_workspace_path=shot_path,
            show="jack_ryan",
            sequence="GF_256",
            shot="0020",
            excluded_users={
                "ryan-p",
                "kate-b",
                "john-d",
                "excluded-user",
            },  # Only check alice-w
        )

        # Should handle empty directories gracefully
        assert len(scenes) == 0, "Should find no scenes for user with empty directories"

    @pytest.mark.parametrize("max_depth", [1, 3, 5, 10, 15])
    def test_various_nesting_depths(self, tmp_path, max_depth):
        """Test scanner with various nesting depths."""
        # Create proper shot structure
        shot_path = tmp_path / "shot_workspace"
        user_base = shot_path / "user" / "test-user"

        # Build path with specified depth
        deep_path = user_base
        for i in range(max_depth):
            deep_path = deep_path / f"level_{i}"

        deep_path.mkdir(parents=True)
        test_file = deep_path / f"test_depth_{max_depth}.3de"
        test_file.write_text(f"Test at depth {max_depth}")

        # Find scenes
        scenes = ThreeDESceneFinder.find_scenes_for_shot(
            shot_workspace_path=str(shot_path),
            show="test_show",
            sequence="test_seq",
            shot="test_shot",
            excluded_users=set(),
        )

        # Should find file at any depth up to our limit (15)
        if max_depth <= 15:
            assert len(scenes) == 1, f"Should find file at depth {max_depth}"
            assert scenes[0].scene_path.name == f"test_depth_{max_depth}.3de"
