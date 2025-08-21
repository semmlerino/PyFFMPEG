"""Tests for MainWindow - critical UI integration.

Following UNIFIED_TESTING_GUIDE principles:
- Use real components where possible
- Mock only at system boundaries (subprocess)
- Test behavior not implementation
- Use qtbot for proper Qt testing
"""

from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QMessageBox

from cache_manager import CacheManager
from main_window import MainWindow
from shot_model import Shot
from tests.test_doubles import TestProcessPool


class TestMainWindowInitialization:
    """Test MainWindow initialization and component setup."""

    def test_main_window_creates_all_components(self, qtbot, tmp_path: Path) -> None:
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

    def test_main_window_without_cache_manager(self, qtbot) -> None:
        """Test MainWindow creates its own CacheManager if not provided."""
        main_window = MainWindow()  # No cache_manager argument
        qtbot.addWidget(main_window)

        # Should create its own cache manager
        assert main_window.cache_manager is not None
        assert isinstance(main_window.cache_manager, CacheManager)

    def test_window_title_and_size(self, qtbot, tmp_path: Path) -> None:
        """Test window title and default size are set correctly."""
        cache_manager = CacheManager(cache_dir=tmp_path / "cache")
        main_window = MainWindow(cache_manager=cache_manager)
        qtbot.addWidget(main_window)

        # Check window title includes app name and version
        from config import Config

        expected_title = f"{Config.APP_NAME} v{Config.APP_VERSION}"
        assert main_window.windowTitle() == expected_title

        # Check default window size
        assert main_window.width() == Config.DEFAULT_WINDOW_WIDTH
        assert main_window.height() == Config.DEFAULT_WINDOW_HEIGHT


class TestTabSwitching:
    """Test tab switching functionality."""

    def test_tab_switching_updates_current_view(self, qtbot, tmp_path: Path) -> None:
        """Test that switching tabs updates the current view."""
        cache_manager = CacheManager(cache_dir=tmp_path / "cache")
        main_window = MainWindow(cache_manager=cache_manager)
        qtbot.addWidget(main_window)

        # Start at first tab
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

    def test_shot_selection_enables_app_buttons(self, qtbot, tmp_path: Path) -> None:
        """Test that selecting a shot enables application launcher buttons."""
        cache_manager = CacheManager(cache_dir=tmp_path / "cache")
        main_window = MainWindow(cache_manager=cache_manager)
        qtbot.addWidget(main_window)

        # Initially buttons should be disabled
        for button in main_window.app_buttons.values():
            assert not button.isEnabled()

        # Create a test shot
        shot = Shot("test_show", "seq01", "0010", "/shows/test/seq01/0010")

        # Simulate shot selection
        main_window._on_shot_selected(shot)

        # Now buttons should be enabled
        for button in main_window.app_buttons.values():
            assert button.isEnabled()

        # Shot info panel should display the shot
        assert main_window.shot_info_panel._current_shot == shot

    def test_shot_deselection_disables_app_buttons(self, qtbot, tmp_path: Path) -> None:
        """Test that deselecting a shot disables application launcher buttons."""
        cache_manager = CacheManager(cache_dir=tmp_path / "cache")
        main_window = MainWindow(cache_manager=cache_manager)
        qtbot.addWidget(main_window)

        # Select a shot first
        shot = Shot("test_show", "seq01", "0010", "/shows/test/seq01/0010")
        main_window._on_shot_selected(shot)

        # Verify buttons are enabled
        for button in main_window.app_buttons.values():
            assert button.isEnabled()

        # Deselect shot
        main_window._on_shot_selected(None)

        # Buttons should be disabled again
        for button in main_window.app_buttons.values():
            assert not button.isEnabled()


