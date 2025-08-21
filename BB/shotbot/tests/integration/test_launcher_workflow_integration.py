"""Integration tests for launcher execution workflow."""

import json
import shutil
import tempfile
import time
from pathlib import Path


class TestLauncherWorkflowIntegration:
    """Integration tests for launcher execution and process tracking following UNIFIED_TESTING_GUIDE."""

    def setup_method(self):
        """Minimal setup to avoid pytest fixture overhead."""
        self.temp_dir = Path(tempfile.mkdtemp(prefix="shotbot_launcher_workflow_"))
        self.config_dir = self.temp_dir / "config"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # Create test shot data
        self.test_shot = {
            "show": "test_show",
            "sequence": "seq01", 
            "shot": "0010",
            "workspace_path": "/shows/test_show/shots/seq01/seq01_0010",
            "name": "seq01_0010"
        }

    def teardown_method(self):
        """Direct cleanup without fixture dependencies."""
        try:
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:
            pass  # Ignore cleanup errors

    def test_launcher_manager_command_execution_integration(self):
        """Test launcher manager executing commands with process tracking."""
        # Import locally to avoid pytest environment issues
        import sys
        from pathlib import Path
        from unittest.mock import patch, MagicMock

        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from tests.test_doubles import TestLauncherWorker, TestSignal
        from launcher_manager import LauncherManager, CustomLauncher

        # Create launcher manager with test config directory
        launcher_manager = LauncherManager(config_dir=self.config_dir)
        
        # Create test custom launcher
        test_launcher = CustomLauncher(
            id="test_launcher",
            name="Test Launcher", 
            command="echo 'Hello {shot_name}'",
            icon_path=""
        )
        
        # Create test launcher and add it
        launcher_manager.create_launcher(test_launcher)
        
        # Verify launcher was created
        launchers = launcher_manager.get_custom_launchers()
        assert len(launchers) == 1
        assert launchers[0].id == "test_launcher"
        assert launchers[0].name == "Test Launcher"
        
        # Track signals for integration testing
        command_started_signals = []
        command_finished_signals = []
        
        def on_command_started(launcher_id, command):
            command_started_signals.append((launcher_id, command))
            
        def on_command_finished(launcher_id, success, return_code):
            command_finished_signals.append((launcher_id, success, return_code))
        
        launcher_manager.command_started.connect(on_command_started)
        launcher_manager.command_finished.connect(on_command_finished)
        
        # Mock the LauncherWorker to use test double
        with patch('launcher_manager.LauncherWorker') as mock_worker_class:
            test_worker = TestLauncherWorker(
                launcher_id="test_launcher",
                command="echo 'Hello seq01_0010'"
            )
            mock_worker_class.return_value = test_worker
            
            # Execute launcher
            process_key = launcher_manager.execute_launcher(
                "test_launcher", 
                self.test_shot["name"]
            )
            
            # Verify process key was generated
            assert process_key is not None
            assert isinstance(process_key, str)
            
            # Start the test worker to simulate execution
            test_worker.start()
            
            # Verify signals were emitted
            assert len(command_started_signals) == 1
            assert command_started_signals[0][0] == "test_launcher"
            
            assert len(command_finished_signals) == 1
            assert command_finished_signals[0][0] == "test_launcher"
            assert command_finished_signals[0][1] is True  # Success
            assert command_finished_signals[0][2] == 0     # Return code

    def test_launcher_manager_process_tracking_integration(self):
        """Test launcher manager process tracking and cleanup."""
        import sys
        from pathlib import Path
        from unittest.mock import patch

        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from tests.test_doubles import TestLauncherWorker
        from launcher_manager import LauncherManager, CustomLauncher

        launcher_manager = LauncherManager(config_dir=self.config_dir)
        
        # Create test launcher
        test_launcher = CustomLauncher(
            id="tracking_test",
            name="Tracking Test",
            command="long_running_command {shot_name}",
            icon_path=""
        )
        launcher_manager.create_launcher(test_launcher)
        
        # Track active processes
        initial_process_count = len(launcher_manager.get_active_processes())
        
        with patch('launcher_manager.LauncherWorker') as mock_worker_class:
            test_worker = TestLauncherWorker(
                launcher_id="tracking_test",
                command="long_running_command seq01_0010"
            )
            mock_worker_class.return_value = test_worker
            
            # Execute launcher
            process_key = launcher_manager.execute_launcher(
                "tracking_test",
                self.test_shot["name"] 
            )
            
            # Verify process is tracked
            active_processes = launcher_manager.get_active_processes()
            assert len(active_processes) == initial_process_count + 1
            assert process_key in active_processes
            
            # Verify process info
            process_info = active_processes[process_key]
            assert process_info["launcher_id"] == "tracking_test"
            assert process_info["command"] == "long_running_command seq01_0010"
            assert "timestamp" in process_info
            
            # Simulate process completion
            test_worker.start()  # This completes immediately in test double
            
            # Give launcher manager time to clean up
            # In real code, cleanup happens via signal connection
            launcher_manager._cleanup_finished_process(process_key)
            
            # Verify process was cleaned up
            updated_processes = launcher_manager.get_active_processes()
            assert process_key not in updated_processes

    def test_launcher_manager_signal_emission_flow(self):
        """Test complete signal emission flow during launcher execution."""
        import sys
        from pathlib import Path
        from unittest.mock import patch

        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from tests.test_doubles import TestLauncherWorker, TestSignal
        from launcher_manager import LauncherManager, CustomLauncher

        launcher_manager = LauncherManager(config_dir=self.config_dir)
        
        # Create test launcher  
        test_launcher = CustomLauncher(
            id="signal_test",
            name="Signal Test",
            command="test_command {shot_name}",
            icon_path=""
        )
        launcher_manager.create_launcher(test_launcher)
        
        # Track all signals
        signal_events = []
        
        def track_signal(signal_name):
            def handler(*args):
                signal_events.append((signal_name, args))
            return handler
        
        launcher_manager.command_started.connect(track_signal("command_started"))
        launcher_manager.command_finished.connect(track_signal("command_finished"))
        launcher_manager.command_output.connect(track_signal("command_output"))
        
        with patch('launcher_manager.LauncherWorker') as mock_worker_class:
            test_worker = TestLauncherWorker(
                launcher_id="signal_test",
                command="test_command seq01_0010"
            )
            mock_worker_class.return_value = test_worker
            
            # Execute launcher
            process_key = launcher_manager.execute_launcher(
                "signal_test",
                self.test_shot["name"]
            )
            
            # Start worker to trigger signal flow
            test_worker.start()
            
            # Verify signal emission sequence
            signal_names = [event[0] for event in signal_events]
            
            # Should have at least started signal
            assert "command_started" in signal_names
            
            # Find command_started event
            started_event = next(event for event in signal_events if event[0] == "command_started")
            assert started_event[1][0] == "signal_test"  # launcher_id
            
            # Should have output signal
            assert "command_output" in signal_names
            
            # Should have finished signal
            assert "command_finished" in signal_names
            finished_event = next(event for event in signal_events if event[0] == "command_finished")
            assert finished_event[1][0] == "signal_test"  # launcher_id
            assert finished_event[1][1] is True          # success
            assert finished_event[1][2] == 0             # return_code

    def test_launcher_manager_concurrent_execution_integration(self):
        """Test launcher manager handling multiple concurrent executions."""
        import sys
        from pathlib import Path
        from unittest.mock import patch

        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from tests.test_doubles import TestLauncherWorker
        from launcher_manager import LauncherManager, CustomLauncher

        launcher_manager = LauncherManager(config_dir=self.config_dir)
        
        # Create multiple test launchers
        launcher1 = CustomLauncher(
            id="concurrent_1",
            name="Concurrent 1", 
            command="task1 {shot_name}",
            icon_path=""
        )
        launcher2 = CustomLauncher(
            id="concurrent_2",
            name="Concurrent 2",
            command="task2 {shot_name}", 
            icon_path=""
        )
        
        launcher_manager.create_launcher(launcher1)
        launcher_manager.create_launcher(launcher2)
        
        test_workers = {}
        
        def create_test_worker(*args, **kwargs):
            launcher_id = kwargs.get('launcher_id') or args[0]
            worker = TestLauncherWorker(launcher_id=launcher_id, command=f"task {launcher_id}")
            test_workers[launcher_id] = worker
            return worker
        
        with patch('launcher_manager.LauncherWorker', side_effect=create_test_worker):
            # Execute both launchers concurrently
            process_key1 = launcher_manager.execute_launcher("concurrent_1", self.test_shot["name"])
            process_key2 = launcher_manager.execute_launcher("concurrent_2", self.test_shot["name"])
            
            # Verify both processes are tracked
            active_processes = launcher_manager.get_active_processes()
            assert process_key1 in active_processes
            assert process_key2 in active_processes
            
            # Verify process separation
            assert active_processes[process_key1]["launcher_id"] == "concurrent_1"
            assert active_processes[process_key2]["launcher_id"] == "concurrent_2"
            
            # Start both workers
            test_workers["concurrent_1"].start()
            test_workers["concurrent_2"].start()
            
            # Verify both can run simultaneously (in test environment)
            assert not test_workers["concurrent_1"].isRunning()  # Completed
            assert not test_workers["concurrent_2"].isRunning()  # Completed

    def test_launcher_manager_persistence_integration(self):
        """Test launcher manager persistence of custom launchers."""
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from launcher_manager import LauncherManager, CustomLauncher

        # Create first launcher manager instance
        launcher_manager1 = LauncherManager(config_dir=self.config_dir)
        
        # Create test launcher
        test_launcher = CustomLauncher(
            id="persistent_test",
            name="Persistent Test",
            command="persistent_command {shot_name}",
            icon_path="/path/to/icon.png"
        )
        
        launcher_manager1.create_launcher(test_launcher)
        
        # Verify config file was created
        config_file = self.config_dir / "custom_launchers.json"
        assert config_file.exists()
        
        # Read config file directly
        with open(config_file, 'r') as f:
            config_data = json.load(f)
        
        assert "launchers" in config_data
        assert len(config_data["launchers"]) == 1
        
        launcher_data = config_data["launchers"][0]
        assert launcher_data["id"] == "persistent_test"
        assert launcher_data["name"] == "Persistent Test"
        assert launcher_data["command"] == "persistent_command {shot_name}"
        assert launcher_data["icon_path"] == "/path/to/icon.png"
        
        # Create second launcher manager instance to test loading
        launcher_manager2 = LauncherManager(config_dir=self.config_dir)
        
        # Verify launcher was loaded from config
        loaded_launchers = launcher_manager2.get_custom_launchers()
        assert len(loaded_launchers) == 1
        
        loaded_launcher = loaded_launchers[0]
        assert loaded_launcher.id == "persistent_test"
        assert loaded_launcher.name == "Persistent Test"
        assert loaded_launcher.command == "persistent_command {shot_name}"
        assert loaded_launcher.icon_path == "/path/to/icon.png"


# Allow running as standalone test
if __name__ == "__main__":
    test = TestLauncherWorkflowIntegration()
    test.setup_method()
    try:
        print("Running launcher manager command execution integration...")
        test.test_launcher_manager_command_execution_integration()
        print("✓ Launcher manager command execution passed")

        print("Running launcher manager process tracking integration...")
        test.test_launcher_manager_process_tracking_integration()
        print("✓ Launcher manager process tracking passed")

        print("Running launcher manager signal emission flow...")
        test.test_launcher_manager_signal_emission_flow()
        print("✓ Launcher manager signal emission flow passed")

        print("Running launcher manager concurrent execution integration...")
        test.test_launcher_manager_concurrent_execution_integration()
        print("✓ Launcher manager concurrent execution passed")

        print("Running launcher manager persistence integration...")
        test.test_launcher_manager_persistence_integration()
        print("✓ Launcher manager persistence passed")

        print("All launcher workflow integration tests passed!")
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        test.teardown_method()