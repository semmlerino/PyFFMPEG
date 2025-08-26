"""Test pytest imports to isolate the issue."""

import sys
from pathlib import Path

sys.path.insert(0, ".")


def test_import_step_by_step():
    print("Step 1: Testing basic imports...")
    from config import Config

    print("Config imported successfully")

    print("Step 2: Testing utils import...")
    from utils import PathUtils

    print("PathUtils imported successfully")

    print("Step 3: Testing mock import...")
    from unittest.mock import patch

    print("Mock imported successfully")

    print("Step 4: Testing patch context...")
    with patch.object(Config, "SHOWS_ROOT", "/tmp/test"):
        print("Patch context works")

    print("Step 5: Testing path operations within patch...")
    with patch.object(Config, "SHOWS_ROOT", "/tmp/test"):
        # Create test structure
        test_path = Path(
            "/tmp/test/testshow/shots/seq01/seq01_shot01/publish/turnover/plate/FG01/v001/exr/4312x2304"
        )
        test_path.mkdir(parents=True, exist_ok=True)
        test_file = test_path / "test.1001.exr"
        test_file.touch()

        result = PathUtils.find_turnover_plate_thumbnail(
            "/tmp/test", "testshow", "seq01", "shot01"
        )
        print(f"Result within patch: {result}")

        # Cleanup
        import shutil

        shutil.rmtree("/tmp/test", ignore_errors=True)

    print("All steps completed successfully!")


if __name__ == "__main__":
    test_import_step_by_step()
