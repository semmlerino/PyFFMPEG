"""Unit tests for cache_manager.py"""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from cache_manager import CacheManager, ThumbnailCacheLoader


class TestCacheManager:
    """Test CacheManager class."""

    @pytest.fixture
    def temp_cache_dir(self):
        """Create temporary cache directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def cache_manager(self, temp_cache_dir):
        """Create CacheManager with temporary directory."""
        return CacheManager(cache_dir=temp_cache_dir)

    def test_ensure_cache_dirs(self, cache_manager, temp_cache_dir):
        """Test cache directory creation."""
        assert (temp_cache_dir / "thumbnails").exists()

    def test_get_cached_thumbnail_not_exists(self, cache_manager):
        """Test getting non-existent cached thumbnail."""
        result = cache_manager.get_cached_thumbnail("show1", "seq1", "shot1")
        assert result is None

    def test_get_cached_thumbnail_exists(self, cache_manager, temp_cache_dir):
        """Test getting existing cached thumbnail."""
        # Create cached thumbnail
        cache_path = (
            temp_cache_dir / "thumbnails" / "show1" / "seq1" / "shot1_thumb.jpg"
        )
        cache_path.parent.mkdir(parents=True)
        cache_path.touch()

        result = cache_manager.get_cached_thumbnail("show1", "seq1", "shot1")
        assert result == cache_path

    @patch("cache_manager.QApplication")
    @patch("cache_manager.QThread")
    @patch("cache_manager.QImage")
    def test_cache_thumbnail_success(
        self, mock_qimage_class, mock_qthread, mock_qapp, cache_manager, temp_cache_dir
    ):
        """Test successful thumbnail caching."""
        # Mock Qt thread detection to think we're on main thread
        mock_app_instance = Mock()
        mock_current_thread = Mock()
        mock_qapp.instance.return_value = mock_app_instance
        mock_qthread.currentThread.return_value = mock_current_thread
        mock_app_instance.thread.return_value = mock_current_thread  # Same thread = main thread
        
        # Setup mock for image
        mock_image = Mock()
        mock_image.isNull.return_value = False
        mock_image.width.return_value = 800  # Valid size
        mock_image.height.return_value = 600  # Valid size
        mock_scaled = Mock()
        mock_scaled.isNull.return_value = False  # Scaling succeeded
        
        # Make save actually create the temp file so replace() works
        def mock_save(path, format, quality):
            Path(path).touch()  # Create the file
            return True
        mock_scaled.save.side_effect = mock_save
        
        mock_image.scaled.return_value = mock_scaled
        mock_qimage_class.return_value = mock_image

        # Create source file
        source = temp_cache_dir / "source.jpg"
        source.touch()

        result = cache_manager.cache_thumbnail(source, "show1", "seq1", "shot1")
        expected_path = (
            temp_cache_dir / "thumbnails" / "show1" / "seq1" / "shot1_thumb.jpg"
        )

        assert result == expected_path
        # The implementation saves to a temp file first, so we check it was called with ANY path
        assert mock_scaled.save.called
        # Check it was called with JPEG format and quality 85 (not EXR)
        args, kwargs = mock_scaled.save.call_args
        assert args[1] == "JPEG"
        assert args[2] == 85

    @patch("cache_manager.QApplication")
    @patch("cache_manager.QThread")
    @patch("cache_manager.QImage")
    def test_cache_thumbnail_invalid_image(
        self, mock_qimage_class, mock_qthread, mock_qapp, cache_manager, temp_cache_dir
    ):
        """Test caching invalid thumbnail."""
        # Mock Qt thread detection to think we're on main thread
        mock_app_instance = Mock()
        mock_current_thread = Mock()
        mock_qapp.instance.return_value = mock_app_instance
        mock_qthread.currentThread.return_value = mock_current_thread
        mock_app_instance.thread.return_value = mock_current_thread  # Same thread = main thread
        
        # Setup mock for invalid image
        mock_image = Mock()
        mock_image.isNull.return_value = True
        mock_qimage_class.return_value = mock_image

        source = temp_cache_dir / "invalid.jpg"
        source.touch()

        result = cache_manager.cache_thumbnail(source, "show1", "seq1", "shot1")
        assert result is None

    def test_cache_thumbnail_source_not_exists(self, cache_manager, temp_cache_dir):
        """Test caching non-existent source."""
        source = temp_cache_dir / "nonexistent.jpg"
        result = cache_manager.cache_thumbnail(source, "show1", "seq1", "shot1")
        assert result is None

    def test_get_cached_shots_no_file(self, cache_manager):
        """Test getting shots when cache file doesn't exist."""
        result = cache_manager.get_cached_shots()
        assert result is None

    def test_get_cached_shots_valid(self, cache_manager, temp_cache_dir):
        """Test getting valid cached shots."""
        shots_data = {
            "timestamp": datetime.now().isoformat(),
            "shots": [
                {
                    "show": "show1",
                    "sequence": "seq1",
                    "shot": "0010",
                    "workspace_path": "/path/1",
                },
                {
                    "show": "show1",
                    "sequence": "seq1",
                    "shot": "0020",
                    "workspace_path": "/path/2",
                },
            ],
        }

        with open(temp_cache_dir / "shots.json", "w") as f:
            json.dump(shots_data, f)

        result = cache_manager.get_cached_shots()
        assert len(result) == 2
        assert result[0]["shot"] == "0010"

    def test_get_cached_shots_expired(self, cache_manager, temp_cache_dir):
        """Test getting expired cached shots."""
        old_time = datetime.now() - timedelta(hours=1)
        shots_data = {
            "timestamp": old_time.isoformat(),
            "shots": [
                {
                    "show": "show1",
                    "sequence": "seq1",
                    "shot": "0010",
                    "workspace_path": "/path",
                }
            ],
        }

        with open(temp_cache_dir / "shots.json", "w") as f:
            json.dump(shots_data, f)

        result = cache_manager.get_cached_shots()
        assert result is None

    def test_get_cached_shots_invalid_json(self, cache_manager, temp_cache_dir):
        """Test handling invalid JSON in cache file."""
        with open(temp_cache_dir / "shots.json", "w") as f:
            f.write("invalid json")

        result = cache_manager.get_cached_shots()
        assert result is None

    def test_cache_shots(self, cache_manager, temp_cache_dir):
        """Test caching shots."""
        shots = [
            {
                "show": "show1",
                "sequence": "seq1",
                "shot": "0010",
                "workspace_path": "/path/1",
            },
            {
                "show": "show1",
                "sequence": "seq1",
                "shot": "0020",
                "workspace_path": "/path/2",
            },
        ]

        cache_manager.cache_shots(shots)

        assert (temp_cache_dir / "shots.json").exists()

        with open(temp_cache_dir / "shots.json", "r") as f:
            data = json.load(f)

        assert "timestamp" in data
        assert data["shots"] == shots

    def test_clear_cache(self, cache_manager, temp_cache_dir):
        """Test clearing cache."""
        # Create some cache files
        (temp_cache_dir / "thumbnails" / "test").mkdir(parents=True)
        (temp_cache_dir / "thumbnails" / "test" / "thumb.jpg").touch()
        (temp_cache_dir / "shots.json").touch()

        cache_manager.clear_cache()

        # Thumbnails should be gone but directory recreated
        assert (temp_cache_dir / "thumbnails").exists()
        assert not (temp_cache_dir / "thumbnails" / "test").exists()
        assert not (temp_cache_dir / "shots.json").exists()


