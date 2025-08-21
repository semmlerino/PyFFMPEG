"""Integration tests for 3DE file discovery workflow."""

import shutil
import tempfile
from pathlib import Path


class TestThreeDEScannerIntegration:
    """Integration tests for 3DE file discovery and cache integration following UNIFIED_TESTING_GUIDE."""

    def setup_method(self):
        """Minimal setup to avoid pytest fixture overhead."""
        self.temp_dir = Path(tempfile.mkdtemp(prefix="shotbot_threede_scanner_"))
        self.user_home = self.temp_dir / "home" / "testuser"
        self.user_home.mkdir(parents=True, exist_ok=True)
        self.cache_dir = self.temp_dir / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Create test directory structure
        self.projects_dir = self.user_home / "projects"
        self.projects_dir.mkdir(parents=True, exist_ok=True)

    def teardown_method(self):
        """Direct cleanup without fixture dependencies."""
        try:
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:
            pass  # Ignore cleanup errors

    def test_threede_scanner_file_discovery_integration(self):
        """Test 3DE scanner finding .3de files across directory structure."""
        # Import locally to avoid pytest environment issues
        import sys
        from pathlib import Path
        from unittest.mock import patch

        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from threede_scene_finder import ThreeDESceneFinder
        from cache_manager import CacheManager

        # Create test .3de files in various locations
        test_files = [
            self.projects_dir / "project1" / "shots" / "seq01" / "scene.3de",
            self.projects_dir / "project1" / "shots" / "seq02" / "another_scene.3de", 
            self.projects_dir / "project2" / "3de_files" / "test_scene.3de",
            self.user_home / "desktop" / "quick_scene.3de"
        ]
        
        # Create files and directories
        for file_path in test_files:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text("# 3DE Scene File\nversion 1.0\n")
        
        # Create cache manager
        cache_manager = CacheManager(cache_dir=self.cache_dir)
        
        # Mock username to avoid system dependency
        with patch('threede_scene_finder.getpass.getuser', return_value='testuser'):
            # Create scanner
            scanner = ThreeDESceneFinder(
                user_directories=[str(self.user_home)],
                cache_manager=cache_manager
            )
            
            # Perform scan
            found_scenes = scanner.find_3de_scenes()
            
            # Verify all .3de files were found
            assert len(found_scenes) == len(test_files)
            
            # Verify file paths are correct
            found_paths = {scene.file_path for scene in found_scenes}
            expected_paths = {str(f) for f in test_files}
            assert found_paths == expected_paths
            
            # Verify plate name extraction
            scene_by_path = {scene.file_path: scene for scene in found_scenes}
            
            seq01_scene = scene_by_path[str(test_files[0])]
            assert "seq01" in seq01_scene.plate_name
            
            seq02_scene = scene_by_path[str(test_files[1])]  
            assert "seq02" in seq02_scene.plate_name

    def test_threede_scanner_cache_integration(self):
        """Test 3DE scanner integration with cache system."""
        import sys
        from pathlib import Path
        from unittest.mock import patch
        import json

        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from threede_scene_finder import ThreeDESceneFinder
        from cache_manager import CacheManager

        # Create test .3de file
        test_file = self.projects_dir / "cached_project" / "scene.3de"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("# Cached 3DE Scene\nversion 1.0\n")
        
        cache_manager = CacheManager(cache_dir=self.cache_dir)
        
        with patch('threede_scene_finder.getpass.getuser', return_value='testuser'):
            scanner = ThreeDESceneFinder(
                user_directories=[str(self.user_home)],
                cache_manager=cache_manager
            )
            
            # First scan - should populate cache
            scenes1 = scanner.find_3de_scenes()
            assert len(scenes1) == 1
            
            # Verify cache file was created
            cache_file = self.cache_dir / "threede_cache.json"
            assert cache_file.exists()
            
            # Read cache data
            with open(cache_file, 'r') as f:
                cache_data = json.load(f)
            
            assert "scenes" in cache_data
            assert len(cache_data["scenes"]) == 1
            
            cached_scene = cache_data["scenes"][0]
            assert cached_scene["file_path"] == str(test_file)
            assert "scene.3de" in cached_scene["plate_name"]
            
            # Second scan with same files - should use cache
            scenes2 = scanner.find_3de_scenes()
            assert len(scenes2) == 1
            assert scenes2[0].file_path == scenes1[0].file_path

    def test_threede_scanner_filtering_and_deduplication(self):
        """Test 3DE scanner filtering and deduplication logic."""
        import sys
        from pathlib import Path
        from unittest.mock import patch

        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from threede_scene_finder import ThreeDESceneFinder
        from cache_manager import CacheManager

        # Create duplicate .3de files for same shot
        shot_dir = self.projects_dir / "show1" / "shots" / "seq01" / "seq01_0010"
        shot_dir.mkdir(parents=True, exist_ok=True)
        
        # Create multiple .3de files in same shot directory
        scene1 = shot_dir / "scene_v001.3de"
        scene2 = shot_dir / "scene_v002.3de"  # Newer version
        scene3 = shot_dir / "backup_scene.3de"
        
        scene1.write_text("# Scene v001\nversion 1.0\n")
        scene2.write_text("# Scene v002\nversion 1.0\n")  
        scene3.write_text("# Backup Scene\nversion 1.0\n")
        
        # Make scene2 newer (higher mtime)
        import time
        time.sleep(0.1)  # Ensure different mtimes
        scene2.touch()
        
        cache_manager = CacheManager(cache_dir=self.cache_dir)
        
        with patch('threede_scene_finder.getpass.getuser', return_value='testuser'):
            scanner = ThreeDESceneFinder(
                user_directories=[str(self.user_home)],
                cache_manager=cache_manager
            )
            
            # Find scenes
            found_scenes = scanner.find_3de_scenes()
            
            # Should find all files (deduplication happens at model level)
            assert len(found_scenes) == 3
            
            # Verify all scenes have same shot but different files
            shot_scenes = [scene for scene in found_scenes if "seq01_0010" in scene.plate_name]
            assert len(shot_scenes) == 3
            
            # Verify file paths are different
            file_paths = {scene.file_path for scene in shot_scenes}
            assert len(file_paths) == 3

    def test_threede_scanner_user_exclusion_integration(self):
        """Test 3DE scanner excluding current user's shots."""
        import sys
        from pathlib import Path
        from unittest.mock import patch

        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from threede_scene_finder import ThreeDESceneFinder
        from cache_manager import CacheManager

        # Create .3de files for different users
        current_user_shot = self.projects_dir / "show1" / "user" / "testuser" / "seq01_0010" / "scene.3de"
        other_user_shot = self.projects_dir / "show1" / "user" / "otheruser" / "seq01_0020" / "scene.3de"
        no_user_shot = self.projects_dir / "show1" / "shots" / "seq01_0030" / "scene.3de"
        
        for shot_file in [current_user_shot, other_user_shot, no_user_shot]:
            shot_file.parent.mkdir(parents=True, exist_ok=True)
            shot_file.write_text("# 3DE Scene\nversion 1.0\n")
        
        cache_manager = CacheManager(cache_dir=self.cache_dir)
        
        with patch('threede_scene_finder.getpass.getuser', return_value='testuser'):
            scanner = ThreeDESceneFinder(
                user_directories=[str(self.user_home)],
                cache_manager=cache_manager,
                exclude_current_user=True  # Enable user exclusion
            )
            
            found_scenes = scanner.find_3de_scenes()
            
            # Should exclude current user's shots
            found_paths = {scene.file_path for scene in found_scenes}
            
            # Should NOT include current user's shot
            assert str(current_user_shot) not in found_paths
            
            # Should include other user's shot and non-user shots
            assert str(other_user_shot) in found_paths
            assert str(no_user_shot) in found_paths
            
            # Verify correct count
            assert len(found_scenes) == 2

    def test_threede_scanner_background_scanning_workflow(self):
        """Test 3DE scanner background scanning with progress reporting."""
        import sys
        from pathlib import Path
        from unittest.mock import patch

        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from tests.test_doubles import TestSignal
        from threede_scene_worker import ThreeDESceneWorker
        from cache_manager import CacheManager

        # Create several .3de files to scan
        test_files = []
        for i in range(5):
            file_path = self.projects_dir / f"project_{i}" / f"scene_{i}.3de"
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(f"# Scene {i}\nversion 1.0\n")
            test_files.append(file_path)
        
        cache_manager = CacheManager(cache_dir=self.cache_dir)
        
        # Track signals
        progress_signals = []
        scene_found_signals = []
        finished_signals = []
        
        def track_progress(*args):
            progress_signals.append(args)
            
        def track_scene_found(*args):
            scene_found_signals.append(args)
            
        def track_finished(*args):
            finished_signals.append(args)
        
        with patch('threede_scene_finder.getpass.getuser', return_value='testuser'):
            # Create worker
            worker = ThreeDESceneWorker(
                user_directories=[str(self.user_home)],
                cache_manager=cache_manager
            )
            
            # Connect signals
            worker.scan_progress.connect(track_progress)
            worker.scene_found.connect(track_scene_found)
            worker.scan_finished.connect(track_finished)
            
            # Start scanning
            worker.start_scan()
            
            # Wait for completion (in real usage, this would be async)
            worker.wait_for_completion()
            
            # Verify progress signals were emitted
            assert len(progress_signals) > 0
            
            # Verify scene found signals (one per file)
            assert len(scene_found_signals) == len(test_files)
            
            # Verify all files were found
            found_files = [signal[0] for signal in scene_found_signals]  # First arg is file path
            expected_files = [str(f) for f in test_files]
            
            assert set(found_files) == set(expected_files)
            
            # Verify scan finished signal
            assert len(finished_signals) == 1

    def test_threede_scanner_error_handling_integration(self):
        """Test 3DE scanner error handling with inaccessible directories."""
        import sys
        from pathlib import Path
        from unittest.mock import patch

        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from threede_scene_finder import ThreeDESceneFinder
        from cache_manager import CacheManager

        # Create accessible and inaccessible directories
        accessible_dir = self.user_home / "accessible"
        accessible_dir.mkdir(parents=True, exist_ok=True)
        
        # Create .3de file in accessible directory
        accessible_file = accessible_dir / "good_scene.3de"
        accessible_file.write_text("# Good Scene\nversion 1.0\n")
        
        # Create inaccessible directory path (doesn't exist)
        inaccessible_dir = "/nonexistent/path/to/directory"
        
        cache_manager = CacheManager(cache_dir=self.cache_dir)
        
        with patch('threede_scene_finder.getpass.getuser', return_value='testuser'):
            scanner = ThreeDESceneFinder(
                user_directories=[str(self.user_home), inaccessible_dir],
                cache_manager=cache_manager
            )
            
            # Should handle errors gracefully
            found_scenes = scanner.find_3de_scenes()
            
            # Should still find accessible files despite errors
            assert len(found_scenes) >= 1
            
            # Verify accessible file was found
            found_paths = {scene.file_path for scene in found_scenes}
            assert str(accessible_file) in found_paths


# Allow running as standalone test
if __name__ == "__main__":
    test = TestThreeDEScannerIntegration()
    test.setup_method()
    try:
        print("Running 3DE scanner file discovery integration...")
        test.test_threede_scanner_file_discovery_integration()
        print("✓ 3DE scanner file discovery passed")

        print("Running 3DE scanner cache integration...")
        test.test_threede_scanner_cache_integration()
        print("✓ 3DE scanner cache integration passed")

        print("Running 3DE scanner filtering and deduplication...")
        test.test_threede_scanner_filtering_and_deduplication()
        print("✓ 3DE scanner filtering and deduplication passed")

        print("Running 3DE scanner user exclusion integration...")
        test.test_threede_scanner_user_exclusion_integration()
        print("✓ 3DE scanner user exclusion integration passed")

        print("Running 3DE scanner background scanning workflow...")
        test.test_threede_scanner_background_scanning_workflow()
        print("✓ 3DE scanner background scanning workflow passed")

        print("Running 3DE scanner error handling integration...")
        test.test_threede_scanner_error_handling_integration()
        print("✓ 3DE scanner error handling integration passed")

        print("All 3DE scanner integration tests passed!")
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        test.teardown_method()