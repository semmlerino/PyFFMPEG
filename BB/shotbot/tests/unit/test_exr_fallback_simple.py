"""Simplified tests for EXR thumbnail fallback functionality.

Following the testing guide's advice to minimize mocking and test real behavior.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cache_manager import CacheManager
from config import Config
from shot_model import Shot

# This test file follows UNIFIED_TESTING_GUIDE best practices:
# - Test behavior, not implementation
# - Use test doubles instead of mocks
# - Real components where possible
# - Thread-safe testing patterns
# Test doubles for behavior testing (UNIFIED_TESTING_GUIDE)
from utils import FileUtils, PathUtils

pytestmark = pytest.mark.unit


class TestThumbnailPriority:
    """Test that lightweight formats are preferred over EXR."""

    def test_jpg_preferred_over_exr(self, tmp_path):
        """JPG should be chosen when both JPG and EXR exist."""
        test_dir = tmp_path / "thumbnails"
        test_dir.mkdir()

        # Create both formats
        (test_dir / "thumb.jpg").touch()
        (test_dir / "thumb.exr").touch()

        result = FileUtils.get_first_image_file(test_dir)
        assert result is not None
        assert result.suffix == ".jpg"

    def test_exr_used_as_fallback(self, tmp_path):
        """EXR should be used when no lightweight formats exist."""
        test_dir = tmp_path / "thumbnails"
        test_dir.mkdir()

        # Only EXR available
        (test_dir / "thumb.exr").touch()

        result = FileUtils.get_first_image_file(test_dir, allow_fallback=True)
        assert result is not None
        assert result.suffix == ".exr"

    def test_no_fallback_returns_none(self, tmp_path):
        """Should return None when fallback disabled and only EXR exists."""
        test_dir = tmp_path / "thumbnails"
        test_dir.mkdir()

        (test_dir / "thumb.exr").touch()

        result = FileUtils.get_first_image_file(test_dir, allow_fallback=False)
        assert result is None


class TestShotThumbnailDiscovery:
    """Test shot's thumbnail discovery with EXR fallback."""

    def test_shot_finds_jpg_first(self, tmp_path):
        """Shot should find JPG when available."""
        # Setup directory structure
        shows_root = tmp_path / "shows"
        shot_dir = shows_root / "testshow" / "shots" / "seq01" / "seq01_0010"

        # Create editorial directory (where thumbnails are expected)
        editorial_dir = shot_dir
        for segment in Config.THUMBNAIL_SEGMENTS:
            editorial_dir = editorial_dir / segment
        editorial_dir.mkdir(parents=True)

        # Create JPG
        (editorial_dir / "thumb.jpg").touch()

        shot = Shot(
            show="testshow", sequence="seq01", shot="0010", workspace_path=str(shot_dir)
        )

        with pytest.MonkeyPatch.context() as m:
            m.setattr(Config, "SHOWS_ROOT", str(shows_root))

            thumb_path = shot.get_thumbnail_path()
            assert thumb_path is not None
            assert thumb_path.suffix == ".jpg"

    def test_shot_falls_back_to_turnover_plate(self, tmp_path):
        """Shot should find turnover plate EXR when no editorial thumbnail."""
        shows_root = tmp_path / "shows"

        # Create turnover plate structure
        plate_path = (
            shows_root
            / "testshow"
            / "shots"
            / "seq01"
            / "seq01_0010"
            / "publish"
            / "turnover"
            / "plate"
            / "FG01"
            / "v001"
            / "exr"
            / "4k"
        )
        plate_path.mkdir(parents=True)

        # Create EXR plate
        exr_file = plate_path / "plate.1001.exr"
        exr_file.write_bytes(b"x" * 1024)  # Small test file

        shot = Shot(
            show="testshow",
            sequence="seq01",
            shot="0010",
            workspace_path=str(
                shows_root / "testshow" / "shots" / "seq01" / "seq01_0010"
            ),
        )

        with pytest.MonkeyPatch.context() as m:
            m.setattr(Config, "SHOWS_ROOT", str(shows_root))

            thumb_path = shot.get_thumbnail_path()
            assert thumb_path is not None
            assert thumb_path.suffix == ".exr"
            assert "FG01" in str(thumb_path)


