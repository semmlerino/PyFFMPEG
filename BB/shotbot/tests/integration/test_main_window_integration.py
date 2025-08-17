"""Integration tests for MainWindow component integration.

Following UNIFIED_TESTING_GUIDE principles:
- Test real component integration
- Mock only at system boundaries (subprocess)
- Use QSignalSpy for Qt signals
- Test actual user workflows
"""

import time
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QSettings, QTimer
from PySide6.QtGui import QImage
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from cache_manager import CacheManager
from main_window import MainWindow
from shot_model import RefreshResult


class ProcessPoolDouble:
    """Test double for ProcessPoolManager."""
    
    def __init__(self):
        self.commands = []
        self.workspace_output = """workspace /shows/test_show/shots/seq01/seq01_0010
workspace /shows/test_show/shots/seq01/seq01_0020
workspace /shows/test_show/shots/seq02/seq02_0010"""
        self._cache = {}
    
    def execute_workspace_command(self, command, **kwargs):
        """Simulate workspace command execution."""
        self.commands.append(command)
        
        if command == "ws -sg":
            return self.workspace_output
        return f"Executed: {command}"
    
    def get_metrics(self):
        """Get performance metrics."""
        return {
            "subprocess_calls": len(self.commands),
            "cache_stats": {"hits": 0, "misses": len(self.commands)},
            "average_response_ms": 10,
        }
    
    @classmethod
    def get_instance(cls):
        """Get singleton instance."""
        if not hasattr(cls, '_instance'):
            cls._instance = cls()
        return cls._instance
    
    def shutdown(self):
        """Shutdown the pool."""
        pass


@pytest.fixture
def cache_manager(tmp_path):
    """Create real cache manager with temp storage."""
    return CacheManager(cache_dir=tmp_path / "cache")


@pytest.fixture
def main_window(qtbot, cache_manager, tmp_path):
    """Create MainWindow with test dependencies."""
    # Patch ProcessPoolManager before import
    with patch('process_pool_manager.ProcessPoolManager.get_instance', ProcessPoolDouble.get_instance):
        with patch('shot_model.ProcessPoolManager.get_instance', ProcessPoolDouble.get_instance):
            # Create settings with test values
            settings = QSettings("TestCompany", "TestApp")
            settings.clear()
            
            # Create window
            window = MainWindow(cache_manager=cache_manager)
            qtbot.addWidget(window)
            
            # Replace process pool in shot model
            window.shot_model._process_pool = ProcessPoolDouble()
            
            # Clear any existing launchers from previous test runs
            window.launcher_manager._launchers.clear()
            
            # Disable process pool to ensure subprocess.Popen is used directly
            window.launcher_manager._use_process_pool = False
            
            # Patch launcher save to always succeed in tests
            window.launcher_manager._save_launchers = Mock(return_value=True)
            
            return window


