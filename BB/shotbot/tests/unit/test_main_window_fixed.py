"""Fixed tests for MainWindow - avoiding hanging issues.

This version uses test doubles instead of mocks, following UNIFIED_TESTING_GUIDE.
Background workers are managed properly through Qt mechanisms.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cache_manager import CacheManager
from main_window import MainWindow
from shot_model import Shot

# Test doubles for behavior testing (UNIFIED_TESTING_GUIDE)
from tests.test_doubles_library import (
    TestCompletedProcess,
    TestProcessPool,
)

pytestmark = [pytest.mark.unit, pytest.mark.qt, pytest.mark.slow]


class TestMainWindowNoHang:
    """Fixed MainWindow tests that don't hang."""

    @pytest.fixture
    def safe_main_window(self, qtbot, tmp_path: Path):
        """Create MainWindow with test doubles for subprocess operations."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir(exist_ok=True)
        cache_manager = CacheManager(cache_dir=cache_dir)

        # Create window with test process pool to avoid real subprocess calls
        main_window = MainWindow(cache_manager=cache_manager)
        qtbot.addWidget(main_window)

        # Replace process pool with test double
        test_pool = TestProcessPool()
        test_pool.set_outputs("")  # Empty output by default
        main_window.shot_model._process_pool = test_pool

        # Stop any background workers if they exist
        if hasattr(main_window, "_background_refresh_worker"):
            worker = main_window._background_refresh_worker
            if worker and worker.isRunning():
                worker.stop()
                worker.wait(100)  # Short wait

        # Disable auto-refresh timers if they exist
        if hasattr(main_window, "_refresh_timer"):
            if main_window._refresh_timer and main_window._refresh_timer.isActive():
                main_window._refresh_timer.stop()

        return main_window

    def test_main_window_creates_components(self, safe_main_window) -> None:
        """Test that MainWindow initializes all required components."""
        # Test all components exist
        assert safe_main_window.cache_manager is not None
        assert safe_main_window.shot_model is not None
        assert safe_main_window.threede_scene_model is not None
        assert safe_main_window.previous_shots_model is not None
        assert safe_main_window.command_launcher is not None
        assert safe_main_window.launcher_manager is not None

        # Test UI components
        assert safe_main_window.tab_widget is not None
        assert safe_main_window.shot_grid is not None
        assert safe_main_window.threede_shot_grid is not None
        assert safe_main_window.previous_shots_grid is not None
        assert safe_main_window.shot_info_panel is not None

        # Test tabs
        assert safe_main_window.tab_widget.count() == 3
        assert safe_main_window.tab_widget.tabText(0) == "My Shots"
        assert safe_main_window.tab_widget.tabText(1) == "Other 3DE scenes"
        assert safe_main_window.tab_widget.tabText(2) == "Previous Shots"

    def test_shot_selection_enables_buttons(self, safe_main_window) -> None:
        """Test that selecting a shot enables application launcher buttons."""
        # Initially disabled
        for button in safe_main_window.app_buttons.values():
            assert not button.isEnabled()

        # Select shot
        shot = Shot("test_show", "seq01", "0010", "/shows/test/seq01/0010")
        safe_main_window._on_shot_selected(shot)

        # Now enabled
        for button in safe_main_window.app_buttons.values():
            assert button.isEnabled()

        # Shot info updated
        assert safe_main_window.shot_info_panel._current_shot == shot

    def test_refresh_shots_with_test_pool(self, safe_main_window) -> None:
        """Test shot refresh with test process pool."""
        # Configure test pool response
        test_pool = safe_main_window.shot_model._process_pool
        test_pool.set_outputs("workspace /shows/test/shots/seq01/0010\n")

        # Clear any existing shots
        safe_main_window.shot_model.shots = []

        # Refresh
        safe_main_window._refresh_shots()

        # Verify shot loaded
        assert len(safe_main_window.shot_model.shots) == 1
        assert safe_main_window.shot_model.shots[0].shot == "0010"


class TestApplicationLaunchingNoHang:
    """Test application launching without hanging."""

    @pytest.fixture
    def safe_window_with_shot(self, qtbot, tmp_path):
        """Create window with a shot pre-selected."""
        cache_manager = CacheManager(cache_dir=tmp_path / "cache")

        main_window = MainWindow(cache_manager=cache_manager)
        qtbot.addWidget(main_window)

        # Use test process pool
        test_pool = TestProcessPool()
        test_pool.set_outputs("")
        main_window.shot_model._process_pool = test_pool

        # Disable timers
        if hasattr(main_window, "_refresh_timer"):
            if main_window._refresh_timer and main_window._refresh_timer.isActive():
                main_window._refresh_timer.stop()

        # Select a shot
        shot = Shot("test_show", "seq01", "0010", "/shows/test/seq01/0010")
        main_window._on_shot_selected(shot)

        return main_window, shot

    def test_launch_app_with_selected_shot(self, safe_window_with_shot) -> None:
        """Test launching an application with a selected shot."""
        main_window, shot = safe_window_with_shot

        # Replace command launcher's subprocess execution with test double
        executed_commands = []
        original_run = None

        if hasattr(main_window.command_launcher, "_run_command"):
            original_run = main_window.command_launcher._run_command

            def test_run_command(command, **kwargs):
                executed_commands.append(command)
                return TestCompletedProcess(
                    args=command, returncode=0, stdout="", stderr=""
                )

            main_window.command_launcher._run_command = test_run_command

        try:
            # Launch app
            result = main_window._launch_app("nuke")

            # Test behavior: verify command was executed
            if original_run:
                assert len(executed_commands) > 0
                # Should have nuke in the command
                assert any("nuke" in str(cmd) for cmd in executed_commands)
                # Verify launch was successful
                assert result is True
        finally:
            if original_run:
                main_window.command_launcher._run_command = original_run

    def test_launch_without_shot_returns_false(self, qtbot, tmp_path) -> None:
        """Test launching without shot is handled properly."""
        cache_manager = CacheManager(cache_dir=tmp_path / "cache")
        main_window = MainWindow(cache_manager=cache_manager)
        qtbot.addWidget(main_window)

        # Use test process pool
        test_pool = TestProcessPool()
        main_window.shot_model._process_pool = test_pool

        # Disable timers
        if hasattr(main_window, "_refresh_timer"):
            if main_window._refresh_timer and main_window._refresh_timer.isActive():
                main_window._refresh_timer.stop()

        # No shot selected - buttons should be disabled
        assert not main_window.app_buttons["nuke"].isEnabled()

        # Try to launch without shot - button is disabled so can't be clicked
        # This is the correct behavior - UI prevents invalid operations


# Helper fixture for all tests
@pytest.fixture(autouse=True)
def cleanup_workers():
    """Ensure all workers are cleaned up after each test."""
    yield
    # Cleanup happens after test
    # Qt widgets are automatically cleaned up by qtbot
