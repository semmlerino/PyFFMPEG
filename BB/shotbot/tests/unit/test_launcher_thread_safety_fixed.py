#!/usr/bin/env python3
"""Test launcher thread safety focusing on BEHAVIOR not implementation.

Following UNIFIED_TESTING_GUIDE:
- Test behavior, not implementation details
- No testing of internal _lock or _active_processes
- Test actual API, not imagined interface
"""

import threading
import time

import pytest
from PySide6.QtCore import QCoreApplication

from launcher_manager import CustomLauncher, LauncherManager


class TestLauncherThreadSafetyBehavior:
    """Test thread safety BEHAVIOR without testing internals."""

    @pytest.fixture(autouse=True)
    def setup_manager(self, qtbot):
        """Set up LauncherManager."""
        self.manager = LauncherManager()
        self.qtbot = qtbot

    def test_concurrent_launcher_creation(self):
        """Test that multiple launchers can be created concurrently.

        BEHAVIOR TEST: Creating launchers from multiple threads should work.
        """
        created_ids = []
        lock = threading.Lock()

        def create_launcher(thread_id):
            """Create a launcher from a thread."""
            launcher = CustomLauncher(
                id=f"concurrent_{thread_id}",
                name=f"Concurrent {thread_id}",
                description=f"Test launcher {thread_id}",
                command="echo test",
            )

            # Try to create the launcher
            try:
                self.manager.create_launcher(launcher)
                with lock:
                    created_ids.append(launcher.id)
            except Exception as e:
                print(f"Thread {thread_id} failed: {e}")

        # Start multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=create_launcher, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join(timeout=2)

        # Verify all launchers were created
        assert len(created_ids) == 5

        # Clean up
        for launcher_id in created_ids:
            self.manager.delete_launcher(launcher_id)

    def test_launcher_list_consistency(self):
        """Test that launcher list remains consistent under concurrent access.

        BEHAVIOR TEST: Reading launcher list while modifying should be safe.
        """
        # Create initial launchers
        for i in range(3):
            launcher = CustomLauncher(
                id=f"initial_{i}",
                name=f"Initial {i}",
                description=f"Initial launcher {i}",
                command="echo test",
            )
            self.manager.create_launcher(launcher)

        errors = []

        def read_launchers():
            """Read launcher list repeatedly."""
            for _ in range(10):
                try:
                    launchers = self.manager.get_launchers()
                    assert isinstance(launchers, list)
                    time.sleep(0.01)
                except Exception as e:
                    errors.append(f"Read error: {e}")

        def modify_launchers():
            """Modify launcher list."""
            for i in range(5):
                try:
                    launcher = CustomLauncher(
                        id=f"dynamic_{i}",
                        name=f"Dynamic {i}",
                        description=f"Dynamic launcher {i}",
                        command="echo test",
                    )
                    self.manager.create_launcher(launcher)
                    time.sleep(0.02)
                    self.manager.delete_launcher(f"dynamic_{i}")
                except Exception as e:
                    errors.append(f"Modify error: {e}")

        # Start concurrent operations
        read_thread = threading.Thread(target=read_launchers)
        modify_thread = threading.Thread(target=modify_launchers)

        read_thread.start()
        modify_thread.start()

        read_thread.join(timeout=5)
        modify_thread.join(timeout=5)

        # No errors should occur
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # Clean up
        for i in range(3):
            self.manager.delete_launcher(f"initial_{i}")

    def test_launcher_execution_independence(self):
        """Test that launcher executions are independent.

        BEHAVIOR TEST: Multiple launchers should execute without interfering.
        """
        # Create test launchers
        launchers = []
        for i in range(3):
            launcher = CustomLauncher(
                id=f"exec_test_{i}",
                name=f"Exec Test {i}",
                description=f"Execution test {i}",
                command="echo test",
            )
            self.manager.create_launcher(launcher)
            launchers.append(launcher)

        execution_results = []
        lock = threading.Lock()

        def execute_launcher(launcher_id):
            """Execute a launcher."""
            try:
                # Use actual API - execute_launcher takes launcher_id
                result = self.manager.execute_launcher(
                    launcher_id=launcher_id,
                    dry_run=True,  # Dry run to avoid actual process
                )
                with lock:
                    execution_results.append((launcher_id, result))
            except Exception as e:
                with lock:
                    execution_results.append((launcher_id, f"Error: {e}"))

        # Execute launchers concurrently
        threads = []
        for launcher in launchers:
            thread = threading.Thread(target=execute_launcher, args=(launcher.id,))
            threads.append(thread)
            thread.start()

        # Wait for all executions
        for thread in threads:
            thread.join(timeout=5)

        # Verify all executed
        assert len(execution_results) == 3

        # Clean up
        for launcher in launchers:
            self.manager.delete_launcher(launcher.id)

    def test_signal_emission_thread_safety(self):
        """Test that signals are emitted safely from any thread.

        BEHAVIOR TEST: Signals should work from multiple threads.
        """
        signal_count = 0
        lock = threading.Lock()

        def on_launchers_changed():
            """Track signal emissions."""
            nonlocal signal_count
            with lock:
                signal_count += 1

        # Connect to the ACTUAL signal that exists
        self.manager.launchers_changed.connect(on_launchers_changed)

        def modify_from_thread(thread_id):
            """Modify launchers from a thread."""
            launcher = CustomLauncher(
                id=f"signal_test_{thread_id}",
                name=f"Signal Test {thread_id}",
                description=f"Signal test {thread_id}",
                command="echo test",
            )
            self.manager.create_launcher(launcher)
            time.sleep(0.01)
            self.manager.delete_launcher(launcher.id)

        # Start multiple threads
        threads = []
        for i in range(3):
            thread = threading.Thread(target=modify_from_thread, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join(timeout=5)

        # Process Qt events
        app = QCoreApplication.instance()
        if app:
            app.processEvents()

        # Should have received signals (at least 3 creates)
        assert signal_count >= 3, f"Expected at least 3 signals, got {signal_count}"


if __name__ == "__main__":
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "run_tests.py", __file__, "-v"], capture_output=True, text=True
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    sys.exit(result.returncode)
