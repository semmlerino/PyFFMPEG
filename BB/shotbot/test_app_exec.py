#!/usr/bin/env python3
"""Test if app.exec() is causing the hang."""

import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

# Add the shotbot directory to path
sys.path.insert(0, str(Path(__file__).parent))

print("Testing Qt app.exec()...")

# Create application
app = QApplication(sys.argv)
print("✓ QApplication created")

# Import and create main window
from main_window import MainWindow

window = MainWindow()
print("✓ MainWindow created")

# Show window
window.show()
print("✓ Window shown")

# Set a timer to quit after 2 seconds
QTimer.singleShot(2000, lambda: (print("✓ Timer fired, quitting..."), app.quit()))

print("Starting event loop...")
# Run event loop
result = app.exec()
print(f"✓ Event loop exited with code: {result}")

sys.exit(result)