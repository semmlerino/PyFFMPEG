#!/usr/bin/env python3
"""
Quick validation script to test the current fixes we've implemented.

This script verifies that:
1. Individual test files that were fixed continue to work
2. Small batches work as expected
3. The new MainWindow cleanup() method is working
"""

# Standard library imports
import subprocess
import sys
import time
from pathlib import Path


def run_test(description: str, cmd: list[str], timeout: int = 60) -> bool:
    """Run a test command and report results."""
    print(f"\n{'=' * 50}")
    print(f"Testing: {description}")
    print(f"Command: {' '.join(cmd)}")

    start_time = time.time()
    try:
        result = subprocess.run(
            cmd,
            timeout=timeout,
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent,
        )

        duration = time.time() - start_time
        success = result.returncode == 0

        if success:
            print(f"✅ PASS ({duration:.1f}s)")
            # Show test count from output
            if "passed" in result.stdout:
                # Standard library imports
                import re

                match = re.search(r"(\d+) passed", result.stdout)
                if match:
                    print(f"   {match.group(1)} tests passed")
        else:
            print(f"❌ FAIL ({duration:.1f}s, exit code: {result.returncode})")
            if result.stderr:
                print(f"   Error: {result.stderr.strip()}")

        return success

    except subprocess.TimeoutExpired:
        print(f"⏰ TIMEOUT after {timeout}s")
        return False
    except Exception as e:
        print(f"💥 ERROR: {e}")
        return False


def main() -> int:
    """Test current fixes."""
    print("=== Testing Current Test Suite Fixes ===")
    print(f"Working directory: {Path(__file__).parent}")

    # Change to correct directory
    original_cwd = Path.cwd()
    os.chdir(Path(__file__).parent)

    try:
        tests_to_run = [
            # These should work based on previous conversation
            (
                "Cache Manager Tests (57 tests)",
                ["python3", "-m", "pytest", "tests/unit/test_cache_manager.py", "-v"],
            ),
            (
                "EXR Edge Cases",
                ["python3", "-m", "pytest", "tests/unit/test_exr_edge_cases.py", "-v"],
            ),
            (
                "MainWindow Unit Tests",
                ["python3", "-m", "pytest", "tests/unit/test_main_window.py", "-v"],
            ),
            # Small batch that should work
            (
                "Small Batch (3 files)",
                [
                    "python3",
                    "-m",
                    "pytest",
                    "tests/unit/test_cache_manager.py",
                    "tests/unit/test_exr_edge_cases.py",
                    "tests/unit/test_main_window.py",
                    "-v",
                ],
                120,
            ),
            # Quick validation tests
            ("Quick Validation", ["python3", "tests/utilities/quick_test.py"]),
            # Test MainWindow cleanup is working - run integration test
            (
                "MainWindow Integration (cleanup test)",
                [
                    "python3",
                    "-m",
                    "pytest",
                    "tests/integration/test_main_window_complete.py",
                    "-v",
                ],
                90,
            ),
        ]

        results = []
        for test_data in tests_to_run:
            if len(test_data) == 3:
                description, cmd, timeout = test_data
            else:
                description, cmd = test_data
                timeout = 60

            success = run_test(description, cmd, timeout)
            results.append((description, success))

            # If basic tests are failing, stop here
            if not success and len(results) <= 3:
                print(f"\n🚨 Basic test failed: {description}")
                print("Fix this issue before proceeding to larger test batches.")
                break

        # Summary
        print(f"\n{'=' * 50}")
        print("SUMMARY:")
        passed = sum(1 for _, success in results if success)
        total = len(results)
        print(f"{passed}/{total} test groups passed")

        for description, success in results:
            status = "✅" if success else "❌"
            print(f"{status} {description}")

        if passed == total:
            print(f"\n🎉 All current fixes are working! ({passed}/{total})")
            print("You can now test larger combinations or the full suite.")
            return 0
        else:
            print(f"\n⚠️  Some fixes need attention ({passed}/{total})")
            return 1

    finally:
        os.chdir(original_cwd)


if __name__ == "__main__":
    # Standard library imports
    import os

    sys.exit(main())
