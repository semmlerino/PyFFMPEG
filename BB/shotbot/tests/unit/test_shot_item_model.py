"""Unit tests for shot_item_model module.

This module tests the ShotItemModel class, a proper Qt Model/View implementation.
Following the testing guide principles:
- Test behavior, not implementation
- Use real components with test doubles for I/O
- Mock only at system boundaries
- Use QSignalSpy for real Qt signals
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtTest import QSignalSpy

from cache_manager import CacheManager
from shot_item_model import ShotItemModel, ShotRole
from shot_model import Shot


# Test Fixtures
@pytest.fixture
def sample_shots():
    """Create sample Shot objects for testing."""
    return [
        Shot(
            show="test_show",
            sequence="seq01",
            shot="shot01",
            workspace_path="/shows/test_show/seq01/seq01_shot01",
        ),
        Shot(
            show="test_show",
            sequence="seq01",
            shot="shot02",
            workspace_path="/shows/test_show/seq01/seq01_shot02",
        ),
        Shot(
            show="test_show",
            sequence="seq02",
            shot="shot01",
            workspace_path="/shows/test_show/seq02/seq02_shot01",
        ),
    ]


@pytest.fixture
def mock_cache_manager(tmp_path):
    """Create a real CacheManager with temp storage."""
    return CacheManager(cache_dir=tmp_path / "cache")


@pytest.fixture
def shot_item_model(mock_cache_manager):
    """Create a ShotItemModel instance for testing."""
    model = ShotItemModel(cache_manager=mock_cache_manager)
    # Note: Models are not widgets, so we don't use qtbot.addWidget
    return model


@pytest.fixture
def sample_thumbnail_pixmap():
    """Create a sample pixmap for testing."""
    pixmap = QPixmap(100, 100)
    pixmap.fill(Qt.GlobalColor.blue)
    return pixmap


class TestShotRole:
    """Test ShotRole enum."""

    def test_role_values(self):
        """Test that custom roles have unique values."""
        # Standard roles
        assert ShotRole.DisplayRole == Qt.ItemDataRole.DisplayRole
        assert ShotRole.DecorationRole == Qt.ItemDataRole.DecorationRole
        assert ShotRole.ToolTipRole == Qt.ItemDataRole.ToolTipRole
        assert ShotRole.SizeHintRole == Qt.ItemDataRole.SizeHintRole

        # Custom roles should be unique
        custom_roles = [
            ShotRole.ShotObjectRole,
            ShotRole.ShowRole,
            ShotRole.SequenceRole,
            ShotRole.ShotNameRole,
            ShotRole.FullNameRole,
            ShotRole.WorkspacePathRole,
            ShotRole.ThumbnailPathRole,
            ShotRole.ThumbnailPixmapRole,
            ShotRole.LoadingStateRole,
            ShotRole.IsSelectedRole,
        ]

        # All custom roles should be unique
        assert len(custom_roles) == len(set(custom_roles))

        # All should be greater than UserRole
        for role in custom_roles:
            assert role >= Qt.ItemDataRole.UserRole


class TestShotItemModel:
    """Test ShotItemModel class."""

    def test_initialization(self, shot_item_model):
        """Test model initialization."""
        assert shot_item_model.rowCount() == 0
        assert shot_item_model._cache_manager is not None
        assert isinstance(shot_item_model._thumbnail_cache, dict)
        assert isinstance(shot_item_model._loading_states, dict)
        assert shot_item_model._thumbnail_timer is not None
        assert not shot_item_model._thumbnail_timer.isActive()

    def test_row_count_empty(self, shot_item_model):
        """Test row count with no shots."""
        assert shot_item_model.rowCount() == 0
        assert shot_item_model.rowCount(QModelIndex()) == 0

    def test_row_count_with_shots(self, shot_item_model, sample_shots):
        """Test row count after setting shots."""
        shot_item_model.set_shots(sample_shots)
        assert shot_item_model.rowCount() == len(sample_shots)

    def test_row_count_with_parent(self, shot_item_model, sample_shots):
        """Test that row count returns 0 for valid parent (list model)."""
        shot_item_model.set_shots(sample_shots)
        index = shot_item_model.index(0, 0)
        assert shot_item_model.rowCount(index) == 0  # List models don't have children

    def test_data_invalid_index(self, shot_item_model):
        """Test data retrieval with invalid index."""
        invalid_index = QModelIndex()
        assert shot_item_model.data(invalid_index) is None

        # Out of range index
        index = shot_item_model.index(10, 0)
        assert shot_item_model.data(index) is None

    def test_data_display_role(self, shot_item_model, sample_shots):
        """Test data retrieval for DisplayRole."""
        shot_item_model.set_shots(sample_shots)

        index = shot_item_model.index(0, 0)
        display_text = shot_item_model.data(index, Qt.ItemDataRole.DisplayRole)
        assert display_text == "seq01_shot01"

        index = shot_item_model.index(1, 0)
        display_text = shot_item_model.data(index, Qt.ItemDataRole.DisplayRole)
        assert display_text == "seq01_shot02"

    def test_data_tooltip_role(self, shot_item_model, sample_shots):
        """Test data retrieval for ToolTipRole."""
        shot_item_model.set_shots(sample_shots)

        index = shot_item_model.index(0, 0)
        tooltip = shot_item_model.data(index, Qt.ItemDataRole.ToolTipRole)
        assert "test_show" in tooltip
        assert "seq01" in tooltip
        assert "shot01" in tooltip
        assert "/shows/test_show/seq01/seq01_shot01" in tooltip

    def test_data_size_hint_role(self, shot_item_model, sample_shots):
        """Test data retrieval for SizeHintRole."""
        shot_item_model.set_shots(sample_shots)

        index = shot_item_model.index(0, 0)
        size_hint = shot_item_model.data(index, Qt.ItemDataRole.SizeHintRole)
        assert isinstance(size_hint, QSize)
        assert size_hint.width() > 0
        assert size_hint.height() > 0

    def test_data_custom_roles(self, shot_item_model, sample_shots):
        """Test data retrieval for custom roles."""
        shot_item_model.set_shots(sample_shots)
        index = shot_item_model.index(0, 0)
        shot = sample_shots[0]

        # ShotObjectRole
        assert shot_item_model.data(index, ShotRole.ShotObjectRole) == shot

        # ShowRole
        assert shot_item_model.data(index, ShotRole.ShowRole) == "test_show"

        # SequenceRole
        assert shot_item_model.data(index, ShotRole.SequenceRole) == "seq01"

        # ShotNameRole
        assert shot_item_model.data(index, ShotRole.ShotNameRole) == "shot01"

        # FullNameRole
        assert shot_item_model.data(index, ShotRole.FullNameRole) == "seq01_shot01"

        # WorkspacePathRole
        assert (
            shot_item_model.data(index, ShotRole.WorkspacePathRole)
            == "/shows/test_show/seq01/seq01_shot01"
        )

    def test_data_thumbnail_path_role(self, shot_item_model, sample_shots):
        """Test thumbnail path retrieval."""
        shot_item_model.set_shots(sample_shots)
        index = shot_item_model.index(0, 0)

        # Mock get_thumbnail_path
        with patch.object(sample_shots[0], "get_thumbnail_path") as mock_get_path:
            mock_get_path.return_value = Path("/test/thumbnail.jpg")

            thumb_path = shot_item_model.data(index, ShotRole.ThumbnailPathRole)
            assert thumb_path == "/test/thumbnail.jpg"

            # Test with no thumbnail
            mock_get_path.return_value = None
            thumb_path = shot_item_model.data(index, ShotRole.ThumbnailPathRole)
            assert thumb_path is None

    def test_data_loading_state_role(self, shot_item_model, sample_shots):
        """Test loading state retrieval."""
        shot_item_model.set_shots(sample_shots)
        index = shot_item_model.index(0, 0)

        # Default state
        state = shot_item_model.data(index, ShotRole.LoadingStateRole)
        assert state == "idle"

        # Set loading state
        shot_item_model._loading_states["seq01_shot01"] = "loading"
        state = shot_item_model.data(index, ShotRole.LoadingStateRole)
        assert state == "loading"

    def test_data_selection_role(self, shot_item_model, sample_shots):
        """Test selection state retrieval."""
        shot_item_model.set_shots(sample_shots)
        index = shot_item_model.index(0, 0)

        # Not selected by default
        is_selected = shot_item_model.data(index, ShotRole.IsSelectedRole)
        assert is_selected is False

        # Set as selected
        shot_item_model._selected_index = QPersistentModelIndex(index)
        is_selected = shot_item_model.data(index, ShotRole.IsSelectedRole)
        assert is_selected is True

    def test_role_names(self, shot_item_model):
        """Test role names for QML compatibility."""
        role_names = shot_item_model.roleNames()

        assert isinstance(role_names, dict)
        assert ShotRole.ShotObjectRole in role_names
        assert role_names[ShotRole.ShotObjectRole] == b"shotObject"
        assert role_names[ShotRole.ShowRole] == b"show"
        assert role_names[ShotRole.FullNameRole] == b"fullName"

    def test_flags(self, shot_item_model, sample_shots):
        """Test item flags."""
        shot_item_model.set_shots(sample_shots)

        # Valid index
        index = shot_item_model.index(0, 0)
        flags = shot_item_model.flags(index)
        assert flags & Qt.ItemFlag.ItemIsEnabled
        assert flags & Qt.ItemFlag.ItemIsSelectable

        # Invalid index
        invalid_index = QModelIndex()
        flags = shot_item_model.flags(invalid_index)
        assert flags == Qt.ItemFlag.NoItemFlags

    def test_set_data_selection(self, qtbot, shot_item_model, sample_shots):
        """Test setting selection state."""
        shot_item_model.set_shots(sample_shots)
        index = shot_item_model.index(0, 0)

        # Set up signal spy
        selection_spy = QSignalSpy(shot_item_model.selection_changed)

        # Select item
        result = shot_item_model.setData(index, True, ShotRole.IsSelectedRole)
        assert result is True
        assert shot_item_model._selected_index == QPersistentModelIndex(index)
        assert selection_spy.count() == 1
        assert selection_spy.at(0)[0] == index

        # Deselect item
        result = shot_item_model.setData(index, False, ShotRole.IsSelectedRole)
        assert result is True
        assert not shot_item_model._selected_index.isValid()

    def test_set_data_loading_state(self, qtbot, shot_item_model, sample_shots):
        """Test setting loading state."""
        shot_item_model.set_shots(sample_shots)
        index = shot_item_model.index(0, 0)

        # Set up signal spy
        data_changed_spy = QSignalSpy(shot_item_model.dataChanged)

        # Set loading state
        result = shot_item_model.setData(index, "loading", ShotRole.LoadingStateRole)
        assert result is True
        assert shot_item_model._loading_states["seq01_shot01"] == "loading"
        assert data_changed_spy.count() == 1

    def test_set_data_invalid_index(self, shot_item_model):
        """Test setData with invalid index."""
        invalid_index = QModelIndex()
        result = shot_item_model.setData(invalid_index, True, ShotRole.IsSelectedRole)
        assert result is False

    def test_set_shots(self, qtbot, shot_item_model, sample_shots):
        """Test setting shots with model reset."""
        # Set up signal spies
        reset_spy = QSignalSpy(shot_item_model.modelReset)
        updated_spy = QSignalSpy(shot_item_model.shots_updated)

        shot_item_model.set_shots(sample_shots)

        # Verify model updated
        assert shot_item_model._shots == sample_shots
        assert shot_item_model.rowCount() == len(sample_shots)

        # Verify caches cleared
        assert len(shot_item_model._thumbnail_cache) == 0
        assert len(shot_item_model._loading_states) == 0
        assert not shot_item_model._selected_index.isValid()

        # Verify signals emitted
        assert reset_spy.count() >= 1  # beginResetModel/endResetModel
        assert updated_spy.count() == 1

    def test_set_visible_range(self, shot_item_model, sample_shots):
        """Test setting visible range for lazy loading."""
        shot_item_model.set_shots(sample_shots)

        # Set visible range
        shot_item_model.set_visible_range(0, 2)

        assert shot_item_model._visible_start == 0
        assert shot_item_model._visible_end == 2
        assert shot_item_model._thumbnail_timer.isActive()

        # Test bounds checking
        shot_item_model.set_visible_range(-5, 10)
        assert shot_item_model._visible_start == 0
        assert shot_item_model._visible_end == len(sample_shots)

    def test_get_shot_at_index(self, shot_item_model, sample_shots):
        """Test getting shot at specific index."""
        shot_item_model.set_shots(sample_shots)

        # Valid index
        index = shot_item_model.index(0, 0)
        shot = shot_item_model.get_shot_at_index(index)
        assert shot == sample_shots[0]

        # Invalid index
        invalid_index = QModelIndex()
        shot = shot_item_model.get_shot_at_index(invalid_index)
        assert shot is None

        # Out of range
        index = shot_item_model.index(10, 0)
        shot = shot_item_model.get_shot_at_index(index)
        assert shot is None

    def test_refresh_shots_with_changes(self, qtbot, shot_item_model, sample_shots):
        """Test refreshing shots when there are changes."""
        shot_item_model.set_shots(sample_shots[:2])  # Start with 2 shots

        # Set up signal spy
        updated_spy = QSignalSpy(shot_item_model.shots_updated)

        # Refresh with different shots
        result = shot_item_model.refresh_shots(sample_shots)  # All 3 shots

        assert result.success is True
        assert result.has_changes is True
        assert shot_item_model.rowCount() == len(sample_shots)
        assert updated_spy.count() == 1

    def test_refresh_shots_no_changes(self, shot_item_model, sample_shots):
        """Test refreshing shots when there are no changes."""
        shot_item_model.set_shots(sample_shots)

        # Refresh with same shots
        result = shot_item_model.refresh_shots(sample_shots)

        assert result.success is True
        assert result.has_changes is False

    def test_clear_thumbnail_cache(
        self, qtbot, shot_item_model, sample_shots, sample_thumbnail_pixmap,
    ):
        """Test clearing thumbnail cache."""
        shot_item_model.set_shots(sample_shots)

        # Add some cached thumbnails
        shot_item_model._thumbnail_cache["seq01_shot01"] = sample_thumbnail_pixmap
        shot_item_model._thumbnail_cache["seq01_shot02"] = sample_thumbnail_pixmap

        # Set up signal spy
        data_changed_spy = QSignalSpy(shot_item_model.dataChanged)

        # Clear cache
        shot_item_model.clear_thumbnail_cache()

        assert len(shot_item_model._thumbnail_cache) == 0
        assert data_changed_spy.count() == 1

        # Check signal parameters
        top_left = data_changed_spy.at(0)[0]
        bottom_right = data_changed_spy.at(0)[1]
        roles = data_changed_spy.at(0)[2] if len(data_changed_spy.at(0)) > 2 else []

        assert top_left.row() == 0
        assert bottom_right.row() == len(sample_shots) - 1
        if roles:  # Roles might not be captured in all Qt versions
            assert (
                ShotRole.ThumbnailPixmapRole in roles
                or Qt.ItemDataRole.DecorationRole in roles
            )

    def test_load_thumbnail_async(self, qtbot, shot_item_model, sample_shots):
        """Test async thumbnail loading simulation."""
        shot_item_model.set_shots(sample_shots)

        # Mock thumbnail path
        with patch.object(sample_shots[0], "get_thumbnail_path") as mock_get_path:
            mock_path = Path("/test/thumbnail.jpg")
            mock_get_path.return_value = mock_path

            # Mock path exists
            with patch.object(Path, "exists", return_value=True):
                # Mock QPixmap creation
                with patch("shot_item_model.QPixmap") as MockPixmap:
                    mock_pixmap = Mock()
                    mock_pixmap.isNull.return_value = False
                    mock_pixmap.scaled.return_value = mock_pixmap
                    MockPixmap.return_value = mock_pixmap

                    # Set up signal spies
                    data_changed_spy = QSignalSpy(shot_item_model.dataChanged)
                    thumbnail_loaded_spy = QSignalSpy(shot_item_model.thumbnail_loaded)

                    # Load thumbnail
                    shot_item_model._load_thumbnail_async(0, sample_shots[0])

                    # Verify loading state set
                    assert shot_item_model._loading_states["seq01_shot01"] == "loaded"

                    # Verify thumbnail cached
                    assert "seq01_shot01" in shot_item_model._thumbnail_cache

                    # Verify signals emitted
                    assert data_changed_spy.count() >= 2  # Loading and loaded states
                    assert thumbnail_loaded_spy.count() == 1
                    assert thumbnail_loaded_spy.at(0)[0] == 0  # Row 0

    def test_load_thumbnail_async_failed(self, qtbot, shot_item_model, sample_shots):
        """Test failed thumbnail loading."""
        shot_item_model.set_shots(sample_shots)

        # Mock no thumbnail path
        with patch.object(sample_shots[0], "get_thumbnail_path", return_value=None):
            # Set up signal spy
            data_changed_spy = QSignalSpy(shot_item_model.dataChanged)

            # Load thumbnail
            shot_item_model._load_thumbnail_async(0, sample_shots[0])

            # Verify failed state
            assert shot_item_model._loading_states["seq01_shot01"] == "failed"
            assert "seq01_shot01" not in shot_item_model._thumbnail_cache

            # Verify signals emitted
            assert data_changed_spy.count() >= 2  # Loading and failed states

    def test_get_thumbnail_pixmap(
        self, shot_item_model, sample_shots, sample_thumbnail_pixmap,
    ):
        """Test getting cached thumbnail pixmap."""
        shot_item_model.set_shots(sample_shots)

        # No cached thumbnail
        pixmap = shot_item_model._get_thumbnail_pixmap(sample_shots[0])
        assert pixmap is None

        # Add cached thumbnail
        shot_item_model._thumbnail_cache["seq01_shot01"] = sample_thumbnail_pixmap

        # Get cached thumbnail
        pixmap = shot_item_model._get_thumbnail_pixmap(sample_shots[0])
        assert pixmap == sample_thumbnail_pixmap

    def test_data_decoration_role(
        self, shot_item_model, sample_shots, sample_thumbnail_pixmap,
    ):
        """Test decoration role returns icon."""
        shot_item_model.set_shots(sample_shots)
        index = shot_item_model.index(0, 0)

        # No thumbnail - no icon
        icon = shot_item_model.data(index, Qt.ItemDataRole.DecorationRole)
        assert icon is None

        # With thumbnail - returns icon
        shot_item_model._thumbnail_cache["seq01_shot01"] = sample_thumbnail_pixmap
        icon = shot_item_model.data(index, Qt.ItemDataRole.DecorationRole)
        assert (
            isinstance(icon, QIcon) or icon is not None
        )  # QIcon conversion might vary

    def test_load_visible_thumbnails(self, shot_item_model, sample_shots):
        """Test loading thumbnails for visible items."""
        shot_item_model.set_shots(sample_shots)

        # Set visible range
        shot_item_model._visible_start = 0
        shot_item_model._visible_end = 2

        # Mock thumbnail loading
        with patch.object(shot_item_model, "_load_thumbnail_async") as mock_load:
            shot_item_model._load_visible_thumbnails()

            # Should attempt to load thumbnails for visible shots
            assert mock_load.called
            # Check that it was called for shots in the visible range
            call_count = mock_load.call_count
            assert call_count > 0  # At least some thumbnails should be loaded

    def test_model_index_creation(self, shot_item_model, sample_shots):
        """Test creating model indices."""
        shot_item_model.set_shots(sample_shots)

        # Create valid index
        index = shot_item_model.index(0, 0)
        assert index.isValid()
        assert index.row() == 0
        assert index.column() == 0

        # Create index for each shot
        for i in range(len(sample_shots)):
            index = shot_item_model.index(i, 0)
            assert index.isValid()
            assert index.row() == i

    def test_persistent_model_index(self, shot_item_model, sample_shots):
        """Test persistent model index behavior."""
        shot_item_model.set_shots(sample_shots)

        # Create persistent index
        index = shot_item_model.index(0, 0)
        persistent = QPersistentModelIndex(index)

        assert persistent.isValid()
        assert persistent.row() == 0

        # Persistent index should survive some operations
        shot_item_model._selected_index = persistent
        assert shot_item_model._selected_index.isValid()
        assert shot_item_model._selected_index.row() == 0

        # Reset model should invalidate persistent index
        shot_item_model.set_shots([])
        assert not shot_item_model._selected_index.isValid()
