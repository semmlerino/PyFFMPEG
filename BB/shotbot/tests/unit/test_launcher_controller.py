"""Comprehensive tests for LauncherController.

Testing the newly refactored launcher functionality extracted from MainWindow.
Following UNIFIED_TESTING_GUIDE patterns.
"""

from __future__ import annotations

# Standard library imports
from typing import Any
from unittest.mock import Mock, patch

# Third-party imports
import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMenu, QMessageBox, QStatusBar

# Local application imports
from controllers.launcher_controller import LauncherController
from shot_model import Shot
from threede_scene_model import ThreeDEScene


# Test doubles
class TestCommandLauncher(QObject):
    """Test double for CommandLauncher with real signal behavior."""

    __test__ = False  # Prevent pytest collection

    # Signals
    command_executed = Signal(str, str)  # timestamp, command
    command_error = Signal(str, str)  # timestamp, error

    def __init__(self) -> None:
        """Initialize test command launcher."""
        super().__init__()
        self.current_shot: Shot | None = None
        self.last_command: str | None = None
        self.launch_success = True  # Control test behavior
        self.executed_commands: list[tuple[str, dict]] = []

    def set_current_shot(self, shot: Shot | None) -> None:
        """Set current shot context."""
        self.current_shot = shot

    def launch_app(
        self,
        app_name: str,
        include_undistortion: bool = False,
        include_raw_plate: bool = False,
        open_latest_threede: bool = False,
        open_latest_maya: bool = False,
        open_latest_scene: bool = False,
        create_new_file: bool = False,
    ) -> bool:
        """Simulate launching an application."""
        self.last_command = f"{app_name} with options"
        self.executed_commands.append(
            (app_name, {
                "include_undistortion": include_undistortion,
                "include_raw_plate": include_raw_plate,
                "open_latest_threede": open_latest_threede,
                "open_latest_maya": open_latest_maya,
                "open_latest_scene": open_latest_scene,
                "create_new_file": create_new_file,
                "shot": self.current_shot.full_name if self.current_shot else None
            })
        )

        if self.launch_success:
            self.command_executed.emit("00:00:00", self.last_command)
        else:
            self.command_error.emit("00:00:00", f"Failed to launch {app_name}")

        return self.launch_success

    def launch_app_with_scene(self, app_name: str, scene: ThreeDEScene) -> bool:
        """Simulate launching app with 3DE scene."""
        self.last_command = f"{app_name} {scene.scene_path}"
        self.executed_commands.append(
            (app_name, {"scene": scene.scene_path})
        )

        if self.launch_success:
            self.command_executed.emit("00:00:00", self.last_command)
            return True
        else:
            self.command_error.emit("00:00:00", f"Failed to launch {app_name} with scene")
            return False

    def launch_app_with_scene_context(
        self,
        app_name: str,
        scene: ThreeDEScene,
        include_undistortion: bool = False,
        include_raw_plate: bool = False,
    ) -> bool:
        """Simulate launching app with scene context."""
        self.last_command = f"{app_name} in context of {scene.scene_path}"
        self.executed_commands.append(
            (app_name, {
                "scene_context": scene.scene_path,
                "include_undistortion": include_undistortion,
                "include_raw_plate": include_raw_plate,
            })
        )

        if self.launch_success:
            self.command_executed.emit("00:00:00", self.last_command)
            return True
        else:
            self.command_error.emit("00:00:00", "Failed with scene context")
            return False


class MockLauncherTarget(QObject):
    """Mock implementation of LauncherTarget protocol."""

    __test__ = False  # Prevent pytest collection

    def __init__(self) -> None:
        """Initialize mock launcher target."""
        super().__init__()
        self.command_launcher = TestCommandLauncher()
        self.launcher_manager: Any = Mock()  # Will be configured per test
        self.launcher_panel = Mock()
        self.log_viewer = Mock()
        self.status_bar = Mock(spec=QStatusBar)
        self.custom_launcher_menu = Mock(spec=QMenu)
        self.status_messages: list[str] = []

    def update_status(self, message: str) -> None:
        """Update status bar with a message."""
        self.status_messages.append(message)
        self.status_bar.showMessage(message)


