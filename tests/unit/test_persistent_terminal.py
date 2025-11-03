#!/usr/bin/env python3
"""Test script for the persistent terminal implementation."""

# Standard library imports
import logging
from typing import TYPE_CHECKING


# Third-party imports

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication

# Local application imports
from persistent_terminal_manager import PersistentTerminalManager


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def test_persistent_terminal_manager_creation(qapp: "QApplication") -> None:
    """Test that PersistentTerminalManager can be created."""
    # This is a basic smoke test - actual terminal functionality
    # requires GUI and is tested manually
    manager = PersistentTerminalManager()
    assert manager is not None

    # Cleanup without trying to use terminal
    manager.cleanup_fifo_only()
