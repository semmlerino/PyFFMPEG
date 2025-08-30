"""Extended unit tests for utils.py to improve coverage.

This module adds comprehensive tests for uncovered functionality in utils.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# This test file follows UNIFIED_TESTING_GUIDE best practices:
# - Test behavior, not implementation
# - Use test doubles instead of mocks
# - Real components where possible
# - Thread-safe testing patterns
# Test doubles for behavior testing (UNIFIED_TESTING_GUIDE)
from utils import PathUtils, ValidationUtils

pytestmark = pytest.mark.unit


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
            / "plate"
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

        # Test with real path building and validation
        result = PathUtils.find_turnover_plate_thumbnail(
            str(tmp_path / "shows"),
            "testshow",
            "seq01",
            "shot01",
        )

        # Should find FG01 first due to priority (when structure exists)
        assert result is not None
        assert "FG01" in str(result)
        assert "1001.exr" in result.name

    def test_find_turnover_plate_no_plates(self, tmp_path):
        """Test find_turnover_plate_thumbnail when no plates exist."""
        # Create base structure without plates
        shows_root = tmp_path / "shows"
        base_path = (
            shows_root
            / "testshow"
            / "shots"
            / "seq01"
            / "seq01_shot01"
            / "publish"
            / "turnover"
            / "plate"
        )
        base_path.mkdir(parents=True)

        result = PathUtils.find_turnover_plate_thumbnail(
            str(shows_root),
            "testshow",
            "seq01",
            "shot01",
        )
        assert result is None

    def test_find_turnover_plate_empty_directory(self, tmp_path):
        """Test when turnover directory exists but is empty."""
        shows_root = tmp_path / "shows"
        turnover_path = (
            shows_root
            / "testshow"
            / "shots"
            / "seq01"
            / "seq01_shot01"
            / "publish"
            / "turnover"
            / "plates"
        )
        turnover_path.mkdir(parents=True)

        result = PathUtils.find_turnover_plate_thumbnail(
            str(shows_root),
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
        # Create proper show/shot structure
        shows_root = tmp_path / "shows"
        publish_path = (
            shows_root / "testshow" / "shots" / "seq01" / "seq01_shot01" / "publish"
        )

        # Create very deep structure
        very_deep = publish_path
        for i in range(10):  # Create 10 levels deep
            very_deep = very_deep / f"level{i}"
        very_deep.mkdir(parents=True)

        # Put file too deep
        (very_deep / "test.1001.exr").touch()

        # Put file at acceptable depth
        shallow = publish_path / "level0" / "level1"
        shallow.mkdir(parents=True, exist_ok=True)
        (shallow / "test.1001.exr").touch()

        result = PathUtils.find_any_publish_thumbnail(
            str(shows_root),
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
        shows_root = tmp_path / "shows"
        publish_path = (
            shows_root / "testshow" / "shots" / "seq01" / "seq01_shot01" / "publish"
        )
        publish_path.mkdir(parents=True)

        # Create a subdirectory and make it inaccessible
        restricted_dir = publish_path / "restricted"
        restricted_dir.mkdir()
        restricted_dir.chmod(0o000)  # Remove all permissions

        try:
            result = PathUtils.find_any_publish_thumbnail(
                str(shows_root),
                "testshow",
                "seq01",
                "shot01",
            )
            # Should handle permission error gracefully and return None
            assert result is None
        finally:
            # Restore permissions for cleanup
            restricted_dir.chmod(0o755)

    def test_find_any_publish_thumbnail_no_publish_dir(self, tmp_path):
        """Test when publish directory doesn't exist."""
        shows_root = tmp_path / "shows"
        shows_root.mkdir()
        # Don't create the publish directory structure

        result = PathUtils.find_any_publish_thumbnail(
            str(shows_root),
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
        result = PathUtils.discover_plate_directories("/non/existent/path")
        assert result == []


class TestValidationUtilsExtended:
    """Extended tests for ValidationUtils."""

    def test_get_excluded_users(self):
        """Test getting excluded users list."""
        # Test with real username from environment or default
        excluded = ValidationUtils.get_excluded_users()

        assert isinstance(excluded, set)
        assert len(excluded) >= 1  # Should include at least current user

    def test_get_excluded_users_with_additional(self):
        """Test getting excluded users with additional users."""
        additional = {"user1", "user2"}
        excluded = ValidationUtils.get_excluded_users(additional)

        assert isinstance(excluded, set)
        assert "user1" in excluded
        assert "user2" in excluded
        assert len(excluded) >= 3  # Should include current user + 2 additional
