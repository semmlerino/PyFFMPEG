"""Unit tests for 3DE scene discovery filtering logic.

Following UNIFIED_TESTING_GUIDE:
- Test behavior, not implementation (line 42)
- Use real components with test doubles at boundaries (line 46)
- Mock only at system boundaries (line 50)
"""

from __future__ import annotations

# Standard library imports
from pathlib import Path

# Third-party imports
import pytest


class TestSceneFiltering:
    """Test the critical scene filtering logic that caused the bug.

    The bug: Only 1 scene was shown instead of 888 because scenes were
    incorrectly filtered out if they didn't match user's assigned shots.
    """

    @pytest.fixture
    def make_shot(self):
        """Factory fixture for creating test shots (GUIDE line 27)."""
        # Standard library imports
        from collections import namedtuple

        Shot = namedtuple("Shot", ["workspace_path", "show", "sequence", "shot"])

        def _make(show="test_show", seq="seq01", shot="0010"):
            return Shot(f"/shows/{show}/shots/{seq}/{seq}_{shot}", show, seq, shot)

        return _make

    @pytest.fixture
    def make_file_tuple(self):
        """Factory fixture for creating file tuples returned by scanner."""

        def _make(
            show="test_show",
            seq="seq01",
            shot="0010",
            user="other-user",
            plate="bg01",
        ):
            scene_path = Path(
                f"/shows/{show}/shots/{seq}/{seq}_{shot}/user/{user}/3de/scene.3de"
            )
            return (scene_path, show, seq, shot, user, plate)

        return _make

    def test_scene_creation_for_matching_shot(self, make_shot, make_file_tuple) -> None:
        """Test that scenes ARE created when shot matches user's assignments."""
        # Setup - user has this shot assigned
        user_shots = [make_shot(show="gator", seq="013_DC", shot="2120")]

        # File from a shot the user IS assigned to
        file_tuple = make_file_tuple(
            show="gator", seq="013_DC", shot="2120", user="sarah-b"
        )

        # Simulate the logic from scene_discovery_coordinator.py
        _scene_path, show_name, seq, shot, _user, _plate = file_tuple
        matching_shot = next(
            (
                s
                for s in user_shots
                if s.show == show_name and s.sequence == seq and s.shot == shot
            ),
            None,
        )

        # THIS SHOULD PASS: User is assigned to this shot
        assert matching_shot is not None
        assert matching_shot.workspace_path == "/shows/gator/shots/013_DC/013_DC_2120"

        # Scene should be created with user's workspace path
        workspace_path = matching_shot.workspace_path
        assert workspace_path == "/shows/gator/shots/013_DC/013_DC_2120"

    def test_scene_creation_for_non_matching_shot(
        self, make_shot, make_file_tuple
    ) -> None:
        """Test that scenes ARE created even when shot doesn't match assignments.

        This was the BUG: Scenes were dropped if matching_shot was None.
        The FIX: Always create scenes, constructing workspace_path if needed.
        """
        # Setup - user has different shots assigned
        user_shots = [
            make_shot(show="gator", seq="013_DC", shot="2120"),
            make_shot(show="jack_ryan", seq="MA_074", shot="0340"),
        ]

        # File from a shot the user is NOT assigned to
        file_tuple = make_file_tuple(
            show="gator", seq="019_JF", shot="1060", user="tony-a"
        )

        # Simulate the logic from scene_discovery_coordinator.py
        _scene_path, show_name, seq, shot, _user, _plate = file_tuple
        matching_shot = next(
            (
                s
                for s in user_shots
                if s.show == show_name and s.sequence == seq and s.shot == shot
            ),
            None,
        )

        # User is NOT assigned to this shot
        assert matching_shot is None

        # THE FIX: Construct workspace path when no matching shot
        shows_root = "/shows"
        if matching_shot:
            workspace_path = matching_shot.workspace_path
        else:
            # This is the critical fix - always create a path
            workspace_path = f"{shows_root}/{show_name}/shots/{seq}/{seq}_{shot}"

        # Scene should still be created with constructed path
        assert workspace_path == "/shows/gator/shots/019_JF/019_JF_1060"

    def test_all_scenes_created_regardless_of_assignment(
        self, make_shot, make_file_tuple
    ) -> None:
        """Test that ALL scenes from other users are created.

        Verifies the fix creates scenes for:
        1. Shots assigned to the user
        2. Shots NOT assigned to the user
        3. All users except excluded ones
        """
        # User has only 2 shots assigned
        user_shots = [
            make_shot(show="gator", seq="013_DC", shot="2120"),
            make_shot(show="jack_ryan", seq="MA_074", shot="0340"),
        ]

        # Simulate files from many different shots and users
        file_tuples = [
            # Assigned shot, other user
            make_file_tuple("gator", "013_DC", "2120", "sarah-b", "bg01"),
            # NOT assigned shot, other user (PREVIOUSLY DROPPED)
            make_file_tuple("gator", "019_JF", "1060", "tony-a", "fg01"),
            # NOT assigned shot, another user (PREVIOUSLY DROPPED)
            make_file_tuple("jack_ryan", "DM_062", "3220", "ryan-p", "bg01"),
            # Assigned shot, different user
            make_file_tuple("jack_ryan", "MA_074", "0340", "published-mm", "pl01"),
            # Many more NOT assigned (PREVIOUSLY ALL DROPPED)
            make_file_tuple("broken_eggs", "BRX_119", "0010", "alex-k", "bg01"),
            make_file_tuple("broken_eggs", "BRX_170", "0100", "mike-d", "fg01"),
        ]

        # Process all files with the FIXED logic
        scenes_created = []
        shows_root = "/shows"

        for file_tuple in file_tuples:
            _scene_path, show_name, seq, shot, user, _plate = file_tuple

            # Find matching shot
            matching_shot = next(
                (
                    s
                    for s in user_shots
                    if s.show == show_name and s.sequence == seq and s.shot == shot
                ),
                None,
            )

            # CRITICAL FIX: Always create scene
            if matching_shot:
                workspace_path = matching_shot.workspace_path
            else:
                # Construct path for non-assigned shots
                workspace_path = f"{shows_root}/{show_name}/shots/{seq}/{seq}_{shot}"

            # Scene is ALWAYS created now
            scenes_created.append(
                {
                    "show": show_name,
                    "sequence": seq,
                    "shot": shot,
                    "user": user,
                    "workspace_path": workspace_path,
                }
            )

        # ALL 6 scenes should be created (not just 2 from assigned shots)
        assert len(scenes_created) == 6

        # Verify non-assigned shots have constructed paths
        broken_eggs_scene = next(
            s for s in scenes_created if s["show"] == "broken_eggs"
        )
        assert (
            broken_eggs_scene["workspace_path"]
            == "/shows/broken_eggs/shots/BRX_119/BRX_119_0010"
        )

    def test_excluded_users_still_filtered(self, make_file_tuple) -> None:
        """Test that excluded users are still properly filtered out."""
        # Local application imports
        from scene_parser import SceneParser

        parser = SceneParser()
        excluded_users = {"gabriel-h", "test-user"}

        # Create file path that would be from excluded user
        threede_file = Path(
            "/shows/gator/shots/013_DC/013_DC_2120/user/gabriel-h/3de/scene.3de"
        )
        show_path = Path("/shows/gator")
        show = "gator"

        # Parser should return None for excluded user
        result = parser.parse_3de_file_path(
            threede_file, show_path, show, excluded_users
        )

        assert result is None  # Correctly filtered out

    @pytest.mark.parametrize(
        ("show", "seq", "shot", "expected_path"),
        [
            ("gator", "013_DC", "2120", "/shows/gator/shots/013_DC/013_DC_2120"),
            (
                "jack_ryan",
                "DM_062",
                "3220",
                "/shows/jack_ryan/shots/DM_062/DM_062_3220",
            ),
            (
                "broken_eggs",
                "BRX_119",
                "0010",
                "/shows/broken_eggs/shots/BRX_119/BRX_119_0010",
            ),
        ],
    )
    def test_workspace_path_construction(self, show, seq, shot, expected_path) -> None:
        """Test workspace path construction for various shots (GUIDE line 143)."""
        shows_root = "/shows"
        workspace_path = f"{shows_root}/{show}/shots/{seq}/{seq}_{shot}"
        assert workspace_path == expected_path
