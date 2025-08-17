"""Tests for EXR thumbnail fallback functionality.

This test module verifies the intelligent EXR fallback system that:
1. Prefers lightweight formats (JPG/PNG) when available
2. Falls back to EXR files when no lightweight formats exist
3. Triggers PIL resizing for large EXR files
4. Integrates properly with cache manager
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from PySide6.QtGui import QImage, QPixmap

from cache_manager import CacheManager
from config import Config
from shot_item_model import ShotItemModel
from shot_model import Shot
from utils import FileUtils, PathUtils


class TestEXRFallbackPriority:
    """Test that lightweight formats are preferred over EXR."""

    def test_get_first_image_prefers_jpg_over_exr(self, tmp_path):
        """Test that JPG is chosen when both JPG and EXR exist."""
        # Create test directory with both formats
        test_dir = tmp_path / "thumbnails"
        test_dir.mkdir()
        
        jpg_file = test_dir / "thumb.jpg"
        exr_file = test_dir / "thumb.exr"
        jpg_file.touch()
        exr_file.touch()
        
        # Should return JPG, not EXR
        result = FileUtils.get_first_image_file(test_dir)
        assert result == jpg_file
        assert result.suffix == ".jpg"

    def test_get_first_image_prefers_png_over_exr(self, tmp_path):
        """Test that PNG is chosen when both PNG and EXR exist."""
        test_dir = tmp_path / "thumbnails"
        test_dir.mkdir()
        
        png_file = test_dir / "thumb.png"
        exr_file = test_dir / "thumb.exr"
        png_file.touch()
        exr_file.touch()
        
        result = FileUtils.get_first_image_file(test_dir)
        assert result == png_file
        assert result.suffix == ".png"

    def test_get_first_image_falls_back_to_exr(self, tmp_path):
        """Test that EXR is used when no lightweight formats exist."""
        test_dir = tmp_path / "thumbnails"
        test_dir.mkdir()
        
        exr_file = test_dir / "thumb.exr"
        exr_file.touch()
        
        # With fallback enabled (default)
        result = FileUtils.get_first_image_file(test_dir, allow_fallback=True)
        assert result == exr_file
        assert result.suffix == ".exr"

    def test_get_first_image_no_fallback(self, tmp_path):
        """Test that EXR is not used when fallback is disabled."""
        test_dir = tmp_path / "thumbnails"
        test_dir.mkdir()
        
        exr_file = test_dir / "thumb.exr"
        exr_file.touch()
        
        # With fallback disabled
        result = FileUtils.get_first_image_file(test_dir, allow_fallback=False)
        assert result is None

    def test_find_any_publish_thumbnail_priority(self, tmp_path):
        """Test that find_any_publish_thumbnail prefers JPG over EXR."""
        # Create publish structure
        shows_root = tmp_path / "shows"
        publish_path = (
            shows_root / "testshow" / "shots" / "seq01" / "seq01_shot01" / "publish"
        )
        publish_path.mkdir(parents=True)
        
        # Create both JPG and EXR with "1001" in name
        jpg_file = publish_path / "thumb.1001.jpg"
        exr_file = publish_path / "thumb.1001.exr"
        jpg_file.touch()
        exr_file.touch()
        
        with patch.object(Config, "SHOWS_ROOT", str(shows_root)):
            result = PathUtils.find_any_publish_thumbnail(
                str(shows_root), "testshow", "seq01", "shot01"
            )
        
        assert result == jpg_file
        assert result.suffix == ".jpg"

    def test_find_turnover_plate_returns_exr_for_resizing(self, tmp_path):
        """Test that find_turnover_plate_thumbnail returns EXR for PIL resizing."""
        shows_root = tmp_path / "shows"
        plate_path = (
            shows_root
            / "testshow"
            / "shots"
            / "seq01"
            / "seq01_shot01"
            / "publish"
            / "turnover"
            / "plate"
            / "FG01"
            / "v001"
            / "exr"
            / "4312x2304"
        )
        plate_path.mkdir(parents=True)
        
        # Create large EXR file (simulate with size attribute)
        exr_file = plate_path / "plate.1001.exr"
        exr_file.write_bytes(b"x" * (15 * 1024 * 1024))  # 15MB file
        
        with patch.object(Config, "SHOWS_ROOT", str(shows_root)):
            result = PathUtils.find_turnover_plate_thumbnail(
                str(shows_root), "testshow", "seq01", "shot01"
            )
        
        assert result == exr_file
        assert result.stat().st_size > 10 * 1024 * 1024  # Larger than 10MB


class TestCacheManagerEXRHandling:
    """Test cache manager's PIL-based EXR resizing."""

    @pytest.fixture
    def cache_manager(self, tmp_path):
        """Create a cache manager with temp directory."""
        return CacheManager(cache_dir=tmp_path / "cache")

    def test_cache_manager_detects_heavy_format(self, cache_manager, tmp_path):
        """Test that cache manager identifies EXR as needing PIL."""
        # Create real EXR file
        exr_path = tmp_path / "test.exr"
        exr_path.write_bytes(b"x" * (5 * 1024 * 1024))  # 5MB
        
        # Mock PIL operations (imported inside the method)
        import PIL.Image
        with patch.object(PIL, "Image") as mock_pil_module:
            mock_image = MagicMock()
            mock_pil_module.open.return_value = mock_image
            mock_image.mode = "RGB"
            mock_image.thumbnail = MagicMock()
            
            # Call cache_thumbnail which handles EXR files
            result = cache_manager.cache_thumbnail(
                exr_path,
                show="test",
                sequence="seq01",
                shot="0010"
            )
            
            # Verify PIL was used for EXR
            mock_pil_module.open.assert_called_once()
            assert result is not None  # Returns path to cached JPEG

    def test_cache_manager_resizes_large_exr(self, cache_manager, tmp_path):
        """Test that large EXR files trigger PIL resizing."""
        # Create a large test file
        exr_file = tmp_path / "large.exr"
        exr_file.write_bytes(b"x" * (20 * 1024 * 1024))  # 20MB
        
        with patch("PIL.Image") as mock_pil_module:
            mock_image = MagicMock()
            mock_pil_module.open.return_value = mock_image
            mock_image.mode = "RGB"
            
            # Mock the thumbnail method
            mock_image.thumbnail = MagicMock()
            
            result = cache_manager.cache_thumbnail(
                exr_file,
                show="test",
                sequence="seq01",
                shot="0010"
            )
            
            # Verify thumbnail was called for resizing
            mock_image.thumbnail.assert_called_once()
            assert result is not None  # Returns path to cached JPEG

    def test_cache_manager_handles_jpg_directly(self, cache_manager, tmp_path):
        """Test that JPG files are loaded directly without PIL."""
        jpg_file = tmp_path / "small.jpg"
        jpg_file.write_bytes(b"x" * (1 * 1024 * 1024))  # 1MB
        
        # Mock QImage for Qt-based loading
        with patch("cache_manager.QImage") as mock_qimage_class:
            mock_image = MagicMock()
            mock_image.isNull.return_value = False
            mock_image.width.return_value = 1920
            mock_image.height.return_value = 1080
            mock_image.scaled.return_value = mock_image
            mock_image.save.return_value = True
            mock_qimage_class.return_value = mock_image
            
            # PIL should NOT be called for JPG
            import PIL.Image
            with patch.object(PIL, "Image") as mock_pil:
                result = cache_manager.cache_thumbnail(
                    jpg_file,
                    show="test",
                    sequence="seq01",
                    shot="0010"
                )
                
                # PIL not used for small JPG
                mock_pil.open.assert_not_called()
                assert result is not None


