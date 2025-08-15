#!/usr/bin/env python3
"""Debug startup issues."""

import logging
import os
import sys

# Set up very verbose logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

print("=== Debug Startup ===")
print(f"Python: {sys.version}")
print(f"Platform: {sys.platform}")
print(f"DISPLAY: {os.environ.get('DISPLAY', 'NOT SET')}")
print(f"QT_QPA_PLATFORM: {os.environ.get('QT_QPA_PLATFORM', 'NOT SET')}")

print("\n1. Importing PySide6...")
try:
    from PySide6 import QtCore
    print(f"✓ Qt version: {QtCore.qVersion()}")
    print("✓ PySide6 imported successfully")
except Exception as e:
    print(f"✗ Failed: {e}")
    sys.exit(1)

print("\n2. Creating QApplication...")
try:
    from PySide6.QtWidgets import QApplication
    print("About to create QApplication...")
    app = QApplication(sys.argv)
    print("✓ QApplication created")
except Exception as e:
    print(f"✗ Failed to create QApplication: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n3. Getting platform name...")
try:
    platform_name = app.platformName()
    print(f"✓ Platform: {platform_name}")
except Exception as e:
    print(f"✗ Failed: {e}")

print("\n4. Checking screen availability...")
try:
    screens = app.screens()
    print(f"✓ Found {len(screens)} screen(s)")
    for i, screen in enumerate(screens):
        print(f"  Screen {i}: {screen.name()} - {screen.geometry()}")
except Exception as e:
    print(f"✗ Failed: {e}")

print("\n5. Testing MainWindow creation...")
try:
    print("Importing main_window...")
    from main_window import MainWindow
    print("✓ MainWindow imported")
    
    print("Creating MainWindow instance...")
    window = MainWindow()
    print("✓ MainWindow created successfully!")
    
    print("\n✅ Full application initialization successful!")
    print("The application should be able to start.")
except Exception as e:
    print(f"✗ MainWindow creation failed: {e}")
    import traceback
    traceback.print_exc()