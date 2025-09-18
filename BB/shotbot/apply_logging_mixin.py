#!/usr/bin/env python3
"""Apply LoggingMixin pattern to files using the old logging pattern.

This script automates the conversion of files from the old logging pattern
to use the LoggingMixin class for standardized logging.
"""

import ast
import re
import sys
from pathlib import Path


def apply_logging_mixin(file_path: Path) -> bool:
    """Apply LoggingMixin pattern to a single file.

    Returns:
        True if changes were made, False otherwise
    """
    with open(file_path) as f:
        content = f.read()
        original_content = content

    # Skip if already using LoggingMixin
    if "LoggingMixin" in content:
        print(f"  ✓ {file_path.name} already uses LoggingMixin")
        return False

    # Check if file has logger = logging.getLogger(__name__)
    if "logger = logging.getLogger(__name__)" not in content:
        print(f"  ✓ {file_path.name} doesn't use old pattern")
        return False

    # Parse the file to find class definitions
    try:
        tree = ast.parse(content)
    except SyntaxError:
        print(f"  ✗ {file_path.name} has syntax errors, skipping")
        return False

    # Find all class definitions
    classes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            classes.append(
                {
                    "name": node.name,
                    "line": node.lineno,
                    "has_qobject": any(
                        (isinstance(base, ast.Name) and base.id == "QObject")
                        or (isinstance(base, ast.Attribute) and base.attr == "QObject")
                        for base in node.bases
                    ),
                }
            )

    if not classes:
        print(f"  ⚠ {file_path.name} has no classes to update")
        return False

    # Step 1: Add LoggingMixin import in the right place
    lines = content.split("\n")

    # Find the best place for the import
    last_regular_import = -1
    in_type_checking_block = False

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Track TYPE_CHECKING blocks
        if "if TYPE_CHECKING:" in line:
            in_type_checking_block = True
            continue
        if in_type_checking_block and line and not line[0].isspace():
            in_type_checking_block = False

        # Track imports that are not in TYPE_CHECKING
        if not in_type_checking_block:
            if stripped.startswith("import ") or stripped.startswith("from "):
                last_regular_import = i

    # Add the import after the last regular import
    if last_regular_import >= 0:
        # Check if there's already a from logging_mixin import
        if not any("from logging_mixin import" in line for line in lines):
            # Find a good place - after the last import but before any blank lines
            insert_pos = last_regular_import + 1

            # Skip any trailing blank lines after imports
            while insert_pos < len(lines) and not lines[insert_pos].strip():
                insert_pos += 1

            # Insert the import
            lines.insert(insert_pos, "from logging_mixin import LoggingMixin")

    content = "\n".join(lines)

    # Step 2: Remove logger = logging.getLogger(__name__)
    content = re.sub(
        r"^logger = logging\.getLogger\(__name__\)\n?", "", content, flags=re.MULTILINE
    )

    # Step 3: Update class definitions to inherit from LoggingMixin
    for cls in classes:
        if cls["has_qobject"]:
            # Add LoggingMixin before QObject
            content = re.sub(
                rf"^(class {cls['name']}\()([^)]*QObject)",
                r"\1LoggingMixin, \2",
                content,
                flags=re.MULTILINE,
            )
        else:
            # Check if class has any base classes
            match = re.search(
                rf"^class {cls['name']}\(([^)]*)\):", content, flags=re.MULTILINE
            )
            if match and match.group(1).strip():
                # Has base classes, add LoggingMixin first
                content = re.sub(
                    rf"^(class {cls['name']}\()([^)]+)",
                    r"\1LoggingMixin, \2",
                    content,
                    flags=re.MULTILINE,
                )
            else:
                # No base classes, add LoggingMixin
                content = re.sub(
                    rf"^class {cls['name']}(\(\))?:",
                    rf"class {cls['name']}(LoggingMixin):",
                    content,
                    flags=re.MULTILINE,
                )

    # Step 4: Replace logger. with self.logger. in methods
    # This is tricky - we need to identify method boundaries
    # For now, do a simple replacement that might need manual review

    # Find all method definitions
    tree = ast.parse(content)
    method_ranges = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    # Get the method's line range
                    start_line = item.lineno - 1  # ast uses 1-based indexing
                    # Find the end of the method (approximate)
                    end_line = start_line
                    for child in ast.walk(item):
                        if hasattr(child, "lineno"):
                            end_line = max(end_line, getattr(child, "lineno") - 1)
                    method_ranges.append((start_line, end_line))

    # Apply replacements within method ranges
    lines = content.split("\n")
    for start, end in method_ranges:
        for i in range(start, min(end + 1, len(lines))):
            # Only replace if it's not in a string or comment
            if "logger." in lines[i] and not lines[i].strip().startswith("#"):
                # Simple heuristic: replace logger. at start of expressions
                lines[i] = re.sub(r"\blogger\.", "self.logger.", lines[i])

    content = "\n".join(lines)

    # Only write if changes were made
    if content != original_content:
        with open(file_path, "w") as f:
            f.write(content)
        print(f"  ✓ Updated {file_path.name}")
        return True
    else:
        print(f"  ✓ No changes needed for {file_path.name}")
        return False


def main():
    """Apply LoggingMixin to all eligible Python files."""

    # Get list of files with old pattern
    files_to_update = []
    for file_path in Path(".").glob("*.py"):
        if file_path.name == "apply_logging_mixin.py":
            continue

        with open(file_path) as f:
            content = f.read()
            if (
                "logger = logging.getLogger(__name__)" in content
                and "LoggingMixin" not in content
            ):
                files_to_update.append(file_path)

    print(f"Found {len(files_to_update)} files to update")

    if not files_to_update:
        print("No files need updating!")
        return 0

    print("\nFiles to update:")
    for f in sorted(files_to_update):
        print(f"  - {f.name}")

    print("\nApplying LoggingMixin pattern...")

    updated_count = 0
    for file_path in sorted(files_to_update):
        if apply_logging_mixin(file_path):
            updated_count += 1

    print(f"\n✓ Updated {updated_count} files")

    # Show files that may need manual review
    print("\nNext steps:")
    print("1. Review the changes with: git diff")
    print("2. Run tests: python3 tests/utilities/quick_test.py")
    print("3. Check type errors: basedpyright")

    return 0


if __name__ == "__main__":
    sys.exit(main())
