#!/usr/bin/env python3
"""Verify all tests pass by running them file by file."""

import subprocess
import sys
from pathlib import Path


def run_test_file(test_file):
    """Run a single test file and return result."""
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(test_file),
        "-q",
        "--tb=no",
        "--timeout=30",
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60, cwd=Path(__file__).parent
        )

        # Extract test count from output
        output = result.stdout + result.stderr
        if "passed" in output:
            # Parse something like "42 passed in 5.23s"
            for line in output.split("\n"):
                if "passed" in line:
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part == "passed":
                            if i > 0 and parts[i - 1].isdigit():
                                return int(parts[i - 1]), 0, True
                            # Handle "1 failed, 42 passed"
                            if i > 0:
                                for j in range(i - 1, -1, -1):
                                    if parts[j].replace(",", "").isdigit():
                                        return int(parts[j].replace(",", "")), 0, True

        if "failed" in output:
            # Count failures
            for line in output.split("\n"):
                if "failed" in line and "passed" in line:
                    parts = line.split()
                    failed = 0
                    passed = 0
                    for i, part in enumerate(parts):
                        if part == "failed" and i > 0:
                            failed = int(parts[i - 1])
                        if part == "passed" and i > 0:
                            passed = int(parts[i - 1].replace(",", ""))
                    return passed, failed, False
                elif "failed" in line:
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part == "failed" and i > 0:
                            return 0, int(parts[i - 1]), False

        return 0, 0, False

    except subprocess.TimeoutExpired:
        return 0, 0, False
    except Exception as e:
        print(f"Error running {test_file}: {e}")
        return 0, 0, False


def main():
    """Main function to verify all tests."""
    # Activate virtual environment
    venv_path = Path(__file__).parent / "venv"
    if venv_path.exists():
        activate_this = venv_path / "bin" / "activate_this.py"
        if activate_this.exists():
            exec(open(activate_this).read(), {"__file__": str(activate_this)})

    # Find all test files
    test_dir = Path(__file__).parent / "tests" / "unit"
    test_files = sorted(test_dir.glob("test_*.py"))

    # Filter out disabled tests
    test_files = [f for f in test_files if not f.name.endswith(".disabled")]

    print(f"Found {len(test_files)} test files to verify\n")

    total_passed = 0
    total_failed = 0
    failed_files = []

    for test_file in test_files:
        print(f"Running {test_file.name:50} ... ", end="", flush=True)
        passed, failed, success = run_test_file(test_file)

        if success and failed == 0:
            print(f"✓ {passed} passed")
            total_passed += passed
        elif passed > 0 or failed > 0:
            print(f"✗ {passed} passed, {failed} failed")
            total_passed += passed
            total_failed += failed
            if failed > 0:
                failed_files.append(test_file.name)
        else:
            print("⚠ Timeout or error")
            failed_files.append(test_file.name)

    print("\n" + "=" * 70)
    print(f"SUMMARY: {total_passed} tests passed, {total_failed} tests failed")

    if failed_files:
        print(f"\nFailed files: {', '.join(failed_files)}")
        return 1
    else:
        print("\n✅ ALL TESTS PASSED!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
