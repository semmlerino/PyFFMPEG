#!/usr/bin/env python3
"""Test script to verify the segmentation fault fix in qprocess_manager.

This script specifically tests the scenarios that were causing crashes:
1. Process termination during execution
2. Concurrent process management
3. Rapid start/stop cycles
4. Signal emission under load
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from PySide6.QtCore import QCoreApplication, QTimer

from qprocess_manager_fixed import ProcessState, QProcessManager


def test_terminate_during_execution():
    """Test terminating a process while it's running - this was causing the crash."""
    print("Testing process termination during execution...")
    
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    manager = QProcessManager()
    
    # Start a long-running process
    process_id = manager.execute(
        command="sleep",
        arguments=["10"],
        capture_output=False
    )
    
    assert process_id is not None, "Failed to start process"
    print(f"Started process: {process_id}")
    
    # Give it time to start
    QTimer.singleShot(100, app.quit)
    app.exec()
    
    # Now terminate it - this is where the crash was happening
    print("Terminating process...")
    success = manager.terminate_process(process_id)
    assert success, "Failed to terminate process"
    
    # Wait a bit for cleanup
    QTimer.singleShot(1000, app.quit)
    app.exec()
    
    # Verify process is terminated
    info = manager.get_process_info(process_id)
    if info:
        assert info.state in (ProcessState.TERMINATED, ProcessState.FINISHED), \
            f"Process in unexpected state: {info.state}"
    
    print("✓ Process termination test passed")
    manager.shutdown()
    return True


def test_concurrent_processes():
    """Test running multiple processes concurrently."""
    print("\nTesting concurrent process execution...")
    
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    manager = QProcessManager()
    
    # Start multiple processes
    process_ids = []
    for i in range(5):
        pid = manager.execute(
            command="echo",
            arguments=[f"Process {i}"],
            capture_output=True
        )
        if pid:
            process_ids.append(pid)
            print(f"Started process {i}: {pid}")
    
    assert len(process_ids) == 5, "Failed to start all processes"
    
    # Wait for them to complete
    QTimer.singleShot(2000, app.quit)
    app.exec()
    
    # Check all completed successfully
    for pid in process_ids:
        info = manager.get_process_info(pid)
        if info:
            assert info.state == ProcessState.FINISHED, \
                f"Process {pid} in unexpected state: {info.state}"
    
    print("✓ Concurrent processes test passed")
    manager.shutdown()
    return True


def test_rapid_start_stop():
    """Test rapid start/stop cycles to stress thread management."""
    print("\nTesting rapid start/stop cycles...")
    
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    manager = QProcessManager()
    
    for cycle in range(3):
        print(f"Cycle {cycle + 1}...")
        
        # Start a process
        pid = manager.execute(
            command="sleep",
            arguments=["5"],
            capture_output=False
        )
        
        assert pid is not None, f"Failed to start process in cycle {cycle}"
        
        # Quick stop
        QTimer.singleShot(50, app.quit)
        app.exec()
        
        # Terminate it
        success = manager.terminate_process(pid)
        assert success, f"Failed to terminate in cycle {cycle}"
        
        # Brief pause
        QTimer.singleShot(100, app.quit)
        app.exec()
    
    print("✓ Rapid start/stop test passed")
    manager.shutdown()
    return True


def test_signal_emission_under_load():
    """Test signal emission with multiple active processes."""
    print("\nTesting signal emission under load...")
    
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    manager = QProcessManager()
    
    # Track signal emissions
    signal_count = {"started": 0, "finished": 0, "output": 0}
    
    def on_started(pid, info):
        signal_count["started"] += 1
    
    def on_finished(pid, info):
        signal_count["finished"] += 1
    
    def on_output(pid, line):
        signal_count["output"] += 1
    
    # Connect signals
    manager.process_started.connect(on_started)
    manager.process_finished.connect(on_finished)
    manager.process_output.connect(on_output)
    
    # Start multiple processes that generate output
    process_ids = []
    for i in range(3):
        pid = manager.execute_shell(
            command=f"for j in {{1..3}}; do echo 'Process {i} line '$j; sleep 0.1; done",
            capture_output=True
        )
        if pid:
            process_ids.append(pid)
    
    # Let them run
    QTimer.singleShot(3000, app.quit)
    app.exec()
    
    # Verify signals were emitted
    print(f"Signals emitted - Started: {signal_count['started']}, "
          f"Finished: {signal_count['finished']}, "
          f"Output: {signal_count['output']}")
    
    assert signal_count["started"] >= 3, "Not enough start signals"
    assert signal_count["finished"] >= 3, "Not enough finish signals"
    assert signal_count["output"] >= 9, "Not enough output signals"
    
    print("✓ Signal emission test passed")
    manager.shutdown()
    return True


def test_error_handling():
    """Test error scenarios that might trigger the race condition."""
    print("\nTesting error handling scenarios...")
    
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    manager = QProcessManager()
    
    # Try to execute non-existent command
    pid = manager.execute(
        command="this_command_does_not_exist",
        arguments=["test"],
        capture_output=True
    )
    
    if pid:
        # Wait for it to fail
        QTimer.singleShot(1000, app.quit)
        app.exec()
        
        info = manager.get_process_info(pid)
        if info:
            assert info.state == ProcessState.FAILED, \
                f"Expected FAILED state, got {info.state}"
    
    # Try to terminate non-existent process
    success = manager.terminate_process("fake_process_id")
    assert not success, "Should fail to terminate non-existent process"
    
    print("✓ Error handling test passed")
    manager.shutdown()
    return True


def run_all_tests():
    """Run all segfault fix verification tests."""
    print("=" * 60)
    print("SEGMENTATION FAULT FIX VERIFICATION")
    print("=" * 60)
    
    tests = [
        ("Process Termination", test_terminate_during_execution),
        ("Concurrent Processes", test_concurrent_processes),
        ("Rapid Start/Stop", test_rapid_start_stop),
        ("Signal Emission", test_signal_emission_under_load),
        ("Error Handling", test_error_handling),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            success = test_func()
            results.append((name, success))
        except Exception as e:
            print(f"✗ {name} failed with exception: {e}")
            results.append((name, False))
    
    print("\n" + "=" * 60)
    print("TEST RESULTS")
    print("=" * 60)
    
    all_passed = True
    for name, success in results:
        status = "✓ PASSED" if success else "✗ FAILED"
        print(f"{name:.<40} {status}")
        if not success:
            all_passed = False
    
    print("=" * 60)
    if all_passed:
        print("ALL TESTS PASSED - Segfault fix verified!")
        return 0
    else:
        print("SOME TESTS FAILED - Fix may be incomplete")
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())