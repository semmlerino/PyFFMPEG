#!/usr/bin/env python3
"""Debug echo command execution."""

import sys
import time

from PySide6.QtCore import QCoreApplication

from qprocess_manager import QProcessManager


def test_echo():
    """Test echo command execution with debug output."""
    print("Creating QCoreApplication...")
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    
    print("Creating QProcessManager...")
    manager = QProcessManager()
    
    print("Executing echo command...")
    process_id = manager.execute(
        command="echo",
        arguments=["hello"],
        capture_output=True
    )
    
    if process_id is None:
        print("❌ Failed to create process")
        return False
        
    print(f"✓ Process created: {process_id}")
    
    # Check state over time
    for i in range(10):
        info = manager.get_process_info(process_id)
        if info:
            print(f"  {i*0.2:.1f}s: state={info.state}, is_active={info.is_active}, exit_code={info.exit_code}")
            if not info.is_active:
                print(f"✓ Process completed: state={info.state}, exit_code={info.exit_code}")
                print(f"  Output: {info.output_buffer}")
                manager.shutdown()
                return True
        time.sleep(0.2)
        app.processEvents()
    
    print("❌ Process didn't complete after 2 seconds")
    info = manager.get_process_info(process_id)
    if info:
        print(f"  Final state: {info.state}, is_active={info.is_active}")
        print(f"  Output buffer: {info.output_buffer}")
    
    manager.shutdown()
    return False

if __name__ == "__main__":
    success = test_echo()
    if success:
        print("✅ Test passed")
    else:
        print("❌ Test failed")