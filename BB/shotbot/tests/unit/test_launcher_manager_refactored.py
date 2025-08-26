"""Refactored launcher_manager tests following UNIFIED_TESTING_GUIDE best practices.

This file demonstrates proper testing patterns:
- Uses real LauncherManager components with minimal test doubles
- Tests behavior through state changes and signal emissions  
- Uses real Qt components where possible
- Only uses test doubles for controlled testing scenarios
- No complex injection or mocking frameworks

Follows the principle: test real components with controlled dependencies.
"""

import tempfile
from pathlib import Path

import pytest
from PySide6.QtTest import QSignalSpy

# Import real classes to test
from launcher_manager import (
    CustomLauncher,
    LauncherConfig,
    LauncherManager,
    LauncherTerminal,
    LauncherValidation,
)
from shot_model import Shot

pytestmark = [pytest.mark.unit, pytest.mark.qt]


# =============================================================================
# TEST FIXTURES AND HELPERS
# =============================================================================

@pytest.fixture
def temp_config_dir():
    """Create temporary directory for configuration."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir

@pytest.fixture
def test_shot():
    """Create test shot for variable substitution."""
    return Shot("testshow", "seq01", "shot001", "/shows/testshow")

@pytest.fixture
def launcher_config(temp_config_dir):
    """Create LauncherConfig for testing."""
    return LauncherConfig(temp_config_dir)

@pytest.fixture  
def launcher_manager(temp_config_dir):
    """Create LauncherManager for testing."""
    return LauncherManager(temp_config_dir)


# =============================================================================
# BEHAVIOR-FOCUSED TEST CLASSES
# =============================================================================

class TestLauncherManagerBasicOperations:
    """Test LauncherManager core functionality with real components."""
    
    def test_launcher_creation_and_retrieval(self, launcher_manager):
        """Test creating and retrieving launchers."""
        # Create launcher
        launcher_id = launcher_manager.create_launcher(
            "Test App", 
            "echo hello", 
            "Test launcher"
        )
        
        # Should return valid ID
        assert launcher_id is not None
        assert isinstance(launcher_id, str)
        
        # Should be retrievable
        launcher = launcher_manager.get_launcher(launcher_id)
        assert launcher is not None
        assert launcher.name == "Test App"
        assert launcher.command == "echo hello"
        assert launcher.description == "Test launcher"
        
    def test_launcher_list_operations(self, launcher_manager):
        """Test listing and counting launchers."""
        # Initially empty
        assert len(launcher_manager.list_launchers()) == 0
        
        # Add launchers
        id1 = launcher_manager.create_launcher("App 1", "echo 1")
        id2 = launcher_manager.create_launcher("App 2", "echo 2")
        
        # Should list both
        launchers = launcher_manager.list_launchers()
        assert len(launchers) == 2
        
        launcher_names = [l.name for l in launchers]
        assert "App 1" in launcher_names
        assert "App 2" in launcher_names
        
    def test_launcher_deletion(self, launcher_manager):
        """Test launcher deletion."""
        # Create launcher
        launcher_id = launcher_manager.create_launcher("Delete Me", "echo delete")
        assert launcher_manager.get_launcher(launcher_id) is not None
        
        # Delete launcher  
        success = launcher_manager.delete_launcher(launcher_id)
        assert success is True
        
        # Should be gone
        assert launcher_manager.get_launcher(launcher_id) is None
        assert len(launcher_manager.list_launchers()) == 0


class TestLauncherConfigPersistence:
    """Test LauncherConfig persistence behavior with real file operations."""
    
    def test_config_save_and_load_cycle(self, launcher_config):
        """Test complete save/load cycle with real files."""
        # Create test launchers
        launchers = {
            "test1": CustomLauncher("test1", "Test 1", "Desc 1", "echo test1"),
            "test2": CustomLauncher("test2", "Test 2", "Desc 2", "echo test2"),
        }
        
        # Save configuration
        saved = launcher_config.save_launchers(launchers)
        assert saved is True
        
        # Load in same instance
        loaded = launcher_config.load_launchers()
        
        # Verify data integrity
        assert len(loaded) == 2
        assert loaded["test1"].name == "Test 1"
        assert loaded["test1"].command == "echo test1"
        assert loaded["test2"].name == "Test 2"
        assert loaded["test2"].command == "echo test2"
        
    def test_empty_config_handling(self, launcher_config):
        """Test handling of non-existent config file."""
        # Should return empty dict for non-existent file
        launchers = launcher_config.load_launchers()
        assert launchers == {}
        
    def test_corrupted_config_recovery(self, temp_config_dir):
        """Test recovery from corrupted configuration."""
        config = LauncherConfig(temp_config_dir)
        
        # Write corrupted JSON directly
        config.config_file.parent.mkdir(parents=True, exist_ok=True)
        config.config_file.write_text("{ invalid json")
        
        # Load should handle corruption gracefully
        launchers = config.load_launchers()
        assert launchers == {}
        
        # Should be able to save valid config after corruption
        new_launchers = {"test": CustomLauncher("test", "Test", "Desc", "echo test")}
        saved = config.save_launchers(new_launchers)
        assert saved is True


class TestLauncherValidation:
    """Test launcher validation behavior with real validation logic."""
    
    def test_empty_name_validation(self, launcher_manager):
        """Test that empty names are rejected."""
        # Attempt to create launcher with empty name
        launcher_id = launcher_manager.create_launcher("", "echo test")
        
        # Should reject and return None
        assert launcher_id is None
        
    def test_dangerous_command_detection(self, launcher_manager):
        """Test that dangerous commands are detected."""
        # Attempt to create launcher with dangerous command
        launcher_id = launcher_manager.create_launcher("Dangerous", "rm -rf /")
        
        # Should reject dangerous command
        assert launcher_id is None
        
    def test_valid_launcher_creation(self, launcher_manager):
        """Test that valid launchers are accepted."""
        # Create valid launcher
        launcher_id = launcher_manager.create_launcher("Valid App", "echo safe")
        
        # Should succeed
        assert launcher_id is not None
        launcher = launcher_manager.get_launcher(launcher_id)
        assert launcher.name == "Valid App"
        
    def test_variable_substitution(self, launcher_manager, test_shot):
        """Test variable substitution behavior."""
        result = launcher_manager._substitute_variables(
            "Working on $show/$sequence/$shot",
            shot=test_shot
        )
        
        # Verify substitution
        assert "testshow" in result
        assert "seq01" in result
        assert "shot001" in result


class TestLauncherSignalEmission:
    """Test launcher signal emission behavior."""
    
    def test_launcher_added_signal(self, qtbot, launcher_manager):
        """Test launcher_added signal emission."""
        # Set up signal spy
        added_spy = QSignalSpy(launcher_manager.launcher_added)
        
        # Create launcher
        launcher_id = launcher_manager.create_launcher("Test App", "echo hello")
        
        # Should emit signal
        assert added_spy.count() == 1
        assert added_spy.at(0)[0] == launcher_id
        
    def test_launcher_updated_signal(self, qtbot, launcher_manager):
        """Test launcher_updated signal emission."""
        # Create launcher first
        launcher_id = launcher_manager.create_launcher("Test App", "echo hello")
        
        # Set up signal spy
        updated_spy = QSignalSpy(launcher_manager.launcher_updated)
        
        # Update launcher
        success = launcher_manager.update_launcher(launcher_id, name="Updated App")
        
        # Should emit signal
        assert success is True
        assert updated_spy.count() == 1
        assert updated_spy.at(0)[0] == launcher_id
        
    def test_launcher_deleted_signal(self, qtbot, launcher_manager):
        """Test launcher_deleted signal emission."""
        # Create launcher first
        launcher_id = launcher_manager.create_launcher("Test App", "echo hello")
        
        # Set up signal spy
        deleted_spy = QSignalSpy(launcher_manager.launcher_deleted)
        
        # Delete launcher
        success = launcher_manager.delete_launcher(launcher_id)
        
        # Should emit signal
        assert success is True
        assert deleted_spy.count() == 1
        assert deleted_spy.at(0)[0] == launcher_id
        
    def test_validation_error_signal(self, qtbot, launcher_manager):
        """Test validation_error signal emission."""
        # Set up signal spy
        validation_spy = QSignalSpy(launcher_manager.validation_error)
        
        # Try invalid creation
        launcher_id = launcher_manager.create_launcher("", "echo test")
        
        # Should emit validation error
        assert launcher_id is None
        assert validation_spy.count() > 0


class TestLauncherExecution:
    """Test launcher execution behavior with dry run mode."""
    
    def test_dry_run_execution(self, qtbot, launcher_manager):
        """Test dry run execution doesn't actually run commands."""
        # Create launcher
        launcher_id = launcher_manager.create_launcher("Test", "echo hello")
        
        # Set up signal spy
        started_spy = QSignalSpy(launcher_manager.execution_started)
        
        # Execute in dry run mode
        success = launcher_manager.execute_launcher(launcher_id, dry_run=True)
        
        # Should succeed but not actually execute
        assert success is True
        # Should not emit execution_started in dry run
        assert started_spy.count() == 0
        
    def test_execution_with_custom_variables(self, launcher_manager):
        """Test execution with custom variable substitution."""
        # Create launcher with variables
        launcher_id = launcher_manager.create_launcher(
            "Variable Test", 
            "echo $custom_var"
        )
        
        # Test dry run with variables  
        success = launcher_manager.execute_launcher(
            launcher_id, 
            custom_vars={"custom_var": "test_value"},
            dry_run=True
        )
        
        # Should handle variable substitution
        assert success is True
        
    def test_nonexistent_launcher_execution(self, launcher_manager):
        """Test executing non-existent launcher."""
        # Try to execute non-existent launcher
        success = launcher_manager.execute_launcher("nonexistent")
        
        # Should fail gracefully
        assert success is False


