"""Unit tests for UndistortionFinder module."""

from pathlib import Path
from unittest.mock import patch

import pytest

from undistortion_finder import UndistortionFinder


@pytest.fixture
def mock_workspace_path():
    """Mock workspace path for testing."""
    return "/shows/testshow/shots/seq01/seq01_shot01"


@pytest.fixture
def mock_shot_name():
    """Mock shot name for testing."""
    return "seq01_shot01"


@pytest.fixture
def mock_username():
    """Mock username for testing."""
    return "testuser"


@pytest.fixture
def undistortion_structure(tmp_path, mock_shot_name, mock_username):
    """Create a mock undistortion directory structure for testing."""
    # Create base path
    base_path = (
        tmp_path / "user" / mock_username / "mm" / "3de" / "mm-default" / "exports"
    )

    # Create scene directory with FG01 plate
    scene_dir = base_path / "scene"
    fg01_dir = scene_dir / "FG01" / "nuke_lens_distortion"

    # Create version directories
    v001_dir = fg01_dir / "v001"
    v002_dir = fg01_dir / "v002"
    v001_dir.mkdir(parents=True)
    v002_dir.mkdir(parents=True)

    # Create undistortion .nk files
    nk_file_v001 = v001_dir / f"{mock_shot_name}_FG01_LD_v001.nk"
    nk_file_v001.write_text("# Nuke script v001")

    nk_file_v002 = v002_dir / f"{mock_shot_name}_FG01_LD_v002.nk"
    nk_file_v002.write_text("# Nuke script v002")

    # Create BG01 plate with v001
    bg01_dir = scene_dir / "BG01" / "nuke_lens_distortion"
    bg01_v001_dir = bg01_dir / "v001"
    bg01_v001_dir.mkdir(parents=True)

    bg_nk_file = bg01_v001_dir / f"{mock_shot_name}_BG01_LD_v001.nk"
    bg_nk_file.write_text("# Nuke script BG01")

    # Create sceneMasterSurvey directory with BC01 plate
    scene_master_dir = base_path / "sceneMasterSurvey"
    bc01_dir = scene_master_dir / "BC01" / "nuke_lens_distortion"
    bc01_v001_dir = bc01_dir / "v001"
    bc01_v001_dir.mkdir(parents=True)

    bc_nk_file = bc01_v001_dir / f"{mock_shot_name}_BC01_LD_v001.nk"
    bc_nk_file.write_text("# Nuke script BC01")

    return tmp_path


