"""Single entry point for read-only ffprobe invocations.

The metadata, duration, and audio-codec probes share an identical
run + timeout + error skeleton; this helper owns it so each caller only has to
parse the stdout it cares about.

Deliberately NOT used by ``conversion_controller._verify_output_integrity``:
that call must distinguish "ffprobe ran and the file is invalid" (delete-unsafe)
from "ffprobe could not run at all" (size-only fallback), a safety-critical
distinction this flattened None-on-any-failure contract would lose.
"""

from __future__ import annotations

import subprocess

from pympeg.config import ProcessConfig
from pympeg.logging_config import get_logger


def run_ffprobe(
    args: list[str],
    timeout: int = ProcessConfig.SUBPROCESS_TIMEOUT,
    timeout_log_label: str | None = None,
) -> str | None:
    """Run ``ffprobe`` with ``args`` and return its stdout, or None on failure.

    Args:
        args: ffprobe arguments; the ``ffprobe`` executable is prepended.
        timeout: seconds before the probe is abandoned.
        timeout_log_label: when given, a timeout is logged via
            ``log_process_timeout`` under this label. Other failures stay quiet,
            matching the original per-call behaviour.

    Returns:
        Captured stdout (text) when ffprobe exits 0; otherwise None. None covers
        a timeout, a non-zero exit, a missing executable, or any OSError — each
        caller decides what an absent result means for it.
    """
    try:
        result = subprocess.run(
            ["ffprobe", *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        if timeout_log_label is not None:
            get_logger().log_process_timeout(timeout_log_label, timeout)
        return None
    except (subprocess.CalledProcessError, OSError):
        return None

    return result.stdout if result.returncode == 0 else None
