#!/usr/bin/env python3
"""Test deduplication and scene discovery logic."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from threede_scene_model import ThreeDEScene, ThreeDESceneModel


def test_deduplication():
    """Test that deduplication works correctly."""

    # Create sample scenes with duplicates for the same shot
    scenes = [
        ThreeDEScene(
            show="jack_ryan",
            sequence="GF_256",
            shot="1420",
            workspace_path="/shows/jack_ryan/shots/GF_256/GF_256_1420",
            user="published-mm",
            plate="FG01",
            scene_path=Path(
                "/shows/jack_ryan/shots/GF_256/GF_256_1420/publish/mm/default/fg01/lens_distortion/v001/3de/GF_256_1420_mm-default_fg01_v001.3de",
            ),
        ),
        ThreeDEScene(
            show="jack_ryan",
            sequence="GF_256",
            shot="1420",
            workspace_path="/shows/jack_ryan/shots/GF_256/GF_256_1420",
            user="published-mm",
            plate="FG01",
            scene_path=Path(
                "/shows/jack_ryan/shots/GF_256/GF_256_1420/publish/mm/default/fg01/lens_distortion/v002/3de/GF_256_1420_mm-default_fg01_v002.3de",
            ),
        ),
        ThreeDEScene(
            show="jack_ryan",
            sequence="GF_256",
            shot="1420",
            workspace_path="/shows/jack_ryan/shots/GF_256/GF_256_1420",
            user="published-mm",
            plate="BG01",
            scene_path=Path(
                "/shows/jack_ryan/shots/GF_256/GF_256_1420/publish/mm/default/bg01/lens_distortion/v001/3de/GF_256_1420_mm-default_bg01_v001.3de",
            ),
        ),
        ThreeDEScene(
            show="jack_ryan",
            sequence="GF_256",
            shot="0980",
            workspace_path="/shows/jack_ryan/shots/GF_256/GF_256_0980",
            user="rob-o",
            plate="FG01",
            scene_path=Path(
                "/shows/jack_ryan/shots/GF_256/GF_256_0980/user/rob-o/3de/scenes/test.3de",
            ),
        ),
    ]

    print(f"Original scenes: {len(scenes)} scenes")
    for scene in scenes:
        print(f"  - {scene.full_name} - {scene.user} - {scene.plate}")

    # Create model and deduplicate
    model = ThreeDESceneModel(load_cache=False)
    deduplicated = model._deduplicate_scenes_by_shot(scenes)

    print(f"\nDeduplicated: {len(deduplicated)} scenes (should be 2, one per shot)")
    for scene in deduplicated:
        print(f"  - {scene.full_name} - {scene.user} - {scene.plate}")

    # Check that we have one scene per shot
    shot_ids = set()
    for scene in deduplicated:
        shot_id = f"{scene.show}/{scene.sequence}/{scene.shot}"
        if shot_id in shot_ids:
            print(f"ERROR: Duplicate shot found: {shot_id}")
        shot_ids.add(shot_id)

    if len(deduplicated) == 2:
        print("\n✅ Deduplication working correctly!")
    else:
        print(f"\n❌ Deduplication failed! Expected 2 scenes, got {len(deduplicated)}")


if __name__ == "__main__":
    test_deduplication()