class TestUndistortionFinder:
    """Test UndistortionFinder class."""

    def test_find_latest_undistortion_success(
        self, undistortion_structure, mock_workspace_path, mock_shot_name, mock_username,
    ):
        """Test successfully finding the latest undistortion file."""
        workspace_path = str(undistortion_structure)

        result = UndistortionFinder.find_latest_undistortion(
            workspace_path, mock_shot_name, mock_username,
        )

        assert result is not None
        assert "FG01" in str(result)  # Should prioritize FG01
        assert "v002" in str(result)  # Should find latest version
        assert result.suffix == ".nk"
        assert mock_shot_name in result.name

    def test_find_latest_undistortion_no_username(
        self, undistortion_structure, mock_shot_name, mock_username,
    ):
        """Test finding undistortion with no username provided (uses default)."""
        workspace_path = str(undistortion_structure)

        with patch("undistortion_finder.Config.DEFAULT_USERNAME", mock_username):
            result = UndistortionFinder.find_latest_undistortion(
                workspace_path, mock_shot_name, None,
            )

            assert result is not None
            assert "FG01" in str(result)

    def test_find_latest_undistortion_no_exports_path(
        self, tmp_path, mock_shot_name, mock_username,
    ):
        """Test when exports path doesn't exist."""
        workspace_path = str(tmp_path / "nonexistent")

        result = UndistortionFinder.find_latest_undistortion(
            workspace_path, mock_shot_name, mock_username,
        )

        assert result is None

    def test_find_latest_undistortion_no_scene_dirs(
        self, tmp_path, mock_shot_name, mock_username,
    ):
        """Test when no scene directories are found."""
        # Create exports path but no scene directories
        base_path = (
            tmp_path / "user" / mock_username / "mm" / "3de" / "mm-default" / "exports"
        )
        base_path.mkdir(parents=True)

        result = UndistortionFinder.find_latest_undistortion(
            str(tmp_path), mock_shot_name, mock_username,
        )

        assert result is None

    def test_find_latest_undistortion_fallback_scene_dir(
        self, tmp_path, mock_shot_name, mock_username,
    ):
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
            str(tmp_path), mock_shot_name, mock_username,
        )

        assert result is not None
        assert result.name == f"{mock_shot_name}_LD.nk"

    def test_find_latest_undistortion_no_plate_dirs(
        self, tmp_path, mock_shot_name, mock_username,
    ):
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
            str(tmp_path), mock_shot_name, mock_username,
        )

        assert result is None

    def test_find_latest_undistortion_no_nuke_lens_dir(
        self, tmp_path, mock_shot_name, mock_username,
    ):
        """Test when plate directory exists but no nuke_lens_distortion directory."""
        base_path = (
            tmp_path / "user" / mock_username / "mm" / "3de" / "mm-default" / "exports"
        )
        scene_dir = base_path / "scene"
        fg01_dir = scene_dir / "FG01"
        fg01_dir.mkdir(parents=True)

        result = UndistortionFinder.find_latest_undistortion(
            str(tmp_path), mock_shot_name, mock_username,
        )

        assert result is None

    def test_find_latest_undistortion_no_version_dirs(
        self, tmp_path, mock_shot_name, mock_username,
    ):
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
            str(tmp_path), mock_shot_name, mock_username,
        )

        assert result is None

    def test_find_latest_undistortion_general_pattern(
        self, tmp_path, mock_shot_name, mock_username,
    ):
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
            str(tmp_path), mock_shot_name, mock_username,
        )

        assert result is not None
        assert result.name == f"{mock_shot_name}_undistortion.nk"

    def test_find_latest_undistortion_any_nk_file(
        self, tmp_path, mock_shot_name, mock_username,
    ):
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
            str(tmp_path), mock_shot_name, mock_username,
        )

        assert result is not None
        assert result.name == "undistortion.nk"

    def test_find_latest_undistortion_plate_priority(
        self, tmp_path, mock_shot_name, mock_username,
    ):
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
            str(tmp_path), mock_shot_name, mock_username,
        )

        # Should find BG01 v003 (highest version trumps plate priority)
        assert result is not None
        assert "BG01" in str(result)
        assert "v003" in str(result)

    def test_find_latest_undistortion_case_insensitive_scene(
        self, tmp_path, mock_shot_name, mock_username,
    ):
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
            str(tmp_path), mock_shot_name, mock_username,
        )

        assert result is not None
        assert "SceneMasterSurvey" in str(result)

    def test_find_latest_undistortion_case_insensitive_plate(
        self, tmp_path, mock_shot_name, mock_username,
    ):
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
            str(tmp_path), mock_shot_name, mock_username,
        )

        assert result is not None
        assert "fg01" in str(result)

    def test_find_latest_undistortion_case_insensitive_version(
        self, tmp_path, mock_shot_name, mock_username,
    ):
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
            str(tmp_path), mock_shot_name, mock_username,
        )

        assert result is not None
        assert "V001" in str(result)

    def test_get_version_from_path(self):
        """Test extracting version from path."""
        test_path = Path("/path/to/v002/undistortion.nk")

        with patch(
            "undistortion_finder.VersionUtils.extract_version_from_path",
            return_value="v002",
        ):
            result = UndistortionFinder.get_version_from_path(test_path)
            assert result == "v002"

    def test_get_version_from_path_none(self):
        """Test extracting version returns None when not found."""
        test_path = Path("/path/to/undistortion.nk")

        with patch(
            "undistortion_finder.VersionUtils.extract_version_from_path",
            return_value=None,
        ):
            result = UndistortionFinder.get_version_from_path(test_path)
            assert result is None

    def test_sort_key_function(self, tmp_path, mock_shot_name, mock_username):
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
            str(tmp_path), mock_shot_name, mock_username,
        )

        # Should get BG01 v003 (highest version)
        assert result is not None
        assert "BG01" in str(result)
        assert "v003" in str(result)

    def test_find_latest_undistortion_subdirectory_search(
        self, tmp_path, mock_shot_name, mock_username,
    ):
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
            str(tmp_path), mock_shot_name, mock_username,
        )

        assert result is not None
        assert "subdir" in str(result)
        assert "nested" in str(result)
    
    def test_find_latest_undistortion_plate_subdirectory(
        self, tmp_path, mock_username,
    ):
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
            str(tmp_path), shot_name, mock_username,
        )
        
        assert result is not None
        assert "v002" in str(result)  # Should find latest version
        assert plate_subdir in str(result)  # Should find file in nested directory
        assert result.name == f"{shot_name}_mm_default_FG01_LD_v002.nk"

    def test_find_latest_undistortion_file_not_found_error(
        self, tmp_path, mock_shot_name, mock_username,
    ):
        """Test that FileNotFoundError is handled gracefully during directory iteration."""
        from unittest.mock import patch
        
        # Create a workspace path
        workspace_path = str(tmp_path)
        
        # Mock iterdir to raise FileNotFoundError
        with patch("pathlib.Path.iterdir") as mock_iterdir:
            mock_iterdir.side_effect = FileNotFoundError("Directory was deleted")
            
            result = UndistortionFinder.find_latest_undistortion(
                workspace_path, mock_shot_name, mock_username,
            )
            
            # Should return None instead of crashing
            assert result is None

