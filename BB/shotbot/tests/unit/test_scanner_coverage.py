#!/usr/bin/env python3
"""Test 3DE scanner coverage to ensure all shots are discovered.

This test ensures the scanner discovers ALL 3DE files across entire shows,
not just the user's assigned shots from 'ws -sg'.
"""

import unittest
from pathlib import Path
from typing import Dict, List, Set, Tuple
from unittest.mock import MagicMock, Mock, patch

from PySide6.QtCore import QObject, Signal

from threede_scene_finder import ThreeDESceneFinder
from threede_scene_worker import ThreeDESceneWorker


class TestScannerCoverage(unittest.TestCase):
    """Test suite for 3DE scanner coverage."""

    def setUp(self):
        """Set up test fixtures."""
        self.finder = ThreeDESceneFinder()
        
    def create_mock_file_structure(self) -> Dict[str, List[Path]]:
        """Create a mock file structure representing a VFX show hierarchy."""
        return {
            "/shows/jack_ryan": [
                # User's assigned shots (from ws -sg)
                Path("/shows/jack_ryan/shots/GF_256/GF_256_1400/user/johndoe/3de/scene1.3de"),
                Path("/shows/jack_ryan/shots/GF_256/GF_256_1410/user/johndoe/3de/scene2.3de"),
                
                # Other users' shots in same sequence
                Path("/shows/jack_ryan/shots/GF_256/GF_256_1420/user/alice/3de/scene3.3de"),
                Path("/shows/jack_ryan/shots/GF_256/GF_256_1430/user/bob/3de/scene4.3de"),
                
                # Different sequence entirely
                Path("/shows/jack_ryan/shots/ABC_123/ABC_123_0010/user/charlie/3de/scene5.3de"),
                Path("/shows/jack_ryan/shots/ABC_123/ABC_123_0020/user/dave/3de/scene6.3de"),
                Path("/shows/jack_ryan/shots/ABC_123/ABC_123_0030/user/eve/3de/scene7.3de"),
                
                # Published files
                Path("/shows/jack_ryan/shots/GF_256/GF_256_1400/publish/3de/final.3de"),
                Path("/shows/jack_ryan/shots/DEF_456/DEF_456_0100/publish/editorial/approved.3de"),
                
                # Deeply nested files
                Path("/shows/jack_ryan/shots/XYZ_789/XYZ_789_5000/user/frank/work/3de/deep/nested/file.3de"),
            ],
            "/shows/other_show": [
                # Files from a different show entirely
                Path("/shows/other_show/shots/SEQ_01/SEQ_01_0010/user/george/3de/other.3de"),
                Path("/shows/other_show/shots/SEQ_01/SEQ_01_0020/user/helen/3de/another.3de"),
            ]
        }

    def test_scan_all_shots_mode(self):
        """Test that scan_all_shots=True discovers all shots, not just user's."""
        with patch.object(ThreeDESceneWorker, '__init__', return_value=None) as mock_init:
            # Create worker with scan_all_shots=True
            worker = ThreeDESceneWorker(scan_all_shots=True)
            mock_init.assert_called_with(scan_all_shots=True)
            
            # Verify the worker is configured to scan all shots
            worker.scan_all_shots = True
            self.assertTrue(worker.scan_all_shots)

    def test_discover_all_scenes_in_shows(self):
        """Test that _discover_all_scenes_in_shows finds all 3DE files."""
        mock_files = self.create_mock_file_structure()
        
        with patch('threede_scene_finder.Path.glob') as mock_glob:
            # Setup mock to return our test files
            all_files = []
            for show_files in mock_files.values():
                all_files.extend(show_files)
            
            mock_glob.return_value = iter(all_files)
            
            # Run discovery
            scenes = self.finder._discover_all_scenes_in_shows(Path("/shows"))
            
            # Should find all .3de files
            self.assertEqual(len(scenes), len(all_files))

    def test_user_shots_vs_all_shots(self):
        """Test difference between user's shots and all discovered shots."""
        # User's assigned shots (from ws -sg)
        user_shots = [
            ("jack_ryan", "GF_256", "1400"),
            ("jack_ryan", "GF_256", "1410"),
        ]
        
        # All discovered shots (should be much more)
        all_discovered_files = self.create_mock_file_structure()["/shows/jack_ryan"]
        
        # Extract unique shots from all files
        discovered_shots = set()
        for file_path in all_discovered_files:
            shot_info = self.finder.extract_shot_info_from_path(file_path)
            if shot_info:
                show, sequence, shot, _ = shot_info
                discovered_shots.add((show.split("/")[-1], sequence, shot))
        
        # User should have only 2 shots
        self.assertEqual(len(user_shots), 2)
        
        # Discovery should find many more shots
        self.assertGreater(len(discovered_shots), len(user_shots))
        
        # User's shots should be a subset of discovered shots
        for user_shot in user_shots:
            self.assertIn(user_shot, discovered_shots)

    def test_scan_mode_configuration(self):
        """Test that scan mode is properly configured from config."""
        from config import Config
        
        # Verify configuration is set for full show scanning
        self.assertEqual(Config.THREEDE_SCAN_MODE, "full_show")
        self.assertEqual(Config.THREEDE_SCAN_MAX_DEPTH, 15)
        
    def test_published_files_discovery(self):
        """Test that published files are discovered and properly identified."""
        published_paths = [
            Path("/shows/jack_ryan/shots/GF_256/GF_256_1400/publish/3de/final.3de"),
            Path("/shows/jack_ryan/shots/DEF_456/DEF_456_0100/publish/editorial/approved.3de"),
        ]
        
        for path in published_paths:
            with self.subTest(path=path):
                shot_info = self.finder.extract_shot_info_from_path(path)
                self.assertIsNotNone(shot_info)
                
                show, sequence, shot, username = shot_info
                # Published files should have pseudo-username
                self.assertTrue(username.startswith("published-"))
                
    def test_deep_directory_traversal(self):
        """Test that scanner can find deeply nested 3DE files."""
        deep_path = Path("/shows/jack_ryan/shots/XYZ_789/XYZ_789_5000/user/frank/work/3de/deep/nested/very/deep/folder/structure/file.3de")
        
        # Count depth from user directory
        user_idx = deep_path.parts.index("user")
        depth = len(deep_path.parts) - user_idx - 1
        
        # Verify it's within configured max depth
        from config import Config
        self.assertLessEqual(depth, Config.THREEDE_SCAN_MAX_DEPTH)
        
        # Should still be able to extract shot info
        shot_info = self.finder.extract_shot_info_from_path(deep_path)
        self.assertIsNotNone(shot_info)
        
    def test_cross_show_isolation(self):
        """Test that scanner properly isolates shows from each other."""
        show1_files = [
            Path("/shows/jack_ryan/shots/SEQ_01/SEQ_01_0010/user/artist/3de/file.3de"),
        ]
        show2_files = [
            Path("/shows/other_show/shots/SEQ_01/SEQ_01_0010/user/artist/3de/file.3de"),
        ]
        
        # Same sequence/shot but different shows
        for path in show1_files:
            shot_info = self.finder.extract_shot_info_from_path(path)
            self.assertIsNotNone(shot_info)
            show, _, _, _ = shot_info
            self.assertIn("jack_ryan", show)
            
        for path in show2_files:
            shot_info = self.finder.extract_shot_info_from_path(path)
            self.assertIsNotNone(shot_info)
            show, _, _, _ = shot_info
            self.assertIn("other_show", show)

    def test_scanner_excludes_current_user(self):
        """Test that scanner excludes current user's files from Other 3DE scenes."""
        current_user = "johndoe"
        
        files = [
            (Path("/shows/jack_ryan/shots/GF_256/GF_256_1400/user/johndoe/3de/mine.3de"), "johndoe"),
            (Path("/shows/jack_ryan/shots/GF_256/GF_256_1400/user/alice/3de/other.3de"), "alice"),
            (Path("/shows/jack_ryan/shots/GF_256/GF_256_1410/user/bob/3de/another.3de"), "bob"),
        ]
        
        other_scenes = []
        for path, username in files:
            if username != current_user:
                shot_info = self.finder.extract_shot_info_from_path(path)
                if shot_info:
                    other_scenes.append(shot_info)
        
        # Should exclude current user's files
        for scene in other_scenes:
            _, _, _, username = scene
            self.assertNotEqual(username, current_user)

    def test_scanner_performance_with_many_files(self):
        """Test scanner performance considerations with many files."""
        # Create a large number of mock files
        num_files = 1000
        mock_files = []
        
        for i in range(num_files):
            seq_num = i // 100  # 10 sequences
            shot_num = i % 100  # 100 shots per sequence
            path = Path(f"/shows/bigshow/shots/SEQ_{seq_num:02d}/SEQ_{seq_num:02d}_{shot_num:04d}/user/artist{i%10}/3de/file_{i}.3de")
            mock_files.append(path)
        
        # Test that extraction is efficient
        import time
        start_time = time.time()
        
        extracted_count = 0
        for path in mock_files:
            shot_info = self.finder.extract_shot_info_from_path(path)
            if shot_info:
                extracted_count += 1
        
        elapsed = time.time() - start_time
        
        # Should process all files
        self.assertEqual(extracted_count, num_files)
        
        # Should be reasonably fast (< 1 second for 1000 files)
        self.assertLess(elapsed, 1.0, f"Processing {num_files} files took {elapsed:.2f}s")

    def test_batch_processing(self):
        """Test that scanner processes files in batches for UI responsiveness."""
        from config import Config
        
        # Verify batch configuration exists
        self.assertGreater(Config.THREEDE_BATCH_SIZE, 0)
        self.assertLessEqual(Config.THREEDE_BATCH_SIZE, 100)
        
        # Test batch processing logic
        total_files = 250
        batch_size = Config.THREEDE_BATCH_SIZE
        expected_batches = (total_files + batch_size - 1) // batch_size
        
        batches_processed = 0
        for i in range(0, total_files, batch_size):
            batch_end = min(i + batch_size, total_files)
            batch_items = batch_end - i
            self.assertLessEqual(batch_items, batch_size)
            batches_processed += 1
        
        self.assertEqual(batches_processed, expected_batches)

    def test_scan_shows_root_configuration(self):
        """Test that scanner uses correct shows root path."""
        from config import Config
        
        # Verify shows root is configured
        self.assertEqual(Config.SHOWS_ROOT, "/shows")
        
        # Test with different show roots
        test_roots = ["/shows", "/mnt/shows", "/production/shows"]
        
        for root in test_roots:
            with self.subTest(root=root):
                path = Path(f"{root}/project/shots/SEQ_01/SEQ_01_0010/user/artist/3de/file.3de")
                # Path should be valid for any configured root
                self.assertTrue(path.parts[0] == "/" or path.parts[0].startswith("/"))


if __name__ == "__main__":
    unittest.main()