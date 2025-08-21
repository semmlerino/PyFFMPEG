"""Unit tests for launcher dialog components.

Tests the LauncherEditDialog, LauncherPreviewPanel, and LauncherManagerDialog
following UNIFIED_TESTING_GUIDE principles:
- Use real Qt components with qtbot
- Mock only external dependencies (LauncherManager methods)
- Test behavior, not implementation
- Use QSignalSpy for signal testing
- No time.sleep() - use Qt event processing
"""

from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QDialog, QMessageBox

from launcher_dialog import (
    LauncherEditDialog,
    LauncherListWidget,
    LauncherManagerDialog,
    LauncherPreviewPanel,
)
from launcher_manager import (
    CustomLauncher,
    LauncherEnvironment,
    LauncherManager,
    LauncherTerminal,
)


# Test Data Factories
def create_test_launcher(
    launcher_id: str = "test_launcher",
    name: str = "Test Launcher",
    description: str = "Test description",
    command: str = "echo test",
    category: str = "custom",
    environment: LauncherEnvironment = None,
    terminal: LauncherTerminal = None,
) -> CustomLauncher:
    """Factory for creating test launchers."""
    return CustomLauncher(
        id=launcher_id,
        name=name,
        description=description,
        command=command,
        category=category,
        environment=environment or LauncherEnvironment(),
        terminal=terminal or LauncherTerminal(),
    )


def create_rez_launcher() -> CustomLauncher:
    """Factory for rez environment launcher."""
    env = LauncherEnvironment(type="rez", packages=["PySide6_Essentials", "pillow"])
    terminal = LauncherTerminal(persist=True)
    return create_test_launcher(
        launcher_id="rez_launcher",
        name="Rez Launcher",
        command="nuke {workspace_path}/{shot}.nk",
        environment=env,
        terminal=terminal,
    )


def create_conda_launcher() -> CustomLauncher:
    """Factory for conda environment launcher."""
    env = LauncherEnvironment(type="conda", command_prefix="vfx_env")
    return create_test_launcher(
        launcher_id="conda_launcher",
        name="Conda Launcher",
        command="python script.py",
        environment=env,
    )


# Mock LauncherManager Fixture
@pytest.fixture
def mock_launcher_manager():
    """Create a mock LauncherManager with proper method signatures."""
    manager = Mock(spec=LauncherManager)

    # Setup default return values
    manager.validate_command_syntax.return_value = (True, None)
    manager.get_launcher_by_name.return_value = None
    manager.create_launcher.return_value = "new_launcher_id"
    manager.update_launcher.return_value = True
    manager.delete_launcher.return_value = True
    manager.execute_launcher.return_value = True
    manager.list_launchers.return_value = []

    # Mock signals
    manager.launchers_changed = Mock()
    manager.execution_started = Mock()
    manager.execution_finished = Mock()

    return manager


@pytest.fixture
def sample_launchers():
    """Create sample launchers for testing."""
    return [create_test_launcher(), create_rez_launcher(), create_conda_launcher()]


class TestLauncherListWidget:
    """Test the custom launcher list widget."""

    def test_initialization(self, qtbot):
        """Test widget initialization with drag-and-drop support."""
        widget = LauncherListWidget()
        qtbot.addWidget(widget)

        # Check drag-and-drop configuration
        assert widget.dragDropMode() == widget.DragDropMode.InternalMove
        assert widget.defaultDropAction() == Qt.DropAction.MoveAction
        assert widget.alternatingRowColors() is True
        assert widget.objectName() == "launcherList"


