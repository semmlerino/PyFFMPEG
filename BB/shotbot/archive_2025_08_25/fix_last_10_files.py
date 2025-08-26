#!/usr/bin/env python3
"""Fix the last 10 test files with collection errors."""

from pathlib import Path

# Fix scripts for each specific file
fixes = {
    "tests/unit/test_previous_shots_finder.py": '''"""Tests for PreviousShotsFinder class.

Following best practices:
- Mocks only at system boundaries (subprocess)
- Uses real filesystem structures with tmp_path
- Tests behavior, not implementation
- No excessive mocking
"""

from __future__ import annotations

import sys
import pytest
import unittest
from pathlib import Path

from unittest.mock import patch
from previous_shots_finder import PreviousShotsFinder
from shot_model import Shot

# Import test helpers
sys.path.insert(0, str(Path(__file__).parent.parent))

pytestmark = [pytest.mark.unit, pytest.mark.slow]
''',
    "tests/unit/test_previous_shots_grid.py": '''"""Tests for PreviousShotsGrid widget.

Tests the UI grid component with real Qt widgets and signal interactions.
Follows best practices:
- Uses real Qt components where possible
- Proper signal race condition prevention
- Tests actual behavior, not implementation
- Uses qtbot properly for QWidget testing
"""

from __future__ import annotations

import pytest
import sys
import unittest

from PySide6.QtCore import QObject, Signal
from cache_manager import CacheManager
from previous_shots_grid import PreviousShotsGrid
from previous_shots_model import PreviousShotsModel
from shot_model import Shot

pytestmark = [pytest.mark.unit, pytest.mark.qt]
''',
    "tests/unit/test_main_window_widgets.py": '''"""Tests for MainWindow widgets and components.

Following UNIFIED_TESTING_GUIDE principles:
- Test behavior not implementation
- Use real Qt components with minimal mocking
- Use QSignalSpy for signal testing
- Test user interactions with real Qt events
- Verify widget state changes
- Handle Qt event loop properly with qtbot
- Clean up widgets with qtbot.addWidget()
"""

from __future__ import annotations

import pytest
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtWidgets import (
    QLabel,
    QPushButton,
    QStatusBar,
    QTabWidget,
    QWidget,
)
from PySide6.QtTest import QSignalSpy, QTest
from main_window import MainWindow
from cache_manager import CacheManager

pytestmark = [pytest.mark.unit, pytest.mark.qt]
''',
    "tests/unit/test_undistortion_finder.py": '''"""Tests for UndistortionFinder."""

import pytest
import unittest
from pathlib import Path

from unittest.mock import patch
from undistortion_finder import UndistortionFinder

pytestmark = pytest.mark.unit
''',
}


def fix_file(filepath: Path, new_content: str) -> bool:
    """Replace file content with fixed version."""
    try:
        # Read current content to find where the actual class definitions start
        current = filepath.read_text()

        # Find the first class or function definition
        lines = current.split("\n")
        class_start = -1
        for i, line in enumerate(lines):
            if (
                line.startswith("class ")
                or line.startswith("def ")
                or line.startswith("@")
            ):
                class_start = i
                break

        # If we found where classes start, preserve everything from there
        if class_start > 0:
            # Add the class definitions to our new content
            final_content = (
                new_content.strip() + "\n\n" + "\n".join(lines[class_start:])
            )
        else:
            # Just use the new content
            final_content = new_content

        filepath.write_text(final_content)
        return True
    except Exception as e:
        print(f"Error fixing {filepath}: {e}")
        return False


def main():
    """Fix remaining test files."""
    fixed_count = 0

    for file_path, content in fixes.items():
        full_path = Path("/mnt/c/CustomScripts/Python/PyFFMPEG/BB/shotbot") / file_path
        if full_path.exists():
            if fix_file(full_path, content):
                print(f"Fixed: {file_path}")
                fixed_count += 1
        else:
            print(f"Not found: {file_path}")

    print(f"\nTotal files fixed: {fixed_count}")


if __name__ == "__main__":
    main()
