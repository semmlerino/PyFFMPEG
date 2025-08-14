#!/usr/bin/env python3
"""Test the third thumbnail fallback for finding EXR files with 1001 in publish folder."""

import logging
from pathlib import Path

from config import Config
from shot_model import Shot
from utils import PathUtils

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)


def test_third_fallback():
    """Test the third fallback thumbnail discovery."""

    print("=" * 60)
    print("Testing Third Fallback Thumbnail Discovery")
    print("=" * 60)

    # Test with the exact path from the example
    test_shot = Shot(
        show="jack_ryan",
        sequence="DB_256",
        shot="1210",
        workspace_path="/shows/jack_ryan/shots/DB_256/DB_256_1210",
    )

    print(f"\n=== Testing Shot: {test_shot.full_name} ===")
    print(f"Workspace: {test_shot.workspace_path}")

    # Test each fallback method individually
    print("\n1. Testing editorial thumbnail:")
    editorial_thumbnail = None
    if PathUtils.validate_path_exists(test_shot.thumbnail_dir, "Thumbnail directory"):
        from utils import FileUtils

        editorial_thumbnail = FileUtils.get_first_image_file(test_shot.thumbnail_dir)

    if editorial_thumbnail:
        print(f"   ✓ Found editorial: {editorial_thumbnail}")
    else:
        print(f"   ✗ No editorial thumbnail at: {test_shot.thumbnail_dir}")

    print("\n2. Testing turnover plate thumbnail:")
    turnover_thumbnail = PathUtils.find_turnover_plate_thumbnail(
        Config.SHOWS_ROOT, test_shot.show, test_shot.sequence, test_shot.shot
    )

    if turnover_thumbnail:
        print(f"   ✓ Found turnover plate: {turnover_thumbnail}")
    else:
        print("   ✗ No turnover plate thumbnails found")

    print("\n3. Testing third fallback (any EXR with 1001 in publish):")
    publish_thumbnail = PathUtils.find_any_publish_thumbnail(
        Config.SHOWS_ROOT, test_shot.show, test_shot.sequence, test_shot.shot
    )

    if publish_thumbnail:
        print(f"   ✓ Found publish EXR: {publish_thumbnail}")
        print(f"   Full path: {publish_thumbnail}")
        print(
            f"   File size: {publish_thumbnail.stat().st_size / (1024 * 1024):.2f} MB"
        )
        # Show directory structure
        relative_path = publish_thumbnail.relative_to(
            Path(test_shot.workspace_path) / "publish"
        )
        print(f"   Relative to publish: {relative_path}")
    else:
        print("   ✗ No EXR files with 1001 found in publish folder")

    print("\n4. Testing complete get_thumbnail_path() with all fallbacks:")
    final_thumbnail = test_shot.get_thumbnail_path()

    if final_thumbnail:
        print(f"   ✓ Found thumbnail: {final_thumbnail}")
        if "editorial" in str(final_thumbnail):
            print("   Source: Editorial (first fallback)")
        elif "turnover" in str(final_thumbnail):
            print("   Source: Turnover plate (second fallback)")
        elif "publish" in str(final_thumbnail):
            print("   Source: Publish folder EXR (third fallback)")
        else:
            print("   Source: Unknown")
    else:
        print("   ✗ No thumbnail found from any source")

    # Test another shot
    print("\n" + "=" * 60)
    test_shot2 = Shot(
        show="jack_ryan",
        sequence="GG_000",
        shot="0050",
        workspace_path="/shows/jack_ryan/shots/GG_000/GG_000_0050",
    )

    print(f"\n=== Testing Shot 2: {test_shot2.full_name} ===")
    thumbnail2 = test_shot2.get_thumbnail_path()

    if thumbnail2:
        print(f"   ✓ Found thumbnail: {thumbnail2.name}")
        if "editorial" in str(thumbnail2):
            print("   Source: Editorial")
        elif "turnover" in str(thumbnail2):
            print("   Source: Turnover plate")
        elif "publish" in str(thumbnail2):
            print("   Source: Publish folder EXR")
    else:
        print("   ✗ No thumbnail found")

    print("\n" + "=" * 60)
    print("Third Fallback Test Complete")
    print("=" * 60)


if __name__ == "__main__":
    test_third_fallback()
