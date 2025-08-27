#!/usr/bin/env python3
"""Integration tests to ensure functionality is preserved during refactoring.

These tests verify that core functionality works before, during, and after
the architecture surgery refactoring.
"""

import json
import tempfile
from pathlib import Path
from typing import Optional
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from launcher_manager import LauncherManager
from launcher.models import CustomLauncher
from shot_model import Shot


class TestLauncherRefactoringSafety:
    """Test suite ensuring launcher functionality is preserved."""

    @pytest.fixture
    def temp_config_dir(self):
        """Create temporary config directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def launcher_manager(self, temp_config_dir):
        """Create LauncherManager with temporary config."""
        return LauncherManager(config_dir=temp_config_dir)

    @pytest.fixture
    def sample_launcher(self):
        """Create a sample launcher for testing."""
        return CustomLauncher(
            id="test_launcher",
            name="Test Launcher",
            command="echo 'Testing {shot_name}'",
            description="Test launcher for refactoring safety",
            category="Test",
        )

    def test_launcher_crud_operations(self, launcher_manager, sample_launcher):
        """Verify all CRUD operations work correctly."""
        # Create
        assert launcher_manager.create_launcher(sample_launcher)
        
        # Read
        retrieved = launcher_manager.get_launcher(sample_launcher.id)
        assert retrieved is not None
        assert retrieved.name == sample_launcher.name
        assert retrieved.command == sample_launcher.command
        
        # List
        launchers = launcher_manager.list_launchers()
        assert len(launchers) > 0
        assert any(l.id == sample_launcher.id for l in launchers)
        
        # Update
        updated_launcher = CustomLauncher(
            id=sample_launcher.id,
            name="Updated Test Launcher",
            command="echo 'Updated {shot_name}'",
            description="Updated description",
            category="Test",
        )
        assert launcher_manager.update_launcher(updated_launcher)
        
        # Verify update
        retrieved_after_update = launcher_manager.get_launcher(sample_launcher.id)
        assert retrieved_after_update.name == "Updated Test Launcher"
        assert retrieved_after_update.command == "echo 'Updated {shot_name}'"
        
        # Delete
        assert launcher_manager.delete_launcher(sample_launcher.id)
        
        # Verify deletion
        assert launcher_manager.get_launcher(sample_launcher.id) is None

    def test_launcher_execution(self, launcher_manager, sample_launcher):
        """Verify launchers can execute commands."""
        # Create launcher
        launcher_manager.create_launcher(sample_launcher)
        
        # Mock subprocess to avoid actual execution
        with patch('subprocess.Popen') as mock_popen:
            mock_process = Mock()
            mock_process.poll.return_value = 0
            mock_process.returncode = 0
            mock_process.stdout.readline.return_value = b''
            mock_process.stderr.readline.return_value = b''
            mock_popen.return_value = mock_process
            
            # Execute launcher
            shot = Shot(
                show="TEST",
                sequence="seq01",
                shot="0010",
                workspace_path="/shows/TEST/seq01/0010"
            )
            
            process_id = launcher_manager.execute_launcher(
                sample_launcher.id,
                shot=shot
            )
            
            # Verify execution started
            assert process_id is not None

    def test_launcher_validation(self, launcher_manager):
        """Verify command validation works correctly."""
        # Valid commands
        valid_commands = [
            "nuke {shot_path}",
            "maya -file {shot_path}/maya/scenes/shot.ma",
            "3de {project_path}",
        ]
        
        for cmd in valid_commands:
            valid, error = launcher_manager.validate_command_syntax(cmd)
            assert valid, f"Valid command rejected: {cmd}, error: {error}"
        
        # Invalid commands (security risks)
        invalid_commands = [
            "rm -rf /",  # Dangerous
            "echo test && rm file",  # Command chaining
            "cat /etc/passwd",  # System file access
        ]
        
        for cmd in invalid_commands:
            valid, error = launcher_manager.validate_command_syntax(cmd)
            assert not valid, f"Invalid command accepted: {cmd}"

    def test_launcher_persistence(self, launcher_manager, sample_launcher, temp_config_dir):
        """Verify launcher configurations persist correctly."""
        # Create and save launcher
        launcher_manager.create_launcher(sample_launcher)
        
        # Create new manager instance with same config dir
        new_manager = LauncherManager(config_dir=temp_config_dir)
        
        # Verify launcher persisted
        loaded_launcher = new_manager.get_launcher(sample_launcher.id)
        assert loaded_launcher is not None
        assert loaded_launcher.name == sample_launcher.name
        assert loaded_launcher.command == sample_launcher.command

    def test_launcher_categories(self, launcher_manager):
        """Verify category management works."""
        # Create launchers in different categories
        categories = ["VFX", "Pipeline", "Utility"]
        
        for i, category in enumerate(categories):
            launcher = CustomLauncher(
                id=f"cat_test_{i}",
                name=f"Category Test {i}",
                command=f"echo 'Category {category}'",
                description=f"Test for {category}",
                category=category,
            )
            launcher_manager.create_launcher(launcher)
        
        # Verify categories
        retrieved_categories = launcher_manager.get_categories()
        for category in categories:
            assert category in retrieved_categories
        
        # Test filtering by category
        vfx_launchers = launcher_manager.list_launchers(category="VFX")
        assert len(vfx_launchers) >= 1
        assert all(l.category == "VFX" for l in vfx_launchers)

    def test_process_tracking(self, launcher_manager, sample_launcher):
        """Verify process tracking functionality."""
        launcher_manager.create_launcher(sample_launcher)
        
        with patch('subprocess.Popen') as mock_popen:
            # Setup mock process
            mock_process = Mock()
            mock_process.poll.return_value = None  # Still running
            mock_process.pid = 12345
            mock_popen.return_value = mock_process
            
            # Start process
            process_id = launcher_manager.execute_launcher(sample_launcher.id)
            
            # Check active process count
            assert launcher_manager.get_active_process_count() > 0
            
            # Get process info
            process_info = launcher_manager.get_active_process_info()
            assert len(process_info) > 0
            assert any(p['launcher_id'] == sample_launcher.id for p in process_info)

    def test_signal_emission(self, launcher_manager, sample_launcher, qtbot):
        """Verify Qt signals are emitted correctly."""
        launcher_manager.create_launcher(sample_launcher)
        
        # Track signal emissions
        signal_emissions = []
        
        def track_signal(signal_name):
            def handler(*args):
                signal_emissions.append((signal_name, args))
            return handler
        
        # Connect signal trackers
        launcher_manager.launcher_created.connect(track_signal("created"))
        launcher_manager.launcher_updated.connect(track_signal("updated"))
        launcher_manager.launcher_deleted.connect(track_signal("deleted"))
        
        # Create new launcher
        new_launcher = CustomLauncher(
            id="signal_test",
            name="Signal Test",
            command="echo test",
            description="Testing signals",
            category="Test",
        )
        
        launcher_manager.create_launcher(new_launcher)
        assert ("created", (new_launcher.id,)) in signal_emissions
        
        # Update launcher
        new_launcher.name = "Updated Signal Test"
        launcher_manager.update_launcher(new_launcher)
        assert ("updated", (new_launcher.id,)) in signal_emissions
        
        # Delete launcher
        launcher_manager.delete_launcher(new_launcher.id)
        assert ("deleted", (new_launcher.id,)) in signal_emissions


class TestMainWindowRefactoringSafety:
    """Test suite ensuring main window functionality is preserved."""

    @pytest.fixture
    def app(self, qapp):
        """Ensure QApplication exists."""
        return qapp

    def test_ui_initialization(self, app, qtbot):
        """Verify UI initializes without errors."""
        from main_window import MainWindow
        
        # Create window
        window = MainWindow()
        qtbot.addWidget(window)
        
        # Verify basic structure
        assert window.windowTitle() == "ShotBot"
        assert window.tab_widget is not None
        assert window.menuBar() is not None
        assert window.statusBar() is not None

    def test_tab_creation(self, app, qtbot):
        """Verify all tabs are created."""
        from main_window import MainWindow
        
        window = MainWindow()
        qtbot.addWidget(window)
        
        # Check tab count
        assert window.tab_widget.count() >= 3  # At least 3 tabs
        
        # Check tab names
        tab_titles = [
            window.tab_widget.tabText(i) 
            for i in range(window.tab_widget.count())
        ]
        
        assert "My Shots" in tab_titles
        assert "Other 3DE scenes" in tab_titles

    def test_menu_structure(self, app, qtbot):
        """Verify menu structure is preserved."""
        from main_window import MainWindow
        
        window = MainWindow()
        qtbot.addWidget(window)
        
        # Get menu bar
        menubar = window.menuBar()
        
        # Check for expected menus
        menu_titles = [action.text() for action in menubar.actions()]
        
        # Basic menus should exist
        assert any("File" in title for title in menu_titles)
        assert any("Help" in title for title in menu_titles)

    def test_signal_connections(self, app, qtbot):
        """Verify critical signal-slot connections work."""
        from main_window import MainWindow
        
        with patch('main_window.ShotModel') as mock_model_class:
            # Create mock shot model
            mock_model = Mock()
            mock_model.shots_updated = Signal()
            mock_model.refresh_shots.return_value = (True, False)
            mock_model_class.return_value = mock_model
            
            window = MainWindow()
            qtbot.addWidget(window)
            
            # Verify model created
            assert window.shot_model is not None


class TestCombinedIntegration:
    """Test launcher and main window work together."""

    def test_launcher_execution_from_ui(self, qapp, qtbot):
        """Verify launchers can be executed from UI context."""
        from main_window import MainWindow
        
        with patch('subprocess.Popen'):
            window = MainWindow()
            qtbot.addWidget(window)
            
            # Get launcher manager
            launcher_manager = window.launcher_manager
            
            # Create test launcher
            launcher = CustomLauncher(
                id="ui_test",
                name="UI Test Launcher",
                command="echo 'UI Test'",
                description="Testing UI integration",
                category="Test",
            )
            
            # Create launcher through UI's manager
            assert launcher_manager.create_launcher(launcher)
            
            # Verify it appears in list
            launchers = launcher_manager.list_launchers()
            assert any(l.id == "ui_test" for l in launchers)


def test_import_compatibility():
    """Verify all imports still work after refactoring."""
    # These imports should not fail
    from launcher_manager import LauncherManager
    from launcher.models import (
        CustomLauncher,
        LauncherValidation,
        LauncherTerminal,
        LauncherEnvironment,
    )
    
    # Verify classes can be instantiated
    manager = LauncherManager()
    launcher = CustomLauncher(
        id="import_test",
        name="Import Test",
        command="echo test",
        description="Test",
        category="Test",
    )
    
    assert manager is not None
    assert launcher is not None