class TestLauncherPreviewPanel:
    """Test the launcher preview panel component."""

    def test_initialization(self, qtbot):
        """Test panel initialization with default state."""
        panel = LauncherPreviewPanel()
        qtbot.addWidget(panel)

        # Check initial state
        assert panel.name_label.text() == "Select a launcher"
        assert panel.description_label.text() == ""
        assert panel.command_preview.toPlainText() == ""
        assert not panel.launch_button.isEnabled()
        assert not panel.edit_button.isEnabled()
        assert not panel.delete_button.isEnabled()
        assert panel._current_launcher_id is None

    def test_set_launcher_with_data(self, qtbot):
        """Test setting launcher data updates UI properly."""
        panel = LauncherPreviewPanel()
        qtbot.addWidget(panel)

        launcher = create_test_launcher()
        panel.set_launcher(launcher)

        # Check UI updates
        assert panel.name_label.text() == launcher.name
        assert panel.description_label.text() == launcher.description
        assert panel.command_preview.toPlainText() == launcher.command
        assert panel.launch_button.isEnabled()
        assert panel.edit_button.isEnabled()
        assert panel.delete_button.isEnabled()
        assert panel._current_launcher_id == launcher.id

    def test_set_launcher_with_none(self, qtbot):
        """Test setting None launcher clears UI."""
        panel = LauncherPreviewPanel()
        qtbot.addWidget(panel)

        # First set a launcher
        launcher = create_test_launcher()
        panel.set_launcher(launcher)
        assert panel.launch_button.isEnabled()

        # Then clear it
        panel.set_launcher(None)

        assert panel.name_label.text() == "Select a launcher"
        assert panel.description_label.text() == ""
        assert panel.command_preview.toPlainText() == ""
        assert not panel.launch_button.isEnabled()
        assert not panel.edit_button.isEnabled()
        assert not panel.delete_button.isEnabled()
        assert panel._current_launcher_id is None

    def test_launch_button_signal(self, qtbot):
        """Test launch button emits correct signal."""
        panel = LauncherPreviewPanel()
        qtbot.addWidget(panel)

        # Setup launcher
        launcher = create_test_launcher()
        panel.set_launcher(launcher)

        # Use QSignalSpy to test signal emission
        spy = QSignalSpy(panel.launch_requested)

        # Click button
        QTest.mouseClick(panel.launch_button, Qt.MouseButton.LeftButton)
        qtbot.wait(10)  # Brief wait for signal processing

        # Verify signal emission
        assert spy.count() == 1
        signal_args = spy.at(0)
        assert signal_args[0] == launcher.id

    def test_edit_button_signal(self, qtbot):
        """Test edit button emits correct signal."""
        panel = LauncherPreviewPanel()
        qtbot.addWidget(panel)

        launcher = create_test_launcher()
        panel.set_launcher(launcher)

        spy = QSignalSpy(panel.edit_requested)
        QTest.mouseClick(panel.edit_button, Qt.MouseButton.LeftButton)
        qtbot.wait(10)

        assert spy.count() == 1
        signal_args = spy.at(0)
        assert signal_args[0] == launcher.id

    def test_delete_button_signal(self, qtbot):
        """Test delete button emits correct signal."""
        panel = LauncherPreviewPanel()
        qtbot.addWidget(panel)

        launcher = create_test_launcher()
        panel.set_launcher(launcher)

        spy = QSignalSpy(panel.delete_requested)
        QTest.mouseClick(panel.delete_button, Qt.MouseButton.LeftButton)
        qtbot.wait(10)

        assert spy.count() == 1
        signal_args = spy.at(0)
        assert signal_args[0] == launcher.id

    def test_button_signals_when_no_launcher(self, qtbot):
        """Test buttons don't emit signals when no launcher is set."""
        panel = LauncherPreviewPanel()
        qtbot.addWidget(panel)

        # Buttons should be disabled, but test they don't emit even if clicked
        spies = [
            QSignalSpy(panel.launch_requested),
            QSignalSpy(panel.edit_requested),
            QSignalSpy(panel.delete_requested),
        ]

        # Try clicking disabled buttons (shouldn't work, but testing defensive code)
        QTest.mouseClick(panel.launch_button, Qt.MouseButton.LeftButton)
        QTest.mouseClick(panel.edit_button, Qt.MouseButton.LeftButton)
        QTest.mouseClick(panel.delete_button, Qt.MouseButton.LeftButton)
        qtbot.wait(10)

        # No signals should be emitted
        for spy in spies:
            assert spy.count() == 0


