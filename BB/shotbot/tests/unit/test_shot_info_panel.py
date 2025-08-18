"""Unit tests for ShotInfoPanel widget."""

import logging
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout

from cache_manager import CacheManager, ThumbnailCacheLoader
from shot_info_panel import ShotInfoPanel
from shot_model import Shot


@pytest.fixture
def mock_cache_manager():
    """Create a mock cache manager."""
    cache = Mock(spec=CacheManager)
    cache.get_cached_thumbnail.return_value = None
    return cache


@pytest.fixture
def shot_info_panel(qtbot, mock_cache_manager):
    """Create a ShotInfoPanel widget."""
    panel = ShotInfoPanel(cache_manager=mock_cache_manager)
    qtbot.addWidget(panel)
    return panel


@pytest.fixture
def sample_shot():
    """Create a sample shot for testing."""
    shot = Shot(
        show="test_show",
        sequence="seq01",
        shot="shot01",
        workspace_path="/shows/test_show/seq01/shot01",
    )
    return shot


@pytest.fixture
def thumbnail_image(tmp_path):
    """Create a test thumbnail image."""
    image_path = tmp_path / "test_thumbnail.jpg"

    # Create a simple QPixmap and save it
    pixmap = QPixmap(100, 100)
    pixmap.fill(Qt.GlobalColor.blue)
    pixmap.save(str(image_path))

    return image_path