class TestShotContextExecution:
    """Test execution in shot context."""
    
    def test_shot_context_variable_substitution(self, launcher_manager, test_shot):
        """Test shot variable substitution in commands."""
        # Create launcher with shot variables
        launcher_id = launcher_manager.create_launcher(
            "Shot Tool",
            "echo Working on $show/$sequence/$shot"
        )
        
        # Get the launcher
        launcher = launcher_manager.get_launcher(launcher_id)
        
        # Test variable substitution
        substituted = launcher_manager._substitute_variables(
            launcher.command, 
            shot=test_shot
        )
        
        # Verify substitution
        assert "testshow" in substituted
        assert "seq01" in substituted
        assert "shot001" in substituted
        
    def test_shot_context_dry_run(self, launcher_manager, test_shot):
        """Test dry run execution in shot context."""
        # Create launcher
        launcher_id = launcher_manager.create_launcher("Test", "echo test")
        
        # Execute dry run in shot context
        success = launcher_manager.execute_in_shot_context(
            launcher_id, 
            test_shot, 
            dry_run=True
        )
        
        # Should succeed without actual execution
        assert success is True
        
    def test_nonexistent_launcher_in_shot_context(self, launcher_manager, test_shot):
        """Test handling nonexistent launcher in shot context."""
        # Try to execute non-existent launcher
        success = launcher_manager.execute_in_shot_context(
            "nonexistent", 
            test_shot
        )
        
        # Should fail gracefully
        assert success is False


