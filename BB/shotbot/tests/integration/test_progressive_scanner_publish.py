"""Test progressive scanner with publish directory support."""

from unittest.mock import patch

from config import Config
from threede_scene_finder import ThreeDESceneFinder


class TestProgressiveScannerPublish:
    """Test progressive scanner finds both user and published 3DE files."""

    def test_progressive_scan_finds_published_files(self, tmp_path):
        """Test that progressive scanner finds files in publish directories."""
        # Create shot structure with both user and publish files
        shot_path = tmp_path / "shows" / "testshow" / "shots" / "seq01" / "seq01_shot01"

        # Create user directory with 3DE file
        user_path = shot_path / "user" / "alice" / "3de" / "scenes"
        user_path.mkdir(parents=True)
        user_3de = user_path / "test_user.3de"
        user_3de.touch()

        # Create publish directory with 3DE file
        publish_path = (
            shot_path / "publish" / "mm" / "default" / "bg01" / "3de" / "v001"
        )
        publish_path.mkdir(parents=True)
        publish_3de = publish_path / "test_published.3de"
        publish_3de.touch()

        # Create list of shots to scan
        shots = [(str(shot_path), "testshow", "seq01", "shot01")]

        # Run progressive scan
        all_scenes = []
        for batch, _, _, _ in ThreeDESceneFinder.find_all_scenes_progressive(
            shots, excluded_users={"gabriel-h"}, batch_size=10
        ):
            all_scenes.extend(batch)

        # Check that both scenes were found
        assert len(all_scenes) == 2

        # Check user scene
        user_scenes = [s for s in all_scenes if s.user == "alice"]
        assert len(user_scenes) == 1
        assert user_scenes[0].scene_path.name == "test_user.3de"

        # Check published scene
        published_scenes = [s for s in all_scenes if s.user.startswith("published-")]
        assert len(published_scenes) == 1
        assert published_scenes[0].user == "published-mm"
        assert published_scenes[0].scene_path.name == "test_published.3de"

    def test_progressive_scan_handles_missing_directories(self, tmp_path):
        """Test that progressive scanner handles shots with missing directories gracefully."""
        # Create shot with only publish directory (no user directory)
        shot_path = tmp_path / "shows" / "testshow" / "shots" / "seq01" / "seq01_shot01"

        # Create only publish directory
        publish_path = shot_path / "publish" / "comp" / "v001"
        publish_path.mkdir(parents=True)
        publish_3de = publish_path / "comp.3de"
        publish_3de.touch()

        # Create list of shots to scan
        shots = [(str(shot_path), "testshow", "seq01", "shot01")]

        # Run progressive scan
        all_scenes = []
        for batch, _, _, status in ThreeDESceneFinder.find_all_scenes_progressive(
            shots, excluded_users=set(), batch_size=10
        ):
            all_scenes.extend(batch)

        # Check that published scene was found even without user directory
        assert len(all_scenes) == 1
        assert all_scenes[0].user == "published-comp"
        assert all_scenes[0].scene_path.name == "comp.3de"

    def test_progressive_scan_excludes_users_but_not_published(self, tmp_path):
        """Test that excluded users are skipped but published files are always included."""
        # Create shot structure
        shot_path = tmp_path / "shows" / "testshow" / "shots" / "seq01" / "seq01_shot01"

        # Create excluded user directory with 3DE file
        user_path = shot_path / "user" / "bob" / "3de"
        user_path.mkdir(parents=True)
        user_3de = user_path / "bob_scene.3de"
        user_3de.touch()

        # Create publish directory with 3DE file
        publish_path = shot_path / "publish" / "mm" / "3de"
        publish_path.mkdir(parents=True)
        publish_3de = publish_path / "published_scene.3de"
        publish_3de.touch()

        # Create list of shots to scan
        shots = [(str(shot_path), "testshow", "seq01", "shot01")]

        # Run progressive scan with "bob" excluded
        all_scenes = []
        for batch, _, _, _ in ThreeDESceneFinder.find_all_scenes_progressive(
            shots, excluded_users={"bob"}, batch_size=10
        ):
            all_scenes.extend(batch)

        # Check that only published scene was found (bob was excluded)
        assert len(all_scenes) == 1
        assert all_scenes[0].user == "published-mm"
        assert all_scenes[0].scene_path.name == "published_scene.3de"

    def test_progressive_scan_deeply_nested_publish_files(self, tmp_path):
        """Test that progressive scanner finds deeply nested files in publish directories."""
        # Create shot structure with deeply nested publish file
        shot_path = tmp_path / "shows" / "testshow" / "shots" / "seq01" / "seq01_shot01"

        # Create deeply nested publish directory (10+ levels)
        publish_path = (
            shot_path
            / "publish"
            / "mm"
            / "default"
            / "bg01"
            / "lens_distortion"
            / "v001"
            / "3de"
            / "scenes"
            / "backup"
            / "old"
            / "archive"
        )
        publish_path.mkdir(parents=True)
        publish_3de = publish_path / "deep_nested.3de"
        publish_3de.touch()

        # Create list of shots to scan
        shots = [(str(shot_path), "testshow", "seq01", "shot01")]

        # Run progressive scan with increased depth limit
        with patch.object(Config, "THREEDE_SCAN_MAX_DEPTH", 15):
            all_scenes = []
            for batch, _, _, _ in ThreeDESceneFinder.find_all_scenes_progressive(
                shots, excluded_users=set(), batch_size=10
            ):
                all_scenes.extend(batch)

        # Check that deeply nested file was found
        assert len(all_scenes) == 1
        assert all_scenes[0].user == "published-mm"
        assert all_scenes[0].scene_path.name == "deep_nested.3de"
        assert "archive" in str(all_scenes[0].scene_path)
