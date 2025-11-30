"""Subprocess smoke tests - run in CI, skip locally with SHOTBOT_SKIP_SMOKE=1.

These tests use real subprocess execution to verify that basic shell operations
work correctly. They're useful for catching environment issues and ensuring
the subprocess infrastructure is functional.

Run explicitly:
    pytest tests/integration/test_subprocess_smoke.py -v

Skip locally (default in development):
    SHOTBOT_SKIP_SMOKE=1 pytest tests/

In CI:
    These tests run by default (CI env var is set)
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest


# Apply markers to entire module
pytestmark = [
    pytest.mark.smoke,
    pytest.mark.real_subprocess,
    pytest.mark.skipif(
        os.environ.get("SHOTBOT_SKIP_SMOKE", "0") == "1"
        and os.environ.get("CI") != "true"
        and os.environ.get("GITHUB_ACTIONS") != "true",
        reason="Smoke tests skipped locally (SHOTBOT_SKIP_SMOKE=1)",
    ),
]


class TestSubprocessSmoke:
    """Smoke tests verifying basic subprocess functionality."""

    def test_basic_echo(self) -> None:
        """Verify subprocess.run with echo works."""
        result = subprocess.run(
            ["echo", "smoke-test-ok"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 0
        assert "smoke-test-ok" in result.stdout

    def test_python_subprocess(self) -> None:
        """Verify Python subprocess execution works."""
        result = subprocess.run(
            [sys.executable, "-c", "print('subprocess-python-ok')"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "subprocess-python-ok" in result.stdout

    def test_subprocess_popen(self) -> None:
        """Verify Popen works correctly."""
        proc = subprocess.Popen(
            ["echo", "popen-test-ok"],
            stdout=subprocess.PIPE,
            text=True,
        )
        stdout, _ = proc.communicate(timeout=5)
        assert proc.returncode == 0
        assert "popen-test-ok" in stdout

    def test_nonzero_exit(self) -> None:
        """Verify subprocess handles non-zero exit codes."""
        result = subprocess.run(
            [sys.executable, "-c", "import sys; sys.exit(42)"],
            capture_output=True,
            timeout=10,
        )
        assert result.returncode == 42

    def test_stderr_capture(self) -> None:
        """Verify stderr is captured correctly."""
        result = subprocess.run(
            [sys.executable, "-c", "import sys; print('error', file=sys.stderr)"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "error" in result.stderr


class TestBashShellSmoke:
    """Smoke tests for bash shell operations used by CommandLauncher."""

    @pytest.mark.skipif(
        not os.path.exists("/bin/bash"),
        reason="bash not available",
    )
    def test_bash_interactive_login(self) -> None:
        """Verify bash -ilc works (used by CommandLauncher).

        This is the pattern used for VFX environment commands where
        shell functions (like 'ws') are defined in .bashrc.
        """
        result = subprocess.run(
            ["bash", "-ilc", "echo shotbot_bash_test_ok"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # Note: bash -i may return non-zero if .bashrc has issues
        # but we should still get our echo output
        assert "shotbot_bash_test_ok" in result.stdout

    @pytest.mark.skipif(
        not os.path.exists("/bin/bash"),
        reason="bash not available",
    )
    def test_environment_variable_expansion(self) -> None:
        """Verify env var expansion works in shell commands."""
        env = os.environ.copy()
        env["SHOTBOT_TEST_VAR"] = "test_value_xyz"

        result = subprocess.run(
            ["bash", "-c", "echo $SHOTBOT_TEST_VAR"],
            capture_output=True,
            text=True,
            env=env,
            timeout=5,
        )
        assert result.returncode == 0
        assert "test_value_xyz" in result.stdout

    @pytest.mark.skipif(
        not os.path.exists("/bin/bash"),
        reason="bash not available",
    )
    def test_shell_quote_handling(self) -> None:
        """Verify nested quotes work in shell mode."""
        result = subprocess.run(
            '''bash -c "echo 'inner quotes work'"''',
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert "inner quotes work" in result.stdout


class TestSubprocessTimeout:
    """Tests for subprocess timeout handling."""

    def test_timeout_raises_exception(self) -> None:
        """Verify TimeoutExpired is raised for slow commands."""
        with pytest.raises(subprocess.TimeoutExpired):
            subprocess.run(
                [sys.executable, "-c", "import time; time.sleep(10)"],
                timeout=0.1,
            )
