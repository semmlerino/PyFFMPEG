"""Unit test fixtures and configuration."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def mock_shows_root(monkeypatch: pytest.MonkeyPatch) -> str:
    """Mock Config.SHOWS_ROOT for VFX path testing.

    Sets SHOWS_ROOT to /shows, which:
    1. Doesn't exist on dev machines (preventing filesystem access)
    2. Matches hardcoded paths in test data (workspace /shows/...)
    3. Ensures consistent path behavior across all unit tests

    Can be used as a simple fixture parameter to avoid @patch decorators.
    """
    from config import (
        Config,
    )

    monkeypatch.setattr(Config, "SHOWS_ROOT", "/shows")
    return "/shows"
