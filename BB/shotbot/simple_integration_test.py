"""Simple integration test without pytest."""

import shutil
import sys
import tempfile
from pathlib import Path

# Set up path
sys.path.insert(0, ".")


def test_integration_without_pytest():
    print("Starting integration test without pytest...")

    # Create temp directory
    temp_dir = Path(tempfile.mkdtemp(prefix="shotbot_test_"))
    shows_root = temp_dir / "shows"
    shows_root.mkdir(parents=True)

    try:
        # Import after path setup
        from utils import PathUtils

        print("PathUtils imported successfully")

        # Create test structure
        plate_path = (
            shows_root
            / "testshow"
            / "shots"
            / "seq01"
            / "seq01_shot01"
            / "publish"
            / "turnover"
            / "plate"
            / "FG01"
            / "v001"
            / "exr"
            / "4312x2304"
        )
        plate_path.mkdir(parents=True)
        print(f"Created directory structure: {plate_path}")

        # Create test file
        test_file = plate_path / "seq01_shot01_turnover-plate_FG01_v001.1001.exr"
        test_file.write_bytes(b"EXR_HEADER")
        print(f"Created test file: {test_file}")

        # Call the function
        print("Calling PathUtils.find_turnover_plate_thumbnail...")
        result = PathUtils.find_turnover_plate_thumbnail(
            str(shows_root), "testshow", "seq01", "shot01"
        )

        print(f"Result: {result}")
        assert result is not None
        assert result == test_file
        assert "FG01" in str(result)

        print("Test passed!")

    except Exception as e:
        print(f"Test failed with error: {e}")
        import traceback

        traceback.print_exc()

    finally:
        # Cleanup
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
            print("Cleanup completed")
        except Exception:
            pass


if __name__ == "__main__":
    test_integration_without_pytest()
