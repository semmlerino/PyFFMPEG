#!/usr/bin/env python3
"""Debug script to test state transitions."""

import sys

from PySide6.QtCore import QCoreApplication

from qprocess_manager import QProcessManager


def test_state_transitions():
    """Test and debug state transitions."""
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    manager = QProcessManager()
    
    # Track all signals
    signals_received = []
    
    def on_state_changed(pid, state):
        print(f"State changed: {pid} -> {state}")
        signals_received.append(('state', pid, state))
    
    def on_started(pid, info):
        print(f"Process started: {pid}")
        signals_received.append(('started', pid))
    
    def on_finished(pid, info):
        print(f"Process finished: {pid}")
        signals_received.append(('finished', pid))
    
    # Connect signals
    manager.process_state_changed.connect(on_state_changed)
    manager.process_started.connect(on_started)
    manager.process_finished.connect(on_finished)
    
    # Execute command
    print("Executing echo command...")
    process_id = manager.execute(
        command="echo",
        arguments=["test"],
        capture_output=True
    )
    
    print(f"Process ID: {process_id}")
    
    # Check initial state
    info = manager.get_process_info(process_id)
    print(f"Initial state: {info.state if info else 'None'}")
    
    # Wait for completion
    print("Waiting for completion...")
    final_info = manager.wait_for_process(process_id, timeout_ms=5000)
    
    if final_info:
        print(f"Final state: {final_info.state}")
        print(f"Exit code: {final_info.exit_code}")
        print(f"Output: {final_info.output_buffer}")
    else:
        print("Process didn't complete")
    
    # Print all signals received
    print("\nSignals received:")
    for signal in signals_received:
        print(f"  {signal}")
    
    manager.shutdown()
    
    # Check what states were seen
    states_seen = [s[2] for s in signals_received if s[0] == 'state']
    print(f"\nStates seen: {states_seen}")
    
    return len(signals_received) > 0

if __name__ == "__main__":
    success = test_state_transitions()
    if success:
        print("\n✅ Test passed - signals received")
    else:
        print("\n❌ Test failed - no signals received")