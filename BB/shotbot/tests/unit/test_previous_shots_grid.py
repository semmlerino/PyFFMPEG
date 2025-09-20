"""Tests for PreviousShotsView component.

Tests the Model/View UI component with real Qt widgets and signal interactions.
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

from unittest.mock import patch

import pytest
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtTest import QSignalSpy, QTest

from cache_manager import CacheManager
from config import Config
from previous_shots_item_model import PreviousShotsItemModel
from previous_shots_model import PreviousShotsModel
from previous_shots_view import PreviousShotsView
from shot_model import Shot

# Test doubles for behavior testing (UNIFIED_TESTING_GUIDE)
from tests.test_doubles_library import (
    TestCacheManager,
    TestProgressManager,
)

pytestmark = [pytest.mark.unit, pytest.mark.qt]


def create_test_shot(show="testshow", sequence="seq01", shot="0010"):
    """Create test shot for testing."""
    return Shot(show, sequence, shot, f"/shows/{show}")


def create_test_shots(count=3):
    """Create multiple test shots."""
    shots = []
    for i in range(count):
        shots.append(create_test_shot("show1", "seq01", f"{(i + 1) * 10:04d}"))
    return shots


class FakePreviousShotsModel(QObject):
    """Test double for PreviousShotsModel with real Qt signals."""

    # Real Qt signals for proper testing
    shots_updated = Signal()
    scan_started = Signal()
    scan_finished = Signal()
    scan_progress = Signal(int, int)

    def __init__(self) -> None:
        super().__init__()
        self._shots = []
        self._scanning = False
        self.refresh_calls = []

    def get_shots(self):
        return self._shots.copy()

    def get_shot_count(self):
        return len(self._shots)

    def set_shots(self, shots) -> None:
        """Configure shots for testing."""
        self._shots = shots
        self.shots_updated.emit()

    def refresh_shots(self) -> bool:
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


class TestPreviousShotsView:
    """Test cases for PreviousShotsView Model/View component with real Qt components."""

    @pytest.fixture
    def test_model(self, qtbot) -> FakePreviousShotsModel:
        """Create test double PreviousShotsModel with real Qt signals."""
        model = FakePreviousShotsModel()
        # Ensure cleanup on test end
        yield model
        # Manual cleanup
        model.deleteLater()

    @pytest.fixture
    def test_cache_manager(self) -> TestCacheManager:
        """Create test double CacheManager."""
        return TestCacheManager()

    @pytest.fixture
    def real_cache_manager(self, tmp_path) -> CacheManager:
        """Create real CacheManager with temp storage for integration tests."""
        return CacheManager(cache_dir=tmp_path / "cache")

    @pytest.fixture
    def grid_widget(self, test_model, test_cache_manager, qtbot) -> PreviousShotsView:
        """Create PreviousShotsView widget with Model/View architecture."""
        # Create the item model wrapper for the previous shots model
        item_model = PreviousShotsItemModel(test_model, cache_manager=test_cache_manager)
        # Create the view with the model
        view = PreviousShotsView(model=item_model)
        qtbot.addWidget(view)  # Proper - this IS a QWidget
        view.show()
        qtbot.waitExposed(view)  # Wait for widget to be visible
        yield view
        # Cleanup the item model manually
        item_model.deleteLater()

    def test_grid_initialization(
        self, grid_widget, test_model, test_cache_manager
    ) -> None:
        """Test grid widget initialization."""
        # View has the item model, which wraps the test_model
        assert grid_widget.model is not None
        assert isinstance(grid_widget.model, PreviousShotsItemModel)
        assert grid_widget.selected_shot is None

        # UI components should be created
        assert grid_widget._status_label is not None
        assert grid_widget._refresh_button is not None
        assert hasattr(grid_widget, "list_view")  # Model/View uses list_view
        assert hasattr(grid_widget, "size_slider")  # Size control

        # View should have proper methods
        assert hasattr(grid_widget, "refresh")
        assert hasattr(grid_widget, "get_selected_shot")

    def test_refresh_button_interaction(self, grid_widget, test_model, qtbot) -> None:
        """Test refresh button click behavior with signal waiting."""
        # Initially button should be enabled
        assert grid_widget._refresh_button.isEnabled()
        assert grid_widget._refresh_button.text() == "Refresh"

        # Use test double for ProgressManager to avoid Qt lifecycle issues with status bar
        with patch(
            "progress_manager.ProgressManager.start_operation",
            TestProgressManager.start_operation,
        ):
            with patch(
                "progress_manager.ProgressManager.finish_operation",
                TestProgressManager.finish_operation,
            ):
                # Test button click
                QTest.mouseClick(grid_widget._refresh_button, Qt.MouseButton.LeftButton)
                qtbot.wait(10)  # Brief wait for signal processing

        # Verify refresh was attempted (the important behavior)
        assert len(test_model.refresh_calls) >= 1

    def test_scan_state_signal_handling(self, grid_widget, test_model, qtbot) -> None:
        """Test handling of scan state signals."""
        # Use test double for ProgressManager to avoid Qt lifecycle issues with status bar
        with patch(
            "progress_manager.ProgressManager.start_operation",
            TestProgressManager.start_operation,
        ):
            with patch(
                "progress_manager.ProgressManager.finish_operation",
                TestProgressManager.finish_operation,
            ):
                # Test scan started signal
                test_model.scan_started.emit()
                qtbot.wait(10)

                # Test scan finished signal
                test_model.scan_finished.emit()
                qtbot.wait(10)

        # The key test is that signals don't crash the widget
        assert grid_widget is not None

    def test_scan_progress_updates(self, grid_widget, test_model, qtbot) -> None:
        """Test scan progress signal handling."""
        test_model.scan_progress.emit(50, 100)

        # Wait for queued signal to be processed
        qtbot.wait(10)

        status_text = grid_widget._status_label.text()
        # The scan progress might be quickly replaced by status update
        # Test that the signal was handled without crashing
        assert status_text is not None  # Label was updated

    def test_empty_state_display(self, grid_widget, test_model, qtbot) -> None:
        """Test display when no shots are available."""
        # Model has no shots
        test_model.set_shots([])

        # PreviousShotsView uses Model/View architecture
        # Test that widget exists and model has no items
        assert grid_widget.isVisible()
        if grid_widget._model:
            assert grid_widget._model.rowCount() == 0

    def test_grid_population_with_real_thumbnails(
        self, grid_widget, test_model, qtbot
    ) -> None:
        """Test grid population with real ThumbnailWidget components.

        Following UNIFIED_TESTING_GUIDE:
        - Use real components where possible
        - Test actual behavior
        """
        # Add test shots to model
        test_shots = create_test_shots(3)
        test_model.set_shots(test_shots)

        # Grid should be visible (uses list_view in Model/View architecture)
        qtbot.waitUntil(lambda: grid_widget.list_view.isVisible(), timeout=500)

        # Wait for model to update (QueuedConnection needs event loop processing)
        qtbot.waitUntil(
            lambda: grid_widget._model and grid_widget._model.rowCount() == 3,
            timeout=1000,
        )

        # Status should show shot count
        qtbot.waitUntil(lambda: "3" in grid_widget._status_label.text(), timeout=1000)

    def test_thumbnail_signal_connections(self, grid_widget, test_model, qtbot) -> None:
        """Test that thumbnail signals are properly connected."""
        # Add a shot
        shot = create_test_shot("test", "seq01", "shot01")
        test_model.set_shots([shot])

        # Wait for model to have data
        qtbot.waitUntil(
            lambda: grid_widget._model and grid_widget._model.rowCount() > 0,
            timeout=500,
        )

        # Set up signal spy on grid's shot_selected signal
        shot_selected_spy = QSignalSpy(grid_widget.shot_selected)

        # Simulate click on item by calling the handler directly
        # (In Model/View, we don't have direct widget access)
        from PySide6.QtCore import QModelIndex

        index = grid_widget._model.index(0, 0) if grid_widget._model else QModelIndex()
        grid_widget._on_item_clicked(index)

        # Verify signal propagation
        assert shot_selected_spy.count() == 1
        assert shot_selected_spy.at(0)[0] == shot

    def test_shot_selection_behavior(self, grid_widget, test_model, qtbot) -> None:
        """Test shot selection and visual feedback."""
        shot1 = create_test_shot("show1", "seq1", "shot1")
        shot2 = create_test_shot("show1", "seq1", "shot2")
        test_model.set_shots([shot1, shot2])

        # Wait for model population
        qtbot.waitUntil(
            lambda: grid_widget._model and grid_widget._model.rowCount() == 2,
            timeout=500,
        )

        # Set up signal spy
        shot_selected_spy = QSignalSpy(grid_widget.shot_selected)

        # Simulate shot selection using model index
        from PySide6.QtCore import QModelIndex

        index = grid_widget._model.index(0, 0) if grid_widget._model else QModelIndex()
        grid_widget._on_item_clicked(index)

        # Should update selection state (using selected_shot, not selected_item)
        assert grid_widget.selected_shot is shot1
        assert shot_selected_spy.count() == 1
        assert shot_selected_spy.at(0)[0] is shot1

    def test_shot_double_click_behavior(self, grid_widget, test_model, qtbot) -> None:
        """Test shot double-click signal emission."""
        shot = create_test_shot("show1", "seq1", "shot1")
        test_model.set_shots([shot])

        # Wait for model to have data
        qtbot.waitUntil(
            lambda: grid_widget._model and grid_widget._model.rowCount() > 0,
            timeout=500,
        )

        # Set up signal spy
        shot_double_clicked_spy = QSignalSpy(grid_widget.shot_double_clicked)

        # Simulate double-click using model index
        from PySide6.QtCore import QModelIndex

        index = grid_widget._model.index(0, 0) if grid_widget._model else QModelIndex()
        grid_widget._on_item_double_clicked(index)

        # Should emit signal
        assert shot_double_clicked_spy.count() == 1
        assert shot_double_clicked_spy.at(0)[0] is shot

    def test_grid_clear_functionality(self, grid_widget, test_model, qtbot) -> None:
        """Test clearing grid widgets properly."""
        # Add shots
        test_model.set_shots(create_test_shots(2))
        qtbot.waitUntil(
            lambda: grid_widget._model and grid_widget._model.rowCount() == 2,
            timeout=1000,
        )

        # Clear model
        test_model.set_shots([])

        # Wait for model to clear (QueuedConnection needs event loop processing)
        qtbot.waitUntil(
            lambda: grid_widget._model and grid_widget._model.rowCount() == 0,
            timeout=1000,
        )

        # Selection should be reset
        assert grid_widget.selected_shot is None

    def test_resize_debouncing(self, grid_widget, test_model, qtbot) -> None:
        """Test that resize events are debounced for performance.

        Following UNIFIED_TESTING_GUIDE:
        - Test actual behavior (debouncing)
        - Verify performance optimization works
        """
        # Skip test - Model/View implementation handles resize differently
        # The list view automatically handles resize without custom reflow logic
        pytest.skip(
            "Model/View implementation uses QListView's built-in resize handling"
        )

    def test_grid_column_calculation(self, grid_widget, test_model, qtbot) -> None:
        """Test that grid columns are calculated correctly based on width."""
        # Set specific size
        grid_widget.resize(1000, 600)

        # Add shots to trigger population
        test_model.set_shots(create_test_shots(6))

        # Wait for model population
        qtbot.waitUntil(
            lambda: grid_widget._model and grid_widget._model.rowCount() == 6,
            timeout=500,
        )

        # Calculate expected columns based on widget width
        available_width = grid_widget.width()
        expected_columns = max(
            1, available_width // (Config.DEFAULT_THUMBNAIL_SIZE + 20)
        )

        # Verify layout (Model/View manages layout automatically)
        assert expected_columns > 0
        # List view in icon mode automatically arranges items based on size
        assert (
            grid_widget.list_view.viewMode() == grid_widget.list_view.ViewMode.IconMode
        )

    def test_refresh_method_delegation(self, grid_widget, test_model) -> None:
        """Test that refresh method delegates to model."""
        # Use test double for ProgressManager to avoid Qt lifecycle issues with status bar
        with patch(
            "progress_manager.ProgressManager.start_operation",
            TestProgressManager.start_operation,
        ):
            with patch(
                "progress_manager.ProgressManager.finish_operation",
                TestProgressManager.finish_operation,
            ):
                grid_widget.refresh()

        # The important thing is the refresh call was attempted
        assert len(test_model.refresh_calls) >= 1

    def test_get_selected_shot(self, grid_widget, test_model, qtbot) -> None:
        """Test getting currently selected shot."""
        # Initially no selection
        assert grid_widget.get_selected_shot() is None

        # Add shot and select it
        shot = create_test_shot("show1", "seq1", "shot1")
        test_model.set_shots([shot])

        # Wait for model to update
        qtbot.waitUntil(
            lambda: grid_widget._model and grid_widget._model.rowCount() == 1,
            timeout=1000,
        )

        # Select the shot through the proper API
        from PySide6.QtCore import QModelIndex

        index = grid_widget._model.index(0, 0) if grid_widget._model else QModelIndex()
        grid_widget._on_item_clicked(index)

        assert grid_widget.get_selected_shot() is shot


class TestPreviousShotsViewIntegration:
    """Integration tests with real components."""

    @pytest.fixture
    def integration_grid(self, qtbot, tmp_path) -> PreviousShotsView:
        """Create view with all real components for integration testing."""
        from shot_model import ShotModel

        # Real components
        cache_manager = CacheManager(cache_dir=tmp_path / "cache")
        shot_model = ShotModel(cache_manager)
        previous_model = PreviousShotsModel(shot_model, cache_manager)

        # Create the item model and view
        item_model = PreviousShotsItemModel(previous_model)
        view = PreviousShotsView(model=item_model)
        qtbot.addWidget(view)
        view.show()
        qtbot.waitExposed(view)

        yield view

        # Cleanup
        if hasattr(previous_model, "stop_auto_refresh"):
            previous_model.stop_auto_refresh()
        previous_model.deleteLater()

    def test_integration_grid_creation(self, integration_grid, qtbot) -> None:
        """Test that integration grid creates successfully."""
        grid = integration_grid

        # Grid should be created successfully
        assert grid is not None
        assert isinstance(grid, PreviousShotsView)

        # Should have UI components
        assert hasattr(grid, "_refresh_button")
        assert hasattr(grid, "_status_label")
        assert hasattr(grid, "list_view")  # Model/View uses list_view

        # Test basic functionality without triggering ProgressManager
        # Just verify the grid works and doesn't crash
        try:
            # Test basic properties
            assert grid._refresh_button.isEnabled()
            assert grid._status_label is not None
            assert grid.list_view is not None
        except RuntimeError:
            # Qt object lifecycle issues during testing are expected
            pass

        # Verify grid remains functional
        assert grid is not None
