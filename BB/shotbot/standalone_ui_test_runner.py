#!/usr/bin/env python3
"""
Standalone UI Test Runner
Identifies failing UI component tests using pytest.
"""

import os
import subprocess
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))


def setup_environment():
    """Setup environment for testing."""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["SHOTBOT_DEBUG"] = "1"


def run_single_test_file(test_file_path):
    """Run a single test file using pytest and capture results."""
    print(f"\n{'=' * 60}")
    print(f"Testing: {test_file_path.name}")
    print(f"{'=' * 60}")

    try:
        # Setup environment
        setup_environment()

        # Run pytest with the specific file
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            str(test_file_path),
            "-v",
            "--tb=short",
            "--no-header",
            "--disable-warnings",
        ]

        result = subprocess.run(
            cmd, cwd=Path(__file__).parent, capture_output=True, text=True, timeout=120,
        )

        print("STDOUT:")
        print(result.stdout)
        if result.stderr:
            print("STDERR:")
            print(result.stderr)

        success = result.returncode == 0

        # Parse output to get summary
        output_lines = result.stdout.split("\n")
        summary_line = None
        for line in reversed(output_lines):
            if "failed" in line or "passed" in line or "error" in line:
                summary_line = line.strip()
                break

        summary = summary_line if summary_line else f"Exit code: {result.returncode}"

        print(f"\n{'✅' if success else '❌'} {test_file_path.name}: {summary}")
        return success, summary

    except subprocess.TimeoutExpired:
        error_msg = "Test timed out after 120 seconds"
        print(f"❌ {test_file_path.name}: {error_msg}")
        return False, error_msg
    except Exception as e:
        error_msg = f"Failed to run pytest: {str(e)}"
        print(f"❌ {test_file_path.name}: {error_msg}")
        return False, error_msg


def main():
    """Run all UI component tests."""
    print("ShotBot UI Component Test Runner")
    print("=" * 60)

    # Target UI test files
    ui_test_files = [
        "test_main_window.py",
        "test_shot_grid.py",
        "test_shot_info_panel.py",
        "test_threede_shot_grid.py",
        "test_thumbnail_widget.py",
        "test_log_viewer.py",
    ]

    test_dir = Path(__file__).parent / "tests" / "unit"
    results = {}

    for test_file_name in ui_test_files:
        test_file_path = test_dir / test_file_name

        if not test_file_path.exists():
            print(f"❌ {test_file_name}: File not found")
            results[test_file_name] = (False, "File not found")
            continue

        success, summary = run_single_test_file(test_file_path)
        results[test_file_name] = (success, summary)

    # Summary report
    print(f"\n{'=' * 60}")
    print("SUMMARY REPORT")
    print(f"{'=' * 60}")

    passed = 0
    failed = 0

    for test_file, (success, summary) in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status:8} {test_file:25} {summary}")
        if success:
            passed += 1
        else:
            failed += 1

    print(f"\nTotal: {len(results)} | Passed: {passed} | Failed: {failed}")

    if failed > 0:
        print(f"\n⚠️  {failed} test files need attention")
        sys.exit(1)
    else:
        print("\n🎉 All UI tests passing!")
        sys.exit(0)


if __name__ == "__main__":
    main()
