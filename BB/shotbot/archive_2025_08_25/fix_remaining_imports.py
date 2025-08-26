#!/usr/bin/env python3
"""Fix remaining import errors in test files."""

from pathlib import Path


def fix_file(filepath: Path, fixes: list) -> bool:
    """Apply fixes to a file."""
    try:
        content = filepath.read_text()
        original = content

        for old, new in fixes:
            content = content.replace(old, new)

        if content != original:
            filepath.write_text(content)
            return True
        return False
    except Exception as e:
        print(f"Error fixing {filepath}: {e}")
        return False


def main():
    """Fix all remaining import issues."""

    # Fix test_user_workflows.py - missing MagicMock
    test_file = Path("tests/integration/test_user_workflows.py")
    if test_file.exists():
        content = test_file.read_text()
        if "from unittest.mock import" in content and "MagicMock" not in content:
            content = content.replace(
                "from unittest.mock import patch",
                "from unittest.mock import MagicMock, patch",
            )
            test_file.write_text(content)
            print(f"Fixed: {test_file}")

    # Fix test_scene_finder_performance.py - Path in class method
    test_file = Path("tests/performance/test_scene_finder_performance.py")
    if test_file.exists():
        content = test_file.read_text()
        lines = content.splitlines()
        # Find the line with the issue and fix the import
        if "from typing import Dict, Tuple" in content:
            content = content.replace(
                "from typing import Dict, Tuple", "from typing import Dict, Tuple"
            )
        # Ensure Path is imported
        if "from pathlib import Path" not in content:
            # Add after imports section
            for i, line in enumerate(lines):
                if line.startswith("from threede_scene_finder import"):
                    lines.insert(i, "from pathlib import Path")
                    break
            content = "\n".join(lines)
        test_file.write_text(content)
        print(f"Fixed: {test_file}")

    # Fix test_threede_optimization_coverage.py - sys not imported before use
    test_file = Path("tests/performance/test_threede_optimization_coverage.py")
    if test_file.exists():
        content = test_file.read_text()
        # Move sys import before sys.path.insert
        lines = content.splitlines()
        new_lines = []
        sys_import_found = False

        for line in lines:
            if "import sys" in line and not sys_import_found:
                sys_import_found = True
                # Skip this line, we'll add it earlier
                continue
            elif line.startswith("from threede_scene_finder_optimized"):
                # Add sys import before this
                if not sys_import_found:
                    new_lines.append("import sys")
                    sys_import_found = True
                new_lines.append(line)
            else:
                new_lines.append(line)

        content = "\n".join(new_lines)
        test_file.write_text(content)
        print(f"Fixed: {test_file}")

    # Fix test_doubles.py - missing Optional
    test_file = Path("tests/test_doubles.py")
    if test_file.exists():
        content = test_file.read_text()
        # Add Optional to imports
        if "from typing import" not in content:
            # Add typing import after docstring
            lines = content.splitlines()
            for i, line in enumerate(lines):
                if line.startswith("from PySide6"):
                    lines.insert(i, "from typing import Optional")
                    break
            content = "\n".join(lines)
        elif "Optional" not in content.split("from typing import")[1].split("\n")[0]:
            content = content.replace(
                "from typing import", "from typing import Optional,"
            )
        test_file.write_text(content)
        print(f"Fixed: {test_file}")

    # Fix test_doubles_previous_shots.py - missing QObject
    test_file = Path("tests/test_doubles_previous_shots.py")
    if test_file.exists():
        content = test_file.read_text()
        # Add QObject to PySide6.QtCore imports
        if "from PySide6.QtCore import" in content:
            # Check if QObject is already imported
            if "QObject" not in content:
                content = content.replace(
                    "from PySide6.QtCore import Signal",
                    "from PySide6.QtCore import QObject, Signal",
                )
        test_file.write_text(content)
        print(f"Fixed: {test_file}")

    # Fix test_threading_fixes.py - missing logging
    test_file = Path("tests/threading/test_threading_fixes.py")
    if test_file.exists():
        content = test_file.read_text()
        # Add logging import
        if "import logging" not in content:
            lines = content.splitlines()
            # Add after other imports
            for i, line in enumerate(lines):
                if line.startswith("import concurrent.futures"):
                    lines.insert(i + 1, "import logging")
                    break
            content = "\n".join(lines)
        test_file.write_text(content)
        print(f"Fixed: {test_file}")

    print("\nAll import fixes applied!")


if __name__ == "__main__":
    main()
