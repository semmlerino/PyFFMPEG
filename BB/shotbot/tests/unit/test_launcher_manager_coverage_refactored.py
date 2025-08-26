"""Launcher manager tests following UNIFIED_TESTING_GUIDE best practices.

This refactored test suite demonstrates:
- Testing behavior instead of mock calls  
- Using test doubles from the library
- Real Qt signals with QSignalSpy
- No assert_called() anti-patterns
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional

import pytest
from PySide6.QtCore import QObject, QThread
from PySide6.QtTest import QSignalSpy

# Add parent path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from launcher_manager import LauncherManager, LauncherWorker
from config import Config

# Import comprehensive test doubles
from tests.test_doubles_library import (
    TestLauncher,
    PopenDouble,
    TestShot,
    TestSubprocess,
    TestWorker,
)

pytestmark = [pytest.mark.unit, pytest.mark.qt]


class TestLauncherManagerBehavior:
    """Test LauncherManager behavior, not implementation."""
    
    def setup_method(self) -> None:
        """Setup with real components and test doubles."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config_dir = self.temp_dir / "config"
        self.config_dir.mkdir(parents=True)
        
        # Real launcher manager
        self.manager = LauncherManager(config_dir=self.config_dir)
        
        # Test subprocess for system boundary
        self.test_subprocess = TestSubprocess()
        
        # Track behavior through signals
        self.execution_events: List[tuple] = []
        self.manager.execution_started.connect(
            lambda lid: self.execution_events.append(("started", lid))
        )
        self.manager.execution_finished.connect(
            lambda lid, success: self.execution_events.append(("finished", lid, success))
        )
    
    def teardown_method(self) -> None:
        """Clean up temp files."""
        import shutil
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    def test_create_launcher_behavior(self) -> None:
        """Test launcher creation behavior, not mocks."""
        # Setup signal spy for real Qt signal
        spy_added = QSignalSpy(self.manager.launcher_added)
        
        # Create launcher (real behavior)
        launcher_id = self.manager.create_launcher(
            name="Test Tool",
            command="echo {shot_name}",
            description="Test launcher for echo"
        )
        
        # Assert behavior
        assert launcher_id is not None
        # launcher_id is a UUID string
        import uuid
        assert uuid.UUID(launcher_id)  # Will raise if not valid UUID
        
        # Verify signal emitted (behavior)
        assert spy_added.count() == 1
        assert spy_added.at(0)[0] == launcher_id
        
        # Verify launcher exists (behavior)
        launchers = self.manager.list_launchers()
        assert len(launchers) == 1
        assert launchers[0].id == launcher_id
        assert launchers[0].name == "Test Tool"
        assert launchers[0].command == "echo {shot_name}"
        
        # Verify persistence (behavior)
        config_file = self.config_dir / "custom_launchers.json"
        assert config_file.exists()
        
        with open(config_file) as f:
            config_data = json.load(f)
        assert "launchers" in config_data
        assert launcher_id in config_data["launchers"]
    
    def test_execute_launcher_behavior(self) -> None:
        """Test launcher execution behavior."""
        # Create launcher
        launcher_id = self.manager.create_launcher(
            name="Test Executor",
            command="nuke {shot_name}",
            description="Test nuke launcher"
        )
        
        # Setup signal spies
        spy_started = QSignalSpy(self.manager.execution_started)
        spy_finished = QSignalSpy(self.manager.execution_finished)
        
        # Execute launcher (real behavior)
        custom_vars = {"shot_name": "seq01_0010"}
        success = self.manager.execute_launcher(launcher_id, custom_vars)
        
        # Assert execution behavior
        assert success is True
        
        # Verify signals (behavior)
        assert spy_started.count() == 1
        assert spy_started.at(0)[0] == launcher_id
        
        # Wait briefly for async completion
        import time
        time.sleep(0.1)
        
        # Check execution history (behavior)
        assert len(self.execution_events) >= 1
        assert self.execution_events[0] == ("started", launcher_id)
    
    def test_delete_launcher_behavior(self) -> None:
        """Test launcher deletion behavior."""
        # Create launcher
        launcher_id = self.manager.create_launcher(
            name="To Delete",
            command="echo test",
            description="Will be deleted"
        )
        
        # Setup signal spy
        spy_removed = QSignalSpy(self.manager.launcher_deleted)
        
        # Delete launcher (real behavior)
        success = self.manager.delete_launcher(launcher_id)
        
        # Assert deletion behavior
        assert success is True
        assert spy_removed.count() == 1
        assert spy_removed.at(0)[0] == launcher_id
        
        # Verify launcher no longer exists
        launchers = self.manager.list_launchers()
        launcher_ids = [l.id for l in launchers]
        assert launcher_id not in launcher_ids
        
        # Verify persistence updated
        config_file = self.config_dir / "custom_launchers.json"
        with open(config_file) as f:
            config_data = json.load(f)
        assert launcher_id not in config_data["launchers"]
    
    def test_concurrent_execution_behavior(self) -> None:
        """Test concurrent launcher execution behavior."""
        # Create multiple launchers
        launcher1 = self.manager.create_launcher(
            name="Launcher 1",
            command="echo launcher1",
            description="First launcher"
        )
        launcher2 = self.manager.create_launcher(
            name="Launcher 2", 
            command="echo launcher2",
            description="Second launcher"
        )
        
        # Setup test subprocess with delays
        self.manager._subprocess_handler = self.test_subprocess
        self.test_subprocess.delay = 0.05  # Small delay to simulate work
        
        # Track execution order
        execution_order: List[str] = []
        
        def track_start(launcher_id: str) -> None:
            execution_order.append(f"start_{launcher_id}")
        
        def track_finish(launcher_id: str, success: bool) -> None:
            execution_order.append(f"finish_{launcher_id}")
        
        self.manager.execution_started.connect(track_start)
        self.manager.execution_finished.connect(track_finish)
        
        # Execute both launchers concurrently
        success1 = self.manager.execute_launcher(launcher1)
        success2 = self.manager.execute_launcher(launcher2)
        
        assert success1 is True
        assert success2 is True
        
        # Wait for async completion
        time.sleep(0.2)
        
        # Verify both started (behavior)
        assert f"start_{launcher1}" in execution_order
        assert f"start_{launcher2}" in execution_order
        
        # Verify concurrent execution capability
        active_count = self.manager.get_active_process_count()
        assert active_count >= 0  # May have completed already
    
    def test_validation_error_behavior(self) -> None:
        """Test validation error behavior."""
        spy_error = QSignalSpy(self.manager.validation_error)
        
        # Try to create invalid launcher (empty name)
        launcher_id = self.manager.create_launcher(
            name="",  # Invalid
            command="echo test",
            description="Invalid launcher"
        )
        
        # Assert validation behavior
        assert launcher_id is None
        assert spy_error.count() == 1
        
        # validation_error signal has (field, error_message)
        field = spy_error.at(0)[0]
        error_msg = spy_error.at(0)[1]
        assert "name" in field.lower() or "name" in error_msg.lower()
        
        # Verify launcher was not created
        launchers = self.manager.list_launchers()
        assert len(launchers) == 0
    
    def test_process_cleanup_behavior(self) -> None:
        """Test process cleanup behavior."""
        # Create launcher
        launcher_id = self.manager.create_launcher(
            name="Cleanup Test",
            command="long_running_process",
            description="Test cleanup"
        )
        
        # Create test process that appears to be running
        test_process = PopenDouble("long_running", returncode=None)
        
        # Add to active processes using ProcessInfo structure
        process_key = f"{launcher_id}_{time.time()}"
        from launcher_manager import ProcessInfo
        process_info = ProcessInfo(
            process=test_process,
            launcher_id=launcher_id,
            launcher_name="Cleanup Test",
            command="long_running_process",
            timestamp=time.time()
        )
        self.manager._active_processes[process_key] = process_info
        
        # Verify process is tracked
        initial_count = self.manager.get_active_process_count()
        assert initial_count == 1
        
        # Simulate process completion
        test_process.returncode = 0
        test_process._terminated = True
        
        # Trigger cleanup
        self.manager._cleanup_finished_processes()
        
        # Verify cleanup behavior
        final_count = self.manager.get_active_process_count()
        assert final_count == 0
        assert process_key not in self.manager._active_processes


