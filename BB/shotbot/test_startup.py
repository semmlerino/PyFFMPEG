#!/usr/bin/env python3
"""Test Shotbot startup with verbose debugging."""

import logging
import sys
from pathlib import Path

# Set up very verbose logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)

# Add the shotbot directory to path
sys.path.insert(0, str(Path(__file__).parent))

print("=== Testing Shotbot Startup ===")
print("Step 1: Importing modules...")

try:
    from PySide6.QtWidgets import QApplication
    print("✓ Qt imported successfully")
except Exception as e:
    print(f"✗ Qt import failed: {e}")
    sys.exit(1)

try:
    from process_pool_manager import ProcessPoolManager
    print("✓ ProcessPoolManager imported successfully")
except Exception as e:
    print(f"✗ ProcessPoolManager import failed: {e}")
    sys.exit(1)

print("\nStep 2: Creating Qt application...")
app = QApplication(sys.argv)
print("✓ QApplication created")

print("\nStep 3: Testing ProcessPoolManager initialization...")
try:
    manager = ProcessPoolManager.get_instance()
    print("✓ ProcessPoolManager initialized")
    
    # Test a simple command to ensure it doesn't hang
    print("\nStep 4: Testing command execution...")
    result = manager.execute_workspace_command("echo 'test'", timeout=3)
    print(f"✓ Command executed successfully: {result.strip()}")
    
    print("\nStep 5: Shutting down manager...")
    manager.shutdown()
    print("✓ Manager shutdown complete")
    
except Exception as e:
    print(f"✗ ProcessPoolManager test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\nStep 6: Testing MainWindow import...")
try:
    from main_window import MainWindow
    print("✓ MainWindow imported successfully")
except Exception as e:
    print(f"✗ MainWindow import failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\nStep 7: Creating MainWindow (with 3-second timeout)...")
import signal


def timeout_handler(signum, frame):
    print("\n✗ MainWindow creation timed out - HANG DETECTED!")
    sys.exit(1)

# Set a 3-second timeout
signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm(3)

try:
    window = MainWindow()
    signal.alarm(0)  # Cancel the timeout
    print("✓ MainWindow created successfully")
    
    # Don't show the window, just test creation
    print("\n✅ All startup tests passed!")
    
except Exception as e:
    signal.alarm(0)  # Cancel the timeout
    print(f"✗ MainWindow creation failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

sys.exit(0)