# Fixtures
@pytest.fixture
def make_launcher_controller():
    """Factory fixture for LauncherController."""
    def _make(launcher_manager=Mock(), launch_success=True):
        target = MockLauncherTarget()
        # Always set launcher_manager - could be None, Mock, or custom value
        target.launcher_manager = launcher_manager
        target.command_launcher.launch_success = launch_success
        controller = LauncherController(target)
        return controller, target
    return _make


@pytest.fixture
def test_shot():
    """Create a test shot."""
    return Shot(
        show="TEST",
        sequence="seq01",
        shot="0010",
        workspace_path="/shows/TEST/shots/seq01/seq01_0010"
    )


@pytest.fixture
def test_scene():
    """Create a test 3DE scene."""
    from pathlib import Path
    return ThreeDEScene(
        scene_path=Path("/shows/TEST/shots/seq01/seq01_0010/3de/v001/scene.3de"),
        show="TEST",
        sequence="seq01",
        shot="0010",
        workspace_path="/shows/TEST/shots/seq01/seq01_0010",
        user="testuser",
        plate="plate_v001",
    )


# Basic functionality tests
class TestLauncherControllerBasics:
    """Test basic launcher controller functionality."""

    def test_initialization(self, make_launcher_controller):
        """Test controller initializes correctly."""
        controller, target = make_launcher_controller()

        assert controller.window == target
        assert controller._current_shot is None
        assert controller._current_scene is None
        assert controller._launcher_dialog is None

    def test_set_current_shot(self, make_launcher_controller, test_shot):
        """Test setting current shot context."""
        controller, target = make_launcher_controller()

        controller.set_current_shot(test_shot)

        assert controller._current_shot == test_shot
        assert target.command_launcher.current_shot == test_shot

    def test_set_current_shot_none(self, make_launcher_controller):
        """Test clearing current shot context."""
        controller, target = make_launcher_controller()

        controller.set_current_shot(None)

        assert controller._current_shot is None
        assert target.command_launcher.current_shot is None

    def test_set_current_scene(self, make_launcher_controller, test_scene):
        """Test setting current scene context."""
        controller, _ = make_launcher_controller()

        controller.set_current_scene(test_scene)

        assert controller._current_scene == test_scene

    def test_set_current_scene_none(self, make_launcher_controller):
        """Test clearing current scene context."""
        controller, _ = make_launcher_controller()

        controller.set_current_scene(None)

        assert controller._current_scene is None


