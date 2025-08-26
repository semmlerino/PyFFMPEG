#!/usr/bin/env python3
"""Mark tests with speed categories based on their characteristics."""

import re
from pathlib import Path


def categorize_test_file(filepath: Path) -> list[str]:
    """Categorize a test file based on its content."""
    content = filepath.read_text()
    markers = []

    # Check for characteristics that indicate slow tests
    slow_indicators = [
        r"time\.sleep\(",
        r"qtbot\.wait\(",
        r"Thread",
        r"subprocess",
        r"QApplication",
        r"tmp_path.*10000",  # Large file operations
        r"for.*range.*1000",  # Large loops
        r"@pytest\.mark\.slow",
    ]

    # Check for fast test indicators
    fast_indicators = [
        r"def test_.*_basic\(",
        r"def test_.*_simple\(",
        r"def test_.*_initialization\(",
        r"assert.*==",  # Simple assertions
        r"return.*Mock",  # Mock-based tests
    ]

    # Check for critical tests
    critical_indicators = [
        r"test_shot_model",
        r"test_cache_manager",
        r"test_main_window_initialization",
        r"test_command_launcher",
    ]

    # Count indicators
    slow_count = sum(1 for pattern in slow_indicators if re.search(pattern, content))
    fast_count = sum(1 for pattern in fast_indicators if re.search(pattern, content))

    filename = filepath.name

    # Determine markers
    if any(re.search(pattern, content) for pattern in critical_indicators):
        markers.append("critical")

    if (
        slow_count > 2
        or "integration" in str(filepath)
        or "performance" in str(filepath)
    ):
        markers.append("slow")
    elif fast_count > slow_count or "unit" in str(filepath):
        if slow_count == 0:
            markers.append("fast")

    if "qt" in filename.lower() or "widget" in filename.lower() or "qtbot" in content:
        markers.append("qt")

    return markers


def add_markers_to_file(filepath: Path):
    """Add pytest markers to a test file."""
    content = filepath.read_text()
    lines = content.split("\n")

    # Check if pytestmark already exists
    if "pytestmark" in content:
        return False

    # Get markers for this file
    markers = categorize_test_file(filepath)
    if not markers:
        return False

    # Find where to insert pytestmark (after imports, before first class/function)
    insert_idx = -1
    for i, line in enumerate(lines):
        if line.strip().startswith("class ") or line.strip().startswith("def "):
            insert_idx = i
            break

    if insert_idx > 0:
        # Build pytestmark line
        marker_str = ", ".join(f"pytest.mark.{m}" for m in markers)
        pytestmark_line = f"pytestmark = [{marker_str}]"

        # Insert with proper spacing
        lines.insert(insert_idx, "")
        lines.insert(insert_idx, pytestmark_line)

        # Write back
        filepath.write_text("\n".join(lines))
        return True

    return False


def main():
    """Mark all test files with appropriate speed categories."""
    test_files = list(Path("tests").rglob("test_*.py"))

    categorized = {"fast": [], "slow": [], "critical": [], "qt": [], "unmarked": []}

    for test_file in test_files:
        markers = categorize_test_file(test_file)

        if not markers:
            categorized["unmarked"].append(test_file.name)
        else:
            for marker in markers:
                if marker in categorized:
                    categorized[marker].append(test_file.name)

    # Print report
    print("Test Speed Categorization Report")
    print("=" * 50)

    for category, files in categorized.items():
        print(f"\n{category.upper()} ({len(files)} files):")
        if category != "unmarked":
            for f in sorted(files)[:10]:  # Show first 10
                print(f"  - {f}")
            if len(files) > 10:
                print(f"  ... and {len(files) - 10} more")

    # Summary
    total = len(test_files)
    marked = total - len(categorized["unmarked"])
    print(f"\n📊 Summary: {marked}/{total} files categorized")

    # Recommendations
    print("\n📝 Run tests with:")
    print("  Fast tests:     python run_tests_wsl.py --fast")
    print("  Critical tests: python run_tests_wsl.py --critical")
    print("  Single file:    python run_tests_wsl.py --file tests/unit/test_utils.py")
    print("  Pattern match:  python run_tests_wsl.py -k test_shot")


if __name__ == "__main__":
    main()
