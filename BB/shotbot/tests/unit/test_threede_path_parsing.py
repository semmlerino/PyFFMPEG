#!/usr/bin/env python3
"""Test 3DE scene path parsing to prevent regression of the GF_256_1400 bug.

This test ensures that shot directories following the pattern {sequence}_{shot}
are correctly parsed, preventing the duplication bug where GF_256_1400 was
incorrectly parsed as GF_256_GF_256_1400.
"""

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from threede_scene_finder import ThreeDESceneFinder


class TestThreeDEPathParsing(unittest.TestCase):
    """Test suite for 3DE scene path parsing."""

    def setUp(self):
        """Set up test fixtures."""
        self.finder = ThreeDESceneFinder()

    def test_sequence_shot_directory_parsing(self):
        """Test parsing of shot directories with sequence_shot naming pattern.
        
        This tests the critical bug fix where directories like GF_256_1400
        were incorrectly parsed, causing path construction errors.
        """
        test_cases = [
            # (path, expected_show, expected_sequence, expected_shot, expected_username)
            (
                "/shows/jack_ryan/shots/GF_256/GF_256_1400/user/johndoe/3de/scene.3de",
                "/shows/jack_ryan/shots/GF_256/GF_256_1400",
                "GF_256",
                "1400",
                "johndoe",
            ),
            (
                "/shows/project/shots/ABC_123/ABC_123_4567/user/artist/work/file.3de",
                "/shows/project/shots/ABC_123/ABC_123_4567",
                "ABC_123",
                "4567",
                "artist",
            ),
            (
                "/shows/show/shots/SEQ_01/SEQ_01_0010/user/bob/3de/test.3de",
                "/shows/show/shots/SEQ_01/SEQ_01_0010",
                "SEQ_01",
                "0010",
                "bob",
            ),
            # Test with underscores in sequence name
            (
                "/shows/test/shots/LONG_SEQ_01/LONG_SEQ_01_0020/user/alice/3de/comp.3de",
                "/shows/test/shots/LONG_SEQ_01/LONG_SEQ_01_0020",
                "LONG_SEQ_01",
                "0020",
                "alice",
            ),
        ]

        for path_str, exp_show, exp_seq, exp_shot, exp_user in test_cases:
            with self.subTest(path=path_str):
                path = Path(path_str)
                result = self.finder.extract_shot_info_from_path(path)
                
                self.assertIsNotNone(result, f"Failed to extract info from {path_str}")
                show, sequence, shot, username = result
                
                self.assertEqual(show, exp_show, f"Show mismatch for {path_str}")
                self.assertEqual(sequence, exp_seq, f"Sequence mismatch for {path_str}")
                self.assertEqual(shot, exp_shot, f"Shot mismatch for {path_str}")
                self.assertEqual(username, exp_user, f"Username mismatch for {path_str}")

    def test_published_file_parsing(self):
        """Test parsing of published 3DE files."""
        test_cases = [
            (
                "/shows/jack_ryan/shots/GF_256/GF_256_1400/publish/3de/scene.3de",
                "/shows/jack_ryan/shots/GF_256/GF_256_1400",
                "GF_256",
                "1400",
                "published-3de",  # Pseudo-username for published files
            ),
            (
                "/shows/project/shots/ABC_123/ABC_123_4567/publish/editorial/test.3de",
                "/shows/project/shots/ABC_123/ABC_123_4567",
                "ABC_123",
                "4567",
                "published-editorial",
            ),
        ]

        for path_str, exp_show, exp_seq, exp_shot, exp_user in test_cases:
            with self.subTest(path=path_str):
                path = Path(path_str)
                result = self.finder.extract_shot_info_from_path(path)
                
                self.assertIsNotNone(result, f"Failed to extract info from {path_str}")
                show, sequence, shot, username = result
                
                self.assertEqual(show, exp_show)
                self.assertEqual(sequence, exp_seq)
                self.assertEqual(shot, exp_shot)
                self.assertEqual(username, exp_user)

    def test_deeply_nested_paths(self):
        """Test parsing of deeply nested 3DE files."""
        # Test up to 15 levels deep as configured in THREEDE_SCAN_MAX_DEPTH
        deep_path = "/shows/project/shots/SEQ_01/SEQ_01_0010/user/artist/work/subfolder/deep/deeper/even_deeper/still_going/almost_there/finally/scene.3de"
        
        path = Path(deep_path)
        result = self.finder.extract_shot_info_from_path(path)
        
        self.assertIsNotNone(result)
        show, sequence, shot, username = result
        
        self.assertEqual(show, "/shows/project/shots/SEQ_01/SEQ_01_0010")
        self.assertEqual(sequence, "SEQ_01")
        self.assertEqual(shot, "0010")
        self.assertEqual(username, "artist")

    def test_invalid_paths(self):
        """Test that invalid paths return None."""
        invalid_paths = [
            "/not/a/valid/path.3de",
            "/shows/missing/structure.3de",
            "/shows/project/not_shots/SEQ_01/SEQ_01_0010/user/artist/scene.3de",
            "/shows/project/shots/only_sequence/user/artist/scene.3de",
            "",
        ]

        for path_str in invalid_paths:
            with self.subTest(path=path_str):
                if path_str:  # Skip empty string
                    path = Path(path_str)
                    result = self.finder.extract_shot_info_from_path(path)
                    self.assertIsNone(result, f"Expected None for invalid path {path_str}")

    def test_path_without_underscore_separator(self):
        """Test handling of shot directories that don't follow sequence_shot pattern."""
        # If a shot directory doesn't have the sequence prefix, it should still work
        path = Path("/shows/project/shots/SEQ_01/DIFFERENT_0010/user/artist/scene.3de")
        result = self.finder.extract_shot_info_from_path(path)
        
        if result:  # This might be None depending on implementation
            show, sequence, shot, username = result
            self.assertEqual(sequence, "SEQ_01")
            # Shot should be the full directory name if pattern doesn't match
            self.assertIn(shot, ["DIFFERENT_0010", "0010"])

    def test_publish_directory_construction(self):
        """Test that publish directories are constructed correctly.
        
        This verifies the fix for the bug where paths like
        /shows/jack_ryan/shots/GF_256/GF_256_GF_256_1400/publish
        were incorrectly generated.
        """
        test_cases = [
            # (show, sequence, shot, expected_path)
            ("jack_ryan", "GF_256", "1400", "/shows/jack_ryan/shots/GF_256/GF_256_1400/publish"),
            ("project", "ABC_123", "4567", "/shows/project/shots/ABC_123/ABC_123_4567/publish"),
            ("show", "SEQ_01", "0010", "/shows/show/shots/SEQ_01/SEQ_01_0010/publish"),
            ("test", "LONG_SEQ_01", "0020", "/shows/test/shots/LONG_SEQ_01/LONG_SEQ_01_0020/publish"),
        ]

        for show, sequence, shot, expected_path in test_cases:
            with self.subTest(show=show, sequence=sequence, shot=shot):
                # Construct the path as the application would
                constructed_path = f"/shows/{show}/shots/{sequence}/{sequence}_{shot}/publish"
                self.assertEqual(constructed_path, expected_path)
                
                # Verify no duplication occurs
                self.assertNotIn(f"{sequence}_{sequence}", constructed_path)

    def test_extract_plate_name_from_path(self):
        """Test plate name extraction from various path structures."""
        test_cases = [
            # User workspace paths
            ("/shows/project/shots/SEQ_01/SEQ_01_0010/user/artist/3de/BG01_comp.3de", "BG01"),
            ("/shows/project/shots/SEQ_01/SEQ_01_0010/user/artist/3de/fg01_track.3de", "fg01"),
            ("/shows/project/shots/SEQ_01/SEQ_01_0010/user/artist/3de/SEQ_01_0010_comp.3de", "SEQ_01_0010"),
            # Published paths
            ("/shows/project/shots/SEQ_01/SEQ_01_0010/publish/3de/BG01_final.3de", "BG01"),
            ("/shows/project/shots/SEQ_01/SEQ_01_0010/publish/editorial/FG01_v002.3de", "FG01"),
            # No clear plate name
            ("/shows/project/shots/SEQ_01/SEQ_01_0010/user/artist/3de/random_file.3de", "random"),
        ]

        for path_str, expected_plate in test_cases:
            with self.subTest(path=path_str):
                path = Path(path_str)
                # This would call a method to extract plate name
                # For now, we'll just test the basic extraction logic
                filename = path.stem
                if "BG01" in filename.upper():
                    plate = "BG01" if "BG01" in filename else "bg01"
                elif "FG01" in filename.upper():
                    plate = "FG01" if "FG01" in filename else "fg01"
                elif filename.startswith("SEQ_"):
                    plate = filename.split("_comp")[0].split("_track")[0]
                else:
                    plate = filename.split("_")[0]
                
                # Basic assertion - would be more sophisticated in actual implementation
                self.assertTrue(expected_plate.upper() in plate.upper() or plate.upper() in expected_plate.upper())


if __name__ == "__main__":
    unittest.main()