#!/usr/bin/env python3
"""Fix all remaining import issues comprehensively."""

import re
from pathlib import Path


def add_missing_imports(filepath: Path) -> bool:
    """Add all missing imports based on usage in the file."""
    try:
        content = filepath.read_text()
        lines = content.split("\n")

        # Track what needs to be imported
        needs_imports = set()

        # Check for usage patterns
        if (
            re.search(r"\bPath\b", content)
            and "from pathlib import Path" not in content
        ):
            needs_imports.add("from pathlib import Path")

        if re.search(r"\bos\.", content) and "import os" not in content:
            needs_imports.add("import os")

        if re.search(r"\bsys\.", content) and "import sys" not in content:
            needs_imports.add("import sys")

        if re.search(r"\bSignal\b", content) and "Signal" not in content:
            needs_imports.add("from PySide6.QtCore import Signal")

        if (
            "LauncherEnvironment" in content
            and "from launcher_config import" not in content
        ):
            needs_imports.add(
                "from launcher_config import LauncherEnvironment, LauncherTerminal"
            )

        if (
            "LauncherManager" in content
            and "from launcher_manager import" not in content
        ):
            needs_imports.add("from launcher_manager import LauncherManager")

        if "CustomLauncher" in content and "from launcher_config import" not in content:
            needs_imports.add("from launcher_config import CustomLauncher")

        if "CacheManager" in content and "from cache_manager import" not in content:
            needs_imports.add("from cache_manager import CacheManager")

        if "Mock" in content and "from unittest.mock import" not in content:
            if "from unittest.mock import patch" in content:
                # Add Mock to existing import
                for i, line in enumerate(lines):
                    if "from unittest.mock import patch" in line:
                        lines[i] = "from unittest.mock import Mock, patch"
                        break
            else:
                needs_imports.add("from unittest.mock import Mock")

        if not needs_imports:
            return False

        # Find insertion point (after __future__ imports, before other imports)
        insert_idx = 0
        has_future = False

        for i, line in enumerate(lines):
            if "from __future__ import" in line:
                has_future = True
                insert_idx = i + 1
            elif has_future and line.strip() and not line.startswith("from __future__"):
                break
            elif not has_future and (
                line.startswith("import ") or line.startswith("from ")
            ):
                insert_idx = i
                break

        # Insert the missing imports
        for imp in sorted(needs_imports):
            lines.insert(insert_idx, imp)
            insert_idx += 1

        # Write back
        new_content = "\n".join(lines)
        filepath.write_text(new_content)
        return True

    except Exception as e:
        print(f"Error processing {filepath}: {e}")
        return False


def main():
    """Fix all test files."""
    test_dir = Path("/mnt/c/CustomScripts/Python/PyFFMPEG/BB/shotbot/tests")

    # Get all test files with errors
    error_files = [
        "integration/test_thumbnail_discovery_integration.py",
        "performance/test_threede_optimization_coverage_fixed.py",
        "unit/test_example_best_practices.py",
        "unit/test_exr_edge_cases.py",
        "unit/test_launcher_dialog.py",
        "unit/test_launcher_manager.py",
        "unit/test_main_window.py",
        "unit/test_main_window_widgets.py",
        "unit/test_previous_shots_finder.py",
        "unit/test_previous_shots_grid.py",
        "unit/test_undistortion_finder.py",
        "unit/test_utils.py",
    ]

    fixed_count = 0
    for file_path in error_files:
        full_path = test_dir / file_path
        if full_path.exists():
            if add_missing_imports(full_path):
                print(f"Fixed: {file_path}")
                fixed_count += 1

    print(f"\nTotal files fixed: {fixed_count}")


if __name__ == "__main__":
    main()
