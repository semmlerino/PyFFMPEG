"""Tests for UndistortionFinder."""

from __future__ import annotations

import pytest

# Test doubles for behavior testing (UNIFIED_TESTING_GUIDE)
from undistortion_finder import UndistortionFinder

# This test file follows UNIFIED_TESTING_GUIDE best practices:
# - Test behavior, not implementation
# - Use test doubles instead of mocks
# - Real components where possible
# - Thread-safe testing patterns

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_shot_name() -> str:
    """Mock shot name for testing."""
    return "seq01_shot01"


@pytest.fixture
def mock_username() -> str:
    """Mock username for testing."""
    return "testuser"


@pytest.fixture
def undistortion_structure(make_test_filesystem, mock_shot_name, mock_username):
    """Create undistortion directory structure using TestFileSystem."""
    fs = make_test_filesystem()

    # Create base path structure
    base_path = (
        fs.base_path / "user" / mock_username / "mm" / "3de" / "mm-default" / "exports"
    )

    # Create FG01 plate with multiple versions
    scene_dir = base_path / "scene"

    # FG01 with v001 and v002
    fg01_v001 = scene_dir / "FG01" / "nuke_lens_distortion" / "v001"
    fg01_v002 = scene_dir / "FG01" / "nuke_lens_distortion" / "v002"

    nk_file_v001 = fg01_v001 / f"{mock_shot_name}_FG01_LD_v001.nk"
    fs.create_file(nk_file_v001, "# Nuke script v001\nroot {\n  frame_range 1 100\n}")

    nk_file_v002 = fg01_v002 / f"{mock_shot_name}_FG01_LD_v002.nk"
    fs.create_file(nk_file_v002, "# Nuke script v002\nroot {\n  frame_range 1 100\n}")

    # BG01 plate with v001
    bg01_v001 = scene_dir / "BG01" / "nuke_lens_distortion" / "v001"
    bg_nk_file = bg01_v001 / f"{mock_shot_name}_BG01_LD_v001.nk"
    fs.create_file(bg_nk_file, "# Nuke script BG01\nroot {\n  inputs 0\n}")

    # sceneMasterSurvey directory with BC01 plate
    scene_master_dir = base_path / "sceneMasterSurvey"
    bc01_v001 = scene_master_dir / "BC01" / "nuke_lens_distortion" / "v001"
    bc_nk_file = bc01_v001 / f"{mock_shot_name}_BC01_LD_v001.nk"
    fs.create_file(bc_nk_file, "# Nuke script BC01\nroot {\n  name BC01_distortion\n}")

    return fs.base_path


