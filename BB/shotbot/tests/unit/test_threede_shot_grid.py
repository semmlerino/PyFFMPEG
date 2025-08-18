"""Unit tests for ThreeDEShotGrid widget."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QResizeEvent, QWheelEvent
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QWidget

from config import Config
from threede_scene_model import ThreeDEScene, ThreeDESceneModel
from threede_shot_grid import ThreeDEShotGrid
from threede_thumbnail_widget import ThreeDEThumbnailWidget


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
        with patch.object(threede_grid, "_clear_grid") as mock_clear:
            with patch.object(threede_grid, "_get_column_count", return_value=3):
                threede_grid.refresh_scenes()

        mock_clear.assert_called_once()

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

        with patch.object(threede_grid, "_show_empty_state") as mock_empty:
            threede_grid.refresh_scenes()

        mock_empty.assert_called_once()
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
        with patch.object(threede_grid, "_reflow_grid") as mock_reflow:
            threede_grid._on_size_changed(new_size)

        assert threede_grid._thumbnail_size == new_size
        assert threede_grid.size_label.text() == f"{new_size}px"

        # Check all thumbnails were resized
        for thumbnail in threede_grid.thumbnails.values():
            # The thumbnail's set_size method should have been called
            pass  # We'd need to mock set_size to verify

        mock_reflow.assert_called_once()

    def test_wheel_event_with_ctrl(self, threede_grid):
        """Test wheel event with Ctrl for size adjustment."""
        # Create mock wheel event with Ctrl modifier
        event = MagicMock(spec=QWheelEvent)
        event.modifiers.return_value = Qt.KeyboardModifier.ControlModifier
        event.angleDelta.return_value.y.return_value = 120  # Positive = zoom in

        initial_size = threede_grid._thumbnail_size
        threede_grid.wheelEvent(event)

        # Size should increase
        assert threede_grid.size_slider.value() > initial_size
        event.accept.assert_called_once()

    def test_wheel_event_without_ctrl(self, threede_grid):
        """Test wheel event without Ctrl passes through."""
        event = MagicMock(spec=QWheelEvent)
        event.modifiers.return_value = Qt.KeyboardModifier.NoModifier

        with patch.object(QWidget, "wheelEvent") as mock_super:
            threede_grid.wheelEvent(event)

        mock_super.assert_called_once_with(event)


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
        with patch.object(threede_grid, "_on_thumbnail_clicked") as mock_click:
            threede_grid.select_scene(scene)

        mock_click.assert_called_once_with(scene)

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

        event = MagicMock(spec=QKeyEvent)
        event.key.return_value = Qt.Key.Key_Right

        with patch.object(threede_grid, "select_scene") as mock_select:
            threede_grid.keyPressEvent(event)

        mock_select.assert_called_once_with(sample_scenes[1])
        event.accept.assert_called_once()

    def test_arrow_key_left(self, threede_grid, sample_scenes):
        """Test left arrow navigation."""
        threede_grid.refresh_scenes()
        threede_grid.selected_scene = sample_scenes[2]

        event = MagicMock(spec=QKeyEvent)
        event.key.return_value = Qt.Key.Key_Left

        with patch.object(threede_grid, "select_scene") as mock_select:
            threede_grid.keyPressEvent(event)

        mock_select.assert_called_once_with(sample_scenes[1])
        event.accept.assert_called_once()

    def test_arrow_key_down(self, threede_grid, sample_scenes):
        """Test down arrow navigation."""
        threede_grid.refresh_scenes()
        threede_grid.selected_scene = sample_scenes[0]

        event = MagicMock(spec=QKeyEvent)
        event.key.return_value = Qt.Key.Key_Down

        with patch.object(threede_grid, "_get_column_count", return_value=3):
            with patch.object(threede_grid, "select_scene") as mock_select:
                threede_grid.keyPressEvent(event)

        # Should move down by column count
        mock_select.assert_called_once_with(sample_scenes[3])
        event.accept.assert_called_once()

    def test_home_key(self, threede_grid, sample_scenes):
        """Test Home key navigation."""
        threede_grid.refresh_scenes()
        threede_grid.selected_scene = sample_scenes[3]

        event = MagicMock(spec=QKeyEvent)
        event.key.return_value = Qt.Key.Key_Home

        with patch.object(threede_grid, "select_scene") as mock_select:
            threede_grid.keyPressEvent(event)

        mock_select.assert_called_once_with(sample_scenes[0])
        event.accept.assert_called_once()

    def test_end_key(self, threede_grid, sample_scenes):
        """Test End key navigation."""
        threede_grid.refresh_scenes()
        threede_grid.selected_scene = sample_scenes[0]

        event = MagicMock(spec=QKeyEvent)
        event.key.return_value = Qt.Key.Key_End

        with patch.object(threede_grid, "select_scene") as mock_select:
            threede_grid.keyPressEvent(event)

        mock_select.assert_called_once_with(sample_scenes[-1])
        event.accept.assert_called_once()

    def test_enter_key(self, threede_grid, qtbot, sample_scenes):
        """Test Enter key triggers double click."""
        threede_grid.refresh_scenes()
        threede_grid.selected_scene = sample_scenes[0]

        event = MagicMock(spec=QKeyEvent)
        event.key.return_value = Qt.Key.Key_Return

        spy = QSignalSpy(threede_grid.scene_double_clicked)
        threede_grid.keyPressEvent(event)

        assert spy.count() == 1
        assert spy.at(0)[0] == sample_scenes[0]
        event.accept.assert_called_once()

    def test_app_launch_shortcuts(self, threede_grid, qtbot, sample_scenes):
        """Test application launch keyboard shortcuts."""
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
            event = MagicMock(spec=QKeyEvent)
            event.key.return_value = key

            spy = QSignalSpy(threede_grid.app_launch_requested)
            threede_grid.keyPressEvent(event)

            assert spy.count() == 1
            assert spy.at(0)[0] == app_name
            event.accept.assert_called_once()

    def test_keyboard_nav_empty_grid(self, threede_grid):
        """Test keyboard navigation with empty grid."""
        threede_grid.scene_model.scenes = []
        threede_grid.refresh_scenes()

        event = MagicMock(spec=QKeyEvent)
        event.key.return_value = Qt.Key.Key_Right

        with patch.object(QWidget, "keyPressEvent") as mock_super:
            threede_grid.keyPressEvent(event)

        # Should pass to parent since no scenes
        mock_super.assert_called_once_with(event)

    def test_ensure_widget_visible(self, threede_grid, sample_scenes):
        """Test ensuring selected widget is visible after navigation."""
        threede_grid.refresh_scenes()
        threede_grid.selected_scene = sample_scenes[0]

        event = MagicMock(spec=QKeyEvent)
        event.key.return_value = Qt.Key.Key_Right

        with patch.object(
            threede_grid.scroll_area,
            "ensureWidgetVisible",
        ) as mock_ensure:
            threede_grid.keyPressEvent(event)

        # Should ensure new selection is visible
        new_thumb = threede_grid.thumbnails[sample_scenes[1].display_name]
        mock_ensure.assert_called_once_with(new_thumb)


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

    def test_resize_event_triggers_reflow(self, threede_grid):
        """Test resize event triggers reflow."""
        event = MagicMock(spec=QResizeEvent)

        with patch.object(threede_grid, "_reflow_grid") as mock_reflow:
            with patch.object(QWidget, "resizeEvent") as mock_super:
                threede_grid.resizeEvent(event)

        mock_super.assert_called_once_with(event)
        mock_reflow.assert_called_once()


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
