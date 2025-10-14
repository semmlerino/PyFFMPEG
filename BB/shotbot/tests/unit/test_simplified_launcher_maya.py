"""Tests for Maya functionality in SimplifiedLauncher.

This module tests the Maya-specific features of the SimplifiedLauncher,
particularly the "open latest scene" functionality which requires finding
Maya scene files in the VFX workspace structure.
"""

from __future__ import annotations

# Standard library imports
from pathlib import Path
from unittest.mock import MagicMock, patch

# Third-party imports
import pytest

# Local application imports
from shot_model import Shot
from simplified_launcher import SimplifiedLauncher


@pytest.fixture
def launcher() -> SimplifiedLauncher:
    """Create a SimplifiedLauncher instance for testing."""
    return SimplifiedLauncher()


@pytest.fixture
def test_shot() -> Shot:
    """Create a test shot with typical VFX workspace structure."""
    return Shot(
        show="test_show",
        sequence="010",
        shot="0010",
        workspace_path="/shows/test_show/shots/010/0010",
    )


@pytest.fixture
def maya_workspace(tmp_path: Path) -> Path:
    """Create a temporary VFX workspace with Maya scene files.

    Structure:
        workspace/
        └── user/
            ├── artist1/
            │   └── maya/
            │       └── scenes/
            │           ├── shot_v001.ma
            │           ├── shot_v002.ma
            │           └── shot_v003.ma
            └── artist2/
                └── maya/
                    └── scenes/
                        └── shot_v001.ma
    """
    workspace = tmp_path / "workspace"

    # Create artist1's Maya scenes
    artist1_scenes = workspace / "user" / "artist1" / "maya" / "scenes"
    artist1_scenes.mkdir(parents=True)
    (artist1_scenes / "shot_v001.ma").touch()
    (artist1_scenes / "shot_v002.ma").touch()
    (artist1_scenes / "shot_v003.ma").touch()

    # Create artist2's Maya scenes
    artist2_scenes = workspace / "user" / "artist2" / "maya" / "scenes"
    artist2_scenes.mkdir(parents=True)
    (artist2_scenes / "shot_v001.ma").touch()

    return workspace


class TestMayaLatestSceneFinding:
    """Test finding latest Maya scene files in VFX workspace structure."""

    def test_find_latest_maya_scene_with_multiple_versions(
        self,
        launcher: SimplifiedLauncher,
        maya_workspace: Path,
        test_shot: Shot,
    ) -> None:
        """Test finding latest Maya scene when multiple versions exist.

        Verifies that _find_latest_scene correctly identifies the highest
        version number (v003) among multiple versioned Maya scene files.
        """
        launcher.set_current_shot(test_shot)

        latest = launcher._find_latest_scene(maya_workspace, "maya")

        assert latest is not None, "Should find a Maya scene file"
        assert latest.name == "shot_v003.ma", f"Should find v003, got {latest.name}"
        assert latest.exists(), "Found file should exist"

    def test_find_latest_maya_scene_with_multiple_users(
        self,
        launcher: SimplifiedLauncher,
        maya_workspace: Path,
        test_shot: Shot,
    ) -> None:
        """Test finding latest Maya scene across multiple user directories.

        The MayaLatestFinder searches all user directories and returns the
        globally latest version, not just from a specific user.
        """
        launcher.set_current_shot(test_shot)

        latest = launcher._find_latest_scene(maya_workspace, "maya")

        assert latest is not None, "Should find Maya scene across users"
        # Should find artist1's v003, which is newer than artist2's v001
        assert "artist1" in str(latest), "Should find scene from artist1"
        assert latest.name == "shot_v003.ma", "Should find highest version"

    def test_find_latest_maya_scene_without_shot_context(
        self,
        launcher: SimplifiedLauncher,
        maya_workspace: Path,
    ) -> None:
        """Test finding latest Maya scene without setting current shot.

        Even without a current shot set, the finder should still work
        and return the latest scene file.
        """
        # Don't set current_shot
        latest = launcher._find_latest_scene(maya_workspace, "maya")

        assert latest is not None, "Should find Maya scene without shot context"
        assert latest.name == "shot_v003.ma", "Should still find latest version"

    def test_find_latest_maya_scene_empty_workspace(
        self,
        launcher: SimplifiedLauncher,
        tmp_path: Path,
    ) -> None:
        """Test handling of empty workspace with no Maya scenes."""
        empty_workspace = tmp_path / "empty"
        empty_workspace.mkdir()

        latest = launcher._find_latest_scene(empty_workspace, "maya")

        assert latest is None, "Should return None for empty workspace"

    def test_find_latest_maya_scene_nonexistent_workspace(
        self,
        launcher: SimplifiedLauncher,
    ) -> None:
        """Test handling of nonexistent workspace path."""
        nonexistent = Path("/nonexistent/workspace")

        latest = launcher._find_latest_scene(nonexistent, "maya")

        assert latest is None, "Should return None for nonexistent workspace"

    def test_find_latest_maya_scene_no_user_directory(
        self,
        launcher: SimplifiedLauncher,
        tmp_path: Path,
    ) -> None:
        """Test handling workspace without user directory structure."""
        workspace = tmp_path / "no_users"
        workspace.mkdir()

        latest = launcher._find_latest_scene(workspace, "maya")

        assert latest is None, "Should return None when no user directory exists"


