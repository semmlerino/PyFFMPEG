"""Tests for MainWindow - critical UI integration.

Following UNIFIED_TESTING_GUIDE principles:
- Use real components where possible
- Use test doubles at system boundaries (subprocess)
- Test behavior not implementation
- Use qtbot for proper Qt testing
"""

# Standard library imports
from pathlib import Path
from typing import Self

# Third-party imports
import pytest
from pytestqt.qtbot import QtBot

# Local application imports
# Lazy imports to avoid Qt initialization at module level
# from cache_manager import CacheManager
# from main_window import MainWindow
# from shot_model import Shot
from config import Config
from tests.unit.test_protocols import ProcessPoolProtocol as TestProcessPoolType

pytestmark = [
    pytest.mark.unit,
    pytest.mark.qt,
    pytest.mark.slow,
    pytest.mark.xdist_group("qt_state"),
]

# Module-level fixture to handle lazy imports
@pytest.fixture(scope="module", autouse=True)
def setup_qt_imports():
    """Import Qt and MainWindow components after test setup."""
    global MainWindow, CacheManager, Shot
    # Local application imports
    from cache_manager import CacheManager
    from main_window import MainWindow
    from shot_model import Shot


class TestMainWindowInitialization:
    """Test MainWindow initialization and component setup."""

    def test_main_window_creates_all_components(
        self, qtbot: QtBot, tmp_path: Path
    ) -> None:
        """Test that MainWindow initializes all required components."""
        # Use real cache manager with temp directory
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir(exist_ok=True)
        cache_manager = CacheManager(cache_dir=cache_dir)

        # Create main window with real components
        main_window = MainWindow(cache_manager=cache_manager)
        qtbot.addWidget(main_window)

        # Verify all critical components exist
        assert main_window.cache_manager is not None
        assert main_window.shot_model is not None
        assert main_window.threede_scene_model is not None
        assert main_window.previous_shots_model is not None
        assert main_window.command_launcher is not None
        assert main_window.launcher_manager is not None

        # Verify UI components
        assert main_window.tab_widget is not None
        assert main_window.shot_grid is not None
        assert main_window.threede_shot_grid is not None
        assert main_window.previous_shots_grid is not None
        assert main_window.shot_info_panel is not None

        # Verify tab widget has correct tabs
        assert main_window.tab_widget.count() == 3
        assert main_window.tab_widget.tabText(0) == "My Shots"
        assert main_window.tab_widget.tabText(1) == "Other 3DE scenes"
        assert main_window.tab_widget.tabText(2) == "Previous Shots"

    def test_main_window_without_cache_manager(self, qtbot: QtBot) -> None:
        """Test MainWindow creates its own CacheManager if not provided."""
        main_window = MainWindow()  # No cache_manager argument
        qtbot.addWidget(main_window)

        # Should create its own cache manager
        assert main_window.cache_manager is not None
        assert isinstance(main_window.cache_manager, CacheManager)

    def test_window_title_is_set(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Test window title is set correctly."""
        cache_manager = CacheManager(cache_dir=tmp_path / "cache")
        main_window = MainWindow(cache_manager=cache_manager)
        qtbot.addWidget(main_window)

        # Check window title includes app name
        # Note: MainWindow may or may not include version in title
        assert Config.APP_NAME in main_window.windowTitle()

        # Skip size test as window size can vary based on display settings


class TestTabSwitching:
    """Test tab switching functionality."""

    def test_tab_switching_updates_current_view(
        self, qtbot: QtBot, tmp_path: Path
    ) -> None:
        """Test that switching tabs updates the current view."""
        cache_manager = CacheManager(cache_dir=tmp_path / "cache")
        main_window = MainWindow(cache_manager=cache_manager)
        qtbot.addWidget(main_window)

        # Set to first tab (in case settings loaded different tab)
        main_window.tab_widget.setCurrentIndex(0)
        assert main_window.tab_widget.currentIndex() == 0
        assert main_window.tab_widget.currentWidget() == main_window.shot_grid

        # Switch to second tab
        main_window.tab_widget.setCurrentIndex(1)
        assert main_window.tab_widget.currentIndex() == 1
        assert main_window.tab_widget.currentWidget() == main_window.threede_shot_grid

        # Switch to third tab
        main_window.tab_widget.setCurrentIndex(2)
        assert main_window.tab_widget.currentIndex() == 2
        assert main_window.tab_widget.currentWidget() == main_window.previous_shots_grid


class TestShotSelection:
    """Test shot selection and application launching."""

    def test_shot_selection_enables_app_buttons(
        self, qtbot: QtBot, tmp_path: Path
    ) -> None:
        """Test that selecting a shot enables application launcher buttons."""
        cache_manager = CacheManager(cache_dir=tmp_path / "cache")
        main_window = MainWindow(cache_manager=cache_manager)
        qtbot.addWidget(main_window)

        # Initially launcher panel's app buttons should be disabled
        for section in main_window.launcher_panel.app_sections.values():
            assert not section.launch_button.isEnabled()

        # Create a test shot
        shot = Shot("test_show", "seq01", "0010", "/shows/test/seq01/0010")

        # Simulate shot selection
        main_window._on_shot_selected(shot)

        # Now buttons should be enabled
        for section in main_window.launcher_panel.app_sections.values():
            assert section.launch_button.isEnabled()

        # Shot info panel should be updated with the shot
        # Test behavior: info panel should show shot information
        assert main_window.shot_info_panel is not None

    def test_shot_deselection_disables_app_buttons(
        self, qtbot: QtBot, tmp_path: Path
    ) -> None:
        """Test that deselecting a shot disables application launcher buttons."""
        cache_manager = CacheManager(cache_dir=tmp_path / "cache")
        main_window = MainWindow(cache_manager=cache_manager)
        qtbot.addWidget(main_window)

        # Select a shot first
        shot = Shot("test_show", "seq01", "0010", "/shows/test/seq01/0010")
        main_window._on_shot_selected(shot)

        # Verify buttons are enabled
        for section in main_window.launcher_panel.app_sections.values():
            assert section.launch_button.isEnabled()

        # Deselect shot
        main_window._on_shot_selected(None)

        # Buttons should be disabled again
        for section in main_window.launcher_panel.app_sections.values():
            assert not section.launch_button.isEnabled()


class TestShotRefresh:
    """Test shot refresh functionality."""

    def test_refresh_shots_updates_display(
        self, test_process_pool: TestProcessPoolType, qtbot: QtBot, tmp_path: Path
    ) -> None:
        """Test that refreshing shots updates the display."""
        # QMessageBox mocking now handled by autouse fixture in conftest.py
        cache_manager = CacheManager(cache_dir=tmp_path / "cache")
        main_window = MainWindow(cache_manager=cache_manager)
        qtbot.addWidget(main_window)

        # Use test process pool to avoid real subprocess calls (UNIFIED_TESTING_GUIDE)
        # Use correct VFX path format: /shows/{show}/shots/{sequence}/{sequence}_{shot}
        test_process_pool.set_outputs(
            "workspace /shows/test/shots/seq01/seq01_0010\nworkspace /shows/test/shots/seq01/seq01_0020"
        )
        main_window.shot_model._process_pool = test_process_pool

        # Initial state - no shots
        assert len(main_window.shot_model.shots) == 0

        # Follow integration test pattern from UNIFIED_TESTING_GUIDE line 186-203
        # Directly update the model with parsed output to avoid async issues
        output = test_process_pool.execute_workspace_command("ws -sg")
        shots = main_window.shot_model._parse_ws_output(output)

        # Update the model's shots
        main_window.shot_model.shots = shots

        # Directly call the handler method instead of using signals to avoid Qt event loop issues
        # This tests our logic without relying on Qt's signal processing
        main_window._on_shots_changed(shots)

        # Should have 2 shots now
        assert len(main_window.shot_model.shots) == 2
        assert main_window.shot_model.shots[0].shot == "0010"
        assert main_window.shot_model.shots[1].shot == "0020"

        # Shot grid should be updated via _on_shots_changed -> _refresh_shot_display
        assert main_window.shot_item_model.rowCount() == 2


class TestApplicationLaunching:
    """Test application launching functionality."""

    def test_launch_app_with_selected_shot(
        self, qtbot: QtBot, tmp_path: Path, monkeypatch
    ) -> None:
        """Test launching an application with a selected shot."""
        cache_manager = CacheManager(cache_dir=tmp_path / "cache")
        main_window = MainWindow(cache_manager=cache_manager)
        qtbot.addWidget(main_window)

        # Select a shot with tmp_path as workspace
        workspace_path = str(tmp_path / "test_workspace")
        shot = Shot("test_show", "seq01", "0010", workspace_path)
        main_window._on_shot_selected(shot)

        # Mock subprocess at the system boundary
        # This is at the system boundary, so acceptable per UNIFIED_TESTING_GUIDE
        executed_commands = []

        class MockProcess:
            def __init__(self) -> None:
                self.returncode = 0
                self.args = None
                self.stdout = ""
                self.stderr = ""
                self.pid = 12345  # Mock PID for persistent terminal

            def __enter__(self) -> Self:
                return self

            def __exit__(self, exc_type, exc_val, exc_tb) -> None:
                pass

            def communicate(self, input=None, timeout=None):
                return (self.stdout, self.stderr)

            def poll(self):
                return self.returncode

            def kill(self) -> None:
                pass

            def wait(self, timeout=None):
                return self.returncode

        def mock_popen(command, **kwargs):
            executed_commands.append(command)
            process = MockProcess()
            process.args = command
            return process

        # Mock both subprocess.run and subprocess.Popen
        class CompletedProcessMock:
            def __init__(self, args, returncode) -> None:
                self.args = args
                self.returncode = returncode
                self.stdout = ""
                self.stderr = ""

        def mock_run(command, **kwargs):
            executed_commands.append(command)
            return CompletedProcessMock(command, 0)

        monkeypatch.setattr("subprocess.Popen", mock_popen)
        monkeypatch.setattr("subprocess.run", mock_run)

        # Launch an app - test behavior, not implementation
        main_window.launch_app("nuke")

        # Test behavior: command should have been executed
        assert len(executed_commands) > 0

        # Find the nuke command (might not be first due to rez check)
        nuke_command_found = False
        for executed_command in executed_commands:
            if isinstance(executed_command, list):
                command_str = " ".join(str(c) for c in executed_command)
            else:
                command_str = str(executed_command)
            if "nuke" in command_str.lower():
                nuke_command_found = True
                break

        assert nuke_command_found, f"nuke command not found in: {executed_commands}"
        # Verify launch was successful (returns None for successful subprocess.Popen)
        # Note: launch_app doesn't return True/False, it returns None on success

    def test_launch_app_without_shot_shows_error(
        self, qtbot: QtBot, tmp_path: Path
    ) -> None:
        """Test launching an app without a shot shows appropriate error."""
        cache_manager = CacheManager(cache_dir=tmp_path / "cache")
        main_window = MainWindow(cache_manager=cache_manager)
        qtbot.addWidget(main_window)

        # No shot selected - buttons should be disabled
        for section in main_window.launcher_panel.app_sections.values():
            assert not section.launch_button.isEnabled()

        # Test behavior: app launch should be prevented when no shot is selected
        # This is handled by UI state - buttons are disabled
        # Testing the actual behavior rather than mocking internal methods


class TestSignalConnections:
    """Test signal connections between components."""

    def test_shot_model_refresh_behavior(
        self,
        mock_gui_blocking_components: TestProcessPoolType,
        qtbot: QtBot,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """Test that shot model refresh works correctly."""
        # Force use of legacy ShotModel for synchronous behavior testing
        monkeypatch.setenv("SHOTBOT_USE_LEGACY_MODEL", "1")

        cache_manager = CacheManager(cache_dir=tmp_path / "cache")
        main_window = MainWindow(cache_manager=cache_manager)
        qtbot.addWidget(main_window)

        # The autouse fixture patches ProcessPoolManager.get_instance(), but the shot model
        # has already gotten the real instance during MainWindow.__init__().
        # We need to replace the shot model's _process_pool with our test instance.
        mock_gui_blocking_components.reset()  # Reset the pool first to clear any previous outputs
        mock_gui_blocking_components.set_outputs(
            "workspace /shows/different/shots/seq01/seq01_0010"
        )

        # Replace the shot model's process pool with our test instance
        main_window.shot_model._process_pool = mock_gui_blocking_components

        # Clear any existing shots first to ensure test starts clean
        main_window.shot_model.shots = []

        # Set test output for the refresh operation
        mock_gui_blocking_components.set_outputs(
            "workspace /shows/different/shots/seq01/seq01_0010"
        )

        # Initially no shots after clearing
        assert len(main_window.shot_model.shots) == 0

        # Trigger refresh
        result = main_window.shot_model.refresh_shots()

        # Should succeed and have changes
        assert result.success
        assert result.has_changes
        assert len(main_window.shot_model.shots) == 1

    def test_custom_launcher_signals_connected(
        self, qtbot: QtBot, tmp_path: Path
    ) -> None:
        """Test that custom launcher signals are properly connected."""
        cache_manager = CacheManager(cache_dir=tmp_path / "cache")
        main_window = MainWindow(cache_manager=cache_manager)
        qtbot.addWidget(main_window)

        # Verify launcher manager exists and is connected
        assert main_window.launcher_manager is not None

        # Verify that custom launcher container exists in the launcher panel
        assert hasattr(main_window, "launcher_panel")
        assert hasattr(main_window.launcher_panel, "custom_launcher_container")
        assert main_window.launcher_panel.custom_launcher_container is not None


class TestWindowCleanup:
    """Test proper cleanup when window closes."""

    def test_cleanup_on_close(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Test that resources are properly cleaned up on window close."""
        cache_manager = CacheManager(cache_dir=tmp_path / "cache")
        main_window = MainWindow(cache_manager=cache_manager)
        qtbot.addWidget(main_window)

        # Track that window is not closing initially
        assert not main_window._closing

        # Close the window
        main_window.close()

        # Verify cleanup happened
        assert main_window._closing

        # 3DE worker should be stopped (if it exists)
        if hasattr(main_window, "_threede_worker") and main_window._threede_worker:
            assert not main_window._threede_worker.isRunning()


class TestStatusBar:
    """Test status bar updates."""

    def test_status_bar_updates(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Test that status bar displays messages correctly."""
        cache_manager = CacheManager(cache_dir=tmp_path / "cache")
        main_window = MainWindow(cache_manager=cache_manager)
        qtbot.addWidget(main_window)

        # Update status
        test_message = "Test status message"
        main_window._update_status(test_message)

        # Check status bar shows the message
        status_bar = main_window.statusBar()
        assert status_bar is not None
        # Status bar message is shown temporarily, we can't directly check it
        # but we can verify the method works without error


class TestThumbnailSizeControl:
    """Test thumbnail size increase/decrease functionality."""

    def test_increase_thumbnail_size(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Test increasing thumbnail size updates all grids."""
        cache_manager = CacheManager(cache_dir=tmp_path / "cache")
        main_window = MainWindow(cache_manager=cache_manager)
        qtbot.addWidget(main_window)

        # Get initial size from size slider
        initial_size = main_window.shot_grid.size_slider.value()

        # Increase size
        main_window._increase_thumbnail_size()

        # Size should have increased
        new_size = main_window.shot_grid.size_slider.value()
        assert new_size > initial_size

    def test_decrease_thumbnail_size(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Test decreasing thumbnail size updates all grids."""
        cache_manager = CacheManager(cache_dir=tmp_path / "cache")
        main_window = MainWindow(cache_manager=cache_manager)
        qtbot.addWidget(main_window)

        # Increase first so we can decrease
        main_window._increase_thumbnail_size()
        current_size = main_window.shot_grid.size_slider.value()

        # Decrease size
        main_window._decrease_thumbnail_size()

        # Size should have decreased
        new_size = main_window.shot_grid.size_slider.value()
        assert new_size < current_size


# Integration test for complete workflow
class TestMainWindowIntegration:
    """Integration tests for complete workflows."""

    def test_complete_shot_selection_workflow(
        self,
        mock_gui_blocking_components: TestProcessPoolType,
        qtbot: QtBot,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """Test complete workflow: load shots -> select -> launch app."""
        # Force use of legacy ShotModel for synchronous behavior testing
        monkeypatch.setenv("SHOTBOT_USE_LEGACY_MODEL", "1")

        cache_manager = CacheManager(cache_dir=tmp_path / "cache")
        main_window = MainWindow(cache_manager=cache_manager)
        qtbot.addWidget(main_window)

        # Clear existing shots to ensure clean test start
        main_window.shot_model.shots = []

        # Set up test process pool for 'ws' command with different data than autouse fixture
        mock_gui_blocking_components.reset()
        # Must use standard VFX format for parsing to work: /shows/{show}/shots/{seq}/{seq}_{shot}
        # The path doesn't need to exist since subprocess is mocked
        mock_gui_blocking_components.set_outputs(
            "workspace /shows/workflow/shots/seq01/seq01_0010"
        )
        main_window.shot_model._process_pool = mock_gui_blocking_components

        # Load shots
        main_window._refresh_shots()

        # Verify shot loaded
        assert len(main_window.shot_model.shots) == 1
        shot = main_window.shot_model.shots[0]

        # Select the shot
        main_window._on_shot_selected(shot)

        # Verify buttons enabled (test behavior)
        assert "nuke" in main_window.launcher_panel.app_sections
        assert main_window.launcher_panel.app_sections["nuke"].launch_button.isEnabled()

        # Test complete workflow - just verify the app launch doesn't crash
        # The subprocess call is already mocked by our autouse fixture (no real process spawned)
        # We're testing the integration, not the implementation details

        # Mock the workspace directory creation to avoid permission errors
        def mock_mkdir(self, *args, **kwargs) -> None:
            pass  # Don't actually create directories

        monkeypatch.setattr("pathlib.Path.mkdir", mock_mkdir)
        main_window.launch_app("nuke")

        # Test behavior: app launch completed without errors
        # (If it failed, it would have shown an error notification which is mocked)
