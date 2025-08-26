#!/usr/bin/env python3
"""Fix all remaining test collection issues."""

from pathlib import Path


def fix_test_file(filepath: Path) -> bool:
    """Fix import and docstring issues in a test file."""
    try:
        content = filepath.read_text()
        original_content = content
        lines = content.split("\n")

        # Track if we have a module docstring
        has_docstring = False
        docstring_start = -1
        docstring_end = -1
        in_docstring = False
        quote_type = None

        # Find docstring boundaries
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not has_docstring and (
                stripped.startswith('"""') or stripped.startswith("'''")
            ):
                has_docstring = True
                docstring_start = i
                quote_type = '"""' if '"""' in stripped else "'''"
                # Check if it's a single-line docstring
                if stripped.count(quote_type) >= 2:
                    docstring_end = i
                else:
                    in_docstring = True
            elif in_docstring and quote_type in line:
                docstring_end = i
                in_docstring = False
                break

        # Collect all imports and pytestmark lines
        import_lines = []
        pytestmark_lines = []
        other_lines = []

        # Process lines after docstring
        start_idx = docstring_end + 1 if has_docstring else 0

        for i in range(start_idx, len(lines)):
            line = lines[i]
            stripped = line.strip()

            # Skip empty lines at the beginning
            if (
                not stripped
                and not import_lines
                and not pytestmark_lines
                and not other_lines
            ):
                continue

            # Categorize lines
            if stripped.startswith("import ") or stripped.startswith("from "):
                import_lines.append(line)
            elif "pytestmark" in line and "=" in line:
                pytestmark_lines.append(line)
            else:
                other_lines.append(line)

        # Check if we need to add missing imports based on the file
        missing_imports = []

        # Check for missing imports in the entire file content
        if "pytest." in content or "pytestmark" in content:
            if "import pytest" not in content:
                missing_imports.append("import pytest")

        if "Optional[" in content or "Optional," in content:
            if "from typing import" in content:
                # Check if Optional is already imported
                if "Optional" not in content:
                    # Find the typing import line and add Optional to it
                    for i, line in enumerate(import_lines):
                        if "from typing import" in line:
                            import_lines[i] = line  # Will handle below
            else:
                missing_imports.append("from typing import Optional")

        if "Any[" in content or "Any," in content or " Any" in content:
            if "from typing import" not in content or "Any" not in "".join(
                import_lines
            ):
                missing_imports.append("from typing import Any")

        if "patch(" in content or "@patch" in content:
            if "from unittest.mock import" not in content or "patch" not in "".join(
                import_lines
            ):
                missing_imports.append("from unittest.mock import patch")

        if "QObject" in content and "from PySide6" not in content:
            if "QObject" not in "".join(import_lines):
                missing_imports.append("from PySide6.QtCore import QObject")

        if "sys." in content and "import sys" not in content:
            missing_imports.append("import sys")

        if "unittest." in content and "import unittest" not in content:
            missing_imports.append("import unittest")

        # Add future annotations if needed
        if "from __future__ import annotations" not in content:
            missing_imports.insert(0, "from __future__ import annotations")

        # Reconstruct the file
        new_lines = []

        # Add shebang and encoding if present
        for line in lines[:start_idx]:
            if line.startswith("#!") or line.startswith("# -*- coding"):
                new_lines.append(line)
                break

        # Add docstring if present
        if has_docstring:
            for i in range(docstring_start, docstring_end + 1):
                new_lines.append(lines[i])
            new_lines.append("")

        # Add imports in order
        if missing_imports:
            for imp in missing_imports:
                if imp not in import_lines:
                    import_lines.insert(0, imp)

        # Sort imports properly
        future_imports = [line for line in import_lines if "from __future__" in line]
        std_imports = [
            line
            for line in import_lines
            if line.strip().startswith("import ") and "from" not in line
        ]
        from_imports = [
            line
            for line in import_lines
            if line.strip().startswith("from ") and "__future__" not in line
        ]

        # Add sorted imports
        if future_imports:
            new_lines.extend(future_imports)
            new_lines.append("")

        if std_imports:
            new_lines.extend(sorted(set(std_imports)))

        if from_imports:
            if std_imports:
                new_lines.append("")
            new_lines.extend(sorted(set(from_imports)))

        # Add pytestmark after imports
        if pytestmark_lines:
            new_lines.append("")
            new_lines.extend(pytestmark_lines)

        # Add the rest of the content
        if other_lines:
            new_lines.append("")
            new_lines.extend(other_lines)

        # Join and clean up
        new_content = "\n".join(new_lines)

        # Remove multiple blank lines
        while "\n\n\n" in new_content:
            new_content = new_content.replace("\n\n\n", "\n\n")

        # Write back if changed
        if new_content != original_content:
            filepath.write_text(new_content)
            return True
        return False

    except Exception as e:
        print(f"Error processing {filepath}: {e}")
        return False


def main():
    """Fix all test files with issues."""
    test_dir = Path("/mnt/c/CustomScripts/Python/PyFFMPEG/BB/shotbot/tests")

    # Files with known issues from the error output
    problem_files = [
        "unit/test_cache_manager.py",
        "unit/test_doubles.py",
        "unit/test_exr_edge_cases.py",
        "unit/test_exr_parametrized.py",
        "unit/test_failure_tracker.py",
        "unit/test_launcher_dialog.py",
        "unit/test_launcher_manager.py",
        "unit/test_launcher_manager_coverage.py",
        "unit/test_log_viewer.py",
        "unit/test_main_window.py",
        "unit/test_main_window_fixed.py",
        "unit/test_main_window_widgets.py",
        "unit/test_memory_manager.py",
        "unit/test_previous_shots_cache_integration.py",
        "unit/test_previous_shots_finder.py",
        "unit/test_previous_shots_grid.py",
        "unit/test_previous_shots_model.py",
        "unit/test_previous_shots_worker.py",
        "unit/test_previous_shots_worker_fixed.py",
        "unit/test_process_pool_manager_simple.py",
        "unit/test_scanner_coverage.py",
        "unit/test_shot_grid.py",
        "unit/test_shot_grid_view.py",
        "unit/test_shot_info_panel.py",
        "unit/test_shot_model.py",
        "unit/test_shotbot.py",
        "unit/test_shotbot_ui.py",
        "unit/test_storage_backend.py",
        "unit/test_thread_safe_worker.py",
        "unit/test_thumbnail_loader.py",
        "unit/test_thumbnail_processor.py",
        "unit/test_thumbnail_widget.py",
        "unit/test_threede_cache.py",
        "unit/test_validation_edge_cases.py",
        "performance/test_parallel_command_execution.py",
    ]

    fixed_count = 0
    for file_path in problem_files:
        full_path = test_dir / file_path
        if full_path.exists():
            if fix_test_file(full_path):
                print(f"Fixed: {file_path}")
                fixed_count += 1
        else:
            print(f"Not found: {file_path}")

    # Also scan all test files for issues
    for test_file in test_dir.rglob("test_*.py"):
        if test_file.is_file():
            rel_path = test_file.relative_to(test_dir)
            if str(rel_path) not in problem_files:
                if fix_test_file(test_file):
                    print(f"Fixed additional: {rel_path}")
                    fixed_count += 1

    print(f"\nTotal files fixed: {fixed_count}")


if __name__ == "__main__":
    main()
