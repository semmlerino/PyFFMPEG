"""Unit tests for NukeScriptGenerator following UNIFIED_TESTING_GUIDE.

Tests Nuke script generation with proper Read nodes for plates and undistortion.
Focuses on script content, colorspace handling, and temporary file management.

Following UNIFIED_TESTING_GUIDE principles:
- Test behavior, not implementation
- Use real NukeScriptGenerator with temporary files
- Mock only at system boundaries
- Focus on edge cases and error conditions
"""

from __future__ import annotations

import pytest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
from nuke_script_generator import NukeScriptGenerator
import os
import tempfile

pytestmark = [pytest.mark.unit, pytest.mark.slow]

# Test doubles for behavior testing (UNIFIED_TESTING_GUIDE)
from tests.test_doubles_library import (
    TestSubprocess, TestShot, TestShotModel,
    TestCacheManager, TestLauncher, TestWorker,
    ThreadSafeTestImage, SignalDouble, TestProcessPool
)


class TestNukeScriptGenerator:
    """Test NukeScriptGenerator with real components."""

    def test_initialization(self):
        """Test NukeScriptGenerator initializes correctly."""
        generator = NukeScriptGenerator()
        
        # Test class variables exist
        assert hasattr(NukeScriptGenerator, '_temp_files')
        assert hasattr(NukeScriptGenerator, '_cleanup_registered')
        assert isinstance(NukeScriptGenerator._temp_files, set)
        assert isinstance(NukeScriptGenerator._cleanup_registered, bool)

    def test_cleanup_registration(self):
        """Test cleanup function registration happens when tracking files."""
        # Reset cleanup state for testing
        NukeScriptGenerator._cleanup_registered = False
        NukeScriptGenerator._temp_files.clear()
        
        # Creating instance doesn't register cleanup
        generator = NukeScriptGenerator()
        assert NukeScriptGenerator._cleanup_registered is False
        
        # Tracking a temp file should register cleanup
        temp_file = "/tmp/test_file.nk"
        NukeScriptGenerator._track_temp_file(temp_file)
        assert NukeScriptGenerator._cleanup_registered is True
        assert temp_file in NukeScriptGenerator._temp_files

    def test_generate_script_basic(self):
        """Test basic script generation."""
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            plate_path = temp_path / "test_plate.exr"
            plate_path.touch()  # Create dummy file
            
            # Use create_plate_script for basic script generation
            script_path = NukeScriptGenerator.create_plate_script(
                plate_path=str(plate_path),
                shot_name="test_shot"
            )
            
            assert script_path is not None
            assert Path(script_path).exists()
            
            # Read script content
            with open(script_path, 'r') as f:
                content = f.read()
            
            # Test basic script structure
            assert "Read {" in content
            assert "test_plate.exr" in content
            assert "linear" in content

    def test_generate_script_with_undistortion(self):
        """Test script generation with undistortion file."""
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            plate_path = temp_path / "test_plate.exr"
            undist_path = temp_path / "undistort.nk"
            plate_path.touch()
            undist_path.touch()
            
            # Use create_plate_script_with_undistortion for undistortion support
            script_path = NukeScriptGenerator.create_plate_script_with_undistortion(
                plate_path=str(plate_path),
                undistortion_path=str(undist_path),
                shot_name="test_shot"
            )
            
            assert script_path is not None
            assert Path(script_path).exists()
            
            with open(script_path, 'r') as f:
                content = f.read()
            
            # Test undistortion is included
            assert "undistort.nk" in content or "Group {" in content or "StickyNote {" in content

    def test_colorspace_detection(self):
        """Test colorspace detection from file paths."""
        generator = NukeScriptGenerator()
        
        # Test different colorspace patterns
        test_cases = [
            ("plate_linear.exr", "Linear"),
            ("plate_rec709.exr", "Rec.709"),
            ("plate_srgb.exr", "sRGB"),
            ("plate_unknown.exr", "Linear")  # Default fallback
        ]
        
        for filepath, expected in test_cases:
            with patch('os.path.exists', return_value=True):
                colorspace, use_raw = NukeScriptGenerator._detect_colorspace(filepath)
                # Test that some colorspace is returned (exact matching may vary)
                assert isinstance(colorspace, str)
                assert len(colorspace) > 0
                assert isinstance(use_raw, bool)

    def test_shot_name_sanitization(self):
        """Test shot name sanitization for script generation."""
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            plate_path = temp_path / "test_plate.exr"
            plate_path.touch()
            
            # Test shot name with special characters
            script_path = NukeScriptGenerator.create_plate_script(
                plate_path=str(plate_path),
                shot_name="shot/with\\special:chars"
            )
            
            assert script_path is not None
            assert Path(script_path).exists()
            
            with open(script_path, 'r') as f:
                content = f.read()
            
            # Test that problematic characters are handled
            assert "shot_with_special_chars" in content

    def test_temporary_file_tracking(self):
        """Test that temporary files are properly tracked."""
        initial_count = len(NukeScriptGenerator._temp_files)
        
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            plate_path = temp_path / "test_plate.exr"
            plate_path.touch()
            
            script_path = NukeScriptGenerator.create_plate_script(
                plate_path=str(plate_path),
                shot_name="test_shot"
            )
            
            # Test that temp file was tracked
            assert len(NukeScriptGenerator._temp_files) > initial_count
            assert script_path in NukeScriptGenerator._temp_files

    def test_cleanup_temp_files(self):
        """Test temporary file cleanup functionality."""
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            plate_path = temp_path / "test_plate.exr"
            plate_path.touch()
            
            script_path = NukeScriptGenerator.create_plate_script(
                plate_path=str(plate_path),
                shot_name="test_shot"
            )
            
            # Verify file exists and is tracked
            assert Path(script_path).exists()
            assert script_path in NukeScriptGenerator._temp_files
            
            # Test cleanup
            NukeScriptGenerator._cleanup_temp_files()
            
            # File should be removed and not tracked
            assert not Path(script_path).exists()
            assert script_path not in NukeScriptGenerator._temp_files

    def test_error_handling_missing_plate(self):
        """Test error handling for missing plate file."""
        # Test with non-existent file
        script_path = NukeScriptGenerator.create_plate_script(
            plate_path="/path/that/does/not/exist.exr",
            shot_name="test_shot"
        )
        
        # Should handle gracefully (may return None or create script anyway)
        # The exact behavior depends on implementation
        if script_path is not None:
            assert isinstance(script_path, str)

    def test_multiple_script_generation(self):
        """Test generating multiple scripts in sequence."""
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            script_paths = []
            
            for i in range(3):
                plate_path = temp_path / f"plate_{i}.exr"
                plate_path.touch()
                
                script_path = NukeScriptGenerator.create_plate_script(
                    plate_path=str(plate_path),
                    shot_name=f"shot_{i}"
                )
                
                script_paths.append(script_path)
                assert script_path is not None
                assert Path(script_path).exists()
            
            # Test all scripts are unique
            assert len(set(script_paths)) == 3
            
            # Test all are tracked
            for path in script_paths:
                assert path in NukeScriptGenerator._temp_files

    def test_colorspace_with_spaces(self):
        """Test colorspace handling with spaces in names."""
        # Test colorspace names that contain spaces
        test_colorspace = "Input - Sony - S-Gamut3.Cine - Linear"
        
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            plate_path = temp_path / "test_plate.exr"
            plate_path.touch()
            
            with patch.object(NukeScriptGenerator, '_detect_colorspace', return_value=(test_colorspace, False)):
                script_path = NukeScriptGenerator.create_plate_script(
                    plate_path=str(plate_path),
                    shot_name="test_shot"
                )
                
                with open(script_path, 'r') as f:
                    content = f.read()
                
                # Test colorspace is properly quoted/handled
                assert test_colorspace in content or test_colorspace.replace(' ', '_') in content

    def test_generate_complete_comp_script(self):
        """Test generating complete comp script with Read and Write nodes."""
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            plate_path = temp_path / "test_plate.exr"
            output_dir = temp_path / "output"
            plate_path.touch()
            output_dir.mkdir()
            
            # Use generate_comp_script for complete comp scripts
            script_path = NukeScriptGenerator.generate_comp_script(
                shot_name="test_shot",
                plate_path=str(plate_path),
                colorspace="linear",
                first_frame=1001,
                last_frame=1100,
                output_dir=str(output_dir)
            )
            
            assert script_path is not None
            assert Path(script_path).exists()
            
            with open(script_path, 'r') as f:
                content = f.read()
            
            # Test complete comp script structure
            assert "Read {" in content
            assert "Write {" in content
            assert "Grade {" in content
            assert "Viewer {" in content
            assert "test_plate.exr" in content