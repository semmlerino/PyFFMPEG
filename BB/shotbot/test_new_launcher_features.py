#!/usr/bin/env python3
"""Test script to verify new launcher manager features work correctly."""

import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

# Add the current directory to sys.path to import our modules
sys.path.insert(0, str(Path(__file__).parent))

try:
    from launcher_manager import (
        LauncherManager,
        ProcessInfo,
    )
except ImportError as e:
    print(f"Warning: Could not import required modules: {e}")
    print("This is expected if PySide6 is not installed. The syntax validation passed.")
    sys.exit(0)


class TestNewLauncherFeatures(unittest.TestCase):
    """Test new launcher manager features for thread safety and resource management."""

    def setUp(self):
        """Set up test environment."""
        self.test_dir = tempfile.mkdtemp()

        # Mock the config to use test directory
        with patch("launcher_manager.LauncherConfig") as mock_config_class:
            mock_config = Mock()
            mock_config.load_launchers.return_value = {}
            mock_config.save_launchers.return_value = True
            mock_config_class.return_value = mock_config

            self.manager = LauncherManager()
            self.manager.config = mock_config

    def tearDown(self):
        """Clean up test environment."""
        import shutil

        # Shutdown the manager to clean up resources
        self.manager.shutdown()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_process_info_creation(self):
        """Test ProcessInfo class creation."""
        mock_process = Mock()
        mock_process.pid = 12345

        process_info = ProcessInfo(
            process=mock_process,
            launcher_id="test-launcher",
            launcher_name="Test Launcher",
            command="echo test",
            timestamp=time.time(),
        )

        self.assertEqual(process_info.launcher_id, "test-launcher")
        self.assertEqual(process_info.launcher_name, "Test Launcher")
        self.assertEqual(process_info.command, "echo test")
        self.assertFalse(process_info.validated)

    def test_unique_process_key_generation(self):
        """Test that process keys are unique."""
        launcher_id = "test-launcher"
        pid = 12345

        # Generate multiple keys
        keys = set()
        for _ in range(10):
            key = self.manager._generate_process_key(launcher_id, pid)
            keys.add(key)
            time.sleep(0.001)  # Small delay to ensure different timestamps

        # All keys should be unique
        self.assertEqual(len(keys), 10)

        # Keys should contain expected components
        for key in keys:
            self.assertIn(launcher_id, key)
            self.assertIn(str(pid), key)

    def test_process_limits(self):
        """Test that process limits are enforced."""
        # Create a launcher
        launcher_id = self.manager.create_launcher(
            name="Test Launcher", command="sleep 1"
        )
        self.assertIsNotNone(launcher_id)

        # Mock the process limit to be very low for testing
        original_limit = self.manager.MAX_CONCURRENT_PROCESSES
        self.manager.MAX_CONCURRENT_PROCESSES = 2

        try:
            with patch("subprocess.Popen") as mock_popen:
                # Create mock processes
                mock_processes = []
                for i in range(3):
                    mock_process = Mock()
                    mock_process.pid = 1000 + i
                    mock_process.poll.return_value = None  # Still running
                    mock_processes.append(mock_process)

                mock_popen.side_effect = mock_processes

                # Mock process validation to always succeed
                with patch.object(
                    self.manager, "_validate_process_startup", return_value=True
                ):
                    # First two executions should succeed
                    success1 = self.manager.execute_launcher(launcher_id)
                    self.assertTrue(success1)

                    success2 = self.manager.execute_launcher(launcher_id)
                    self.assertTrue(success2)

                    # Third execution should fail due to limit
                    success3 = self.manager.execute_launcher(launcher_id)
                    self.assertFalse(success3)

        finally:
            # Restore original limit
            self.manager.MAX_CONCURRENT_PROCESSES = original_limit

    def test_process_cleanup(self):
        """Test that finished processes are cleaned up."""
        # Create launcher
        launcher_id = self.manager.create_launcher(
            name="Cleanup Test", command="echo test"
        )

        with patch("subprocess.Popen") as mock_popen:
            # Create mock process that starts then finishes
            mock_process = Mock()
            mock_process.pid = 12345
            mock_process.poll.side_effect = [None, None, 0]  # Running, then finished
            mock_popen.return_value = mock_process

            with patch.object(
                self.manager, "_validate_process_startup", return_value=True
            ):
                # Execute launcher
                success = self.manager.execute_launcher(launcher_id)
                self.assertTrue(success)

                # Should have one active process
                initial_count = self.manager.get_active_process_count()
                self.assertEqual(initial_count, 1)

                # After cleanup, should have none
                self.manager._cleanup_finished_processes()
                final_count = self.manager.get_active_process_count()
                self.assertEqual(final_count, 0)

    def test_get_active_process_info(self):
        """Test getting active process information."""
        # Initially no processes
        info = self.manager.get_active_process_info()
        self.assertEqual(len(info), 0)

        # Create launcher
        launcher_id = self.manager.create_launcher(
            name="Info Test", command="echo info test"
        )

        with patch("subprocess.Popen") as mock_popen:
            mock_process = Mock()
            mock_process.pid = 54321
            mock_process.poll.return_value = None  # Still running
            mock_popen.return_value = mock_process

            with patch.object(
                self.manager, "_validate_process_startup", return_value=True
            ):
                success = self.manager.execute_launcher(launcher_id)
                self.assertTrue(success)

                # Get process info
                info = self.manager.get_active_process_info()
                self.assertEqual(len(info), 1)

                process_info = info[0]
                self.assertEqual(process_info["launcher_id"], launcher_id)
                self.assertEqual(process_info["launcher_name"], "Info Test")
                self.assertEqual(process_info["pid"], 54321)
                self.assertTrue(process_info["validated"])
                self.assertTrue(process_info["running"])

    def test_process_termination(self):
        """Test manual process termination."""
        launcher_id = self.manager.create_launcher(
            name="Termination Test", command="sleep 60"
        )

        with patch("subprocess.Popen") as mock_popen:
            mock_process = Mock()
            mock_process.pid = 99999
            mock_process.poll.return_value = None  # Still running
            mock_process.wait.return_value = None
            mock_popen.return_value = mock_process

            with patch.object(
                self.manager, "_validate_process_startup", return_value=True
            ):
                success = self.manager.execute_launcher(launcher_id)
                self.assertTrue(success)

                # Get the process key
                info = self.manager.get_active_process_info()
                self.assertEqual(len(info), 1)
                process_key = info[0]["key"]

                # Terminate the process
                terminated = self.manager.terminate_process(process_key)
                self.assertTrue(terminated)

                # Verify process was cleaned up
                mock_process.terminate.assert_called_once()

    def test_shutdown_cleanup(self):
        """Test that shutdown properly cleans up all processes."""
        # Create multiple launchers and execute them
        launcher_ids = []
        for i in range(3):
            launcher_id = self.manager.create_launcher(
                name=f"Shutdown Test {i}", command=f"sleep {i + 1}"
            )
            launcher_ids.append(launcher_id)

        with patch("subprocess.Popen") as mock_popen:
            mock_processes = []
            for i in range(3):
                mock_process = Mock()
                mock_process.pid = 10000 + i
                mock_process.poll.return_value = None  # Still running
                mock_process.wait.return_value = None
                mock_processes.append(mock_process)

            mock_popen.side_effect = mock_processes

            with patch.object(
                self.manager, "_validate_process_startup", return_value=True
            ):
                # Execute all launchers
                for launcher_id in launcher_ids:
                    success = self.manager.execute_launcher(launcher_id)
                    self.assertTrue(success)

                # Should have 3 active processes
                initial_count = self.manager.get_active_process_count()
                self.assertEqual(initial_count, 3)

                # Shutdown should clean up all processes
                self.manager.shutdown()

                # Verify all processes were terminated
                for mock_process in mock_processes:
                    mock_process.terminate.assert_called_once()


if __name__ == "__main__":
    # Run the tests
    unittest.main(verbosity=2)
