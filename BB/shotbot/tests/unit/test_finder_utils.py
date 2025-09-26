"""Unit tests for FinderUtils class."""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

import pytest

from config import Config
from finder_utils import FinderUtils


class TestSanitizeUsername:
    """Test username sanitization functionality."""

    def test_valid_usernames(self):
        """Test that valid usernames pass through unchanged."""
        assert FinderUtils.sanitize_username("john_doe") == "john_doe"
        assert FinderUtils.sanitize_username("user123") == "user123"
        assert FinderUtils.sanitize_username("test-user") == "test-user"
        assert FinderUtils.sanitize_username("UPPERCASE") == "UPPERCASE"

    def test_path_traversal_removal(self):
        """Test that path traversal characters are removed."""
        assert FinderUtils.sanitize_username("user/../etc") == "useretc"
        assert FinderUtils.sanitize_username("./user") == "user"
        assert FinderUtils.sanitize_username("user\\system") == "usersystem"
        assert FinderUtils.sanitize_username("user/admin") == "useradmin"

    def test_invalid_usernames_raise_error(self):
        """Test that invalid usernames raise ValueError."""
        with pytest.raises(ValueError, match="Invalid username after sanitization"):
            FinderUtils.sanitize_username("...")

        with pytest.raises(ValueError, match="Invalid username after sanitization"):
            FinderUtils.sanitize_username("")

        with pytest.raises(ValueError, match="Username contains invalid characters"):
            FinderUtils.sanitize_username("user@domain")

        with pytest.raises(ValueError, match="Username contains invalid characters"):
            FinderUtils.sanitize_username("user!name")

    def test_edge_cases(self):
        """Test edge cases for username sanitization."""
        # Single character usernames
        assert FinderUtils.sanitize_username("a") == "a"
        assert FinderUtils.sanitize_username("1") == "1"

        # Usernames with multiple hyphens/underscores
        assert FinderUtils.sanitize_username("user__name") == "user__name"
        assert FinderUtils.sanitize_username("test--user") == "test--user"


class TestExtractVersion:
    """Test version extraction functionality."""

    def test_default_pattern(self):
        """Test version extraction with default pattern."""
        assert FinderUtils.extract_version(Path("file_v001.ma")) == 1
        assert FinderUtils.extract_version(Path("scene_v042.3de")) == 42
        assert FinderUtils.extract_version(Path("render_v999.exr")) == 999
        assert FinderUtils.extract_version("string_path_v123.txt") == 123

    def test_custom_pattern_string(self):
        """Test version extraction with custom string pattern."""
        pattern = r"\.v(\d{4})\."
        assert FinderUtils.extract_version("file.v0001.exr", pattern) == 1
        assert FinderUtils.extract_version("plate.v1234.dpx", pattern) == 1234

    def test_custom_pattern_compiled(self):
        """Test version extraction with compiled pattern."""
        pattern = re.compile(r"_ver(\d{2})")
        assert FinderUtils.extract_version("file_ver01.txt", pattern) == 1
        assert FinderUtils.extract_version("scene_ver99.ma", pattern) == 99

    def test_no_version_found(self):
        """Test that None is returned when no version found."""
        assert FinderUtils.extract_version(Path("file_without_version.txt")) is None
        assert FinderUtils.extract_version("no_version_here.ma") is None
        assert FinderUtils.extract_version("v_but_no_numbers.txt") is None

    def test_multiple_versions(self):
        """Test that first matching version is extracted."""
        assert FinderUtils.extract_version("file_v001_v002.ma") == 1
        assert FinderUtils.extract_version("text_v001_file_v002.txt") == 1  # Fixed to match _v pattern


