#!/usr/bin/env python3
"""Debug QProcessManager signal flow."""

import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from qprocess_manager import QProcessManager


def main():
    app = QApplication(sys.argv)
    
    manager = QProcessManager()
    
    def on_started(process_id, info):
        print(f"✓ Manager started: {process_id}, state={info.state}")
    
    def on_finished(process_id, info):
        print(f"✓ Manager finished: {process_id}, state={info.state}, exit_code={info.exit_code}")
        app.quit()
    
    def on_state_changed(process_id, state):
        print(f"✓ Manager state changed: {process_id} -> {state}")
    
    def on_output(process_id, line):
        print(f"✓ Manager output: {line}")
    
    def timeout_check():
        print("Timeout check...")
        app.quit()
    
    # Connect manager signals
    manager.process_started.connect(on_started)
    manager.process_finished.connect(on_finished)
    manager.process_state_changed.connect(on_state_changed)
    manager.process_output.connect(on_output)
    
    # Set timeout
    QTimer.singleShot(5000, timeout_check)
    
    print("Starting process via manager...")
    process_id = manager.execute('echo', ['hello'], capture_output=True)
    print(f"Process ID: {process_id}")
    
    if process_id:
        # Check initial state
        info = manager.get_process_info(process_id)
        print(f"Initial state: {info.state if info else None}")
        
    # Run event loop
    app.exec()
    
    # Check final state
    if process_id:
        info = manager.get_process_info(process_id)
        print(f"Final state: {info.state if info else None}")
        print(f"Exit code: {info.exit_code if info else None}")
        print(f"Is active: {info.is_active if info else None}")
    
    manager.shutdown()

if __name__ == "__main__":
    main()