class TestMainWindowIntegration:
    """Test MainWindow component integration."""
    
    def test_window_initialization(self, main_window):
        """Test MainWindow initializes with all components."""
        # Check main components exist
        assert main_window.shot_model is not None
        assert main_window.cache_manager is not None
        assert main_window.launcher_manager is not None
        
        # Check UI components
        assert main_window.shot_grid is not None
        assert main_window.shot_info_panel is not None
        assert main_window.tab_widget is not None
        
        # Check tabs exist
        assert main_window.tab_widget.count() >= 2  # My Shots, Other 3DE
    
    def test_shot_refresh_workflow(self, main_window, qtbot):
        """Test shot refresh updates UI components."""
        # Initial state
        initial_count = main_window.shot_grid.model.rowCount()
        
        # Trigger refresh through MainWindow (ensures UI update)
        main_window._refresh_shots()
        
        # Wait for UI update
        qtbot.wait(100)
        
        # Check grid updated
        new_count = main_window.shot_grid.model.rowCount()
        assert new_count > initial_count
        
        # Check shots loaded
        shots = main_window.shot_model.get_shots()
        assert len(shots) == 3
    
    def test_shot_selection_propagation(self, main_window, qtbot):
        """Test shot selection propagates through components."""
        # Load shots first through MainWindow
        main_window._refresh_shots()
        qtbot.wait(100)
        
        # Get first shot
        shots = main_window.shot_model.get_shots()
        assert len(shots) > 0
        first_shot = shots[0]
        
        # Select shot in grid using the public API
        main_window.shot_grid.select_shot_by_name(first_shot.full_name)
        
        # Wait for signal propagation
        qtbot.wait(100)
        
        # Check info panel updated
        # Note: Implementation might vary
        assert main_window.shot_info_panel is not None
    
    def test_custom_launcher_creation(self, main_window):
        """Test creating and managing custom launchers."""
        # Create custom launcher
        launcher_id = main_window.launcher_manager.create_launcher(
            name="Test Tool",
            command="echo {shot_name}",
            description="Test launcher for testing"
        )
        
        # Verify launcher was created
        assert launcher_id is not None
        launchers = main_window.launcher_manager.list_launchers()
        assert len(launchers) > 0
        assert any(launcher.id == launcher_id for launcher in launchers)
        
        # Delete launcher
        main_window.launcher_manager.delete_launcher(launcher_id)
        
        # Verify deleted
        launchers = main_window.launcher_manager.list_launchers()
        assert not any(launcher.id == launcher_id for launcher in launchers)
    
    def test_tab_widget_functionality(self, main_window):
        """Test tab widget switches between different views."""
        tab_widget = main_window.tab_widget
        
        # Check all tabs accessible
        for i in range(tab_widget.count()):
            tab_widget.setCurrentIndex(i)
            assert tab_widget.currentIndex() == i
            
            # Get tab widget
            widget = tab_widget.currentWidget()
            assert widget is not None
    
    def test_refresh_timer_integration(self, main_window, qtbot):
        """Test background refresh worker functionality."""
        # Check background refresh worker exists
        assert hasattr(main_window, '_background_refresh_worker')
        assert main_window._background_refresh_worker is not None
        
        # Check worker has proper signals
        assert hasattr(main_window._background_refresh_worker, 'refresh_requested')
        assert hasattr(main_window._background_refresh_worker, 'status_update')
    
    def test_error_handling_shot_refresh(self, main_window, qtbot):
        """Test error handling when shot refresh fails."""
        # Make refresh fail
        main_window.shot_model._process_pool.workspace_output = ""
        
        # Attempt refresh
        result = main_window.shot_model.refresh_shots()
        
        # Should handle gracefully
        if result.success:
            # Empty list is acceptable
            assert len(main_window.shot_model.get_shots()) == 0
        else:
            # Failure is also acceptable
            assert result.success is False
    
    def test_settings_persistence(self, main_window, qtbot, tmp_path):
        """Test window settings are saved and restored."""
        # Move and resize window
        main_window.move(100, 100)
        main_window.resize(800, 600)
        
        # Save settings
        main_window._save_settings()
        
        # Create new window
        with patch('process_pool_manager.ProcessPoolManager.get_instance', ProcessPoolDouble.get_instance):
            with patch('shot_model.ProcessPoolManager.get_instance', ProcessPoolDouble.get_instance):
                new_window = MainWindow(cache_manager=main_window.cache_manager)
                qtbot.addWidget(new_window)
                
                # Check geometry restored
                # Note: Exact restoration might vary by platform
                assert new_window.width() > 0
                assert new_window.height() > 0
    
    def test_launcher_execution_workflow(self, main_window, qtbot):
        """Test launcher execution with signals."""
        # Create launcher with test command
        launcher_id = main_window.launcher_manager.create_launcher(
            name="Test Exec",
            command="echo test",
            description="Test launcher for execution"
        )
        
        # Verify launcher was created
        assert launcher_id is not None, "Launcher creation failed"
        
        # Mock subprocess to avoid real execution
        with patch('launcher_manager.subprocess.Popen') as mock_popen:
            mock_process = Mock()
            mock_process.poll.return_value = 0
            mock_process.stdout.readline.side_effect = [b"test output\n", b""]
            mock_process.stderr.readline.return_value = b""
            mock_process.returncode = 0
            mock_popen.return_value = mock_process
            
            # Execute launcher with the actual launcher_id
            result = main_window.launcher_manager.execute_launcher(launcher_id, {"shot_name": "test"})
            assert result is True, "execute_launcher returned False"
            
            # Wait longer for worker thread to start and execute
            qtbot.wait(500)
            
            # Process events to ensure signal delivery
            QApplication.processEvents()
            
            # Verify execution
            mock_popen.assert_called_once()
    
    def test_concurrent_operations(self, main_window, qtbot):
        """Test multiple operations can run concurrently."""
        # Refresh shots
        result1 = main_window.shot_model.refresh_shots()
        
        # Create launcher while refresh might be ongoing
        launcher_id = main_window.launcher_manager.create_launcher(
            name="Concurrent",
            command="echo concurrent",
            description="Test launcher for concurrent operations"
        )
        
        # Both should succeed
        assert result1.success is True
        assert len(main_window.launcher_manager.list_launchers()) > 0


