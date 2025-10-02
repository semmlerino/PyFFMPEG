"""Unit test fixtures and configuration."""

from __future__ import annotations

import pytest


@pytest.fixture
def mock_shows_root(monkeypatch: pytest.MonkeyPatch):
    """Mock Config.SHOWS_ROOT for VFX path testing.

    Sets SHOWS_ROOT to a test path that many tests expect.
    Can be used as a simple fixture parameter to avoid @patch decorators.
    """
    from config import Config

    monkeypatch.setattr(Config, "SHOWS_ROOT", "/tmp/mock_vfx/shows")
    return "/tmp/mock_vfx/shows"
