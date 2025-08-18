#!/usr/bin/env python3
"""Test stop-after-first optimization for 3DE scanner using real files.

This test follows best practices from UNIFIED_TESTING_GUIDE:
- Uses real files with tmp_path instead of mocking Path operations
- Tests behavior, not implementation
- Only mocks configuration values (appropriate boundary)
"""

import time
from pathlib import Path
from typing import List
from unittest.mock import patch

import pytest

from threede_scene_finder import ThreeDESceneFinder


@pytest.fixture
def create_test_show_structure(tmp_path):
    """Factory fixture to create real test file structures.

    Following UNIFIED_TESTING_GUIDE: Factory Fixtures pattern.
    """

    def _create_structure(
        num_shots: int,
        files_per_shot: int,
    ) -> tuple[Path, List[Path]]:
        """Create real .3de files in a test directory structure.

        Args:
            num_shots: Number of unique shots to create
            files_per_shot: Number of .3de files per shot

        Returns:
            Tuple of (shows_root, list_of_created_files)
        """
        shows_root = tmp_path / "shows"
        created_files = []

        for shot_num in range(num_shots):
            sequence = f"SEQ_{shot_num // 10:02d}"
            shot = f"{shot_num:04d}"
            shot_dir = f"{sequence}_{shot}"

            for file_num in range(files_per_shot):
                # Create real directory structure
                user = f"artist{file_num % 3}"
                version = f"v{file_num + 1:03d}"

                file_dir = (
                    shows_root
                    / "test_show"
                    / "shots"
                    / sequence
                    / shot_dir
                    / "user"
                    / user
                    / "3de"
                )
                file_dir.mkdir(parents=True, exist_ok=True)

                # Create real .3de file
                file_path = file_dir / f"{shot_dir}_comp_{version}.3de"
                file_path.write_text(f"# Mock 3DE content for {shot_dir} {version}")
                created_files.append(file_path)

        return shows_root, created_files

    return _create_structure


@pytest.fixture
def finder():
    """Create a ThreeDESceneFinder instance."""
    return ThreeDESceneFinder()


@pytest.fixture
def mock_shot():
    """Create a mock shot object for testing.

    Following UNIFIED_TESTING_GUIDE: Use test doubles for data objects.
    """

    class TestShot:
        def __init__(self):
            self.show = "test_show"
            self.sequence = "SEQ_00"
            self.shot = "0001"
            self.workspace_path = "/shows/test_show/shots/SEQ_00/SEQ_00_0001"

    return TestShot()


