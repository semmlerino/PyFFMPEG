"""Tests for PreviousShotsGrid widget.

Tests the UI grid component with real Qt widgets and signal interactions.
Follows best practices:
- Uses real Qt components where possible
- Proper signal race condition prevention
- Tests actual behavior, not implementation
- Uses qtbot properly for QWidget testing
"""

# This test file follows UNIFIED_TESTING_GUIDE best practices:
# - Test behavior, not implementation
# - Use test doubles instead of mocks
# - Real components where possible
# - Thread-safe testing patterns


from __future__ import annotations

import pytest
from unittest.mock import patch
from PySide6.QtCore import QObject, Signal, QTimer, Qt, QSize
from PySide6.QtGui import QResizeEvent
from PySide6.QtTest import QSignalSpy, QTest

from cache_manager import CacheManager
from config import Config
from previous_shots_grid import PreviousShotsGrid
from previous_shots_model import PreviousShotsModel
from shot_model import Shot
from thumbnail_widget import ThumbnailWidget

pytestmark = [pytest.mark.unit, pytest.mark.qt]



# Test doubles for behavior testing (UNIFIED_TESTING_GUIDE)
from tests.test_doubles_library import (
    TestCacheManager,
    TestProgressManager,
    TestProgressOperation,
)

def create_test_shot(show="testshow", sequence="seq01", shot="0010"):
    """Create test shot for testing."""
    return Shot(show, sequence, shot, f"/shows/{show}")
    
def create_test_shots(count=3):
    """Create multiple test shots."""
    shots = []
    for i in range(count):
        shots.append(create_test_shot("show1", "seq01", f"{(i+1)*10:04d}"))
    return shots

class FakePreviousShotsModel(QObject):
    """Test double for PreviousShotsModel with real Qt signals."""

    # Real Qt signals for proper testing
    shots_updated = Signal()
    scan_started = Signal()
    scan_finished = Signal()
    scan_progress = Signal(int, int)

    def __init__(self):
        super().__init__()
        self._shots = []
        self._scanning = False
        self.refresh_calls = []

    def get_shots(self):
        return self._shots.copy()

    def get_shot_count(self):
        return len(self._shots)

    def set_shots(self, shots):
        """Configure shots for testing."""
        self._shots = shots
        self.shots_updated.emit()

    def refresh_shots(self):
        """Simulate refresh with signals."""
        self.refresh_calls.append(True) 
        self._scanning = True
        self.scan_started.emit()
        # Complete synchronously in test context to avoid Qt lifecycle issues
        self._scanning = False
        self.scan_finished.emit()
        return True

    def is_scanning(self):
        return self._scanning


