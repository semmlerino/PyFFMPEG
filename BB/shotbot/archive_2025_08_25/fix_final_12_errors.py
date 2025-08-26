#!/usr/bin/env python3
"""Fix the final 12 test collection errors."""

from pathlib import Path


def fix_specific_file(filepath: Path, missing_imports: list[str]) -> bool:
    """Fix specific import issues in a file."""
    try:
        content = filepath.read_text()
        lines = content.split("\n")

        # Find where to insert imports (after docstring, before other imports)
        import_insert_line = 0
        in_docstring = False
        quote_type = None

        for i, line in enumerate(lines):
            stripped = line.strip()
            if not in_docstring and (
                stripped.startswith('"""') or stripped.startswith("'''")
            ):
                quote_type = '"""' if '"""' in stripped else "'''"
                if stripped.count(quote_type) >= 2:
                    import_insert_line = i + 1
                    break
                else:
                    in_docstring = True
            elif in_docstring and quote_type in line:
                import_insert_line = i + 1
                break

        # If no docstring, insert at beginning
        if import_insert_line == 0:
            import_insert_line = 0

        # Skip any blank lines after docstring
        while import_insert_line < len(lines) and not lines[import_insert_line].strip():
            import_insert_line += 1

        # Insert missing imports
        for imp in missing_imports:
            if imp not in content:
                lines.insert(import_insert_line, imp)
                import_insert_line += 1

        new_content = "\n".join(lines)

        if new_content != content:
            filepath.write_text(new_content)
            return True
        return False
    except Exception as e:
        print(f"Error fixing {filepath}: {e}")
        return False


def main():
    """Fix the final 12 test files with errors."""
    test_dir = Path("/mnt/c/CustomScripts/Python/PyFFMPEG/BB/shotbot/tests/unit")

    fixes = {
        "test_launcher_dialog.py": [
            "from launcher_config import LauncherEnvironment, LauncherTerminal",
            "from unittest.mock import Mock",
        ],
        "test_launcher_manager.py": ["import pytest"],
        "test_main_window.py": [
            "from pathlib import Path",
            "from config import Config",
        ],
        "test_main_window_widgets.py": [
            "from PySide6.QtCore import Signal, Qt",
            "from PySide6.QtWidgets import QLabel, QPushButton",
            "from pathlib import Path",
        ],
        "test_previous_shots_finder.py": [
            "from pathlib import Path",
        ],
        "test_previous_shots_grid.py": [
            "from PySide6.QtCore import Signal",
            "from cache_manager import CacheManager",
            "from previous_shots_model import PreviousShotsModel",
            "from test_doubles_previous_shots import FakeShotModel",
        ],
        "test_undistortion_finder.py": [
            "from pathlib import Path",
            "from undistortion_finder import UndistortionFinder",
        ],
        "test_utils.py": [
            "from utils import (",
            "    PathUtils,",
            "    FileUtils,",
            "    ValidationUtils,",
            "    VersionUtils,",
            "    ImageUtils,",
            "    cleanup_expired_cache,",
            "    get_cache_stats,",
            ")",
        ],
    }

    fixed_count = 0
    for filename, imports in fixes.items():
        filepath = test_dir / filename
        if filepath.exists():
            if fix_specific_file(filepath, imports):
                print(f"Fixed: {filename}")
                fixed_count += 1
        else:
            print(f"Not found: {filename}")

    print(f"\nTotal files fixed: {fixed_count}")


if __name__ == "__main__":
    main()
