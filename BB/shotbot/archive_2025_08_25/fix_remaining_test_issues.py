#!/usr/bin/env python3
"""Fix remaining test collection issues."""

from pathlib import Path


def fix_test_file_comprehensive(filepath: Path) -> bool:
    """Comprehensively fix all import and docstring issues in a test file."""
    try:
        content = filepath.read_text()
        lines = content.split("\n")

        # Find module docstring
        docstring_start = -1
        docstring_end = -1
        quote_type = None
        in_docstring = False

        for i, line in enumerate(lines):
            stripped = line.strip()
            if not in_docstring:
                if i < 20 and (
                    stripped.startswith('"""') or stripped.startswith("'''")
                ):
                    docstring_start = i
                    quote_type = '"""' if '"""' in stripped else "'''"
                    # Check if single-line docstring
                    if stripped.count(quote_type) >= 2:
                        docstring_end = i
                    else:
                        in_docstring = True
            elif in_docstring and quote_type in line:
                docstring_end = i
                break

        # Extract imports and other lines after docstring
        imports = []
        pytestmark_lines = []
        other_lines = []

        start_idx = docstring_end + 1 if docstring_end >= 0 else 0

        for i in range(start_idx, len(lines)):
            line = lines[i]
            stripped = line.strip()

            # Skip empty lines at beginning
            if (
                not stripped
                and not imports
                and not pytestmark_lines
                and not other_lines
            ):
                continue

            # Check for imports
            if stripped.startswith("import ") or stripped.startswith("from "):
                # Skip indented imports (they're likely inside something else)
                if not line.startswith(" ") or stripped == line:
                    imports.append(stripped)  # Store only the stripped version
            elif "pytestmark" in line and "=" in line:
                pytestmark_lines.append(line)
            else:
                # Everything else
                other_lines.append(line)

        # Clean up duplicate imports
        seen_imports = set()
        unique_imports = []
        for imp in imports:
            if imp not in seen_imports:
                seen_imports.add(imp)
                unique_imports.append(imp)

        # Sort imports properly
        future_imports = [i for i in unique_imports if "from __future__" in i]
        std_imports = [
            i for i in unique_imports if i.startswith("import ") and "from" not in i
        ]
        from_imports = [
            i for i in unique_imports if i.startswith("from ") and "__future__" not in i
        ]

        # Ensure essential imports are present
        all_imports_text = " ".join(unique_imports)

        if "pytest." in content or "pytestmark" in content:
            if "import pytest" not in all_imports_text:
                std_imports.append("import pytest")

        if "sys." in content and "import sys" not in all_imports_text:
            std_imports.append("import sys")

        if "unittest." in content and "import unittest" not in all_imports_text:
            std_imports.append("import unittest")

        if "Optional[" in content or "Optional," in content:
            found_optional = False
            for imp in from_imports:
                if "from typing import" in imp and "Optional" in imp:
                    found_optional = True
                    break
            if not found_optional:
                # Check if there's already a typing import
                typing_import_idx = -1
                for i, imp in enumerate(from_imports):
                    if "from typing import" in imp:
                        typing_import_idx = i
                        break

                if typing_import_idx >= 0:
                    # Add Optional to existing typing import
                    from_imports[typing_import_idx] += ", Optional"
                else:
                    from_imports.append("from typing import Optional")

        # Similar checks for other common imports
        if "Any[" in content or "Any," in content or " Any" in content:
            found_any = False
            for imp in from_imports:
                if "from typing import" in imp and "Any" in imp:
                    found_any = True
                    break
            if not found_any:
                typing_import_idx = -1
                for i, imp in enumerate(from_imports):
                    if "from typing import" in imp:
                        typing_import_idx = i
                        break

                if typing_import_idx >= 0:
                    # Add Any to existing typing import if not already there
                    if "Any" not in from_imports[typing_import_idx]:
                        from_imports[typing_import_idx] += ", Any"
                else:
                    from_imports.append("from typing import Any")

        if "patch(" in content or "@patch" in content:
            if (
                "from unittest.mock import" not in all_imports_text
                or "patch" not in all_imports_text
            ):
                from_imports.append("from unittest.mock import patch")

        if "QObject" in content:
            if (
                "from PySide6.QtCore import" not in all_imports_text
                or "QObject" not in all_imports_text
            ):
                # Check if we have a QtCore import already
                found = False
                for imp in from_imports:
                    if "from PySide6.QtCore import" in imp:
                        if "QObject" not in imp:
                            from_imports[from_imports.index(imp)] += ", QObject"
                        found = True
                        break
                if not found:
                    from_imports.append("from PySide6.QtCore import QObject")

        # Build the new file content
        new_lines = []

        # Add docstring if exists
        if docstring_start >= 0 and docstring_end >= 0:
            for i in range(docstring_start, docstring_end + 1):
                new_lines.append(lines[i])
            new_lines.append("")

        # Add future imports first
        if future_imports:
            for imp in sorted(set(future_imports)):
                new_lines.append(imp)
            new_lines.append("")

        # Add standard imports
        if std_imports:
            for imp in sorted(set(std_imports)):
                new_lines.append(imp)
            if from_imports:
                new_lines.append("")

        # Add from imports
        if from_imports:
            for imp in sorted(set(from_imports)):
                new_lines.append(imp)

        # Add pytestmark after imports
        if pytestmark_lines:
            new_lines.append("")
            for line in pytestmark_lines:
                new_lines.append(line)

        # Add the rest of the content
        if other_lines:
            new_lines.append("")
            new_lines.extend(other_lines)

        # Join and clean up
        new_content = "\n".join(new_lines)

        # Remove excessive blank lines
        while "\n\n\n" in new_content:
            new_content = new_content.replace("\n\n\n", "\n\n")

        # Write back if changed
        if new_content != content:
            filepath.write_text(new_content)
            return True
        return False

    except Exception as e:
        print(f"Error processing {filepath}: {e}")
        return False


def main():
    """Fix all test files with remaining issues."""
    test_dir = Path("/mnt/c/CustomScripts/Python/PyFFMPEG/BB/shotbot/tests")

    # Get all test files
    test_files = list(test_dir.rglob("test_*.py"))

    fixed_count = 0
    for test_file in test_files:
        if fix_test_file_comprehensive(test_file):
            print(f"Fixed: {test_file.relative_to(test_dir)}")
            fixed_count += 1

    print(f"\nTotal files fixed: {fixed_count}")


if __name__ == "__main__":
    main()