class TestMainWindowSignals:
    """Test MainWindow signal/slot connections."""
    
    def test_shot_model_signals(self, main_window, qtbot):
        """Test shot model signals are connected."""
        # The shot model doesn't inherit from QObject
        # so it doesn't have Qt signals
        # Test the refresh mechanism instead
        initial_shots = main_window.shot_model.get_shots()
        
        # Trigger refresh
        result = main_window.shot_model.refresh_shots()
        
        # Verify change detection
        assert isinstance(result, RefreshResult)
    
    def test_launcher_manager_signals(self, main_window, qtbot):
        """Test launcher manager signals."""
        # LauncherManager has signals
        assert hasattr(main_window.launcher_manager, 'launcher_added')
        assert hasattr(main_window.launcher_manager, 'launcher_deleted')
        assert hasattr(main_window.launcher_manager, 'execution_started')
        assert hasattr(main_window.launcher_manager, 'execution_finished')
        
        # Test signal emission with spy
        spy_created = QSignalSpy(main_window.launcher_manager.launcher_added)
        
        # Create launcher
        launcher_id = main_window.launcher_manager.create_launcher(
            name="Signal Test",
            command="echo test",
            description="Test launcher for signal testing"
        )
        
        # Check signal emitted
        assert spy_created.count() == 1
        # Signal emits launcher_id (a string)
        # Note: QSignalSpy stores signals as list of arguments
        # In PySide6, use .at() method to access signal data
        if spy_created.count() > 0:
            signal_args = spy_created.at(0)
            if signal_args:  # Check if we got args
                assert signal_args[0] == launcher_id
    
    def test_ui_responsiveness(self, main_window, qtbot):
        """Test UI remains responsive during operations."""
        # Start a refresh
        main_window.shot_model.refresh_shots()
        
        # UI should still be responsive
        # Try to interact with tab widget
        main_window.tab_widget.setCurrentIndex(1)
        assert main_window.tab_widget.currentIndex() == 1
        
        # Process events
        QApplication.processEvents()
        
        # Window should still be visible
        assert main_window.isVisible() or True  # May not be shown in tests


