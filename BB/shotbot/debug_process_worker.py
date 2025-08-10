#!/usr/bin/env python3
"""Debug script to test ProcessWorker directly."""

import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from qprocess_manager import ProcessConfig, ProcessState, ProcessWorker


def main():
    app = QApplication(sys.argv)
    
    config = ProcessConfig(
        command="echo",
        arguments=["hello"],
        capture_output=True,
        timeout_ms=5000
    )
    
    worker = ProcessWorker("debug_test", config)
    
    def on_started(process_id):
        print(f"✓ Started: {process_id}")
    
    def on_finished(process_id, exit_code, exit_status):
        print(f"✓ Finished: {process_id}, exit_code={exit_code}, status={exit_status}")
        info = worker.get_info()
        print(f"  Final state: {info.state}")
        app.quit()
    
    def on_output(process_id, line):
        print(f"✓ Output: {line}")
    
    def on_error(process_id, error):
        print(f"✗ Error: {error}")
        app.quit()
    
    def on_state_changed(process_id, state):
        print(f"✓ State changed: {state}")
    
    def timeout_check():
        info = worker.get_info()
        print(f"Timeout check - State: {info.state}, Active: {info.is_active}")
        if info.state == ProcessState.RUNNING:
            print("Process still running after 3 seconds - something is wrong!")
            app.quit()
    
    # Connect signals
    worker.started.connect(on_started)
    worker.finished.connect(on_finished)
    worker.output_ready.connect(on_output)
    worker.failed.connect(on_error)
    worker.state_changed.connect(on_state_changed)
    
    # Set up timeout
    QTimer.singleShot(3000, timeout_check)
    
    print("Starting worker...")
    worker.start()
    
    # Run the event loop
    app.exec()
    
    worker.wait()
    final_info = worker.get_info()
    print(f"Final info: state={final_info.state}, exit_code={final_info.exit_code}")

if __name__ == "__main__":
    main()