class TestBuildUserPath:
    """Test VFX user path building."""

    def test_maya_path(self):
        """Test Maya application path building."""
        workspace = Path("/shows/test/shots/010/0010")
        path = FinderUtils.build_user_path(workspace, "john", "maya")
        assert path == Path("/shows/test/shots/010/0010/user/john/maya/scenes")

    def test_nuke_path(self):
        """Test Nuke application path building."""
        workspace = Path("/shows/test/shots/020/0020")
        path = FinderUtils.build_user_path(workspace, "jane", "nuke")
        assert path == Path("/shows/test/shots/020/0020/user/jane/nuke/scenes")

    def test_3de_special_path(self):
        """Test 3DE special directory structure."""
        workspace = Path("/shows/test/shots/030/0030")
        path = FinderUtils.build_user_path(workspace, "bob", "3de")
        expected = Path("/shows/test/shots/030/0030/user/bob/mm/3de/mm-default/scenes/scene")
        assert path == expected

    def test_custom_subdir(self):
        """Test custom subdirectory specification."""
        workspace = Path("/shows/test/shots/040/0040")
        path = FinderUtils.build_user_path(workspace, "alice", "maya", "scripts")
        assert path == Path("/shows/test/shots/040/0040/user/alice/maya/scripts")

    def test_3de_ignores_subdir(self):
        """Test that 3DE ignores custom subdir parameter."""
        workspace = Path("/shows/test/shots/050/0050")
        path = FinderUtils.build_user_path(workspace, "charlie", "3de", "custom")
        # 3DE should still use its special structure
        expected = Path("/shows/test/shots/050/0050/user/charlie/mm/3de/mm-default/scenes/scene")
        assert path == expected


class TestFindLatestByVersion:
    """Test finding latest file by version."""

    def test_find_latest_from_versioned_files(self):
        """Test finding latest version from list."""
        files = [
            Path("file_v001.ma"),
            Path("file_v005.ma"),
            Path("file_v003.ma"),
            Path("file_v002.ma"),
        ]
        latest = FinderUtils.find_latest_by_version(files)
        assert latest == Path("file_v005.ma")

    def test_empty_list_returns_none(self):
        """Test that empty list returns None."""
        assert FinderUtils.find_latest_by_version([]) is None

    def test_no_versioned_files_returns_none(self):
        """Test that list with no versioned files returns None."""
        files = [
            Path("file_without_version.ma"),
            Path("another_file.txt"),
        ]
        assert FinderUtils.find_latest_by_version(files) is None

    def test_mixed_versioned_and_unversioned(self):
        """Test handling mix of versioned and unversioned files."""
        files = [
            Path("file_v001.ma"),
            Path("no_version.ma"),
            Path("file_v003.ma"),
            Path("also_no_version.txt"),
        ]
        latest = FinderUtils.find_latest_by_version(files)
        assert latest == Path("file_v003.ma")

    def test_custom_version_pattern(self):
        """Test with custom version pattern."""
        files = [
            Path("file.v0001.exr"),
            Path("file.v0010.exr"),
            Path("file.v0005.exr"),
        ]
        pattern = r"\.v(\d{4})\."
        latest = FinderUtils.find_latest_by_version(files, pattern)
        assert latest == Path("file.v0010.exr")


class TestSortByVersion:
    """Test version-based sorting."""

    def test_sort_ascending(self):
        """Test sorting files in ascending version order."""
        files = [
            Path("file_v003.ma"),
            Path("file_v001.ma"),
            Path("file_v002.ma"),
        ]
        sorted_files = FinderUtils.sort_by_version(files)
        assert sorted_files == [
            Path("file_v001.ma"),
            Path("file_v002.ma"),
            Path("file_v003.ma"),
        ]

    def test_sort_descending(self):
        """Test sorting files in descending version order."""
        files = [
            Path("file_v003.ma"),
            Path("file_v001.ma"),
            Path("file_v002.ma"),
        ]
        sorted_files = FinderUtils.sort_by_version(files, reverse=True)
        assert sorted_files == [
            Path("file_v003.ma"),
            Path("file_v002.ma"),
            Path("file_v001.ma"),
        ]

    def test_unversioned_files_at_end(self):
        """Test that unversioned files are placed at the end."""
        files = [
            Path("file_v002.ma"),
            Path("no_version.ma"),
            Path("file_v001.ma"),
            Path("also_no_version.txt"),
        ]
        sorted_files = FinderUtils.sort_by_version(files)
        assert sorted_files == [
            Path("file_v001.ma"),
            Path("file_v002.ma"),
            Path("also_no_version.txt"),  # Alphabetically sorted
            Path("no_version.ma"),
        ]