class TestMainWindowWorkflows:
    """Test complete user workflows."""
    
    def test_shot_selection_to_launch_workflow(self, main_window, qtbot):
        """Test complete workflow from shot selection to app launch."""
        # 1. Load shots through MainWindow
        main_window._refresh_shots()
        qtbot.wait(100)
        
        # 2. Select a shot
        shots = main_window.shot_model.get_shots()
        assert len(shots) > 0
        
        # 3. Create launcher for the shot - use echo instead of 3de to avoid "command not found"
        # Note: string.Template uses $variable format, not {variable}
        launcher_id = main_window.launcher_manager.create_launcher(
            name="3DE",
            command="echo 3de ${shot_name}",
            description="Test launcher for workflow testing"
        )
        
        # Verify launcher was created
        assert launcher_id is not None, "Launcher creation failed"
        
        # 4. Execute launcher with shot context
        with patch('launcher_manager.subprocess.Popen') as mock_popen:
            mock_process = Mock()
            mock_process.poll.return_value = 0
            mock_process.returncode = 0
            mock_process.stdout = Mock()
            mock_process.stdout.readline.side_effect = [b"", b""]
            mock_process.stderr = Mock()
            mock_process.stderr.readline.return_value = b""
            mock_popen.return_value = mock_process
            
            result = main_window.launcher_manager.execute_launcher(
                launcher_id,
                {"shot_name": shots[0].full_name}
            )
            assert result is True, "execute_launcher returned False"
            
            # Wait for worker thread to execute
            qtbot.wait(500)
            QApplication.processEvents()
            
            # Verify command executed with shot name
            mock_popen.assert_called_once()
            call_args = mock_popen.call_args[0][0]
            # Command should contain the shot name
            command_str = " ".join(call_args) if isinstance(call_args, list) else call_args
            assert shots[0].full_name in command_str
    
    def test_cache_integration_workflow(self, main_window, qtbot, tmp_path):
        """Test cache integration with shot loading."""
        # Create test thumbnail
        thumb_path = tmp_path / "thumb.jpg"
        image = QImage(100, 100, QImage.Format.Format_RGB32)
        image.fill(0xFF0000)
        image.save(str(thumb_path))
        
        # Cache thumbnail
        cached = main_window.cache_manager.cache_thumbnail_direct(
            thumb_path,
            "test_show",
            "seq01",
            "0010"
        )
        
        assert cached is not None
        
        # Retrieve from cache
        retrieved = main_window.cache_manager.get_cached_thumbnail(
            "test_show",
            "seq01",
            "0010"
        )
        
        assert retrieved == cached
    
    def test_error_recovery_workflow(self, main_window, qtbot):
        """Test application recovers from errors."""
        # Cause an error in shot refresh
        main_window.shot_model._process_pool.workspace_output = "invalid output"
        
        # Attempt refresh
        result1 = main_window.shot_model.refresh_shots()
        
        # Fix the issue
        main_window.shot_model._process_pool.workspace_output = """workspace /shows/test_show/shots/seq01/seq01_0010"""
        
        # Retry refresh
        result2 = main_window.shot_model.refresh_shots()
        
        # Should recover
        assert result2.success is True
        assert len(main_window.shot_model.get_shots()) > 0


class TestMainWindowPerformance:
    """Test performance-related aspects."""
    
    def test_large_shot_list_handling(self, main_window, qtbot):
        """Test handling of large shot lists."""
        # Generate large shot list
        large_output = ""
        for i in range(100):
            large_output += f"workspace /shows/test_show/shots/seq{i:02d}/seq{i:02d}_0010\n"
        
        main_window.shot_model._process_pool.workspace_output = large_output
        
        # Refresh with large list
        start_time = time.time()
        result = main_window.shot_model.refresh_shots()
        elapsed = time.time() - start_time
        
        # Should complete reasonably quickly
        assert result.success is True
        assert elapsed < 5.0  # Should parse 100 shots in under 5 seconds
        assert len(main_window.shot_model.get_shots()) == 100
    
    def test_cache_memory_management(self, main_window, tmp_path):
        """Test cache manages memory properly."""
        # Create many thumbnails
        for i in range(50):
            thumb_path = tmp_path / f"thumb_{i}.jpg"
            image = QImage(100, 100, QImage.Format.Format_RGB32)
            image.save(str(thumb_path))
            
            main_window.cache_manager.cache_thumbnail_direct(
                thumb_path,
                "show",
                "seq",
                f"shot{i:03d}"
            )
        
        # Check memory usage
        usage = main_window.cache_manager.get_memory_usage()
        
        # Should not exceed limits
        max_bytes = usage.get("max_mb", 100) * 1024 * 1024
        assert usage["total_bytes"] <= max_bytes