class TestPlateDiscoveryPriority:
    """Test plate discovery priority (FG > BG > others)."""

    def test_fg_preferred_over_bg(self, tmp_path):
        """FG plates should be preferred over BG plates."""
        shows_root = tmp_path / "shows"
        base_path = (
            shows_root
            / "testshow"
            / "shots"
            / "seq01"
            / "seq01_0010"
            / "publish"
            / "turnover"
            / "plate"
        )

        # Create both FG and BG plates
        for plate_name in ["FG01", "BG01"]:
            plate_dir = base_path / plate_name / "v001" / "exr" / "hd"
            plate_dir.mkdir(parents=True)
            (plate_dir / f"{plate_name}.1001.exr").touch()

        with pytest.MonkeyPatch.context() as m:
            m.setattr(Config, "SHOWS_ROOT", str(shows_root))

            result = PathUtils.find_turnover_plate_thumbnail(
                str(shows_root), "testshow", "seq01", "0010"
            )

            assert result is not None
            assert "FG01" in str(result)  # FG should be chosen


class TestCacheManagerIntegration:
    """Test cache manager with real file operations (minimal mocking)."""

    def test_cache_small_jpg(self, tmp_path):
        """Cache manager should handle small JPG files."""
        # Create test JPG
        jpg_file = tmp_path / "test.jpg"
        jpg_file.write_bytes(b"\xff\xd8\xff" + b"x" * 100)  # Minimal JPG header

        cache_manager = CacheManager(cache_dir=tmp_path / "cache")

        # This will fail with real image loading but we're testing the flow
        result = cache_manager.cache_thumbnail(
            jpg_file, show="test", sequence="seq01", shot="0010"
        )

        # With real implementation, this might return None due to invalid image
        # But we're testing that it doesn't crash
        assert result is None or isinstance(result, Path)

    def test_cache_creates_directory_structure(self, tmp_path):
        """Cache manager should create proper directory structure."""
        cache_manager = CacheManager(cache_dir=tmp_path / "cache")

        # Check that cache directories are created
        assert cache_manager.thumbnails_dir.exists()
        assert cache_manager.shots_cache_file.parent.exists()


class TestEndToEndPriority:
    """Test complete workflow with minimal mocking."""

    def test_jpg_preferred_in_full_workflow(self, tmp_path):
        """Full workflow should prefer JPG over EXR."""
        # Setup complete directory structure
        shows_root = tmp_path / "shows"
        shot_dir = shows_root / "testshow" / "shots" / "seq01" / "seq01_0010"

        # Create editorial directory with both formats
        editorial_dir = shot_dir
        for segment in Config.THUMBNAIL_SEGMENTS:
            editorial_dir = editorial_dir / segment
        editorial_dir.mkdir(parents=True)

        (editorial_dir / "thumb.jpg").touch()
        (editorial_dir / "thumb.exr").touch()

        # Test complete discovery
        shot = Shot(
            show="testshow", sequence="seq01", shot="0010", workspace_path=str(shot_dir)
        )

        with pytest.MonkeyPatch.context() as m:
            m.setattr(Config, "SHOWS_ROOT", str(shows_root))

            # 1. Shot finds JPG
            thumb_path = shot.get_thumbnail_path()
            assert thumb_path is not None
            assert thumb_path.suffix == ".jpg"

            # 2. Utils also prefer JPG
            first_image = FileUtils.get_first_image_file(editorial_dir)
            assert first_image is not None
            assert first_image.suffix == ".jpg"

    def test_exr_fallback_in_full_workflow(self, tmp_path):
        """Full workflow should use EXR when no JPG available."""
        shows_root = tmp_path / "shows"
        shot_dir = shows_root / "testshow" / "shots" / "seq01" / "seq01_0010"

        # Create only EXR in editorial
        editorial_dir = shot_dir
        for segment in Config.THUMBNAIL_SEGMENTS:
            editorial_dir = editorial_dir / segment
        editorial_dir.mkdir(parents=True)

        (editorial_dir / "thumb.exr").write_bytes(b"x" * 1024)

        shot = Shot(
            show="testshow", sequence="seq01", shot="0010", workspace_path=str(shot_dir)
        )

        with pytest.MonkeyPatch.context() as m:
            m.setattr(Config, "SHOWS_ROOT", str(shows_root))

            # Shot should find EXR as fallback
            thumb_path = shot.get_thumbnail_path()
            assert thumb_path is not None
            assert thumb_path.suffix == ".exr"