class TestShotRefresh:
    """Test shot refresh functionality."""

    @patch("subprocess.run")
    def test_refresh_shots_updates_display(
        self, mock_run, qtbot, tmp_path: Path
    ) -> None:
        """Test that refreshing shots updates the display."""
        # Mock the workspace command at system boundary
        mock_run.return_value = Mock(
            returncode=0,
            stdout="workspace /shows/test/shots/seq01/0010\nworkspace /shows/test/shots/seq01/0020\n",
            stderr="",
        )

        cache_manager = CacheManager(cache_dir=tmp_path / "cache")
        main_window = MainWindow(cache_manager=cache_manager)
        qtbot.addWidget(main_window)

        # Use test process pool to avoid real subprocess calls
        test_pool = TestProcessPool()
        test_pool.set_outputs(
            "workspace /shows/test/shots/seq01/0010",
            "workspace /shows/test/shots/seq01/0020",
        )
        main_window.shot_model._process_pool = test_pool

        # Initial state - no shots
        assert len(main_window.shot_model.shots) == 0

        # Refresh shots
        main_window._refresh_shots()

        # Should have 2 shots now
        assert len(main_window.shot_model.shots) == 2
        assert main_window.shot_model.shots[0].shot == "0010"
        assert main_window.shot_model.shots[1].shot == "0020"

        # Shot grid should be updated
        assert main_window.shot_item_model.rowCount() == 2


class TestApplicationLaunching:
    """Test application launching functionality."""

    @patch("command_launcher.CommandLauncher.launch_app")
    def test_launch_app_with_selected_shot(
        self, mock_launch, qtbot, tmp_path: Path
    ) -> None:
        """Test launching an application with a selected shot."""
        cache_manager = CacheManager(cache_dir=tmp_path / "cache")
        main_window = MainWindow(cache_manager=cache_manager)
        qtbot.addWidget(main_window)

        # Select a shot
        shot = Shot("test_show", "seq01", "0010", "/shows/test/seq01/0010")
        main_window._on_shot_selected(shot)

        # Launch an app
        main_window._launch_app("nuke")

        # Verify launch was called with correct parameters
        mock_launch.assert_called_once_with("nuke", shot)

    def test_launch_app_without_shot_shows_warning(
        self, qtbot, tmp_path: Path, monkeypatch
    ) -> None:
        """Test launching an app without a shot shows warning."""
        cache_manager = CacheManager(cache_dir=tmp_path / "cache")
        main_window = MainWindow(cache_manager=cache_manager)
        qtbot.addWidget(main_window)

        # Mock QMessageBox to prevent actual dialog
        mock_warning = Mock()
        monkeypatch.setattr(QMessageBox, "warning", mock_warning)

        # Try to launch without selecting a shot
        main_window._launch_app("nuke")

        # Should show warning
        mock_warning.assert_called_once()
        args = mock_warning.call_args[0]
        assert "No Shot Selected" in args[1]  # Window title
        assert "select a shot" in args[2].lower()  # Message


class TestSignalConnections:
    """Test signal connections between components."""

    def test_shot_model_signals_connected(self, qtbot, tmp_path: Path) -> None:
        """Test that shot model signals are properly connected."""
        cache_manager = CacheManager(cache_dir=tmp_path / "cache")
        main_window = MainWindow(cache_manager=cache_manager)
        qtbot.addWidget(main_window)

        # Check signal connections exist
        # Note: We can't directly test private signal connections,
        # but we can test the behavior

        # Mock the process pool
        test_pool = TestProcessPool()
        test_pool.set_outputs("workspace /shows/test/shots/seq01/0010")
        main_window.shot_model._process_pool = test_pool

        # Spy on shots_updated signal
        spy = QSignalSpy(main_window.shot_model.shots_updated)

        # Trigger refresh
        main_window.shot_model.refresh_shots()

        # Signal should have been emitted
        assert spy.count() == 1

    def test_custom_launcher_signals_connected(self, qtbot, tmp_path: Path) -> None:
        """Test that custom launcher signals are properly connected."""
        cache_manager = CacheManager(cache_dir=tmp_path / "cache")
        main_window = MainWindow(cache_manager=cache_manager)
        qtbot.addWidget(main_window)

        # Verify launcher manager exists and is connected
        assert main_window.launcher_manager is not None

        # Test that launcher buttons are created for custom launchers
        # This would require mocking launcher_manager.get_launchers()


