"""Unit tests for threede_thumbnail_widget module.

This module tests the ThreeDEThumbnailWidget class.
Following the testing guide principles:
- Test behavior, not implementation
- Use real components with test doubles for I/O
- Mock only at system boundaries
- Use QSignalSpy for real Qt signals
"""

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QLabel, QMenu

from threede_scene_model import ThreeDEScene
from threede_thumbnail_widget import ThreeDEThumbnailWidget


# Test Fixtures
@pytest.fixture
def sample_scene():
    """Create a sample ThreeDEScene for testing."""
    return ThreeDEScene(
        show="test_show",
        sequence="seq01",
        shot="shot01",
        workspace_path="/shows/test_show/seq01/seq01_shot01",
        user="testuser",
        plate="FG01",
        scene_path=Path(
            "/shows/test_show/seq01/seq01_shot01/user/testuser/work/3de/scenes/test.3de"
        ),
    )


@pytest.fixture
def threede_widget(qtbot, sample_scene):
    """Create a ThreeDEThumbnailWidget instance for testing."""
    widget = ThreeDEThumbnailWidget(sample_scene)
    qtbot.addWidget(widget)
    return widget


class TestThreeDEThumbnailWidget:
    """Test ThreeDEThumbnailWidget class."""

    def test_initialization(self, threede_widget, sample_scene):
        """Test widget initialization."""
        assert threede_widget.scene == sample_scene
        # The widget inherits from ThumbnailWidgetBase which is a QFrame
        assert isinstance(threede_widget, ThreeDEThumbnailWidget)
        # Check that UI elements were created
        assert hasattr(threede_widget, "shot_label")
        assert hasattr(threede_widget, "user_label")
        assert hasattr(threede_widget, "plate_label")

    def test_custom_ui_setup(self, threede_widget, sample_scene):
        """Test custom UI elements are set up correctly."""
        # Shot label
        assert isinstance(threede_widget.shot_label, QLabel)
        assert threede_widget.shot_label.text() == "seq01_shot01"
        assert threede_widget.shot_label.objectName() == "shot"
        assert threede_widget.shot_label.alignment() == Qt.AlignmentFlag.AlignCenter
        assert threede_widget.shot_label.wordWrap() is True

        # Check font settings
        shot_font = threede_widget.shot_label.font()
        assert shot_font.pointSize() == 10
        assert shot_font.bold() is True

        # User label
        assert isinstance(threede_widget.user_label, QLabel)
        assert threede_widget.user_label.text() == "testuser"
        assert threede_widget.user_label.objectName() == "user"
        assert threede_widget.user_label.alignment() == Qt.AlignmentFlag.AlignCenter

        user_font = threede_widget.user_label.font()
        assert user_font.pointSize() == 8

        # Plate label
        assert isinstance(threede_widget.plate_label, QLabel)
        assert threede_widget.plate_label.text() == "FG01"
        assert threede_widget.plate_label.objectName() == "plate"
        assert threede_widget.plate_label.alignment() == Qt.AlignmentFlag.AlignCenter

        plate_font = threede_widget.plate_label.font()
        assert plate_font.pointSize() == 9
        assert plate_font.bold() is True

    def test_initialization_with_custom_size(self, qtbot, sample_scene):
        """Test widget initialization with custom size."""
        custom_size = 200
        widget = ThreeDEThumbnailWidget(sample_scene, size=custom_size)
        qtbot.addWidget(widget)

        # The size parameter is passed to the base class and stored internally
        assert widget.scene == sample_scene
        # Verify the widget was created (actual size depends on layout)

    def test_selected_style(self, threede_widget):
        """Test the selected style CSS."""
        style = threede_widget._get_selected_style()

        assert isinstance(style, str)
        assert "ThreeDEThumbnailWidget" in style
        assert "background-color: #0d7377" in style
        assert "border: 3px solid #14ffec" in style
        assert "QLabel#shot" in style
        assert "QLabel#user" in style
        assert "QLabel#plate" in style
        assert "color: #14ffec" in style  # Shot label color when selected

    def test_unselected_style(self, threede_widget):
        """Test the unselected style CSS."""
        style = threede_widget._get_unselected_style()

        assert isinstance(style, str)
        assert "ThreeDEThumbnailWidget" in style
        assert "background-color: #2b2b2b" in style
        assert "border: 2px solid #444" in style
        assert "ThreeDEThumbnailWidget:hover" in style
        assert "QLabel#shot" in style
        assert "QLabel#user" in style
        assert "QLabel#plate" in style
        assert "color: white" in style  # Shot label color when unselected

    def test_create_context_menu(self, threede_widget):
        """Test context menu creation."""
        menu = threede_widget._create_context_menu()

        assert isinstance(menu, QMenu)
        actions = menu.actions()
        assert len(actions) == 1
        assert actions[0].text() == "Open Shot Folder"

    def test_signals_exist(self, threede_widget):
        """Test that required signals exist."""
        # These signals should be inherited or defined
        assert hasattr(threede_widget, "clicked")
        assert hasattr(threede_widget, "double_clicked")

    def test_click_signal(self, qtbot, threede_widget, sample_scene):
        """Test that clicked signal is emitted with scene object."""
        # Set up signal spy
        clicked_spy = QSignalSpy(threede_widget.clicked)

        # Simulate a click (from base class behavior)
        # The base class handles the actual mouse event and signal emission
        # We'll directly emit to test the signal connectivity
        threede_widget.clicked.emit(sample_scene)

        assert clicked_spy.count() == 1
        assert clicked_spy.at(0)[0] == sample_scene

    def test_double_click_signal(self, qtbot, threede_widget, sample_scene):
        """Test that double_clicked signal is emitted with scene object."""
        # Set up signal spy
        double_clicked_spy = QSignalSpy(threede_widget.double_clicked)

        # Simulate double click
        threede_widget.double_clicked.emit(sample_scene)

        assert double_clicked_spy.count() == 1
        assert double_clicked_spy.at(0)[0] == sample_scene

    def test_labels_in_layout(self, threede_widget):
        """Test that labels are added to the content layout."""
        # Check that content_layout exists (from base class)
        assert hasattr(threede_widget, "content_layout")

        # Get all widgets in the layout
        layout = threede_widget.content_layout
        widget_count = layout.count()

        # Should have at least the three labels we added
        assert widget_count >= 3

        # Find our labels in the layout
        labels_found = []
        for i in range(widget_count):
            widget = layout.itemAt(i).widget()
            if widget:
                if widget.objectName() in ["shot", "user", "plate"]:
                    labels_found.append(widget.objectName())

        assert "shot" in labels_found
        assert "user" in labels_found
        assert "plate" in labels_found

    def test_inheritance_from_base(self, threede_widget):
        """Test that widget properly inherits from ThumbnailWidgetBase."""
        # Check for base class methods
        assert hasattr(threede_widget, "_setup_custom_ui")
        assert hasattr(threede_widget, "_get_selected_style")
        assert hasattr(threede_widget, "_get_unselected_style")
        assert hasattr(threede_widget, "_create_context_menu")

        # Check that set_selected method exists (from base class)
        assert hasattr(threede_widget, "set_selected")

    def test_scene_data_displayed(self, threede_widget, sample_scene):
        """Test that scene data is properly displayed in labels."""
        # Verify the data is displayed
        assert threede_widget.shot_label.text() == sample_scene.full_name
        assert threede_widget.user_label.text() == sample_scene.user
        assert threede_widget.plate_label.text() == sample_scene.plate

    def test_style_update_called(self, threede_widget):
        """Test that style update is called during initialization."""
        # The _update_style method should be called from _setup_custom_ui
        # We can verify by checking the widget has a stylesheet
        stylesheet = threede_widget.styleSheet()
        assert stylesheet != ""  # Should have some style applied

    def test_context_menu_action_connected(self, threede_widget):
        """Test that context menu action is properly connected."""
        menu = threede_widget._create_context_menu()
        actions = menu.actions()

        # The action should be connected to _open_shot_folder
        actions[0]

        # Check the action has a connection (we can't easily test the actual connection)
        # but we can verify the method exists
        assert hasattr(threede_widget, "_open_shot_folder")

    def test_widget_size_policy(self, threede_widget):
        """Test widget size policy settings."""
        # Widget should have appropriate size policy for thumbnails
        size_policy = threede_widget.sizePolicy()

        # Thumbnails typically have fixed or minimum size policies
        assert size_policy is not None

    def test_scene_with_different_plates(self, qtbot):
        """Test widget with different plate types."""
        scenes = [
            ThreeDEScene(
                show="test",
                sequence="seq01",
                shot="shot01",
                workspace_path="/test",
                user="user1",
                plate="FG01",
                scene_path=Path("/test/fg.3de"),
            ),
            ThreeDEScene(
                show="test",
                sequence="seq01",
                shot="shot02",
                workspace_path="/test",
                user="user2",
                plate="BG01",
                scene_path=Path("/test/bg.3de"),
            ),
            ThreeDEScene(
                show="test",
                sequence="seq01",
                shot="shot03",
                workspace_path="/test",
                user="user3",
                plate="EL01",
                scene_path=Path("/test/el.3de"),
            ),
        ]

        for scene in scenes:
            widget = ThreeDEThumbnailWidget(scene)
            qtbot.addWidget(widget)

            assert widget.plate_label.text() == scene.plate
            assert widget.shot_label.text() == scene.full_name
            assert widget.user_label.text() == scene.user

    def test_widget_with_long_names(self, qtbot):
        """Test widget handles long shot/user names gracefully."""
        scene = ThreeDEScene(
            show="very_long_show_name_that_might_overflow",
            sequence="very_long_sequence_name",
            shot="very_long_shot_name_0001",
            workspace_path="/test",
            user="very_long_username_that_might_also_overflow",
            plate="FG01",
            scene_path=Path("/test/long.3de"),
        )

        widget = ThreeDEThumbnailWidget(scene)
        qtbot.addWidget(widget)

        # Word wrap should be enabled for shot label
        assert widget.shot_label.wordWrap() is True

        # Labels should contain the text even if long
        assert (
            "very_long_sequence_name_very_long_shot_name_0001"
            in widget.shot_label.text()
        )
        assert "very_long_username_that_might_also_overflow" in widget.user_label.text()

    def test_font_configuration(self, threede_widget):
        """Test that fonts are configured as specified."""
        # Shot label font
        shot_font = threede_widget.shot_label.font()
        assert shot_font.pointSize() == 10
        assert shot_font.bold() is True

        # User label font
        user_font = threede_widget.user_label.font()
        assert user_font.pointSize() == 8
        assert user_font.bold() is False  # Should not be bold

        # Plate label font
        plate_font = threede_widget.plate_label.font()
        assert plate_font.pointSize() == 9
        assert plate_font.bold() is True

    def test_label_alignment(self, threede_widget):
        """Test that all labels are center-aligned."""
        assert threede_widget.shot_label.alignment() == Qt.AlignmentFlag.AlignCenter
        assert threede_widget.user_label.alignment() == Qt.AlignmentFlag.AlignCenter
        assert threede_widget.plate_label.alignment() == Qt.AlignmentFlag.AlignCenter

    def test_object_names_for_styling(self, threede_widget):
        """Test that object names are set for CSS styling."""
        assert threede_widget.shot_label.objectName() == "shot"
        assert threede_widget.user_label.objectName() == "user"
        assert threede_widget.plate_label.objectName() == "plate"
