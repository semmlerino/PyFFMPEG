#!/usr/bin/env python3
"""Apply LoggingMixin to multiple files in batch."""

import re
from pathlib import Path

FILES_TO_CONVERT = [
    "shot_item_model.py",
    "shot_grid_view.py",
    "settings_manager.py",
    "raw_plate_finder.py",
    "previous_shots_worker.py",
    "previous_shots_finder.py",
    "shot_model_optimized.py",
]


def apply_logging_mixin(filepath: str) -> bool:
    """Apply LoggingMixin to a single file."""
    path = Path(filepath)
    if not path.exists():
        print(f"❌ File not found: {filepath}")
        return False

    content = path.read_text()

    # Check if already has LoggingMixin
    if "from logging_mixin import LoggingMixin" in content:
        print(f"⏭️  Already has LoggingMixin: {filepath}")
        return False

    # Check if has logger = logging.getLogger
    if "logger = logging.getLogger" not in content:
        print(f"⏭️  No old logger pattern: {filepath}")
        return False

    # Find the main class name
    class_match = re.search(r'^class\s+(\w+)\s*\((.*?)\):', content, re.MULTILINE)
    if not class_match:
        print(f"⚠️  No class found: {filepath}")
        return False

    class_name = class_match.group(1)
    parent_classes = class_match.group(2)

    # Add LoggingMixin import after other imports
    import_pattern = r'(from PySide6.*?\n|import.*?\n)+\n'
    import_match = re.search(import_pattern, content)
    if import_match:
        # Find good place to add import
        if "from config import" in content:
            content = content.replace(
                "from config import",
                "from logging_mixin import LoggingMixin\nfrom config import"
            )
        else:
            # Add after last import
            last_import = list(re.finditer(r'^(from|import)\s+.*$', content, re.MULTILINE))[-1]
            insert_pos = last_import.end()
            content = content[:insert_pos] + "\n\nfrom logging_mixin import LoggingMixin" + content[insert_pos:]

    # Remove module-level logger
    content = re.sub(r'^logger = logging\.getLogger\(__name__\)\s*$', '', content, flags=re.MULTILINE)

    # Update class inheritance
    if parent_classes:
        # Add LoggingMixin as first parent
        new_parents = f"LoggingMixin, {parent_classes}"
    else:
        new_parents = "LoggingMixin"

    old_class_def = f"class {class_name}({parent_classes}):"
    new_class_def = f"class {class_name}({new_parents}):"
    content = content.replace(old_class_def, new_class_def)

    # Replace logger. with self.logger.
    content = re.sub(r'(?<!\w)logger\.', 'self.logger.', content)

    # Clean up extra blank lines
    content = re.sub(r'\n\n\n+', '\n\n', content)

    # Write back
    path.write_text(content)
    print(f"✅ Converted: {filepath} (class {class_name})")
    return True


def main():
    """Apply LoggingMixin to all target files."""
    print("Applying LoggingMixin to batch of files...\n")

    converted = 0
    for filepath in FILES_TO_CONVERT:
        if apply_logging_mixin(filepath):
            converted += 1

    print(f"\n🎉 Successfully converted {converted} files")


if __name__ == "__main__":
    main()