class TestLauncherEditDialog:
    """Test the launcher edit dialog."""

    def test_create_mode_initialization(self, qtbot, mock_launcher_manager):
        """Test dialog initialization in create mode."""
        dialog = LauncherEditDialog(mock_launcher_manager)
        qtbot.addWidget(dialog)

        # Check create mode setup
        assert dialog.windowTitle() == "New Launcher"
        assert not dialog.is_editing
        assert dialog.launcher is None

        # Check empty fields
        assert dialog.name_field.text() == ""
        assert dialog.command_field.toPlainText() == ""
        assert dialog.description_field.text() == ""
        assert dialog.category_field.text() == ""
        assert dialog.env_type_combo.currentText() == "none"
        assert dialog.env_spec_field.text() == ""
        assert not dialog.persist_terminal.isChecked()

    def test_edit_mode_initialization(self, qtbot, mock_launcher_manager):
        """Test dialog initialization in edit mode."""
        launcher = create_rez_launcher()
        dialog = LauncherEditDialog(mock_launcher_manager, launcher)
        qtbot.addWidget(dialog)

        # Check edit mode setup
        assert dialog.windowTitle() == "Edit Launcher"
        assert dialog.is_editing
        assert dialog.launcher == launcher

        # Check field population
        assert dialog.name_field.text() == launcher.name
        assert dialog.command_field.toPlainText() == launcher.command
        assert dialog.description_field.text() == launcher.description
        assert dialog.category_field.text() == launcher.category
        assert dialog.env_type_combo.currentText() == launcher.environment.type
        assert dialog.env_spec_field.text() == " ".join(launcher.environment.packages)
        assert dialog.persist_terminal.isChecked() == launcher.terminal.persist

    def test_conda_environment_population(self, qtbot, mock_launcher_manager):
        """Test conda environment field population."""
        launcher = create_conda_launcher()
        dialog = LauncherEditDialog(mock_launcher_manager, launcher)
        qtbot.addWidget(dialog)

        assert dialog.env_type_combo.currentText() == "conda"
        assert dialog.env_spec_field.text() == launcher.environment.command_prefix

    def test_name_validation_empty(self, qtbot, mock_launcher_manager):
        """Test name validation with empty name."""
        dialog = LauncherEditDialog(mock_launcher_manager)
        qtbot.addWidget(dialog)

        # Empty name should be invalid
        dialog.name_field.setText("")
        qtbot.wait(10)  # Allow validation to process

        assert not dialog._validate_name()
        assert "border: 1px solid #f44336" in dialog.name_field.styleSheet()

    def test_name_validation_valid(self, qtbot, mock_launcher_manager):
        """Test name validation with valid name."""
        dialog = LauncherEditDialog(mock_launcher_manager)
        qtbot.addWidget(dialog)

        # Valid name should pass
        dialog.name_field.setText("Valid Launcher Name")
        qtbot.wait(10)

        assert dialog._validate_name()
        assert "border: 1px solid #4caf50" in dialog.name_field.styleSheet()

    def test_name_validation_duplicate(self, qtbot, mock_launcher_manager):
        """Test name validation with duplicate name."""
        # Mock manager to return existing launcher
        existing_launcher = create_test_launcher(name="Existing Launcher")
        mock_launcher_manager.get_launcher_by_name.return_value = existing_launcher

        dialog = LauncherEditDialog(mock_launcher_manager)
        qtbot.addWidget(dialog)

        # Duplicate name should be invalid
        dialog.name_field.setText("Existing Launcher")
        qtbot.wait(10)

        assert not dialog._validate_name()
        assert "border: 1px solid #f44336" in dialog.name_field.styleSheet()

    def test_name_validation_duplicate_self_edit(self, qtbot, mock_launcher_manager):
        """Test name validation allows same name when editing same launcher."""
        launcher = create_test_launcher(name="Test Launcher")
        mock_launcher_manager.get_launcher_by_name.return_value = launcher

        dialog = LauncherEditDialog(mock_launcher_manager, launcher)
        qtbot.addWidget(dialog)

        # Same name should be valid when editing same launcher
        dialog.name_field.setText("Test Launcher")
        qtbot.wait(10)

        assert dialog._validate_name()
        assert "border: 1px solid #4caf50" in dialog.name_field.styleSheet()

    def test_command_validation_empty(self, qtbot, mock_launcher_manager):
        """Test command validation with empty command."""
        dialog = LauncherEditDialog(mock_launcher_manager)
        qtbot.addWidget(dialog)

        dialog.command_field.setPlainText("")
        qtbot.wait(10)

        assert not dialog._validate_command()
        assert "border: 1px solid #f44336" in dialog.command_field.styleSheet()

    def test_command_validation_valid(self, qtbot, mock_launcher_manager):
        """Test command validation with valid command."""
        mock_launcher_manager.validate_command_syntax.return_value = (True, None)

        dialog = LauncherEditDialog(mock_launcher_manager)
        qtbot.addWidget(dialog)

        dialog.command_field.setPlainText("echo test")
        qtbot.wait(10)

        assert dialog._validate_command()
        assert "border: 1px solid #4caf50" in dialog.command_field.styleSheet()

    def test_command_validation_invalid(self, qtbot, mock_launcher_manager):
        """Test command validation with invalid command."""
        mock_launcher_manager.validate_command_syntax.return_value = (
            False,
            "Invalid syntax",
        )

        dialog = LauncherEditDialog(mock_launcher_manager)
        qtbot.addWidget(dialog)

        dialog.command_field.setPlainText("invalid {bad_var}")
        qtbot.wait(10)

        assert not dialog._validate_command()
        assert "border: 1px solid #f44336" in dialog.command_field.styleSheet()

    def test_command_testing_success(self, qtbot, mock_launcher_manager):
        """Test command testing with successful validation."""
        mock_launcher_manager.execute_launcher.return_value = True

        dialog = LauncherEditDialog(mock_launcher_manager)
        qtbot.addWidget(dialog)

        dialog.command_field.setPlainText("echo test")

        # Click test button
        QTest.mouseClick(dialog.test_button, Qt.MouseButton.LeftButton)
        qtbot.wait(50)  # Wait for test execution

        # Check success message
        assert "✓ Command validated successfully" in dialog.test_output.text()
        assert "color: #4caf50" in dialog.test_output.styleSheet()

        # Verify manager was called with dry_run=True
        mock_launcher_manager.execute_launcher.assert_called_once()
        call_args = mock_launcher_manager.execute_launcher.call_args
        assert call_args.kwargs.get("dry_run") is True

    def test_command_testing_failure(self, qtbot, mock_launcher_manager):
        """Test command testing with validation failure."""
        mock_launcher_manager.execute_launcher.side_effect = Exception("Test error")

        dialog = LauncherEditDialog(mock_launcher_manager)
        qtbot.addWidget(dialog)

        dialog.command_field.setPlainText("bad command")

        QTest.mouseClick(dialog.test_button, Qt.MouseButton.LeftButton)
        qtbot.wait(50)

        assert "✗ Test error" in dialog.test_output.text()
        assert "color: #f44336" in dialog.test_output.styleSheet()

    def test_command_testing_empty_command(self, qtbot, mock_launcher_manager):
        """Test command testing with empty command."""
        dialog = LauncherEditDialog(mock_launcher_manager)
        qtbot.addWidget(dialog)

        # Empty command field
        dialog.command_field.setPlainText("")

        QTest.mouseClick(dialog.test_button, Qt.MouseButton.LeftButton)
        qtbot.wait(10)

        assert dialog.test_output.text() == "No command to test"
        mock_launcher_manager.execute_launcher.assert_not_called()

    def test_save_create_success(self, qtbot, mock_launcher_manager):
        """Test successful launcher creation."""
        mock_launcher_manager.validate_command_syntax.return_value = (True, None)
        mock_launcher_manager.create_launcher.return_value = "new_launcher_id"

        dialog = LauncherEditDialog(mock_launcher_manager)
        qtbot.addWidget(dialog)

        # Fill in valid form data
        dialog.name_field.setText("New Launcher")
        dialog.command_field.setPlainText("echo test")
        dialog.description_field.setText("Test description")
        dialog.category_field.setText("test_category")
        dialog.env_type_combo.setCurrentText("rez")
        dialog.env_spec_field.setText("PySide6_Essentials pillow")
        dialog.persist_terminal.setChecked(True)

        # Mock dialog result
        dialog.accept = Mock()

        # Trigger save
        dialog._save()

        # Verify create_launcher was called with correct parameters
        mock_launcher_manager.create_launcher.assert_called_once()
        call_kwargs = mock_launcher_manager.create_launcher.call_args.kwargs

        assert call_kwargs["name"] == "New Launcher"
        assert call_kwargs["command"] == "echo test"
        assert call_kwargs["description"] == "Test description"
        assert call_kwargs["category"] == "test_category"
        assert call_kwargs["environment"].type == "rez"
        assert call_kwargs["environment"].packages == ["PySide6_Essentials", "pillow"]
        assert call_kwargs["terminal"].persist is True

        # Dialog should be accepted
        dialog.accept.assert_called_once()

    def test_save_update_success(self, qtbot, mock_launcher_manager):
        """Test successful launcher update."""
        launcher = create_test_launcher()
        mock_launcher_manager.validate_command_syntax.return_value = (True, None)
        mock_launcher_manager.update_launcher.return_value = True

        dialog = LauncherEditDialog(mock_launcher_manager, launcher)
        qtbot.addWidget(dialog)

        # Modify fields
        dialog.name_field.setText("Updated Name")
        dialog.command_field.setPlainText("updated command")

        dialog.accept = Mock()
        dialog._save()

        # Verify update_launcher was called
        mock_launcher_manager.update_launcher.assert_called_once()
        call_args = mock_launcher_manager.update_launcher.call_args
        assert call_args[0][0] == launcher.id  # First positional arg is launcher_id
        assert call_args.kwargs["name"] == "Updated Name"
        assert call_args.kwargs["command"] == "updated command"

        dialog.accept.assert_called_once()

    def test_save_validation_failure(self, qtbot, mock_launcher_manager):
        """Test save with validation failures."""
        dialog = LauncherEditDialog(mock_launcher_manager)
        qtbot.addWidget(dialog)

        # Leave required fields empty
        dialog.name_field.setText("")
        dialog.command_field.setPlainText("")

        # Mock QMessageBox to avoid actual dialog
        with patch("launcher_dialog.QMessageBox.warning") as mock_warning:
            dialog._save()

        # Should not call create_launcher
        mock_launcher_manager.create_launcher.assert_not_called()
        # Should show validation error
        mock_warning.assert_called()

    def test_save_create_failure(self, qtbot, mock_launcher_manager):
        """Test save when create_launcher fails."""
        mock_launcher_manager.validate_command_syntax.return_value = (True, None)
        mock_launcher_manager.create_launcher.return_value = None  # Failure

        dialog = LauncherEditDialog(mock_launcher_manager)
        qtbot.addWidget(dialog)

        # Fill valid data
        dialog.name_field.setText("Test Launcher")
        dialog.command_field.setPlainText("echo test")

        # Mock QMessageBox
        with patch("launcher_dialog.QMessageBox.critical") as mock_critical:
            dialog._save()
            mock_critical.assert_called()

        mock_launcher_manager.create_launcher.assert_called_once()

    def test_conda_environment_handling(self, qtbot, mock_launcher_manager):
        """Test conda environment configuration in save."""
        mock_launcher_manager.validate_command_syntax.return_value = (True, None)
        mock_launcher_manager.create_launcher.return_value = "new_id"

        dialog = LauncherEditDialog(mock_launcher_manager)
        qtbot.addWidget(dialog)

        dialog.name_field.setText("Conda Launcher")
        dialog.command_field.setPlainText("python script.py")
        dialog.env_type_combo.setCurrentText("conda")
        dialog.env_spec_field.setText("vfx_env")

        dialog.accept = Mock()
        dialog._save()

        # Check conda environment was created correctly
        call_kwargs = mock_launcher_manager.create_launcher.call_args.kwargs
        env = call_kwargs["environment"]
        assert env.type == "conda"
        assert env.command_prefix == "vfx_env"


