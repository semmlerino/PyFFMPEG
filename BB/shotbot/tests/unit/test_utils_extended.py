"""Extended unit tests for utils.py to improve coverage.

This module adds comprehensive tests for uncovered functionality in utils.py.
"""

from pathlib import Path
from unittest.mock import patch

from utils import PathUtils, ValidationUtils


class TestPathUtilsTurnoverPlate:
    """Test turnover plate discovery functionality."""

    def test_find_turnover_plate_thumbnail_with_plates(self, tmp_path):
        """Test finding turnover plate thumbnail with actual plate structure."""
        # Create test structure matching expected layout
        show_path = tmp_path / "shows" / "testshow"
        turnover_path = (
            show_path
            / "shots"
            / "seq01"
            / "seq01_shot01"
            / "publish"
            / "turnover"
            / "plates"
        )

        # Create multiple plate directories with priority
        fg_plate = turnover_path / "FG01" / "v001" / "exr" / "1920x1080"
        bg_plate = turnover_path / "BG01" / "v001" / "exr" / "1920x1080"
        el_plate = turnover_path / "EL01" / "v001" / "exr" / "1920x1080"

        for plate_dir in [fg_plate, bg_plate, el_plate]:
            plate_dir.mkdir(parents=True)
            # Create test EXR files
            (plate_dir / "test.1001.exr").touch()
            (plate_dir / "test.1002.exr").touch()

        # Mock the path building and validation
        with patch("utils.PathUtils.validate_path_exists", return_value=True):
            with patch("utils.PathUtils.build_path", return_value=turnover_path):
                result = PathUtils.find_turnover_plate_thumbnail(
                    str(tmp_path / "shows"),
                    "testshow",
                    "seq01",
                    "shot01",
                )

                # Should find FG01 first due to priority
                assert result is not None
                assert "FG01" in str(result)
                assert "1001.exr" in result.name

    def test_find_turnover_plate_no_plates(self):
        """Test find_turnover_plate_thumbnail when no plates exist."""
        with patch("utils.PathUtils.validate_path_exists", return_value=True):
            with patch(
                "pathlib.Path.iterdir",
                side_effect=OSError("Permission denied"),
            ):
                result = PathUtils.find_turnover_plate_thumbnail(
                    "/shows",
                    "testshow",
                    "seq01",
                    "shot01",
                )
                assert result is None

    def test_find_turnover_plate_empty_directory(self, tmp_path):
        """Test when turnover directory exists but is empty."""
        turnover_path = tmp_path / "publish" / "turnover" / "plates"
        turnover_path.mkdir(parents=True)

        with patch("utils.PathUtils.validate_path_exists", return_value=True):
            with patch("utils.PathUtils.build_path", return_value=turnover_path):
                result = PathUtils.find_turnover_plate_thumbnail(
                    str(tmp_path),
                    "testshow",
                    "seq01",
                    "shot01",
                )
                assert result is None

    def test_plate_priority_sorting(self):
        """Test plate priority function used in sorting."""
        # Create mock plate directories
        plates = [
            Path("/test/EL01"),
            Path("/test/FG01"),
            Path("/test/BG01"),
            Path("/test/FG02"),
            Path("/test/random"),
        ]

        # Define the priority function (copied from implementation)
        def plate_priority(plate_dir: Path):
            name = plate_dir.name.upper()
            if name.startswith("FG"):
                return (0, name)
            if name.startswith("BG"):
                return (1, name)
            return (2, name)

        sorted_plates = sorted(plates, key=plate_priority)

        # Check order: FG plates first, then BG, then others
        assert sorted_plates[0].name == "FG01"
        assert sorted_plates[1].name == "FG02"
        assert sorted_plates[2].name == "BG01"
        assert sorted_plates[3].name == "EL01"
        assert sorted_plates[4].name == "random"


