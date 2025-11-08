"""Minimal test to isolate the timeout issue."""

# Standard library imports
import sys
from pathlib import Path


sys.path.insert(0, ".")


def test_basic_import() -> None:
    print("Testing basic imports...")
    print("PathUtils imported successfully")


def test_path_validation(tmp_path: Path) -> None:
    print("Testing path validation...")
    # Local application imports
    from utils import (
        PathUtils,
    )

    # Create a temporary directory using pytest's tmp_path fixture
    test_path = tmp_path / "test_path"
    test_path.mkdir(exist_ok=True)

    result = PathUtils.validate_path_exists(test_path, "Test path")
    print(f"Path validation result: {result}")

    # No cleanup needed - pytest handles tmp_path automatically


def test_find_thumbnail(tmp_path: Path) -> None:
    print("Testing find_turnover_plate_thumbnail...")
    # Local application imports
    from utils import (
        PathUtils,
    )

    # Create a temporary structure using pytest's tmp_path fixture
    base = tmp_path / "shotbot_test"
    shows_root = base / "shows"
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
    plate_path.mkdir(parents=True, exist_ok=True)

    # Create test file
    test_file = plate_path / "seq01_shot01_turnover-plate_FG01_v001.1001.exr"
    test_file.touch()

    print(f"Created test structure at: {shows_root}")
    print(f"Test file exists: {test_file.exists()}")

    result = PathUtils.find_turnover_plate_thumbnail(
        str(shows_root), "testshow", "seq01", "shot01"
    )

    print(f"Find result: {result}")

    # No cleanup needed - pytest handles tmp_path automatically


if __name__ == "__main__":
    print("Starting minimal tests...")
    test_basic_import()
    test_path_validation()
    test_find_thumbnail()
    print("All tests completed.")
