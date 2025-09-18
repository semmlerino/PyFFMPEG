#!/usr/bin/env python3
"""
Comprehensive test suite for critical fixes in ShotBot.

This test suite validates:
1. Dynamic SHOWS_ROOT configuration in regex patterns
2. PreviousShotsModel cleanup in main window closeEvent
3. JSON error handling in mock workspace pool

Run with: python test_critical_fixes_complete.py
"""

import json
import os
import re
import sys
import tempfile
from pathlib import Path
from unittest import mock

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))


def test_shows_root_dynamic_configuration():
    """Test that regex patterns adapt to SHOWS_ROOT configuration."""
    print("\n=== Testing Dynamic SHOWS_ROOT Configuration ===")

    test_cases = [
        ("/shows", r"\/shows\/([^/]+)/shots/([^/]+)/\2_([^/]+)/"),
        ("/tmp/mock_vfx", r"\/tmp\/mock_vfx\/([^/]+)/shots/([^/]+)/\2_([^/]+)/"),
        ("/custom/path", r"\/custom\/path\/([^/]+)/shots/([^/]+)/\2_([^/]+)/"),
    ]

    success_count = 0

    for shows_root, expected_pattern_start in test_cases:
        print(f"\nTesting with SHOWS_ROOT={shows_root}")

        # Set environment variable
        with mock.patch.dict(os.environ, {"SHOWS_ROOT": shows_root}):
            # Force reload of config to pick up new environment
            import importlib

            import config

            importlib.reload(config)

            # Test shot_finder_base.py
            try:
                from shot_finder_base import ShotFinderBase

                class TestFinder(ShotFinderBase):
                    def find_shots(self) -> None:
                        pass  # Abstract method implementation

                finder = TestFinder()
                pattern = finder._shot_pattern.pattern

                # Check pattern contains escaped SHOWS_ROOT
                shows_root_escaped = re.escape(shows_root)
                if shows_root_escaped in pattern:
                    print(
                        f"  ✓ shot_finder_base.py: Pattern contains {shows_root_escaped}"
                    )
                    success_count += 1
                else:
                    print(
                        f"  ✗ shot_finder_base.py: Pattern missing {shows_root_escaped}"
                    )
                    print(f"    Got: {pattern}")

                # Test pattern matching
                test_path = f"{shows_root}/show1/shots/seq1/seq1_0010/user/test"
                match = finder._shot_pattern.search(test_path)
                if match and match.groups() == ("show1", "seq1", "0010"):
                    print("  ✓ shot_finder_base.py: Pattern matches correctly")
                    success_count += 1
                else:
                    print("  ✗ shot_finder_base.py: Pattern match failed")

            except Exception as e:
                print(f"  ✗ Error testing shot_finder_base.py: {e}")

            # Test base_shot_model.py
            try:
                from base_shot_model import BaseShotModel

                # Create a mock implementation
                class TestShotModel(BaseShotModel):
                    def load_shots(self) -> None:
                        pass

                    def refresh_strategy(self) -> None:
                        pass

                model = TestShotModel()
                pattern = model._parse_pattern.pattern

                # Check pattern contains escaped SHOWS_ROOT
                if shows_root_escaped in pattern:
                    print(
                        f"  ✓ base_shot_model.py: Pattern contains {shows_root_escaped}"
                    )
                    success_count += 1
                else:
                    print(
                        f"  ✗ base_shot_model.py: Pattern missing {shows_root_escaped}"
                    )
                    print(f"    Got: {pattern}")

                # Test pattern matching
                test_line = f"workspace {shows_root}/show1/shots/seq1/seq1_0010"
                match = model._parse_pattern.search(test_line)
                if match:
                    print("  ✓ base_shot_model.py: Workspace pattern matches")
                    success_count += 1
                else:
                    print("  ✗ base_shot_model.py: Workspace pattern failed")

            except Exception as e:
                print(f"  ✗ Error testing base_shot_model.py: {e}")

    print(f"\n✅ Dynamic SHOWS_ROOT tests: {success_count}/8 passed")
    return success_count == 8


