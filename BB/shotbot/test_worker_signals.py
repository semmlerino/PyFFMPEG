#!/usr/bin/env python3
"""Test ProcessWorker signal emissions directly."""

import sys

from PySide6.QtCore import QCoreApplication

from qprocess_manager import ProcessConfig, ProcessWorker


def test_worker_signals():
    """Test worker signal emissions."""
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    
    # Create worker directly
    config = ProcessConfig(
        command="echo",
        arguments=["test"],
        capture_output=True
    )
    worker = ProcessWorker("test_worker", config)
    
    # Track signals
    signals = []
    
    def on_started(pid):
        print(f"Worker started: {pid}")
        signals.append(('started', pid))
    
    def on_finished(pid, code, status):
        print(f"Worker finished: {pid}, code={code}")
        signals.append(('finished', pid, code))
    
    def on_state_changed(pid, state):
        print(f"State changed: {pid} -> {state}")
        signals.append(('state', pid, state))
    
    def on_output(pid, line):
        print(f"Output: {pid}: {line}")
        signals.append(('output', pid, line))
    
    # Connect signals with explicit connection type
    from PySide6.QtCore import Qt
    worker.started.connect(on_started, Qt.QueuedConnection)
    worker.finished.connect(on_finished, Qt.QueuedConnection)
    worker.state_changed.connect(on_state_changed, Qt.QueuedConnection)
    worker.output_ready.connect(on_output, Qt.QueuedConnection)
    
    print("Starting worker...")
    worker.start()
    
    print("Waiting for worker to finish...")
    # Process events while waiting
    count = 0
    while worker.isRunning() and count < 50:  # 5 seconds max
        app.processEvents()
        worker.wait(100)
        count += 1
    
    if worker.isRunning():
        print("Worker didn't finish in time")
        worker.stop()
        worker.wait(2000)
    
    print("\nWorker info:")
    info = worker.get_info()
    print(f"  State: {info.state}")
    print(f"  Exit code: {info.exit_code}")
    print(f"  Output: {info.output_buffer}")
    
    print(f"\nSignals received: {len(signals)}")
    for sig in signals:
        print(f"  {sig}")
    
    return len(signals) > 0

if __name__ == "__main__":
    success = test_worker_signals()
    if success:
        print("\n✅ Worker signals working")
    else:
        print("\n❌ No worker signals received")