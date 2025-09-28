#!/usr/bin/env python3
"""Fast test runner - runs only fast tests and skips slow ones."""

# Standard library imports
import subprocess
import sys
import time


def run_fast_tests():
    """Run only fast tests."""
    start = time.time()

    # Run tests excluding slow markers
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-m",
        "not slow",  # Skip slow tests
        "--tb=short",  # Short traceback
        "--maxfail=10",  # Stop after 10 failures
        "-q",  # Quiet output
        "tests/",
    ]

    result = subprocess.run(cmd)

    elapsed = time.time() - start
    print(f"\n⏱️  Fast tests completed in {elapsed:.1f} seconds")

    return result.returncode


if __name__ == "__main__":
    sys.exit(run_fast_tests())
