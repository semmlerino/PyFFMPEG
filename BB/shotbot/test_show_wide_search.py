#!/usr/bin/env python3
"""Test script for show-wide 3DE scene search functionality."""

import logging
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from threede_scene_finder import ThreeDESceneFinder
from utils import ValidationUtils

# Configure logging to see debug output
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


@dataclass
class MockShot:
    """Mock Shot object for testing."""

    show: str
    sequence: str
    shot: str
    workspace_path: str

    @property
    def full_name(self) -> str:
        """Get full shot name."""
        return f"{self.sequence}_{self.shot}"


def create_show_structure(base_dir: Path) -> tuple:
    """Create a test show structure with multiple sequences and shots.

    Returns:
        tuple: (user_shots, all_shot_paths)
    """
    # Get current user
    current_user = ValidationUtils.get_current_username()
    print(f"Current user: {current_user}")

    # Create show structure
    show_name = "test_show"
    shows_dir = base_dir / "shows" / show_name / "shots"

    # Define sequences and shots
    structure = {
        "AB_100": ["AB_100_0010", "AB_100_0020", "AB_100_0030"],
        "CD_200": ["CD_200_0010", "CD_200_0020"],
        "EF_300": ["EF_300_0010", "EF_300_0020", "EF_300_0030", "EF_300_0040"],
    }

    # Create user's assigned shots (just 2 shots)
    user_shots = [
        MockShot(
            show_name,
            "AB_100",
            "AB_100_0010",
            str(shows_dir / "AB_100" / "AB_100_0010"),
        ),
        MockShot(
            show_name,
            "CD_200",
            "CD_200_0020",
            str(shows_dir / "CD_200" / "CD_200_0020"),
        ),
    ]

    all_shot_paths = []
    scene_count = 0

    # Create the directory structure and add .3de files
    for sequence, shots in structure.items():
        for shot in shots:
            shot_path = shows_dir / sequence / shot
            user_dir = shot_path / "user"

            # Create various users with .3de files
            users_with_scenes = {
                "alice": [
                    "mm/3de/scenes/bg01/track_v001.3de",
                    "mm/3de/scenes/bg01/track_v002.3de",
                ],
                "bob": [
                    "matchmove/3de/scene/main_track.3de",
                ],
                "charlie": [
                    "work/tracking/shot_solve.3de",
                    "3de_files/final/approved.3de",
                ],
                current_user: [  # Current user also has scenes
                    "mm/3de/scenes/bg01/my_work.3de",
                ],
            }

            # Only add scenes to some shots to make it realistic
            if shot in [
                "AB_100_0010",
                "AB_100_0030",
                "CD_200_0010",
                "EF_300_0020",
                "EF_300_0040",
            ]:
                for user, files in users_with_scenes.items():
                    for file_path in files:
                        full_path = user_dir / user / file_path
                        full_path.parent.mkdir(parents=True, exist_ok=True)

                        # Create .3de file
                        with open(full_path, "w") as f:
                            f.write(f"# 3DE scene\n# Shot: {shot}\n# User: {user}\n")

                        scene_count += 1
                        print(f"Created scene: {shot}/{user}/{file_path}")
            else:
                # Create empty user directories for other shots
                (user_dir / "empty_user").mkdir(parents=True, exist_ok=True)

            all_shot_paths.append(shot_path)

    print(
        f"\nCreated {len(structure)} sequences with {sum(len(shots) for shots in structure.values())} shots"
    )
    print(f"Total 3DE scenes created: {scene_count}")
    print(f"User assigned to {len(user_shots)} shots")

    return user_shots, all_shot_paths


def test_show_wide_search():
    """Test the show-wide 3DE scene search."""
    with tempfile.TemporaryDirectory() as temp_dir:
        base_dir = Path(temp_dir)
        print(f"\nCreating test show structure in: {base_dir}")
        print("=" * 80)

        # Create test structure
        user_shots, all_shot_paths = create_show_structure(base_dir)

        print("\nTesting show-wide search...")
        print("=" * 80)

        # Test 1: Discover all shots in show
        print("\n1. Testing shot discovery:")
        discovered_shots = ThreeDESceneFinder.discover_all_shots_in_show(
            str(base_dir / "shows"), "test_show"
        )
        print(f"Discovered {len(discovered_shots)} shots in show")

        # Test 2: Show-wide 3DE scene search
        print("\n2. Testing show-wide 3DE search:")
        print(f"User is assigned to shots: {[s.full_name for s in user_shots]}")
        print("But searching ALL shots in the show...")

        all_scenes = ThreeDESceneFinder.find_all_scenes_in_shows(
            user_shots,
            excluded_users=None,  # Will auto-exclude current user
        )

        print(f"\nFound {len(all_scenes)} 3DE scenes across the entire show")

        # Group by shot for display
        scenes_by_shot = {}
        for scene in all_scenes:
            shot_key = f"{scene.sequence}_{scene.shot}"
            if shot_key not in scenes_by_shot:
                scenes_by_shot[shot_key] = []
            scenes_by_shot[shot_key].append(scene)

        print(f"\nScenes found in {len(scenes_by_shot)} different shots:")
        for shot_key in sorted(scenes_by_shot.keys()):
            shot_scenes = scenes_by_shot[shot_key]
            print(f"\n  {shot_key}: {len(shot_scenes)} scenes")
            for scene in shot_scenes:
                print(f"    - {scene.user}/{scene.plate}")

        # Verify we found scenes from shots NOT assigned to the user
        user_shot_names = {f"{s.sequence}_{s.shot}" for s in user_shots}
        other_shot_scenes = [
            s for s in all_scenes if s.full_name not in user_shot_names
        ]

        print("\nVerification:")
        print(f"- User assigned to {len(user_shots)} shots: {sorted(user_shot_names)}")
        print(f"- Found scenes from {len(scenes_by_shot)} total shots")
        print(
            f"- Found {len(other_shot_scenes)} scenes from OTHER shots (not assigned to user)"
        )

        # Show which other shots had scenes
        other_shots_with_scenes = set()
        for scene in other_shot_scenes:
            other_shots_with_scenes.add(scene.full_name)

        if other_shots_with_scenes:
            print("\nOther shots with scenes (user NOT assigned to these):")
            for shot in sorted(other_shots_with_scenes):
                print(f"  - {shot}")


if __name__ == "__main__":
    print("Testing Show-Wide 3DE Scene Search")
    print("=" * 80)
    test_show_wide_search()
    print("\nTest complete!")
