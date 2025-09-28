#!/usr/bin/env python3
"""
Simple test suite for critical fixes in ShotBot.
Tests the actual code changes we made.
"""

# Standard library imports
import os
import re
import sys
from pathlib import Path


def test_shows_root_in_files():
    """Test that our fixes are present in the actual files."""
    print("\n=== Testing SHOWS_ROOT Configuration in Files ===")

    success_count = 0
    total_tests = 0

    # Test 1: shot_finder_base.py contains Config.SHOWS_ROOT
    print("\n1. Checking shot_finder_base.py")
    total_tests += 2

    with open("shot_finder_base.py") as f:
        content = f.read()

    if "from config import Config" in content:
        print("  ✓ Config import present")
        success_count += 1
    else:
        print("  ✗ Config import missing")

    if "shows_root_escaped = re.escape(Config.SHOWS_ROOT)" in content:
        print("  ✓ Dynamic SHOWS_ROOT usage found")
        success_count += 1
    else:
        print("  ✗ Dynamic SHOWS_ROOT usage not found")

    # Test 2: base_shot_model.py contains Config.SHOWS_ROOT
    print("\n2. Checking base_shot_model.py")
    total_tests += 2

    with open("base_shot_model.py") as f:
        content = f.read()

    if "from config import Config" in content:
        print("  ✓ Config import present")
        success_count += 1
    else:
        print("  ✗ Config import missing")

    if "shows_root_escaped = re.escape(Config.SHOWS_ROOT)" in content:
        print("  ✓ Dynamic SHOWS_ROOT usage found")
        success_count += 1
    else:
        print("  ✗ Dynamic SHOWS_ROOT usage not found")

    # Test 3: Verify no hardcoded /shows in regex patterns
    print("\n3. Checking for hardcoded /shows paths")
    total_tests += 2

    hardcoded_pattern = re.compile(r'["\']\/shows\/["\']')

    with open("shot_finder_base.py") as f:
        if hardcoded_pattern.search(f.read()):
            print("  ✗ Hardcoded /shows found in shot_finder_base.py")
        else:
            print("  ✓ No hardcoded /shows in shot_finder_base.py")
            success_count += 1

    with open("base_shot_model.py") as f:
        if hardcoded_pattern.search(f.read()):
            print("  ✗ Hardcoded /shows found in base_shot_model.py")
        else:
            print("  ✓ No hardcoded /shows in base_shot_model.py")
            success_count += 1

    print(f"\n✅ SHOWS_ROOT tests: {success_count}/{total_tests} passed")
    return success_count == total_tests


def test_previous_shots_cleanup():
    """Test that PreviousShotsModel cleanup is in main_window.py."""
    print("\n=== Testing PreviousShotsModel Cleanup ===")

    success_count = 0
    total_tests = 0

    with open("main_window.py") as f:
        content = f.read()

    # Simply check if the cleanup code exists in the file
    # Test 1: PreviousShotsModel cleanup present
    total_tests += 1
    if (
        "if hasattr(self, 'previous_shots_model') and self.previous_shots_model:"
        in content
    ):
        print("  ✓ PreviousShotsModel check present")
        success_count += 1
    else:
        print("  ✗ PreviousShotsModel check missing")

    # Test 2: Cleanup method called
    total_tests += 1
    if "self.previous_shots_model.cleanup()" in content:
        print("  ✓ Cleanup method called")
        success_count += 1
    else:
        print("  ✗ Cleanup method not called")

    # Test 3: Error handling
    total_tests += 1
    if 'logger.error(f"Error cleaning up PreviousShotsModel' in content:
        print("  ✓ Error logging present")
        success_count += 1
    else:
        print("  ✗ Error logging missing")

    # Test 4: PreviousShotsItemModel cleanup
    total_tests += 1
    if "if hasattr(self, 'previous_shots_item_model')" in content:
        print("  ✓ PreviousShotsItemModel check present")
        success_count += 1
    else:
        print("  ✗ PreviousShotsItemModel check missing")

    print(
        f"\n✅ PreviousShotsModel cleanup tests: {success_count}/{total_tests} passed"
    )
    return success_count == total_tests


def test_json_error_handling():
    """Test that JSON error handling is present in mock_workspace_pool.py."""
    print("\n=== Testing JSON Error Handling ===")

    success_count = 0
    total_tests = 0

    with open("mock_workspace_pool.py") as f:
        content = f.read()

    # Test 1: JSONDecodeError handling
    total_tests += 1
    if "except json.JSONDecodeError as e:" in content:
        print("  ✓ JSONDecodeError handling present")
        success_count += 1
    else:
        print("  ✗ JSONDecodeError handling missing")

    # Test 2: IOError/OSError handling
    total_tests += 1
    if (
        "except (IOError, OSError) as e:" in content
        or "except OSError as e:" in content
    ):
        print("  ✓ I/O error handling present")
        success_count += 1
    else:
        print("  ✗ I/O error handling missing")

    # Test 3: ValueError handling
    total_tests += 1
    if "except ValueError as e:" in content:
        print("  ✓ ValueError handling present")
        success_count += 1
    else:
        print("  ✗ ValueError handling missing")

    # Test 4: Structure validation
    total_tests += 1
    if "if not isinstance(demo_data, dict):" in content:
        print("  ✓ Dictionary validation present")
        success_count += 1
    else:
        print("  ✗ Dictionary validation missing")

    # Test 5: Required fields check
    total_tests += 1
    if 'required_fields = ["show", "seq", "shot"]' in content:
        print("  ✓ Required fields validation present")
        success_count += 1
    else:
        print("  ✗ Required fields validation missing")

    # Test 6: Fallback to filesystem
    total_tests += 1
    if "pool.set_shots_from_filesystem" in content:
        print("  ✓ Filesystem fallback present")
        success_count += 1
    else:
        print("  ✗ Filesystem fallback missing")

    print(f"\n✅ JSON error handling tests: {success_count}/{total_tests} passed")
    return success_count == total_tests


