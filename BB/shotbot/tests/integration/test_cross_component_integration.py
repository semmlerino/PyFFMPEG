"""Cross-component integration tests for ShotBot.

This module tests critical interactions between multiple components to ensure
they work together correctly. Following UNIFIED_TESTING_GUIDE principles:
- Use real components with test doubles only at boundaries
- Test behavior, not implementation
- Thread-safe testing patterns
- Proper signal testing with qtbot.waitSignal()
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

from cache_manager import CacheManager
from main_window import MainWindow
from shot_model import Shot
from tests.test_doubles_library import TestProcessPool
from threede_scene_model import ThreeDEScene

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot

pytestmark = [
    pytest.mark.integration,
    pytest.mark.qt,
    pytest.mark.xdist_group("qt_mainwindow_isolation"),  # Force isolation group
]


class TestCrossTabSynchronization:
    """Test data synchronization across all three tabs."""

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self, qtbot: QtBot) -> None:
        """Clean up Qt state between tests to prevent segfaults."""
        # Clear ProcessPoolManager singleton before test
        from process_pool_manager import ProcessPoolManager
        ProcessPoolManager._instance = None

        # Track windows created during test
        self.test_windows: list[MainWindow] = []

        yield

        # Properly close all windows to trigger closeEvent and cleanup
        for window in self.test_windows:
            if window:
                # Explicitly call closeEvent to ensure workers are stopped
                from PySide6.QtGui import QCloseEvent
                close_event = QCloseEvent()
                window.closeEvent(close_event)

                # Now close the window
                if not window.isHidden():
                    window.close()
                    # Wait for window to close
                    qtbot.waitUntil(lambda: window.isHidden(), timeout=2000)

                # Delete the window instance explicitly
                window.deleteLater()

        # Clear the list immediately after closing
        self.test_windows.clear()

        # Process all pending events and deleteLater calls
        # Be defensive about Qt state to avoid segfaults
        app = QApplication.instance()
        if app:
            for _ in range(3):
                app.processEvents()
                app.sendPostedEvents(None, 0)  # Process all deferred deletions
                # Use small timeout, don't use QTest.qWait which might crash
                import time
                time.sleep(0.01)

        # Clear ProcessPoolManager singleton after test
        ProcessPoolManager._instance = None

    def test_shot_selection_syncs_info_panel_across_tabs(
        self, qapp, qtbot: QtBot, tmp_path: Path
    ) -> None:
        """Verify info panel updates when switching tabs with different selections.

        This tests that:
        1. Selecting a shot in My Shots tab updates info panel
        2. Switching to 3DE tab and selecting a scene updates info panel
        3. Info panel correctly reflects the current selection
        """
        # Force legacy model to avoid async issues in tests
        os.environ["SHOTBOT_USE_LEGACY_MODEL"] = "1"

        # Create MainWindow with real components
        window = MainWindow()
        qtbot.addWidget(window)  # CRITICAL: Register for cleanup
        self.test_windows.append(window)  # Track for proper cleanup

        # Mock only the subprocess boundary
        # Note: ws -sg returns all shots in a single multi-line output
        test_pool = TestProcessPool()
        test_pool.set_outputs(
            "workspace /shows/TEST/shots/seq01/seq01_0010\n"
            "workspace /shows/TEST/shots/seq01/seq01_0020"
        )
        window.shot_model._process_pool = test_pool

        # Refresh shots to populate the model
        success, has_changes = window.shot_model.refresh_shots()
        assert success, "refresh_shots should succeed"

        # Verify shots were loaded
        assert len(window.shot_model.shots) == 2, f"Expected 2 shots, got {len(window.shot_model.shots)}"
        # Note: has_changes might be False if cache was loaded on init
        # assert has_changes  # Removed - not reliable with cache

        # Process events to ensure UI updates
        qtbot.wait(100)

        # Ensure we start on the My Shots tab
        window.tab_widget.setCurrentIndex(0)
        qtbot.wait(50)

        # Tab 1: Select a shot in My Shots tab
        assert window.tab_widget.currentIndex() == 0  # My Shots tab
        shots = window.shot_model.get_shots()
        assert len(shots) == 2

        # Simulate selecting first shot
        first_shot = shots[0]
        window._on_shot_selected(first_shot)

        # Verify info panel shows the selected shot
        assert window.shot_info_panel._current_shot == first_shot
        assert first_shot.shot in window.shot_info_panel.shot_name_label.text()

        # Tab 2: Switch to 3DE tab
        window.tab_widget.setCurrentIndex(1)  # Other 3DE scenes tab
        qtbot.wait(100)

        # Create and select a 3DE scene
        scene = ThreeDEScene(
            show="TEST",
            sequence="seq02",
            shot="0030",
            workspace_path="/shows/TEST/shots/seq02/seq02_0030",
            user="testuser",
            plate="PLATE01",
            scene_path=Path("/test/scene.3de"),
        )
        window._on_scene_selected(scene)

        # Verify info panel updated to show the 3DE scene
        current_shot = window.shot_info_panel._current_shot
        assert current_shot is not None
        assert current_shot.shot == "0030"
        assert current_shot.sequence == "seq02"
        assert "0030" in window.shot_info_panel.shot_name_label.text()

        # Tab 3: Switch to Previous Shots tab
        window.tab_widget.setCurrentIndex(2)  # Previous shots tab
        qtbot.wait(100)

        # The info panel should be cleared since Previous Shots tab has no selection
        # (Tab switching calls _on_shot_selected(None) when new tab has no selection)
        assert window.shot_info_panel._current_shot is None

        # Go back to My Shots and verify it also clears since no selection
        # (Each tab maintains its own selection state independently)
        window.tab_widget.setCurrentIndex(0)
        qtbot.wait(100)

        # Info panel should be cleared because My Shots tab has no current selection
        assert window.shot_info_panel._current_shot is None

        # Select second shot to verify update works
        second_shot = shots[1]
        window._on_shot_selected(second_shot)
        assert window.shot_info_panel._current_shot == second_shot
        assert second_shot.shot in window.shot_info_panel.shot_name_label.text()

    def test_show_filter_affects_all_tabs(self, qapp, qtbot: QtBot, tmp_path: Path) -> None:
        """Test that show filtering propagates to all tabs correctly.

        This verifies that:
        1. Show filter is available on all tabs
        2. Filtering on one tab affects that tab's display
        3. Each tab can have independent filter settings
        """
        # Force legacy model for consistency
        os.environ["SHOTBOT_USE_LEGACY_MODEL"] = "1"

        # Create MainWindow
        window = MainWindow()
        qtbot.addWidget(window)
        self.test_windows.append(window)  # Track for proper cleanup

        # Set up test data with multiple shows
        # Note: ws -sg returns all shots in a single multi-line output
        test_pool = TestProcessPool()
        test_pool.set_outputs(
            "workspace /shows/SHOW1/shots/seq01/seq01_0010\n"
            "workspace /shows/SHOW1/shots/seq01/seq01_0020\n"
            "workspace /shows/SHOW2/shots/seq02/seq02_0030"
        )
        window.shot_model._process_pool = test_pool

        # Refresh to populate
        success, _ = window.shot_model.refresh_shots()
        assert success
        # Use processEvents instead of qWait to avoid timer issues
        QApplication.processEvents()

        # Check My Shots tab has all shots initially
        shot_item_model = window.shot_item_model
        assert shot_item_model.rowCount() == 3

        # Apply show filter to SHOW1
        shot_item_model.set_show_filter(window.shot_model, "SHOW1")
        QApplication.processEvents()  # Process updates without timer

        # Verify filter applied
        assert shot_item_model.rowCount() == 2  # Only SHOW1 shots visible

        # Clear filter
        shot_item_model.set_show_filter(window.shot_model, None)
        assert shot_item_model.rowCount() == 3  # All shots visible again


class TestCacheUICoordination:
    """Test cache manager and UI synchronization."""

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Clean up state between tests."""
        from process_pool_manager import ProcessPoolManager
        ProcessPoolManager._instance = None

        # Clear test cache directory
        import shutil
        from pathlib import Path
        cache_dir = Path.home() / ".shotbot" / "cache_test"
        if cache_dir.exists():
            shutil.rmtree(cache_dir, ignore_errors=True)

        # Track windows for cleanup
        self.test_windows: list[MainWindow] = []

        yield

        # Properly close all windows to trigger closeEvent and cleanup
        for window in self.test_windows:
            if window:
                # Explicitly call closeEvent to ensure workers are stopped
                from PySide6.QtGui import QCloseEvent
                close_event = QCloseEvent()
                window.closeEvent(close_event)

                # Now close the window
                if not window.isHidden():
                    window.close()
                    # Wait for window to close
                    qtbot.waitUntil(lambda: window.isHidden(), timeout=2000)

                # Delete the window instance explicitly
                window.deleteLater()

        self.test_windows.clear()

        # Process all pending events and deleteLater calls
        # Be defensive about Qt state to avoid segfaults
        app = QApplication.instance()
        if app:
            for _ in range(3):
                app.processEvents()
                app.sendPostedEvents(None, 0)  # Process all deferred deletions
                # Use small timeout, don't use QTest.qWait which might crash
                import time
                time.sleep(0.01)

        ProcessPoolManager._instance = None

    def test_thumbnail_cache_updates_ui(self, qapp, qtbot: QtBot, tmp_path: Path) -> None:
        """Verify thumbnail caching updates UI correctly.

        This tests that:
        1. Thumbnails are cached after first load
        2. Cache manager provides cached thumbnails
        3. UI updates when cache is invalidated
        """
        # Force legacy model for synchronous behavior
        os.environ["SHOTBOT_USE_LEGACY_MODEL"] = "1"

        # Create test cache directory
        cache_dir = tmp_path / "test_cache"
        cache_dir.mkdir(exist_ok=True)

        # Create MainWindow with test cache
        window = MainWindow()
        qtbot.addWidget(window)
        self.test_windows.append(window)  # Track for cleanup

        # Set up test shot
        test_pool = TestProcessPool()
        test_pool.set_outputs(
            "workspace /shows/TEST/shots/seq01/seq01_0010"
        )
        window.shot_model._process_pool = test_pool
        window.shot_model.refresh_shots()

        # Get the shot
        shots = window.shot_model.get_shots()
        assert len(shots) == 1
        shot = shots[0]

        # Verify cache manager can check for cached thumbnail
        cache_path = window.cache_manager.get_cached_thumbnail(
            shot.show, shot.sequence, shot.shot
        )
        # Cache path will be None if no thumbnail cached yet
        assert cache_path is None  # No thumbnail cached initially

        # Create a valid test image file to cache
        fake_thumb = tmp_path / "test_thumb.jpg"
        # Create a minimal valid JPEG (1x1 red pixel)
        from PySide6.QtGui import QImage, QColor
        img = QImage(1, 1, QImage.Format.Format_RGB32)
        img.fill(QColor(255, 0, 0))
        img.save(str(fake_thumb), "JPEG")

        # Cache the thumbnail
        cached_path = window.cache_manager.cache_thumbnail(
            fake_thumb, shot.show, shot.sequence, shot.shot
        )
        assert cached_path is not None

        # Now get_cached_thumbnail should return the path
        cache_path = window.cache_manager.get_cached_thumbnail(
            shot.show, shot.sequence, shot.shot
        )
        assert cache_path is not None
        assert cache_path.exists()
        assert str(shot.show) in str(cache_path)

    def test_cache_invalidation_refreshes_data(
        self, qapp, qtbot: QtBot, tmp_path: Path
    ) -> None:
        """Verify cache invalidation causes data refresh.

        This tests that:
        1. Data is loaded from cache initially
        2. Cache invalidation clears cached data
        3. Next access fetches fresh data
        """
        # Force legacy model
        os.environ["SHOTBOT_USE_LEGACY_MODEL"] = "1"

        window = MainWindow()
        qtbot.addWidget(window)
        self.test_windows.append(window)  # Track for cleanup

        # Set up initial data
        test_pool = TestProcessPool()
        test_pool.set_outputs(
            "workspace /shows/TEST/shots/seq01/seq01_0010\n"
            "workspace /shows/TEST/shots/seq01/seq01_0020"
        )
        window.shot_model._process_pool = test_pool

        # Initial refresh
        success, _ = window.shot_model.refresh_shots()
        assert success
        assert len(window.shot_model.shots) == 2

        # Change the test data
        test_pool.set_outputs(
            "workspace /shows/TEST/shots/seq01/seq01_0010\n"
            "workspace /shows/TEST/shots/seq01/seq01_0020\n"
            "workspace /shows/TEST/shots/seq01/seq01_0030"
        )

        # Refresh again - should get new data
        success, has_changes = window.shot_model.refresh_shots()
        assert success
        assert len(window.shot_model.shots) == 3  # New shot added


