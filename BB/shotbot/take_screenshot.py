#!/usr/bin/env python3
"""Take a screenshot using Qt's built-in screen capture."""

import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication


def capture_screenshot() -> Path | None:
    """Capture screenshot of the primary screen."""
    # Get existing QApplication instance or create one
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    # Get the primary screen
    screen = app.primaryScreen()
    if not screen:
        print("Error: No screen found")
        return None

    # Capture the screen
    pixmap = screen.grabWindow(0)

    # Save to file
    output_path = Path("/tmp/shotbot_screenshot.png")
    success = pixmap.save(str(output_path))

    if success:
        print(f"✓ Screenshot saved to: {output_path}")
        return output_path
    else:
        print("✗ Failed to save screenshot")
        return None

if __name__ == "__main__":
    # Create app if running standalone
    app = QApplication.instance() or QApplication(sys.argv)

    # Capture after a brief delay to ensure everything is rendered
    def delayed_capture() -> None:
        capture_screenshot()
        app.quit()

    QTimer.singleShot(100, delayed_capture)
    sys.exit(app.exec())