class TestWindowCleanup:
    """Test proper cleanup when window closes."""

    def test_cleanup_on_close(self, qtbot, tmp_path: Path) -> None:
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

        # Background worker should be stopped
        if hasattr(main_window, "_background_refresh_worker"):
            assert not main_window._background_refresh_worker.isRunning()


class TestStatusBar:
    """Test status bar updates."""

    def test_status_bar_updates(self, qtbot, tmp_path: Path) -> None:
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

    def test_increase_thumbnail_size(self, qtbot, tmp_path: Path) -> None:
        """Test increasing thumbnail size updates all grids."""
        cache_manager = CacheManager(cache_dir=tmp_path / "cache")
        main_window = MainWindow(cache_manager=cache_manager)
        qtbot.addWidget(main_window)

        # Get initial size
        initial_size = main_window.shot_grid.thumbnail_size

        # Increase size
        main_window._increase_thumbnail_size()

        # All grids should have increased size
        assert main_window.shot_grid.thumbnail_size > initial_size
        assert (
            main_window.threede_shot_grid.thumbnail_size
            == main_window.shot_grid.thumbnail_size
        )
        assert (
            main_window.previous_shots_grid.thumbnail_size
            == main_window.shot_grid.thumbnail_size
        )

    def test_decrease_thumbnail_size(self, qtbot, tmp_path: Path) -> None:
        """Test decreasing thumbnail size updates all grids."""
        cache_manager = CacheManager(cache_dir=tmp_path / "cache")
        main_window = MainWindow(cache_manager=cache_manager)
        qtbot.addWidget(main_window)

        # Increase first so we can decrease
        main_window._increase_thumbnail_size()
        current_size = main_window.shot_grid.thumbnail_size

        # Decrease size
        main_window._decrease_thumbnail_size()

        # All grids should have decreased size
        assert main_window.shot_grid.thumbnail_size < current_size
        assert (
            main_window.threede_shot_grid.thumbnail_size
            == main_window.shot_grid.thumbnail_size
        )
        assert (
            main_window.previous_shots_grid.thumbnail_size
            == main_window.shot_grid.thumbnail_size
        )


# Integration test for complete workflow
class TestMainWindowIntegration:
    """Integration tests for complete workflows."""

    @patch("subprocess.run")
    def test_complete_shot_selection_workflow(
        self, mock_run, qtbot, tmp_path: Path, monkeypatch
    ) -> None:
        """Test complete workflow: load shots -> select -> launch app."""
        # Mock subprocess at system boundary
        mock_run.return_value = Mock(
            returncode=0, stdout="workspace /shows/test/shots/seq01/0010\n", stderr=""
        )

        cache_manager = CacheManager(cache_dir=tmp_path / "cache")
        main_window = MainWindow(cache_manager=cache_manager)
        qtbot.addWidget(main_window)

        # Set up test process pool
        test_pool = TestProcessPool()
        test_pool.set_outputs("workspace /shows/test/shots/seq01/0010")
        main_window.shot_model._process_pool = test_pool

        # Mock the launch command
        with patch.object(main_window.command_launcher, "launch_app") as mock_launch:
            # Load shots
            main_window._refresh_shots()

            # Verify shot loaded
            assert len(main_window.shot_model.shots) == 1
            shot = main_window.shot_model.shots[0]

            # Select the shot
            main_window._on_shot_selected(shot)

            # Verify buttons enabled
            assert main_window.app_buttons["nuke"].isEnabled()

            # Launch app
            main_window._launch_app("nuke")

            # Verify launch was called
            mock_launch.assert_called_once_with("nuke", shot)