# Application launch tests
class TestApplicationLaunching:
    """Test application launching with different contexts."""

    def test_get_launch_options_nuke(self, make_launcher_controller):
        """Test getting Nuke launch options."""
        controller, target = make_launcher_controller()

        # Mock launcher panel checkbox states
        target.launcher_panel.get_checkbox_state = Mock(side_effect=lambda app, opt: {
            ("nuke", "include_undistortion"): True,
            ("nuke", "include_raw_plate"): False,
            ("nuke", "open_latest_scene"): True,
            ("nuke", "create_new_file"): False,
        }.get((app, opt), False))

        options = controller.get_launch_options("nuke")

        assert options["include_undistortion"] is True
        assert options["include_raw_plate"] is False
        assert options["open_latest_scene"] is True
        assert options["create_new_file"] is False

    def test_get_launch_options_3de(self, make_launcher_controller):
        """Test getting 3DE launch options."""
        controller, target = make_launcher_controller()

        target.launcher_panel.get_checkbox_state = Mock(side_effect=lambda app, opt: {
            ("3de", "open_latest_threede"): True,
        }.get((app, opt), False))

        options = controller.get_launch_options("3de")

        assert options["open_latest_threede"] is True

    def test_launch_app_with_shot_context(self, make_launcher_controller, test_shot):
        """Test launching app with shot context."""
        controller, target = make_launcher_controller()
        controller.set_current_shot(test_shot)

        # Mock checkbox states
        target.launcher_panel.get_checkbox_state = Mock(return_value=False)

        controller.launch_app("nuke")

        # Verify command was issued
        assert len(target.command_launcher.executed_commands) == 1
        cmd, opts = target.command_launcher.executed_commands[0]
        assert cmd == "nuke"
        assert opts["shot"] == test_shot.full_name
        assert "Launched nuke" in target.status_messages

    def test_launch_app_with_scene_context_3de(self, make_launcher_controller, test_scene):
        """Test launching 3DE with scene context."""
        controller, target = make_launcher_controller()
        controller.set_current_scene(test_scene)

        controller.launch_app("3de")

        # Should use launch_app_with_scene for 3DE
        assert len(target.command_launcher.executed_commands) == 1
        cmd, opts = target.command_launcher.executed_commands[0]
        assert cmd == "3de"
        assert opts["scene"] == test_scene.scene_path
        assert "Launched 3de with testuser's scene" in target.status_messages

    def test_launch_app_with_scene_context_nuke(self, make_launcher_controller, test_scene):
        """Test launching Nuke with scene context (not the scene file itself)."""
        controller, target = make_launcher_controller()
        controller.set_current_scene(test_scene)

        # Mock checkbox states for Nuke options
        target.launcher_panel.get_checkbox_state = Mock(side_effect=lambda app, opt: {
            ("nuke", "include_undistortion"): True,
            ("nuke", "include_raw_plate"): True,
        }.get((app, opt), False))

        # Add launch_app_with_scene_context method to test launcher
        target.command_launcher.launch_app_with_scene_context = Mock(return_value=True)

        controller.launch_app("nuke")

        # Should use launch_app_with_scene_context for Nuke
        target.command_launcher.launch_app_with_scene_context.assert_called_once_with(
            "nuke",
            test_scene,
            True,  # include_undistortion
            True,  # include_raw_plate
        )

    def test_launch_app_failure(self, make_launcher_controller, test_shot):
        """Test handling of launch failure."""
        controller, target = make_launcher_controller(launch_success=False)
        controller.set_current_shot(test_shot)

        target.launcher_panel.get_checkbox_state = Mock(return_value=False)

        controller.launch_app("nuke")

        # Verify failure was handled
        assert "Failed to launch nuke" in target.status_messages

    def test_launch_app_priority_open_latest_over_create_new(self, make_launcher_controller, test_shot):
        """Test that open_latest_scene takes priority over create_new_file."""
        controller, target = make_launcher_controller()
        controller.set_current_shot(test_shot)

        # Both options are True, but open_latest should take priority
        target.launcher_panel.get_checkbox_state = Mock(side_effect=lambda app, opt: {
            ("nuke", "open_latest_scene"): True,
            ("nuke", "create_new_file"): True,
        }.get((app, opt), False))

        controller.launch_app("nuke")

        # Check that create_new_file was set to False in the actual call
        assert len(target.command_launcher.executed_commands) == 1
        _, opts = target.command_launcher.executed_commands[0]
        assert opts["open_latest_scene"] is True
        assert opts["create_new_file"] is False  # Should be overridden


