"""Qt safety fixtures to prevent common test failures.

This module provides autouse fixtures that prevent Qt-related test failures
by suppressing modal dialogs and preventing application exit calls that
would corrupt the event loop.

These fixtures are ALWAYS active (autouse=True) because the issues they
prevent can cascade through the entire test suite.

Fixtures:
    suppress_qmessagebox: Auto-dismiss modal dialogs (autouse)
    prevent_qapp_exit: Prevent QApplication exit/quit calls (autouse)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication


@pytest.fixture(autouse=True)
def suppress_qmessagebox(monkeypatch: pytest.MonkeyPatch) -> None:
    """Auto-dismiss modal dialogs to prevent blocking tests.

    This autouse fixture provides default mocks for QMessageBox to prevent
    real dialogs from appearing. Individual tests can override these mocks
    with their own monkeypatch calls - test-specific patches take priority.

    Critical for:
    - Preventing real widgets from appearing ("getting real widgets" issue)
    - Avoiding timeouts from modal dialogs waiting for user input
    - Preventing resource exhaustion under high parallel load
    """
    from PySide6.QtWidgets import QMessageBox

    def _ok(*args, **kwargs):
        return QMessageBox.StandardButton.Ok

    def _yes(*args, **kwargs):
        return QMessageBox.StandardButton.Yes

    # Static method patches
    for name in ("information", "warning", "critical"):
        monkeypatch.setattr(QMessageBox, name, _ok, raising=True)
    monkeypatch.setattr(QMessageBox, "question", _yes, raising=True)

    # Instance-style dialog patches (catch .exec() and .open() usage)
    monkeypatch.setattr(QMessageBox, "exec", _ok, raising=True)
    monkeypatch.setattr(QMessageBox, "open", lambda *_args, **_kwargs: None, raising=True)


@pytest.fixture(autouse=True)
def prevent_qapp_exit(monkeypatch: pytest.MonkeyPatch, qapp: QApplication) -> None:
    """Prevent tests from calling QApplication.exit() or quit() which poisons event loops.

    pytest-qt explicitly warns that calling QApplication.exit() in one test
    breaks subsequent tests because it corrupts the event loop state.
    This monkeypatch ensures tests can't accidentally poison the event loop.

    This is critical for large test suites where one bad test can cascade
    failures to all subsequent tests in the same process.

    See: https://pytest-qt.readthedocs.io/en/latest/note_dialogs.html#warning-about-qapplication-exit

    Args:
        monkeypatch: Pytest monkeypatch fixture
        qapp: QApplication fixture from qt_bootstrap
    """
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtWidgets import QApplication

    def _noop(*args, **kwargs) -> None:
        """No-op exit/quit - tests shouldn't exit the application."""

    # Patch both exit and quit (instance + class methods)
    # Code often calls Q(Core)Application.quit() in addition to exit()
    monkeypatch.setattr(qapp, "exit", _noop)
    monkeypatch.setattr(QApplication, "exit", _noop)
    monkeypatch.setattr(qapp, "quit", _noop)
    monkeypatch.setattr(QApplication, "quit", _noop)
    # Also patch QCoreApplication (some code paths use this)
    monkeypatch.setattr(QCoreApplication, "exit", _noop)
    monkeypatch.setattr(QCoreApplication, "quit", _noop)
