"""Unit tests for BaseSceneFinder class."""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

import pytest

from base_scene_finder import BaseSceneFinder


class ConcreteSceneFinder(BaseSceneFinder):
    """Concrete implementation for testing."""

    VERSION_PATTERN = re.compile(r"_v(\d{3})\.test$")

    def get_scene_paths(self, user_dir: Path) -> list[Path]:
        """Get test scene directories."""
        test_scenes = user_dir / "test" / "scenes"
        return [test_scenes] if test_scenes.exists() else []

    def get_file_extensions(self) -> list[str]:
        """Get test file extensions."""
        return [".test"]


class TestBaseSceneFinder:
    """Test BaseSceneFinder abstract base class."""

    def test_initialization(self) -> None:
        """Test that concrete finder initializes correctly."""
        finder = ConcreteSceneFinder()
        assert finder is not None
        assert finder.VERSION_PATTERN is not None

    # Test removed: VERSION_PATTERN is now enforced by type system (Pattern[str] not Optional)
    # Subclasses must define VERSION_PATTERN at class level or basedpyright will error

    def test_find_latest_scene_with_files(self, tmp_path: Path) -> None:
        """Test finding latest scene with multiple versions."""
        workspace = tmp_path / "workspace"
        test_scenes = workspace / "user" / "alice" / "test" / "scenes"
        test_scenes.mkdir(parents=True)

        # Create versioned files
        (test_scenes / "scene_v001.test").touch()
        (test_scenes / "scene_v002.test").touch()
        (test_scenes / "scene_v003.test").touch()

        finder = ConcreteSceneFinder()
        latest = finder.find_latest_scene(str(workspace))

        assert latest is not None
        assert latest.name == "scene_v003.test"

    def test_find_latest_scene_no_workspace(self) -> None:
        """Test behavior with nonexistent workspace."""
        finder = ConcreteSceneFinder()
        result = finder.find_latest_scene("/nonexistent/path")
        assert result is None

    def test_find_latest_scene_empty_workspace(self, tmp_path: Path) -> None:
        """Test behavior with empty workspace."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        finder = ConcreteSceneFinder()
        result = finder.find_latest_scene(str(workspace))
        assert result is None

    def test_find_all_scenes(self, tmp_path: Path) -> None:
        """Test finding all scene files."""
        workspace = tmp_path / "workspace"
        test_scenes = workspace / "user" / "bob" / "test" / "scenes"
        test_scenes.mkdir(parents=True)

        # Create files
        files = [
            "scene_v001.test",
            "scene_v002.test",
            "scene_v003.test",
        ]
        for f in files:
            (test_scenes / f).touch()

        finder = ConcreteSceneFinder()
        all_scenes = finder.find_all_scenes(str(workspace))

        assert len(all_scenes) == 3
        assert all(f.suffix == ".test" for f in all_scenes)
        # Should be sorted by version
        assert all_scenes[0].name == "scene_v001.test"
        assert all_scenes[2].name == "scene_v003.test"

    def test_find_all_scenes_include_unversioned(self, tmp_path: Path) -> None:
        """Test finding all files including unversioned."""
        workspace = tmp_path / "workspace"
        test_scenes = workspace / "user" / "charlie" / "test" / "scenes"
        test_scenes.mkdir(parents=True)

        # Create versioned and unversioned files
        (test_scenes / "scene_v001.test").touch()
        (test_scenes / "backup.test").touch()
        (test_scenes / "temp.test").touch()

        finder = ConcreteSceneFinder()
        all_scenes = finder.find_all_scenes(str(workspace), include_all=True)

        assert len(all_scenes) == 3
        names = {f.name for f in all_scenes}
        assert "backup.test" in names
        assert "temp.test" in names

    def test_multiple_users(self, tmp_path: Path) -> None:
        """Test finding scenes across multiple users."""
        workspace = tmp_path / "workspace"

        # User 1
        user1_scenes = workspace / "user" / "alice" / "test" / "scenes"
        user1_scenes.mkdir(parents=True)
        (user1_scenes / "scene_v001.test").touch()
        (user1_scenes / "scene_v003.test").touch()

        # User 2
        user2_scenes = workspace / "user" / "bob" / "test" / "scenes"
        user2_scenes.mkdir(parents=True)
        (user2_scenes / "scene_v002.test").touch()
        (user2_scenes / "scene_v004.test").touch()

        finder = ConcreteSceneFinder()
        latest = finder.find_latest_scene(str(workspace))

        assert latest is not None
        assert latest.name == "scene_v004.test"
        assert "bob" in str(latest)

    def test_subdirectory_search(self, tmp_path: Path) -> None:
        """Test searching in subdirectories."""
        workspace = tmp_path / "workspace"
        test_scenes = workspace / "user" / "dave" / "test" / "scenes"
        subdir = test_scenes / "subdir"
        subdir.mkdir(parents=True)

        # Files in main dir and subdir
        (test_scenes / "scene_v001.test").touch()
        (subdir / "scene_v002.test").touch()

        finder = ConcreteSceneFinder()
        latest = finder.find_latest_scene(str(workspace))

        assert latest is not None
        assert latest.name == "scene_v002.test"

    def test_filter_autosave_files(self, tmp_path: Path) -> None:
        """Test filtering autosave files."""
        files = [
            tmp_path / "scene_v001.test",
            tmp_path / "scene_v001.test.autosave",
            tmp_path / "scene_autosave.test",
            tmp_path / "scene_v002.test",
        ]
        for f in files:
            f.touch()

        finder = ConcreteSceneFinder()
        filtered = finder.filter_autosave_files(files)

        assert len(filtered) == 2
        assert all("autosave" not in f.name for f in filtered)

    def test_filter_by_pattern(self, tmp_path: Path) -> None:
        """Test filtering files by regex pattern."""
        files = [
            tmp_path / "scene_v001.test",
            tmp_path / "model_v001.test",
            tmp_path / "scene_v002.test",
            tmp_path / "rig_v001.test",
        ]
        for f in files:
            f.touch()

        finder = ConcreteSceneFinder()
        # Filter for scene files only
        filtered = finder.filter_by_pattern(files, r"scene_")

        assert len(filtered) == 2
        assert all("scene" in f.name for f in filtered)

    def test_group_by_user(self, tmp_path: Path) -> None:
        """Test grouping files by user."""
        files = [
            tmp_path / "workspace" / "user" / "alice" / "test" / "file1.test",
            tmp_path / "workspace" / "user" / "alice" / "test" / "file2.test",
            tmp_path / "workspace" / "user" / "bob" / "test" / "file3.test",
            tmp_path / "workspace" / "user" / "charlie" / "test" / "file4.test",
        ]

        finder = ConcreteSceneFinder()
        grouped = finder.group_by_user(files)

        assert len(grouped) == 3
        assert len(grouped["alice"]) == 2
        assert len(grouped["bob"]) == 1
        assert len(grouped["charlie"]) == 1

    @pytest.mark.parametrize(
        "workspace",
        [None, ""],
        ids=["none", "empty_string"],
    )
    def test_validate_workspace_returns_none(self, workspace: str | None) -> None:
        """Test workspace validation returns None for invalid inputs."""
        finder = ConcreteSceneFinder()
        result = finder._validate_workspace(workspace)
        assert result is None

    def test_validate_workspace_valid(self, tmp_path: Path) -> None:
        """Test workspace validation with valid path."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        finder = ConcreteSceneFinder()
        result = finder._validate_workspace(str(workspace))

        assert result is not None
        assert result == workspace

    def test_logging_shot_name(self, tmp_path: Path) -> None:
        """Test that shot name is used in logging."""
        workspace = tmp_path / "workspace"
        test_scenes = workspace / "user" / "alice" / "test" / "scenes"
        test_scenes.mkdir(parents=True)
        (test_scenes / "scene_v001.test").touch()

        finder = ConcreteSceneFinder()

        with patch.object(finder.logger, "info") as mock_log:
            finder.find_latest_scene(str(workspace), shot_name="TEST_SHOT")
            mock_log.assert_called()
            assert "TEST_SHOT" in mock_log.call_args[0][0]

    def test_no_user_directory(self, tmp_path: Path) -> None:
        """Test behavior when user directory doesn't exist."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        # No user subdirectory

        finder = ConcreteSceneFinder()
        result = finder.find_latest_scene(str(workspace))
        assert result is None

    def test_empty_scene_directory(self, tmp_path: Path) -> None:
        """Test behavior with empty scene directory."""
        workspace = tmp_path / "workspace"
        test_scenes = workspace / "user" / "alice" / "test" / "scenes"
        test_scenes.mkdir(parents=True)
        # No files in directory

        finder = ConcreteSceneFinder()
        result = finder.find_latest_scene(str(workspace))
        assert result is None

    def test_files_without_version(self, tmp_path: Path) -> None:
        """Test that files without version are ignored in find_latest."""
        workspace = tmp_path / "workspace"
        test_scenes = workspace / "user" / "alice" / "test" / "scenes"
        test_scenes.mkdir(parents=True)

        # Create files without version
        (test_scenes / "scene.test").touch()
        (test_scenes / "backup.test").touch()

        finder = ConcreteSceneFinder()
        result = finder.find_latest_scene(str(workspace))
        assert result is None  # No versioned files
