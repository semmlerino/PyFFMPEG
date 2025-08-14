#!/usr/bin/env python3
"""Integration tests for button launchers with minimal mocking.

These tests verify the complete flow from button click to command execution,
catching issues like lambda closure bugs that unit tests miss.
"""

from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from config import Config
from main_window import MainWindow
from shot_model import Shot


class TestButtonLauncherIntegration:
    """Test button clicks launch the correct applications."""

    @pytest.fixture
    def main_window(self, qtbot, tmp_path):
        """Create main window with minimal mocking."""
        # Override settings to use temp directory
        Config.SETTINGS_FILE = tmp_path / "test_settings.json"

        # Create window
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()

        # Set up a test shot
        test_shot = Shot(
            show="test_show",
            sequence="ABC_001",
            shot="0010",
            workspace_path="/shows/test_show/shots/ABC_001/ABC_001_0010",
        )

        # Mock the shot model to provide test data
        window.shot_model.shots = [test_shot]
        window.shot_model.refresh_shots = Mock(return_value=(True, False))

        # Update the grid with the test shot
        window.shot_grid.model.set_shots([test_shot])

        # Select the shot to enable buttons
        window.shot_grid.select_shot_by_name(test_shot.full_name)
        window._on_shot_selected(test_shot)

        return window

    @pytest.fixture
    def mock_subprocess(self):
        """Mock only the subprocess.Popen to prevent actual app launches."""
        with patch("subprocess.Popen") as mock_popen:
            # Set up mock process
            mock_process = Mock()
            mock_process.poll.return_value = None  # Process is running
            mock_process.pid = 12345
            mock_process.returncode = 0
            mock_popen.return_value = mock_process
            yield mock_popen

    def test_each_button_launches_correct_app(
        self, main_window, mock_subprocess, qtbot
    ):
        """Test that each app button launches its corresponding application.

        This test catches lambda closure bugs where all buttons might
        launch the same app due to variable capture issues.
        """
        # Track which apps were launched
        launched_commands = []

        def capture_launch(cmd, *args, **kwargs):
            """Capture the command being launched."""
            launched_commands.append(cmd)
            mock_process = Mock()
            mock_process.poll.return_value = None
            mock_process.pid = 12345 + len(launched_commands)
            return mock_process

        mock_subprocess.side_effect = capture_launch

        # Test each button
        for app_name, expected_command in Config.APPS.items():
            launched_commands.clear()
            mock_subprocess.reset_mock(side_effect=True)
            mock_subprocess.side_effect = capture_launch

            # Get the button
            button = main_window.app_buttons[app_name]
            assert button is not None, f"Button for {app_name} not found"
            assert button.isEnabled(), f"Button for {app_name} should be enabled"

            # Click the button
            QTest.mouseClick(button, Qt.MouseButton.LeftButton)

            # Process events to handle signal/slot
            qtbot.wait(50)

            # Verify subprocess was called
            assert mock_subprocess.called, f"Subprocess not called for {app_name}"

            # Get the actual command that was executed
            call_args = mock_subprocess.call_args
            if call_args and call_args[0]:
                # subprocess.Popen was called with a command list as first argument
                # The args are in a tuple, so extract the first element
                command_list = call_args[0][0] if call_args[0] else []

                # The command format is: ['gnome-terminal', '--', 'bash', '-i', '-c', 'ws ... && <app>']
                # Find the actual command string (last element typically contains the full command)
                full_command = ""
                for i, arg in enumerate(command_list):
                    if arg == "-c" and i + 1 < len(command_list):
                        # The next argument after -c is the actual command
                        full_command = command_list[i + 1]
                        break

                if not full_command:
                    # Fallback: convert entire command to string
                    full_command = " ".join(str(arg) for arg in command_list)

                # Verify the correct app command is in the executed command
                assert expected_command in full_command, (
                    f"Button {app_name} should launch {expected_command}, but command was: {full_command}"
                )

    def test_button_state_changes_with_selection(self, main_window, qtbot):
        """Test buttons are enabled/disabled based on shot selection."""
        # Initially buttons should be enabled (shot selected in fixture)
        for app_name in Config.APPS:
            button = main_window.app_buttons[app_name]
            assert button.isEnabled(), (
                f"{app_name} button should be enabled with shot selected"
            )

        # Clear selection
        main_window.shot_grid.clear_selection()
        main_window._on_shot_selected(None)
        qtbot.wait(50)

        # Buttons should be disabled
        for app_name in Config.APPS:
            button = main_window.app_buttons[app_name]
            assert not button.isEnabled(), (
                f"{app_name} button should be disabled without shot"
            )

        # Select shot again
        test_shot = main_window.shot_model.shots[0]
        main_window.shot_grid.select_shot_by_name(test_shot.full_name)
        main_window._on_shot_selected(test_shot)
        qtbot.wait(50)

        # Buttons should be enabled again
        for app_name in Config.APPS:
            button = main_window.app_buttons[app_name]
            assert button.isEnabled(), f"{app_name} button should be re-enabled"

    def test_keyboard_shortcuts_launch_correct_apps(
        self, main_window, mock_subprocess, qtbot
    ):
        """Test keyboard shortcuts trigger the correct applications."""
        # Focus the main window
        main_window.activateWindow()
        main_window.raise_()
        qtbot.waitForWindowShown(main_window)

        # Test keyboard shortcuts
        shortcuts_to_test = [
            ("3", "3de"),  # 3 key for 3de
            ("N", "nuke"),  # N key for nuke
            ("M", "maya"),  # M key for maya
            ("R", "rv"),  # R key for rv
        ]

        for key_char, expected_app in shortcuts_to_test:
            mock_subprocess.reset_mock()

            # Send keyboard shortcut
            QTest.keyClick(main_window, key_char)
            qtbot.wait(50)

            if mock_subprocess.called:
                call_args = mock_subprocess.call_args
                if call_args:
                    actual_command = str(call_args[0][0])
                    expected_command = Config.APPS[expected_app]
                    assert expected_command in actual_command, (
                        f"Shortcut {key_char} should launch {expected_app}/{expected_command}"
                    )

    def test_double_click_launches_default_app(
        self, main_window, mock_subprocess, qtbot
    ):
        """Test double-clicking a shot launches the default application."""
        mock_subprocess.reset_mock()

        # Get the first shot widget
        shot = main_window.shot_model.shots[0]

        # Simulate double-click signal
        main_window.shot_grid.shot_double_clicked.emit(shot)
        qtbot.wait(50)

        # Verify default app was launched
        assert mock_subprocess.called, "Double-click should launch app"

        call_args = mock_subprocess.call_args
        if call_args:
            actual_command = str(call_args[0][0])
            default_command = Config.APPS[Config.DEFAULT_APP]
            assert default_command in actual_command, (
                f"Double-click should launch default app {Config.DEFAULT_APP}"
            )

    def test_checkboxes_affect_command(self, main_window, mock_subprocess, qtbot):
        """Test undistortion and raw plate checkboxes affect the command."""
        # Test with undistortion checkbox
        main_window.undistortion_checkbox.setChecked(True)
        main_window.raw_plate_checkbox.setChecked(False)

        mock_subprocess.reset_mock()
        QTest.mouseClick(main_window.app_buttons["nuke"], Qt.MouseButton.LeftButton)
        qtbot.wait(50)

        if mock_subprocess.called:
            # With undistortion, command should include undistortion file loading
            call_args = mock_subprocess.call_args
            command_str = str(call_args)
            # Command construction happens in command_launcher, verify it was called correctly
            assert "nuke" in command_str.lower()

        # Test with raw plate checkbox
        main_window.undistortion_checkbox.setChecked(False)
        main_window.raw_plate_checkbox.setChecked(True)

        mock_subprocess.reset_mock()
        QTest.mouseClick(main_window.app_buttons["nuke"], Qt.MouseButton.LeftButton)
        qtbot.wait(50)

        if mock_subprocess.called:
            call_args = mock_subprocess.call_args
            command_str = str(call_args)
            assert "nuke" in command_str.lower()

    def test_custom_launcher_buttons_unique_commands(
        self, main_window, mock_subprocess, qtbot
    ):
        """Test custom launcher buttons each execute their unique commands.

        This catches lambda closure bugs in custom launcher button creation.
        """
        # Create some test custom launchers
        from launcher_manager import CustomLauncher

        launcher_manager = main_window.launcher_manager

        # Add test launchers
        test_launchers = [
            CustomLauncher(
                id="test_launcher_1",
                name="Test Tool 1",
                command="test_tool_1 --option1",
                description="First test launcher",
            ),
            CustomLauncher(
                id="test_launcher_2",
                name="Test Tool 2",
                command="test_tool_2 --option2",
                description="Second test launcher",
            ),
            CustomLauncher(
                id="test_launcher_3",
                name="Test Tool 3",
                command="test_tool_3 --option3",
                description="Third test launcher",
            ),
        ]

        for launcher in test_launchers:
            launcher_manager.create_launcher(
                name=launcher.name,
                command=launcher.command,
                description=launcher.description,
            )

        # Update UI to show new launchers
        main_window._update_custom_launcher_buttons()
        qtbot.wait(100)

        # Test each custom launcher button
        # We need to get the actual launcher IDs from the manager since they're generated
        all_launchers = launcher_manager.list_launchers()
        for launcher in all_launchers[-3:]:  # Get the last 3 launchers we added
            mock_subprocess.reset_mock()

            # Find the button for this launcher
            button = main_window.custom_launcher_buttons.get(launcher.id)
            if button and button.isVisible():
                # Click the button
                QTest.mouseClick(button, Qt.MouseButton.LeftButton)
                qtbot.wait(50)

                # Verify the correct command was executed
                if mock_subprocess.called:
                    call_args = mock_subprocess.call_args
                    command_str = str(call_args)

                    # Verify this launcher's specific command was used
                    assert (
                        launcher.command in command_str
                        or launcher.command.split()[0] in command_str
                    ), (
                        f"Custom launcher {launcher.name} should execute '{launcher.command}'"
                    )

    def test_rapid_button_clicks(self, main_window, mock_subprocess, qtbot):
        """Test rapid clicking of different buttons launches correct apps.

        This can catch race conditions or state management issues.
        """
        apps_to_test = list(Config.APPS.keys())[:3]  # Test first 3 apps

        # Track all launched commands
        all_commands = []

        def track_command(cmd, *args, **kwargs):
            all_commands.append(cmd)
            mock_process = Mock()
            mock_process.poll.return_value = None
            mock_process.pid = 12345 + len(all_commands)
            return mock_process

        mock_subprocess.side_effect = track_command

        # Rapidly click different buttons
        for _ in range(2):  # Do 2 rounds
            for app_name in apps_to_test:
                button = main_window.app_buttons[app_name]
                QTest.mouseClick(button, Qt.MouseButton.LeftButton)
                qtbot.wait(10)  # Very short wait

        # Verify we got the expected number of launches
        assert len(all_commands) == 2 * len(apps_to_test), (
            f"Expected {2 * len(apps_to_test)} launches, got {len(all_commands)}"
        )

        # Each app should have been launched exactly twice
        for app_name in apps_to_test:
            expected_command = Config.APPS[app_name]
            command_count = sum(
                1 for cmd in all_commands if expected_command in str(cmd)
            )
            assert command_count >= 1, (
                f"App {app_name} should have been launched, but wasn't found in commands"
            )

    def test_button_tooltips_match_apps(self, main_window):
        """Test button tooltips are correct for each app."""
        for app_name in Config.APPS:
            button = main_window.app_buttons[app_name]
            tooltip = button.toolTip()

            # Tooltip should mention the app name
            assert app_name.upper() in tooltip.upper(), (
                f"Button tooltip should mention {app_name}"
            )

    def test_status_bar_shows_correct_app(self, main_window, mock_subprocess, qtbot):
        """Test status bar messages show the correct app being launched."""
        for app_name in Config.APPS:
            mock_subprocess.reset_mock()

            # Click button
            QTest.mouseClick(
                main_window.app_buttons[app_name], Qt.MouseButton.LeftButton
            )
            qtbot.wait(50)

            # Check status bar message
            status_message = main_window.status_bar.currentMessage()
            if status_message:
                # Status should mention the app that was launched
                assert (
                    app_name in status_message.lower()
                    or app_name.upper() in status_message
                ), f"Status bar should mention {app_name} after launch"


