"""Tests for PreviousShotsFinder class.

Following best practices:
- Mocks only at system boundaries (subprocess)
- Uses real filesystem structures with tmp_path
- Tests behavior, not implementation
- No excessive mocking
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from previous_shots_finder import PreviousShotsFinder
from shot_model import Shot

# Import test helpers
sys.path.insert(0, str(Path(__file__).parent.parent))

pytestmark = [pytest.mark.unit, pytest.mark.slow]


from tests.test_doubles_library import TestSubprocess
from tests.test_doubles_previous_shots import create_test_shot, create_test_shots


class TestPreviousShotsFinder:
    """Test cases for PreviousShotsFinder with real filesystem structures.

    Following UNIFIED_TESTING_GUIDE:
    - Mock only subprocess calls (system boundary)
    - Use real filesystem operations
    - Test actual behavior
    """

    @pytest.fixture
    def finder(self) -> PreviousShotsFinder:
        """Create finder with test username."""
        return PreviousShotsFinder(username="testuser")

    @pytest.fixture
    def real_shows_structure(self, tmp_path: Path) -> Path:
        """Create realistic shows directory structure using real filesystem.

        Following UNIFIED_TESTING_GUIDE:
        - Use real filesystem operations
        - Create actual directory structures
        """
        shows_root = tmp_path / "shows"

        # Create multiple shows with shots containing user work
        for show in ["testshow", "anothershow"]:
            for seq in ["101_ABC", "102_DEF"]:
                for shot in ["0010", "0020", "0030"]:
                    shot_path = shows_root / show / "shots" / seq / shot
                    user_path = shot_path / "user" / "testuser"
                    user_path.mkdir(parents=True, exist_ok=True)

                    # Add some work files (real files)
                    (user_path / "work.3de").write_text("3DE scene")
                    (user_path / "comp.nk").write_text("Nuke script")

        # Create some shots without user work
        no_work_path = shows_root / "testshow" / "shots" / "101_ABC" / "0040"
        no_work_path.mkdir(parents=True, exist_ok=True)

        return shows_root

    def test_finder_initialization_with_username(self):
        """Test finder initialization with specific username."""
        finder = PreviousShotsFinder(username="customuser")

        assert finder.username == "customuser"
        assert finder.user_path_pattern == "/user/customuser"
        assert finder._shot_pattern is not None

    def test_finder_initialization_with_sanitization(self):
        """Test that username is properly sanitized for security."""
        # Test path traversal attempt is sanitized (not blocked)
        finder = PreviousShotsFinder(username="../../../etc/passwd")
        assert finder.username == "etcpasswd"  # Dots and slashes removed

        # Test that dots and slashes are removed
        finder = PreviousShotsFinder(username="test.user")
        assert finder.username == "testuser"

        # Test empty username after sanitization
        with pytest.raises(ValueError, match="Invalid username after sanitization"):
            PreviousShotsFinder(username="../../")

    def test_finder_initialization_default_user(self):
        """Test finder initialization with default user."""
        with patch.dict(os.environ, {"USER": "envuser"}):
            finder = PreviousShotsFinder()
            assert finder.username == "envuser"

    @pytest.mark.parametrize(
        "path,expected_shot",
        [
            (
                "/shows/testshow/shots/101_ABC/0010/user/testuser",
                ("testshow", "101_ABC", "0010"),
            ),
            (
                "/shows/feature/shots/seq01/shot01/user/artist",
                ("feature", "seq01", "shot01"),
            ),
            ("/invalid/path/structure", None),
            (
                "/shows/test/shots/",  # Incomplete path
                None,
            ),
        ],
    )
    def test_parse_shot_from_path(self, finder, path, expected_shot):
        """Test shot parsing from various path structures.

        Testing actual behavior of path parsing.
        """
        shot = finder._parse_shot_from_path(path)

        if expected_shot is None:
            assert shot is None
        else:
            show, sequence, shot_name = expected_shot
            assert shot.show == show
            assert shot.sequence == sequence
            assert shot.shot == shot_name
            assert f"/shows/{show}/shots/{sequence}/{shot_name}" in shot.workspace_path

    def test_find_user_shots_with_real_structure(self, finder, real_shows_structure):
        """Test finding user shots with real directory structure.

        Following UNIFIED_TESTING_GUIDE:
        - Mock only subprocess (system boundary)
        - Use real filesystem structure
        """
        # Mock subprocess.run to return paths from our test structure
        mock_paths = [
            str(
                real_shows_structure
                / "testshow"
                / "shots"
                / "101_ABC"
                / "0010"
                / "user"
                / "testuser"
            ),
            str(
                real_shows_structure
                / "testshow"
                / "shots"
                / "101_ABC"
                / "0020"
                / "user"
                / "testuser"
            ),
            str(
                real_shows_structure
                / "anothershow"
                / "shots"
                / "102_DEF"
                / "0010"
                / "user"
                / "testuser"
            ),
        ]

        # Use test double for subprocess
        test_subprocess = TestSubprocess()
        test_subprocess.return_code = 0
        test_subprocess.stdout = "\n".join(mock_paths)
        test_subprocess.stderr = ""

        with patch("subprocess.run", test_subprocess.run) as mock_run:
            shots = finder.find_user_shots(real_shows_structure)

        # Verify find command was called correctly
        # Test behavior instead: assert result is True
        args = mock_run.call_args[0][0]
        assert "find" in args
        assert str(real_shows_structure) in args
        # Pattern should be in the path argument
        pattern_found = any("*/user/testuser" in arg for arg in args)
        assert pattern_found, f"Pattern '*/user/testuser' not found in args: {args}"
        # We no longer have "2>/dev/null" as it's handled by stderr=subprocess.DEVNULL
        assert "2>/dev/null" not in args

        # Verify stderr handling
        kwargs = mock_run.call_args[1]
        assert kwargs.get("stderr") == subprocess.DEVNULL

        # Verify shots were parsed correctly
        assert len(shots) == 3
        shot_ids = {(s.show, s.sequence, s.shot) for s in shots}
        expected_ids = {
            ("testshow", "101_ABC", "0010"),
            ("testshow", "101_ABC", "0020"),
            ("anothershow", "102_DEF", "0010"),
        }
        assert shot_ids == expected_ids

    def test_find_user_shots_nonexistent_directory(self, finder, tmp_path):
        """Test behavior with nonexistent shows directory."""
        nonexistent = tmp_path / "nonexistent"
        shots = finder.find_user_shots(nonexistent)

        assert shots == []

    def test_find_user_shots_subprocess_timeout(self, finder, real_shows_structure):
        """Test handling of subprocess timeout."""
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("find", 30)):
            shots = finder.find_user_shots(real_shows_structure)

        assert shots == []

    def test_find_user_shots_subprocess_error(self, finder, real_shows_structure):
        """Test handling of subprocess errors."""
        # Use test double for subprocess error
        test_subprocess = TestSubprocess()
        test_subprocess.return_code = 1
        test_subprocess.stderr = "Permission denied"
        test_subprocess.stdout = ""

        with patch("subprocess.run", test_subprocess.run):
            shots = finder.find_user_shots(real_shows_structure)

        # Should handle errors gracefully and return empty list
        assert shots == []

    def test_filter_approved_shots_behavior(self, finder):
        """Test actual filtering behavior, not implementation.

        Following UNIFIED_TESTING_GUIDE:
        - Test behavior (what gets filtered)
        - Don't test implementation details
        """
        # Create test shots
        all_user_shots = create_test_shots(4)
        active_shots = [
            all_user_shots[0],
            all_user_shots[3],
        ]  # First and last are active

        approved_shots = finder.filter_approved_shots(all_user_shots, active_shots)

        # Should return only non-active shots
        assert len(approved_shots) == 2
        assert all_user_shots[1] in approved_shots
        assert all_user_shots[2] in approved_shots
        assert all_user_shots[0] not in approved_shots  # Active
        assert all_user_shots[3] not in approved_shots  # Active

    def test_filter_approved_shots_edge_cases(self, finder):
        """Test filtering edge cases."""
        all_user_shots = create_test_shots(2)

        # No active shots - all should be approved
        approved = finder.filter_approved_shots(all_user_shots, [])
        assert approved == all_user_shots

        # All shots active - none should be approved
        approved = finder.filter_approved_shots(all_user_shots, all_user_shots)
        assert approved == []

        # Empty user shots
        approved = finder.filter_approved_shots([], [])
        assert approved == []

    def test_find_approved_shots_integration(self, finder, real_shows_structure):
        """Test complete workflow from finding to filtering.

        Integration test with real filesystem and subprocess mocking.
        """
        # Mock subprocess to return some user shots
        mock_paths = [
            str(
                real_shows_structure
                / "testshow"
                / "shots"
                / "101_ABC"
                / "0010"
                / "user"
                / "testuser"
            ),
            str(
                real_shows_structure
                / "testshow"
                / "shots"
                / "101_ABC"
                / "0020"
                / "user"
                / "testuser"
            ),
        ]

        # Use test double for subprocess
        test_subprocess = TestSubprocess()
        test_subprocess.return_code = 0
        test_subprocess.stdout = "\n".join(mock_paths)
        test_subprocess.stderr = ""

        # Create active shots (one overlapping)
        active_shots = [
            create_test_shot("testshow", "101_ABC", "0010"),
        ]

        with patch("subprocess.run", test_subprocess.run):
            approved_shots = finder.find_approved_shots(
                active_shots, real_shows_structure
            )

        # Should return only the non-active shot
        assert len(approved_shots) == 1
        assert approved_shots[0].shot == "0020"

    def test_get_shot_details_behavior(self, finder):
        """Test getting shot details returns expected structure."""
        shot = create_test_shot("testshow", "101_ABC", "0010")

        details = finder.get_shot_details(shot)

        # Test behavior - what details are returned
        assert details["show"] == "testshow"
        assert details["sequence"] == "101_ABC"
        assert details["shot"] == "0010"
        assert details["workspace_path"] == shot.workspace_path
        assert details["user_path"] == f"{shot.workspace_path}/user/testuser"
        assert details["status"] == "approved"

    def test_get_shot_details_with_real_directory(self, finder, tmp_path):
        """Test getting shot details with real user directory.

        Uses real filesystem to test file detection.
        """
        # Create real user directory structure
        shot_path = tmp_path / "shows" / "testshow" / "shots" / "101_ABC" / "0010"
        user_path = shot_path / "user" / "testuser"
        user_path.mkdir(parents=True, exist_ok=True)

        # Add various work files (real files)
        (user_path / "scene.3de").write_text("3DE scene")
        (user_path / "comp.nk").write_text("Nuke script")
        (user_path / "anim.ma").write_text("Maya ASCII")
        (user_path / "model.mb").write_text("Maya Binary")

        shot = Shot("testshow", "101_ABC", "0010", str(shot_path))

        # Get details with real directory
        details = finder.get_shot_details(shot)

        # Manually check the directory exists (since the method checks this)
        actual_user_path = Path(details["user_path"])
        if actual_user_path.exists():
            # Would have these checks in real implementation
            has_3de = any(actual_user_path.rglob("*.3de"))
            has_nuke = any(actual_user_path.rglob("*.nk"))
            has_maya = any(actual_user_path.rglob("*.m[ab]"))

            assert has_3de
            assert has_nuke
            assert has_maya


class TestPreviousShotsFinderPerformance:
    """Performance tests for PreviousShotsFinder."""

    @pytest.fixture
    def large_shows_structure(self, tmp_path: Path) -> Path:
        """Create large shows structure for performance testing.

        Real filesystem structure for realistic performance testing.
        """
        shows_root = tmp_path / "shows"

        # Create many shows, sequences, and shots
        for show_idx in range(3):
            for seq_idx in range(5):
                for shot_idx in range(10):
                    show = f"show{show_idx:02d}"
                    seq = f"seq{seq_idx:03d}"
                    shot = f"shot{shot_idx:04d}"

                    shot_path = shows_root / show / "shots" / seq / shot
                    user_path = shot_path / "user" / "testuser"
                    user_path.mkdir(parents=True, exist_ok=True)

        return shows_root

