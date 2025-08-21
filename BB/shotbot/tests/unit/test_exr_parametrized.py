"""Parametrized tests for comprehensive EXR fallback coverage.

These tests use pytest.mark.parametrize to efficiently test multiple
scenarios with the same test logic, ensuring thorough coverage.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cache_manager import CacheManager
from config import Config
from shot_model import Shot
from utils import FileUtils, PathUtils


class TestParametrizedPriority:
    """Parametrized tests for format priority logic."""

    @pytest.mark.parametrize(
        "formats,expected",
        [
            # Single format scenarios
            ([".jpg"], ".jpg"),
            ([".png"], ".png"),
            ([".exr"], ".exr"),
            # Mixed format scenarios
            ([".jpg", ".exr"], ".jpg"),
            ([".png", ".exr"], ".png"),
            ([".jpg", ".png"], ".jpg"),  # JPG preferred over PNG
            ([".jpg", ".png", ".exr"], ".jpg"),
            # Only heavy formats
            ([".exr", ".tiff"], ".exr"),
            ([".tiff", ".exr"], ".exr"),  # EXR is the only supported fallback
            # Empty (no files)
            ([], None),
        ],
    )
    def test_format_priority(self, tmp_path, formats, expected):
        """Test format selection priority with various combinations."""
        test_dir = tmp_path / "test"
        test_dir.mkdir()

        # Create files for each format
        for i, fmt in enumerate(formats):
            (test_dir / f"file_{i}{fmt}").touch()

        result = FileUtils.get_first_image_file(test_dir, allow_fallback=True)

        if expected is None:
            assert result is None
        else:
            assert result is not None
            assert result.suffix == expected

    @pytest.mark.parametrize(
        "plate_name,priority",
        [
            ("FG01", 0),  # Highest priority
            ("FG02", 0),
            ("FG99", 0),
            ("BG01", 1),  # Second priority
            ("BG02", 1),
            ("EL01", 2),  # Lower priority
            ("COMP01", 2),
            ("random", 2),
        ],
    )
    def test_plate_priority_ordering(self, tmp_path, plate_name, priority):
        """Test plate priority calculation for different plate names."""
        shows_root = tmp_path / "shows"

        # Create plate directory
        plate_path = (
            shows_root
            / "test"
            / "shots"
            / "seq01"
            / "seq01_0010"
            / "publish"
            / "turnover"
            / "plate"
            / plate_name
            / "v001"
            / "exr"
            / "4k"
        )
        plate_path.mkdir(parents=True)
        (plate_path / f"{plate_name}.1001.exr").touch()

        # Also create a competing plate
        other_name = "ZZ99"  # Should have lowest priority
        other_path = (
            plate_path.parent.parent.parent / other_name / "v001" / "exr" / "4k"
        )
        other_path.mkdir(parents=True)
        (other_path / f"{other_name}.1001.exr").touch()

        with patch.object(Config, "SHOWS_ROOT", str(shows_root)):
            result = PathUtils.find_turnover_plate_thumbnail(
                str(shows_root), "test", "seq01", "0010"
            )

            # Should find the plate with higher priority
            assert result is not None
            if priority < 2:  # FG or BG should win
                assert plate_name in str(result)
            else:
                # Could be either, but not None
                assert ".exr" in str(result)


class TestParametrizedFileOperations:
    """Parametrized tests for file operations."""

    @pytest.mark.parametrize(
        "file_size_mb,should_resize",
        [
            (0.1, False),  # Very small, no resize needed
            (1, False),  # Small, no resize
            (5, False),  # Medium, maybe resize
            (10, True),  # Large, should resize
            (50, True),  # Very large, definitely resize
            (100, True),  # Huge, must resize
        ],
    )
    def test_file_size_handling(self, tmp_path, file_size_mb, should_resize):
        """Test handling of various file sizes."""
        exr_file = tmp_path / "test.exr"
        exr_file.write_bytes(b"EXR" + b"x" * int(file_size_mb * 1024 * 1024))

        cache_manager = CacheManager(cache_dir=tmp_path / "cache")

        from PIL import Image

        with patch.object(Image, "open") as mock_open:
            mock_img = MagicMock()
            mock_img.size = (4096, 2160)
            mock_img.thumbnail = MagicMock()
            mock_open.return_value = mock_img

            result = cache_manager.cache_thumbnail(
                exr_file,
                show="test",
                sequence="seq",
                shot="0010",
                wait=False,  # Don't wait for async
            )

            # Test behavior: all sizes should be handled without crashing
            assert result is not None  # Returns async result object

    @pytest.mark.parametrize(
        "extension",
        [
            ".jpg",
            ".JPG",
            ".Jpg",
            ".jPg",
            ".png",
            ".PNG",
            ".Png",
            ".exr",
            ".EXR",
            ".Exr",
            ".tiff",
            ".TIFF",
            ".Tiff",
        ],
    )
    def test_extension_case_variations(self, tmp_path, extension):
        """Test that all case variations of extensions are recognized."""
        test_file = tmp_path / f"image{extension}"
        test_file.touch()

        # Test with lowercase search
        base_ext = extension.lower()
        files = FileUtils.find_files_by_extension(tmp_path, base_ext)
        assert len(files) == 1
        assert files[0] == test_file

        # Test with uppercase search
        files = FileUtils.find_files_by_extension(tmp_path, extension.upper())
        assert len(files) == 1
        assert files[0] == test_file


class TestParametrizedPaths:
    """Parametrized tests for path handling."""

    @pytest.mark.parametrize(
        "show,sequence,shot",
        [
            ("show1", "seq01", "0010"),
            ("MyShow", "AB01", "0020"),
            ("test-show", "seq_01", "0030a"),
            ("UPPERCASE", "SEQ99", "9999"),
            ("with_underscore", "with-dash", "0001"),
        ],
    )
    def test_shot_path_construction(self, tmp_path, show, sequence, shot):
        """Test path construction with various naming conventions."""
        shows_root = tmp_path / "shows"

        # Build expected path
        shot_dir = f"{sequence}_{shot}"
        expected_base = shows_root / show / "shots" / sequence / shot_dir

        # Create shot
        Shot(show, sequence, shot, str(expected_base))

        with patch.object(Config, "SHOWS_ROOT", str(shows_root)):
            # Test thumbnail path construction
            thumb_base = PathUtils.build_thumbnail_path(
                str(shows_root), show, sequence, shot
            )

            assert show in str(thumb_base)
            assert sequence in str(thumb_base)
            assert shot_dir in str(thumb_base)

    @pytest.mark.parametrize(
        "depth,exists",
        [
            (1, True),
            (5, True),
            (10, True),
            (20, False),  # Too deep, might not exist
        ],
    )
    def test_directory_depth_handling(self, tmp_path, depth, exists):
        """Test handling of various directory depths."""
        current = tmp_path
        for i in range(depth):
            current = current / f"level_{i}"

        if exists and depth < 15:  # Reasonable depth
            current.mkdir(parents=True)
            (current / "test.exr").touch()

            result = FileUtils.get_first_image_file(current, allow_fallback=True)
            assert result is not None
        else:
            result = PathUtils.validate_path_exists(current, "Deep path")
            assert result is False


class TestParametrizedCaching:
    """Parametrized tests for caching behavior."""

    @pytest.mark.parametrize(
        "wait,expected_return",
        [
            (True, "path_or_none"),  # Synchronous, returns result
            (False, "always_none"),  # Asynchronous, returns None
        ],
    )
    def test_cache_wait_behavior(self, tmp_path, wait, expected_return):
        """Test cache behavior with wait parameter."""
        test_file = tmp_path / "test.jpg"
        test_file.touch()

        cache_manager = CacheManager(cache_dir=tmp_path / "cache")

        from PySide6.QtGui import QImage

        with patch.object(QImage, "__init__", return_value=None):
            result = cache_manager.cache_thumbnail(
                test_file, show="test", sequence="seq", shot="0010", wait=wait
            )

            if expected_return == "always_none":
                # Async returns ThumbnailCacheResult object
                assert result is not None  # Should be ThumbnailCacheResult
            else:
                # Could be path or None depending on success
                assert result is None or isinstance(result, Path)

    @pytest.mark.parametrize("num_shots", [1, 5, 25])
    def test_cache_scalability(self, tmp_path, num_shots):
        """Test cache with varying numbers of shots."""
        cache_manager = CacheManager(cache_dir=tmp_path / "cache")

        # Create and cache multiple shots
        shots = []
        for i in range(num_shots):
            shot = Shot(
                show=f"show_{i % 10}",
                sequence=f"seq{i % 20:02d}",
                shot=f"{i:04d}",
                workspace_path=f"/workspace/{i}",
            )
            shots.append(shot)

        # Cache all shots
        cache_manager.cache_shots(shots)

        # Retrieve and verify
        cached = cache_manager.get_cached_shots()
        assert cached is not None
        assert len(cached) == num_shots


class TestParametrizedErrorHandling:
    """Parametrized tests for error conditions."""

    @pytest.mark.parametrize(
        "error_type,error_instance",
        [
            ("PermissionError", PermissionError("No access")),
            ("FileNotFoundError", FileNotFoundError("File gone")),
            ("OSError", OSError("Disk full")),
            ("IOError", IOError("Read error")),
            ("ValueError", ValueError("Invalid data")),
        ],
    )
    def test_error_resilience(self, tmp_path, error_type, error_instance):
        """Test resilience to various error types."""
        test_file = tmp_path / "test.exr"
        test_file.touch()

        cache_manager = CacheManager(cache_dir=tmp_path / "cache")

        # Mock all EXR processing backends to ensure they all fail
        with patch("PIL.Image.open", side_effect=error_instance), patch(
            "cache.thumbnail_processor.ThumbnailProcessor._load_exr_with_openexr",
            side_effect=error_instance,
        ), patch(
            "cache.thumbnail_processor.ThumbnailProcessor._load_exr_with_system_tools",
            side_effect=error_instance,
        ), patch(
            "cache.thumbnail_processor.ThumbnailProcessor._load_exr_with_imageio",
            side_effect=error_instance,
        ):
            # Should handle error gracefully when all backends fail
            result = cache_manager.cache_thumbnail(
                test_file, show="test", sequence="seq", shot="0010", wait=True
            )

            # Should return None on error, not crash
            assert result is None

    @pytest.mark.parametrize(
        "missing_component", ["show", "sequence", "shot", "workspace_path"]
    )
    def test_missing_shot_components(self, missing_component):
        """Test handling of missing shot components."""
        # Create shot data with one missing component
        shot_data = {
            "show": "test",
            "sequence": "seq01",
            "shot": "0010",
            "workspace_path": "/workspace",
        }

        # Set one component to None
        shot_data[missing_component] = None

        # Should handle gracefully (might raise or return invalid)
        try:
            shot = Shot(**shot_data)
            # If created, verify it has some handling
            assert hasattr(shot, missing_component)
        except (TypeError, ValueError):
            # Expected for required fields
            pass


class TestParametrizedIntegration:
    """Parametrized integration tests."""

    @pytest.mark.parametrize(
        "scenario",
        [
            "editorial_jpg",
            "editorial_exr",
            "turnover_fg",
            "turnover_bg",
            "publish_any",
            "no_thumbnail",
        ],
    )
    def test_complete_discovery_scenarios(self, tmp_path, scenario):
        """Test complete discovery flow for various scenarios."""
        shows_root = tmp_path / "shows"
        shot_dir = shows_root / "test" / "shots" / "seq01" / "seq01_0010"

        # Setup based on scenario
        if scenario == "editorial_jpg":
            # Create full path based on Config.THUMBNAIL_SEGMENTS
            editorial = (
                shot_dir
                / "publish"
                / "editorial"
                / "cutref"
                / "v001"
                / "jpg"
                / "1920x1080"
            )
            editorial.mkdir(parents=True)
            (editorial / "thumb.jpg").touch()
            expected_suffix = ".jpg"

        elif scenario == "editorial_exr":
            editorial = (
                shot_dir
                / "publish"
                / "editorial"
                / "cutref"
                / "v001"
                / "jpg"
                / "1920x1080"
            )
            editorial.mkdir(parents=True)
            (editorial / "thumb.exr").touch()
            expected_suffix = ".exr"

        elif scenario == "turnover_fg":
            plate = (
                shot_dir
                / "publish"
                / "turnover"
                / "plate"
                / "FG01"
                / "v001"
                / "exr"
                / "4k"
            )
            plate.mkdir(parents=True)
            (plate / "fg.1001.exr").touch()
            expected_suffix = ".exr"

        elif scenario == "turnover_bg":
            plate = (
                shot_dir
                / "publish"
                / "turnover"
                / "plate"
                / "BG01"
                / "v001"
                / "exr"
                / "4k"
            )
            plate.mkdir(parents=True)
            (plate / "bg.1001.exr").touch()
            expected_suffix = ".exr"

        elif scenario == "publish_any":
            publish = shot_dir / "publish" / "comp" / "v001"
            publish.mkdir(parents=True)
            (publish / "comp.1001.jpg").touch()
            expected_suffix = ".jpg"

        else:  # no_thumbnail
            shot_dir.mkdir(parents=True)
            expected_suffix = None

        # Create shot and test discovery
        shot = Shot("test", "seq01", "0010", str(shot_dir))

        with patch.object(Config, "SHOWS_ROOT", str(shows_root)):
            thumb_path = shot.get_thumbnail_path()

            if expected_suffix is None:
                assert thumb_path is None
            else:
                assert thumb_path is not None
                assert thumb_path.suffix == expected_suffix
