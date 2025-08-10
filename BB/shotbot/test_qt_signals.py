#!/usr/bin/env python3
"""Test Qt signal emission from QThread."""

import sys

from PySide6.QtCore import QCoreApplication, QObject, Qt, QThread, Signal


class TestWorker(QThread):
    """Simple test worker."""
    
    test_signal = Signal(str)
    
    def run(self):
        """Run method that emits signal."""
        print("Worker thread running...")
        
        # Try emitting signal from run method
        self.test_signal.emit("from_run_method")
        
        # Small delay
        self.msleep(100)
        
        print("Worker thread done")

class TestObject(QObject):
    """Test object with signal."""
    
    test_signal = Signal(str)
    
    def emit_signal(self):
        """Emit signal from method."""
        self.test_signal.emit("from_method")

def test_thread_signals():
    """Test signal emission from thread."""
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    
    print("Testing QThread signal emission...")
    
    # Test 1: Simple worker thread
    signals_received = []
    
    def on_signal(msg):
        print(f"Received: {msg}")
        signals_received.append(msg)
    
    worker = TestWorker()
    worker.test_signal.connect(on_signal, Qt.QueuedConnection)  # Explicit queued connection
    
    print("Starting worker...")
    worker.start()
    worker.wait(1000)
    
    # Process events
    app.processEvents()
    
    print(f"Signals received: {signals_received}")
    
    # Test 2: Direct signal emission
    obj = TestObject()
    obj.test_signal.connect(on_signal)
    obj.emit_signal()
    
    app.processEvents()
    
    print(f"Final signals: {signals_received}")
    
    return len(signals_received) > 0

if __name__ == "__main__":
    success = test_thread_signals()
    if success:
        print("\n✅ Signals working")
    else:
        print("\n❌ No signals received")