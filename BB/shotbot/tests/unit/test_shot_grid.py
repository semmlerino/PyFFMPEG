"""Unit tests for ShotGrid class following UNIFIED_TESTING_GUIDE best practices.

This test module covers the deprecated ShotGrid widget with comprehensive testing of:
- Grid initialization and UI setup
- Shot display and thumbnail creation
- Selection handling (single/double click)
- Signal emissions (shot_selected, shot_double_clicked, app_launch_requested)
- Grid refresh and layout operations
- Keyboard navigation and shortcuts
- Size control and resize handling

Note: ShotGrid is deprecated in favor of Model/View architecture, but these tests
ensure the legacy implementation works correctly during the transition period.

Test Philosophy:
- Use real Qt components with minimal mocking
- Test behavior, not implementation details
- Use QSignalSpy for reliable signal testing
- No time.sleep() - rely on Qt event processing
- Focus on user-facing functionality
"""
# pyright: basic

from typing import List
from unittest.mock import MagicMock, Mock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QResizeEvent, QWheelEvent
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QWidget

from config import Config
from shot_grid import ShotGrid
from shot_model import Shot


class TestShotModel:
    """Test double for ShotModel with predictable behavior."""

    __test__ = False

    def __init__(self):
        """Initialize test shot model with sample shots."""
        self.shots: List[Shot] = []
        self._create_test_shots()

    def _create_test_shots(self):
        """Create sample shots for testing."""
        self.shots = [
            Shot(
                show="test_show",
                sequence="seq01",
                shot="0010",
                workspace_path="/workspace/test_show/seq01/0010",
            ),
            Shot(
                show="test_show",
                sequence="seq01",
                shot="0020",
                workspace_path="/workspace/test_show/seq01/0020",
            ),
            Shot(
                show="test_show",
                sequence="seq02",
                shot="0010",
                workspace_path="/workspace/test_show/seq02/0010",
            ),
        ]

    def add_shot(self, shot: Shot):
        """Add a shot to the test model."""
        self.shots.append(shot)

    def clear_shots(self):
        """Clear all shots from the test model."""
        self.shots.clear()


@pytest.fixture
def test_shot_model():
    """Provide a test shot model with sample data."""
    return TestShotModel()


@pytest.fixture
def shot_grid(qtbot, test_shot_model):
    """Create a ShotGrid instance for testing."""
    grid = ShotGrid(test_shot_model)
    qtbot.addWidget(grid)
    return grid


class TestShotGridInitialization:
    """Test ShotGrid initialization and UI setup."""

    def test_grid_creation(self, shot_grid, test_shot_model):
        """Test that ShotGrid is properly initialized."""
        assert shot_grid.shot_model is test_shot_model
        assert shot_grid.thumbnails == {}
        assert shot_grid.selected_shot is None
        assert shot_grid._thumbnail_size == Config.DEFAULT_THUMBNAIL_SIZE

    def test_ui_components_exist(self, shot_grid):
        """Test that all required UI components are created."""
        # Check size slider components
        assert hasattr(shot_grid, "size_slider")
        assert hasattr(shot_grid, "size_label")
        assert shot_grid.size_slider.minimum() == Config.MIN_THUMBNAIL_SIZE
        assert shot_grid.size_slider.maximum() == Config.MAX_THUMBNAIL_SIZE
        assert shot_grid.size_slider.value() == Config.DEFAULT_THUMBNAIL_SIZE

        # Check scroll area and grid layout
        assert hasattr(shot_grid, "scroll_area")
        assert hasattr(shot_grid, "container")
        assert hasattr(shot_grid, "grid_layout")

        # Check initial size label text
        assert shot_grid.size_label.text() == f"{Config.DEFAULT_THUMBNAIL_SIZE}px"

    def test_focus_policy(self, shot_grid):
        """Test that keyboard focus is properly configured."""
        assert shot_grid.focusPolicy() == Qt.FocusPolicy.StrongFocus

    def test_initial_state(self, shot_grid):
        """Test initial widget state."""
        assert shot_grid.thumbnails == {}
        assert shot_grid.selected_shot is None
        assert shot_grid._thumbnail_size == Config.DEFAULT_THUMBNAIL_SIZE


