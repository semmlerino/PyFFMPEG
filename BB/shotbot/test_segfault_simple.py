#!/usr/bin/env python3
"""Simple test to verify segfault fix is working."""

import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from PySide6.QtCore import QCoreApplication

from qprocess_manager import QProcessManager


def test_basic_functionality():
    """Test basic process creation and termination without segfault."""
    print("Testing basic QProcess functionality...")
    
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    manager = QProcessManager()
    
    # Start a simple process
    process_id = manager.execute(
        command="echo",
        arguments=["hello world"],
        capture_output=True
    )
    
    if process_id is None:
        print("❌ Failed to create process")
        return False
        
    print(f"✓ Process created: {process_id}")
    
    # Give it time to complete
    info = manager.wait_for_process(process_id, timeout_ms=3000)
    if info is None:
        print("❌ Process didn't complete in time")
        return False
        
    print(f"✓ Process completed with state: {info.state}")
    
    # Check process count
    active_count, total_count = manager.get_process_count()
    print(f"✓ Process counts: {active_count} active, {total_count} total")
    
    manager.shutdown()
    print("✓ Manager shutdown completed")
    
    return True


def test_termination_scenario():
    """Test the specific termination scenario that was causing segfaults."""
    print("\nTesting process termination scenario...")
    
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    manager = QProcessManager()
    
    # Start a long-running process
    process_id = manager.execute(
        command="sleep",
        arguments=["30"],  # Long enough to terminate
        capture_output=False
    )
    
    if process_id is None:
        print("❌ Failed to create long-running process")
        return False
        
    print(f"✓ Long-running process created: {process_id}")
    
    # Let it start
    time.sleep(0.2)
    
    # Terminate it
    print("Terminating process...")
    success = manager.terminate_process(process_id)
    
    if not success:
        print("❌ Failed to terminate process")
        return False
        
    print("✓ Process termination initiated")
    
    # Wait for termination to complete
    info = manager.wait_for_process(process_id, timeout_ms=10000)
    if info is None:
        print("❌ Process termination didn't complete in time")
        return False
        
    print(f"✓ Process terminated with state: {info.state}")
    
    manager.shutdown()
    print("✓ Manager shutdown completed")
    
    return True


if __name__ == "__main__":
    print("=" * 50)
    print("SEGFAULT FIX VERIFICATION")
    print("=" * 50)
    
    try:
        success1 = test_basic_functionality()
        success2 = test_termination_scenario()
        
        if success1 and success2:
            print("\n✅ ALL TESTS PASSED - No segfaults detected!")
            sys.exit(0)
        else:
            print("\n❌ SOME TESTS FAILED")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n💥 EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)