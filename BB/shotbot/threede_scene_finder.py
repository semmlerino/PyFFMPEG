"""Utility for finding 3DE scene files from other users."""

import os
from pathlib import Path
from typing import Set

from threede_scene_model import ThreeDEScene


class ThreeDESceneFinder:
    """Static utility class for discovering 3DE scene files."""

    @staticmethod
    def find_scenes_for_shot(
        shot_workspace_path: str,
        show: str,
        sequence: str,
        shot: str,
        excluded_users: Set[str],
    ) -> list[ThreeDEScene]:
        """Find all 3DE scenes for a shot from other users.

        Args:
            shot_workspace_path: The workspace path for the shot
            show: Show name
            sequence: Sequence name
            shot: Shot number
            excluded_users: Set of usernames to exclude

        Returns:
            List of ThreeDEScene objects
        """
        scenes: list[ThreeDEScene] = []
        user_dir = Path(shot_workspace_path) / "user"

        # Check if user directory exists
        if not user_dir.exists():
            return scenes

        try:
            # Iterate through user directories
            for user_path in user_dir.iterdir():
                if not user_path.is_dir():
                    continue

                user_name = user_path.name

                # Skip excluded users
                if user_name in excluded_users:
                    continue

                # Look for 3DE scenes in the expected structure
                # Pattern: user/{username}/mm/3de/mm-default/scenes/scene/
                scene_base = (
                    user_path / "mm" / "3de" / "mm-default" / "scenes" / "scene"
                )

                if not scene_base.exists():
                    continue

                # Search recursively for .3de files
                for threede_file in scene_base.rglob("*.3de"):
                    # Extract plate name from path
                    # Expected: .../scene/{plate}/.../*.3de
                    relative_path = threede_file.relative_to(scene_base)
                    path_parts = relative_path.parts

                    if len(path_parts) >= 2:
                        # First part should be the plate (e.g., FG01, BG01)
                        plate = path_parts[0]
                    else:
                        # If structure is different, use parent directory name
                        plate = threede_file.parent.name

                    # Create ThreeDEScene object
                    scene = ThreeDEScene(
                        show=show,
                        sequence=sequence,
                        shot=shot,
                        workspace_path=shot_workspace_path,
                        user=user_name,
                        plate=plate,
                        scene_path=threede_file,
                    )
                    scenes.append(scene)

        except PermissionError as e:
            print(f"Permission denied accessing user directories: {e}")
        except Exception as e:
            print(f"Error scanning for 3DE scenes: {e}")

        return scenes

    @staticmethod
    def find_all_scenes(
        shots: list[tuple[str, str, str, str]], excluded_users: Set[str]
    ) -> list[ThreeDEScene]:
        """Find 3DE scenes for multiple shots.

        Args:
            shots: List of (workspace_path, show, sequence, shot) tuples
            excluded_users: Set of usernames to exclude

        Returns:
            Combined list of ThreeDEScene objects
        """
        all_scenes: list[ThreeDEScene] = []

        for workspace_path, show, sequence, shot in shots:
            scenes = ThreeDESceneFinder.find_scenes_for_shot(
                workspace_path, show, sequence, shot, excluded_users
            )
            all_scenes.extend(scenes)

        return all_scenes

    @staticmethod
    def verify_scene_exists(scene_path: Path) -> bool:
        """Verify that a 3DE scene file exists and is readable.

        Args:
            scene_path: Path to the .3de file

        Returns:
            True if file exists and is readable
        """
        try:
            return (
                scene_path.exists()
                and scene_path.is_file()
                and os.access(scene_path, os.R_OK)
            )
        except Exception:
            return False
