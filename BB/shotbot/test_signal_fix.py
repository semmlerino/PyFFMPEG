#!/usr/bin/env python3
"""Test fix for ProcessWorker signal emission."""

import sys

from PySide6.QtCore import (
    QCoreApplication,
    QMetaObject,
    Qt,
    QThread,
    Signal,
)


class ProcessWorkerFixed(QThread):
    """Fixed version of ProcessWorker with proper signal emission."""
    
    # Signals
    started_signal = Signal(str)
    state_changed = Signal(str, object)  # Using object instead of custom enum
    
    def __init__(self, process_id):
        super().__init__()
        self.process_id = process_id
        self.state = "PENDING"
    
    def run(self):
        """Run method with fixed signal emission."""
        print(f"Worker thread running for {self.process_id}")
        
        # Method 1: Direct emit (might not work from run())
        self.state = "RUNNING"
        print("Emitting state_changed directly...")
        self.state_changed.emit(self.process_id, self.state)
        
        # Method 2: Use QMetaObject.invokeMethod for cross-thread signal
        print("Emitting started_signal via QMetaObject...")
        QMetaObject.invokeMethod(
            self,
            "_emit_started",
            Qt.QueuedConnection
        )
        
        # Simulate work
        self.msleep(100)
        
        self.state = "FINISHED"
        print("Worker thread done")
    
    def _emit_started(self):
        """Helper method to emit signal."""
        self.started_signal.emit(self.process_id)

def test_fixed_worker():
    """Test the fixed worker."""
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    
    signals_received = []
    
    def on_started(pid):
        print(f"Received started: {pid}")
        signals_received.append(('started', pid))
    
    def on_state_changed(pid, state):
        print(f"Received state_changed: {pid} -> {state}")
        signals_received.append(('state', pid, state))
    
    worker = ProcessWorkerFixed("test_process")
    
    # Connect with explicit queued connection
    worker.started_signal.connect(on_started, Qt.QueuedConnection)
    worker.state_changed.connect(on_state_changed, Qt.QueuedConnection)
    
    print("Starting worker...")
    worker.start()
    
    # Process events while waiting
    for _ in range(20):  # 2 seconds
        app.processEvents()
        worker.wait(100)
        if not worker.isRunning():
            break
    
    print(f"\nSignals received: {len(signals_received)}")
    for sig in signals_received:
        print(f"  {sig}")
    
    return len(signals_received) > 0

if __name__ == "__main__":
    success = test_fixed_worker()
    if success:
        print("\n✅ Fixed worker signals working")
    else:
        print("\n❌ No signals received from fixed worker")