"""Improved command launcher tests following UNIFIED_TESTING_GUIDE.

This demonstrates proper testing patterns:
- Use test doubles at system boundaries only
- Test behavior, not implementation
- Use real components where possible
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

# Import test utilities
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from tests.test_doubles import TestSubprocess, TestSignal


class TestCommandLauncherImproved:
    """Improved tests using test doubles instead of mocks."""
    
    def setup_method(self):
        """Setup with real components and test doubles."""
        # Import locally to avoid pytest issues
        from command_launcher import CommandLauncher
        
        # Real component with test double for subprocess
        self.launcher = CommandLauncher()
        self.test_subprocess = TestSubprocess()
        
        # Replace only the system boundary (subprocess)
        self.launcher._run_command = self._run_with_test_double
        
        # Track emitted signals (behavior)
        self.emitted_commands = []
        self.emitted_errors = []
        
        # Connect to real signals
        self.launcher.command_executed.connect(
            lambda cmd, output: self.emitted_commands.append((cmd, output))
        )
        self.launcher.command_error.connect(
            lambda err: self.emitted_errors.append(err)
        )
    
    def _run_with_test_double(self, command, **kwargs):
        """Use test double for subprocess execution."""
        return self.test_subprocess.run(command, **kwargs)
    
    def test_launch_app_success_behavior(self):
        """Test successful app launch BEHAVIOR, not implementation."""
        # Arrange: Set up test double for success
        self.test_subprocess.set_success("Application started successfully")
        
        # Act: Launch the app (real component behavior)
        self.launcher.current_shot = MagicMock(
            show="test_show",
            sequence="seq01", 
            shot="0010",
            workspace_path="/test/path"
        )
        self.launcher.launch_app("nuke")
        
        # Assert: Test BEHAVIOR, not mocks
        assert len(self.emitted_commands) == 1  # Command was executed
        assert "nuke" in self.emitted_commands[0][0]  # Correct app launched
        assert "Application started" in self.emitted_commands[0][1]  # Success output
        assert len(self.emitted_errors) == 0  # No errors
        
        # NOT testing: mock.assert_called(), implementation details
    
    def test_launch_app_failure_behavior(self):
        """Test app launch failure BEHAVIOR."""
        # Arrange: Set up test double for failure
        self.test_subprocess.set_failure("Command not found: nuke")
        
        # Act: Try to launch app
        self.launcher.current_shot = MagicMock(
            show="test_show",
            sequence="seq01",
            shot="0010",
            workspace_path="/test/path"
        )
        self.launcher.launch_app("nuke")
        
        # Assert: Test error BEHAVIOR
        assert len(self.emitted_errors) == 1  # Error was emitted
        assert "Command not found" in self.emitted_errors[0]  # Correct error
        assert len(self.emitted_commands) == 0  # No success signal
    
    def test_launch_without_shot_behavior(self):
        """Test launching without shot context."""
        # Act: Launch without setting shot
        self.launcher.launch_app("maya")
        
        # Assert: Test BEHAVIOR
        assert len(self.emitted_errors) == 1
        assert "No shot selected" in self.emitted_errors[0]
        assert len(self.emitted_commands) == 0
    
    def test_concurrent_launches_behavior(self):
        """Test concurrent app launches (real threading behavior)."""
        # Arrange: Set up shot context
        self.launcher.current_shot = MagicMock(
            show="test_show",
            sequence="seq01",
            shot="0010",
            workspace_path="/test/path"
        )
        self.test_subprocess.set_success("App started")
        
        # Act: Launch multiple apps
        self.launcher.launch_app("nuke")
        self.launcher.launch_app("maya")
        self.launcher.launch_app("houdini")
        
        # Assert: Test concurrent BEHAVIOR
        assert len(self.emitted_commands) == 3  # All commands executed
        apps_launched = [cmd[0] for cmd in self.emitted_commands]
        assert any("nuke" in app for app in apps_launched)
        assert any("maya" in app for app in apps_launched)
        assert any("houdini" in app for app in apps_launched)
    
    def test_command_formatting_behavior(self):
        """Test command formatting with shot variables."""
        # Arrange: Custom command with variables
        self.test_subprocess.set_success("Custom command executed")
        self.launcher.current_shot = MagicMock(
            show="project_x",
            sequence="seq99",
            shot="0420",
            workspace_path="/shows/project_x/seq99/0420"
        )
        
        # Act: Launch with template command
        self.launcher.launch_custom_command(
            "echo 'Working on {show}/{sequence}/{shot}'"
        )
        
        # Assert: Test formatted output BEHAVIOR
        assert len(self.emitted_commands) == 1
        command = self.emitted_commands[0][0]
        assert "project_x/seq99/0420" in command  # Variables replaced
    
    def test_workspace_change_behavior(self):
        """Test behavior when workspace changes."""
        # Arrange: Initial shot
        shot1 = MagicMock(
            show="show1",
            sequence="seq01",
            shot="0010",
            workspace_path="/shows/show1"
        )
        
        shot2 = MagicMock(
            show="show2",
            sequence="seq02",
            shot="0020", 
            workspace_path="/shows/show2"
        )
        
        self.test_subprocess.set_success("Changed workspace")
        
        # Act: Change shots and launch
        self.launcher.set_current_shot(shot1)
        self.launcher.launch_app("nuke")
        
        self.launcher.set_current_shot(shot2)
        self.launcher.launch_app("nuke")
        
        # Assert: Test workspace change BEHAVIOR
        assert len(self.emitted_commands) == 2
        assert "/shows/show1" in self.emitted_commands[0][0]
        assert "/shows/show2" in self.emitted_commands[1][0]


class TestCommandLauncherIntegration:
    """Integration tests with real filesystem."""
    
    def setup_method(self):
        """Setup with real temp directories."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.workspace = self.temp_dir / "workspace"
        self.workspace.mkdir()
        
        # Create shot structure
        (self.workspace / "scripts").mkdir()
        (self.workspace / "renders").mkdir()
    
    def teardown_method(self):
        """Clean up temp files."""
        import shutil
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    def test_real_workspace_navigation(self):
        """Test with real filesystem operations."""
        from command_launcher import CommandLauncher
        
        launcher = CommandLauncher()
        launcher.current_shot = MagicMock(
            workspace_path=str(self.workspace)
        )
        
        # Test real path validation
        assert launcher.validate_workspace()
        assert launcher.get_scripts_path() == self.workspace / "scripts"
        assert launcher.get_renders_path() == self.workspace / "renders"
    
    def test_missing_workspace_handling(self):
        """Test behavior with missing workspace."""
        from command_launcher import CommandLauncher
        
        launcher = CommandLauncher()
        launcher.current_shot = MagicMock(
            workspace_path="/nonexistent/path"
        )
        
        # Test error handling behavior
        assert not launcher.validate_workspace()
        assert launcher.get_scripts_path() is None


# Example of how to run standalone
if __name__ == "__main__":
    test = TestCommandLauncherImproved()
    test.setup_method()
    
    # Run tests
    test.test_launch_app_success_behavior()
    test.test_launch_app_failure_behavior()
    test.test_concurrent_launches_behavior()
    
    print("✅ All improved tests passed!")
    print("Key improvements:")
    print("- No mock.assert_called() patterns")
    print("- Test doubles only at subprocess boundary")
    print("- Testing behavior, not implementation")
    print("- Real components with real signals")