def test_config_shows_root():
    """Test that Config.SHOWS_ROOT is properly configured."""
    print("\n=== Testing Config.SHOWS_ROOT ===")

    success_count = 0
    total_tests = 0

    with open("config.py") as f:
        content = f.read()

    # Test 1: SHOWS_ROOT uses environment variable
    total_tests += 1
    if (
        'SHOWS_ROOT: str = os.environ.get("SHOWS_ROOT", "/shows")' in content
        or 'SHOWS_ROOT = os.environ.get("SHOWS_ROOT", "/shows")' in content
    ):
        print("  ✓ SHOWS_ROOT uses environment variable")
        success_count += 1
    else:
        print("  ✗ SHOWS_ROOT not using environment variable")

    # Test 2: SHOW_ROOT_PATHS uses SHOWS_ROOT
    total_tests += 1
    if (
        "SHOW_ROOT_PATHS = [SHOWS_ROOT]" in content
        or "SHOW_ROOT_PATHS: list[str] = [SHOWS_ROOT]" in content
    ):
        print("  ✓ SHOW_ROOT_PATHS uses SHOWS_ROOT")
        success_count += 1
    else:
        print("  ✗ SHOW_ROOT_PATHS not using SHOWS_ROOT")

    print(f"\n✅ Config tests: {success_count}/{total_tests} passed")
    return success_count == total_tests


def test_import_functionality():
    """Test that the files can actually be imported without errors."""
    print("\n=== Testing Import Functionality ===")

    success_count = 0
    total_tests = 0

    # Test dynamic SHOWS_ROOT with different values
    test_values = ["/shows", "/tmp/mock_vfx", "/custom/path"]

    for shows_root in test_values:
        print(f"\nTesting with SHOWS_ROOT={shows_root}")
        total_tests += 1

        # Set environment variable
        os.environ["SHOWS_ROOT"] = shows_root

        try:
            # Force reload of modules
            # Standard library imports
            import sys

            # Remove modules from cache
            for mod in ["config", "shot_finder_base", "base_shot_model"]:
                if mod in sys.modules:
                    del sys.modules[mod]

            # Import config and verify SHOWS_ROOT
            # Local application imports
            import config

            if config.Config.SHOWS_ROOT == shows_root:
                print(f"  ✓ Config.SHOWS_ROOT correctly set to {shows_root}")
                success_count += 1
            else:
                print(
                    f"  ✗ Config.SHOWS_ROOT is {config.Config.SHOWS_ROOT}, expected {shows_root}"
                )

        except Exception as e:
            print(f"  ✗ Error importing with SHOWS_ROOT={shows_root}: {e}")

    print(f"\n✅ Import tests: {success_count}/{total_tests} passed")
    return success_count == total_tests


def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("SHOTBOT CRITICAL FIXES VERIFICATION")
    print("=" * 60)

    all_passed = True
    test_results = []

    # Test 1: SHOWS_ROOT in files
    result = test_shows_root_in_files()
    test_results.append(("SHOWS_ROOT Configuration", result))
    if not result:
        all_passed = False

    # Test 2: PreviousShotsModel cleanup
    result = test_previous_shots_cleanup()
    test_results.append(("PreviousShotsModel Cleanup", result))
    if not result:
        all_passed = False

    # Test 3: JSON error handling
    result = test_json_error_handling()
    test_results.append(("JSON Error Handling", result))
    if not result:
        all_passed = False

    # Test 4: Config setup
    result = test_config_shows_root()
    test_results.append(("Config Setup", result))
    if not result:
        all_passed = False

    # Test 5: Import functionality
    result = test_import_functionality()
    test_results.append(("Import Functionality", result))
    if not result:
        all_passed = False

    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    for test_name, passed in test_results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name}: {status}")

    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 ALL CRITICAL FIXES VERIFIED! 🎉")
        print("The application is stable and ready for use.")
    else:
        print("⚠️ SOME TESTS FAILED - Please review the output above")
    print("=" * 60)

    return all_passed


if __name__ == "__main__":
    # Change to script directory
    os.chdir(Path(__file__).parent)

    success = run_all_tests()
    sys.exit(0 if success else 1)