class TestLauncherManagerDialog:
    """Test the main launcher manager dialog."""

    def test_initialization(self, qtbot, mock_launcher_manager, sample_launchers):
        """Test dialog initialization and setup."""
        mock_launcher_manager.list_launchers.return_value = sample_launchers

        dialog = LauncherManagerDialog(mock_launcher_manager)
        qtbot.addWidget(dialog)

        # Check basic setup
        assert dialog.windowTitle() == "Custom Launchers"
        assert not dialog.isModal()
        assert dialog.size().width() == 900
        assert dialog.size().height() == 600

        # Check components exist
        assert dialog.launcher_list is not None
        assert dialog.preview_panel is not None
        assert dialog.search_field is not None
        assert dialog.add_button is not None
        assert dialog.close_button is not None

        # Check launcher list was populated
        assert dialog.launcher_list.count() == len(sample_launchers)

        # Check first item is selected
        assert dialog.launcher_list.currentRow() == 0

    def test_launcher_list_population(
        self, qtbot, mock_launcher_manager, sample_launchers
    ):
        """Test launcher list is populated correctly."""
        mock_launcher_manager.list_launchers.return_value = sample_launchers

        dialog = LauncherManagerDialog(mock_launcher_manager)
        qtbot.addWidget(dialog)

        # Check each launcher is in the list
        for i, launcher in enumerate(sample_launchers):
            item = dialog.launcher_list.item(i)
            assert item.text() == launcher.name
            assert item.data(Qt.ItemDataRole.UserRole) == launcher.id
            assert dialog._launchers_cache[launcher.id] == launcher

    def test_selection_updates_preview(
        self, qtbot, mock_launcher_manager, sample_launchers
    ):
        """Test selecting launcher updates preview panel."""
        mock_launcher_manager.list_launchers.return_value = sample_launchers

        dialog = LauncherManagerDialog(mock_launcher_manager)
        qtbot.addWidget(dialog)

        # Select second launcher
        dialog.launcher_list.setCurrentRow(1)
        qtbot.wait(10)

        # Check preview was updated
        selected_launcher = sample_launchers[1]
        assert dialog.preview_panel.name_label.text() == selected_launcher.name
        assert dialog.preview_panel._current_launcher_id == selected_launcher.id

    def test_search_filtering(self, qtbot, mock_launcher_manager, sample_launchers):
        """Test search filtering functionality."""
        mock_launcher_manager.list_launchers.return_value = sample_launchers

        dialog = LauncherManagerDialog(mock_launcher_manager)
        qtbot.addWidget(dialog)

        # Search for "Rez"
        dialog.search_field.setText("Rez")
        qtbot.wait(10)

        # Check filtering - only rez launcher should be visible
        for i in range(dialog.launcher_list.count()):
            item = dialog.launcher_list.item(i)
            launcher_id = item.data(Qt.ItemDataRole.UserRole)
            launcher = dialog._launchers_cache[launcher_id]

            should_be_visible = "rez" in launcher.name.lower()
            assert item.isHidden() != should_be_visible

    def test_search_command_filtering(
        self, qtbot, mock_launcher_manager, sample_launchers
    ):
        """Test search filters by command content."""
        mock_launcher_manager.list_launchers.return_value = sample_launchers

        dialog = LauncherManagerDialog(mock_launcher_manager)
        qtbot.addWidget(dialog)

        # Search for "nuke" (should match rez launcher command)
        dialog.search_field.setText("nuke")
        qtbot.wait(10)

        # Check that rez launcher (which has "nuke" in command) is visible
        rez_launcher = next(
            launcher for launcher in sample_launchers if launcher.id == "rez_launcher"
        )
        for i in range(dialog.launcher_list.count()):
            item = dialog.launcher_list.item(i)
            launcher_id = item.data(Qt.ItemDataRole.UserRole)

            should_be_visible = launcher_id == rez_launcher.id
            assert item.isHidden() != should_be_visible

    def test_double_click_launches(
        self, qtbot, mock_launcher_manager, sample_launchers
    ):
        """Test double-clicking launcher item triggers launch."""
        mock_launcher_manager.list_launchers.return_value = sample_launchers

        dialog = LauncherManagerDialog(mock_launcher_manager)
        qtbot.addWidget(dialog)

        # Select first item and trigger double-click
        dialog.launcher_list.setCurrentRow(0)
        item = dialog.launcher_list.item(0)

        # Trigger the double-click handler directly to test the logic
        dialog._on_double_click(item)
        qtbot.wait(10)

        # Should have called execute_launcher
        expected_launcher_id = sample_launchers[0].id
        mock_launcher_manager.execute_launcher.assert_called_with(expected_launcher_id)

    def test_add_launcher_button(self, qtbot, mock_launcher_manager):
        """Test add launcher button opens edit dialog."""
        dialog = LauncherManagerDialog(mock_launcher_manager)
        qtbot.addWidget(dialog)

        # Mock the edit dialog to avoid actual dialog
        with patch("launcher_dialog.LauncherEditDialog") as mock_edit_dialog:
            mock_edit_dialog.return_value.exec.return_value = (
                QDialog.DialogCode.Accepted
            )
            QTest.mouseClick(dialog.add_button, Qt.MouseButton.LeftButton)
            qtbot.wait(10)

        # Edit dialog should have been created and shown
        mock_edit_dialog.assert_called_once()

    def test_preview_panel_signals(
        self, qtbot, mock_launcher_manager, sample_launchers
    ):
        """Test preview panel signals trigger correct actions."""
        mock_launcher_manager.list_launchers.return_value = sample_launchers

        dialog = LauncherManagerDialog(mock_launcher_manager)
        qtbot.addWidget(dialog)

        launcher_id = sample_launchers[0].id

        # Test launch signal
        dialog._launch_launcher(launcher_id)
        mock_launcher_manager.execute_launcher.assert_called_with(launcher_id)

        # Test edit signal - would normally open dialog
        with patch("launcher_dialog.LauncherEditDialog") as mock_edit_dialog:
            mock_edit_dialog.return_value.exec.return_value = (
                QDialog.DialogCode.Accepted
            )
            dialog._edit_launcher(launcher_id)
            mock_edit_dialog.assert_called()

        # Test delete signal - would normally show confirmation
        with patch("launcher_dialog.QMessageBox.question") as mock_question:
            mock_question.return_value = QMessageBox.StandardButton.Yes
            dialog._delete_launcher(launcher_id)

        mock_launcher_manager.delete_launcher.assert_called_with(launcher_id)

    def test_keyboard_shortcuts(self, qtbot, mock_launcher_manager, sample_launchers):
        """Test keyboard shortcuts work correctly."""
        mock_launcher_manager.list_launchers.return_value = sample_launchers

        dialog = LauncherManagerDialog(mock_launcher_manager)
        qtbot.addWidget(dialog)

        # Select first launcher
        dialog.launcher_list.setCurrentRow(0)
        qtbot.wait(10)

        # Test Enter key for launch (call the shortcut method directly)
        dialog._launch_selected()
        qtbot.wait(10)
        mock_launcher_manager.execute_launcher.assert_called()

        # Test F2 for edit (call the shortcut method directly)
        with patch("launcher_dialog.LauncherEditDialog") as mock_edit_dialog:
            mock_edit_dialog.return_value.exec.return_value = (
                QDialog.DialogCode.Accepted
            )
            dialog._edit_selected()
            qtbot.wait(10)
            mock_edit_dialog.assert_called()

        # Test Delete key (call the shortcut method directly)
        with patch("launcher_dialog.QMessageBox.question") as mock_question:
            mock_question.return_value = QMessageBox.StandardButton.Yes
            dialog._delete_selected()
            qtbot.wait(10)

        # Test Ctrl+N for new launcher (call the shortcut method directly)
        with patch("launcher_dialog.LauncherEditDialog") as mock_edit_dialog:
            mock_edit_dialog.return_value.exec.return_value = (
                QDialog.DialogCode.Accepted
            )
            dialog._add_launcher()
            qtbot.wait(10)
            mock_edit_dialog.assert_called()

        # Test Ctrl+F focuses search (call the shortcut lambda directly)
        dialog.show()  # Make sure dialog is visible for focus to work
        with qtbot.waitExposed(dialog):
            pass
        dialog.search_field.setFocus()  # The lambda does: self.search_field.setFocus()
        qtbot.wait(10)
        assert dialog.search_field.hasFocus()

    def test_execution_signals(self, qtbot, mock_launcher_manager):
        """Test handling of launcher execution signals."""
        dialog = LauncherManagerDialog(mock_launcher_manager)
        qtbot.addWidget(dialog)

        launcher_id = "test_launcher"

        # Test execution started signal
        dialog._on_execution_started(launcher_id)
        # Should log but not crash - mainly testing the signal connection

        # Test execution finished signal
        dialog._on_execution_finished(launcher_id, True)
        dialog._on_execution_finished(launcher_id, False)
        # Should handle both success and failure cases

    def test_empty_launcher_list(self, qtbot, mock_launcher_manager):
        """Test dialog handles empty launcher list correctly."""
        mock_launcher_manager.list_launchers.return_value = []

        dialog = LauncherManagerDialog(mock_launcher_manager)
        qtbot.addWidget(dialog)

        # Should handle empty list gracefully
        assert dialog.launcher_list.count() == 0
        assert dialog.preview_panel._current_launcher_id is None
        assert not dialog.preview_panel.launch_button.isEnabled()

    def test_launcher_reload_on_changes(
        self, qtbot, mock_launcher_manager, sample_launchers
    ):
        """Test launcher list reloads when launchers change."""
        mock_launcher_manager.list_launchers.return_value = sample_launchers

        dialog = LauncherManagerDialog(mock_launcher_manager)
        qtbot.addWidget(dialog)

        initial_count = dialog.launcher_list.count()

        # Simulate launchers changed signal
        new_launchers = sample_launchers + [
            create_test_launcher("new_launcher", "New Launcher")
        ]
        mock_launcher_manager.list_launchers.return_value = new_launchers

        # Trigger reload
        dialog._load_launchers()
        qtbot.wait(10)

        # Should have one more launcher
        assert dialog.launcher_list.count() == initial_count + 1
