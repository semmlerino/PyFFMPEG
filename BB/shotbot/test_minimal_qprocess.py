#!/usr/bin/env python3
"""Minimal test to debug QProcess issues."""

import sys
import time

from PySide6.QtCore import QCoreApplication

from qprocess_manager import ProcessState, QProcessManager


def test_minimal():
    """Test minimal functionality step by step."""
    print("Creating QCoreApplication...")
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    
    print("Creating QProcessManager...")
    manager = QProcessManager()
    
    print("Starting echo process...")
    process_id = manager.execute(
        command="echo",
        arguments=["hello"],
        capture_output=True
    )
    
    if process_id is None:
        print("❌ Failed to create process")
        return False
        
    print(f"✓ Process created: {process_id}")
    
    # Check process info immediately
    info = manager.get_process_info(process_id)
    if info:
        print(f"Initial state: {info.state}")
    else:
        print("❌ No process info available")
        return False
    
    # Wait a bit and check again
    time.sleep(0.5)
    app.processEvents()
    
    info = manager.get_process_info(process_id)
    if info:
        print(f"After 0.5s: {info.state}")
    
    # Try waiting for completion
    print("Waiting for process completion...")
    final_info = manager.wait_for_process(process_id, timeout_ms=2000)
    
    if final_info:
        print(f"✓ Process completed: {final_info.state}, exit_code: {final_info.exit_code}")
        print(f"Output buffer: {final_info.output_buffer}")
        success = final_info.state in [ProcessState.FINISHED, ProcessState.TERMINATED]
    else:
        print("❌ Process didn't complete within timeout")
        success = False
    
    print("Shutting down manager...")
    manager.shutdown()
    
    return success

if __name__ == "__main__":
    success = test_minimal()
    if success:
        print("✅ Test passed")
    else:
        print("❌ Test failed")