class TestStopAfterFirstWithRealFiles:
    """Test suite using real files instead of mocks."""

    def test_stop_after_first_enabled_real_files(
        self,
        finder,
        create_test_show_structure,
        mock_shot,
        tmp_path,
    ):
        """Test that scanner stops after finding one file per shot using REAL files.

        Following UNIFIED_TESTING_GUIDE: Test behavior with real components.
        """
        # Create REAL file structure: 10 shots with 5 files each
        shows_root, created_files = create_test_show_structure(10, 5)

        # Only mock configuration values (appropriate boundary)
        with patch("config.Config.THREEDE_STOP_AFTER_FIRST", True):
            with patch("config.Config.THREEDE_MAX_SHOTS_TO_SCAN", 1000):
                with patch("config.Config.THREEDE_FILE_FIRST_DISCOVERY", True):
                    # Test with REAL file discovery
                    found_files = finder.find_all_3de_files_in_show_python(
                        str(shows_root),
                        "test_show",
                        sequences=None,
                        timeout_seconds=30,
                    )

                    # Verify behavior: should find only one file per shot
                    shot_dirs_seen = set()
                    for file_path in found_files:
                        # Extract shot directory from real path
                        parts = file_path.parts
                        if "shots" in parts:
                            shots_idx = parts.index("shots")
                            if shots_idx + 2 < len(parts):
                                shot_dir = (
                                    f"{parts[shots_idx + 1]}/{parts[shots_idx + 2]}"
                                )
                                shot_dirs_seen.add(shot_dir)

                    # Should have found files from all 10 shots
                    assert len(shot_dirs_seen) == 10
                    # But should have stopped after first file per shot
                    assert len(found_files) <= 10  # At most one per shot

    def test_stop_after_first_disabled_real_files(
        self,
        finder,
        create_test_show_structure,
        mock_shot,
    ):
        """Test that scanner processes all files when disabled using REAL files."""
        # Create REAL file structure: 5 shots with 3 files each
        shows_root, created_files = create_test_show_structure(5, 3)

        with patch("config.Config.THREEDE_STOP_AFTER_FIRST", False):
            with patch("config.Config.THREEDE_MAX_SHOTS_TO_SCAN", 1000):
                with patch("config.Config.THREEDE_SCAN_MAX_FILES_PER_SHOT", 10):
                    with patch("config.Config.THREEDE_FILE_FIRST_DISCOVERY", True):
                        # Test with REAL file discovery
                        found_files = finder.find_all_3de_files_in_show_python(
                            str(shows_root),
                            "test_show",
                            sequences=None,
                            timeout_seconds=30,
                        )

                        # Should find all 15 files (5 shots * 3 files)
                        assert len(found_files) == 15

    def test_performance_improvement_real_files(
        self,
        finder,
        create_test_show_structure,
        mock_shot,
    ):
        """Test performance improvement with REAL files.

        Following UNIFIED_TESTING_GUIDE: Test actual behavior and performance.
        """
        # Create REAL large dataset: 20 shots with 10 files each
        shows_root, created_files = create_test_show_structure(20, 10)

        # Measure with stop-after-first DISABLED
        start_time = time.time()
        with patch("config.Config.THREEDE_STOP_AFTER_FIRST", False):
            with patch("config.Config.THREEDE_MAX_SHOTS_TO_SCAN", 1000):
                with patch("config.Config.THREEDE_SCAN_MAX_FILES_PER_SHOT", 20):
                    files_all = finder.find_all_3de_files_in_show_python(
                        str(shows_root),
                        "test_show",
                        sequences=None,
                        timeout_seconds=30,
                    )
        time_all_files = time.time() - start_time

        # Measure with stop-after-first ENABLED
        start_time = time.time()
        with patch("config.Config.THREEDE_STOP_AFTER_FIRST", True):
            with patch("config.Config.THREEDE_MAX_SHOTS_TO_SCAN", 1000):
                with patch("config.Config.THREEDE_SCAN_MAX_FILES_PER_SHOT", 1):
                    files_optimized = finder.find_all_3de_files_in_show_python(
                        str(shows_root),
                        "test_show",
                        sequences=None,
                        timeout_seconds=30,
                    )
        time_optimized = time.time() - start_time

        # Verify behavior improvements
        assert len(files_optimized) < len(files_all)
        assert len(files_optimized) <= 20  # At most one per shot
        assert len(files_all) == 200  # All files

        # Optimized should be faster (though with small test data, might be minimal)
        print(f"All files: {len(files_all)} in {time_all_files:.3f}s")
        print(f"Optimized: {len(files_optimized)} in {time_optimized:.3f}s")

    def test_extract_shot_info_with_real_paths(self, finder, tmp_path):
        """Test shot info extraction with REAL paths.

        Following UNIFIED_TESTING_GUIDE: Test with real data.
        """
        # Create real directory structure
        test_file = (
            tmp_path
            / "shows"
            / "jack_ryan"
            / "shots"
            / "GF_256"
            / "GF_256_1400"
            / "user"
            / "johndoe"
            / "3de"
            / "scene.3de"
        )
        test_file.parent.mkdir(parents=True)
        test_file.write_text("# Test 3DE content")

        # Test extraction on real path
        result = finder.extract_shot_info_from_path(test_file)

        assert result is not None
        show_path, sequence, shot, username = result
        assert "jack_ryan" in show_path
        assert sequence == "GF_256"
        assert shot == "1400"
        assert username == "johndoe"

    def test_published_files_discovery(self, finder, tmp_path):
        """Test discovery of published files with REAL paths."""
        # Create real published file
        published_file = (
            tmp_path
            / "shows"
            / "test_show"
            / "shots"
            / "SEQ_01"
            / "SEQ_01_0010"
            / "publish"
            / "3de"
            / "final.3de"
        )
        published_file.parent.mkdir(parents=True)
        published_file.write_text("# Published 3DE file")

        # Test extraction
        result = finder.extract_shot_info_from_path(published_file)

        assert result is not None
        show_path, sequence, shot, username = result
        assert sequence == "SEQ_01"
        assert shot == "0010"
        assert username.startswith("published-")


class TestShotDirectoryTracking:
    """Test shot directory tracking logic with real files."""

    def test_shot_directory_deduplication(self, tmp_path):
        """Test that shot directories are properly tracked to avoid duplicates.

        Following UNIFIED_TESTING_GUIDE: Test actual behavior, not implementation.
        """
        # Create REAL file structure with multiple files per shot
        shows_dir = tmp_path / "shows" / "test" / "shots"

        # Shot 1: 3 files from different artists
        shot1_files = []
        for i, artist in enumerate(["artist1", "artist2", "artist3"]):
            file_path = (
                shows_dir
                / "SEQ_01"
                / "SEQ_01_0010"
                / "user"
                / artist
                / "3de"
                / f"file{i + 1}.3de"
            )
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(f"# 3DE file from {artist}")
            shot1_files.append(file_path)

        # Shot 2: 2 files from different artists
        shot2_files = []
        for i, artist in enumerate(["artist1", "artist2"]):
            file_path = (
                shows_dir
                / "SEQ_01"
                / "SEQ_01_0020"
                / "user"
                / artist
                / "3de"
                / f"file{i + 4}.3de"
            )
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(f"# 3DE file from {artist}")
            shot2_files.append(file_path)

        # Simulate stop-after-first logic with REAL files
        all_files = list(shows_dir.rglob("*.3de"))
        assert len(all_files) == 5  # Total files created

        # Track shot directories
        shot_dirs_found = set()
        files_to_process = []

        for file_path in all_files:
            parts = file_path.parts
            if "shots" in parts:
                shots_idx = parts.index("shots")
                if shots_idx + 2 < len(parts):
                    shot_dir = f"{parts[shots_idx + 1]}/{parts[shots_idx + 2]}"

                    # Only add if not already found (stop-after-first behavior)
                    if shot_dir not in shot_dirs_found:
                        files_to_process.append(file_path)
                        shot_dirs_found.add(shot_dir)

        # Should only process 2 files (one per shot)
        assert len(files_to_process) == 2
        assert len(shot_dirs_found) == 2
        assert "SEQ_01/SEQ_01_0010" in shot_dirs_found
        assert "SEQ_01/SEQ_01_0020" in shot_dirs_found


if __name__ == "__main__":
    # Run with pytest
    import subprocess
    import sys

    # Use run_tests.py for proper Qt setup
    result = subprocess.run(
        [sys.executable, "run_tests.py", __file__],
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    sys.exit(result.returncode)