# Custom launcher tests
class TestCustomLaunchers:
    """Test custom launcher functionality."""

    def test_execute_custom_launcher_with_shot(self, make_launcher_controller, test_shot):
        """Test executing a custom launcher with shot context."""
        controller, target = make_launcher_controller()
        controller.set_current_shot(test_shot)

        # Setup mock launcher
        mock_launcher = Mock()
        mock_launcher.id = "test_launcher"
        mock_launcher.name = "Test Launcher"
        target.launcher_manager.get_launcher = Mock(return_value=mock_launcher)
        target.launcher_manager.execute_in_shot_context = Mock(return_value=True)

        controller.execute_custom_launcher("test_launcher")

        # Verify launcher was executed
        target.launcher_manager.execute_in_shot_context.assert_called_once()
        call_args = target.launcher_manager.execute_in_shot_context.call_args
        assert call_args[0][0] == "test_launcher"
        assert call_args[0][1] == test_shot
        assert "Launched 'Test Launcher'" in target.status_messages

    def test_execute_custom_launcher_with_scene(self, make_launcher_controller, test_scene):
        """Test executing a custom launcher with scene context."""
        controller, target = make_launcher_controller()
        controller.set_current_scene(test_scene)

        # Setup mock launcher
        mock_launcher = Mock()
        mock_launcher.id = "test_launcher"
        mock_launcher.name = "Test Launcher"
        target.launcher_manager.get_launcher = Mock(return_value=mock_launcher)
        target.launcher_manager.execute_in_shot_context = Mock(return_value=True)

        controller.execute_custom_launcher("test_launcher")

        # Should create shot from scene and execute
        target.launcher_manager.execute_in_shot_context.assert_called_once()
        call_args = target.launcher_manager.execute_in_shot_context.call_args[0]
        created_shot = call_args[1]
        assert created_shot.show == test_scene.show
        assert created_shot.sequence == test_scene.sequence
        assert created_shot.shot == test_scene.shot

    def test_execute_custom_launcher_no_context(self, make_launcher_controller):
        """Test executing custom launcher without any context."""
        controller, target = make_launcher_controller()

        # No shot or scene set
        target.command_launcher.current_shot = None

        controller.execute_custom_launcher("test_launcher")

        # Should show error status
        assert "No shot or scene selected" in target.status_messages
        # Should not attempt to execute
        target.launcher_manager.execute_in_shot_context.assert_not_called()

    def test_execute_custom_launcher_not_found(self, make_launcher_controller, test_shot):
        """Test executing a custom launcher that doesn't exist."""
        controller, target = make_launcher_controller()
        controller.set_current_shot(test_shot)

        target.launcher_manager.get_launcher = Mock(return_value=None)

        controller.execute_custom_launcher("nonexistent")

        assert "Launcher not found: nonexistent" in target.status_messages
        target.launcher_manager.execute_in_shot_context.assert_not_called()

    def test_execute_custom_launcher_failure(self, make_launcher_controller, test_shot):
        """Test handling custom launcher execution failure."""
        controller, target = make_launcher_controller()
        controller.set_current_shot(test_shot)

        mock_launcher = Mock()
        mock_launcher.id = "test_launcher"
        mock_launcher.name = "Test Launcher"
        target.launcher_manager.get_launcher = Mock(return_value=mock_launcher)
        target.launcher_manager.execute_in_shot_context = Mock(return_value=False)

        controller.execute_custom_launcher("test_launcher")

        assert "Failed to launch 'Test Launcher'" in target.status_messages

    def test_update_launcher_menu_no_manager(self, make_launcher_controller):
        """Test updating launcher menu when no manager available."""
        controller, target = make_launcher_controller(launcher_manager=None)

        controller.update_launcher_menu()

        # Should clear menu but not crash
        target.custom_launcher_menu.clear.assert_called_once()
        # Should not try to list launchers since manager is None
        # The method should return early after clearing

    def test_update_launcher_menu_with_launchers(self, make_launcher_controller):
        """Test updating launcher menu with available launchers."""
        controller, target = make_launcher_controller()

        # Create mock launchers
        launcher1 = Mock()
        launcher1.id = "1"
        launcher1.name = "Launcher 1"
        launcher1.category = "tools"
        launcher1.description = "Tool launcher"

        launcher2 = Mock()
        launcher2.id = "2"
        launcher2.name = "Launcher 2"
        launcher2.category = "scripts"
        launcher2.description = "Script launcher"

        target.launcher_manager.list_launchers = Mock(return_value=[launcher1, launcher2])

        # Mock QAction creation to avoid QWidget issues
        with patch('controllers.launcher_controller.QAction') as MockQAction:
            mock_action = Mock()
            MockQAction.return_value = mock_action

            controller.update_launcher_menu()

            # Verify menu was cleared and rebuilt
            target.custom_launcher_menu.clear.assert_called_once()
            # Should create submenus for multiple categories
            assert target.custom_launcher_menu.addMenu.call_count == 2

    def test_update_launcher_menu_single_category(self, make_launcher_controller):
        """Test menu update with single category (no submenus)."""
        controller, target = make_launcher_controller()

        launcher1 = Mock()
        launcher1.id = "1"
        launcher1.name = "Launcher 1"
        launcher1.category = "custom"
        launcher1.description = "Custom launcher"

        target.launcher_manager.list_launchers = Mock(return_value=[launcher1])

        # Mock QAction creation
        with patch('controllers.launcher_controller.QAction') as MockQAction:
            mock_action = Mock()
            MockQAction.return_value = mock_action

            controller.update_launcher_menu()

            # Should add action directly, no submenu
            target.custom_launcher_menu.clear.assert_called_once()
            target.custom_launcher_menu.addAction.assert_called()

    def test_update_launcher_menu_no_launchers(self, make_launcher_controller):
        """Test menu update when no launchers available."""
        controller, target = make_launcher_controller()

        target.launcher_manager.list_launchers = Mock(return_value=[])

        # Mock QAction creation for placeholder
        with patch('controllers.launcher_controller.QAction') as MockQAction:
            mock_action = Mock()
            MockQAction.return_value = mock_action

            controller.update_launcher_menu()

            # Should add disabled placeholder
            target.custom_launcher_menu.clear.assert_called_once()
            target.custom_launcher_menu.addAction.assert_called_once()

    def test_update_custom_launcher_buttons(self, make_launcher_controller):
        """Test updating custom launcher buttons in panel."""
        controller, target = make_launcher_controller()

        launcher1 = Mock()
        launcher1.id = "1"
        launcher1.name = "Launcher 1"

        launcher2 = Mock()
        launcher2.id = "2"
        launcher2.name = "Launcher 2"

        target.launcher_manager.list_launchers = Mock(return_value=[launcher1, launcher2])

        controller.update_custom_launcher_buttons()

        target.launcher_panel.update_custom_launchers.assert_called_once_with([
            ("1", "Launcher 1"),
            ("2", "Launcher 2")
        ])

    def test_show_launcher_manager_dialog(self, make_launcher_controller):
        """Test showing launcher manager dialog."""
        controller, target = make_launcher_controller()

        # Mock the dialog import (it's imported locally in the method)
        with patch('launcher_dialog.LauncherManagerDialog') as MockDialog:
            mock_dialog = Mock()
            MockDialog.return_value = mock_dialog

            controller.show_launcher_manager()

            MockDialog.assert_called_once_with(target.launcher_manager, target)
            mock_dialog.show.assert_called_once()
            mock_dialog.raise_.assert_called_once()
            mock_dialog.activateWindow.assert_called_once()

    def test_show_launcher_manager_no_manager(self, make_launcher_controller):
        """Test showing launcher manager when using simplified launcher."""
        controller, target = make_launcher_controller(launcher_manager=None)

        with patch.object(QMessageBox, 'information') as mock_info:
            controller.show_launcher_manager()

            mock_info.assert_called_once()
            args = mock_info.call_args[0]
            assert "Custom launchers are not available" in args[2]


