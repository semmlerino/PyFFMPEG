#!/usr/bin/env python3
"""Comprehensive fix for all remaining import issues."""

from pathlib import Path


def add_future_annotations(filepath: Path) -> bool:
    """Add from __future__ import annotations if needed."""
    try:
        content = filepath.read_text()
        lines = content.splitlines()

        # Check if already has future annotations
        if "from __future__ import annotations" in content:
            return False

        # Find where to insert (after shebang/encoding, before other imports)
        insert_index = 0
        for i, line in enumerate(lines):
            if line.startswith("#") or not line.strip():
                insert_index = i + 1
            else:
                break

        # Insert the import
        lines.insert(insert_index, "from __future__ import annotations")

        new_content = "\n".join(lines)
        filepath.write_text(new_content)
        return True
    except Exception as e:
        print(f"Error adding future annotations to {filepath}: {e}")
        return False


def fix_pytest_decorators(filepath: Path) -> bool:
    """Fix pytest decorator issues by ensuring pytest is imported."""
    try:
        content = filepath.read_text()

        # Check if pytest is used but not imported
        if "@pytest" in content and "import pytest" not in content:
            lines = content.splitlines()
            # Add pytest import after docstring
            for i, line in enumerate(lines):
                if line.startswith('"""') and i > 0:  # End of docstring
                    # Find next line after docstring
                    for j in range(i + 1, len(lines)):
                        if not lines[j].startswith('"""'):
                            lines.insert(j, "import pytest")
                            break
                    break

            new_content = "\n".join(lines)
            filepath.write_text(new_content)
            return True
        return False
    except Exception as e:
        print(f"Error fixing pytest in {filepath}: {e}")
        return False


def fix_specific_file_issues(filepath: Path) -> bool:
    """Fix specific known issues in files."""
    fixed = False

    try:
        content = filepath.read_text()
        original = content

        # Fix test_threede_optimization_coverage.py - duplicate sys import
        if filepath.name == "test_threede_optimization_coverage.py":
            lines = content.splitlines()
            new_lines = []
            sys_count = 0
            for line in lines:
                if "import sys" in line:
                    sys_count += 1
                    if sys_count == 1:
                        new_lines.append(line)
                    # Skip duplicate sys imports
                else:
                    new_lines.append(line)
            content = "\n".join(new_lines)

        # Fix test_launcher_dialog.py - LauncherEnvironment type
        if filepath.name == "test_launcher_dialog.py":
            # Add future annotations for forward references
            if "from __future__ import annotations" not in content:
                lines = content.splitlines()
                lines.insert(0, "from __future__ import annotations")
                content = "\n".join(lines)

        # Fix test_cache_manager.py - Optional not imported
        if filepath.name == "test_cache_manager.py":
            if (
                "Optional[QColor]" in content
                and "from typing import Optional" not in content
            ):
                # Add Optional to existing typing imports
                content = content.replace(
                    "from typing import", "from typing import Optional,"
                )

        # Fix test_doubles.py in unit folder - Any not imported
        if filepath.parent.name == "unit" and filepath.name == "test_doubles.py":
            if "Any" in content and "from typing import Any" not in content:
                # Add Any to imports
                lines = content.splitlines()
                for i, line in enumerate(lines):
                    if line.startswith("from typing import"):
                        if "Any" not in line:
                            lines[i] = line.replace(
                                "from typing import", "from typing import Any,"
                            )
                        break
                else:
                    # No typing import found, add one
                    for i, line in enumerate(lines):
                        if line.startswith("import"):
                            lines.insert(i, "from typing import Any")
                            break
                content = "\n".join(lines)

        # Fix test_launcher_manager_coverage.py - patch not imported
        if filepath.name == "test_launcher_manager_coverage.py":
            if "patch" in content and "from unittest.mock import" in content:
                if (
                    "patch"
                    not in content.split("from unittest.mock import")[1].split("\n")[0]
                ):
                    content = content.replace(
                        "from unittest.mock import Mock",
                        "from unittest.mock import Mock, patch",
                    )

        # Fix test_main_window.py - Path not imported in type annotations
        if filepath.name == "test_main_window.py":
            if ": Path" in content:
                # Add future annotations for forward references
                if "from __future__ import annotations" not in content:
                    lines = content.splitlines()
                    lines.insert(0, "from __future__ import annotations")
                    content = "\n".join(lines)

        if content != original:
            filepath.write_text(content)
            fixed = True

    except Exception as e:
        print(f"Error fixing {filepath}: {e}")

    return fixed


def main():
    """Fix all import issues."""
    test_dir = Path("tests")

    files_to_fix_annotations = [
        "tests/integration/test_user_workflows.py",
        "tests/performance/test_scene_finder_performance.py",
        "tests/unit/test_launcher_dialog.py",
        "tests/unit/test_main_window.py",
    ]

    files_to_fix_pytest = [
        "tests/unit/test_exr_edge_cases.py",
        "tests/unit/test_exr_parametrized.py",
        "tests/unit/test_failure_tracker.py",
        "tests/unit/test_log_viewer.py",
        "tests/unit/test_main_window_fixed.py",
        "tests/unit/test_memory_manager.py",
    ]

    # Add future annotations where needed
    for filepath_str in files_to_fix_annotations:
        filepath = Path(filepath_str)
        if filepath.exists():
            if add_future_annotations(filepath):
                print(f"Added future annotations to {filepath}")

    # Fix pytest decorator issues
    for filepath_str in files_to_fix_pytest:
        filepath = Path(filepath_str)
        if filepath.exists():
            if fix_pytest_decorators(filepath):
                print(f"Fixed pytest imports in {filepath}")

    # Fix specific file issues
    all_test_files = list(test_dir.rglob("test_*.py"))
    for filepath in all_test_files:
        if fix_specific_file_issues(filepath):
            print(f"Fixed specific issues in {filepath}")

    print("\nAll import fixes completed!")


if __name__ == "__main__":
    main()