class TestShotGridDisplay:
    """Test shot display and thumbnail creation."""

    def test_refresh_shots_creates_thumbnails(self, shot_grid, test_shot_model, qtbot):
        """Test that refresh_shots creates thumbnail widgets."""
        # Initially no thumbnails
        assert len(shot_grid.thumbnails) == 0

        # Refresh shots
        shot_grid.refresh_shots()
        qtbot.wait(10)  # Allow widgets to be created

        # Should have thumbnails for all shots
        assert len(shot_grid.thumbnails) == len(test_shot_model.shots)

        # Check thumbnails are keyed by full_name
        for shot in test_shot_model.shots:
            assert shot.full_name in shot_grid.thumbnails

    def test_refresh_shots_clears_existing_thumbnails(
        self, shot_grid, test_shot_model, qtbot
    ):
        """Test that refresh_shots clears existing thumbnails."""
        # Create initial thumbnails
        shot_grid.refresh_shots()
        qtbot.wait(10)
        initial_count = len(shot_grid.thumbnails)
        assert initial_count > 0

        # Modify shot model
        test_shot_model.clear_shots()
        test_shot_model.add_shot(
            Shot("new_show", "new_seq", "new_shot", "/workspace/new")
        )

        # Refresh again
        shot_grid.refresh_shots()
        qtbot.wait(10)

        # Should have only the new shot
        assert len(shot_grid.thumbnails) == 1
        assert "new_seq_new_shot" in shot_grid.thumbnails

    def test_thumbnail_grid_layout(self, shot_grid, test_shot_model, qtbot):
        """Test that thumbnails are properly laid out in grid."""
        shot_grid.refresh_shots()
        qtbot.wait(10)

        # Check that widgets are added to grid layout
        layout_item_count = shot_grid.grid_layout.count()
        assert layout_item_count == len(test_shot_model.shots)

        # Verify grid positions (assuming sufficient width for single row)
        for i, shot in enumerate(test_shot_model.shots):
            thumbnail = shot_grid.thumbnails.get(shot.full_name)
            assert thumbnail is not None

            # Check that widget exists in layout
            position = shot_grid.grid_layout.getItemPosition(
                shot_grid.grid_layout.indexOf(thumbnail)
            )
            assert position is not None

    def test_empty_shot_list_handling(self, qtbot, test_shot_model):
        """Test handling of empty shot list."""
        test_shot_model.clear_shots()
        grid = ShotGrid(test_shot_model)
        qtbot.addWidget(grid)

        grid.refresh_shots()
        qtbot.wait(10)

        assert len(grid.thumbnails) == 0
        assert grid.grid_layout.count() == 0


class TestShotGridSelection:
    """Test selection handling and signal emission."""

    def test_thumbnail_click_selection(self, shot_grid, test_shot_model, qtbot):
        """Test single click selection behavior."""
        shot_grid.refresh_shots()
        qtbot.wait(10)

        # Capture signal emissions
        selected_shots = []

        def on_shot_selected(shot):
            selected_shots.append(shot)

        shot_grid.shot_selected.connect(on_shot_selected)

        # Select first shot
        first_shot = test_shot_model.shots[0]
        shot_grid.select_shot(first_shot)

        # Check selection state
        assert shot_grid.selected_shot is first_shot
        assert len(selected_shots) == 1
        assert selected_shots[0] is first_shot

        # Check thumbnail is marked as selected
        shot_grid.thumbnails[first_shot.full_name]
        # Note: We can't easily test visual selection state without accessing private methods

    def test_selection_change(self, shot_grid, test_shot_model, qtbot):
        """Test changing selection between shots."""
        shot_grid.refresh_shots()
        qtbot.wait(10)

        # Capture signal emissions
        selected_shots = []

        def on_shot_selected(shot):
            selected_shots.append(shot)

        shot_grid.shot_selected.connect(on_shot_selected)

        # Select first shot
        first_shot = test_shot_model.shots[0]
        shot_grid.select_shot(first_shot)
        assert shot_grid.selected_shot is first_shot

        # Select second shot
        second_shot = test_shot_model.shots[1]
        shot_grid.select_shot(second_shot)
        assert shot_grid.selected_shot is second_shot

        # Should have two signal emissions
        assert len(selected_shots) == 2
        assert selected_shots[0] is first_shot
        assert selected_shots[1] is second_shot

    def test_double_click_signal(self, shot_grid, test_shot_model, qtbot):
        """Test double click signal emission."""
        shot_grid.refresh_shots()
        qtbot.wait(10)

        # Capture signal emissions
        double_clicked_shots = []

        def on_double_click(shot):
            double_clicked_shots.append(shot)

        shot_grid.shot_double_clicked.connect(on_double_click)

        # Simulate double click
        test_shot = test_shot_model.shots[0]
        shot_grid._on_thumbnail_double_clicked(test_shot)

        # Check signal emission
        assert len(double_clicked_shots) == 1
        assert double_clicked_shots[0] is test_shot

    def test_programmatic_selection(self, shot_grid, test_shot_model, qtbot):
        """Test programmatic shot selection."""
        shot_grid.refresh_shots()
        qtbot.wait(10)

        signal_spy = QSignalSpy(shot_grid.shot_selected)

        # Select shot programmatically
        target_shot = test_shot_model.shots[1]
        shot_grid.select_shot(target_shot)

        assert shot_grid.selected_shot is target_shot
        assert signal_spy.count() == 1