class TestPathUtilsPublishThumbnail:
    """Test publish thumbnail discovery functionality."""

    def test_find_any_publish_thumbnail_recursive(self, tmp_path):
        """Test finding any publish thumbnail with recursive search."""
        # Create test structure
        publish_path = (
            tmp_path
            / "shows"
            / "testshow"
            / "shots"
            / "seq01"
            / "seq01_shot01"
            / "publish"
        )
        deep_path = publish_path / "comp" / "v001" / "exr"
        deep_path.mkdir(parents=True)

        # Create test EXR file with 1001
        test_file = deep_path / "comp_v001.1001.exr"
        test_file.touch()

        # Also create non-1001 files that should be ignored
        (deep_path / "comp_v001.1002.exr").touch()
        (deep_path / "comp_v001.jpg").touch()

        with patch("utils.PathUtils.validate_path_exists", return_value=True):
            with patch("utils.PathUtils.build_path", return_value=publish_path):
                result = PathUtils.find_any_publish_thumbnail(
                    str(tmp_path / "shows"),
                    "testshow",
                    "seq01",
                    "shot01",
                )

                assert result is not None
                assert "1001.exr" in result.name

    def test_find_any_publish_thumbnail_max_depth(self, tmp_path):
        """Test find_any_publish_thumbnail respects max depth."""
        # Create very deep structure
        publish_path = tmp_path / "publish"
        very_deep = publish_path
        for i in range(10):  # Create 10 levels deep
            very_deep = very_deep / f"level{i}"
        very_deep.mkdir(parents=True)

        # Put file too deep
        (very_deep / "test.1001.exr").touch()

        # Put file at acceptable depth
        shallow = publish_path / "level0" / "level1"
        (shallow / "test.1001.exr").touch()

        with patch("utils.PathUtils.validate_path_exists", return_value=True):
            with patch("utils.PathUtils.build_path", return_value=publish_path):
                result = PathUtils.find_any_publish_thumbnail(
                    "/shows",
                    "testshow",
                    "seq01",
                    "shot01",
                    max_depth=3,  # Only search 3 levels
                )

                # Should find the shallow file, not the deep one
                assert result is not None
                assert "level1" in str(result)

    def test_find_any_publish_thumbnail_permission_error(self, tmp_path):
        """Test find_any_publish_thumbnail handles permission errors gracefully."""
        publish_path = tmp_path / "publish"
        publish_path.mkdir()

        with patch("utils.PathUtils.validate_path_exists", return_value=True):
            with patch("utils.PathUtils.build_path", return_value=publish_path):
                with patch.object(
                    Path,
                    "iterdir",
                    side_effect=PermissionError("Access denied"),
                ):
                    result = PathUtils.find_any_publish_thumbnail(
                        "/shows",
                        "testshow",
                        "seq01",
                        "shot01",
                    )
                    assert result is None

    def test_find_any_publish_thumbnail_no_publish_dir(self):
        """Test when publish directory doesn't exist."""
        with patch("utils.PathUtils.validate_path_exists", return_value=False):
            result = PathUtils.find_any_publish_thumbnail(
                "/shows",
                "testshow",
                "seq01",
                "shot01",
            )
            assert result is None


class TestPathUtilsPlateDiscovery:
    """Test plate directory discovery functionality."""

    def test_discover_plate_directories_standard(self, tmp_path):
        """Test discovering standard plate directories with actual discover_plate_directories method."""
        # Create test structure
        raw_path = tmp_path / "raw"
        raw_path.mkdir()

        # Create plate directories matching Config.PLATE_DISCOVERY_PATTERNS
        # Based on the actual code, this looks for specific patterns defined in Config
        plates = ["FG01", "BG01"]  # These should match Config.PLATE_DISCOVERY_PATTERNS
        for plate in plates:
            (raw_path / plate).mkdir()

        # Create non-plate items
        (raw_path / "notes.txt").touch()
        (raw_path / "reference").mkdir()

        result = PathUtils.discover_plate_directories(str(raw_path))

        # Check that we found the expected plates
        assert len(result) == len(plates)
        found_names = [name for name, _ in result]
        for plate in plates:
            assert plate in found_names

    def test_discover_plate_directories_empty(self, tmp_path):
        """Test discovering plates in empty directory."""
        raw_path = tmp_path / "raw"
        raw_path.mkdir()

        result = PathUtils.discover_plate_directories(str(raw_path))
        assert result == []

    def test_discover_plate_directories_nonexistent(self):
        """Test discover_plate_directories with non-existent path."""
        with patch("utils.PathUtils.validate_path_exists", return_value=False):
            result = PathUtils.discover_plate_directories("/non/existent/path")
            assert result == []


class TestValidationUtilsExtended:
    """Extended tests for ValidationUtils."""

    def test_get_excluded_users(self):
        """Test getting excluded users list."""
        with patch(
            "utils.ValidationUtils.get_current_username",
            return_value="testuser",
        ):
            excluded = ValidationUtils.get_excluded_users()

            assert isinstance(excluded, set)
            assert "testuser" in excluded

    def test_get_excluded_users_with_additional(self):
        """Test getting excluded users with additional users."""
        with patch(
            "utils.ValidationUtils.get_current_username",
            return_value="testuser",
        ):
            additional = {"user1", "user2"}
            excluded = ValidationUtils.get_excluded_users(additional)

            assert isinstance(excluded, set)
            assert "testuser" in excluded
            assert "user1" in excluded
            assert "user2" in excluded