def test_previous_shots_model_cleanup():
    """Test that PreviousShotsModel is properly cleaned up in main_window closeEvent."""
    print("\n=== Testing PreviousShotsModel Cleanup ===")

    # Read main_window.py and check for cleanup code
    main_window_path = Path(__file__).parent / "main_window.py"
    if not main_window_path.exists():
        print("✗ main_window.py not found")
        return False

    with open(main_window_path) as f:
        content = f.read()

    checks = [
        (
            "PreviousShotsModel cleanup exists",
            "if hasattr(self, 'previous_shots_model') and self.previous_shots_model:",
        ),
        ("Cleanup method called", "self.previous_shots_model.cleanup()"),
        ("Error handling present", "except Exception as e:"),
        ("Error logging", 'logger.error(f"Error cleaning up PreviousShotsModel: {e}")'),
        (
            "PreviousShotsItemModel cleanup",
            "if hasattr(self, 'previous_shots_item_model')",
        ),
        ("ItemModel cleanup call", "self.previous_shots_item_model.cleanup()"),
    ]

    success_count = 0
    for check_name, check_string in checks:
        if check_string in content:
            print(f"  ✓ {check_name}")
            success_count += 1
        else:
            print(f"  ✗ {check_name} not found")

    # Verify cleanup is in closeEvent method
    import re

    pattern = r"def closeEvent\(self.*?\).*?previous_shots_model.*?cleanup\(\)"
    if re.search(pattern, content, re.DOTALL):
        print("  ✓ Cleanup is in closeEvent method")
        success_count += 1
    else:
        print("  ✗ Cleanup not found in closeEvent method")

    print(f"\n✅ PreviousShotsModel cleanup tests: {success_count}/7 passed")
    return success_count == 7


