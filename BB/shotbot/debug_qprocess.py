#!/usr/bin/env python3
"""Debug script to test basic QProcess functionality."""

import sys

from PySide6.QtCore import QCoreApplication, QProcess


def test_basic_qprocess():
    """Test basic QProcess without our wrapper."""
    print("Testing basic QProcess...")
    
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    
    process = QProcess()
    
    # Simple echo test
    process.start("echo", ["Hello World"])
    
    if not process.waitForStarted(1000):
        print(f"❌ Failed to start: {process.errorString()}")
        return False
    
    print("✓ Process started")
    
    if not process.waitForFinished(5000):
        print(f"❌ Process didn't finish: {process.errorString()}")
        return False
    
    print("✓ Process finished")
    
    output = process.readAllStandardOutput().data().decode()
    print(f"✓ Output: '{output.strip()}'")
    
    return True

if __name__ == "__main__":
    success = test_basic_qprocess()
    if success:
        print("✅ Basic QProcess works")
    else:
        print("❌ Basic QProcess failed")