"""Unit tests for RawPlateFinder module."""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from raw_plate_finder import RawPlateFinder


@pytest.fixture
def mock_workspace_path():
    """Mock workspace path for testing."""
    return "/shows/testshow/shots/seq01/seq01_shot01"


@pytest.fixture
def mock_shot_name():
    """Mock shot name for testing."""
    return "seq01_shot01"


@pytest.fixture
def mock_plate_structure(tmp_path):
    """Create a mock plate directory structure for testing."""
    # Create base path
    base_path = tmp_path / "publish" / "plate" / "turnover"

    # Create FG01 plate with v002 (latest)
    fg01_path = base_path / "FG01"
    fg01_v001 = fg01_path / "v001" / "exr" / "1920x1080"
    fg01_v002 = fg01_path / "v002" / "exr" / "4312x2304"
    fg01_v001.mkdir(parents=True)
    fg01_v002.mkdir(parents=True)

    # Create sample plate files for FG01 v002
    plate_file = fg01_v002 / "seq01_shot01_turnover-plate_FG01_aces_v002.1001.exr"
    plate_file.touch()
    plate_file2 = fg01_v002 / "seq01_shot01_turnover-plate_FG01_aces_v002.1002.exr"
    plate_file2.touch()

    # Create BG01 plate with v001
    bg01_path = base_path / "BG01"
    bg01_v001 = bg01_path / "v001" / "exr" / "1920x1080"
    bg01_v001.mkdir(parents=True)

    # Create sample plate files for BG01 v001
    bg_file = (
        bg01_v001 / "seq01_shot01_turnover-plate_BG01_lin_sgamut3cine_v001.1001.exr"
    )
    bg_file.touch()

    return base_path