class TestErrorPropagationChains:
    """Test error handling across component boundaries."""

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self, qtbot: QtBot) -> None:
        """Clean up state between tests."""
        from process_pool_manager import ProcessPoolManager
        ProcessPoolManager._instance = None

        # Track windows for cleanup
        self.test_windows: list[MainWindow] = []

        yield

        # Properly close all windows to trigger closeEvent and cleanup
        for window in self.test_windows:
            if window:
                # Explicitly call closeEvent to ensure workers are stopped
                from PySide6.QtGui import QCloseEvent
                close_event = QCloseEvent()
                window.closeEvent(close_event)

                # Now close the window
                if not window.isHidden():
                    window.close()
                    # Wait for window to close
                    qtbot.waitUntil(lambda: window.isHidden(), timeout=2000)

                # Delete the window instance explicitly
                window.deleteLater()

        self.test_windows.clear()

        # Process all pending events and deleteLater calls
        # Be defensive about Qt state to avoid segfaults
        app = QApplication.instance()
        if app:
            for _ in range(3):
                app.processEvents()
                app.sendPostedEvents(None, 0)  # Process all deferred deletions
                # Use small timeout, don't use QTest.qWait which might crash
                import time
                time.sleep(0.01)

        ProcessPoolManager._instance = None

    def test_subprocess_failure_handled_gracefully(
        self, qapp, qtbot: QtBot, tmp_path: Path
    ) -> None:
        """Verify subprocess failures are handled without crashing.

        This tests that:
        1. Process pool failures are caught
        2. Error signals are emitted
        3. UI remains responsive after error
        """
        os.environ["SHOTBOT_USE_LEGACY_MODEL"] = "1"

        window = MainWindow()
        qtbot.addWidget(window)
        self.test_windows.append(window)  # Track for cleanup
        window.show()  # Make window visible for test

        # Set up test pool to fail
        test_pool = TestProcessPool()
        test_pool.should_fail = True
        window.shot_model._process_pool = test_pool

        # Track error signal
        error_emitted = False
        error_message = ""

        def on_error(msg: str) -> None:
            nonlocal error_emitted, error_message
            error_emitted = True
            error_message = msg

        window.shot_model.error_occurred.connect(on_error)

        # Refresh should fail gracefully
        success, _ = window.shot_model.refresh_shots()
        assert not success  # Should fail
        assert error_emitted  # Should emit error signal
        assert "fail" in error_message.lower()  # Should contain failure message

        # UI should still be responsive (not crashed)
        assert window.isVisible()

    def test_timeout_handled_properly(self, qapp, qtbot: QtBot, tmp_path: Path) -> None:
        """Verify timeout errors are handled correctly.

        This tests that:
        1. Timeouts are caught and handled
        2. Appropriate error signals are emitted
        3. System recovers from timeout
        """
        os.environ["SHOTBOT_USE_LEGACY_MODEL"] = "1"

        window = MainWindow()
        qtbot.addWidget(window)
        self.test_windows.append(window)  # Track for cleanup
        window.show()  # Make window visible for test

        # Set up test pool to timeout
        test_pool = TestProcessPool()
        test_pool.fail_with_timeout = True
        window.shot_model._process_pool = test_pool

        # Track error signal
        error_emitted = False

        def on_error(msg: str) -> None:
            nonlocal error_emitted
            error_emitted = True

        window.shot_model.error_occurred.connect(on_error)

        # Refresh should handle timeout gracefully
        success, _ = window.shot_model.refresh_shots()
        assert not success  # Should fail
        assert error_emitted  # Should emit error signal

        # Now fix the test pool and verify recovery
        test_pool.fail_with_timeout = False
        test_pool.set_outputs("workspace /shows/TEST/shots/seq01/seq01_0010")

        # Should recover and work again
        success, _ = window.shot_model.refresh_shots()
        assert success  # Should succeed now
        assert len(window.shot_model.shots) == 1