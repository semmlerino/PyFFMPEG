#!/usr/bin/env python3
"""Minimal test of ProcessWorker signal issue."""

import sys

from PySide6.QtCore import QCoreApplication, Qt, QThread

# Import the actual ProcessWorker
from qprocess_manager import ProcessConfig, ProcessWorker


def test_minimal():
    """Minimal test of ProcessWorker."""
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    
    # Create a minimal config
    config = ProcessConfig(
        command="true",  # Command that exits immediately with success
        arguments=[],
        capture_output=False,
        timeout_ms=5000
    )
    
    # Create worker
    worker = ProcessWorker("minimal_test", config)
    
    # Track ALL signals with simple print
    def print_signal(*args):
        print(f"SIGNAL RECEIVED: {args}")
        return True
    
    # Try connecting in different ways
    print("Connecting signals...")
    
    # Method 1: Direct connection
    worker.started.connect(lambda x: print(f"STARTED: {x}"))
    
    # Method 2: Queued connection  
    worker.state_changed.connect(lambda x, y: print(f"STATE: {x} -> {y}"), Qt.QueuedConnection)
    
    # Method 3: Auto connection (default)
    worker.finished.connect(lambda x, y, z: print(f"FINISHED: {x}, {y}, {z}"))
    
    print("Starting worker thread...")
    worker.start()
    
    print("Processing events...")
    # Aggressive event processing
    for i in range(50):  # 5 seconds
        app.processEvents()
        QThread.msleep(100)
        if not worker.isRunning():
            print(f"Worker stopped after {i*100}ms")
            break
    
    print(f"Final state: {worker.get_info().state}")
    
    # Try emitting a signal directly from main thread
    print("\nTesting direct signal emission from main thread...")
    worker.started.emit("direct_test")
    app.processEvents()
    
    return True

if __name__ == "__main__":
    test_minimal()