#!/usr/bin/env python3
"""Debug script to test mock detection."""

from unittest.mock import Mock

from PySide6.QtCore import QProcess

# Create the same mock as the test
mock_process = Mock(spec=QProcess)
mock_process.state.return_value = QProcess.Running

print("Mock attributes:")
print(f"hasattr processId: {hasattr(mock_process, 'processId')}")
print(f"hasattr state: {hasattr(mock_process, 'state')}")
print(f"hasattr waitForFinished: {hasattr(mock_process, 'waitForFinished')}")

# Check if it's a mock
print(f"Is Mock: {isinstance(mock_process, Mock)}")
print(f"Mock spec: {mock_process._spec_class if hasattr(mock_process, '_spec_class') else 'No spec'}")

# Real QProcess for comparison
import sys

from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
real_process = QProcess()

print("\nReal QProcess attributes:")
print(f"hasattr processId: {hasattr(real_process, 'processId')}")
print(f"hasattr state: {hasattr(real_process, 'state')}")
print(f"hasattr waitForFinished: {hasattr(real_process, 'waitForFinished')}")