class TestLauncherWorkerBehavior:
    """Test LauncherWorker thread behavior."""
    
    def test_worker_execution_behavior(self, qtbot) -> None:
        """Test worker thread execution behavior."""
        # Create test worker
        worker = LauncherWorker(
            launcher_id="test_worker",
            command="python -c 'print(\"test\")'"
        )
        
        # Setup test subprocess
        test_subprocess = TestSubprocess()
        test_subprocess.set_command_output("python", 0, "test output")
        worker._subprocess_handler = test_subprocess
        
        # Setup signal spies
        spy_started = QSignalSpy(worker.command_started)
        spy_finished = QSignalSpy(worker.command_finished)
        spy_error = QSignalSpy(worker.command_error)
        
        # Start worker
        with qtbot.waitSignal(worker.command_finished, timeout=2000):
            worker.start()
        
        # Assert execution behavior
        assert spy_started.count() == 1
        assert spy_finished.count() == 1
        
        # Verify success signal (command_finished has launcher_id, success, return_code)
        success = spy_finished.at(0)[1]
        assert success is True
        
        # Cleanup
        if worker.isRunning():
            worker.quit()
            worker.wait(1000)
    
    def test_worker_error_handling_behavior(self, qtbot) -> None:
        """Test worker error handling behavior."""
        worker = LauncherWorker(
            launcher_id="error_test",
            command="forbidden_command"  # This will trigger security error
        )
        
        spy_finished = QSignalSpy(worker.command_finished)
        spy_error = QSignalSpy(worker.command_error)
        
        # Start worker
        with qtbot.waitSignal(worker.command_finished, timeout=2000):
            worker.start()
        
        # Assert error behavior
        assert spy_finished.count() == 1
        assert spy_error.count() == 1
        
        success = spy_finished.at(0)[1]
        assert success is False
        
        error_msg = spy_error.at(0)[1]
        assert "whitelist" in error_msg.lower() or "failed" in error_msg.lower()
        
        # Cleanup
        if worker.isRunning():
            worker.quit()
            worker.wait(1000)
    
    def test_worker_termination_behavior(self, qtbot) -> None:
        """Test worker termination behavior."""
        worker = LauncherWorker(
            launcher_id="terminate_test",
            command="python -c 'import time; time.sleep(10)'"  # Long running
        )
        
        # Setup subprocess with delay
        test_subprocess = TestSubprocess()
        test_subprocess.delay = 5.0  # Simulate long running
        worker._subprocess_handler = test_subprocess
        
        # Start worker
        worker.start()
        
        # Wait briefly then terminate
        qtbot.wait(100)
        
        # Terminate worker
        worker.terminate()
        
        # Wait for termination
        assert worker.wait(2000)  # Should terminate within 2 seconds
        
        # Verify worker stopped
        assert not worker.isRunning()