class TestLauncherUpdateOperations:
    """Test launcher update operations."""
    
    def test_launcher_update_name(self, launcher_manager):
        """Test updating launcher name."""
        # Create launcher
        launcher_id = launcher_manager.create_launcher("Old Name", "echo test")
        
        # Update name
        success = launcher_manager.update_launcher(launcher_id, name="New Name")
        assert success is True
        
        # Verify update
        launcher = launcher_manager.get_launcher(launcher_id)
        assert launcher.name == "New Name"
        assert launcher.command == "echo test"  # Should remain unchanged
        
    def test_launcher_update_command(self, launcher_manager):
        """Test updating launcher command."""
        # Create launcher
        launcher_id = launcher_manager.create_launcher("Test", "echo old")
        
        # Update command
        success = launcher_manager.update_launcher(launcher_id, command="echo new")
        assert success is True
        
        # Verify update
        launcher = launcher_manager.get_launcher(launcher_id)
        assert launcher.command == "echo new"
        assert launcher.name == "Test"  # Should remain unchanged
        
    def test_launcher_update_nonexistent(self, launcher_manager):
        """Test updating non-existent launcher."""
        # Try to update non-existent launcher
        success = launcher_manager.update_launcher("nonexistent", name="New Name")
        
        # Should fail
        assert success is False


