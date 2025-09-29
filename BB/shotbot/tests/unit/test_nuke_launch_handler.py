"""Test the unified Nuke launch handler."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from nuke_launch_handler import NukeLaunchHandler
from shot_model import Shot


@pytest.fixture
def mock_shot():
    """Create a mock shot for testing."""
    shot = Mock(spec=Shot)
    shot.workspace_path = "/test/workspace"
    shot.full_name = "TEST_0010"
    return shot


@pytest.fixture
def nuke_handler():
    """Create a NukeLaunchHandler instance for testing."""
    return NukeLaunchHandler()


class TestNukeLaunchHandler:
    """Test the NukeLaunchHandler class."""

    def test_initialization(self, nuke_handler):
        """Test that handler initializes with required modules."""
        assert nuke_handler.workspace_manager is not None
        assert nuke_handler.script_generator is not None
        assert nuke_handler.raw_plate_finder is not None
        assert nuke_handler.undistortion_finder is not None

    def test_prepare_nuke_command_basic(self, nuke_handler, mock_shot):
        """Test basic command preparation without any options."""
        command, messages = nuke_handler.prepare_nuke_command(mock_shot, "nuke", {})

        assert command == "nuke"
        assert isinstance(messages, list)

    @patch("nuke_launch_handler.Config.NUKE_FIX_OCIO_CRASH", True)
    def test_prepare_nuke_command_with_ocio_fix(self, nuke_handler, mock_shot):
        """Test command preparation with OCIO crash fix enabled."""
        command, messages = nuke_handler.prepare_nuke_command(mock_shot, "nuke", {})

        assert command == "nuke"
        assert any("OCIO" in msg for msg in messages)

    def test_handle_workspace_scripts_open_latest(self, nuke_handler, mock_shot):
        """Test handling workspace scripts when opening latest."""
        with patch.object(
            nuke_handler.workspace_manager, "get_workspace_script_directory"
        ) as mock_get_dir:
            with patch.object(
                nuke_handler.workspace_manager, "find_latest_nuke_script"
            ) as mock_find_latest:
                mock_get_dir.return_value = Path("/test/workspace/comp/nuke")
                mock_find_latest.return_value = Path(
                    "/test/workspace/comp/nuke/TEST_0010_v001.nk"
                )

                options = {"open_latest_scene": True}
                command, messages = nuke_handler._handle_workspace_scripts(
                    mock_shot, "nuke", options
                )

                assert "/TEST_0010_v001.nk" in command
                assert any("Opening existing Nuke script" in msg for msg in messages)

    def test_handle_workspace_scripts_create_new(self, nuke_handler, mock_shot):
        """Test handling workspace scripts when creating new."""
        with patch.object(
            nuke_handler.workspace_manager, "get_workspace_script_directory"
        ) as mock_get_dir:
            with patch.object(
                nuke_handler.workspace_manager, "get_next_script_path"
            ) as mock_get_next:
                with patch.object(
                    nuke_handler, "_create_new_workspace_script"
                ) as mock_create:
                    mock_get_dir.return_value = Path("/test/workspace/comp/nuke")
                    mock_get_next.return_value = (
                        "/test/workspace/comp/nuke/TEST_0010_v002.nk",
                        2,
                    )
                    mock_create.return_value = (
                        "/test/workspace/comp/nuke/TEST_0010_v002.nk"
                    )

                    options = {"create_new_file": True}
                    command, messages = nuke_handler._handle_workspace_scripts(
                        mock_shot, "nuke", options
                    )

                    assert "/TEST_0010_v002.nk" in command
                    assert any(
                        "Creating new Nuke script version: v002" in msg
                        for msg in messages
                    )

    def test_handle_workspace_scripts_priority(self, nuke_handler, mock_shot):
        """Test that open_latest_scene takes priority over create_new_file."""
        with patch.object(
            nuke_handler.workspace_manager, "get_workspace_script_directory"
        ) as mock_get_dir:
            with patch.object(
                nuke_handler.workspace_manager, "find_latest_nuke_script"
            ) as mock_find_latest:
                mock_get_dir.return_value = Path("/test/workspace/comp/nuke")
                mock_find_latest.return_value = Path(
                    "/test/workspace/comp/nuke/TEST_0010_v001.nk"
                )

                options = {"open_latest_scene": True, "create_new_file": True}
                command, messages = nuke_handler._handle_workspace_scripts(
                    mock_shot, "nuke", options
                )

                # Should open latest, not create new
                assert "/TEST_0010_v001.nk" in command
                assert any("Opening existing Nuke script" in msg for msg in messages)
                assert not any("Creating new" in msg for msg in messages)

    def test_handle_media_loading_plate_only(self, nuke_handler, mock_shot):
        """Test media loading with plate only."""
        with patch.object(
            nuke_handler.raw_plate_finder, "find_latest_raw_plate"
        ) as mock_find_plate:
            with patch.object(
                nuke_handler.raw_plate_finder, "verify_plate_exists"
            ) as mock_verify:
                with patch.object(
                    nuke_handler.script_generator, "create_plate_script"
                ) as mock_create_script:
                    with patch.object(
                        nuke_handler.raw_plate_finder, "get_version_from_path"
                    ) as mock_get_version:
                        mock_find_plate.return_value = "/test/plates/TEST_0010_v001.exr"
                        mock_verify.return_value = True
                        mock_create_script.return_value = "/tmp/nuke_script.nk"
                        mock_get_version.return_value = "v001"

                        options = {"include_raw_plate": True}
                        command, messages = nuke_handler._handle_media_loading(
                            mock_shot, "nuke", options
                        )

                        assert "/tmp/nuke_script.nk" in command
                        assert any(
                            "Generated Nuke script with plate: v001" in msg
                            for msg in messages
                        )

    def test_handle_media_loading_undistortion_only(self, nuke_handler, mock_shot):
        """Test media loading with undistortion only."""
        with patch.object(
            nuke_handler.undistortion_finder, "find_latest_undistortion"
        ) as mock_find_undist:
            with patch.object(
                nuke_handler.undistortion_finder, "get_version_from_path"
            ) as mock_get_version:
                with patch(
                    "nuke_launch_handler.Config.NUKE_UNDISTORTION_MODE", "direct"
                ):
                    mock_find_undist.return_value = Path(
                        "/test/undist/TEST_0010_v001.nk"
                    )
                    mock_get_version.return_value = "v001"

                    options = {"include_undistortion": True}
                    command, messages = nuke_handler._handle_media_loading(
                        mock_shot, "nuke", options
                    )

                    assert "/test/undist/TEST_0010_v001.nk" in command
                    assert any(
                        "Opening undistortion file directly: v001" in msg
                        for msg in messages
                    )

    def test_handle_media_loading_plate_and_undistortion(self, nuke_handler, mock_shot):
        """Test media loading with both plate and undistortion."""
        with patch.object(
            nuke_handler.raw_plate_finder, "find_latest_raw_plate"
        ) as mock_find_plate:
            with patch.object(
                nuke_handler.raw_plate_finder, "verify_plate_exists"
            ) as mock_verify:
                with patch.object(
                    nuke_handler.undistortion_finder, "find_latest_undistortion"
                ) as mock_find_undist:
                    with patch.object(
                        nuke_handler.script_generator, "create_loader_script"
                    ) as mock_create_loader:
                        with patch(
                            "nuke_launch_handler.Config.NUKE_USE_LOADER_SCRIPT", True
                        ):
                            mock_find_plate.return_value = (
                                "/test/plates/TEST_0010_v001.exr"
                            )
                            mock_verify.return_value = True
                            mock_find_undist.return_value = Path(
                                "/test/undist/TEST_0010_v001.nk"
                            )
                            mock_create_loader.return_value = "/tmp/loader_script.nk"

                            # Mock version getters
                            with patch.object(
                                nuke_handler.raw_plate_finder, "get_version_from_path"
                            ) as mock_plate_ver:
                                with patch.object(
                                    nuke_handler.undistortion_finder,
                                    "get_version_from_path",
                                ) as mock_undist_ver:
                                    mock_plate_ver.return_value = "v001"
                                    mock_undist_ver.return_value = "v002"

                                    options = {
                                        "include_raw_plate": True,
                                        "include_undistortion": True,
                                    }
                                    command, messages = (
                                        nuke_handler._handle_media_loading(
                                            mock_shot, "nuke", options
                                        )
                                    )

                                    assert "/tmp/loader_script.nk" in command
                                    assert any(
                                        "Created loader script" in msg
                                        for msg in messages
                                    )
                                    assert any(
                                        "(v001)" in msg and "(v002)" in msg
                                        for msg in messages
                                    )

    def test_get_environment_fixes_disabled(self, nuke_handler):
        """Test environment fixes when disabled."""
        with patch("nuke_launch_handler.Config.NUKE_FIX_OCIO_CRASH", False):
            fixes = nuke_handler.get_environment_fixes()
            assert fixes == ""

    def test_get_environment_fixes_with_problematic_plugins(self, nuke_handler):
        """Test environment fixes with problematic plugin paths."""
        with patch("nuke_launch_handler.Config.NUKE_FIX_OCIO_CRASH", True):
            with patch(
                "nuke_launch_handler.Config.NUKE_SKIP_PROBLEMATIC_PLUGINS", True
            ):
                with patch(
                    "nuke_launch_handler.Config.NUKE_PROBLEMATIC_PLUGIN_PATHS",
                    ["/bad/plugin1", "/bad/plugin2"],
                ):
                    fixes = nuke_handler.get_environment_fixes()

                    assert "FILTERED_NUKE_PATH" in fixes
                    assert "grep -v" in fixes
                    assert "NUKE_DISABLE_CRASH_REPORTING=1" in fixes

    def test_get_environment_fixes_with_ocio_fallback(self, nuke_handler):
        """Test environment fixes with OCIO fallback config."""
        with patch("nuke_launch_handler.Config.NUKE_FIX_OCIO_CRASH", True):
            with patch(
                "nuke_launch_handler.Config.NUKE_OCIO_FALLBACK_CONFIG",
                "/test/ocio/config.ocio",
            ):
                with patch("nuke_launch_handler.os.path.exists") as mock_exists:
                    mock_exists.return_value = True
                    fixes = nuke_handler.get_environment_fixes()

                    assert 'export OCIO="/test/ocio/config.ocio"' in fixes
                    assert "NUKE_DISABLE_CRASH_REPORTING=1" in fixes

    def test_create_new_workspace_script_with_plate(self, nuke_handler, mock_shot):
        """Test creating new workspace script with plate."""
        with patch.object(
            nuke_handler.raw_plate_finder, "find_latest_raw_plate"
        ) as mock_find:
            with patch.object(
                nuke_handler.raw_plate_finder, "verify_plate_exists"
            ) as mock_verify:
                with patch.object(
                    nuke_handler.script_generator, "create_workspace_plate_script"
                ) as mock_create:
                    mock_find.return_value = "/test/plates/TEST_0010_v001.exr"
                    mock_verify.return_value = True
                    mock_create.return_value = (
                        "/test/workspace/comp/nuke/TEST_0010_v001.nk"
                    )

                    options = {"include_raw_plate": True}
                    result = nuke_handler._create_new_workspace_script(
                        mock_shot, 1, options
                    )

                    assert result == "/test/workspace/comp/nuke/TEST_0010_v001.nk"
                    mock_create.assert_called_once_with(
                        "/test/plates/TEST_0010_v001.exr",
                        "/test/workspace",
                        "TEST_0010",
                        version=1,
                    )

    def test_create_new_workspace_script_empty(self, nuke_handler, mock_shot):
        """Test creating new empty workspace script."""
        with patch.object(
            nuke_handler.script_generator, "create_plate_script"
        ) as mock_create:
            with patch.object(
                nuke_handler.script_generator, "save_workspace_script"
            ) as mock_save:
                with patch("builtins.open", create=True) as mock_open:
                    mock_open.return_value.__enter__.return_value.read.return_value = (
                        "<nuke_script_content>"
                    )
                    mock_create.return_value = "/tmp/temp_script.nk"
                    mock_save.return_value = (
                        "/test/workspace/comp/nuke/TEST_0010_v001.nk"
                    )

                    options = {}
                    result = nuke_handler._create_new_workspace_script(
                        mock_shot, 1, options
                    )

                    assert result == "/test/workspace/comp/nuke/TEST_0010_v001.nk"
                    mock_create.assert_called_once_with("", "TEST_0010")
                    mock_save.assert_called_once_with(
                        "<nuke_script_content>",
                        "/test/workspace",
                        "TEST_0010",
                        version=1,
                    )
