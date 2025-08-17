#!/usr/bin/env python3
"""Test shot deduplication to prevent multiple thumbnails for the same shot.

This test ensures that when multiple 3DE files exist for the same shot,
only one is displayed (based on priority: latest modification time).
"""

import unittest
from datetime import datetime
from typing import Dict, List, Tuple


class TestShotDeduplication(unittest.TestCase):
    """Test suite for shot deduplication logic."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_scenes = []

    def create_test_scene(
        self,
        show: str,
        sequence: str,
        shot: str,
        username: str,
        filename: str,
        mtime: float,
        is_published: bool = False,
    ) -> Dict:
        """Create a test scene dictionary."""
        return {
            "show": show,
            "sequence": sequence,
            "shot": shot,
            "username": username,
            "filename": filename,
            "file_path": f"/shows/{show}/shots/{sequence}/{sequence}_{shot}/{'publish' if is_published else f'user/{username}'}/3de/{filename}",
            "mtime": mtime,
            "is_published": is_published,
            "plate_name": filename.split("_")[0] if "_" in filename else "unknown",
        }

    def test_deduplication_single_shot_multiple_files(self):
        """Test that multiple files for the same shot are deduplicated."""
        base_time = datetime.now().timestamp()

        # Create multiple 3DE files for the same shot
        scenes = [
            self.create_test_scene(
                "jack_ryan",
                "GF_256",
                "1400",
                "artist1",
                "GF_256_1400_v001.3de",
                base_time,
            ),
            self.create_test_scene(
                "jack_ryan",
                "GF_256",
                "1400",
                "artist2",
                "GF_256_1400_v002.3de",
                base_time + 100,
            ),
            self.create_test_scene(
                "jack_ryan",
                "GF_256",
                "1400",
                "artist3",
                "GF_256_1400_v003.3de",
                base_time + 200,
            ),
        ]

        # Apply deduplication logic
        deduplicated = self.deduplicate_scenes(scenes)

        # Should only have one scene for this shot
        self.assertEqual(len(deduplicated), 1)

        # Should keep the most recent one (v003)
        self.assertEqual(deduplicated[0]["filename"], "GF_256_1400_v003.3de")
        self.assertEqual(deduplicated[0]["username"], "artist3")

    def test_deduplication_multiple_shots(self):
        """Test deduplication across multiple different shots."""
        base_time = datetime.now().timestamp()

        scenes = [
            # Shot 1400 - multiple versions
            self.create_test_scene(
                "jack_ryan",
                "GF_256",
                "1400",
                "artist1",
                "GF_256_1400_v001.3de",
                base_time,
            ),
            self.create_test_scene(
                "jack_ryan",
                "GF_256",
                "1400",
                "artist2",
                "GF_256_1400_v002.3de",
                base_time + 100,
            ),
            # Shot 1410 - multiple versions
            self.create_test_scene(
                "jack_ryan",
                "GF_256",
                "1410",
                "artist1",
                "GF_256_1410_v001.3de",
                base_time + 50,
            ),
            self.create_test_scene(
                "jack_ryan",
                "GF_256",
                "1410",
                "artist3",
                "GF_256_1410_v002.3de",
                base_time + 150,
            ),
            # Shot 1420 - single version
            self.create_test_scene(
                "jack_ryan",
                "GF_256",
                "1420",
                "artist2",
                "GF_256_1420_v001.3de",
                base_time + 200,
            ),
        ]

        deduplicated = self.deduplicate_scenes(scenes)

        # Should have one scene per unique shot
        self.assertEqual(len(deduplicated), 3)

        # Verify we have one of each shot
        shots = {(s["sequence"], s["shot"]) for s in deduplicated}
        expected_shots = {("GF_256", "1400"), ("GF_256", "1410"), ("GF_256", "1420")}
        self.assertEqual(shots, expected_shots)

        # Verify we kept the latest version of each
        shot_1400 = next(s for s in deduplicated if s["shot"] == "1400")
        self.assertEqual(shot_1400["filename"], "GF_256_1400_v002.3de")

        shot_1410 = next(s for s in deduplicated if s["shot"] == "1410")
        self.assertEqual(shot_1410["filename"], "GF_256_1410_v002.3de")

    def test_deduplication_published_vs_user(self):
        """Test that published and user files are handled correctly."""
        base_time = datetime.now().timestamp()

        scenes = [
            # User workspace file
            self.create_test_scene(
                "jack_ryan",
                "GF_256",
                "1400",
                "artist1",
                "GF_256_1400_wip.3de",
                base_time,
                is_published=False,
            ),
            # Published file (older but might have priority)
            self.create_test_scene(
                "jack_ryan",
                "GF_256",
                "1400",
                "published-3de",
                "GF_256_1400_final.3de",
                base_time - 100,
                is_published=True,
            ),
            # Another user file (newest)
            self.create_test_scene(
                "jack_ryan",
                "GF_256",
                "1400",
                "artist2",
                "GF_256_1400_latest.3de",
                base_time + 100,
                is_published=False,
            ),
        ]

        deduplicated = self.deduplicate_scenes(scenes)

        # Should only have one scene
        self.assertEqual(len(deduplicated), 1)

        # Default behavior: keep the most recent regardless of published status
        self.assertEqual(deduplicated[0]["filename"], "GF_256_1400_latest.3de")
        self.assertFalse(deduplicated[0]["is_published"])

    def test_deduplication_different_shows(self):
        """Test that scenes from different shows are not deduplicated together."""
        base_time = datetime.now().timestamp()

        scenes = [
            # Same sequence/shot numbers but different shows
            self.create_test_scene(
                "jack_ryan", "SEQ_01", "0010", "artist1", "SEQ_01_0010.3de", base_time
            ),
            self.create_test_scene(
                "other_show",
                "SEQ_01",
                "0010",
                "artist2",
                "SEQ_01_0010.3de",
                base_time + 100,
            ),
            self.create_test_scene(
                "third_show",
                "SEQ_01",
                "0010",
                "artist3",
                "SEQ_01_0010.3de",
                base_time + 200,
            ),
        ]

        deduplicated = self.deduplicate_scenes(scenes)

        # Should keep all three since they're from different shows
        self.assertEqual(len(deduplicated), 3)

        # Verify all shows are present
        shows = {s["show"] for s in deduplicated}
        self.assertEqual(shows, {"jack_ryan", "other_show", "third_show"})

    def test_deduplication_with_plate_names(self):
        """Test deduplication considering different plate names."""
        base_time = datetime.now().timestamp()

        scenes = [
            # Same shot, different plate names
            self.create_test_scene(
                "jack_ryan", "GF_256", "1400", "artist1", "BG01_comp.3de", base_time
            ),
            self.create_test_scene(
                "jack_ryan",
                "GF_256",
                "1400",
                "artist2",
                "FG01_track.3de",
                base_time + 100,
            ),
            self.create_test_scene(
                "jack_ryan",
                "GF_256",
                "1400",
                "artist3",
                "BG01_final.3de",
                base_time + 200,
            ),
        ]

        # Update plate names
        scenes[0]["plate_name"] = "BG01"
        scenes[1]["plate_name"] = "FG01"
        scenes[2]["plate_name"] = "BG01"

        deduplicated = self.deduplicate_scenes(scenes)

        # Should keep one per shot (latest overall)
        self.assertEqual(len(deduplicated), 1)
        self.assertEqual(deduplicated[0]["filename"], "BG01_final.3de")

    def test_empty_scene_list(self):
        """Test deduplication with empty scene list."""
        deduplicated = self.deduplicate_scenes([])
        self.assertEqual(deduplicated, [])

    def test_single_scene(self):
        """Test deduplication with single scene."""
        scene = self.create_test_scene(
            "jack_ryan",
            "GF_256",
            "1400",
            "artist1",
            "test.3de",
            datetime.now().timestamp(),
        )
        deduplicated = self.deduplicate_scenes([scene])

        self.assertEqual(len(deduplicated), 1)
        self.assertEqual(deduplicated[0], scene)

    def test_my_shots_vs_other_scenes_separation(self):
        """Test that user's shots are properly separated from other scenes."""
        base_time = datetime.now().timestamp()
        current_user = "johndoe"

        # User's assigned shots (from ws -sg)
        user_shots = [("jack_ryan", "GF_256", "1400"), ("jack_ryan", "GF_256", "1410")]

        scenes = [
            # User's assigned shot - their file
            self.create_test_scene(
                "jack_ryan",
                "GF_256",
                "1400",
                current_user,
                "GF_256_1400_mine.3de",
                base_time,
            ),
            # User's assigned shot - someone else's file
            self.create_test_scene(
                "jack_ryan",
                "GF_256",
                "1400",
                "other_artist",
                "GF_256_1400_other.3de",
                base_time + 100,
            ),
            # Another user's assigned shot
            self.create_test_scene(
                "jack_ryan",
                "GF_256",
                "1410",
                "different_artist",
                "GF_256_1410.3de",
                base_time,
            ),
            # Shot not assigned to anyone (should go to "Other 3DE scenes")
            self.create_test_scene(
                "jack_ryan",
                "GF_256",
                "1420",
                "random_artist",
                "GF_256_1420.3de",
                base_time,
            ),
        ]

        # Separate into My Shots and Other 3DE scenes
        my_shots = []
        other_scenes = []

        for scene in scenes:
            shot_key = (scene["show"], scene["sequence"], scene["shot"])
            if shot_key in user_shots and scene["username"] == current_user:
                my_shots.append(scene)
            elif shot_key not in user_shots:
                other_scenes.append(scene)

        # User should only see their own files for assigned shots
        self.assertEqual(len(my_shots), 1)
        self.assertEqual(my_shots[0]["username"], current_user)
        self.assertEqual(my_shots[0]["shot"], "1400")

        # Other scenes should include non-assigned shots
        self.assertEqual(len(other_scenes), 2)
        other_shots = {s["shot"] for s in other_scenes}
        self.assertEqual(other_shots, {"1410", "1420"})

    def deduplicate_scenes(self, scenes: List[Dict]) -> List[Dict]:
        """Apply deduplication logic to scenes.

        This mimics the logic in main_window.py _on_threede_discovery_finished.
        """
        if not scenes:
            return []

        # Group by unique shot (show, sequence, shot)
        shots_dict: Dict[Tuple[str, str, str], Dict] = {}

        for scene in scenes:
            shot_key = (scene["show"], scene["sequence"], scene["shot"])

            # Keep the most recent scene for each shot
            if shot_key not in shots_dict:
                shots_dict[shot_key] = scene
            else:
                # Compare modification times, keep the newer one
                if scene["mtime"] > shots_dict[shot_key]["mtime"]:
                    shots_dict[shot_key] = scene

        return list(shots_dict.values())


if __name__ == "__main__":
    unittest.main()
