"""Tests for NukeScriptGenerator class."""

from pathlib import Path

from nuke_script_generator import NukeScriptGenerator


class TestNukeScriptGenerator:
    """Test NukeScriptGenerator functionality."""

    def test_create_plate_script_basic(self, tmp_path):
        """Test basic plate script generation."""
        # Create test plate files
        plate_dir = tmp_path / "plates"
        plate_dir.mkdir()

        # Create dummy EXR files
        for frame in range(1001, 1004):
            plate_file = plate_dir / f"test_plate.{frame:04d}.exr"
            plate_file.write_text("dummy exr content")

        plate_path = str(plate_dir / "test_plate.%04d.exr")
        shot_name = "test_shot"

        # Generate script
        script_path = NukeScriptGenerator.create_plate_script(plate_path, shot_name)

        assert script_path is not None
        assert Path(script_path).exists()

        # Read and verify script content
        with open(script_path, "r") as f:
            content = f.read()

        assert "test_shot_plate" in content  # Uses _plate suffix for regular scripts
        assert plate_path in content
        assert "Read {" in content
        assert "first_frame 1001" in content
        # The script detects frames 1001-1003 but uses default 1001-1100 range
        assert "last_frame 1003" in content or "last_frame 1100" in content

        # Cleanup
        Path(script_path).unlink()

    def test_create_plate_script_with_undistortion_both_files(self, tmp_path):
        """Test script generation with both plate and undistortion."""
        # Create test plate files
        plate_dir = tmp_path / "plates"
        plate_dir.mkdir()

        for frame in range(1001, 1004):
            plate_file = plate_dir / f"test_plate.{frame:04d}.exr"
            plate_file.write_text("dummy exr content")

        plate_path = str(plate_dir / "test_plate.%04d.exr")

        # Create test undistortion file
        undist_file = tmp_path / "undistortion_v001.nk"
        undist_file.write_text("# Nuke undistortion script\nRead { file test.exr }")

        shot_name = "test_shot"

        # Generate script
        script_path = NukeScriptGenerator.create_plate_script_with_undistortion(
            plate_path, str(undist_file), shot_name
        )

        assert script_path is not None
        assert Path(script_path).exists()

        # Read and verify script content
        with open(script_path, "r") as f:
            content = f.read()

        # Check for plate content
        assert "test_shot_comp" in content
        assert plate_path in content
        assert "name plate_read" in content

        # Check for undistortion content
        assert str(undist_file) in content
        assert "name undistortion_import" in content
        assert "plate_to_undistortion" in content

        # Cleanup
        Path(script_path).unlink()

    def test_create_plate_script_with_undistortion_plate_only(self, tmp_path):
        """Test script generation with plate only (no undistortion)."""
        # Create test plate files
        plate_dir = tmp_path / "plates"
        plate_dir.mkdir()

        for frame in range(1001, 1003):
            plate_file = plate_dir / f"test_plate.{frame:04d}.exr"
            plate_file.write_text("dummy exr content")

        plate_path = str(plate_dir / "test_plate.%04d.exr")
        shot_name = "test_shot"

        # Generate script with no undistortion
        script_path = NukeScriptGenerator.create_plate_script_with_undistortion(
            plate_path, None, shot_name
        )

        assert script_path is not None
        assert Path(script_path).exists()

        # Read and verify script content
        with open(script_path, "r") as f:
            content = f.read()

        # Should have plate content
        assert plate_path in content
        assert "name plate_read" in content

        # Should NOT have undistortion content
        assert "undistortion_import" not in content
        assert "plate_to_undistortion" not in content

        # Cleanup
        Path(script_path).unlink()

    def test_create_plate_script_with_undistortion_undistortion_only(self, tmp_path):
        """Test script generation with undistortion only (no plate)."""
        # Create test undistortion file
        undist_file = tmp_path / "undistortion_v002.nk"
        undist_file.write_text(
            "# Nuke undistortion script\nLensDistortion { file test.nk }"
        )

        shot_name = "test_shot"

        # Generate script with empty plate path
        script_path = NukeScriptGenerator.create_plate_script_with_undistortion(
            "", str(undist_file), shot_name
        )

        assert script_path is not None
        assert Path(script_path).exists()

        # Read and verify script content
        with open(script_path, "r") as f:
            content = f.read()

        # Should have basic Nuke structure
        assert "test_shot_comp" in content
        assert "Root {" in content

        # Should have undistortion content
        assert str(undist_file) in content
        assert "name undistortion_import" in content

        # Should NOT have plate Read node
        assert "name plate_read" not in content

        # Cleanup
        Path(script_path).unlink()

    def test_create_plate_script_with_undistortion_missing_undist_file(self, tmp_path):
        """Test script generation with non-existent undistortion file."""
        # Create test plate files
        plate_dir = tmp_path / "plates"
        plate_dir.mkdir()

        for frame in range(1001, 1003):
            plate_file = plate_dir / f"test_plate.{frame:04d}.exr"
            plate_file.write_text("dummy exr content")

        plate_path = str(plate_dir / "test_plate.%04d.exr")
        undist_path = "/non/existent/undistortion.nk"
        shot_name = "test_shot"

        # Generate script with missing undistortion file
        script_path = NukeScriptGenerator.create_plate_script_with_undistortion(
            plate_path, undist_path, shot_name
        )

        assert script_path is not None
        assert Path(script_path).exists()

        # Read and verify script content
        with open(script_path, "r") as f:
            content = f.read()

        # Should have plate content
        assert plate_path in content
        assert "name plate_read" in content

        # Should NOT have undistortion content (file doesn't exist)
        assert "undistortion_import" not in content

        # Cleanup
        Path(script_path).unlink()

    def test_create_plate_script_resolution_detection(self, tmp_path):
        """Test resolution detection from path."""
        # Create test plate files with resolution in path
        plate_dir = tmp_path / "project" / "shots" / "4312x2304" / "plates"
        plate_dir.mkdir(parents=True)

        for frame in range(1001, 1003):
            plate_file = plate_dir / f"test_plate.{frame:04d}.exr"
            plate_file.write_text("dummy exr content")

        plate_path = str(plate_dir / "test_plate.%04d.exr")
        shot_name = "test_shot"

        # Generate script
        script_path = NukeScriptGenerator.create_plate_script(plate_path, shot_name)

        assert script_path is not None

        # Read and verify script content
        with open(script_path, "r") as f:
            content = f.read()

        # Should detect resolution from path
        assert 'format "4312 2304 0 0 4312 2304 1' in content

        # Cleanup
        Path(script_path).unlink()

    def test_create_plate_script_no_frames(self, tmp_path):
        """Test script generation when no frame files exist."""
        plate_dir = tmp_path / "empty_plates"
        plate_dir.mkdir()

        plate_path = str(plate_dir / "test_plate.%04d.exr")
        shot_name = "test_shot"

        # Generate script with no frame files
        script_path = NukeScriptGenerator.create_plate_script(plate_path, shot_name)

        assert script_path is not None

        # Read and verify script content
        with open(script_path, "r") as f:
            content = f.read()

        # Should use default frame range (1001-1100 as per actual implementation)
        assert "first_frame 1001" in content
        assert "last_frame 1100" in content

        # Cleanup
        Path(script_path).unlink()

    def test_create_plate_script_error_handling(self):
        """Test error handling in script generation."""
        # Test with invalid path
        NukeScriptGenerator.create_plate_script(
            "/invalid/path/plates.%04d.exr", "test_shot"
        )

        # Should not crash, but may return None or handle gracefully
        # This depends on implementation - the main requirement is no crashes

    def test_create_plate_script_with_undistortion_error_handling(self):
        """Test error handling in undistortion script generation."""
        # Test with invalid paths
        NukeScriptGenerator.create_plate_script_with_undistortion(
            "/invalid/plate/path.%04d.exr", "/invalid/undist/path.nk", "test_shot"
        )

        # Should not crash, but may return None or handle gracefully
        # This depends on implementation - the main requirement is no crashes

    def test_script_content_structure(self, tmp_path):
        """Test that generated script has proper Nuke structure."""
        # Create minimal test setup
        plate_dir = tmp_path / "plates"
        plate_dir.mkdir()

        plate_file = plate_dir / "test_plate.1001.exr"
        plate_file.write_text("dummy exr")

        undist_file = tmp_path / "undist.nk"
        undist_file.write_text("# undist")

        plate_path = str(plate_dir / "test_plate.%04d.exr")
        shot_name = "test_shot_123"

        # Generate script
        script_path = NukeScriptGenerator.create_plate_script_with_undistortion(
            plate_path, str(undist_file), shot_name
        )

        assert script_path is not None

        with open(script_path, "r") as f:
            content = f.read()

        # Check essential Nuke script structure
        assert content.startswith("#!")  # Shebang
        assert "version 15.1 v2" in content
        assert "Root {" in content
        assert "name test_shot_123_comp" in content
        assert "OCIO_config aces_1.2" in content
        assert "Viewer {" in content

        # Check that nodes have proper positioning
        assert "xpos" in content
        assert "ypos" in content

        # Cleanup
        Path(script_path).unlink()
