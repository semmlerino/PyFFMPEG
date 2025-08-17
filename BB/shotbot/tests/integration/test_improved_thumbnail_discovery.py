"""Test improved thumbnail discovery with flexible directory structures."""

import os
from pathlib import Path
import pytest
import tempfile
from unittest.mock import patch

from utils import PathUtils
from config import Config


class TestImprovedThumbnailDiscovery:
    """Test thumbnail discovery improvements for handling various directory structures."""

    def test_find_turnover_plate_without_input_plate(self, tmp_path):
        """Test finding turnover plates when input_plate directory doesn't exist."""
        # Create structure without input_plate subdirectory
        # /shows/testshow/shots/seq01/seq01_shot01/publish/turnover/plate/FG01/v001/exr/4312x2304/
        shows_root = tmp_path / "shows"
        plate_path = (
            shows_root
            / "testshow"
            / "shots"
            / "seq01"
            / "seq01_shot01"
            / "publish"
            / "turnover"
            / "plate"
            / "FG01"
            / "v001"
            / "exr"
            / "4312x2304"
        )
        plate_path.mkdir(parents=True)
        
        # Create a test EXR file
        test_file = plate_path / "seq01_shot01_turnover-plate_FG01_v001.1001.exr"
        test_file.touch()
        
        # Test that it finds the plate
        with patch.object(Config, "SHOWS_ROOT", str(shows_root)):
            result = PathUtils.find_turnover_plate_thumbnail(
                str(shows_root), "testshow", "seq01", "shot01"
            )
            
        assert result is not None
        assert result == test_file
        assert "FG01" in str(result)

    def test_find_turnover_plate_with_input_plate(self, tmp_path):
        """Test finding turnover plates with traditional input_plate directory."""
        # Create structure with input_plate subdirectory
        # /shows/testshow/shots/seq01/seq01_shot01/publish/turnover/plate/input_plate/BG01/v001/exr/1920x1080/
        shows_root = tmp_path / "shows"
        plate_path = (
            shows_root
            / "testshow"
            / "shots"
            / "seq01"
            / "seq01_shot01"
            / "publish"
            / "turnover"
            / "plate"
            / "input_plate"
            / "BG01"
            / "v001"
            / "exr"
            / "1920x1080"
        )
        plate_path.mkdir(parents=True)
        
        # Create a test EXR file
        test_file = plate_path / "seq01_shot01_turnover-plate_BG01_v001.1001.exr"
        test_file.touch()
        
        # Test that it finds the plate
        with patch.object(Config, "SHOWS_ROOT", str(shows_root)):
            result = PathUtils.find_turnover_plate_thumbnail(
                str(shows_root), "testshow", "seq01", "shot01"
            )
            
        assert result is not None
        assert result == test_file
        assert "BG01" in str(result)

    def test_find_any_publish_thumbnail_without_publish_dir(self, tmp_path):
        """Test finding EXR files when publish directory doesn't exist."""
        # Create structure without publish subdirectory, EXR directly in shot
        # /shows/testshow/shots/seq01/seq01_shot01/some_path/test.1001.exr
        shows_root = tmp_path / "shows"
        shot_path = (
            shows_root
            / "testshow"
            / "shots"
            / "seq01"
            / "seq01_shot01"
            / "some_path"
        )
        shot_path.mkdir(parents=True)
        
        # Create a test EXR file
        test_file = shot_path / "test.1001.exr"
        test_file.touch()
        
        # Test that it finds the file even without publish directory
        with patch.object(Config, "SHOWS_ROOT", str(shows_root)):
            result = PathUtils.find_any_publish_thumbnail(
                str(shows_root), "testshow", "seq01", "shot01", max_depth=3
            )
            
        assert result is not None
        assert result == test_file
        assert "1001" in result.name

    def test_plate_priority_order(self, tmp_path):
        """Test that FG plates are preferred over BG plates."""
        # Create structure with both FG and BG plates
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
        
        # Create BG01 plate
        bg_path = base_path / "BG01" / "v001" / "exr" / "1920x1080"
        bg_path.mkdir(parents=True)
        bg_file = bg_path / "shot01_BG01.1001.exr"
        bg_file.touch()
        
        # Create FG01 plate
        fg_path = base_path / "FG01" / "v001" / "exr" / "1920x1080"
        fg_path.mkdir(parents=True)
        fg_file = fg_path / "shot01_FG01.1001.exr"
        fg_file.touch()
        
        # Test that FG01 is preferred
        with patch.object(Config, "SHOWS_ROOT", str(shows_root)):
            result = PathUtils.find_turnover_plate_thumbnail(
                str(shows_root), "testshow", "seq01", "shot01"
            )
            
        assert result is not None
        assert result == fg_file
        assert "FG01" in str(result)

    def test_deeply_nested_exr_discovery(self, tmp_path):
        """Test finding deeply nested EXR files."""
        # Create a very deeply nested structure
        shows_root = tmp_path / "shows"
        deep_path = (
            shows_root
            / "testshow"
            / "shots"
            / "seq01"
            / "seq01_shot01"
            / "publish"
            / "level1"
            / "level2"
            / "level3"
            / "level4"
            / "level5"
        )
        deep_path.mkdir(parents=True)
        
        # Create a test EXR file
        test_file = deep_path / "deep.1001.exr"
        test_file.touch()
        
        # Test that it finds the deeply nested file
        with patch.object(Config, "SHOWS_ROOT", str(shows_root)):
            result = PathUtils.find_any_publish_thumbnail(
                str(shows_root), "testshow", "seq01", "shot01", max_depth=6
            )
            
        assert result is not None
        assert result == test_file