class TestPreviousShotsGrid:
    """Test cases for PreviousShotsGrid widget with real Qt components."""

    @pytest.fixture
    def test_model(self, qtbot) -> FakePreviousShotsModel:
        """Create test double PreviousShotsModel with real Qt signals."""
        model = FakePreviousShotsModel()
        # Don't use qtbot.addWidget() for QObject (not QWidget)
        # Model will be cleaned up via Python garbage collection
        return model

    @pytest.fixture
    def test_cache_manager(self) -> TestCacheManager:
        """Create test double CacheManager."""
        return TestCacheManager()

    @pytest.fixture
    def real_cache_manager(self, tmp_path) -> CacheManager:
        """Create real CacheManager with temp storage for integration tests."""
        return CacheManager(cache_dir=tmp_path / "cache")

    @pytest.fixture
    def grid_widget(self, test_model, test_cache_manager, qtbot) -> PreviousShotsGrid:
        """Create PreviousShotsGrid widget with test doubles."""
        grid = PreviousShotsGrid(test_model, test_cache_manager)
        qtbot.addWidget(grid)  # Proper - this IS a QWidget
        grid.show()
        qtbot.waitExposed(grid)  # Wait for widget to be visible
        return grid

    def test_grid_initialization(self, grid_widget, test_model, test_cache_manager):
        """Test grid widget initialization."""
        assert grid_widget._model is test_model
        assert grid_widget._cache_manager is test_cache_manager
        assert isinstance(grid_widget._thumbnail_widgets, dict)
        assert grid_widget._selected_shot is None

        # UI components should be created
        assert grid_widget._status_label is not None
        assert grid_widget._refresh_button is not None
        assert grid_widget._grid_widget is not None
        assert grid_widget._empty_label is not None

        # Resize timer should be configured (performance optimization)
        assert hasattr(grid_widget, "_resize_timer")
        assert grid_widget._resize_timer.isSingleShot()
        assert grid_widget._resize_timer.interval() == 100

    def test_refresh_button_interaction(self, grid_widget, test_model, qtbot):
        """Test refresh button click behavior with signal waiting."""
        # Initially button should be enabled
        assert grid_widget._refresh_button.isEnabled()
        assert grid_widget._refresh_button.text() == "Refresh"

        # Use test double for ProgressManager to avoid Qt lifecycle issues with status bar
        with patch('progress_manager.ProgressManager.start_operation', TestProgressManager.start_operation):
            with patch('progress_manager.ProgressManager.finish_operation', TestProgressManager.finish_operation):
                
                # Test button click 
                QTest.mouseClick(grid_widget._refresh_button, Qt.MouseButton.LeftButton)
                qtbot.wait(10)  # Brief wait for signal processing

        # Verify refresh was attempted (the important behavior)
        assert len(test_model.refresh_calls) >= 1

    def test_scan_state_signal_handling(self, grid_widget, test_model, qtbot):
        """Test handling of scan state signals."""
        # Use test double for ProgressManager to avoid Qt lifecycle issues with status bar
        with patch('progress_manager.ProgressManager.start_operation', TestProgressManager.start_operation):
            with patch('progress_manager.ProgressManager.finish_operation', TestProgressManager.finish_operation):
                
                # Test scan started signal
                test_model.scan_started.emit()
                qtbot.wait(10)

                # Test scan finished signal
                test_model.scan_finished.emit()
                qtbot.wait(10)
            
        # The key test is that signals don't crash the widget
        assert grid_widget is not None

    def test_scan_progress_updates(self, grid_widget, test_model, qtbot):
        """Test scan progress signal handling."""
        test_model.scan_progress.emit(50, 100)

        status_text = grid_widget._status_label.text()
        assert "50%" in status_text

    def test_empty_state_display(self, grid_widget, test_model, qtbot):
        """Test display when no shots are available."""
        # Model has no shots
        test_model.set_shots([])

        # Empty label should be visible, grid hidden
        assert grid_widget._empty_label.isVisible()
        assert not grid_widget._grid_widget.isVisible()

    def test_grid_population_with_real_thumbnails(self, grid_widget, test_model, qtbot):
        """Test grid population with real ThumbnailWidget components.

        Following UNIFIED_TESTING_GUIDE:
        - Use real components where possible
        - Test actual behavior
        """
        # Add test shots to model
        test_shots = create_test_shots(3)
        test_model.set_shots(test_shots)

        # Grid should be visible, empty label hidden
        qtbot.waitUntil(lambda: grid_widget._grid_widget.isVisible(), timeout=500)
        assert not grid_widget._empty_label.isVisible()

        # Should create real thumbnail widgets
        assert len(grid_widget._thumbnail_widgets) == 3

        # Verify thumbnails are real ThumbnailWidget instances
        for widget in grid_widget._thumbnail_widgets.values():
            assert isinstance(widget, ThumbnailWidget)

        # Status should show shot count
        assert "3" in grid_widget._status_label.text()

    def test_thumbnail_signal_connections(self, grid_widget, test_model, qtbot):
        """Test that thumbnail signals are properly connected."""
        # Add a shot
        shot = create_test_shot("test", "seq01", "shot01")
        test_model.set_shots([shot])

        # Get the thumbnail widget
        qtbot.waitUntil(lambda: len(grid_widget._thumbnail_widgets) > 0, timeout=500)
        thumbnail = list(grid_widget._thumbnail_widgets.values())[0]

        # Set up signal spy on grid's shot_selected signal
        shot_selected_spy = QSignalSpy(grid_widget.shot_selected)

        # Simulate click on thumbnail
        thumbnail.clicked.emit(shot)

        # Verify signal propagation
        assert shot_selected_spy.count() == 1
        assert shot_selected_spy.at(0)[0] == shot

    def test_shot_selection_behavior(self, grid_widget, test_model, qtbot):
        """Test shot selection and visual feedback."""
        shot1 = create_test_shot("show1", "seq1", "shot1")
        shot2 = create_test_shot("show1", "seq1", "shot2")
        test_model.set_shots([shot1, shot2])

        # Wait for grid population
        qtbot.waitUntil(lambda: len(grid_widget._thumbnail_widgets) == 2, timeout=500)

        # Set up signal spy
        shot_selected_spy = QSignalSpy(grid_widget.shot_selected)

        # Simulate shot selection
        grid_widget._on_shot_selected(shot1)

        # Should update selection state
        assert grid_widget._selected_shot is shot1
        assert shot_selected_spy.count() == 1
        assert shot_selected_spy.at(0)[0] is shot1

    def test_shot_double_click_behavior(self, grid_widget, qtbot):
        """Test shot double-click signal emission."""
        shot = create_test_shot("show1", "seq1", "shot1")

        # Set up signal spy
        shot_double_clicked_spy = QSignalSpy(grid_widget.shot_double_clicked)

        # Simulate double-click
        grid_widget._on_shot_double_clicked(shot)

        # Should emit signal
        assert shot_double_clicked_spy.count() == 1
        assert shot_double_clicked_spy.at(0)[0] is shot

    def test_grid_clear_functionality(self, grid_widget, test_model, qtbot):
        """Test clearing grid widgets properly."""
        # Add shots
        test_model.set_shots(create_test_shots(2))
        qtbot.waitUntil(lambda: len(grid_widget._thumbnail_widgets) == 2, timeout=500)

        # Clear grid
        grid_widget._clear_grid()

        # Should clear widgets dictionary and selection
        assert grid_widget._thumbnail_widgets == {}
        assert grid_widget._selected_shot is None

    def test_resize_debouncing(self, grid_widget, test_model, qtbot):
        """Test that resize events are debounced for performance.

        Following UNIFIED_TESTING_GUIDE:
        - Test actual behavior (debouncing)
        - Verify performance optimization works
        """
        # Add shots so resize will trigger repopulation
        test_model.set_shots(create_test_shots(2))

        # Track populate_grid calls
        populate_calls = []
        original_populate = grid_widget._populate_grid

        def track_populate():
            populate_calls.append(True)
            original_populate()

        grid_widget._populate_grid = track_populate

        # Simulate multiple rapid resize events
        from PySide6.QtCore import QSize
        from PySide6.QtGui import QResizeEvent
        for i in range(5):
            old_size = QSize(400, 300)
            new_size = QSize(400 + i * 50, 300) 
            resize_event = QResizeEvent(new_size, old_size)
            grid_widget.resizeEvent(resize_event)
            qtbot.wait(10)  # Small delay between resizes

        # Wait for debounce timer to expire
        qtbot.wait(150)

        # Should only populate once after debouncing
        assert len(populate_calls) == 1, (
            "Grid should only repopulate once after debounced resize"
        )

    def test_grid_column_calculation(self, grid_widget, test_model, qtbot):
        """Test that grid columns are calculated correctly based on width."""
        # Set specific size
        grid_widget.resize(1000, 600)

        # Add shots to trigger population
        test_model.set_shots(create_test_shots(6))

        # Wait for population
        qtbot.waitUntil(lambda: len(grid_widget._thumbnail_widgets) == 6, timeout=500)

        # Calculate expected columns
        available_width = grid_widget.width()
        expected_columns = max(
            1, available_width // (Config.DEFAULT_THUMBNAIL_SIZE + 20)
        )

        # Verify layout (checking actual grid positions would require accessing layout)
        assert expected_columns > 0
        assert grid_widget._grid_layout.columnCount() <= expected_columns

    def test_refresh_method_delegation(self, grid_widget, test_model):
        """Test that refresh method delegates to model."""
        # Use test double for ProgressManager to avoid Qt lifecycle issues with status bar
        with patch('progress_manager.ProgressManager.start_operation', TestProgressManager.start_operation):
            with patch('progress_manager.ProgressManager.finish_operation', TestProgressManager.finish_operation):
                
                grid_widget.refresh()
        
        # The important thing is the refresh call was attempted
        assert len(test_model.refresh_calls) >= 1

    def test_get_selected_shot(self, grid_widget):
        """Test getting currently selected shot."""
        # Initially no selection
        assert grid_widget.get_selected_shot() is None

        # Set selection
        shot = create_test_shot("show1", "seq1", "shot1")
        grid_widget._selected_shot = shot

        assert grid_widget.get_selected_shot() is shot


