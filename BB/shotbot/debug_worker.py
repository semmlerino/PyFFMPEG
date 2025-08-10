#!/usr/bin/env python3
"""Debug script to test ProcessWorker functionality."""

import sys
import time

from PySide6.QtCore import QCoreApplication

from qprocess_manager import ProcessConfig, ProcessWorker


def test_worker_directly():
    """Test ProcessWorker directly."""
    print("Testing ProcessWorker...")
    
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    
    config = ProcessConfig(
        command="echo",
        arguments=["test"],
        capture_output=True,
        timeout_ms=5000
    )
    
    worker = ProcessWorker("test_proc", config)
    
    # Connect signals for debugging
    worker.started.connect(lambda pid: print(f"✓ Worker started: {pid}"))
    worker.finished.connect(lambda pid, code, status: print(f"✓ Worker finished: {pid}, code: {code}"))
    worker.failed.connect(lambda pid, error: print(f"❌ Worker failed: {pid}, error: {error}"))
    worker.output_ready.connect(lambda pid, line: print(f"✓ Output: {line}"))
    
    print("Starting worker...")
    worker.start()
    
    # Let it run
    start_time = time.time()
    while worker.isRunning() and (time.time() - start_time) < 10:
        app.processEvents()
        time.sleep(0.1)
    
    if worker.isRunning():
        print("❌ Worker still running after 10 seconds")
        worker.stop()
        worker.wait(2000)
        return False
    
    print("✓ Worker completed")
    return True

if __name__ == "__main__":
    success = test_worker_directly()
    if success:
        print("✅ ProcessWorker test passed")
    else:
        print("❌ ProcessWorker test failed")