class TestUndistortionFinder:
    """Test UndistortionFinder class."""

    def test_find_latest_undistortion_success(
        self,
        undistortion_structure,
        mock_shot_name,
        mock_username,
    ) -> None:
        """Test successfully finding the latest undistortion file."""
        workspace_path = str(undistortion_structure)

        result = UndistortionFinder.find_latest_undistortion(
            workspace_path,
            mock_shot_name,
            mock_username,
        )

        assert result is not None
        assert "FG01" in str(result)  # Should prioritize FG01
        assert "v002" in str(result)  # Should find latest version
        assert result.suffix == ".nk"
        assert mock_shot_name in result.name

    def test_find_latest_undistortion_with_explicit_username(
        self,
        undistortion_structure,
        mock_shot_name,
        mock_username,
    ) -> None:
        """Test finding undistortion with explicitly provided username."""
        workspace_path = str(undistortion_structure)

        # Test with explicit username instead of None
        result = UndistortionFinder.find_latest_undistortion(
            workspace_path,
            mock_shot_name,
            mock_username,  # Explicit username
        )

        assert result is not None
        assert "FG01" in str(result)

    def test_find_latest_undistortion_no_exports_path(
        self,
        tmp_path,
        mock_shot_name,
        mock_username,
    ) -> None:
        """Test when exports path doesn't exist."""
        workspace_path = str(tmp_path / "nonexistent")

        result = UndistortionFinder.find_latest_undistortion(
            workspace_path,
            mock_shot_name,
            mock_username,
        )

        assert result is None

    def test_find_latest_undistortion_no_scene_dirs(
        self,
        tmp_path,
        mock_shot_name,
        mock_username,
    ) -> None:
        """Test when no scene directories are found."""
        # Create exports path but no scene directories
        base_path = (
            tmp_path / "user" / mock_username / "mm" / "3de" / "mm-default" / "exports"
        )
        base_path.mkdir(parents=True)

        result = UndistortionFinder.find_latest_undistortion(
            str(tmp_path),
            mock_shot_name,
            mock_username,
        )

        assert result is None

    def test_find_latest_undistortion_fallback_scene_dir(
        self,
        tmp_path,
        mock_shot_name,
        mock_username,
    ) -> None:
        """Test fallback to direct 'scene' directory."""
        # Create exports path with direct scene directory
        base_path = (
            tmp_path / "user" / mock_username / "mm" / "3de" / "mm-default" / "exports"
        )
        scene_dir = base_path / "scene"
        fg01_dir = scene_dir / "FG01" / "nuke_lens_distortion" / "v001"
        fg01_dir.mkdir(parents=True)

        nk_file = fg01_dir / f"{mock_shot_name}_LD.nk"
        nk_file.write_text("# Nuke script")

        result = UndistortionFinder.find_latest_undistortion(
            str(tmp_path),
            mock_shot_name,
            mock_username,
        )

        assert result is not None
        assert result.name == f"{mock_shot_name}_LD.nk"

    def test_find_latest_undistortion_no_plate_dirs(
        self,
        tmp_path,
        mock_shot_name,
        mock_username,
    ) -> None:
        """Test when scene directory exists but has no plate directories."""
        base_path = (
            tmp_path / "user" / mock_username / "mm" / "3de" / "mm-default" / "exports"
        )
        scene_dir = base_path / "scene"
        scene_dir.mkdir(parents=True)

        # Create non-plate directory
        other_dir = scene_dir / "other"
        other_dir.mkdir()

        result = UndistortionFinder.find_latest_undistortion(
            str(tmp_path),
            mock_shot_name,
            mock_username,
        )

        assert result is None

    def test_find_latest_undistortion_no_nuke_lens_dir(
        self,
        tmp_path,
        mock_shot_name,
        mock_username,
    ) -> None:
        """Test when plate directory exists but no nuke_lens_distortion directory."""
        base_path = (
            tmp_path / "user" / mock_username / "mm" / "3de" / "mm-default" / "exports"
        )
        scene_dir = base_path / "scene"
        fg01_dir = scene_dir / "FG01"
        fg01_dir.mkdir(parents=True)

        result = UndistortionFinder.find_latest_undistortion(
            str(tmp_path),
            mock_shot_name,
            mock_username,
        )

        assert result is None

    def test_find_latest_undistortion_no_version_dirs(
        self,
        tmp_path,
        mock_shot_name,
        mock_username,
    ) -> None:
        """Test when nuke_lens_distortion exists but has no version directories."""
        base_path = (
            tmp_path / "user" / mock_username / "mm" / "3de" / "mm-default" / "exports"
        )
        scene_dir = base_path / "scene"
        fg01_dir = scene_dir / "FG01" / "nuke_lens_distortion"
        fg01_dir.mkdir(parents=True)

        # Create non-version directory
        other_dir = fg01_dir / "other"
        other_dir.mkdir()

        result = UndistortionFinder.find_latest_undistortion(
            str(tmp_path),
            mock_shot_name,
            mock_username,
        )

        assert result is None

    def test_find_latest_undistortion_general_pattern(
        self,
        tmp_path,
        mock_shot_name,
        mock_username,
    ) -> None:
        """Test fallback to general pattern when no LD files found."""
        base_path = (
            tmp_path / "user" / mock_username / "mm" / "3de" / "mm-default" / "exports"
        )
        scene_dir = base_path / "scene"
        fg01_dir = scene_dir / "FG01" / "nuke_lens_distortion" / "v001"
        fg01_dir.mkdir(parents=True)

        # Create file without LD in name
        nk_file = fg01_dir / f"{mock_shot_name}_undistortion.nk"
        nk_file.write_text("# Nuke script")

        result = UndistortionFinder.find_latest_undistortion(
            str(tmp_path),
            mock_shot_name,
            mock_username,
        )

        assert result is not None
        assert result.name == f"{mock_shot_name}_undistortion.nk"

    def test_find_latest_undistortion_any_nk_file(
        self,
        tmp_path,
        mock_shot_name,
        mock_username,
    ) -> None:
        """Test fallback to any .nk file when shot name not in filename."""
        base_path = (
            tmp_path / "user" / mock_username / "mm" / "3de" / "mm-default" / "exports"
        )
        scene_dir = base_path / "scene"
        fg01_dir = scene_dir / "FG01" / "nuke_lens_distortion" / "v001"
        fg01_dir.mkdir(parents=True)

        # Create file without shot name
        nk_file = fg01_dir / "undistortion.nk"
        nk_file.write_text("# Nuke script")

        result = UndistortionFinder.find_latest_undistortion(
            str(tmp_path),
            mock_shot_name,
            mock_username,
        )

        assert result is not None
        assert result.name == "undistortion.nk"

    def test_find_latest_undistortion_plate_priority(
        self,
        tmp_path,
        mock_shot_name,
        mock_username,
    ) -> None:
        """Test that FG plates are prioritized over BG and BC plates."""
        base_path = (
            tmp_path / "user" / mock_username / "mm" / "3de" / "mm-default" / "exports"
        )
        scene_dir = base_path / "scene"

        # Create BG01 with newer version (v003)
        bg01_dir = scene_dir / "BG01" / "nuke_lens_distortion" / "v003"
        bg01_dir.mkdir(parents=True)
        bg_nk = bg01_dir / f"{mock_shot_name}_BG01_LD_v003.nk"
        bg_nk.write_text("# BG v003")

        # Create FG01 with older version (v001)
        fg01_dir = scene_dir / "FG01" / "nuke_lens_distortion" / "v001"
        fg01_dir.mkdir(parents=True)
        fg_nk = fg01_dir / f"{mock_shot_name}_FG01_LD_v001.nk"
        fg_nk.write_text("# FG v001")

        # Create BC01 with v002
        bc01_dir = scene_dir / "BC01" / "nuke_lens_distortion" / "v002"
        bc01_dir.mkdir(parents=True)
        bc_nk = bc01_dir / f"{mock_shot_name}_BC01_LD_v002.nk"
        bc_nk.write_text("# BC v002")

        result = UndistortionFinder.find_latest_undistortion(
            str(tmp_path),
            mock_shot_name,
            mock_username,
        )

        # Should find FG01 v001 (plate priority trumps version)
        assert result is not None
        assert "FG01" in str(result)
        assert "v001" in str(result)

    def test_find_latest_undistortion_case_insensitive_scene(
        self,
        tmp_path,
        mock_shot_name,
        mock_username,
    ) -> None:
        """Test that scene directory search is case-insensitive."""
        base_path = (
            tmp_path / "user" / mock_username / "mm" / "3de" / "mm-default" / "exports"
        )

        # Create scene directory with mixed case
        scene_dir = base_path / "SceneMasterSurvey"
        fg01_dir = scene_dir / "FG01" / "nuke_lens_distortion" / "v001"
        fg01_dir.mkdir(parents=True)

        nk_file = fg01_dir / f"{mock_shot_name}_LD.nk"
        nk_file.write_text("# Nuke script")

        result = UndistortionFinder.find_latest_undistortion(
            str(tmp_path),
            mock_shot_name,
            mock_username,
        )

        assert result is not None
        assert "SceneMasterSurvey" in str(result)

    def test_find_latest_undistortion_case_insensitive_plate(
        self,
        tmp_path,
        mock_shot_name,
        mock_username,
    ) -> None:
        """Test that plate directory matching is case-insensitive."""
        base_path = (
            tmp_path / "user" / mock_username / "mm" / "3de" / "mm-default" / "exports"
        )
        scene_dir = base_path / "scene"

        # Create plate directory with lowercase
        fg01_dir = scene_dir / "fg01" / "nuke_lens_distortion" / "v001"
        fg01_dir.mkdir(parents=True)

        nk_file = fg01_dir / f"{mock_shot_name}_LD.nk"
        nk_file.write_text("# Nuke script")

        result = UndistortionFinder.find_latest_undistortion(
            str(tmp_path),
            mock_shot_name,
            mock_username,
        )

        assert result is not None
        assert "fg01" in str(result)

    def test_find_latest_undistortion_case_insensitive_version(
        self,
        tmp_path,
        mock_shot_name,
        mock_username,
    ) -> None:
        """Test that version directory matching is case-insensitive."""
        base_path = (
            tmp_path / "user" / mock_username / "mm" / "3de" / "mm-default" / "exports"
        )
        scene_dir = base_path / "scene"

        # Create version directory with uppercase
        fg01_dir = scene_dir / "FG01" / "nuke_lens_distortion" / "V001"
        fg01_dir.mkdir(parents=True)

        nk_file = fg01_dir / f"{mock_shot_name}_LD.nk"
        nk_file.write_text("# Nuke script")

        result = UndistortionFinder.find_latest_undistortion(
            str(tmp_path),
            mock_shot_name,
            mock_username,
        )

        assert result is not None
        assert "V001" in str(result)

    def test_get_version_from_path(self, tmp_path) -> None:
        """Test extracting version from path with real file structure."""
        # Create real version directory structure
        version_dir = tmp_path / "v002"
        version_dir.mkdir()
        test_path = version_dir / "undistortion.nk"
        test_path.write_text("# Test nuke script")

        result = UndistortionFinder.get_version_from_path(test_path)
        assert result == "v002"

    def test_get_version_from_path_none(self, tmp_path) -> None:
        """Test extracting version returns None when not found."""
        # Create path without version pattern
        test_path = tmp_path / "no_version_here" / "undistortion.nk"
        test_path.parent.mkdir()
        test_path.write_text("# Test nuke script")

        result = UndistortionFinder.get_version_from_path(test_path)
        assert result is None

    def test_sort_key_function(self, tmp_path, mock_shot_name, mock_username) -> None:
        """Test the sort_key function for proper ordering."""
        base_path = (
            tmp_path / "user" / mock_username / "mm" / "3de" / "mm-default" / "exports"
        )
        scene_dir = base_path / "scene"

        # Create multiple files with different versions and plates
        files_to_create = [
            ("FG01", "v001", f"{mock_shot_name}_FG01_v001.nk"),
            ("FG01", "v002", f"{mock_shot_name}_FG01_v002.nk"),
            ("BG01", "v003", f"{mock_shot_name}_BG01_v003.nk"),
            ("BC01", "v002", f"{mock_shot_name}_BC01_v002.nk"),
        ]

        for plate, version, filename in files_to_create:
            file_dir = scene_dir / plate / "nuke_lens_distortion" / version
            file_dir.mkdir(parents=True)
            nk_file = file_dir / filename
            nk_file.write_text(f"# {plate} {version}")

        result = UndistortionFinder.find_latest_undistortion(
            str(tmp_path),
            mock_shot_name,
            mock_username,
        )

        # Should get FG01 v002 (highest priority plate, then highest version within that plate)
        assert result is not None
        assert "FG01" in str(result)
        assert "v002" in str(result)

    def test_find_latest_undistortion_subdirectory_search(
        self,
        tmp_path,
        mock_shot_name,
        mock_username,
    ) -> None:
        """Test that .nk files are found in subdirectories."""
        base_path = (
            tmp_path / "user" / mock_username / "mm" / "3de" / "mm-default" / "exports"
        )
        scene_dir = base_path / "scene"

        # Create nested subdirectory
        fg01_dir = (
            scene_dir / "FG01" / "nuke_lens_distortion" / "v001" / "subdir" / "nested"
        )
        fg01_dir.mkdir(parents=True)

        nk_file = fg01_dir / f"{mock_shot_name}_LD.nk"
        nk_file.write_text("# Nested Nuke script")

        result = UndistortionFinder.find_latest_undistortion(
            str(tmp_path),
            mock_shot_name,
            mock_username,
        )

        assert result is not None
        assert "subdir" in str(result)
        assert "nested" in str(result)

    def test_find_latest_undistortion_plate_subdirectory(
        self,
        tmp_path,
        mock_username,
    ) -> None:
        """Test finding undistortion in plate-named subdirectory (real-world pattern).

        Tests pattern like:
        /shows/jack_ryan/shots/DB_256/DB_256_1200/user/gabriel-h/mm/3de/mm-default/exports/
        scene/FG01/nuke_lens_distortion/v002/GF_256_1200_turnover-plate_FG01_lin_sgamut3cine_v001/
        DB_256_1200_mm_default_FG01_LD_v002.nk
        """
        # Use realistic shot names
        shot_name = "DB_256_1200"

        base_path = (
            tmp_path / "user" / mock_username / "mm" / "3de" / "mm-default" / "exports"
        )
        scene_dir = base_path / "scene"

        # Create realistic nested structure with plate info in subdirectory name
        plate_subdir = "GF_256_1200_turnover-plate_FG01_lin_sgamut3cine_v001"
        fg01_nested = (
            scene_dir / "FG01" / "nuke_lens_distortion" / "v002" / plate_subdir
        )
        fg01_nested.mkdir(parents=True)

        # Create .nk file with realistic naming
        nk_file = fg01_nested / f"{shot_name}_mm_default_FG01_LD_v002.nk"
        nk_file.write_text("# Real-world undistortion script")

        # Also create an older version for comparison
        fg01_v001 = scene_dir / "FG01" / "nuke_lens_distortion" / "v001"
        fg01_v001.mkdir(parents=True)
        old_nk = fg01_v001 / f"{shot_name}_FG01_LD_v001.nk"
        old_nk.write_text("# Older version")

        result = UndistortionFinder.find_latest_undistortion(
            str(tmp_path),
            shot_name,
            mock_username,
        )

        assert result is not None
        assert "v002" in str(result)  # Should find latest version
        assert plate_subdir in str(result)  # Should find file in nested directory
        assert result.name == f"{shot_name}_mm_default_FG01_LD_v002.nk"

    def test_find_latest_undistortion_exact_vfx_structure(
        self,
        tmp_path,
    ) -> None:
        """Test finding undistortion with exact VFX production structure.

        Tests the exact structure from production:
        /shows/jack_ryan/shots/DB_256/DB_256_1200/user/gabriel-h/mm/3de/mm-default/exports/
        scene/FG01/nuke_lens_distortion/v002/GF_256_1200_turnover-plate_FG01_lin_sgamut3cine_v001/
        DB_256_1200_mm_default_FG01_LD_v002.nk
        """
        shot_name = "DB_256_1200"
        username = "gabriel-h"

        # Create exact production structure
        base_path = (
            tmp_path / "user" / username / "mm" / "3de" / "mm-default" / "exports"
        )
        scene_dir = base_path / "scene"

        # Exact nested subdirectory from production
        plate_subdir = "GF_256_1200_turnover-plate_FG01_lin_sgamut3cine_v001"
        full_path = scene_dir / "FG01" / "nuke_lens_distortion" / "v002" / plate_subdir
        full_path.mkdir(parents=True)

        # Create the exact file from production
        nk_file = full_path / "DB_256_1200_mm_default_FG01_LD_v002.nk"
        nk_file.write_text("# Production undistortion script\nroot {\n  inputs 0\n}")

        result = UndistortionFinder.find_latest_undistortion(
            str(tmp_path),
            shot_name,
            username,
        )

        assert result is not None
        assert result.name == "DB_256_1200_mm_default_FG01_LD_v002.nk"
        assert "v002" in str(result)
        assert plate_subdir in str(result)
        assert "FG01" in str(result)

        # Verify the full path structure
        expected_parts = [
            "scene",
            "FG01",
            "nuke_lens_distortion",
            "v002",
            plate_subdir,
            "DB_256_1200_mm_default_FG01_LD_v002.nk",
        ]
        result_path = str(result)
        for part in expected_parts:
            assert part in result_path, f"Missing {part} in {result_path}"

    def test_find_latest_undistortion_nonexistent_directory(
        self,
        tmp_path,
        mock_shot_name,
        mock_username,
    ) -> None:
        """Test handling of non-existent directories gracefully."""
        # Use non-existent workspace path
        nonexistent_path = str(tmp_path / "does_not_exist")

        result = UndistortionFinder.find_latest_undistortion(
            nonexistent_path,
            mock_shot_name,
            mock_username,
        )

        # Should return None instead of crashing
        assert result is None

    def test_find_latest_undistortion_pl01_plate(
        self,
        tmp_path,
    ) -> None:
        """Test finding PL01 undistortion files with production structure.

        Tests the exact structure from the user's production environment:
        /shows/broken_eggs/shots/BRX_170/BRX_170_0100/user/gabriel-h/mm/3de/mm-default/exports/
        scene/PL01/nuke_lens_distortion/v004/BRX_170_0100_turnover-plate_PL01_film_lin_v001/
        BRX_170_0100_mm_default_PL01_LD_v004.nk
        """
        shot_name = "BRX_170_0100"
        username = "gabriel-h"

        # Create exact production structure matching the user's path
        base_path = (
            tmp_path / "user" / username / "mm" / "3de" / "mm-default" / "exports"
        )
        scene_dir = base_path / "scene"

        # Create PL01 plate structure matching production
        plate_subdir = "BRX_170_0100_turnover-plate_PL01_film_lin_v001"
        pl01_path = scene_dir / "PL01" / "nuke_lens_distortion" / "v004" / plate_subdir
        pl01_path.mkdir(parents=True)

        # Create the exact file from production
        nk_file = pl01_path / "BRX_170_0100_mm_default_PL01_LD_v004.nk"
        nk_file.write_text("# PL01 undistortion script\nroot {\n  inputs 0\n}")

        result = UndistortionFinder.find_latest_undistortion(
            str(tmp_path),
            shot_name,
            username,
        )

        # Verify PL01 plate was found
        assert result is not None, "PL01 undistortion file should be discoverable"
        assert result.name == "BRX_170_0100_mm_default_PL01_LD_v004.nk"
        assert "PL01" in str(result), "Result should contain PL01 plate identifier"
        assert "v004" in str(result), "Result should contain version v004"
        assert plate_subdir in str(result), "Result should contain plate subdirectory"

        # Verify the full expected path structure
        expected_parts = [
            "scene",
            "PL01",
            "nuke_lens_distortion",
            "v004",
            plate_subdir,
            "BRX_170_0100_mm_default_PL01_LD_v004.nk",
        ]
        result_path = str(result)
        for part in expected_parts:
            assert part in result_path, f"Missing {part} in {result_path}"

    def test_pl01_priority_over_bg01(
        self,
        tmp_path,
        mock_shot_name,
        mock_username,
    ) -> None:
        """Test that PL01 plates have higher priority than BG01 but lower than FG01."""
        base_path = (
            tmp_path / "user" / mock_username / "mm" / "3de" / "mm-default" / "exports"
        )
        scene_dir = base_path / "scene"

        # Create BG01 with higher version (v005)
        bg01_v005 = scene_dir / "BG01" / "nuke_lens_distortion" / "v005"
        bg01_v005.mkdir(parents=True)
        bg_nk = bg01_v005 / f"{mock_shot_name}_BG01_LD_v005.nk"
        bg_nk.write_text("# BG01 v005")

        # Create PL01 with lower version (v003)
        pl01_v003 = scene_dir / "PL01" / "nuke_lens_distortion" / "v003"
        pl01_v003.mkdir(parents=True)
        pl_nk = pl01_v003 / f"{mock_shot_name}_PL01_LD_v003.nk"
        pl_nk.write_text("# PL01 v003")

        result = UndistortionFinder.find_latest_undistortion(
            str(tmp_path),
            mock_shot_name,
            mock_username,
        )

        # PL01 should be chosen over BG01 despite lower version due to higher priority
        assert result is not None
        assert "PL01" in str(result), (
            "PL01 should be chosen over BG01 due to higher priority"
        )
        assert "v003" in str(result), "Should find PL01 v003"
        assert "BG01" not in str(result), (
            "BG01 should not be chosen when PL01 is available"
        )

    def test_fg01_priority_over_pl01(
        self,
        tmp_path,
        mock_shot_name,
        mock_username,
    ) -> None:
        """Test that FG01 plates have higher priority than PL01."""
        base_path = (
            tmp_path / "user" / mock_username / "mm" / "3de" / "mm-default" / "exports"
        )
        scene_dir = base_path / "scene"

        # Create FG01 with lower version (v001)
        fg01_v001 = scene_dir / "FG01" / "nuke_lens_distortion" / "v001"
        fg01_v001.mkdir(parents=True)
        fg_nk = fg01_v001 / f"{mock_shot_name}_FG01_LD_v001.nk"
        fg_nk.write_text("# FG01 v001")

        # Create PL01 with higher version (v005)
        pl01_v005 = scene_dir / "PL01" / "nuke_lens_distortion" / "v005"
        pl01_v005.mkdir(parents=True)
        pl_nk = pl01_v005 / f"{mock_shot_name}_PL01_LD_v005.nk"
        pl_nk.write_text("# PL01 v005")

        result = UndistortionFinder.find_latest_undistortion(
            str(tmp_path),
            mock_shot_name,
            mock_username,
        )

        # FG01 should be chosen over PL01 despite lower version due to highest priority
        assert result is not None
        assert "FG01" in str(result), (
            "FG01 should be chosen over PL01 due to highest priority"
        )
        assert "v001" in str(result), "Should find FG01 v001"
        assert "PL01" not in str(result), (
            "PL01 should not be chosen when FG01 is available"
        )