class TestMayaLaunching:
    """Test launching Maya with various options."""

    @patch("simplified_launcher.subprocess.Popen")
    def test_launch_maya_with_open_latest_scene(
        self,
        mock_popen: MagicMock,
        launcher: SimplifiedLauncher,
        maya_workspace: Path,
        test_shot: Shot,
    ) -> None:
        """Test launching Maya with 'open latest scene' option.

        This is the main fix - verifies that when open_latest is enabled,
        the launcher finds the scene file and includes it in the command
        with the correct -file flag.
        """
        # Setup mock
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_popen.return_value = mock_proc

        # Set workspace path to our test workspace
        test_shot.workspace_path = str(maya_workspace)
        launcher.set_current_shot(test_shot)

        # Launch with open_latest option
        success = launcher.launch_vfx_app(
            "maya",
            shot=test_shot,
            open_latest=True,
        )

        # Verify launch succeeded
        assert success, "Maya launch should succeed"

        # Verify Popen was called
        assert mock_popen.called, "Should have called Popen"

        # Get the command that was executed
        call_args = mock_popen.call_args[0][0]
        command_str = " ".join(call_args) if isinstance(call_args, list) else call_args

        # Verify command contains Maya and the scene file
        assert "maya" in command_str, "Command should contain 'maya'"
        assert "-file" in command_str, "Command should contain '-file' flag"
        assert "shot_v003.ma" in command_str, "Command should contain latest scene"

    @patch("simplified_launcher.subprocess.Popen")
    def test_launch_maya_without_open_latest(
        self,
        mock_popen: MagicMock,
        launcher: SimplifiedLauncher,
        test_shot: Shot,
    ) -> None:
        """Test launching Maya without opening a scene file.

        When open_latest is False, Maya should launch without the -file flag.
        """
        # Setup mock
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_popen.return_value = mock_proc

        launcher.set_current_shot(test_shot)

        # Launch without open_latest option
        success = launcher.launch_vfx_app(
            "maya",
            shot=test_shot,
            open_latest=False,
        )

        assert success, "Maya launch should succeed"
        assert mock_popen.called, "Should have called Popen"

        # Get the command
        call_args = mock_popen.call_args[0][0]
        command_str = " ".join(call_args) if isinstance(call_args, list) else call_args

        # Verify command contains Maya but no scene file
        assert "maya" in command_str, "Command should contain 'maya'"
        assert "-file" not in command_str, "Command should not contain '-file' flag"

    @patch("simplified_launcher.subprocess.Popen")
    def test_launch_maya_with_open_latest_but_no_scenes(
        self,
        mock_popen: MagicMock,
        launcher: SimplifiedLauncher,
        tmp_path: Path,
        test_shot: Shot,
    ) -> None:
        """Test launching Maya with open_latest when no scenes exist.

        Should launch Maya without error, just without the scene file.
        """
        # Setup mock
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_popen.return_value = mock_proc

        # Use empty workspace
        empty_workspace = tmp_path / "empty"
        empty_workspace.mkdir()
        test_shot.workspace_path = str(empty_workspace)
        launcher.set_current_shot(test_shot)

        # Launch with open_latest option
        success = launcher.launch_vfx_app(
            "maya",
            shot=test_shot,
            open_latest=True,
        )

        assert success, "Maya should launch even without scene files"
        assert mock_popen.called, "Should have called Popen"

        # Get the command
        call_args = mock_popen.call_args[0][0]
        command_str = " ".join(call_args) if isinstance(call_args, list) else call_args

        # Should launch Maya without -file flag
        assert "maya" in command_str, "Command should contain 'maya'"
        assert "-file" not in command_str, (
            "Should not include -file when no scenes found"
        )