class TestCommandValidation:
    """Test command syntax validation."""
    
    def test_valid_command_syntax(self, launcher_manager):
        """Test validation of valid command syntax."""
        # Test valid command
        valid, error = launcher_manager.validate_command_syntax("echo $show/$sequence/$shot")
        
        assert valid is True
        assert error is None
        
    def test_invalid_command_syntax(self, launcher_manager):
        """Test validation of invalid command syntax."""
        # Test command with invalid variable
        valid, error = launcher_manager.validate_command_syntax("echo $invalid_variable")
        
        assert valid is False
        assert error is not None
        assert "invalid_variable" in error.lower()
        
    def test_empty_command_validation(self, launcher_manager):
        """Test validation of empty command."""
        # Test empty command
        valid, error = launcher_manager.validate_command_syntax("")
        
        assert valid is False
        assert error is not None
        assert "empty" in error.lower()


class TestLauncherCategories:
    """Test launcher category functionality."""
    
    def test_default_category_assignment(self, launcher_manager):
        """Test default category is assigned."""
        launcher_id = launcher_manager.create_launcher("Test", "echo test")
        launcher = launcher_manager.get_launcher(launcher_id)
        
        assert launcher.category == "custom"  # Default category
        
    def test_custom_category_assignment(self, launcher_manager):
        """Test custom category assignment."""
        launcher_id = launcher_manager.create_launcher(
            "Test", 
            "echo test", 
            category="development"
        )
        launcher = launcher_manager.get_launcher(launcher_id)
        
        assert launcher.category == "development"
        
    def test_category_listing(self, launcher_manager):
        """Test listing launchers by category."""
        # Create launchers in different categories
        launcher_manager.create_launcher("App1", "echo 1", category="dev")
        launcher_manager.create_launcher("App2", "echo 2", category="dev")
        launcher_manager.create_launcher("App3", "echo 3", category="prod")
        
        # Get dev category launchers
        dev_launchers = launcher_manager.list_launchers(category="dev")
        assert len(dev_launchers) == 2
        
        # Get prod category launchers  
        prod_launchers = launcher_manager.list_launchers(category="prod")
        assert len(prod_launchers) == 1
        
    def test_get_categories(self, launcher_manager):
        """Test getting all categories."""
        # Create launchers with different categories
        launcher_manager.create_launcher("App1", "echo 1", category="dev")
        launcher_manager.create_launcher("App2", "echo 2", category="test")
        launcher_manager.create_launcher("App3", "echo 3", category="prod")
        
        categories = launcher_manager.get_categories()
        
        # Should include all categories
        assert "dev" in categories
        assert "test" in categories  
        assert "prod" in categories


class TestLauncherConfigReload:
    """Test configuration reload behavior."""
    
    def test_config_reload_success(self, qtbot, launcher_manager):
        """Test successful configuration reload."""
        # Create initial launcher
        launcher_id = launcher_manager.create_launcher("Initial", "echo initial")
        assert launcher_id is not None
        
        # Set up signal spy
        changed_spy = QSignalSpy(launcher_manager.launchers_changed)
        
        # Reload config
        success = launcher_manager.reload_config()
        
        # Should succeed and emit signal
        assert success is True
        assert changed_spy.count() == 1
        
        # Original launcher should still exist
        launcher = launcher_manager.get_launcher(launcher_id)
        assert launcher is not None
        
    def test_get_active_process_count(self, launcher_manager):
        """Test getting active process count."""
        # Initially should be 0
        count = launcher_manager.get_active_process_count()
        assert count == 0
        
    def test_get_active_process_info(self, launcher_manager):
        """Test getting active process info."""
        # Should return empty list initially
        info = launcher_manager.get_active_process_info()
        assert info == []


class TestLauncherPersistenceIntegration:
    """Test persistence behavior across manager instances."""
    
    def test_persistence_across_instances(self, temp_config_dir):
        """Test launchers persist across manager instances."""
        # Create first manager and add launcher
        manager1 = LauncherManager(temp_config_dir)
        launcher_id = manager1.create_launcher("Persistent", "echo persist")
        assert launcher_id is not None
        
        # Create second manager in same directory
        manager2 = LauncherManager(temp_config_dir)
        
        # Should load the persisted launcher
        launcher = manager2.get_launcher(launcher_id)
        assert launcher is not None
        assert launcher.name == "Persistent"
        assert launcher.command == "echo persist"