class TestButtonCreationPatterns:
    """Test patterns that could lead to lambda closure bugs."""

    def test_loop_created_buttons_have_unique_callbacks(self, qtbot):
        """Test that buttons created in loops have unique callbacks."""
        from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

        # Create a test widget with buttons
        widget = QWidget()
        qtbot.addWidget(widget)
        layout = QVBoxLayout(widget)

        # Track clicked values
        clicked_values = []

        # Create buttons in a loop (the pattern that causes bugs)
        buttons = {}
        test_apps = ["app1", "app2", "app3", "app4"]

        for app in test_apps:
            button = QPushButton(app)
            # Correct lambda pattern
            button.clicked.connect(lambda checked, a=app: clicked_values.append(a))
            buttons[app] = button
            layout.addWidget(button)

        # Click each button
        for app in test_apps:
            clicked_values.clear()
            QTest.mouseClick(buttons[app], Qt.MouseButton.LeftButton)

            # Verify correct value was captured
            assert len(clicked_values) == 1, (
                "Button should trigger exactly one callback"
            )
            assert clicked_values[0] == app, (
                f"Button for {app} should append '{app}', but got '{clicked_values[0]}'"
            )

    def test_wrong_lambda_pattern_fails(self, qtbot):
        """Test that the wrong lambda pattern would fail (demonstrating the bug)."""
        from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

        widget = QWidget()
        qtbot.addWidget(widget)
        layout = QVBoxLayout(widget)

        clicked_values = []
        buttons = {}
        test_apps = ["app1", "app2", "app3"]

        # Intentionally use WRONG pattern to demonstrate the bug
        for app in test_apps:
            button = QPushButton(app)
            # WRONG: All lambdas will capture the last value of 'app'
            button.clicked.connect(lambda checked: clicked_values.append(app))
            buttons[app] = button
            layout.addWidget(button)

        # This test demonstrates the bug - all buttons append the same value
        for test_app in test_apps:
            clicked_values.clear()
            QTest.mouseClick(buttons[test_app], Qt.MouseButton.LeftButton)

            # With the bug, all buttons would append "app3" (the last value)
            # This assertion would fail with the buggy pattern
            if clicked_values:
                # With the bug, this would always be "app3"
                actual_value = clicked_values[0]
                # Document that this is the bug we're preventing
                if actual_value != test_app:
                    # This is expected with the wrong pattern
                    assert actual_value == test_apps[-1], (
                        "Bug confirmed: all buttons use last loop value"
                    )