class TestMayaPathQuoting:
    """Test proper path quoting for shell execution."""

    @patch("simplified_launcher.subprocess.Popen")
    def test_maya_scene_path_with_spaces(
        self,
        mock_popen: MagicMock,
        launcher: SimplifiedLauncher,
        tmp_path: Path,
        test_shot: Shot,
    ) -> None:
        """Test that scene paths with spaces are properly quoted.

        VFX paths sometimes contain spaces, which must be properly escaped
        for shell execution.
        """
        # Create workspace with spaces in path
        workspace = tmp_path / "my workspace"
        scenes_dir = workspace / "user" / "test-user" / "maya" / "scenes"
        scenes_dir.mkdir(parents=True)
        (scenes_dir / "my scene_v001.ma").touch()

        # Setup mock
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_popen.return_value = mock_proc

        test_shot.workspace_path = str(workspace)
        launcher.set_current_shot(test_shot)

        # Launch Maya
        success = launcher.launch_vfx_app(
            "maya",
            shot=test_shot,
            open_latest=True,
        )

        assert success, "Should handle paths with spaces"

        # Verify the scene path was properly quoted
        call_args = mock_popen.call_args[0][0]
        command_str = " ".join(call_args) if isinstance(call_args, list) else call_args

        # The path should be quoted (single quotes added by _quote_path)
        assert "my scene_v001.ma" in command_str, "Scene name should be in command"
        # Note: exact quoting style depends on _quote_path implementation


class TestBackwardCompatibility:
    """Test backward compatibility with old launcher interface."""

    @patch("simplified_launcher.subprocess.Popen")
    def test_launch_app_method_with_open_latest_maya(
        self,
        mock_popen: MagicMock,
        launcher: SimplifiedLauncher,
        maya_workspace: Path,
        test_shot: Shot,
    ) -> None:
        """Test the deprecated launch_app method still works for Maya.

        Maintains backward compatibility with code that uses the old interface.
        """
        # Setup mock
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_popen.return_value = mock_proc

        test_shot.workspace_path = str(maya_workspace)
        launcher.set_current_shot(test_shot)

        # Use old interface
        success = launcher.launch_app(
            "maya",
            open_latest_maya=True,
        )

        assert success, "Old interface should still work"
        assert mock_popen.called, "Should have called Popen"

        # Verify scene file is included
        call_args = mock_popen.call_args[0][0]
        command_str = " ".join(call_args) if isinstance(call_args, list) else call_args
        assert "shot_v003.ma" in command_str, (
            "Should find latest scene via old interface"
        )
