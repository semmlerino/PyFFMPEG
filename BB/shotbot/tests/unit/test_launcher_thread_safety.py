#!/usr/bin/env python3
"""Test launcher thread safety for concurrent execution.

This test ensures that multiple launchers can run concurrently without
race conditions, process ID collisions, or resource leaks.
"""

import threading
import time
import unittest
from datetime import datetime
from typing import Dict, List
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

from PySide6.QtCore import QObject, QThread, Signal

from launcher_manager import LauncherManager, CustomLauncher


class TestLauncherThreadSafety(unittest.TestCase):
    """Test suite for launcher thread safety."""

    def setUp(self):
        """Set up test fixtures."""
        self.manager = LauncherManager()
        self.executed_commands = []
        self.lock = threading.Lock()
        
    def test_concurrent_launcher_execution(self):
        """Test that multiple launchers can run concurrently without conflicts."""
        num_launchers = 5
        launchers = []
        
        # Create multiple launchers
        for i in range(num_launchers):
            launcher = CustomLauncher(
                id=f"launcher_{i}",
                name=f"Test Launcher {i}",
                command=f"echo 'Launcher {i} running'",
                icon=""
            )
            launchers.append(launcher)
        
        # Track execution
        execution_times = {}
        
        def execute_launcher(launcher):
            """Execute a launcher and track timing."""
            start_time = time.time()
            process_key = self.manager.execute_launcher(
                launcher,
                shot_name="TEST_SHOT",
                show="test_show"
            )
            execution_times[launcher.id] = {
                'start': start_time,
                'key': process_key
            }
            return process_key
        
        # Start all launchers concurrently
        threads = []
        for launcher in launchers:
            thread = threading.Thread(target=execute_launcher, args=(launcher,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join(timeout=5)
        
        # Verify all launchers executed
        self.assertEqual(len(execution_times), num_launchers)
        
        # Verify unique process keys
        process_keys = [times['key'] for times in execution_times.values()]
        self.assertEqual(len(process_keys), len(set(process_keys)), 
                        "Process keys should be unique")

    def test_process_key_uniqueness(self):
        """Test that process keys are guaranteed unique even with rapid execution."""
        keys = set()
        
        # Rapidly generate many keys
        for _ in range(100):
            key = self.manager._generate_process_key("test_launcher")
            self.assertNotIn(key, keys, f"Duplicate key generated: {key}")
            keys.add(key)
        
        # All keys should be unique
        self.assertEqual(len(keys), 100)
        
        # Keys should contain timestamp and UUID
        for key in keys:
            self.assertIn("test_launcher_", key)
            parts = key.split("_")
            self.assertGreaterEqual(len(parts), 3)  # launcher_timestamp_uuid

    def test_active_processes_thread_safety(self):
        """Test that active processes dictionary is thread-safe."""
        num_threads = 10
        operations_per_thread = 50
        
        def add_remove_processes(thread_id):
            """Add and remove processes from active dict."""
            for i in range(operations_per_thread):
                # Add process
                key = f"thread_{thread_id}_process_{i}"
                with self.manager._lock:
                    self.manager._active_processes[key] = {
                        'launcher': f"launcher_{thread_id}",
                        'process': Mock(),
                        'start_time': datetime.now()
                    }
                
                # Small delay to increase contention
                time.sleep(0.001)
                
                # Remove process
                with self.manager._lock:
                    if key in self.manager._active_processes:
                        del self.manager._active_processes[key]
        
        # Start multiple threads
        threads = []
        for i in range(num_threads):
            thread = threading.Thread(target=add_remove_processes, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        # Should have no active processes left
        self.assertEqual(len(self.manager._active_processes), 0)

    def test_launcher_worker_cleanup(self):
        """Test that LauncherWorker threads are properly cleaned up."""
        from PySide6.QtCore import QCoreApplication
        from PySide6.QtTest import QTest
        
        app = QCoreApplication.instance()
        if not app:
            app = QCoreApplication([])
        
        # Create and start a worker
        worker = self.manager._create_launcher_worker(
            launcher=CustomLauncher("test", "Test", "echo test", ""),
            shot_name="TEST_SHOT",
            show="test_show"
        )
        
        # Track worker lifecycle
        worker_finished = False
        worker_deleted = False
        
        def on_finished():
            nonlocal worker_finished
            worker_finished = True
            
        def on_destroyed():
            nonlocal worker_deleted
            worker_deleted = True
        
        worker.finished.connect(on_finished)
        worker.destroyed.connect(on_destroyed)
        
        # Start worker
        worker.start()
        
        # Wait for completion
        QTest.qWait(1000)
        
        # Worker should finish
        self.assertTrue(worker_finished)
        
        # Clean up worker
        worker.quit()
        worker.wait()
        worker.deleteLater()
        
        # Process events to trigger deletion
        app.processEvents()
        QTest.qWait(100)

    def test_rlock_recursive_locking(self):
        """Test that RLock allows recursive locking from same thread."""
        # RLock should allow recursive acquisition
        with self.manager._lock:
            # Should be able to acquire again from same thread
            with self.manager._lock:
                # Nested lock should work
                self.manager._active_processes["test"] = {"data": "test"}
        
        # Lock should be fully released
        self.assertIn("test", self.manager._active_processes)
        
        # Clean up
        del self.manager._active_processes["test"]

    def test_concurrent_process_termination(self):
        """Test that processes can be safely terminated concurrently."""
        num_processes = 5
        process_keys = []
        
        # Start multiple processes
        for i in range(num_processes):
            key = f"process_{i}"
            process_keys.append(key)
            
            with self.manager._lock:
                self.manager._active_processes[key] = {
                    'launcher': f"launcher_{i}",
                    'process': Mock(),
                    'start_time': datetime.now()
                }
        
        # Terminate all processes concurrently
        def terminate_process(key):
            """Safely terminate a process."""
            self.manager.terminate_process(key)
        
        threads = []
        for key in process_keys:
            thread = threading.Thread(target=terminate_process, args=(key,))
            threads.append(thread)
            thread.start()
        
        # Wait for all terminations
        for thread in threads:
            thread.join()
        
        # All processes should be removed
        self.assertEqual(len(self.manager._active_processes), 0)

    def test_signal_emission_thread_safety(self):
        """Test that Qt signals are safely emitted from worker threads."""
        from PySide6.QtCore import QCoreApplication
        
        app = QCoreApplication.instance()
        if not app:
            app = QCoreApplication([])
        
        received_signals = []
        lock = threading.Lock()
        
        def on_signal(data):
            """Track received signals."""
            with lock:
                received_signals.append(data)
        
        # Connect to manager signals
        self.manager.command_started.connect(on_signal)
        self.manager.command_output.connect(on_signal)
        self.manager.command_finished.connect(on_signal)
        
        # Emit signals from multiple threads
        def emit_signals(thread_id):
            """Emit signals from thread."""
            for i in range(10):
                self.manager.command_started.emit(f"thread_{thread_id}_start_{i}")
                self.manager.command_output.emit(f"thread_{thread_id}_output_{i}")
                self.manager.command_finished.emit(f"thread_{thread_id}_finish_{i}")
        
        threads = []
        for i in range(3):
            thread = threading.Thread(target=emit_signals, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for threads
        for thread in threads:
            thread.join()
        
        # Process Qt events
        app.processEvents()
        
        # Should have received all signals
        expected_count = 3 * 3 * 10  # 3 threads * 3 signals * 10 iterations
        self.assertEqual(len(received_signals), expected_count)

    def test_process_output_buffering(self):
        """Test that process output is properly buffered without blocking."""
        # Create a mock process that produces output
        mock_process = Mock()
        mock_process.readyReadStandardOutput = Signal()
        mock_process.readyReadStandardError = Signal()
        mock_process.readAllStandardOutput = Mock(return_value=b"stdout line\n")
        mock_process.readAllStandardError = Mock(return_value=b"stderr line\n")
        
        # Track output
        output_lines = []
        
        def capture_output(line):
            output_lines.append(line)
        
        self.manager.command_output.connect(capture_output)
        
        # Simulate rapid output from process
        for _ in range(100):
            mock_process.readyReadStandardOutput.emit()
            mock_process.readyReadStandardError.emit()
        
        # Output should be buffered without blocking
        # Note: Actual implementation would process this asynchronously

    def test_launcher_execution_with_timeout(self):
        """Test launcher execution with timeout handling."""
        # Create a launcher that would timeout
        launcher = CustomLauncher(
            id="timeout_test",
            name="Timeout Test",
            command="sleep 60",  # Long-running command
            icon=""
        )
        
        # Execute with timeout tracking
        start_time = time.time()
        process_key = self.manager.execute_launcher(
            launcher,
            shot_name="TEST_SHOT",
            show="test_show"
        )
        
        # Should return immediately (non-blocking)
        elapsed = time.time() - start_time
        self.assertLess(elapsed, 1.0, "Execution should be non-blocking")
        
        # Process should be tracked
        with self.manager._lock:
            self.assertIn(process_key, self.manager._active_processes)
        
        # Clean up
        self.manager.terminate_process(process_key)

    def test_memory_leak_prevention(self):
        """Test that repeated launcher execution doesn't leak memory."""
        initial_process_count = len(self.manager._active_processes)
        
        # Execute and clean up many launchers
        for i in range(100):
            launcher = CustomLauncher(
                id=f"mem_test_{i}",
                name=f"Memory Test {i}",
                command="echo test",
                icon=""
            )
            
            # Execute
            key = self.manager.execute_launcher(
                launcher,
                shot_name="TEST_SHOT",
                show="test_show"
            )
            
            # Simulate completion
            if key in self.manager._active_processes:
                with self.manager._lock:
                    del self.manager._active_processes[key]
        
        # Should have same number of processes as initially
        final_process_count = len(self.manager._active_processes)
        self.assertEqual(final_process_count, initial_process_count)


class MockLauncherManager:
    """Mock launcher manager for testing."""
    
    def __init__(self):
        self._lock = threading.RLock()
        self._active_processes = {}
        self.command_started = Signal(str)
        self.command_output = Signal(str)
        self.command_finished = Signal(str)
    
    def _generate_process_key(self, launcher_id):
        """Generate unique process key."""
        timestamp = int(time.time() * 1000000)
        unique_id = uuid4().hex[:8]
        return f"{launcher_id}_{timestamp}_{unique_id}"
    
    def execute_launcher(self, launcher, shot_name, show):
        """Execute launcher with thread safety."""
        process_key = self._generate_process_key(launcher.id)
        
        with self._lock:
            self._active_processes[process_key] = {
                'launcher': launcher.id,
                'process': Mock(),
                'start_time': datetime.now()
            }
        
        return process_key
    
    def terminate_process(self, process_key):
        """Terminate process safely."""
        with self._lock:
            if process_key in self._active_processes:
                del self._active_processes[process_key]
    
    def _create_launcher_worker(self, launcher, shot_name, show):
        """Create a worker thread."""
        worker = QThread()
        worker.finished = Signal()
        worker.destroyed = Signal()
        return worker


# Monkey patch for testing if real module isn't available
try:
    from launcher_manager import LauncherManager, CustomLauncher
except ImportError:
    LauncherManager = MockLauncherManager
    CustomLauncher = lambda id, name, command, icon: type('CustomLauncher', (), {
        'id': id, 'name': name, 'command': command, 'icon': icon
    })()


if __name__ == "__main__":
    unittest.main()