class TestSortByPriority:
    """Test priority-based sorting."""

    def test_basic_priority_sorting(self):
        """Test sorting items by priority order."""
        items = [
            ("BG01", Path("bg_plate.exr")),
            ("FG01", Path("fg_plate.exr")),
            ("PL01", Path("main_plate.exr")),
        ]
        priority = ["FG01", "PL01", "BG01"]
        sorted_items = FinderUtils.sort_by_priority(items, priority)
        assert sorted_items == [
            ("FG01", Path("fg_plate.exr")),
            ("PL01", Path("main_plate.exr")),
            ("BG01", Path("bg_plate.exr")),
        ]

    def test_unknown_items_go_last(self):
        """Test that unknown items are placed at the end."""
        items = [
            ("UNKNOWN", Path("unknown.exr")),
            ("PL01", Path("main_plate.exr")),
            ("FG01", Path("fg_plate.exr")),
        ]
        priority = ["FG01", "PL01"]
        sorted_items = FinderUtils.sort_by_priority(items, priority)
        assert sorted_items == [
            ("FG01", Path("fg_plate.exr")),
            ("PL01", Path("main_plate.exr")),
            ("UNKNOWN", Path("unknown.exr")),
        ]

    def test_empty_priority_list(self):
        """Test behavior with empty priority list."""
        items = [
            ("BG01", Path("bg.exr")),
            ("FG01", Path("fg.exr")),
        ]
        sorted_items = FinderUtils.sort_by_priority(items, [])
        # All items should have same priority, order unchanged
        assert sorted_items == items


class TestParseShotPath:
    """Test shot path parsing."""

    @patch.object(Config, 'SHOWS_ROOT', '/tmp/mock_vfx/shows')
    def test_valid_shot_path(self):
        """Test parsing valid VFX shot path."""
        path = "/tmp/mock_vfx/shows/test_show/shots/010/0010/user/john/maya/scenes"
        result = FinderUtils.parse_shot_path(path)
        assert result == ("test_show", "010", "0010")

    @patch.object(Config, 'SHOWS_ROOT', '/tmp/mock_vfx/shows')
    def test_partial_shot_path(self):
        """Test parsing path up to shot level."""
        path = "/tmp/mock_vfx/shows/myshow/shots/020/0020/"
        result = FinderUtils.parse_shot_path(path)
        assert result == ("myshow", "020", "0020")

    @patch.object(Config, 'SHOWS_ROOT', '/tmp/mock_vfx/shows')
    def test_invalid_path_returns_none(self):
        """Test that invalid paths return None."""
        # Missing shots directory
        assert FinderUtils.parse_shot_path("/tmp/mock_vfx/shows/test/010/0010") is None
        # Not under shows root
        assert FinderUtils.parse_shot_path("/different/root/test/shots/010/0010") is None
        # Empty path
        assert FinderUtils.parse_shot_path("") is None


class TestGetWorkspaceFromPath:
    """Test workspace extraction from path."""

    @patch.object(Config, 'SHOWS_ROOT', '/tmp/mock_vfx/shows')
    def test_extract_workspace(self):
        """Test extracting workspace from full path."""
        path = "/tmp/mock_vfx/shows/test/shots/010/0010/user/john/maya/scenes/file.ma"
        workspace = FinderUtils.get_workspace_from_path(path)
        assert workspace == "/tmp/mock_vfx/shows/test/shots/010/0010"

    @patch.object(Config, 'SHOWS_ROOT', '/tmp/mock_vfx/shows')
    def test_invalid_path_returns_none(self):
        """Test that invalid paths return None."""
        assert FinderUtils.get_workspace_from_path("/invalid/path") is None
        assert FinderUtils.get_workspace_from_path("") is None


class TestIsValidVfxPath:
    """Test VFX path validation."""

    @patch.object(Config, 'SHOWS_ROOT', '/tmp/mock_vfx/shows')
    def test_valid_vfx_paths(self):
        """Test that valid VFX paths return True."""
        assert FinderUtils.is_valid_vfx_path("/tmp/mock_vfx/shows/test/shots/010/0010/") is True
        assert FinderUtils.is_valid_vfx_path("/tmp/mock_vfx/shows/show/shots/seq/shot/user") is True

    @patch.object(Config, 'SHOWS_ROOT', '/tmp/mock_vfx/shows')
    def test_invalid_vfx_paths(self):
        """Test that invalid paths return False."""
        assert FinderUtils.is_valid_vfx_path("/random/path") is False
        assert FinderUtils.is_valid_vfx_path("") is False
        assert FinderUtils.is_valid_vfx_path("/tmp/mock_vfx/shows/test/010/0010") is False