class TestShotGridSizeControl:
    """Test thumbnail size control functionality."""

    def test_size_slider_change(self, shot_grid, qtbot):
        """Test thumbnail size change via slider."""
        shot_grid.refresh_shots()
        qtbot.wait(10)

        # Change size
        new_size = Config.MIN_THUMBNAIL_SIZE + 50
        shot_grid.size_slider.setValue(new_size)
        qtbot.wait(10)

        # Check size updated
        assert shot_grid._thumbnail_size == new_size
        assert shot_grid.size_label.text() == f"{new_size}px"

    def test_wheel_event_with_ctrl(self, shot_grid, qtbot):
        """Test Ctrl+wheel thumbnail size adjustment."""
        initial_size = shot_grid._thumbnail_size

        # Create mock wheel event with Ctrl modifier (scroll up = larger)
        wheel_event = MagicMock(spec=QWheelEvent)
        wheel_event.modifiers.return_value = Qt.KeyboardModifier.ControlModifier
        wheel_event.angleDelta.return_value.y.return_value = 120  # Positive = scroll up
        wheel_event.accept.return_value = None

        # Send wheel event
        shot_grid.wheelEvent(wheel_event)

        # Size should increase
        expected_size = min(initial_size + 10, Config.MAX_THUMBNAIL_SIZE)
        assert shot_grid._thumbnail_size == expected_size
        assert shot_grid.size_slider.value() == expected_size

    def test_wheel_event_without_ctrl(self, shot_grid, qtbot):
        """Test wheel event without Ctrl modifier (should not change size)."""
        initial_size = shot_grid._thumbnail_size

        # Create mock wheel event without Ctrl
        wheel_event = MagicMock(spec=QWheelEvent)
        wheel_event.modifiers.return_value = Qt.KeyboardModifier.NoModifier
        wheel_event.angleDelta.return_value.y.return_value = 120

        # Mock parent wheelEvent to verify it's called
        with patch.object(QWidget, "wheelEvent") as mock_super_wheel:
            shot_grid.wheelEvent(wheel_event)
            # Verify super().wheelEvent was called since no Ctrl modifier
            mock_super_wheel.assert_called_once_with(wheel_event)

        # Size should not change
        assert shot_grid._thumbnail_size == initial_size

    def test_size_limits(self, shot_grid, qtbot):
        """Test that size changes respect min/max limits."""
        # Test minimum limit
        shot_grid.size_slider.setValue(Config.MIN_THUMBNAIL_SIZE - 50)
        assert shot_grid.size_slider.value() == Config.MIN_THUMBNAIL_SIZE

        # Test maximum limit
        shot_grid.size_slider.setValue(Config.MAX_THUMBNAIL_SIZE + 50)
        assert shot_grid.size_slider.value() == Config.MAX_THUMBNAIL_SIZE


