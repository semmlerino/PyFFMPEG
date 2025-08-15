#!/usr/bin/env python3
"""Test full application startup to identify hang point."""

import logging
import sys
from pathlib import Path

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)

print("=== Testing Full Startup ===")

# Add the shotbot directory to path
sys.path.insert(0, str(Path(__file__).parent))

print("1. Setting up logging...")
from shotbot import setup_logging

setup_logging()
print("✓ Logging configured")

print("\n2. Creating QApplication...")
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
app.setApplicationName("ShotBot")
app.setOrganizationName("VFX")
print("✓ QApplication created")

print("\n3. Setting up theme...")
app.setStyle("Fusion")
# Skip palette setup for brevity
print("✓ Theme configured")

print("\n4. Creating MainWindow...")
from main_window import MainWindow

window = MainWindow()
print("✓ MainWindow created")

print("\n5. Showing window...")
window.show()
print("✓ Window shown")

print("\n6. Setting up auto-quit timer...")
# Auto-quit after 3 seconds
QTimer.singleShot(3000, lambda: (print("✓ Timer fired, quitting..."), app.quit()))
print("✓ Timer scheduled")

print("\n7. Starting event loop...")
print("Calling app.exec()...")
result = app.exec()
print(f"✓ Event loop exited with code: {result}")

print("\n✅ Full application test completed successfully!")
sys.exit(result)