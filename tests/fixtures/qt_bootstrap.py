"""Qt application bootstrap module.

HISTORICAL NOTE: This module previously contained the qapp and _patch_qtbot_short_waits
fixtures. These fixtures have been MOVED to tests/conftest.py because:

1. The qapp fixture needs direct access to _GLOBAL_QAPP (created in conftest.py)
2. Session-scoped fixtures work more reliably when defined in conftest.py
3. Fixtures in pytest_plugins modules can have subtle timing issues with xdist

The QApplication bootstrap happens in conftest.py BEFORE pytest_plugins are loaded.
See tests/conftest.py for the authoritative fixture definitions.

This file is kept for documentation purposes only.
"""
