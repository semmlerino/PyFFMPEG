#!/usr/bin/env python3
"""Test script for flexible 3DE scene search functionality."""

import logging
import sys
import tempfile
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from threede_scene_finder import ThreeDESceneFinder
from utils import ValidationUtils

# Configure logging to see debug output
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


def create_test_structure(base_dir: Path) -> tuple[dict, Path]:
    """Create a test directory structure with various 3DE file locations.

    Returns:
        tuple: (created_files dict, workspace Path)
    """
    # Get current user to exclude
    current_user = ValidationUtils.get_current_username()
    print(f"Current user (will be excluded): {current_user}")

    # Define test structure with various path patterns
    test_structure = {
        "alice": [
            "mm/3de/scenes/bg01/track_v001.3de",
            "mm/3de/scenes/bg01/track_v002.3de",
            "mm/3de/scenes/fg01/hero_track.3de",
        ],
        "bob": [
            "matchmove/3de/scene/shot010_mm.3de",
            "work/3de_files/test_scene.3de",
            "3de/final/approved_track.3de",
        ],
        "charlie": [
            "tracking/scenes/plate01/solve_v003.3de",
            "personal/3de/wip_scene.3de",
        ],
        current_user: [  # Current user's files (should be excluded)
            "mm/3de/scenes/bg01/my_scene.3de",
            "work/test.3de",
        ],
        "dave": [
            "3de_projects/car_track/scene_v001.3de",
            "3de_projects/car_track/scene_v002.3de",
            "matchmove/elem01/track.3de",
        ],
    }

    # Create the structure
    workspace = base_dir / "shots" / "seq001" / "shot010"
    user_dir = workspace / "user"
    user_dir.mkdir(parents=True, exist_ok=True)

    created_files = {}

    for user, files in test_structure.items():
        user_path = user_dir / user
        created_files[user] = []

        for file_path in files:
            full_path = user_path / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)

            # Create a simple .3de file with some content
            with open(full_path, "w") as f:
                f.write(f"# 3DE scene file\n# User: {user}\n# Path: {file_path}\n")

            created_files[user].append(full_path)
            print(f"Created: {full_path.relative_to(base_dir)}")

    return created_files, workspace


def test_flexible_search():
    """Test the flexible 3DE scene search."""
    with tempfile.TemporaryDirectory() as temp_dir:
        base_dir = Path(temp_dir)
        print(f"\nCreating test structure in: {base_dir}")
        print("=" * 80)

        # Create test structure
        created_files, workspace = create_test_structure(base_dir)

        # Test parameters
        show = "testshow"
        sequence = "seq001"
        shot = "shot010"

        print("\nRunning flexible 3DE scene search...")
        print(f"Workspace: {workspace}")
        print("=" * 80)

        # Run the search
        scenes = ThreeDESceneFinder.find_scenes_for_shot(
            str(workspace), show, sequence, shot
        )

        # Display results
        print("\nSearch Results:")
        print(f"Found {len(scenes)} 3DE scenes")
        print("=" * 80)

        # Group by user
        scenes_by_user = {}
        for scene in scenes:
            if scene.user not in scenes_by_user:
                scenes_by_user[scene.user] = []
            scenes_by_user[scene.user].append(scene)

        # Display grouped results
        for user in sorted(scenes_by_user.keys()):
            user_scenes = scenes_by_user[user]
            print(f"\n{user}: {len(user_scenes)} scenes")
            for scene in user_scenes:
                relative_path = Path(scene.scene_path).relative_to(
                    workspace / "user" / user
                )
                print(f"  - Plate: {scene.plate:<15} Path: {relative_path}")

        # Verify exclusions
        current_user = ValidationUtils.get_current_username()
        print("\nVerification:")
        print(
            f"- Current user '{current_user}' should be excluded: {'✓' if current_user not in scenes_by_user else '✗'}"
        )
        print(f"- Expected users found: {len(scenes_by_user)} (should be 4)")

        # Show plate extraction examples
        print("\nPlate Extraction Examples:")
        example_plates = set()
        for scene in scenes[:10]:  # Show first 10
            example_plates.add(
                (scene.plate, str(Path(scene.scene_path).relative_to(workspace)))
            )

        for plate, path in sorted(example_plates):
            print(f"  - '{plate}' extracted from: {path}")


if __name__ == "__main__":
    print("Testing Flexible 3DE Scene Search")
    print("=" * 80)
    test_flexible_search()
    print("\nTest complete!")
