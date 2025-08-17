"""Test that 3DE scanner properly handles published files."""

from pathlib import Path

import pytest

from threede_scene_finder import ThreeDESceneFinder
from threede_scene_model import ThreeDEScene


class TestPublished3DEFiles:
    """Test scanning for published 3DE files."""

    @pytest.fixture
    def published_file_structure(self, tmp_path):
        """Create a structure with both published and user 3DE files."""
        show_root = tmp_path / "shows"

        # Create structure with published files
        # Pattern from logs: /shows/gator/shots/019_JF/019_JF_1080/publish/mm/default/bg01/lens_distortion/v001/3de/
        shot_path = show_root / "gator" / "shots" / "019_JF" / "019_JF_1080"

        # Published files (as seen in logs)
        publish_path = (
            shot_path
            / "publish"
            / "mm"
            / "default"
            / "bg01"
            / "lens_distortion"
            / "v001"
            / "3de"
        )
        publish_path.mkdir(parents=True)
        (publish_path / "019_JF_1080_mm-default_bg01_v001.3de").write_text(
            "Published 3DE file",
        )

        # Also create v002
        publish_path2 = (
            shot_path
            / "publish"
            / "mm"
            / "default"
            / "bg01"
            / "lens_distortion"
            / "v002"
            / "3de"
        )
        publish_path2.mkdir(parents=True)
        (publish_path2 / "019_JF_1080_mm-default_bg01_v002.3de").write_text(
            "Published 3DE v2",
        )

        # User workspace files
        user_path = shot_path / "user" / "john-d" / "mm" / "3de" / "scenes"
        user_path.mkdir(parents=True)
        (user_path / "019_JF_1080_user_work.3de").write_text("User 3DE file")

        # Another shot with only published files
        shot2_path = show_root / "gator" / "shots" / "008_AC" / "008_AC_1320"
        publish2_path = (
            shot2_path
            / "publish"
            / "mm"
            / "default"
            / "bg01"
            / "lens_distortion"
            / "v001"
            / "3de"
        )
        publish2_path.mkdir(parents=True)
        (publish2_path / "008_AC_1320_mm-default_bg01_v001.3de").write_text(
            "Published only",
        )

        # Create user directory but no 3DE files (for validation)
        user2_path = shot2_path / "user" / "empty-user"
        user2_path.mkdir(parents=True)

        return {
            "show_root": show_root,
            "shot1_path": shot_path,
            "shot2_path": shot2_path,
        }

    def test_extract_shot_info_from_published_path(self, published_file_structure):
        """Test that extract_shot_info_from_path handles published paths."""
        publish_path = Path(
            "//shows/gator/shots/019_JF/019_JF_1080/publish/mm/default/bg01/lens_distortion/v001/3de/019_JF_1080_mm-default_bg01_v001.3de",
        )

        shot_info = ThreeDESceneFinder.extract_shot_info_from_path(publish_path)

        assert shot_info is not None, "Should extract info from published path"
        workspace_path, sequence, shot, username = shot_info

        assert sequence == "019_JF"
        assert shot == "019_JF_1080"
        assert username == "published-mm", f"Expected 'published-mm', got '{username}'"
        assert workspace_path.endswith("019_JF_1080")

    def test_extract_shot_info_from_user_path(self):
        """Test that extract_shot_info_from_path still handles user paths."""
        user_path = Path(
            "/shows/jack_ryan/shots/GF_256/GF_256_0020/user/ryan-p/mm/3de/GF_256_0020_scene.3de",
        )

        shot_info = ThreeDESceneFinder.extract_shot_info_from_path(user_path)

        assert shot_info is not None, "Should extract info from user path"
        workspace_path, sequence, shot, username = shot_info

        assert sequence == "GF_256"
        assert shot == "GF_256_0020"
        assert username == "ryan-p"
        assert workspace_path.endswith("GF_256_0020")

    def test_find_published_files_in_shot(self, published_file_structure):
        """Test that published files are found when scanning a shot."""
        shot1_path = str(published_file_structure["shot1_path"])

        # Find all files (including published)
        all_files = []
        for ext in ["*.3de", "*.3DE"]:
            all_files.extend(Path(shot1_path).rglob(ext))

        # Should find both published and user files
        assert len(all_files) == 3, (
            f"Should find 3 files (2 published + 1 user), found {len(all_files)}"
        )

        # Check that published files are included
        published_files = [f for f in all_files if "/publish/" in str(f)]
        assert len(published_files) == 2, (
            f"Should find 2 published files, found {len(published_files)}"
        )

        user_files = [f for f in all_files if "/user/" in str(f)]
        assert len(user_files) == 1, f"Should find 1 user file, found {len(user_files)}"

    def test_published_files_not_excluded(self, published_file_structure):
        """Test that published files are not excluded even when username filtering is active."""
        str(published_file_structure["show_root"])

        # Create mock shot list
        shots = [
            (
                str(published_file_structure["shot1_path"]),
                "gator",
                "019_JF",
                "019_JF_1080",
            ),
            (
                str(published_file_structure["shot2_path"]),
                "gator",
                "008_AC",
                "008_AC_1320",
            ),
        ]

        # Test with excluded users (should not affect published files)
        excluded_users = {"john-d", "empty-user"}  # Exclude the actual user

        all_scenes = []
        for workspace_path, show, sequence, shot in shots:
            # Find all .3de files in the shot
            shot_path = Path(workspace_path)
            threede_files = list(shot_path.rglob("*.3de"))
            threede_files.extend(list(shot_path.rglob("*.3DE")))

            for file_path in threede_files:
                shot_info = ThreeDESceneFinder.extract_shot_info_from_path(file_path)
                if not shot_info:
                    continue

                ws_path, seq, shot_name, username = shot_info

                # Apply exclusion logic (published files should never be excluded)
                if username in excluded_users and not username.startswith("published-"):
                    continue

                scene = ThreeDEScene(
                    show=show,
                    sequence=seq,
                    shot=shot_name,
                    workspace_path=ws_path,
                    user=username,
                    plate="bg01",  # Simplified for test
                    scene_path=file_path,
                )
                all_scenes.append(scene)

        # Should find 3 scenes total (2 from shot1 published, 1 from shot2 published)
        # john-d's file should be excluded
        assert len(all_scenes) == 3, (
            f"Should find 3 published scenes (john-d excluded), found {len(all_scenes)}"
        )

        # All should be published files
        published_scenes = [s for s in all_scenes if s.user.startswith("published-")]
        assert len(published_scenes) == 3, (
            f"All 3 scenes should be published, found {len(published_scenes)}"
        )

        # Check specific users
        users = {s.user for s in all_scenes}
        assert "published-mm" in users, "Should find published-mm user"
        assert "john-d" not in users, "john-d should be excluded"

    def test_mixed_published_and_user_files(self, published_file_structure):
        """Test handling shots with both published and user files."""
        shot1_path = str(published_file_structure["shot1_path"])

        # Find scenes without exclusion
        scenes = ThreeDESceneFinder.find_scenes_for_shot(
            shot_workspace_path=shot1_path,
            show="gator",
            sequence="019_JF",
            shot="1080",
            excluded_users=set(),  # No exclusions
        )

        # Should find all files (2 published + 1 user)
        assert len(scenes) >= 3, f"Should find at least 3 scenes, found {len(scenes)}"

        # Check we have both types
        users = {s.user for s in scenes}
        published_users = [u for u in users if u.startswith("published-")]
        regular_users = [u for u in users if not u.startswith("published-")]

        assert len(published_users) > 0, "Should have at least one published file"
        assert len(regular_users) > 0, "Should have at least one user file"