class TestFilterByExtensions:
    """Test file extension filtering."""

    def test_filter_case_insensitive(self):
        """Test case-insensitive extension filtering."""
        files = [
            Path("file.MA"),
            Path("scene.mb"),
            Path("test.txt"),
            Path("render.exr"),
            Path("MAYA.MB"),
        ]
        filtered = FinderUtils.filter_by_extensions(files, [".ma", ".mb"])
        assert set(filtered) == {Path("file.MA"), Path("scene.mb"), Path("MAYA.MB")}

    def test_filter_case_sensitive(self):
        """Test case-sensitive extension filtering."""
        files = [
            Path("file.MA"),
            Path("scene.mb"),
            Path("test.txt"),
        ]
        filtered = FinderUtils.filter_by_extensions(files, [".ma", ".mb"], case_sensitive=True)
        assert filtered == [Path("scene.mb")]

    def test_empty_files_list(self):
        """Test filtering empty file list."""
        assert FinderUtils.filter_by_extensions([], [".ma"]) == []

    def test_no_matching_extensions(self):
        """Test when no files match extensions."""
        files = [Path("file.txt"), Path("doc.pdf")]
        assert FinderUtils.filter_by_extensions(files, [".ma", ".mb"]) == []


class TestGetRelativePath:
    """Test relative path calculation."""

    def test_valid_relative_path(self):
        """Test getting relative path with common base."""
        path = Path("/shows/test/shots/010/0010/user/file.ma")
        base = Path("/shows/test/shots")
        relative = FinderUtils.get_relative_path(path, base)
        assert relative == Path("010/0010/user/file.ma")

    def test_no_common_base_returns_original(self):
        """Test that paths without common base return original."""
        path = Path("/different/root/file.ma")
        base = Path("/shows/test")
        result = FinderUtils.get_relative_path(path, base)
        assert result == path

    def test_same_path(self):
        """Test relative path when path equals base."""
        path = Path("/shows/test")
        base = Path("/shows/test")
        relative = FinderUtils.get_relative_path(path, base)
        assert relative == Path(".")


class TestFindFilesRecursive:
    """Test recursive file finding with depth limit."""

    def test_find_files_no_depth_limit(self, tmp_path):
        """Test recursive search without depth limit."""
        # Create test structure
        (tmp_path / "level1").mkdir()
        (tmp_path / "level1" / "file1.ma").touch()
        (tmp_path / "level1" / "level2").mkdir()
        (tmp_path / "level1" / "level2" / "file2.ma").touch()
        (tmp_path / "level1" / "level2" / "level3").mkdir()
        (tmp_path / "level1" / "level2" / "level3" / "file3.ma").touch()

        files = FinderUtils.find_files_recursive(tmp_path, "*.ma")
        assert len(files) == 3

    def test_find_files_with_depth_limit(self, tmp_path):
        """Test recursive search with depth limit."""
        # Create test structure
        (tmp_path / "level1").mkdir()
        (tmp_path / "file0.ma").touch()  # Depth 0
        (tmp_path / "level1" / "file1.ma").touch()  # Depth 1
        (tmp_path / "level1" / "level2").mkdir()
        (tmp_path / "level1" / "level2" / "file2.ma").touch()  # Depth 2

        # Depth 0: only file0.ma
        files = FinderUtils.find_files_recursive(tmp_path, "*.ma", max_depth=0)
        assert len(files) == 1
        assert "file0.ma" in [f.name for f in files]

        # Depth 1: file0.ma and file1.ma
        files = FinderUtils.find_files_recursive(tmp_path, "*.ma", max_depth=1)
        assert len(files) == 2

        # Depth 2: all files
        files = FinderUtils.find_files_recursive(tmp_path, "*.ma", max_depth=2)
        assert len(files) == 3

    def test_nonexistent_root_returns_empty(self):
        """Test that nonexistent root returns empty list."""
        files = FinderUtils.find_files_recursive(Path("/nonexistent"), "*.ma")
        assert files == []

    def test_complex_pattern(self, tmp_path):
        """Test with complex glob pattern."""
        # Create mixed file types
        (tmp_path / "file1.ma").touch()
        (tmp_path / "file2.mb").touch()
        (tmp_path / "file3.txt").touch()
        (tmp_path / "scene_v001.ma").touch()

        # Find versioned Maya files
        files = FinderUtils.find_files_recursive(tmp_path, "*_v*.ma")
        assert len(files) == 1
        assert files[0].name == "scene_v001.ma"