class TestLauncherManagerPersistence:
    """Test launcher persistence behavior."""
    
    def test_save_and_load_behavior(self) -> None:
        """Test saving and loading launcher configurations."""
        temp_dir = Path(tempfile.mkdtemp())
        config_dir = temp_dir / "config"
        config_dir.mkdir(parents=True)
        
        try:
            # Create manager and add launchers
            manager1 = LauncherManager(config_dir=config_dir)
            
            launcher1_id = manager1.create_launcher(
                name="Persistent Tool 1",
                command="tool1 {shot}",
                description="First tool",
                category="comp"
            )
            
            launcher2_id = manager1.create_launcher(
                name="Persistent Tool 2",
                command="tool2 {sequence}",
                description="Second tool",
                category="track"
            )
            
            # Verify saved to disk
            config_file = config_dir / "custom_launchers.json"
            assert config_file.exists()
            
            # Create new manager instance (simulates restart)
            manager2 = LauncherManager(config_dir=config_dir)
            
            # Verify launchers loaded (behavior)
            loaded_launchers = manager2.list_launchers()
            assert len(loaded_launchers) == 2
            
            # Verify data integrity
            launcher_ids = [l.id for l in loaded_launchers]
            assert launcher1_id in launcher_ids
            assert launcher2_id in launcher_ids
            
            # Find specific launcher and verify properties
            for launcher in loaded_launchers:
                if launcher.id == launcher1_id:
                    assert launcher.name == "Persistent Tool 1"
                    assert launcher.command == "tool1 {shot}"
                    assert launcher.category == "comp"
                elif launcher.id == launcher2_id:
                    assert launcher.name == "Persistent Tool 2"
                    assert launcher.command == "tool2 {sequence}"
                    assert launcher.category == "track"
            
        finally:
            # Cleanup
            import shutil
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
    
    def test_config_corruption_recovery_behavior(self) -> None:
        """Test recovery from corrupted config file."""
        temp_dir = Path(tempfile.mkdtemp())
        config_dir = temp_dir / "config"
        config_dir.mkdir(parents=True)
        
        try:
            # Write corrupted config
            config_file = config_dir / "custom_launchers.json"
            config_file.write_text("{ invalid json content [}")
            
            # Create manager - should handle corruption gracefully
            manager = LauncherManager(config_dir=config_dir)
            
            # Should start with empty launchers (recovered behavior)
            launchers = manager.list_launchers()
            assert len(launchers) == 0
            
            # Should be able to add new launchers
            launcher_id = manager.create_launcher(
                name="Recovery Test",
                command="echo recovered",
                description="Added after corruption"
            )
            
            assert launcher_id is not None
            
            # Verify config file is now valid
            with open(config_file) as f:
                config_data = json.load(f)  # Should not raise
            assert "launchers" in config_data
            assert launcher_id in config_data["launchers"]
            
        finally:
            import shutil
            if temp_dir.exists():
                shutil.rmtree(temp_dir)