class TestThumbnailCacheLoader:
    """Test ThumbnailCacheLoader class."""

    @pytest.fixture
    def mock_cache_manager(self):
        """Create mock cache manager."""
        return Mock(spec=CacheManager)

    def test_thumbnail_cache_loader_init(self, mock_cache_manager):
        """Test ThumbnailCacheLoader initialization."""
        source_path = Path("/source/image.jpg")
        loader = ThumbnailCacheLoader(
            mock_cache_manager, source_path, "show1", "seq1", "shot1"
        )

        assert loader.cache_manager == mock_cache_manager
        assert loader.source_path == source_path
        assert loader.show == "show1"
        assert loader.sequence == "seq1"
        assert loader.shot == "shot1"

    def test_thumbnail_cache_loader_run_success(self, mock_cache_manager):
        """Test successful thumbnail caching in background."""
        source_path = Path("/source/image.jpg")
        cache_path = Path("/cache/thumb.jpg")

        mock_cache_manager.cache_thumbnail_direct.return_value = cache_path

        loader = ThumbnailCacheLoader(
            mock_cache_manager, source_path, "show1", "seq1", "shot1"
        )

        # Track signal emissions
        emitted = []
        loader.signals.loaded.connect(lambda *args: emitted.append(args))

        loader.run()

        mock_cache_manager.cache_thumbnail_direct.assert_called_once_with(
            source_path, "show1", "seq1", "shot1"
        )
        assert len(emitted) == 1
        assert emitted[0] == ("show1", "seq1", "shot1", cache_path)

    def test_thumbnail_cache_loader_run_failure(self, mock_cache_manager):
        """Test failed thumbnail caching."""
        source_path = Path("/source/image.jpg")

        mock_cache_manager.cache_thumbnail_direct.return_value = None

        loader = ThumbnailCacheLoader(
            mock_cache_manager, source_path, "show1", "seq1", "shot1"
        )

        # Track signal emissions
        emitted = []
        loader.signals.loaded.connect(lambda *args: emitted.append(args))

        loader.run()

        mock_cache_manager.cache_thumbnail_direct.assert_called_once()
        assert len(emitted) == 0  # No signal should be emitted on failure
