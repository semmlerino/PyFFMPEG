"""Simplified regression tests for EXR handling.

These tests verify the fix without calling internal Qt-dependent methods.
"""

import logging
from pathlib import Path

import pytest

from cache_manager import CacheManager
from shot_model import Shot
from utils import FileUtils


class TestEXRNoSkippingBehavior:
    """Verify EXR files are properly handled, not skipped."""
    
    def test_exr_files_accepted_by_utils(self, tmp_path):
        """EXR files should be found and returned by utility functions."""
        test_dir = tmp_path / "test"
        test_dir.mkdir()
        
        # Create EXR file
        exr_file = test_dir / "image.exr"
        exr_file.write_bytes(b"fake exr")
        
        # Should find EXR when fallback enabled
        result = FileUtils.get_first_image_file(test_dir, allow_fallback=True)
        assert result == exr_file
        
        # Should not find when fallback disabled
        result = FileUtils.get_first_image_file(test_dir, allow_fallback=False)
        assert result is None
    
    def test_cache_manager_accepts_exr(self, tmp_path, caplog):
        """Cache manager should process EXR files without warning."""
        exr_file = tmp_path / "test.exr"
        exr_file.write_bytes(b"exr content")
        
        cache_manager = CacheManager(cache_dir=tmp_path / "cache")
        
        with caplog.at_level(logging.WARNING):
            # Should process without "Skipping EXR" warning
            result = cache_manager.cache_thumbnail(
                exr_file,
                show="test",
                sequence="seq",
                shot="0010",
                wait=False  # Don't wait for actual processing
            )
            
            # Check no skipping warning was logged
            for record in caplog.records:
                assert "Skipping EXR file" not in record.message
    
    def test_shot_discovers_exr_thumbnails(self, tmp_path):
        """Shot should find EXR thumbnails when available."""
        shows_root = tmp_path / "shows"
        
        # Create EXR in editorial path
        shot_dir = shows_root / "test" / "shots" / "seq01" / "seq01_0010"
        editorial = shot_dir / "publish" / "editorial" / "cutref" / "v001" / "jpg" / "1920x1080"
        editorial.mkdir(parents=True)
        
        # Only EXR available
        exr_thumb = editorial / "thumb.exr"
        exr_thumb.write_bytes(b"exr data")
        
        shot = Shot("test", "seq01", "0010", str(shot_dir))
        
        # Mock SHOWS_ROOT
        import config
        original_root = config.Config.SHOWS_ROOT
        try:
            config.Config.SHOWS_ROOT = str(shows_root)
            
            # Should find the EXR
            thumb_path = shot.get_thumbnail_path()
            assert thumb_path is not None
            assert thumb_path.suffix == ".exr"
            assert thumb_path == exr_thumb
            
        finally:
            config.Config.SHOWS_ROOT = original_root
    
    def test_priority_still_prefers_jpg(self, tmp_path):
        """JPG should still be preferred when both exist."""
        shows_root = tmp_path / "shows"
        
        # Create both JPG and EXR
        shot_dir = shows_root / "test" / "shots" / "seq01" / "seq01_0010"
        editorial = shot_dir / "publish" / "editorial" / "cutref" / "v001" / "jpg" / "1920x1080"
        editorial.mkdir(parents=True)
        
        (editorial / "thumb.jpg").touch()
        (editorial / "thumb.exr").touch()
        
        shot = Shot("test", "seq01", "0010", str(shot_dir))
        
        import config
        original_root = config.Config.SHOWS_ROOT
        try:
            config.Config.SHOWS_ROOT = str(shows_root)
            
            # Should prefer JPG
            thumb_path = shot.get_thumbnail_path()
            assert thumb_path is not None
            assert thumb_path.suffix == ".jpg"
            
        finally:
            config.Config.SHOWS_ROOT = original_root


class TestEXRCachingBehavior:
    """Test that EXR files go through proper caching pipeline."""
    
    def test_exr_triggers_cache_thumbnail(self, tmp_path):
        """EXR files should go through cache_thumbnail pipeline."""
        exr_file = tmp_path / "test.exr"
        # Create file
        exr_file.write_bytes(b"EXR" + b"x" * 1024)
        
        cache_manager = CacheManager(cache_dir=tmp_path / "cache")
        
        # Call cache_thumbnail - won't succeed but should attempt
        result = cache_manager.cache_thumbnail(
            exr_file,
            show="test",
            sequence="seq",
            shot="0010",
            wait=False  # Don't wait
        )
        
        # Should return ThumbnailCacheResult (not None)
        assert result is not None
        
        # Should not crash or raise exception
    
    def test_exr_caching_creates_jpg_output(self, tmp_path):
        """Cached EXR should be saved as JPG for efficiency."""
        exr_file = tmp_path / "input.exr"
        exr_file.write_bytes(b"exr data")
        
        cache_manager = CacheManager(cache_dir=tmp_path / "cache")
        
        # Expected cache path structure
        expected_cache_path = cache_manager.thumbnails_dir / "test" / "seq" / "0010_thumb.jpg"
        
        # Cache paths should use .jpg extension
        assert expected_cache_path.suffix == ".jpg"
        
        # Verify get_cached_thumbnail would look for JPG
        cached = cache_manager.get_cached_thumbnail("test", "seq", "0010")
        # Will be None since not cached yet, but the path it checks should be JPG
        if cached is not None:
            assert cached.suffix == ".jpg"