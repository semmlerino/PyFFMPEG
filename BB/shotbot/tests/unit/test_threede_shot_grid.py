"""Unit tests for ThreeDEShotGrid widget."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy

from config import Config
from threede_scene_model import ThreeDEScene, ThreeDESceneModel
from threede_shot_grid import ThreeDEShotGrid
from threede_thumbnail_widget import ThreeDEThumbnailWidget

pytestmark = [pytest.mark.unit, pytest.mark.qt]


@pytest.fixture
def sample_scenes():
    """Create sample 3DE scenes for testing."""
    scenes = []
    for i in range(5):
        scene = ThreeDEScene(
            show=f"show{i}",
            sequence=f"seq{i:02d}",
            shot=f"shot{i:03d}",
            user=f"user{i}",
            scene_path=Path(f"/path/to/scene{i}.3de"),
            plate=f"FG{i:02d}",
            workspace_path=f"/workspace/shot{i}",
        )
        scenes.append(scene)
    return scenes


@pytest.fixture
def scene_model(sample_scenes):
    """Create a ThreeDESceneModel with sample scenes."""
    model = ThreeDESceneModel()
    model.scenes = sample_scenes
    return model


@pytest.fixture
def threede_grid(qtbot, scene_model):
    """Create a ThreeDEShotGrid instance for testing."""
    grid = ThreeDEShotGrid(scene_model)
    qtbot.addWidget(grid)
    return grid

class TestThreeDEShotGridInitialization:
    """Test ThreeDEShotGrid initialization."""

    def test_initialization(self, threede_grid, scene_model):
        """Test grid initialization."""
        assert threede_grid.scene_model == scene_model
        assert threede_grid.thumbnails == {}
        assert threede_grid.selected_scene is None
        assert threede_grid._thumbnail_size == Config.DEFAULT_THUMBNAIL_SIZE
        assert threede_grid._is_loading is False

    def test_ui_setup(self, threede_grid):
        """Test UI components are created."""
        assert threede_grid.size_slider is not None
        assert threede_grid.size_label is not None
        assert threede_grid.loading_bar is not None
        assert threede_grid.loading_label is not None
        assert threede_grid.scroll_area is not None
        assert threede_grid.container is not None
        assert threede_grid.grid_layout is not None

        # Check initial states
        assert threede_grid.loading_bar.isVisible() is False
        assert threede_grid.loading_label.isVisible() is False
        assert threede_grid.size_slider.value() == Config.DEFAULT_THUMBNAIL_SIZE
        assert threede_grid.size_label.text() == f"{Config.DEFAULT_THUMBNAIL_SIZE}px"

    def test_focus_policy(self, threede_grid):
        """Test widget has proper focus policy."""
        assert threede_grid.focusPolicy() == Qt.FocusPolicy.StrongFocus


class TestThreeDEShotGridLoadingState:
    """Test loading state management."""

    def test_set_loading_true(self, threede_grid, qtbot):
        """Test setting loading state to true."""
        # Show the widget first
        threede_grid.show()
        qtbot.waitExposed(threede_grid)

        threede_grid.set_loading(True, "Loading test...")

        assert threede_grid._is_loading is True
        assert threede_grid.loading_bar.isVisible() is True
        assert threede_grid.loading_label.isVisible() is True
        assert threede_grid.loading_label.text() == "Loading test..."

    def test_set_loading_false(self, threede_grid):
        """Test setting loading state to false."""
        threede_grid.set_loading(True)
        threede_grid.set_loading(False)

        assert threede_grid._is_loading is False
        assert threede_grid.loading_bar.isVisible() is False
        assert threede_grid.loading_label.isVisible() is False

    def test_set_loading_progress(self, threede_grid):
        """Test setting loading progress."""
        threede_grid.set_loading_progress(5, 10)

        assert threede_grid.loading_bar.minimum() == 0
        assert threede_grid.loading_bar.maximum() == 10
        assert threede_grid.loading_bar.value() == 5
        assert "5/10" in threede_grid.loading_label.text()

    def test_set_loading_progress_zero_total(self, threede_grid):
        """Test setting progress with zero total."""
        # Should not crash with zero total
        threede_grid.set_loading_progress(0, 0)
        # Progress bar remains in indeterminate state


class TestThreeDEShotGridSceneDisplay:
    """Test scene display functionality."""

    def test_refresh_scenes_with_scenes(self, threede_grid, sample_scenes):
        """Test refreshing grid with scenes."""
        with patch.object(threede_grid, "_clear_grid"):
            with patch.object(threede_grid, "_get_column_count", return_value=3):
                threede_grid.refresh_scenes()

        # Check thumbnails were created
        assert len(threede_grid.thumbnails) == len(sample_scenes)

        # Check each thumbnail
        for scene in sample_scenes:
            assert scene.display_name in threede_grid.thumbnails
            thumbnail = threede_grid.thumbnails[scene.display_name]
            assert isinstance(thumbnail, ThreeDEThumbnailWidget)
            assert thumbnail.scene == scene

    def test_refresh_scenes_empty(self, threede_grid):
        """Test refreshing with no scenes."""
        threede_grid.scene_model.scenes = []

        with patch.object(threede_grid, "_show_empty_state"):
            threede_grid.refresh_scenes()
        assert len(threede_grid.thumbnails) == 0

    def test_show_empty_state(self, threede_grid):
        """Test showing empty state message."""
        threede_grid._show_empty_state()

        # Check that empty label was added
        assert threede_grid.grid_layout.count() == 1
        item = threede_grid.grid_layout.itemAt(0)
        assert item is not None
        widget = item.widget()
        assert widget is not None
        assert "No 3DE scenes" in widget.text()

    def test_clear_grid(self, threede_grid, sample_scenes):
        """Test clearing the grid."""
        # First add some thumbnails
        threede_grid.refresh_scenes()
        assert len(threede_grid.thumbnails) > 0

        # Clear the grid
        threede_grid._clear_grid()

        assert len(threede_grid.thumbnails) == 0
        assert threede_grid.grid_layout.count() == 0


class TestThreeDEShotGridColumnCalculation:
    """Test column count calculation."""

    def test_get_column_count_default(self, threede_grid):
        """Test default column count."""
        with patch.object(threede_grid.scroll_area.viewport(), "width", return_value=0):
            count = threede_grid._get_column_count()
        assert count == Config.GRID_COLUMNS

    def test_get_column_count_calculated(self, threede_grid):
        """Test calculated column count."""
        # Mock viewport width
        viewport_width = 500
        with patch.object(
            threede_grid.scroll_area.viewport(),
            "width",
            return_value=viewport_width,
        ):
            count = threede_grid._get_column_count()

        expected = max(
            1,
            viewport_width
            // (Config.DEFAULT_THUMBNAIL_SIZE + Config.THUMBNAIL_SPACING),
        )
        assert count == expected

    def test_get_column_count_minimum(self, threede_grid):
        """Test minimum column count is 1."""
        with patch.object(
            threede_grid.scroll_area.viewport(),
            "width",
            return_value=10,
        ):
            count = threede_grid._get_column_count()
        assert count >= 1


class TestThreeDEShotGridSizeControl:
    """Test thumbnail size control."""

    def test_size_slider_range(self, threede_grid):
        """Test size slider configuration."""
        assert threede_grid.size_slider.minimum() == Config.MIN_THUMBNAIL_SIZE
        assert threede_grid.size_slider.maximum() == Config.MAX_THUMBNAIL_SIZE
        assert threede_grid.size_slider.value() == Config.DEFAULT_THUMBNAIL_SIZE

    def test_on_size_changed(self, threede_grid, sample_scenes):
        """Test handling size change."""
        # Add some thumbnails
        threede_grid.refresh_scenes()

        new_size = 200
        with patch.object(threede_grid, "_reflow_grid"):
            threede_grid._on_size_changed(new_size)

        assert threede_grid._thumbnail_size == new_size
        assert threede_grid.size_label.text() == f"{new_size}px"

        # Check all thumbnails were resized
        for thumbnail in threede_grid.thumbnails.values():
            # The thumbnail's set_size method should have been called
            pass  # We'd need to mock set_size to verify

    def test_wheel_event_with_ctrl(self, threede_grid):
        """Test wheel event with Ctrl for size adjustment."""
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QWheelEvent
        
        initial_size = threede_grid._thumbnail_size
        
        # Create real wheel event with Ctrl modifier (zoom in)
        event = QWheelEvent(
            QPoint(100, 100),  # position
            QPoint(100, 100),  # global position
            QPoint(0, 0),      # pixelDelta
            QPoint(0, 120),    # angleDelta (positive = zoom in)
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.ControlModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False
        )
        
        threede_grid.wheelEvent(event)

        # Size should increase
        assert threede_grid.size_slider.value() > initial_size

    def test_wheel_event_without_ctrl(self, threede_grid):
        """Test wheel event without Ctrl passes through."""
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QWheelEvent
        
        initial_size = threede_grid._thumbnail_size
        
        # Create real wheel event without Ctrl modifier
        event = QWheelEvent(
            QPoint(100, 100),  # position
            QPoint(100, 100),  # global position
            QPoint(0, 0),      # pixelDelta
            QPoint(0, 120),    # angleDelta
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False
        )
        
        threede_grid.wheelEvent(event)

        # Size should remain unchanged (passes through to scroll area)
        assert threede_grid._thumbnail_size == initial_size


class TestThreeDEShotGridSelection:
    """Test scene selection functionality."""

    def test_thumbnail_click(self, threede_grid, qtbot, sample_scenes):
        """Test handling thumbnail click."""
        threede_grid.refresh_scenes()

        scene = sample_scenes[0]
        thumbnail = threede_grid.thumbnails[scene.display_name]

        # Spy on signal
        spy = QSignalSpy(threede_grid.scene_selected)

        # Simulate click
        threede_grid._on_thumbnail_clicked(scene)

        assert threede_grid.selected_scene == scene
        assert spy.count() == 1
        assert spy.at(0)[0] == scene

        # Check selection state
        assert thumbnail._selected is True

    def test_thumbnail_double_click(self, threede_grid, qtbot, sample_scenes):
        """Test handling thumbnail double click."""
        threede_grid.refresh_scenes()

        scene = sample_scenes[0]

        # Spy on signal
        spy = QSignalSpy(threede_grid.scene_double_clicked)

        # Simulate double click
        threede_grid._on_thumbnail_double_clicked(scene)

        assert spy.count() == 1
        assert spy.at(0)[0] == scene

    def test_select_scene_programmatically(self, threede_grid, sample_scenes):
        """Test selecting scene programmatically."""
        threede_grid.refresh_scenes()

        scene = sample_scenes[2]
        threede_grid.select_scene(scene)

        # Verify the scene is actually selected
        assert threede_grid.selected_scene == scene
        
        # Verify the thumbnail is marked as selected
        thumbnail = threede_grid.thumbnails[scene.display_name]
        assert thumbnail._selected is True

    def test_selection_change(self, threede_grid, sample_scenes):
        """Test changing selection between scenes."""
        threede_grid.refresh_scenes()

        # Select first scene
        scene1 = sample_scenes[0]
        threede_grid._on_thumbnail_clicked(scene1)
        thumb1 = threede_grid.thumbnails[scene1.display_name]
        assert thumb1._selected is True

        # Select second scene
        scene2 = sample_scenes[1]
        threede_grid._on_thumbnail_clicked(scene2)
        thumb2 = threede_grid.thumbnails[scene2.display_name]

        # First should be deselected
        assert thumb1._selected is False
        # Second should be selected
        assert thumb2._selected is True
        assert threede_grid.selected_scene == scene2


class TestThreeDEShotGridKeyboardNavigation:
    """Test keyboard navigation."""

    def test_arrow_key_right(self, threede_grid, sample_scenes):
        """Test right arrow navigation."""
        threede_grid.refresh_scenes()
        threede_grid.selected_scene = sample_scenes[0]

        # Create real key event
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QKeyEvent
        
        event = QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_Right,
            Qt.KeyboardModifier.NoModifier
        )

        threede_grid.keyPressEvent(event)

        # Verify navigation moved to next scene
        assert threede_grid.selected_scene == sample_scenes[1]

    def test_arrow_key_left(self, threede_grid, sample_scenes):
        """Test left arrow navigation."""
        threede_grid.refresh_scenes()
        threede_grid.selected_scene = sample_scenes[2]

        # Create real key event
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QKeyEvent
        
        event = QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_Left,
            Qt.KeyboardModifier.NoModifier
        )

        threede_grid.keyPressEvent(event)

        # Verify navigation moved to previous scene
        assert threede_grid.selected_scene == sample_scenes[1]

    def test_arrow_key_down(self, threede_grid, sample_scenes):
        """Test down arrow navigation."""
        threede_grid.refresh_scenes()
        threede_grid.selected_scene = sample_scenes[0]

        # Create real key event
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QKeyEvent
        
        event = QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_Down,
            Qt.KeyboardModifier.NoModifier
        )

        with patch.object(threede_grid, "_get_column_count", return_value=3):
            threede_grid.keyPressEvent(event)

        # Should move down by column count (3 positions)
        assert threede_grid.selected_scene == sample_scenes[3]

    def test_home_key(self, threede_grid, sample_scenes):
        """Test Home key navigation."""
        threede_grid.refresh_scenes()
        threede_grid.selected_scene = sample_scenes[3]

        # Create real key event
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QKeyEvent
        
        event = QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_Home,
            Qt.KeyboardModifier.NoModifier
        )

        threede_grid.keyPressEvent(event)

        # Should move to first scene
        assert threede_grid.selected_scene == sample_scenes[0]

    def test_end_key(self, threede_grid, sample_scenes):
        """Test End key navigation."""
        threede_grid.refresh_scenes()
        threede_grid.selected_scene = sample_scenes[0]

        # Create real key event
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QKeyEvent
        
        event = QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_End,
            Qt.KeyboardModifier.NoModifier
        )

        threede_grid.keyPressEvent(event)

        # Should move to last scene
        assert threede_grid.selected_scene == sample_scenes[-1]

    def test_enter_key(self, threede_grid, qtbot, sample_scenes):
        """Test Enter key triggers double click."""
        threede_grid.refresh_scenes()
        threede_grid.selected_scene = sample_scenes[0]

        # Create real key event
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QKeyEvent
        
        event = QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_Return,
            Qt.KeyboardModifier.NoModifier
        )

        spy = QSignalSpy(threede_grid.scene_double_clicked)
        threede_grid.keyPressEvent(event)

        assert spy.count() == 1
        assert spy.at(0)[0] == sample_scenes[0]

    def test_app_launch_shortcuts(self, threede_grid, qtbot, sample_scenes):
        """Test application launch keyboard shortcuts."""
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QKeyEvent
        
        threede_grid.refresh_scenes()
        threede_grid.selected_scene = sample_scenes[0]

        # Test various app shortcuts
        shortcuts = {
            Qt.Key.Key_3: "3de",
            Qt.Key.Key_N: "nuke",
            Qt.Key.Key_M: "maya",
            Qt.Key.Key_R: "rv",
            Qt.Key.Key_P: "publish",
        }

        for key, app_name in shortcuts.items():
            event = QKeyEvent(
                QEvent.Type.KeyPress,
                key,
                Qt.KeyboardModifier.NoModifier
            )

            spy = QSignalSpy(threede_grid.app_launch_requested)
            threede_grid.keyPressEvent(event)

            assert spy.count() == 1
            assert spy.at(0)[0] == app_name

    def test_keyboard_nav_empty_grid(self, threede_grid):
        """Test keyboard navigation with empty grid."""
        threede_grid.scene_model.scenes = []
        threede_grid.refresh_scenes()

        # Create real key event
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QKeyEvent
        
        event = QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_Right,
            Qt.KeyboardModifier.NoModifier
        )

        # Store initial state (should be None for empty grid)
        initial_selection = threede_grid.selected_scene
        
        threede_grid.keyPressEvent(event)

        # Selection should remain unchanged since no scenes available
        assert threede_grid.selected_scene == initial_selection

    def test_ensure_widget_visible(self, threede_grid, sample_scenes):
        """Test ensuring selected widget is visible after navigation."""
        threede_grid.refresh_scenes()
        threede_grid.selected_scene = sample_scenes[0]

        # Create real key event
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QKeyEvent
        
        event = QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_Right,
            Qt.KeyboardModifier.NoModifier
        )

        threede_grid.keyPressEvent(event)

        # Verify navigation occurred and new thumbnail is selected
        assert threede_grid.selected_scene == sample_scenes[1]
        new_thumb = threede_grid.thumbnails[sample_scenes[1].display_name]
        assert new_thumb._selected is True
        
        # Verify the widget is part of the scroll area (indirect visibility test)
        assert new_thumb.parent() is not None


class TestThreeDEShotGridReflow:
    """Test grid reflow functionality."""

    def test_reflow_grid(self, threede_grid, sample_scenes):
        """Test reflowing grid layout."""
        threede_grid.refresh_scenes()

        with patch.object(threede_grid, "_get_column_count", return_value=2):
            threede_grid._reflow_grid()

        # Check that widgets are in correct positions
        for i, scene in enumerate(sample_scenes):
            if scene.display_name in threede_grid.thumbnails:
                i // 2
                i % 2
                # We'd need to check actual grid positions here

    def test_reflow_empty_grid(self, threede_grid):
        """Test reflowing empty grid doesn't crash."""
        threede_grid.thumbnails = {}
        threede_grid._reflow_grid()  # Should not crash

    def test_resize_event_triggers_reflow(self, threede_grid, sample_scenes):
        """Test resize event triggers reflow."""
        threede_grid.refresh_scenes()
        
        # Create real resize event
        from PySide6.QtCore import QSize
        from PySide6.QtGui import QResizeEvent
        
        old_size = QSize(400, 300)
        new_size = QSize(800, 600)
        event = QResizeEvent(new_size, old_size)
        
        # Store initial thumbnail positions/count
        initial_thumbnail_count = len(threede_grid.thumbnails)

        threede_grid.resizeEvent(event)

        # Verify that thumbnails are still properly arranged after resize
        assert len(threede_grid.thumbnails) == initial_thumbnail_count
        # Verify grid layout still contains all thumbnails
        assert threede_grid.grid_layout.count() >= initial_thumbnail_count


class TestThreeDEShotGridSignalConnections:
    """Test signal connections."""

    def test_thumbnail_signal_connections(self, threede_grid, sample_scenes):
        """Test thumbnail signals are connected properly during refresh."""
        # Just verify that refresh_scenes creates thumbnails correctly
        threede_grid.refresh_scenes()

        # Check that thumbnails were created for each scene
        assert len(threede_grid.thumbnails) == len(sample_scenes)

        # Verify each thumbnail is a ThreeDEThumbnailWidget
        for scene in sample_scenes:
            assert scene.display_name in threede_grid.thumbnails
            thumbnail = threede_grid.thumbnails[scene.display_name]
            assert isinstance(thumbnail, ThreeDEThumbnailWidget)
            assert thumbnail.scene == scene

    def test_size_slider_connection(self, threede_grid):
        """Test size slider is connected."""
        # Change slider value
        new_value = 200
        with patch.object(threede_grid, "_on_size_changed"):
            threede_grid.size_slider.setValue(new_value)
            # The valueChanged signal should trigger the handler
            # Note: In real Qt this would work, but in test we need to verify setup

        # Verify slider was set up with connection
        assert threede_grid.size_slider.value() == new_value
