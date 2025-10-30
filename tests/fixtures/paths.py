"""Path and filesystem-related test fixtures.

Example fixtures for working with paths, directories, and VFX workspace structures.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest


@pytest.fixture
def mock_vfx_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a temporary VFX root directory structure.

    Sets Config.SHOWS_ROOT to the temporary directory.
    Creates basic VFX directory structure.

    Returns:
        Path to the mock VFX root directory
    """
    from config import Config

    vfx_root = tmp_path / "shows"
    vfx_root.mkdir()

    # Set Config.SHOWS_ROOT to our temp directory
    monkeypatch.setattr(Config, "SHOWS_ROOT", str(vfx_root))

    return vfx_root


@pytest.fixture
def make_vfx_shot(mock_vfx_root: Path) -> Callable[[str, str, str], Path]:
    """Factory to create VFX shot directory structures.

    Args:
        show: Show name
        sequence: Sequence name
        shot: Shot name

    Returns:
        Path to the created shot directory
    """

    def _create_shot(show: str, sequence: str, shot: str) -> Path:
        """Create a VFX shot directory structure."""
        shot_dir = mock_vfx_root / show / "shots" / sequence / f"{sequence}_{shot}"
        shot_dir.mkdir(parents=True, exist_ok=True)
        return shot_dir

    return _create_shot


@pytest.fixture
def make_user_workspace(
    mock_vfx_root: Path,
) -> Callable[[str, str, str, str, str], Path]:
    """Factory to create user workspace directories.

    Args:
        show: Show name
        sequence: Sequence name
        shot: Shot name
        username: User name
        app: Application name (maya, nuke, 3de)

    Returns:
        Path to the created user workspace
    """

    def _create_workspace(
        show: str, sequence: str, shot: str, username: str, app: str
    ) -> Path:
        """Create a user workspace directory."""
        shot_dir = mock_vfx_root / show / "shots" / sequence / f"{sequence}_{shot}"

        if app == "3de":
            workspace = (
                shot_dir
                / "user"
                / username
                / "mm"
                / "3de"
                / "mm-default"
                / "scenes"
                / "scene"
            )
        else:
            workspace = shot_dir / "user" / username / app / "scenes"

        workspace.mkdir(parents=True, exist_ok=True)
        return workspace

    return _create_workspace