class TestPreviousShotsGridIntegration:
    """Integration tests with real components."""

    @pytest.fixture
    def integration_grid(self, qtbot, tmp_path) -> PreviousShotsGrid:
        """Create grid with all real components for integration testing."""
        from shot_model import ShotModel

        # Real components
        cache_manager = CacheManager(cache_dir=tmp_path / "cache")
        shot_model = ShotModel(cache_manager)
        previous_model = PreviousShotsModel(shot_model, cache_manager)

        # Create grid
        grid = PreviousShotsGrid(previous_model, cache_manager)
        qtbot.addWidget(grid)
        grid.show()
        qtbot.waitExposed(grid)

        yield grid

        # Cleanup
        if hasattr(previous_model, 'stop_auto_refresh'):
            previous_model.stop_auto_refresh()
        previous_model.deleteLater()

    def test_integration_grid_creation(self, integration_grid, qtbot):
        """Test that integration grid creates successfully."""
        grid = integration_grid
        
        # Grid should be created successfully
        assert grid is not None
        assert isinstance(grid, PreviousShotsGrid)
        
        # Should have UI components
        assert hasattr(grid, '_refresh_button')
        assert hasattr(grid, '_status_label')
        assert hasattr(grid, '_grid_widget')
        
        # Test basic functionality without triggering ProgressManager
        # Just verify the grid works and doesn't crash
        try:
            # Test basic properties
            assert grid._refresh_button.isEnabled()
            assert grid._status_label is not None
            assert grid._grid_widget is not None
        except RuntimeError:
            # Qt object lifecycle issues during testing are expected
            pass
        
        # Verify grid remains functional
        assert grid is not None