class TestShotItemModelIntegration:
    """Test shot_item_model's integration with cache manager for EXR handling."""

    @pytest.fixture
    def shot(self):
        """Create a test shot."""
        return Shot(
            show="testshow",
            sequence="seq01",
            shot="0010",
            workspace_path="/shows/testshow/seq01/0010"
        )

    def test_model_uses_cache_manager_for_exr(self, shot, tmp_path):
        """Test that model uses cache manager to handle EXR files."""
        # Create cache manager
        cache_manager = CacheManager(cache_dir=tmp_path / "cache")
        
        # Create model with cache manager
        model = ShotItemModel(cache_manager=cache_manager)
        model.set_shots([shot])
        
        # Mock shot's get_thumbnail_path to return EXR
        exr_path = tmp_path / "thumb.exr"
        exr_path.write_bytes(b"x" * (5 * 1024 * 1024))  # 5MB EXR
        
        # Create a cached JPEG path
        cached_jpeg = tmp_path / "cache" / "testshow" / "seq01" / "0010_thumb.jpg"
        cached_jpeg.parent.mkdir(parents=True, exist_ok=True)
        cached_jpeg.touch()
        
        with patch.object(shot, "get_thumbnail_path", return_value=exr_path):
            # Mock cache_thumbnail to return the cached path
            with patch.object(cache_manager, "cache_thumbnail", return_value=cached_jpeg):
                # Mock QPixmap loading
                with patch("shot_item_model.QPixmap") as mock_pixmap_class:
                    mock_pixmap = MagicMock()
                    mock_pixmap.isNull.return_value = False
                    mock_pixmap.scaled.return_value = mock_pixmap
                    mock_pixmap_class.return_value = mock_pixmap
                    
                    # Trigger thumbnail loading
                    model._load_thumbnail_async(0, shot)
                    
                    # Verify cache_thumbnail was called with correct params
                    cache_manager.cache_thumbnail.assert_called_once_with(
                        exr_path, shot.show, shot.sequence, shot.shot, wait=True
                    )
                    
                    # Verify thumbnail was cached in model
                    assert shot.full_name in model._thumbnail_cache
                    assert model._loading_states[shot.full_name] == "loaded"

    def test_model_without_cache_skips_exr(self, shot, tmp_path):
        """Test that model without cache manager doesn't load EXR."""
        # Create model WITHOUT cache manager - test fallback behavior
        model = ShotItemModel()
        # Ensure cache_manager is None
        model._cache_manager = None
        model.set_shots([shot])
        
        # Mock shot's get_thumbnail_path to return EXR
        exr_path = tmp_path / "thumb.exr"
        exr_path.touch()
        
        with patch.object(shot, "get_thumbnail_path", return_value=exr_path):
            # Trigger thumbnail loading
            model._load_thumbnail_async(0, shot)
            
            # Verify thumbnail was NOT loaded (EXR not in THUMBNAIL_EXTENSIONS)
            assert shot.full_name not in model._thumbnail_cache
            assert model._loading_states[shot.full_name] == "failed"

    def test_model_loads_jpg_without_cache(self, shot, tmp_path):
        """Test that model can load JPG directly without cache manager."""
        # Create model WITHOUT cache manager
        model = ShotItemModel()
        # Ensure cache_manager is None
        model._cache_manager = None
        model.set_shots([shot])
        
        # Mock shot's get_thumbnail_path to return JPG
        jpg_path = tmp_path / "thumb.jpg"
        jpg_path.touch()
        
        with patch.object(shot, "get_thumbnail_path", return_value=jpg_path):
            with patch("shot_item_model.QPixmap") as mock_pixmap_class:
                mock_pixmap = MagicMock()
                mock_pixmap.isNull.return_value = False
                mock_pixmap.scaled.return_value = mock_pixmap
                mock_pixmap_class.return_value = mock_pixmap
                
                # Trigger thumbnail loading
                model._load_thumbnail_async(0, shot)
                
                # Verify thumbnail was loaded directly
                assert shot.full_name in model._thumbnail_cache
                assert model._loading_states[shot.full_name] == "loaded"