def test_json_error_handling():
    """Test comprehensive JSON error handling in mock_workspace_pool."""
    print("\n=== Testing JSON Error Handling ===")

    import logging

    from mock_workspace_pool import create_mock_pool_from_filesystem

    # Set up logging to capture error messages
    logger = logging.getLogger("mock_workspace_pool")

    success_count = 0

    # Test 1: Missing demo_shots.json (should fall back gracefully)
    print("\n1. Testing missing demo_shots.json")
    with mock.patch("pathlib.Path.exists", return_value=False):
        pool = create_mock_pool_from_filesystem()
        if pool is not None:
            print("  ✓ Handles missing file gracefully")
            success_count += 1
        else:
            print("  ✗ Failed to handle missing file")

    # Test 2: Invalid JSON syntax
    print("\n2. Testing invalid JSON syntax")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("{invalid json}")
        temp_path = f.name

    try:
        with mock.patch("pathlib.Path", return_value=Path(temp_path)):
            with mock.patch("pathlib.Path.exists", return_value=True):
                # Capture log output
                with mock.patch.object(logger, "error") as mock_error:
                    pool = create_mock_pool_from_filesystem()
                    if any(
                        "JSONDecodeError" in str(call)
                        for call in mock_error.call_args_list
                    ):
                        print("  ✓ JSONDecodeError handled and logged")
                        success_count += 1
                    else:
                        print("  ✗ JSONDecodeError not properly handled")
    finally:
        os.unlink(temp_path)

    # Test 3: Wrong JSON structure (not a dict)
    print("\n3. Testing wrong JSON structure (array instead of dict)")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump([], f)  # Array instead of dict
        temp_path = f.name

    try:
        with mock.patch("pathlib.Path.__new__", return_value=Path(temp_path)):
            with mock.patch("pathlib.Path.exists", return_value=True):
                with mock.patch.object(logger, "error") as mock_error:
                    pool = create_mock_pool_from_filesystem()
                    if any(
                        "Expected dict" in str(call)
                        for call in mock_error.call_args_list
                    ):
                        print("  ✓ Wrong structure handled")
                        success_count += 1
                    else:
                        print("  ✗ Wrong structure not handled")
    finally:
        os.unlink(temp_path)

    # Test 4: Missing 'shots' key
    print("\n4. Testing missing 'shots' key")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"other_key": "value"}, f)
        temp_path = f.name

    try:
        with mock.patch("pathlib.Path.__new__", return_value=Path(temp_path)):
            with mock.patch("pathlib.Path.exists", return_value=True):
                with mock.patch.object(logger, "error") as mock_error:
                    pool = create_mock_pool_from_filesystem()
                    if any(
                        "Missing 'shots' key" in str(call)
                        for call in mock_error.call_args_list
                    ):
                        print("  ✓ Missing 'shots' key handled")
                        success_count += 1
                    else:
                        print("  ✗ Missing 'shots' key not handled")
    finally:
        os.unlink(temp_path)

    # Test 5: Invalid shot structure (missing required fields)
    print("\n5. Testing invalid shot structure")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(
            {
                "shots": [
                    {"show": "test"},  # Missing seq and shot
                    {"seq": "seq01", "shot": "0010"},  # Missing show
                ]
            },
            f,
        )
        temp_path = f.name

    try:
        with mock.patch("pathlib.Path.__new__", return_value=Path(temp_path)):
            with mock.patch("pathlib.Path.exists", return_value=True):
                with mock.patch.object(logger, "error") as mock_error:
                    pool = create_mock_pool_from_filesystem()
                    if any(
                        "missing fields" in str(call)
                        for call in mock_error.call_args_list
                    ):
                        print("  ✓ Invalid shot structure handled")
                        success_count += 1
                    else:
                        print("  ✗ Invalid shot structure not handled")
    finally:
        os.unlink(temp_path)

    # Test 6: Valid JSON structure
    print("\n6. Testing valid JSON structure")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(
            {
                "shots": [
                    {"show": "test_show", "seq": "seq01", "shot": "0010"},
                    {"show": "test_show", "seq": "seq01", "shot": "0020"},
                ]
            },
            f,
        )
        temp_path = f.name

    try:
        # Need to properly mock the path
        with mock.patch.object(
            Path, "parent", property(lambda self: Path("/mock/dir"))
        ):
            with mock.patch(
                "builtins.open", mock.mock_open(read_data=open(temp_path).read())
            ):
                with mock.patch("pathlib.Path.exists", return_value=True):
                    pool = create_mock_pool_from_filesystem()
                    if pool and len(pool.shots) == 2:
                        print("  ✓ Valid JSON processed correctly")
                        success_count += 1
                    else:
                        print("  ✗ Valid JSON not processed correctly")
    finally:
        os.unlink(temp_path)

    print(f"\n✅ JSON error handling tests: {success_count}/6 passed")
    return success_count == 6


def run_all_tests():
    """Run all critical fix tests."""
    print("=" * 60)
    print("SHOTBOT CRITICAL FIXES TEST SUITE")
    print("=" * 60)

    all_passed = True

    # Test 1: Dynamic SHOWS_ROOT configuration
    if not test_shows_root_dynamic_configuration():
        all_passed = False
        print("❌ Dynamic SHOWS_ROOT tests FAILED")
    else:
        print("✅ Dynamic SHOWS_ROOT tests PASSED")

    # Test 2: PreviousShotsModel cleanup
    if not test_previous_shots_model_cleanup():
        all_passed = False
        print("❌ PreviousShotsModel cleanup tests FAILED")
    else:
        print("✅ PreviousShotsModel cleanup tests PASSED")

    # Test 3: JSON error handling
    if not test_json_error_handling():
        all_passed = False
        print("❌ JSON error handling tests FAILED")
    else:
        print("✅ JSON error handling tests PASSED")

    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 ALL CRITICAL FIX TESTS PASSED! 🎉")
        print("The application is stable and ready for use.")
    else:
        print("⚠️ SOME TESTS FAILED - Please review the output above")
    print("=" * 60)

    return all_passed


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.WARNING)  # Reduce noise during tests

    success = run_all_tests()
    sys.exit(0 if success else 1)