# Error handling tests
class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_command_error_notification_not_found(self, make_launcher_controller):
        """Test error notification for application not found."""
        controller, target = make_launcher_controller()

        with patch('controllers.launcher_controller.NotificationManager') as MockNotif:
            controller._on_command_error("12:00:00", "nuke: command not found")

            MockNotif.error.assert_called()
            call_args = MockNotif.error.call_args[0]
            assert "Application Not Found" in call_args[0]

    def test_command_error_notification_permission(self, make_launcher_controller):
        """Test error notification for permission denied."""
        controller, target = make_launcher_controller()

        with patch('controllers.launcher_controller.NotificationManager') as MockNotif:
            controller._on_command_error("12:00:00", "Permission denied: /usr/bin/app")

            MockNotif.error.assert_called()
            call_args = MockNotif.error.call_args[0]
            assert "Permission Denied" in call_args[0]

    def test_command_error_notification_no_shot(self, make_launcher_controller):
        """Test error notification for no shot selected."""
        controller, target = make_launcher_controller()

        with patch('controllers.launcher_controller.NotificationManager') as MockNotif:
            controller._on_command_error("12:00:00", "No shot selected")

            MockNotif.warning.assert_called()
            call_args = MockNotif.warning.call_args[0]
            assert "No Shot Selected" in call_args[0]

    def test_command_error_notification_generic(self, make_launcher_controller):
        """Test error notification for generic errors."""
        controller, target = make_launcher_controller()

        with patch('controllers.launcher_controller.NotificationManager') as MockNotif:
            controller._on_command_error("12:00:00", "Something went wrong")

            MockNotif.error.assert_called()
            call_args = MockNotif.error.call_args[0]
            assert "Launch Failed" in call_args[0]

    def test_launcher_started_progress(self, make_launcher_controller):
        """Test progress indication when launcher starts."""
        controller, target = make_launcher_controller()

        mock_launcher = Mock()
        mock_launcher.name = "Test Launcher"
        target.launcher_manager.get_launcher = Mock(return_value=mock_launcher)

        with patch('controllers.launcher_controller.ProgressManager') as MockProgress:
            controller._on_launcher_started("test_launcher")

            MockProgress.start_operation.assert_called_once_with("Launching Test Launcher")

    def test_launcher_finished_success(self, make_launcher_controller):
        """Test handling successful launcher completion."""
        controller, target = make_launcher_controller()

        with patch('controllers.launcher_controller.ProgressManager') as MockProgress:
            with patch('controllers.launcher_controller.NotificationManager') as MockNotif:
                controller._on_launcher_finished("test_launcher", True)

                MockProgress.finish_operation.assert_called_once_with(success=True)
                MockNotif.toast.assert_called()
                call_args = MockNotif.toast.call_args[0]
                assert "successfully" in call_args[0]

    def test_launcher_finished_failure(self, make_launcher_controller):
        """Test handling failed launcher completion."""
        controller, target = make_launcher_controller()

        with patch('controllers.launcher_controller.ProgressManager') as MockProgress:
            with patch('controllers.launcher_controller.NotificationManager') as MockNotif:
                controller._on_launcher_finished("test_launcher", False)

                MockProgress.finish_operation.assert_called_once_with(success=False)
                MockNotif.toast.assert_called()
                call_args = MockNotif.toast.call_args[0]
                assert "failed" in call_args[0]

    def test_update_launcher_menu_availability(self, make_launcher_controller):
        """Test updating launcher menu availability based on context."""
        controller, target = make_launcher_controller()

        # Create mock actions
        action1 = Mock()
        action1.menu = Mock(return_value=None)  # Regular action
        action2 = Mock()
        submenu = Mock()
        submenu.actions = Mock(return_value=[Mock(), Mock()])
        action2.menu = Mock(return_value=submenu)  # Action with submenu

        target.custom_launcher_menu.actions = Mock(return_value=[action1, action2])

        controller.update_launcher_menu_availability(True)

        # Regular action should be enabled
        action1.setEnabled.assert_called_once_with(True)
        # Submenu actions should be enabled
        for sub_action in submenu.actions():
            sub_action.setEnabled.assert_called_once_with(True)


# Simple test to verify everything is working
if __name__ == "__main__":
    pytest.main([__file__, "-v"])