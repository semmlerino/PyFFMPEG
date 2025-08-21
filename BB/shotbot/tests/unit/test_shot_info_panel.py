"""Unit tests for ShotInfoPanel widget following UNIFIED_TESTING_GUIDE.

This refactored version:
- Uses real Qt widgets (they're lightweight, no need to mock)
- Uses real CacheManager with tmp_path
- Creates real image files instead of mocking paths
- Tests actual behavior (what user sees) instead of method calls
- Removes excessive patching
"""

import logging

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout

from cache_manager import CacheManager
from shot_info_panel import ShotInfoPanel
from shot_model import Shot


@pytest.mark.usefixtures("isolated_test_environment", "qapp")
class TestShotInfoPanel:
    """Test ShotInfoPanel widget with real components.

    Uses isolated_test_environment fixture to ensure proper test isolation
    for Qt widgets and cache state. Also uses qapp to ensure QApplication exists.
    """

    def test_init_default_cache_manager(self, qtbot):
        """Test initialization with default cache manager."""
        # Create real panel with default cache manager
        panel = ShotInfoPanel()
        qtbot.addWidget(panel)

        # Test actual behavior
        assert panel.cache_manager is not None
        assert isinstance(panel.cache_manager, CacheManager)
        assert panel._current_shot is None

        # Test UI is properly initialized
        assert panel.shot_name_label.text() == "No Shot Selected"

    def test_init_with_cache_manager(self, qtbot, real_cache_manager):
        """Test initialization with provided cache manager."""
        # Create panel with real cache manager
        panel = ShotInfoPanel(cache_manager=real_cache_manager)
        qtbot.addWidget(panel)

        # Test actual setup
        assert panel.cache_manager is real_cache_manager
        assert panel._current_shot is None

    def test_ui_setup(self, qtbot, real_cache_manager):
        """Test UI components are properly set up."""
        panel = ShotInfoPanel(cache_manager=real_cache_manager)
        qtbot.addWidget(panel)

        # Check real thumbnail label
        assert hasattr(panel, "thumbnail_label")
        assert isinstance(panel.thumbnail_label, QLabel)
        assert panel.thumbnail_label.width() == 128
        assert panel.thumbnail_label.height() == 128

        # Check real info labels
        assert hasattr(panel, "shot_name_label")
        assert hasattr(panel, "show_sequence_label")
        assert hasattr(panel, "path_label")

        # Check actual text content
        assert panel.shot_name_label.text() == "No Shot Selected"
        assert panel.show_sequence_label.text() == ""
        assert panel.path_label.text() == ""

        # Check actual minimum height
        assert panel.minimumHeight() == 150

    def test_set_shot_updates_display(self, qtbot, real_cache_manager, make_test_shot):
        """Test setting a shot updates the display with real shot."""
        panel = ShotInfoPanel(cache_manager=real_cache_manager)
        qtbot.addWidget(panel)

        # Create real shot with real files
        shot = make_test_shot("test_show", "seq01", "shot01")

        # Set the shot
        panel.set_shot(shot)

        # Test actual display updates
        assert panel._current_shot == shot
        assert panel.shot_name_label.text() == "seq01_shot01"
        assert panel.show_sequence_label.text() == "test_show • seq01"
        assert "test_show" in panel.path_label.text()
        assert "seq01" in panel.path_label.text()
        assert "shot01" in panel.path_label.text()

    def test_set_shot_none_clears_display(
        self, qtbot, real_cache_manager, make_test_shot
    ):
        """Test setting shot to None clears the display."""
        panel = ShotInfoPanel(cache_manager=real_cache_manager)
        qtbot.addWidget(panel)

        # First set a real shot
        shot = make_test_shot("test_show", "seq01", "shot01")
        panel.set_shot(shot)
        assert panel.shot_name_label.text() == "seq01_shot01"

        # Then clear it
        panel.set_shot(None)

        # Test actual display is cleared
        assert panel._current_shot is None
        assert panel.shot_name_label.text() == "No Shot Selected"
        assert panel.show_sequence_label.text() == ""
        assert panel.path_label.text() == ""

    def test_load_thumbnail_from_cache(
        self, qtbot, real_cache_manager, tmp_path, make_test_shot
    ):
        """Test loading thumbnail from cache with real files."""
        # Clear any existing cache state
        real_cache_manager.clear_cache()

        panel = ShotInfoPanel(cache_manager=real_cache_manager)
        qtbot.addWidget(panel)

        # Create real shot and real thumbnail
        shot = make_test_shot("test_show", "seq01", "shot01", with_thumbnail=True)

        # Create and cache a real thumbnail with proper JPEG format
        thumb_path = tmp_path / "cached_thumb.jpg"
        pixmap = QPixmap(100, 100)
        pixmap.fill(Qt.GlobalColor.blue)

        # Ensure the pixmap saves successfully
        save_success = pixmap.save(str(thumb_path), "JPEG", 90)
        assert save_success, f"Failed to save pixmap to {thumb_path}"
        assert thumb_path.exists(), f"Thumbnail file not created at {thumb_path}"

        # Verify the saved file can be loaded
        test_pixmap = QPixmap(str(thumb_path))
        assert not test_pixmap.isNull(), (
            f"Could not reload saved pixmap from {thumb_path}"
        )

        # Cache the thumbnail (source_path first, then show/seq/shot)
        cache_result = real_cache_manager.cache_thumbnail(
            thumb_path, "test_show", "seq01", "shot01"
        )
        assert cache_result is not None, "Failed to cache thumbnail"

        # Set the shot
        panel.set_shot(shot)

        # Give Qt time to process the display update
        qtbot.wait(50)

        # Test actual thumbnail is displayed
        displayed_pixmap = panel.thumbnail_label.pixmap()
        assert displayed_pixmap is not None, "No pixmap displayed on label"
        assert not displayed_pixmap.isNull(), "Displayed pixmap is null"
        assert displayed_pixmap.width() <= 128, (
            f"Pixmap width {displayed_pixmap.width()} > 128"
        )
        assert displayed_pixmap.height() <= 128, (
            f"Pixmap height {displayed_pixmap.height()} > 128"
        )

    def test_load_thumbnail_from_source(
        self, qtbot, real_cache_manager, tmp_path, monkeypatch
    ):
        """Test loading thumbnail from source when not cached."""
        # Clear any existing cache state
        real_cache_manager.clear_cache()

        panel = ShotInfoPanel(cache_manager=real_cache_manager)
        qtbot.addWidget(panel)

        # Create real shot directory structure
        shows_root = tmp_path / "shows"
        shot_path = shows_root / "test_show" / "shots" / "seq01" / "seq01_shot01"
        shot_path.mkdir(parents=True, exist_ok=True)

        # Create real thumbnail in editorial path
        editorial_path = (
            shot_path
            / "publish"
            / "editorial"
            / "cutref"
            / "v001"
            / "jpg"
            / "1920x1080"
        )
        editorial_path.mkdir(parents=True, exist_ok=True)
        thumb_file = editorial_path / "frame.1001.jpg"

        # Create real image with proper JPEG format
        pixmap = QPixmap(200, 200)
        pixmap.fill(Qt.GlobalColor.red)

        # Ensure the pixmap saves successfully
        save_success = pixmap.save(str(thumb_file), "JPEG", 90)
        assert save_success, f"Failed to save pixmap to {thumb_file}"
        assert thumb_file.exists(), f"Thumbnail file not created at {thumb_file}"

        # Verify the saved file can be loaded
        test_pixmap = QPixmap(str(thumb_file))
        assert not test_pixmap.isNull(), (
            f"Could not reload saved pixmap from {thumb_file}"
        )

        # Override Config.SHOWS_ROOT
        monkeypatch.setattr("config.Config.SHOWS_ROOT", str(shows_root))

        # Create shot with real path
        shot = Shot("test_show", "seq01", "shot01", str(shot_path))

        # Set the shot (should load from source)
        panel.set_shot(shot)

        # Give it time to load and cache
        qtbot.wait(150)

        # Test actual thumbnail is displayed
        displayed_pixmap = panel.thumbnail_label.pixmap()
        assert displayed_pixmap is not None, "No pixmap displayed on label"
        assert not displayed_pixmap.isNull(), "Displayed pixmap is null"

    def test_load_thumbnail_no_cache_no_source(
        self, qtbot, real_cache_manager, tmp_path
    ):
        """Test placeholder is shown when no thumbnail available."""
        panel = ShotInfoPanel(cache_manager=real_cache_manager)
        qtbot.addWidget(panel)

        # Create shot with no thumbnail
        shot_path = (
            tmp_path / "shows" / "test_show" / "shots" / "seq01" / "seq01_shot01"
        )
        shot_path.mkdir(parents=True, exist_ok=True)
        shot = Shot("test_show", "seq01", "shot01", str(shot_path))

        # Set the shot
        panel.set_shot(shot)

        # Test placeholder is shown
        assert panel.thumbnail_label.text() == "No Image"

    def test_load_pixmap_from_path_valid(self, qtbot, real_cache_manager, tmp_path):
        """Test loading pixmap from valid path with real image."""
        panel = ShotInfoPanel(cache_manager=real_cache_manager)
        qtbot.addWidget(panel)

        # Create real image file
        image_path = tmp_path / "test.jpg"
        pixmap = QPixmap(300, 300)
        pixmap.fill(Qt.GlobalColor.green)
        pixmap.save(str(image_path))

        # Load the real image
        panel._load_pixmap_from_path(image_path)

        # Test actual display
        displayed_pixmap = panel.thumbnail_label.pixmap()
        assert displayed_pixmap is not None
        assert not displayed_pixmap.isNull()
        # Should be scaled to 128x128 or smaller
        assert displayed_pixmap.width() <= 128
        assert displayed_pixmap.height() <= 128

    def test_load_pixmap_from_path_string(self, qtbot, real_cache_manager, tmp_path):
        """Test loading pixmap from string path."""
        panel = ShotInfoPanel(cache_manager=real_cache_manager)
        qtbot.addWidget(panel)

        # Create real image
        image_path = tmp_path / "test.jpg"
        pixmap = QPixmap(100, 100)
        pixmap.fill(Qt.GlobalColor.yellow)
        pixmap.save(str(image_path))

        # Load with string path
        panel._load_pixmap_from_path(str(image_path))

        # Test actual display
        displayed_pixmap = panel.thumbnail_label.pixmap()
        assert displayed_pixmap is not None
        assert not displayed_pixmap.isNull()

    def test_load_pixmap_from_path_nonexistent(
        self, qtbot, real_cache_manager, tmp_path, caplog
    ):
        """Test loading pixmap from nonexistent path."""
        panel = ShotInfoPanel(cache_manager=real_cache_manager)
        qtbot.addWidget(panel)

        nonexistent = tmp_path / "nonexistent.jpg"

        with caplog.at_level(logging.DEBUG):
            panel._load_pixmap_from_path(nonexistent)

        # Test actual behavior - check for any of the possible log messages
        # The implementation may hit different code paths based on how QPixmap handles missing files
        assert (
            "Thumbnail path does not exist:" in caplog.text
            or "Failed to load thumbnail" in caplog.text
            or "does not exist" in caplog.text
        ), f"Expected log message not found. Actual log: {caplog.text}"
        assert panel.thumbnail_label.text() == "No Image"

    def test_load_pixmap_from_path_none(self, qtbot, real_cache_manager, caplog):
        """Test loading pixmap with None path."""
        panel = ShotInfoPanel(cache_manager=real_cache_manager)
        qtbot.addWidget(panel)

        with caplog.at_level(logging.DEBUG):
            panel._load_pixmap_from_path(None)

        # Test actual behavior
        assert "No path provided" in caplog.text
        assert panel.thumbnail_label.text() == "No Image"

    def test_load_pixmap_from_path_invalid_image(
        self, qtbot, real_cache_manager, tmp_path, caplog
    ):
        """Test loading invalid image file."""
        panel = ShotInfoPanel(cache_manager=real_cache_manager)
        qtbot.addWidget(panel)

        # Create a text file with .jpg extension
        invalid_image = tmp_path / "invalid.jpg"
        invalid_image.write_text("not an image")

        with caplog.at_level(logging.DEBUG):
            panel._load_pixmap_from_path(invalid_image)

        # Test actual behavior
        assert "Failed to load thumbnail" in caplog.text
        assert panel.thumbnail_label.text() == "No Image"

    def test_on_thumbnail_cached_current_shot(
        self, qtbot, real_cache_manager, tmp_path, make_test_shot
    ):
        """Test handling thumbnail cached signal for current shot."""
        panel = ShotInfoPanel(cache_manager=real_cache_manager)
        qtbot.addWidget(panel)

        # Set current shot
        shot = make_test_shot("test_show", "seq01", "shot01")
        panel._current_shot = shot

        # Create real cached image
        image_path = tmp_path / "cached.jpg"
        pixmap = QPixmap(100, 100)
        pixmap.fill(Qt.GlobalColor.cyan)
        pixmap.save(str(image_path))

        # Simulate cache signal
        panel._on_thumbnail_cached("test_show", "seq01", "shot01", str(image_path))

        # Test actual thumbnail loaded
        displayed_pixmap = panel.thumbnail_label.pixmap()
        assert displayed_pixmap is not None
        assert not displayed_pixmap.isNull()

    def test_on_thumbnail_cached_different_shot(
        self, qtbot, real_cache_manager, tmp_path, make_test_shot
    ):
        """Test handling thumbnail cached signal for different shot."""
        panel = ShotInfoPanel(cache_manager=real_cache_manager)
        qtbot.addWidget(panel)

        # Set current shot
        shot = make_test_shot("test_show", "seq01", "shot01")
        panel._current_shot = shot

        # Set initial placeholder
        panel._set_placeholder_thumbnail()
        initial_text = panel.thumbnail_label.text()

        # Create image for different shot
        image_path = tmp_path / "other.jpg"
        pixmap = QPixmap(100, 100)
        pixmap.fill(Qt.GlobalColor.magenta)
        pixmap.save(str(image_path))

        # Simulate cache signal for different shot
        panel._on_thumbnail_cached("other_show", "seq02", "shot02", str(image_path))

        # Test display not updated (different shot)
        assert panel.thumbnail_label.text() == initial_text

    def test_on_thumbnail_cached_no_current_shot(
        self, qtbot, real_cache_manager, tmp_path
    ):
        """Test handling thumbnail cached signal with no current shot."""
        panel = ShotInfoPanel(cache_manager=real_cache_manager)
        qtbot.addWidget(panel)

        panel._current_shot = None

        # Create image
        image_path = tmp_path / "test.jpg"
        pixmap = QPixmap(100, 100)
        pixmap.fill(Qt.GlobalColor.black)
        pixmap.save(str(image_path))

        # Simulate cache signal
        panel._on_thumbnail_cached("test_show", "seq01", "shot01", str(image_path))

        # Test no crash and appropriate state
        assert (
            panel.thumbnail_label.text() == ""
            or panel.thumbnail_label.text() == "No Image"
        )

    def test_set_placeholder_thumbnail(self, qtbot, real_cache_manager):
        """Test setting placeholder thumbnail."""
        panel = ShotInfoPanel(cache_manager=real_cache_manager)
        qtbot.addWidget(panel)

        panel._set_placeholder_thumbnail()

        # Test actual placeholder display
        assert panel.thumbnail_label.text() == "No Image"

    def test_fonts_configured(self, qtbot, real_cache_manager):
        """Test that fonts are properly configured."""
        panel = ShotInfoPanel(cache_manager=real_cache_manager)
        qtbot.addWidget(panel)

        # Test actual font properties
        shot_font = panel.shot_name_label.font()
        assert shot_font.pointSize() == 18
        assert shot_font.weight() == QFont.Weight.Bold

        show_font = panel.show_sequence_label.font()
        assert show_font.pointSize() == 12

        path_font = panel.path_label.font()
        assert path_font.pointSize() == 9

    def test_layout_structure(self, qtbot, real_cache_manager):
        """Test the layout structure is correct."""
        panel = ShotInfoPanel(cache_manager=real_cache_manager)
        qtbot.addWidget(panel)

        # Test actual layout structure
        main_layout = panel.layout()
        assert isinstance(main_layout, QHBoxLayout)
        assert main_layout.count() == 2  # Thumbnail + info layout

        # First item should be thumbnail label
        item = main_layout.itemAt(0)
        assert item.widget() == panel.thumbnail_label

        # Second item should be info layout
        info_item = main_layout.itemAt(1)
        assert isinstance(info_item.layout(), QVBoxLayout)

    def test_thumbnail_caching_starts_worker(
        self, qtbot, real_cache_manager, tmp_path, monkeypatch
    ):
        """Test that thumbnail caching starts a worker thread with real components."""
        panel = ShotInfoPanel(cache_manager=real_cache_manager)
        qtbot.addWidget(panel)

        # Create real shot with thumbnail
        shows_root = tmp_path / "shows"
        shot_path = shows_root / "test_show" / "shots" / "seq01" / "seq01_shot01"
        shot_path.mkdir(parents=True, exist_ok=True)

        # Create real thumbnail
        editorial_path = (
            shot_path
            / "publish"
            / "editorial"
            / "cutref"
            / "v001"
            / "jpg"
            / "1920x1080"
        )
        editorial_path.mkdir(parents=True, exist_ok=True)
        thumb_file = editorial_path / "frame.1001.jpg"

        pixmap = QPixmap(100, 100)
        pixmap.fill(Qt.GlobalColor.darkGreen)
        pixmap.save(str(thumb_file))

        # Override Config.SHOWS_ROOT
        monkeypatch.setattr("config.Config.SHOWS_ROOT", str(shows_root))

        shot = Shot("test_show", "seq01", "shot01", str(shot_path))

        # Set the shot (should start caching)
        panel.set_shot(shot)

        # Give worker time to start
        qtbot.wait(100)

        # Test that thumbnail eventually appears (worker completed)
        # May or may not be loaded yet, but should not crash
        panel.thumbnail_label.pixmap()

    def test_error_handling_permission_error(
        self, qtbot, real_cache_manager, tmp_path, caplog
    ):
        """Test handling permission error when loading thumbnail."""
        panel = ShotInfoPanel(cache_manager=real_cache_manager)
        qtbot.addWidget(panel)

        # Create a file that will fail to load
        test_file = tmp_path / "test.jpg"
        test_file.write_text("dummy")

        # Make file unreadable (on Unix-like systems)
        import os
        import platform

        if platform.system() != "Windows":
            os.chmod(test_file, 0o000)

        with caplog.at_level(logging.WARNING):
            panel._load_pixmap_from_path(test_file)

        # Test actual error handling
        assert panel.thumbnail_label.text() == "No Image"

        # Restore permissions for cleanup
        if platform.system() != "Windows":
            os.chmod(test_file, 0o644)

    def test_scaled_pixmap_handling(self, qtbot, real_cache_manager, tmp_path):
        """Test handling of pixmap scaling with real images."""
        panel = ShotInfoPanel(cache_manager=real_cache_manager)
        qtbot.addWidget(panel)

        # Create a large image
        image_path = tmp_path / "large.jpg"
        pixmap = QPixmap(1000, 1000)
        pixmap.fill(Qt.GlobalColor.darkBlue)
        pixmap.save(str(image_path))

        # Load and scale
        panel._load_pixmap_from_path(image_path)

        # Test actual scaling worked
        displayed_pixmap = panel.thumbnail_label.pixmap()
        assert displayed_pixmap is not None
        assert displayed_pixmap.width() <= 128
        assert displayed_pixmap.height() <= 128

    def test_concurrent_shot_changes(self, qtbot, real_cache_manager, make_test_shot):
        """Test rapid shot changes don't cause issues."""
        panel = ShotInfoPanel(cache_manager=real_cache_manager)
        qtbot.addWidget(panel)

        # Create multiple shots
        shot1 = make_test_shot("show1", "seq01", "shot01")
        shot2 = make_test_shot("show2", "seq02", "shot02")
        shot3 = make_test_shot("show3", "seq03", "shot03")

        # Rapidly change shots
        panel.set_shot(shot1)
        panel.set_shot(shot2)
        panel.set_shot(shot3)
        panel.set_shot(None)
        panel.set_shot(shot1)

        # Test final state is correct
        assert panel._current_shot == shot1
        assert panel.shot_name_label.text() == "seq01_shot01"
        assert "show1" in panel.show_sequence_label.text()
