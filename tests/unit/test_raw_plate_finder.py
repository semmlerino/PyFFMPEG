"""Unit tests for RawPlateFinder module following UNIFIED_TESTING_GUIDE.

This refactored version:
- Creates real directory structures with actual files
- Tests actual plate discovery behavior
- No mocking of internal PathUtils/FileUtils/VersionUtils
- Uses real file operations
"""

from __future__ import annotations

# Standard library imports
from typing import TYPE_CHECKING

# Third-party imports
import pytest
from config import Config

# Local application imports
from raw_plate_finder import RawPlateFinder
from utils import VersionUtils

if TYPE_CHECKING:
    from pathlib import Path

# This test file follows UNIFIED_TESTING_GUIDE best practices:
# - Test behavior, not implementation
# - Use test doubles instead of mocks
# - Real components where possible
# - Thread-safe testing patterns
# Test doubles for behavior testing (UNIFIED_TESTING_GUIDE)

pytestmark = pytest.mark.unit


class TestRawPlateFinder:
    """Test RawPlateFinder with real file operations."""

    def test_find_latest_raw_plate_success(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test successfully finding the latest raw plate with real files."""
        # Create real directory structure
        shows_root = tmp_path / "shows"
        workspace_path = shows_root / "testshow" / "shots" / "seq01" / "seq01_shot01"
        workspace_path.mkdir(parents=True, exist_ok=True)

        # Create real plate structure
        plate_base = workspace_path / "publish" / "turnover" / "plate" / "input_plate"

        # Create FG01 with v001 and v002 (v002 is latest)
        fg01_v001 = plate_base / "FG01" / "v001" / "exr" / "1920x1080"
        fg01_v001.mkdir(parents=True, exist_ok=True)
        (fg01_v001 / "seq01_shot01_turnover-plate_FG01_aces_v001.1001.exr").touch()
        (fg01_v001 / "seq01_shot01_turnover-plate_FG01_aces_v001.1002.exr").touch()

        fg01_v002 = plate_base / "FG01" / "v002" / "exr" / "4312x2304"
        fg01_v002.mkdir(parents=True, exist_ok=True)
        (fg01_v002 / "seq01_shot01_turnover-plate_FG01_aces_v002.1001.exr").touch()
        (fg01_v002 / "seq01_shot01_turnover-plate_FG01_aces_v002.1002.exr").touch()

        # Create BG01 with v001
        bg01_v001 = plate_base / "BG01" / "v001" / "exr" / "1920x1080"
        bg01_v001.mkdir(parents=True, exist_ok=True)
        (
            bg01_v001 / "seq01_shot01_turnover-plate_BG01_lin_sgamut3cine_v001.1001.exr"
        ).touch()

        # Override Config.SHOWS_ROOT if needed
        monkeypatch.setattr("config.Config.SHOWS_ROOT", str(shows_root))

        # Test actual discovery
        result = RawPlateFinder.find_latest_raw_plate(
            str(workspace_path), "seq01_shot01"
        )

        # Verify behavior
        assert result is not None
        assert "FG01" in result  # Should prioritize FG01
        assert "v002" in result  # Should find latest version
        assert "####" in result  # Should have frame pattern
        assert "aces" in result  # Should detect color space
        assert "4312x2304" in result  # Should use highest resolution

    def test_find_latest_raw_plate_bg_only(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test finding BG plate when no FG plate exists."""
        # Create real directory structure
        shows_root = tmp_path / "shows"
        workspace_path = shows_root / "testshow" / "shots" / "seq01" / "seq01_shot01"
        workspace_path.mkdir(parents=True, exist_ok=True)

        # Create only BG01 plate
        plate_base = workspace_path / "publish" / "turnover" / "plate" / "input_plate"
        bg01_v001 = plate_base / "BG01" / "v001" / "exr" / "1920x1080"
        bg01_v001.mkdir(parents=True, exist_ok=True)
        (bg01_v001 / "seq01_shot01_turnover-plate_BG01_aces_v001.1001.exr").touch()
        (bg01_v001 / "seq01_shot01_turnover-plate_BG01_aces_v001.1002.exr").touch()

        monkeypatch.setattr("config.Config.SHOWS_ROOT", str(shows_root))

        # Test actual discovery
        result = RawPlateFinder.find_latest_raw_plate(
            str(workspace_path), "seq01_shot01"
        )

        # Verify behavior
        assert result is not None
        assert "BG01" in result
        assert "v001" in result
        assert "####" in result
        assert "aces" in result

    def test_find_latest_raw_plate_no_plates(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test when no plate directories exist."""
        # Create workspace but no plates
        shows_root = tmp_path / "shows"
        workspace_path = shows_root / "testshow" / "shots" / "seq01" / "seq01_shot01"
        workspace_path.mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr("config.Config.SHOWS_ROOT", str(shows_root))

        # Test actual discovery
        result = RawPlateFinder.find_latest_raw_plate(
            str(workspace_path), "seq01_shot01"
        )

        # Should return None when no plates found
        assert result is None

    def test_find_latest_raw_plate_no_workspace(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test when workspace path doesn't exist."""
        shows_root = tmp_path / "shows"
        nonexistent_path = shows_root / "nonexistent" / "path"

        monkeypatch.setattr("config.Config.SHOWS_ROOT", str(shows_root))

        # Test with nonexistent path
        result = RawPlateFinder.find_latest_raw_plate(
            str(nonexistent_path), "seq01_shot01"
        )

        assert result is None

    def test_find_plate_file_pattern_standard(self, tmp_path: Path) -> None:
        """Test finding standard plate file pattern with underscore."""
        resolution_dir = tmp_path / "resolution"
        resolution_dir.mkdir()

        # Create standard pattern file (underscore before color space)
        plate_file = (
            resolution_dir / "seq01_shot01_turnover-plate_FG01_aces_v002.1001.exr"
        )
        plate_file.touch()
        plate_file2 = (
            resolution_dir / "seq01_shot01_turnover-plate_FG01_aces_v002.1002.exr"
        )
        plate_file2.touch()

        # Test actual file discovery
        result = RawPlateFinder._find_plate_file_pattern(
            resolution_dir, "seq01_shot01", "FG01", "v002"
        )

        assert result is not None
        assert "aces" in result
        assert "####" in result
        assert "FG01_aces" in result  # Standard format with underscore

    def test_find_plate_file_pattern_alternative(self, tmp_path: Path) -> None:
        """Test finding alternative plate file pattern without underscore."""
        resolution_dir = tmp_path / "resolution"
        resolution_dir.mkdir()

        # Create alternative pattern file (no underscore before color space)
        plate_file = (
            resolution_dir / "seq01_shot01_turnover-plate_FG01aces_v002.1001.exr"
        )
        plate_file.touch()
        plate_file2 = (
            resolution_dir / "seq01_shot01_turnover-plate_FG01aces_v002.1002.exr"
        )
        plate_file2.touch()

        # Test actual file discovery
        result = RawPlateFinder._find_plate_file_pattern(
            resolution_dir, "seq01_shot01", "FG01", "v002"
        )

        assert result is not None
        assert "aces" in result
        assert "####" in result
        assert "FG01aces" in result  # Alternative format without underscore

    def test_find_plate_file_pattern_mixed_colorspaces(self, tmp_path: Path) -> None:
        """Test discovering actual color space from files."""
        resolution_dir = tmp_path / "resolution"
        resolution_dir.mkdir()

        # Create files with different color spaces
        (
            resolution_dir
            / "seq01_shot01_turnover-plate_FG01_lin_sgamut3cine_v002.1001.exr"
        ).touch()
        (
            resolution_dir
            / "seq01_shot01_turnover-plate_FG01_lin_sgamut3cine_v002.1002.exr"
        ).touch()

        # Test actual discovery
        result = RawPlateFinder._find_plate_file_pattern(
            resolution_dir, "seq01_shot01", "FG01", "v002"
        )

        assert result is not None
        assert "lin_sgamut3cine" in result  # Should detect actual color space
        assert "####" in result
        assert "FG01" in result

    def test_find_plate_file_pattern_no_files(self, tmp_path: Path) -> None:
        """Test when no matching files exist."""
        resolution_dir = tmp_path / "resolution"
        resolution_dir.mkdir()

        # Create non-matching file
        (resolution_dir / "different_file.exr").touch()

        # Test actual discovery
        result = RawPlateFinder._find_plate_file_pattern(
            resolution_dir, "seq01_shot01", "FG01", "v002"
        )

        assert result is None

    def test_verify_plate_exists_with_real_files(self, tmp_path: Path) -> None:
        """Test verifying plate exists with real matching files."""
        plate_dir = tmp_path / "plates"
        plate_dir.mkdir()

        # Create real plate sequence
        (plate_dir / "shot_v001.1001.exr").touch()
        (plate_dir / "shot_v001.1002.exr").touch()
        (plate_dir / "shot_v001.1003.exr").touch()

        # Test with #### pattern
        plate_path = str(plate_dir / "shot_v001.####.exr")
        result = RawPlateFinder.verify_plate_exists(plate_path)

        assert result is True

    def test_verify_plate_exists_no_matching_files(self, tmp_path: Path) -> None:
        """Test verify when no matching files found."""
        plate_dir = tmp_path / "plates"
        plate_dir.mkdir()

        # Create non-matching files
        (plate_dir / "other_shot.1001.exr").touch()

        # Test with different pattern
        plate_path = str(plate_dir / "shot_v001.####.exr")
        result = RawPlateFinder.verify_plate_exists(plate_path)

        assert result is False

    def test_verify_plate_exists_invalid_pattern(self) -> None:
        """Test verify with invalid path (no #### pattern)."""
        result = RawPlateFinder.verify_plate_exists("/path/to/plate.exr")
        assert result is False

        result = RawPlateFinder.verify_plate_exists("/path/to/plate")
        assert result is False

    def test_verify_plate_exists_empty_path(self) -> None:
        """Test verify with empty or None path."""
        result = RawPlateFinder.verify_plate_exists("")
        assert result is False

        result = RawPlateFinder.verify_plate_exists(None)
        assert result is False

    def test_multiple_plates_priority(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that FG plates are prioritized over BG plates with real files."""
        # Create real directory structure
        shows_root = tmp_path / "shows"
        workspace_path = shows_root / "testshow" / "shots" / "seq01" / "seq01_shot01"
        workspace_path.mkdir(parents=True, exist_ok=True)

        plate_base = workspace_path / "publish" / "turnover" / "plate" / "input_plate"

        # Create BG01 with newer version (v003)
        bg01_v003 = plate_base / "BG01" / "v003" / "exr" / "1920x1080"
        bg01_v003.mkdir(parents=True, exist_ok=True)
        (bg01_v003 / "seq01_shot01_turnover-plate_BG01_aces_v003.1001.exr").touch()

        # Create FG01 with older version (v001)
        fg01_v001 = plate_base / "FG01" / "v001" / "exr" / "1920x1080"
        fg01_v001.mkdir(parents=True, exist_ok=True)
        (fg01_v001 / "seq01_shot01_turnover-plate_FG01_aces_v001.1001.exr").touch()

        monkeypatch.setattr("config.Config.SHOWS_ROOT", str(shows_root))

        # Test actual discovery
        result = RawPlateFinder.find_latest_raw_plate(
            str(workspace_path), "seq01_shot01"
        )

        # Should find FG01 even though BG01 has newer version
        assert result is not None
        assert "FG01" in result
        assert "v001" in result  # Older version but FG01 has priority

    def test_multiple_versions_selection(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test selecting the latest version from multiple versions."""
        # Create real directory structure
        shows_root = tmp_path / "shows"
        workspace_path = shows_root / "testshow" / "shots" / "seq01" / "seq01_shot01"
        workspace_path.mkdir(parents=True, exist_ok=True)

        plate_base = workspace_path / "publish" / "turnover" / "plate" / "input_plate"

        # Create FG01 with multiple versions
        versions = ["v001", "v002", "v003", "v010"]
        for version in versions:
            version_dir = plate_base / "FG01" / version / "exr" / "1920x1080"
            version_dir.mkdir(parents=True, exist_ok=True)
            (
                version_dir
                / f"seq01_shot01_turnover-plate_FG01_aces_{version}.1001.exr"
            ).touch()

        monkeypatch.setattr("config.Config.SHOWS_ROOT", str(shows_root))

        # Test actual discovery
        result = RawPlateFinder.find_latest_raw_plate(
            str(workspace_path), "seq01_shot01"
        )

        # Should find v010 (latest when sorted)
        assert result is not None
        assert "v010" in result

    @pytest.mark.parametrize(
        ("version", "plate_name", "expected_version"),
        [
            pytest.param("v001", "FG01", "v001", id="basic_version"),
            pytest.param("v010", "FG01", "v010", id="higher_version"),
            pytest.param("v002", "BG01", "v002", id="bg_plate"),
            pytest.param(
                "v999",
                "COMP01",
                "v999",
                marks=pytest.mark.slow,
                id="high_version_number",
            ),
        ],
    )
    def test_parametrized_version_discovery(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, version: str, plate_name: str, expected_version: str
    ) -> None:
        """Test version discovery with various plate and version combinations."""
        # Clear all caches for test isolation in parallel execution
        RawPlateFinder._pattern_cache.clear()
        RawPlateFinder._verify_pattern_cache.clear()
        VersionUtils._version_cache.clear()

        # Setup structure
        shows_root = tmp_path / "shows"
        workspace_path = shows_root / "testshow" / "shots" / "seq01" / "seq01_shot01"
        workspace_path.mkdir(parents=True, exist_ok=True)

        plate_base = workspace_path / "publish" / "turnover" / "plate" / "input_plate"

        # Create specific version structure
        version_dir = plate_base / plate_name / version / "exr" / "1920x1080"
        version_dir.mkdir(parents=True, exist_ok=True)
        (
            version_dir
            / f"seq01_shot01_turnover-plate_{plate_name}_aces_{version}.1001.exr"
        ).touch()

        monkeypatch.setattr("config.Config.SHOWS_ROOT", str(shows_root))

        # Test discovery
        result = RawPlateFinder.find_latest_raw_plate(
            str(workspace_path), "seq01_shot01"
        )

        # Should find the specific version
        assert result is not None
        assert expected_version in result

    def test_multiple_resolutions_selection(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test selecting the highest resolution from multiple options."""
        # Create real directory structure
        shows_root = tmp_path / "shows"
        workspace_path = shows_root / "testshow" / "shots" / "seq01" / "seq01_shot01"
        workspace_path.mkdir(parents=True, exist_ok=True)

        plate_base = workspace_path / "publish" / "turnover" / "plate" / "input_plate"

        # Create FG01 v001 with multiple resolutions
        resolutions = ["1920x1080", "2048x1152", "4096x2304", "3840x2160"]
        for resolution in resolutions:
            res_dir = plate_base / "FG01" / "v001" / "exr" / resolution
            res_dir.mkdir(parents=True, exist_ok=True)
            (res_dir / "seq01_shot01_turnover-plate_FG01_aces_v001.1001.exr").touch()

        monkeypatch.setattr("config.Config.SHOWS_ROOT", str(shows_root))

        # Test actual discovery
        result = RawPlateFinder.find_latest_raw_plate(
            str(workspace_path), "seq01_shot01"
        )

        # Should find highest resolution (4096x2304)
        assert result is not None
        assert "4096x2304" in result

    def test_pattern_caching(self, tmp_path: Path) -> None:
        """Test that regex patterns are cached for performance."""
        # Clear cache first
        RawPlateFinder._pattern_cache.clear()

        shot_name = "seq01_shot01"
        plate_name = "FG01"
        version = "v002"

        # First call should create patterns
        patterns1 = RawPlateFinder._get_plate_patterns(shot_name, plate_name, version)
        assert patterns1 is not None
        assert len(RawPlateFinder._pattern_cache) == 1

        # Second call with same params should return cached patterns
        patterns2 = RawPlateFinder._get_plate_patterns(shot_name, plate_name, version)
        assert patterns1 is patterns2  # Same object reference
        assert len(RawPlateFinder._pattern_cache) == 1  # Still only one entry

        # Different params should create new cache entry
        patterns3 = RawPlateFinder._get_plate_patterns(shot_name, "BG01", "v001")
        assert patterns3 is not patterns1
        assert len(RawPlateFinder._pattern_cache) == 2

    def test_find_plate_with_special_characters(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test finding plates with special characters in shot names."""
        # Create workspace with special characters
        shows_root = tmp_path / "shows"
        workspace_path = shows_root / "testshow" / "shots" / "seq01" / "seq01_shot01-fx"
        workspace_path.mkdir(parents=True, exist_ok=True)

        plate_base = workspace_path / "publish" / "turnover" / "plate" / "input_plate"
        fg01_v001 = plate_base / "FG01" / "v001" / "exr" / "1920x1080"
        fg01_v001.mkdir(parents=True, exist_ok=True)
        (fg01_v001 / "seq01_shot01-fx_turnover-plate_FG01_aces_v001.1001.exr").touch()

        monkeypatch.setattr("config.Config.SHOWS_ROOT", str(shows_root))

        # Test actual discovery
        result = RawPlateFinder.find_latest_raw_plate(
            str(workspace_path), "seq01_shot01-fx"
        )

        assert result is not None
        assert "FG01" in result
        assert "seq01_shot01-fx" in result

    def test_empty_version_directory(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test handling version directory with no exr subdirectory."""
        # Create real directory structure
        shows_root = tmp_path / "shows"
        workspace_path = shows_root / "testshow" / "shots" / "seq01" / "seq01_shot01"
        workspace_path.mkdir(parents=True, exist_ok=True)

        plate_base = workspace_path / "publish" / "turnover" / "plate" / "input_plate"

        # Create FG01 with version but no exr directory
        fg01_v001 = plate_base / "FG01" / "v001"
        fg01_v001.mkdir(parents=True, exist_ok=True)
        # No exr subdirectory created

        monkeypatch.setattr("config.Config.SHOWS_ROOT", str(shows_root))

        # Test actual discovery
        result = RawPlateFinder.find_latest_raw_plate(
            str(workspace_path), "seq01_shot01"
        )

        # Should return None when no exr directory found
        assert result is None

    def test_empty_resolution_directory(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test handling resolution directory with no plate files."""
        # Create real directory structure
        shows_root = tmp_path / "shows"
        workspace_path = shows_root / "testshow" / "shots" / "seq01" / "seq01_shot01"
        workspace_path.mkdir(parents=True, exist_ok=True)

        plate_base = workspace_path / "publish" / "turnover" / "plate" / "input_plate"

        # Create FG01 with exr/resolution directory but no files
        fg01_v001 = plate_base / "FG01" / "v001" / "exr" / "1920x1080"
        fg01_v001.mkdir(parents=True, exist_ok=True)
        # No plate files created

        monkeypatch.setattr("config.Config.SHOWS_ROOT", str(shows_root))

        # Test actual discovery
        result = RawPlateFinder.find_latest_raw_plate(
            str(workspace_path), "seq01_shot01"
        )

        # Should return None when no plate files found
        assert result is None

    def test_get_version_from_path(self) -> None:
        """Test extracting version from path using real paths."""
        # Test various path formats
        test_cases = [
            ("/path/to/plate_v002.exr", "v002"),
            (f"{Config.SHOWS_ROOT}/test/shot_v010_final.exr", "v010"),
            ("/data/v001/exr/plate.exr", "v001"),
            ("/path/without/version.exr", None),
        ]

        for path, expected in test_cases:
            result = RawPlateFinder.get_version_from_path(path)
            if expected:
                assert result == expected
            else:
                assert result is None

    def test_pl01_turnover_plate_discovery(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test PL01 turnover plate discovery with film_lin colorspace.

        This test validates the exact production scenario reported by the user:
        /shows/broken_eggs/shots/BRX_170/BRX_170_0100/publish/turnover/plate/input_plate/PL01/v001/exr/4356x2880/BRX_170_0100_turnover-plate_PL01_film_lin_v001.####.exr
        """
        # Create workspace matching production structure
        shows_root = tmp_path / "shows"
        workspace_path = (
            shows_root / "broken_eggs" / "shots" / "BRX_170" / "BRX_170_0100"
        )
        workspace_path.mkdir(parents=True, exist_ok=True)

        # Create exact production plate structure
        plate_base = workspace_path / "publish" / "turnover" / "plate" / "input_plate"
        pl01_v001 = plate_base / "PL01" / "v001" / "exr" / "4356x2880"
        pl01_v001.mkdir(parents=True, exist_ok=True)

        # Create plate files with production naming pattern
        shot_name = "BRX_170_0100"
        plate_file1 = (
            pl01_v001 / f"{shot_name}_turnover-plate_PL01_film_lin_v001.1001.exr"
        )
        plate_file2 = (
            pl01_v001 / f"{shot_name}_turnover-plate_PL01_film_lin_v001.1002.exr"
        )
        plate_file3 = (
            pl01_v001 / f"{shot_name}_turnover-plate_PL01_film_lin_v001.1100.exr"
        )

        plate_file1.touch()
        plate_file2.touch()
        plate_file3.touch()

        monkeypatch.setattr("config.Config.SHOWS_ROOT", str(shows_root))

        # Test PL01 plate discovery
        result = RawPlateFinder.find_latest_raw_plate(str(workspace_path), shot_name)

        # Verify PL01 plate was found
        assert result is not None, "PL01 turnover plate should be discoverable"
        assert "PL01" in result, "Result should contain PL01 plate identifier"
        assert "film_lin" in result, "Result should contain film_lin colorspace"
        assert "v001" in result, "Result should contain version v001"
        assert "4356x2880" in result, "Result should contain resolution"
        assert result.endswith(".####.exr"), "Result should use #### frame pattern"

        # Verify the full expected path structure
        expected_pattern = f"{shot_name}_turnover-plate_PL01_film_lin_v001.####.exr"
        assert expected_pattern in result, (
            f"Result should contain expected pattern: {expected_pattern}"
        )

    def test_pl01_priority_over_bg01(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that PL01 has higher priority than BG01 plates."""
        # Create workspace with both PL01 and BG01 plates
        shows_root = tmp_path / "shows"
        workspace_path = shows_root / "testshow" / "shots" / "seq01" / "seq01_shot01"
        workspace_path.mkdir(parents=True, exist_ok=True)

        plate_base = workspace_path / "publish" / "turnover" / "plate" / "input_plate"

        # Create BG01 plate (lower priority)
        bg01_v001 = plate_base / "BG01" / "v001" / "exr" / "1920x1080"
        bg01_v001.mkdir(parents=True, exist_ok=True)
        (bg01_v001 / "seq01_shot01_turnover-plate_BG01_aces_v001.1001.exr").touch()

        # Create PL01 plate (higher priority)
        pl01_v001 = plate_base / "PL01" / "v001" / "exr" / "4356x2880"
        pl01_v001.mkdir(parents=True, exist_ok=True)
        (pl01_v001 / "seq01_shot01_turnover-plate_PL01_film_lin_v001.1001.exr").touch()

        monkeypatch.setattr("config.Config.SHOWS_ROOT", str(shows_root))

        # Test that PL01 is chosen over BG01
        result = RawPlateFinder.find_latest_raw_plate(
            str(workspace_path), "seq01_shot01"
        )

        assert result is not None
        assert "PL01" in result, (
            "PL01 should be chosen over BG01 due to higher priority"
        )
        assert "BG01" not in result, "BG01 should not be chosen when PL01 is available"
