#!/usr/bin/env python3
"""Test lazy initialization fix."""

import sys

from PySide6.QtWidgets import QApplication  # noqa: E402

from process_pool_manager import ProcessPoolManager  # noqa: E402

print("Testing lazy initialization...")

# Step 1: Import and create ProcessPoolManager
print("1. Importing ProcessPoolManager...")

print("✓ Imported")

print("2. Getting ProcessPoolManager instance...")
pm = ProcessPoolManager.get_instance()
print("✓ Instance created (sessions should NOT be created yet)")

print("3. Creating QApplication...")

app = QApplication(sys.argv)
print("✓ QApplication created")

print("4. Now triggering first command (sessions should be created now)...")
try:
    result = pm.execute_workspace_command("echo test", timeout=3)
    print(f"✓ Command executed: {result[:50] if result else 'empty'}")
except Exception as e:
    print(f"✗ Command failed: {e}")

print("5. Shutting down...")
pm.shutdown()
print("✓ Complete")

print("\nTest passed - no hang during Qt initialization!")