class TestRawPlateFinder:
    """Test RawPlateFinder class."""

    def test_find_latest_raw_plate_success(
        self, mock_workspace_path, mock_shot_name, mock_plate_structure
    ):
        """Test successfully finding the latest raw plate."""
        with patch(
            "raw_plate_finder.PathUtils.build_raw_plate_path",
            return_value=mock_plate_structure,
        ):
            with patch(
                "raw_plate_finder.PathUtils.validate_path_exists", return_value=True
            ):
                with patch(
                    "raw_plate_finder.PathUtils.discover_plate_directories",
                    return_value=[("FG01", 10), ("BG01", 7)],
                ):
                    result = RawPlateFinder.find_latest_raw_plate(
                        mock_workspace_path, mock_shot_name
                    )

                    assert result is not None
                    assert "FG01" in result  # Should prioritize FG01
                    assert "v002" in result  # Should find latest version
                    assert "####" in result  # Should have frame pattern
                    assert "aces" in result  # Should detect color space

    def test_find_latest_raw_plate_no_base_path(
        self, mock_workspace_path, mock_shot_name
    ):
        """Test when base path doesn't exist."""
        with patch(
            "raw_plate_finder.PathUtils.build_raw_plate_path",
            return_value=Path("/nonexistent"),
        ):
            with patch(
                "raw_plate_finder.PathUtils.validate_path_exists", return_value=False
            ):
                result = RawPlateFinder.find_latest_raw_plate(
                    mock_workspace_path, mock_shot_name
                )
                assert result is None

    def test_find_latest_raw_plate_no_plate_dirs(
        self, mock_workspace_path, mock_shot_name
    ):
        """Test when no plate directories are found."""
        with patch(
            "raw_plate_finder.PathUtils.build_raw_plate_path",
            return_value=Path("/test"),
        ):
            with patch(
                "raw_plate_finder.PathUtils.validate_path_exists", return_value=True
            ):
                with patch(
                    "raw_plate_finder.PathUtils.discover_plate_directories",
                    return_value=[],
                ):
                    result = RawPlateFinder.find_latest_raw_plate(
                        mock_workspace_path, mock_shot_name
                    )
                    assert result is None

    def test_find_latest_raw_plate_no_versions(
        self, mock_workspace_path, mock_shot_name, tmp_path
    ):
        """Test when plate directory exists but has no version directories."""
        base_path = tmp_path / "plate"
        fg01_path = base_path / "FG01"
        fg01_path.mkdir(parents=True)

        with patch(
            "raw_plate_finder.PathUtils.build_raw_plate_path", return_value=base_path
        ):
            with patch(
                "raw_plate_finder.PathUtils.validate_path_exists", return_value=True
            ):
                with patch(
                    "raw_plate_finder.PathUtils.discover_plate_directories",
                    return_value=[("FG01", 10)],
                ):
                    result = RawPlateFinder.find_latest_raw_plate(
                        mock_workspace_path, mock_shot_name
                    )
                    assert result is None

    def test_find_latest_raw_plate_no_exr_directory(
        self, mock_workspace_path, mock_shot_name, tmp_path
    ):
        """Test when version exists but no exr directory."""
        base_path = tmp_path / "plate"
        fg01_v001 = base_path / "FG01" / "v001"
        fg01_v001.mkdir(parents=True)

        with patch(
            "raw_plate_finder.PathUtils.build_raw_plate_path", return_value=base_path
        ):
            with patch(
                "raw_plate_finder.PathUtils.validate_path_exists", return_value=True
            ):
                with patch(
                    "raw_plate_finder.PathUtils.discover_plate_directories",
                    return_value=[("FG01", 10)],
                ):
                    result = RawPlateFinder.find_latest_raw_plate(
                        mock_workspace_path, mock_shot_name
                    )
                    assert result is None

    def test_find_plate_file_pattern_match(self, mock_shot_name, tmp_path):
        """Test finding plate file pattern with color space."""
        resolution_dir = tmp_path / "resolution"
        resolution_dir.mkdir()

        # Create file that matches pattern 1
        plate_file = (
            resolution_dir / "seq01_shot01_turnover-plate_FG01_aces_v002.1001.exr"
        )
        plate_file.touch()

        result = RawPlateFinder._find_plate_file_pattern(
            resolution_dir, mock_shot_name, "FG01", "v002"
        )

        assert result is not None
        assert "aces" in result
        assert "####" in result
        assert "FG01" in result

    def test_find_plate_file_pattern_alternative(self, mock_shot_name, tmp_path):
        """Test finding plate file with alternative pattern (no underscore before color space)."""
        resolution_dir = tmp_path / "resolution"
        resolution_dir.mkdir()

        # Create file that matches pattern 2 (no underscore before color space)
        # Pattern is: FG01 directly followed by color space
        plate_file = (
            resolution_dir / "seq01_shot01_turnover-plate_FG01aces_v002.1001.exr"
        )
        plate_file.touch()

        result = RawPlateFinder._find_plate_file_pattern(
            resolution_dir, mock_shot_name, "FG01", "v002"
        )

        assert result is not None
        assert "aces" in result
        assert "####" in result
        assert "FG01aces" in result  # Pattern 2 format

    def test_find_plate_file_pattern_fallback(self, mock_shot_name, tmp_path):
        """Test fallback to common color spaces when no files found."""
        resolution_dir = tmp_path / "resolution"
        resolution_dir.mkdir()

        # Create file with fallback color space pattern
        fallback_file = (
            resolution_dir / "seq01_shot01_turnover-plate_FG01_aces_v002.1001.exr"
        )
        fallback_file.touch()

        with patch("raw_plate_finder.Config.COLOR_SPACE_PATTERNS", ["aces"]):
            result = RawPlateFinder._find_plate_file_pattern(
                resolution_dir, mock_shot_name, "FG01", "v002"
            )

            # Should use fallback color space
            assert result is not None
            assert "aces" in result

    def test_find_plate_file_pattern_permission_error(self, mock_shot_name):
        """Test handling permission error when scanning directory."""
        resolution_dir = MagicMock(spec=Path)
        resolution_dir.iterdir.side_effect = PermissionError("Access denied")

        result = RawPlateFinder._find_plate_file_pattern(
            resolution_dir, mock_shot_name, "FG01", "v002"
        )

        assert result is None

    def test_get_version_from_path(self):
        """Test extracting version from path."""
        with patch(
            "raw_plate_finder.VersionUtils.extract_version_from_path",
            return_value="v002",
        ):
            result = RawPlateFinder.get_version_from_path("/path/to/plate_v002.exr")
            assert result == "v002"

    def test_get_version_from_path_none(self):
        """Test extracting version returns None when not found."""
        with patch(
            "raw_plate_finder.VersionUtils.extract_version_from_path", return_value=None
        ):
            result = RawPlateFinder.get_version_from_path("/path/to/plate.exr")
            assert result is None

    def test_verify_plate_exists_valid(self, tmp_path):
        """Test verifying plate exists with valid path."""
        # Create test structure
        plate_dir = tmp_path / "plates"
        plate_dir.mkdir()

        # Create matching plate file
        plate_file = plate_dir / "shot_v001.1001.exr"
        plate_file.touch()

        plate_path = str(plate_dir / "shot_v001.####.exr")

        with patch(
            "raw_plate_finder.PathUtils.validate_path_exists", return_value=True
        ):
            result = RawPlateFinder.verify_plate_exists(plate_path)
            assert result is True

    def test_verify_plate_exists_invalid_path(self):
        """Test verify with invalid path (no #### pattern)."""
        result = RawPlateFinder.verify_plate_exists("/path/to/plate.exr")
        assert result is False

    def test_verify_plate_exists_empty_path(self):
        """Test verify with empty path."""
        result = RawPlateFinder.verify_plate_exists("")
        assert result is False

        result = RawPlateFinder.verify_plate_exists(None)
        assert result is False

    def test_verify_plate_exists_directory_not_found(self):
        """Test verify when directory doesn't exist."""
        with patch(
            "raw_plate_finder.PathUtils.validate_path_exists", return_value=False
        ):
            result = RawPlateFinder.verify_plate_exists("/nonexistent/plate.####.exr")
            assert result is False

    def test_verify_plate_exists_no_matching_files(self, tmp_path):
        """Test verify when no matching files found."""
        plate_dir = tmp_path / "plates"
        plate_dir.mkdir()

        # Create non-matching file
        other_file = plate_dir / "other.exr"
        other_file.touch()

        plate_path = str(plate_dir / "shot_v001.####.exr")

        with patch(
            "raw_plate_finder.PathUtils.validate_path_exists", return_value=True
        ):
            result = RawPlateFinder.verify_plate_exists(plate_path)
            assert result is False

    def test_verify_plate_exists_permission_error(self):
        """Test verify with permission error."""
        mock_dir = MagicMock(spec=Path)
        mock_dir.iterdir.side_effect = PermissionError("Access denied")

        with patch(
            "raw_plate_finder.PathUtils.validate_path_exists", return_value=True
        ):
            with patch("pathlib.Path", return_value=mock_dir):
                result = RawPlateFinder.verify_plate_exists("/test/plate.####.exr")
                assert result is False

    def test_verify_plate_exists_regex_error(self):
        """Test verify with invalid regex pattern."""
        mock_dir = MagicMock(spec=Path)
        mock_dir.iterdir.return_value = []

        # Create a path that would generate invalid regex
        plate_path = "/test/plate[invalid.####.exr"

        with patch(
            "raw_plate_finder.PathUtils.validate_path_exists", return_value=True
        ):
            with patch(
                "pathlib.Path.parent", new_callable=lambda: Mock(return_value=mock_dir)
            ):
                result = RawPlateFinder.verify_plate_exists(plate_path)
                assert result is False

    def test_get_plate_patterns_caching(self, mock_shot_name):
        """Test that regex patterns are cached properly."""
        # Clear cache first
        RawPlateFinder._pattern_cache.clear()

        # First call should create patterns
        patterns1 = RawPlateFinder._get_plate_patterns(mock_shot_name, "FG01", "v002")
        assert patterns1 is not None
        assert len(RawPlateFinder._pattern_cache) == 1

        # Second call with same params should return cached patterns
        patterns2 = RawPlateFinder._get_plate_patterns(mock_shot_name, "FG01", "v002")
        assert patterns1 is patterns2  # Same object
        assert len(RawPlateFinder._pattern_cache) == 1  # Still only one entry

        # Different params should create new cache entry
        patterns3 = RawPlateFinder._get_plate_patterns(mock_shot_name, "BG01", "v001")
        assert patterns3 is not patterns1
        assert len(RawPlateFinder._pattern_cache) == 2

    def test_pattern_matching_variations(self):
        """Test regex patterns match expected filename formats."""
        shot_name = "seq01_shot01"
        plate_name = "FG01"
        version = "v002"

        pattern1, pattern2 = RawPlateFinder._get_plate_patterns(
            shot_name, plate_name, version
        )

        # Test pattern 1: underscore before color space
        filename1 = "seq01_shot01_turnover-plate_FG01_aces_v002.1001.exr"
        match1 = pattern1.match(filename1)
        assert match1 is not None
        assert match1.group(1) == "aces"

        # Test pattern 2: no underscore before color space
        # Note: The actual pattern expects FG01 followed directly by color space
        # (no underscore), then underscore before version
        filename2 = "seq01_shot01_turnover-plate_FG01aces_v002.1001.exr"
        match2 = pattern2.match(filename2)
        assert match2 is not None
        assert match2.group(1) == "aces"

        # Test non-matching filename
        filename3 = "different_shot_turnover-plate_FG01_aces_v002.1001.exr"
        assert pattern1.match(filename3) is None
        assert pattern2.match(filename3) is None

    def test_multiple_plates_priority(
        self, mock_workspace_path, mock_shot_name, tmp_path
    ):
        """Test that FG plates are prioritized over BG plates."""
        base_path = tmp_path / "plate"

        # Create BG01 with newer version (v003)
        bg01_v003 = base_path / "BG01" / "v003" / "exr" / "1920x1080"
        bg01_v003.mkdir(parents=True)
        bg_file = bg01_v003 / "seq01_shot01_turnover-plate_BG01_aces_v003.1001.exr"
        bg_file.touch()

        # Create FG01 with older version (v001)
        fg01_v001 = base_path / "FG01" / "v001" / "exr" / "1920x1080"
        fg01_v001.mkdir(parents=True)
        fg_file = fg01_v001 / "seq01_shot01_turnover-plate_FG01_aces_v001.1001.exr"
        fg_file.touch()

        with patch(
            "raw_plate_finder.PathUtils.build_raw_plate_path", return_value=base_path
        ):
            with patch(
                "raw_plate_finder.PathUtils.validate_path_exists", return_value=True
            ):
                with patch(
                    "raw_plate_finder.PathUtils.discover_plate_directories",
                    return_value=[("FG01", 10), ("BG01", 7)],
                ):  # FG01 has higher priority
                    result = RawPlateFinder.find_latest_raw_plate(
                        mock_workspace_path, mock_shot_name
                    )

                    # Should find FG01 even though BG01 has newer version
                    assert result is not None
                    assert "FG01" in result
                    assert "v001" in result