class TestShotGridKeyboardNavigation:
    """Test keyboard navigation and shortcuts."""

    def test_arrow_key_navigation(self, shot_grid, test_shot_model, qtbot):
        """Test arrow key navigation between shots."""
        shot_grid.refresh_shots()
        qtbot.wait(10)

        # Select first shot
        shot_grid.select_shot(test_shot_model.shots[0])
        signal_spy = QSignalSpy(shot_grid.shot_selected)

        # Press right arrow
        key_event = QKeyEvent(
            QKeyEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier
        )
        shot_grid.keyPressEvent(key_event)

        # Should select next shot
        if len(test_shot_model.shots) > 1:
            assert shot_grid.selected_shot is test_shot_model.shots[1]
            assert signal_spy.count() == 1

    def test_home_end_navigation(self, shot_grid, test_shot_model, qtbot):
        """Test Home/End key navigation."""
        shot_grid.refresh_shots()
        qtbot.wait(10)

        QSignalSpy(shot_grid.shot_selected)

        # Press Home key
        home_event = QKeyEvent(
            QKeyEvent.Type.KeyPress, Qt.Key.Key_Home, Qt.KeyboardModifier.NoModifier
        )
        shot_grid.keyPressEvent(home_event)

        # Should select first shot
        assert shot_grid.selected_shot is test_shot_model.shots[0]

        # Press End key
        end_event = QKeyEvent(
            QKeyEvent.Type.KeyPress, Qt.Key.Key_End, Qt.KeyboardModifier.NoModifier
        )
        shot_grid.keyPressEvent(end_event)

        # Should select last shot
        assert shot_grid.selected_shot is test_shot_model.shots[-1]

    def test_enter_key_double_click(self, shot_grid, test_shot_model, qtbot):
        """Test Enter key triggers double-click behavior."""
        shot_grid.refresh_shots()
        qtbot.wait(10)

        # Select a shot
        shot_grid.select_shot(test_shot_model.shots[0])

        # Capture signal emissions
        double_clicked_shots = []

        def on_double_click(shot):
            double_clicked_shots.append(shot)

        shot_grid.shot_double_clicked.connect(on_double_click)

        # Press Enter
        enter_event = QKeyEvent(
            QKeyEvent.Type.KeyPress, Qt.Key.Key_Enter, Qt.KeyboardModifier.NoModifier
        )
        shot_grid.keyPressEvent(enter_event)

        # Should emit double-click signal
        assert len(double_clicked_shots) == 1
        assert double_clicked_shots[0] is test_shot_model.shots[0]

    def test_app_launch_shortcuts(self, shot_grid, test_shot_model, qtbot):
        """Test application launch keyboard shortcuts."""
        shot_grid.refresh_shots()
        qtbot.wait(10)

        # Select a shot
        shot_grid.select_shot(test_shot_model.shots[0])

        # Capture signal emissions
        app_launches = []

        def on_app_launch(app_name):
            app_launches.append(app_name)

        shot_grid.app_launch_requested.connect(on_app_launch)

        # Test 3DE shortcut (key '3')
        key_3_event = QKeyEvent(
            QKeyEvent.Type.KeyPress, Qt.Key.Key_3, Qt.KeyboardModifier.NoModifier
        )
        shot_grid.keyPressEvent(key_3_event)

        assert len(app_launches) == 1
        assert app_launches[0] == "3de"

        # Test Nuke shortcut (key 'N')
        key_n_event = QKeyEvent(
            QKeyEvent.Type.KeyPress, Qt.Key.Key_N, Qt.KeyboardModifier.NoModifier
        )
        shot_grid.keyPressEvent(key_n_event)

        assert len(app_launches) == 2
        assert app_launches[1] == "nuke"

    def test_keyboard_navigation_no_shots(self, qtbot, test_shot_model):
        """Test keyboard navigation with empty shot list."""
        test_shot_model.clear_shots()
        grid = ShotGrid(test_shot_model)
        qtbot.addWidget(grid)

        # Key events should not crash
        key_event = QKeyEvent(
            QKeyEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier
        )
        grid.keyPressEvent(key_event)  # Should not raise exception

    def test_app_shortcuts_without_selection(self, shot_grid, qtbot):
        """Test app shortcuts with no shot selected."""
        signal_spy = QSignalSpy(shot_grid.app_launch_requested)

        # Try shortcut without selection
        key_event = QKeyEvent(
            QKeyEvent.Type.KeyPress, Qt.Key.Key_3, Qt.KeyboardModifier.NoModifier
        )
        shot_grid.keyPressEvent(key_event)

        # Should not emit signal
        assert signal_spy.count() == 0


