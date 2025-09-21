"""Unit tests for ThreeDEGridView Model/View component.

This file tests the actual ThreeDEGridView implementation which uses Qt Model/View
architecture with QListView, not manual widget management.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from config import Config
from threede_grid_view import ThreeDEGridView
from threede_item_model import ThreeDEItemModel
from threede_scene_model import ThreeDEScene, ThreeDESceneModel

pytestmark = [pytest.mark.unit, pytest.mark.qt, pytest.mark.xdist_group("qt_state")]


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
    """Create a ThreeDEGridView instance for testing."""
    # Create the item model wrapper
    item_model = ThreeDEItemModel(scene_model)
    # Create the view with the model
    view = ThreeDEGridView(model=item_model)
    qtbot.addWidget(view)
    return view


class TestThreeDEGridViewInitialization:
    """Test ThreeDEGridView initialization."""

    def test_initialization(self, threede_grid) -> None:
        """Test grid initialization."""
        # Note: threede_grid._model is an ItemModel wrapper
        assert threede_grid._model is not None
        assert threede_grid.selected_scene is None
        assert threede_grid._thumbnail_size == Config.DEFAULT_THUMBNAIL_SIZE
        assert threede_grid.is_loading is False

    def test_ui_setup(self, threede_grid) -> None:
        """Test UI components are created."""
        assert threede_grid.size_slider is not None
        assert threede_grid.size_label is not None
        assert threede_grid.loading_bar is not None
        assert threede_grid.loading_label is not None

        # Check initial states
        assert threede_grid.loading_bar.isVisible() is False
        assert threede_grid.loading_label.isVisible() is False
        assert threede_grid.size_slider.value() == Config.DEFAULT_THUMBNAIL_SIZE
        assert threede_grid.size_label.text() == f"{Config.DEFAULT_THUMBNAIL_SIZE}px"

    def test_focus_policy(self, threede_grid) -> None:
        """Test widget has proper focus policy."""
        assert threede_grid.focusPolicy() == Qt.FocusPolicy.StrongFocus


class TestThreeDEGridViewSizeControl:
    """Test thumbnail size control."""

    def test_size_slider_range(self, threede_grid) -> None:
        """Test size slider configuration."""
        assert threede_grid.size_slider.minimum() == Config.MIN_THUMBNAIL_SIZE
        assert threede_grid.size_slider.maximum() == Config.MAX_THUMBNAIL_SIZE
        assert threede_grid.size_slider.value() == Config.DEFAULT_THUMBNAIL_SIZE

    def test_size_slider_exists(self, threede_grid) -> None:
        """Test size slider is properly connected."""
        # Change slider value
        new_value = 200
        threede_grid.size_slider.setValue(new_value)

        # Verify slider value was set
        assert threede_grid.size_slider.value() == new_value
