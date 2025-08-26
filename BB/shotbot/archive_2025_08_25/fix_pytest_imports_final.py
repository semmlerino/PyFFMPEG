#!/usr/bin/env python3
"""Fix pytest import ordering issues in all test files."""

import re
from pathlib import Path


def fix_pytest_imports(filepath: Path) -> bool:
    """Fix pytest import ordering in a single file."""
    try:
        content = filepath.read_text()
        lines = content.splitlines()

        # Find pytestmark lines before pytest import
        pytestmark_pattern = re.compile(r"^pytestmark\s*=")
        pytest_import_pattern = re.compile(r"^(from pytest|import pytest)")

        # Extract all import lines and pytestmark lines
        import_lines = []
        pytestmark_lines = []
        other_lines = []
        found_pytest_import = False

        for line in lines:
            if pytest_import_pattern.match(line):
                found_pytest_import = True
                import_lines.append(line)
            elif pytestmark_pattern.match(line):
                pytestmark_lines.append(line)
            elif line.startswith(("import ", "from ")) and not line.startswith(
                "from __future__"
            ):
                import_lines.append(line)
            else:
                other_lines.append(line)

        # If pytestmark exists but no pytest import, add it
        if pytestmark_lines and not found_pytest_import:
            import_lines.insert(0, "import pytest")

        # Rebuild file with correct order
        new_lines = []

        # Add header comments/docstrings
        for line in other_lines[:]:
            if line.startswith('"""') or line.startswith("#") or not line.strip():
                new_lines.append(line)
                other_lines.remove(line)
            else:
                break

        # Add imports (including pytest)
        if import_lines:
            # Ensure pytest import comes first
            pytest_imports = [line for line in import_lines if "pytest" in line]
            other_imports = [line for line in import_lines if "pytest" not in line]

            for imp in pytest_imports:
                new_lines.append(imp)
            for imp in sorted(set(other_imports)):
                new_lines.append(imp)
            new_lines.append("")

        # Add pytestmark after imports
        if pytestmark_lines:
            for mark in pytestmark_lines:
                new_lines.append(mark)
            new_lines.append("")

        # Add remaining content
        new_lines.extend(other_lines)

        # Write back
        new_content = "\n".join(new_lines)
        if new_content != content:
            filepath.write_text(new_content)
            return True
        return False

    except Exception as e:
        print(f"Error processing {filepath}: {e}")
        return False


def main():
    """Fix all test files."""
    test_dir = Path("/mnt/c/CustomScripts/Python/PyFFMPEG/BB/shotbot/tests")

    fixed_files = []
    for test_file in test_dir.rglob("test_*.py"):
        if fix_pytest_imports(test_file):
            fixed_files.append(test_file)
            print(f"Fixed: {test_file.relative_to(test_dir.parent)}")

    print(f"\nFixed {len(fixed_files)} files")

    # Also check for syntax errors
    print("\nChecking for syntax errors...")
    import ast
    import traceback

    for test_file in test_dir.rglob("test_*.py"):
        try:
            ast.parse(test_file.read_text())
        except SyntaxError as e:
            print(f"Syntax error in {test_file.relative_to(test_dir.parent)}: {e}")
            traceback.print_exc()


if __name__ == "__main__":
    main()
