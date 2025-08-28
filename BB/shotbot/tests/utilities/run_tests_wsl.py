#!/usr/bin/env python3
"""Optimized test runner for WSL environment with filesystem performance considerations."""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

# Ensure we're in the project directory
project_root = Path(__file__).parent
os.chdir(project_root)

# Set up environment for offscreen Qt
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_LOGGING_RULES"] = "*.debug=false"
os.environ["PYTEST_QT_API"] = "pyside6"

# Disable Python bytecode writing to reduce I/O
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

# Reduce pytest verbosity
os.environ["PYTEST_CURRENT_TEST"] = ""


def run_fast_tests():
    """Run only fast unit tests for quick feedback."""
    print("🚀 Running fast tests only...")
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-c",
        "pytest_wsl.ini",
        "-m",
        "fast or (unit and not slow)",
        "--maxfail=3",  # Stop after 3 failures
        "-x",  # Stop on first failure
        "--durations=10",  # Show 10 slowest tests
        "tests/unit",
    ]
    return subprocess.run(cmd).returncode


def run_critical_tests():
    """Run only critical path tests."""
    print("🎯 Running critical tests...")
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-c",
        "pytest_wsl.ini",
        "-m",
        "critical",
        "--maxfail=1",
        "tests/",
    ]
    return subprocess.run(cmd).returncode


def run_single_file(filepath):
    """Run tests from a single file to minimize collection overhead."""
    print(f"📝 Running tests from {filepath}...")
    cmd = [sys.executable, "-m", "pytest", "-c", "pytest_wsl.ini", filepath, "-v"]
    return subprocess.run(cmd).returncode


def run_focused_tests(pattern):
    """Run tests matching a pattern."""
    print(f"🔍 Running tests matching '{pattern}'...")
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-c",
        "pytest_wsl.ini",
        "-k",
        pattern,
        "--maxfail=5",
    ]
    return subprocess.run(cmd).returncode


def run_all_tests_batched():
    """Run all tests in batches to avoid timeout issues."""
    print("📦 Running all tests in batches...")

    test_dirs = [
        "tests/unit/test_shot_model.py",
        "tests/unit/test_cache_manager.py",
        "tests/unit/test_utils.py",
        "tests/unit/test_launcher_*.py",
        "tests/unit/test_previous_shots_*.py",
        "tests/unit/test_main_window*.py",
        "tests/unit/test_threede_*.py",
        "tests/unit/test_thumbnail_*.py",
        "tests/integration",
    ]

    failed_batches = []
    for test_path in test_dirs:
        print(f"\n⏳ Testing {test_path}...")
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            "-c",
            "pytest_wsl.ini",
            test_path,
            "--tb=short",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            failed_batches.append(test_path)
            print(f"❌ Failed: {test_path}")
        else:
            print(f"✅ Passed: {test_path}")

    if failed_batches:
        print(f"\n❌ Failed batches: {', '.join(failed_batches)}")
        return 1
    else:
        print("\n✅ All batches passed!")
        return 0


def check_imports():
    """Quick check that all test files can be imported."""
    print("🔍 Checking all test imports...")

    test_files = list(Path("tests").rglob("test_*.py"))
    failed_imports = []

    for test_file in test_files:
        module_path = str(test_file).replace("/", ".").replace("\\", ".")[:-3]
        try:
            cmd = [sys.executable, "-c", f"import {module_path}"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                failed_imports.append(test_file)
                print(f"❌ Import failed: {test_file}")
        except subprocess.TimeoutExpired:
            failed_imports.append(test_file)
            print(f"⏱️ Import timeout: {test_file}")

    if failed_imports:
        print(f"\n❌ Failed imports: {len(failed_imports)}/{len(test_files)}")
        return 1
    else:
        print(f"\n✅ All {len(test_files)} test files import successfully!")
        return 0


def main():
    """Main entry point for WSL test runner."""
    parser = argparse.ArgumentParser(description="Optimized test runner for WSL")
    parser.add_argument("--fast", action="store_true", help="Run only fast tests")
    parser.add_argument(
        "--critical", action="store_true", help="Run only critical tests"
    )
    parser.add_argument("--file", help="Run tests from a single file")
    parser.add_argument("-k", "--pattern", help="Run tests matching pattern")
    parser.add_argument(
        "--check-imports", action="store_true", help="Check all imports"
    )
    parser.add_argument("--all", action="store_true", help="Run all tests in batches")

    args = parser.parse_args()

    # Record start time
    start_time = time.time()

    # Choose test strategy
    if args.check_imports:
        result = check_imports()
    elif args.fast:
        result = run_fast_tests()
    elif args.critical:
        result = run_critical_tests()
    elif args.file:
        result = run_single_file(args.file)
    elif args.pattern:
        result = run_focused_tests(args.pattern)
    elif args.all:
        result = run_all_tests_batched()
    else:
        # Default: run fast tests
        result = run_fast_tests()

    # Report elapsed time
    elapsed = time.time() - start_time
    print(f"\n⏱️ Total time: {elapsed:.1f} seconds")

    return result


if __name__ == "__main__":
    sys.exit(main())