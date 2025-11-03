#!/usr/bin/env python3
"""Clean test runner that bypasses pytest-qt issues."""

# Standard library imports
import os
import subprocess
import sys


# Set environment to disable Qt plugins
env = os.environ.copy()
env["PYTEST_QT_API"] = "none"
env["QT_QPA_PLATFORM"] = "offscreen"


def run_tests():
    """Run tests with clean environment."""
    print("Running clean pytest suite...")
    print("=" * 70)

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-p",
        "no:qt",  # Disable pytest-qt
        "-p",
        "no:xvfb",  # Disable xvfb
        "-p",
        "no:warnings",  # Disable warnings
        "--tb=short",
        "-v",
        "--no-header",
        "tests/",
    ]

    result = subprocess.run(cmd, check=False, env=env, capture_output=True, text=True)

    print(result.stdout)
    print(result.stderr)

    return result.returncode


if __name__ == "__main__":
    sys.exit(run_tests())