class TestShotGridLayout:
    """Test grid layout and resize handling."""

    def test_column_calculation(self, shot_grid, qtbot):
        """Test column count calculation based on width."""
        # Mock viewport width
        shot_grid.scroll_area.resize(800, 600)
        qtbot.wait(10)

        columns = shot_grid._get_column_count()

        # Should calculate reasonable column count
        assert columns >= 1
        assert isinstance(columns, int)

    def test_column_calculation_zero_width(self, shot_grid):
        """Test column calculation with zero width."""
        # Mock viewport to return zero width
        with patch.object(shot_grid.scroll_area, "viewport") as mock_viewport:
            mock_widget = Mock()
            mock_widget.width.return_value = 0
            mock_viewport.return_value = mock_widget

            columns = shot_grid._get_column_count()

            # Should fall back to default
            assert columns == Config.GRID_COLUMNS

    def test_reflow_grid(self, shot_grid, test_shot_model, qtbot):
        """Test grid reflow on resize."""
        shot_grid.refresh_shots()
        qtbot.wait(10)

        initial_layout_count = shot_grid.grid_layout.count()

        # Trigger reflow
        shot_grid._reflow_grid()
        qtbot.wait(10)

        # Should have same number of items
        assert shot_grid.grid_layout.count() == initial_layout_count

    def test_resize_event_triggers_reflow(self, shot_grid, qtbot):
        """Test that resize events trigger grid reflow."""
        shot_grid.refresh_shots()
        qtbot.wait(10)

        # Create resize event
        resize_event = QResizeEvent(shot_grid.size(), shot_grid.size())

        # Send resize event (should not crash)
        shot_grid.resizeEvent(resize_event)
        qtbot.wait(10)

    def test_reflow_with_empty_grid(self, shot_grid, qtbot):
        """Test reflow with no thumbnails."""
        # Ensure grid is empty
        assert len(shot_grid.thumbnails) == 0

        # Reflow should not crash
        shot_grid._reflow_grid()


class TestShotGridSignals:
    """Test signal emission and connection."""

    def test_signal_connections_exist(self, shot_grid):
        """Test that required signals exist."""
        assert hasattr(shot_grid, "shot_selected")
        assert hasattr(shot_grid, "shot_double_clicked")
        assert hasattr(shot_grid, "app_launch_requested")

    def test_multiple_signal_connections(self, shot_grid, test_shot_model, qtbot):
        """Test that signals can handle multiple connections."""
        shot_grid.refresh_shots()
        qtbot.wait(10)

        # Connect multiple handlers
        handler1_called = []
        handler2_called = []

        def handler1(shot):
            handler1_called.append(shot)

        def handler2(shot):
            handler2_called.append(shot)

        shot_grid.shot_selected.connect(handler1)
        shot_grid.shot_selected.connect(handler2)

        # Select a shot
        test_shot = test_shot_model.shots[0] if test_shot_model.shots else None
        if test_shot:
            shot_grid.select_shot(test_shot)

            # Both handlers should be called
            assert len(handler1_called) == 1
            assert len(handler2_called) == 1
            assert handler1_called[0] is test_shot
            assert handler2_called[0] is test_shot


class TestShotGridEdgeCases:
    """Test edge cases and error conditions."""

    def test_select_nonexistent_shot(self, shot_grid, qtbot):
        """Test selecting a shot that doesn't exist in the grid."""
        shot_grid.refresh_shots()
        qtbot.wait(10)

        # Create a shot not in the model
        fake_shot = Shot("fake", "fake", "fake", "/fake")

        # Should not crash when selecting non-existent shot
        shot_grid.select_shot(fake_shot)
        assert shot_grid.selected_shot is fake_shot

    def test_clear_grid_multiple_times(self, shot_grid, qtbot):
        """Test clearing grid multiple times."""
        shot_grid.refresh_shots()
        qtbot.wait(10)

        # Clear multiple times should not crash
        shot_grid._clear_grid()
        shot_grid._clear_grid()
        shot_grid._clear_grid()

        assert len(shot_grid.thumbnails) == 0

    def test_grid_with_single_shot(self, qtbot):
        """Test grid behavior with single shot."""
        single_shot_model = TestShotModel()
        single_shot_model.clear_shots()
        single_shot_model.add_shot(Shot("single", "shot", "test", "/workspace"))

        grid = ShotGrid(single_shot_model)
        qtbot.addWidget(grid)

        grid.refresh_shots()
        qtbot.wait(10)

        assert len(grid.thumbnails) == 1

        # Navigation should work with single shot
        key_event = QKeyEvent(
            QKeyEvent.Type.KeyPress, Qt.Key.Key_Home, Qt.KeyboardModifier.NoModifier
        )
        grid.keyPressEvent(key_event)

        assert grid.selected_shot is single_shot_model.shots[0]
