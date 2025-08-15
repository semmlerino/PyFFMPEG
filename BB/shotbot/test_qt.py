#!/usr/bin/env python3
"""Test if Qt is working."""
import sys

from PySide6.QtWidgets import QApplication, QLabel

try:
    app = QApplication(sys.argv)
    print("✓ QApplication created successfully")
    
    # Try to create a simple widget
    label = QLabel("Test")
    print("✓ Widget created successfully")
    
    # Don't show the widget, just test creation
    print("✓ Qt is working properly")
    sys.exit(0)
except Exception as e:
    print(f"❌ Qt test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)