class TestEndToEndWorkflow:
    """Test the complete EXR fallback workflow from discovery to display."""

    def test_complete_workflow_with_exr_fallback(self, tmp_path):
        """Test complete workflow: discover EXR → resize with PIL → display."""
        # Setup directory structure
        shows_root = tmp_path / "shows"
        shot_dir = shows_root / "testshow" / "shots" / "seq01" / "seq01_0010"
        publish_dir = shot_dir / "publish" / "editorial"
        publish_dir.mkdir(parents=True)
        
        # Create only EXR file (no JPG/PNG)
        exr_file = publish_dir / "thumb.1001.exr"
        exr_file.write_bytes(b"x" * (5 * 1024 * 1024))  # 5MB EXR
        
        # Create shot
        shot = Shot(
            show="testshow",
            sequence="seq01", 
            shot="0010",
            workspace_path=str(shot_dir)
        )
        
        # Setup config
        with patch.object(Config, "SHOWS_ROOT", str(shows_root)):
            # 1. Discovery: Shot should find the EXR
            thumb_path = shot.get_thumbnail_path()
            assert thumb_path is not None
            assert thumb_path.suffix == ".exr"
            
            # 2. Cache Manager: Should resize with PIL
            cache_manager = CacheManager(cache_dir=tmp_path / "cache")
            
            import PIL.Image
            with patch.object(PIL, "Image") as mock_pil:
                mock_image = MagicMock()
                mock_pil.open.return_value = mock_image
                mock_image.mode = "RGB"
                mock_image.thumbnail = MagicMock()
                
                cached_path = cache_manager.cache_thumbnail(
                    thumb_path,
                    shot.show,
                    shot.sequence,
                    shot.shot
                )
                
                # Verify PIL was used
                mock_pil.open.assert_called_once()
                mock_image.thumbnail.assert_called_once()
                assert cached_path is not None
            
            # 3. Model: Should use cached thumbnail
            model = ShotItemModel(cache_manager=cache_manager)
            model.set_shots([shot])
            
            # Create mock cached JPEG
            cached_jpeg = tmp_path / "cache" / "testshow" / "seq01" / "0010_thumb.jpg"
            cached_jpeg.parent.mkdir(parents=True, exist_ok=True)
            cached_jpeg.touch()
            
            with patch.object(cache_manager, "cache_thumbnail", return_value=cached_jpeg):
                with patch("shot_item_model.QPixmap") as mock_pixmap_class:
                    mock_pixmap = MagicMock()
                    mock_pixmap.isNull.return_value = False
                    mock_pixmap.scaled.return_value = mock_pixmap
                    mock_pixmap_class.return_value = mock_pixmap
                    
                    model._load_thumbnail_async(0, shot)
                    
                    # Verify thumbnail is ready for display
                    assert shot.full_name in model._thumbnail_cache
                    assert model._loading_states[shot.full_name] == "loaded"

    def test_workflow_prefers_jpg_when_available(self, tmp_path):
        """Test that workflow uses JPG when both JPG and EXR exist."""
        # Setup directory structure matching Config.THUMBNAIL_SEGMENTS
        shows_root = tmp_path / "shows"
        shot_dir = shows_root / "testshow" / "shots" / "seq01" / "seq01_0010"
        
        # Build editorial path using Config.THUMBNAIL_SEGMENTS
        editorial_dir = shot_dir
        for segment in Config.THUMBNAIL_SEGMENTS:
            editorial_dir = editorial_dir / segment
        editorial_dir.mkdir(parents=True)
        
        # Create both JPG and EXR
        jpg_file = editorial_dir / "thumb.jpg"
        exr_file = editorial_dir / "thumb.exr"
        jpg_file.touch()
        exr_file.write_bytes(b"x" * (10 * 1024 * 1024))  # Large EXR
        
        # Create shot
        shot = Shot(
            show="testshow",
            sequence="seq01",
            shot="0010",
            workspace_path=str(shot_dir)
        )
        
        with patch.object(Config, "SHOWS_ROOT", str(shows_root)):
            # Shot should find JPG, not EXR
            thumb_path = shot.get_thumbnail_path()
            assert thumb_path is not None, "Should find thumbnail"
            assert thumb_path == jpg_file
            assert thumb_path.suffix == ".jpg"
            
            # Cache manager should load JPG directly
            cache_manager = CacheManager(cache_dir=tmp_path / "cache")
            
            # Mock QImage for Qt-based loading of JPG
            with patch("cache_manager.QImage") as mock_qimage_class:
                mock_image = MagicMock()
                mock_image.isNull.return_value = False
                mock_image.width.return_value = 1920
                mock_image.height.return_value = 1080
                mock_image.scaled.return_value = mock_image
                mock_image.save.return_value = True
                mock_qimage_class.return_value = mock_image
                
                # PIL should NOT be called for JPG
                import PIL.Image
            with patch.object(PIL, "Image") as mock_pil:
                    cached_path = cache_manager.cache_thumbnail(
                        thumb_path,
                        shot.show,
                        shot.sequence,
                        shot.shot
                    )
                    
                    # PIL not used for JPG
                    mock_pil.open.assert_not_called()
                    assert cached_path is not None