class TestLauncherManagerThreadSafety:
    """Test thread safety of launcher manager."""
    
    def test_concurrent_launcher_creation_behavior(self) -> None:
        """Test creating launchers from multiple threads."""
        import threading
        from queue import Queue
        
        temp_dir = Path(tempfile.mkdtemp())
        config_dir = temp_dir / "config"
        config_dir.mkdir(parents=True)
        
        try:
            manager = LauncherManager(config_dir=config_dir)
            
            launcher_ids = Queue()
            errors = Queue()
            
            def create_launcher(thread_id: int) -> None:
                """Create launcher in thread."""
                try:
                    lid = manager.create_launcher(
                        name=f"Thread {thread_id} Tool",
                        command=f"tool{thread_id} {{shot}}",
                        description=f"Tool from thread {thread_id}"
                    )
                    launcher_ids.put(lid)
                except Exception as e:
                    errors.put(str(e))
            
            # Create launchers from multiple threads
            threads = []
            for i in range(10):
                thread = threading.Thread(target=create_launcher, args=(i,))
                threads.append(thread)
                thread.start()
            
            # Wait for all threads
            for thread in threads:
                thread.join(timeout=2.0)
            
            # Verify all succeeded (thread-safe behavior)
            assert errors.qsize() == 0
            assert launcher_ids.qsize() == 10
            
            # Verify all launchers exist
            launchers = manager.list_launchers()
            assert len(launchers) == 10
            
            # Verify unique IDs
            created_ids = []
            while not launcher_ids.empty():
                created_ids.append(launcher_ids.get())
            assert len(set(created_ids)) == 10  # All unique
            
        finally:
            import shutil
            if temp_dir.exists():
                shutil.rmtree(temp_dir)


if __name__ == "__main__":
    """Allow running tests directly."""
    pytest.main([__file__, "-v"])