class TestShotInfoPanel:
    """Test ShotInfoPanel widget."""

    def test_init_default_cache_manager(self, qtbot):
        """Test initialization with default cache manager."""
        panel = ShotInfoPanel()
        qtbot.addWidget(panel)

        assert panel.cache_manager is not None
        assert isinstance(panel.cache_manager, CacheManager)
        assert panel._current_shot is None

    def test_init_with_cache_manager(self, shot_info_panel, mock_cache_manager):
        """Test initialization with provided cache manager."""
        assert shot_info_panel.cache_manager is mock_cache_manager
        assert shot_info_panel._current_shot is None

    def test_ui_setup(self, shot_info_panel):
        """Test UI components are properly set up."""
        # Check thumbnail label
        assert hasattr(shot_info_panel, "thumbnail_label")
        assert isinstance(shot_info_panel.thumbnail_label, QLabel)
        assert shot_info_panel.thumbnail_label.width() == 128
        assert shot_info_panel.thumbnail_label.height() == 128

        # Check info labels
        assert hasattr(shot_info_panel, "shot_name_label")
        assert hasattr(shot_info_panel, "show_sequence_label")
        assert hasattr(shot_info_panel, "path_label")

        assert shot_info_panel.shot_name_label.text() == "No Shot Selected"
        assert shot_info_panel.show_sequence_label.text() == ""
        assert shot_info_panel.path_label.text() == ""

        # Check minimum height
        assert shot_info_panel.minimumHeight() == 150

    def test_set_shot_updates_display(self, shot_info_panel, sample_shot):
        """Test setting a shot updates the display."""
        shot_info_panel.set_shot(sample_shot)

        assert shot_info_panel._current_shot == sample_shot
        assert (
            shot_info_panel.shot_name_label.text() == "seq01_shot01"
        )  # full_name is sequence_shot
        assert shot_info_panel.show_sequence_label.text() == "test_show • seq01"
        assert (
            shot_info_panel.path_label.text()
            == "Workspace: /shows/test_show/seq01/shot01"
        )

    def test_set_shot_none_clears_display(self, shot_info_panel, sample_shot):
        """Test setting shot to None clears the display."""
        # First set a shot
        shot_info_panel.set_shot(sample_shot)
        assert (
            shot_info_panel.shot_name_label.text() == "seq01_shot01"
        )  # full_name is sequence_shot

        # Then clear it
        shot_info_panel.set_shot(None)

        assert shot_info_panel._current_shot is None
        assert shot_info_panel.shot_name_label.text() == "No Shot Selected"
        assert shot_info_panel.show_sequence_label.text() == ""
        assert shot_info_panel.path_label.text() == ""

    def test_load_thumbnail_from_cache(
        self,
        shot_info_panel,
        sample_shot,
        mock_cache_manager,
        thumbnail_image,
    ):
        """Test loading thumbnail from cache."""
        # Setup cache to return the test image
        mock_cache_manager.get_cached_thumbnail.return_value = thumbnail_image

        shot_info_panel.set_shot(sample_shot)

        # Check cache was queried
        mock_cache_manager.get_cached_thumbnail.assert_called_once_with(
            "test_show",
            "seq01",
            "shot01",
        )

        # Check thumbnail was loaded
        pixmap = shot_info_panel.thumbnail_label.pixmap()
        assert pixmap is not None
        assert not pixmap.isNull()

    def test_load_thumbnail_from_source(
        self,
        shot_info_panel,
        sample_shot,
        mock_cache_manager,
        thumbnail_image,
        qtbot,
    ):
        """Test loading thumbnail from source when not cached."""
        # Setup cache to return None (not cached)
        mock_cache_manager.get_cached_thumbnail.return_value = None

        # Mock shot's get_thumbnail_path to return test image
        with patch.object(
            sample_shot,
            "get_thumbnail_path",
            return_value=thumbnail_image,
        ):
            shot_info_panel.set_shot(sample_shot)

        # Check cache was queried
        mock_cache_manager.get_cached_thumbnail.assert_called_once()

        # Check thumbnail was loaded
        pixmap = shot_info_panel.thumbnail_label.pixmap()
        assert pixmap is not None
        assert not pixmap.isNull()

    def test_load_thumbnail_no_cache_no_source(
        self,
        shot_info_panel,
        sample_shot,
        mock_cache_manager,
    ):
        """Test placeholder is shown when no thumbnail available."""
        # Setup cache to return None
        mock_cache_manager.get_cached_thumbnail.return_value = None

        # Mock shot's get_thumbnail_path to return None
        with patch.object(sample_shot, "get_thumbnail_path", return_value=None):
            shot_info_panel.set_shot(sample_shot)

        # Check placeholder is shown
        pixmap = shot_info_panel.thumbnail_label.pixmap()
        assert pixmap is not None
        assert shot_info_panel.thumbnail_label.text() == "No Image"

    def test_load_pixmap_from_path_valid(self, shot_info_panel, thumbnail_image):
        """Test loading pixmap from valid path."""
        shot_info_panel._load_pixmap_from_path(thumbnail_image)

        pixmap = shot_info_panel.thumbnail_label.pixmap()
        assert pixmap is not None
        assert not pixmap.isNull()
        # Should be scaled to 128x128 or smaller
        assert pixmap.width() <= 128
        assert pixmap.height() <= 128

    def test_load_pixmap_from_path_string(self, shot_info_panel, thumbnail_image):
        """Test loading pixmap from string path."""
        shot_info_panel._load_pixmap_from_path(str(thumbnail_image))

        pixmap = shot_info_panel.thumbnail_label.pixmap()
        assert pixmap is not None
        assert not pixmap.isNull()

    def test_load_pixmap_from_path_nonexistent(self, shot_info_panel, tmp_path, caplog):
        """Test loading pixmap from nonexistent path."""
        nonexistent = tmp_path / "nonexistent.jpg"

        with caplog.at_level(logging.DEBUG):
            shot_info_panel._load_pixmap_from_path(nonexistent)

        assert "does not exist" in caplog.text
        assert shot_info_panel.thumbnail_label.text() == "No Image"

    def test_load_pixmap_from_path_none(self, shot_info_panel, caplog):
        """Test loading pixmap with None path."""
        with caplog.at_level(logging.DEBUG):
            shot_info_panel._load_pixmap_from_path(None)

        assert "No path provided" in caplog.text
        assert shot_info_panel.thumbnail_label.text() == "No Image"

    def test_load_pixmap_from_path_invalid_image(
        self,
        shot_info_panel,
        tmp_path,
        caplog,
    ):
        """Test loading invalid image file."""
        # Create a text file with .jpg extension
        invalid_image = tmp_path / "invalid.jpg"
        invalid_image.write_text("not an image")

        with caplog.at_level(logging.DEBUG):
            shot_info_panel._load_pixmap_from_path(invalid_image)

        assert "Failed to load thumbnail" in caplog.text
        assert shot_info_panel.thumbnail_label.text() == "No Image"

    def test_load_pixmap_dimension_validation(self, shot_info_panel, thumbnail_image):
        """Test image dimension validation."""
        # Patch the utils module ImageUtils
        with patch("utils.ImageUtils") as mock_image_utils:
            # Setup dimension check to fail
            mock_image_utils.validate_image_dimensions.return_value = False

            shot_info_panel._load_pixmap_from_path(thumbnail_image)

            # Should fall back to placeholder
            assert shot_info_panel.thumbnail_label.text() == "No Image"

    def test_on_thumbnail_cached_current_shot(
        self,
        shot_info_panel,
        sample_shot,
        thumbnail_image,
    ):
        """Test handling thumbnail cached signal for current shot."""
        shot_info_panel._current_shot = sample_shot

        shot_info_panel._on_thumbnail_cached(
            "test_show",
            "seq01",
            "shot01",
            str(thumbnail_image),
        )

        # Should load the cached thumbnail
        pixmap = shot_info_panel.thumbnail_label.pixmap()
        assert pixmap is not None
        assert not pixmap.isNull()

    def test_on_thumbnail_cached_different_shot(
        self,
        shot_info_panel,
        sample_shot,
        thumbnail_image,
    ):
        """Test handling thumbnail cached signal for different shot."""
        shot_info_panel._current_shot = sample_shot
        # Set an initial placeholder
        shot_info_panel._set_placeholder_thumbnail()
        initial_text = shot_info_panel.thumbnail_label.text()

        shot_info_panel._on_thumbnail_cached(
            "other_show",
            "seq02",
            "shot02",
            str(thumbnail_image),
        )

        # Should not update since it's a different shot
        assert shot_info_panel.thumbnail_label.text() == initial_text

    def test_on_thumbnail_cached_no_current_shot(
        self,
        shot_info_panel,
        thumbnail_image,
    ):
        """Test handling thumbnail cached signal with no current shot."""
        shot_info_panel._current_shot = None

        shot_info_panel._on_thumbnail_cached(
            "test_show",
            "seq01",
            "shot01",
            str(thumbnail_image),
        )

        # Should not crash, but also not load anything
        assert (
            shot_info_panel.thumbnail_label.text() == ""
            or shot_info_panel.thumbnail_label.text() == "No Image"
        )

    def test_set_placeholder_thumbnail(self, shot_info_panel):
        """Test setting placeholder thumbnail."""
        shot_info_panel._set_placeholder_thumbnail()

        pixmap = shot_info_panel.thumbnail_label.pixmap()
        assert pixmap is not None
        # Pixmap will be null (0x0) when filled with transparent
        # but the label will have the right text
        assert shot_info_panel.thumbnail_label.text() == "No Image"

    def test_fonts_configured(self, shot_info_panel):
        """Test that fonts are properly configured."""
        # Shot name should be 18pt bold
        shot_font = shot_info_panel.shot_name_label.font()
        assert shot_font.pointSize() == 18
        assert shot_font.weight() == QFont.Weight.Bold

        # Show/sequence should be 12pt
        show_font = shot_info_panel.show_sequence_label.font()
        assert show_font.pointSize() == 12

        # Path should be 9pt
        path_font = shot_info_panel.path_label.font()
        assert path_font.pointSize() == 9

    def test_layout_structure(self, shot_info_panel):
        """Test the layout structure is correct."""
        main_layout = shot_info_panel.layout()
        assert isinstance(main_layout, QHBoxLayout)
        assert main_layout.count() == 2  # Thumbnail + info layout

        # First item should be thumbnail label
        item = main_layout.itemAt(0)
        assert item.widget() == shot_info_panel.thumbnail_label

        # Second item should be info layout
        info_item = main_layout.itemAt(1)
        assert isinstance(info_item.layout(), QVBoxLayout)

    @patch("shot_info_panel.QThreadPool")
    def test_thumbnail_caching_starts_worker(
        self,
        mock_thread_pool,
        shot_info_panel,
        sample_shot,
        mock_cache_manager,
        thumbnail_image,
    ):
        """Test that thumbnail caching starts a worker thread."""
        # Setup
        mock_cache_manager.get_cached_thumbnail.return_value = None
        mock_pool_instance = Mock()
        mock_thread_pool.globalInstance.return_value = mock_pool_instance

        with patch.object(
            sample_shot,
            "get_thumbnail_path",
            return_value=thumbnail_image,
        ):
            shot_info_panel.set_shot(sample_shot)

        # Check that a worker was started
        mock_pool_instance.start.assert_called_once()

        # Check that the worker is a ThumbnailCacheLoader
        worker = mock_pool_instance.start.call_args[0][0]
        assert isinstance(worker, ThumbnailCacheLoader)

    def test_error_handling_permission_error(
        self,
        shot_info_panel,
        tmp_path,
        caplog,
        monkeypatch,
    ):
        """Test handling permission error when loading thumbnail."""
        test_file = tmp_path / "test.jpg"
        test_file.write_text("dummy")

        # Create a mock QPixmap class that raises PermissionError only for our test file
        def mock_pixmap(*args, **kwargs):
            if args and str(test_file) in str(args[0]):
                raise PermissionError("Access denied")
            # Return a normal QPixmap for placeholder
            pixmap = QPixmap()
            if args and isinstance(args[0], int):
                # For QPixmap(width, height) used in placeholder
                real_pixmap = QPixmap(*args)
                return real_pixmap
            return pixmap

        monkeypatch.setattr("shot_info_panel.QPixmap", mock_pixmap)

        with caplog.at_level(logging.WARNING):
            shot_info_panel._load_pixmap_from_path(test_file)

        assert "Permission denied" in caplog.text
        assert shot_info_panel.thumbnail_label.text() == "No Image"

    def test_error_handling_memory_error(
        self,
        shot_info_panel,
        tmp_path,
        caplog,
        monkeypatch,
    ):
        """Test handling memory error when loading thumbnail."""
        test_file = tmp_path / "test.jpg"
        test_file.write_text("dummy")

        # Create a mock QPixmap class that raises MemoryError only for our test file
        def mock_pixmap(*args, **kwargs):
            if args and str(test_file) in str(args[0]):
                raise MemoryError("Out of memory")
            # Return a normal QPixmap for placeholder
            pixmap = QPixmap()
            if args and isinstance(args[0], int):
                # For QPixmap(width, height) used in placeholder
                real_pixmap = QPixmap(*args)
                return real_pixmap
            return pixmap

        monkeypatch.setattr("shot_info_panel.QPixmap", mock_pixmap)

        with caplog.at_level(logging.ERROR):
            shot_info_panel._load_pixmap_from_path(test_file)

        assert "Out of memory" in caplog.text
        assert shot_info_panel.thumbnail_label.text() == "No Image"

    def test_error_handling_io_error(
        self,
        shot_info_panel,
        tmp_path,
        caplog,
        monkeypatch,
    ):
        """Test handling I/O error when loading thumbnail."""
        test_file = tmp_path / "test.jpg"
        test_file.write_text("dummy")

        # Create a mock QPixmap class that raises IOError only for our test file
        def mock_pixmap(*args, **kwargs):
            if args and str(test_file) in str(args[0]):
                raise IOError("I/O error")
            # Return a normal QPixmap for placeholder
            pixmap = QPixmap()
            if args and isinstance(args[0], int):
                # For QPixmap(width, height) used in placeholder
                real_pixmap = QPixmap(*args)
                return real_pixmap
            return pixmap

        monkeypatch.setattr("shot_info_panel.QPixmap", mock_pixmap)

        with caplog.at_level(logging.WARNING):
            shot_info_panel._load_pixmap_from_path(test_file)

        assert "I/O error" in caplog.text
        assert shot_info_panel.thumbnail_label.text() == "No Image"

    def test_error_handling_unexpected_error(
        self,
        shot_info_panel,
        tmp_path,
        caplog,
        monkeypatch,
    ):
        """Test handling unexpected error when loading thumbnail."""
        test_file = tmp_path / "test.jpg"
        test_file.write_text("dummy")

        # Create a mock QPixmap class that raises ValueError only for our test file
        def mock_pixmap(*args, **kwargs):
            if args and str(test_file) in str(args[0]):
                raise ValueError("Unexpected error")
            # Return a normal QPixmap for placeholder
            pixmap = QPixmap()
            if args and isinstance(args[0], int):
                # For QPixmap(width, height) used in placeholder
                real_pixmap = QPixmap(*args)
                return real_pixmap
            return pixmap

        monkeypatch.setattr("shot_info_panel.QPixmap", mock_pixmap)

        with caplog.at_level(logging.ERROR):
            shot_info_panel._load_pixmap_from_path(test_file)

        assert "Unexpected error" in caplog.text
        assert shot_info_panel.thumbnail_label.text() == "No Image"

    def test_scaled_pixmap_null_handling(self, shot_info_panel, tmp_path, caplog):
        """Test handling null pixmap after scaling."""
        # Create a valid image
        image_path = tmp_path / "test.jpg"
        pixmap = QPixmap(100, 100)
        pixmap.fill(Qt.GlobalColor.red)
        pixmap.save(str(image_path))

        with patch.object(QPixmap, "scaled") as mock_scaled:
            # Make scaled return a null pixmap
            null_pixmap = QPixmap()
            mock_scaled.return_value = null_pixmap

            with caplog.at_level(logging.WARNING):
                shot_info_panel._load_pixmap_from_path(image_path)

            assert "Failed to scale thumbnail" in caplog.text
            assert shot_info_panel.thumbnail_label.text() == "No Image"
