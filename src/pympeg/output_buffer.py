#!/usr/bin/env python3
"""
Optimized Output Buffer for FFmpeg Processing
Implements efficient batch processing and ring buffer for performance
"""

from __future__ import annotations

import threading
import time
from collections import deque
from threading import Lock
from typing import TypedDict


class ProgressData(TypedDict):
    """Type definition for progress data returned by OutputBuffer"""

    elapsed_sec: float
    fps: int
    frame: int
    has_data: bool


class OutputBuffer:
    """Parses FFmpeg ``-progress`` key=value output into progress data.

    FFmpeg writes machine-readable progress to stdout (``-progress pipe:1``):
    one ``key=value`` per line, e.g. ``out_time_us=1900000`` / ``fps=30.00`` /
    ``speed=3.02x`` / ``progress=continue``. We keep the latest value seen for
    each key. Parsing is pure (no Qt/IO) so it can be unit-tested directly.
    """

    def __init__(self, max_size: int = 1000, batch_interval: float = 0.1):
        """
        Initialize output buffer

        Args:
            max_size: Maximum number of lines to keep in buffer
            batch_interval: Time interval for batch processing (seconds)
        """
        self.buffer: deque[str] = deque(maxlen=max_size)
        self.pending_lines: list[str] = []
        # Trailing bytes from the last chunk that did not end in a newline.
        # QProcess delivers stdout at arbitrary byte boundaries, so a key=value
        # line can be split across reads; we hold the fragment until its newline
        # (or force_process) arrives, so a partial line is never parsed as whole.
        self._carry: str = ""
        self.batch_interval: float = batch_interval
        self.last_batch_time: float = time.time()
        self.lock: Lock = threading.Lock()

        # Cached latest progress values.
        self.last_elapsed_sec: float = 0.0
        self.last_fps: int = 0
        self.last_frame: int = 0
        self.last_speed: float = 0.0
        self.last_progress: str = ""
        self.has_progress: bool = False

    def add_output(self, chunk: str) -> None:
        """Add an output chunk, splitting out complete (newline-terminated) lines.

        A trailing fragment with no terminating newline is retained and prepended
        to the next chunk, so a key=value line split across reads still parses.
        """
        with self.lock:
            data = self._carry + chunk
            parts = data.split("\n")
            # The final element is the (possibly empty) incomplete trailing line.
            self._carry = parts.pop()
            self.pending_lines.extend(line for line in parts if line.strip())

    def process_batch(self) -> ProgressData:
        """
        Parse pending lines in batch, throttled by batch_interval.

        Returns:
            Latest cached progress data.
        """
        current_time = time.time()

        # Throttle: only parse once per batch_interval.
        if current_time - self.last_batch_time < self.batch_interval:
            return self._get_cached_results()

        with self.lock:
            if not self.pending_lines:
                return self._get_cached_results()

            lines = self.pending_lines
            # Keep recent lines for display, then parse and reset pending.
            self.buffer.extend(lines)
            self.pending_lines = []

            self._parse_progress_lines(lines)
            self.last_batch_time = current_time

        return self._get_cached_results()

    def force_process(self) -> ProgressData:
        """Force immediate parsing of all pending data.

        Also flushes any retained trailing fragment: this is the end-of-stream /
        completion path, where the final ``-progress`` block may arrive without a
        terminating newline and must not be stranded in the carry buffer.
        """
        with self.lock:
            if self._carry.strip():
                self.pending_lines.append(self._carry)
            self._carry = ""

        self.last_batch_time = 0  # Bypass the batch_interval throttle.
        return self.process_batch()

    def _parse_progress_lines(self, lines: list[str]) -> None:
        """Parse FFmpeg ``-progress`` key=value lines into the cache (pure).

        Takes the latest valid value per key across the batch. ``N/A`` values
        (emitted before encoding starts) raise on conversion and are skipped, so
        ``has_progress`` stays False until a real ``out_time`` arrives.
        """
        for line in lines:
            key, sep, value = line.partition("=")
            if not sep:
                continue
            key = key.strip()
            value = value.strip()

            if key in ("out_time_us", "out_time_ms"):
                # Both FFmpeg spellings report MICROSECONDS (out_time_ms is a
                # long-standing misnomer that still carries µs); /1e6 -> seconds.
                try:
                    self.last_elapsed_sec = int(value) / 1_000_000
                except ValueError:
                    continue
                self.has_progress = True
            elif key == "fps":
                try:
                    self.last_fps = int(float(value))
                except ValueError:
                    continue
            elif key == "frame":
                try:
                    self.last_frame = int(value)
                except ValueError:
                    continue
            elif key == "speed":
                # e.g. "3.02x"
                try:
                    self.last_speed = float(value.rstrip("x"))
                except ValueError:
                    continue
            elif key == "progress":
                # "continue" while running, "end" on completion.
                self.last_progress = value

    def _get_cached_results(self) -> ProgressData:
        """Get cached results without processing"""
        return {
            "elapsed_sec": self.last_elapsed_sec,
            "fps": self.last_fps,
            "frame": self.last_frame,
            "has_data": self.has_progress,
        }

    def get_recent_lines(self, count: int = 50) -> list[str]:
        """Get recent output lines for display"""
        with self.lock:
            # Include both buffered and pending lines
            all_lines = list(self.buffer) + self.pending_lines
            return all_lines[-count:] if len(all_lines) > count else all_lines

    def clear(self) -> None:
        """Clear all buffers"""
        with self.lock:
            self.buffer.clear()
            self.pending_lines.clear()
            self._carry = ""
            self.last_elapsed_sec = 0.0
            self.last_fps = 0
            self.last_frame = 0
            self.last_speed = 0.0
            self.last_progress = ""
            self.has_progress = False


class ProcessOutputManager:
    """Manages output buffers for multiple processes"""

    def __init__(self, batch_interval: float = 0.1):
        self.buffers: dict[str, OutputBuffer] = {}
        self.base_batch_interval: float = batch_interval
        self.lock: Lock = threading.Lock()

    def get_buffer(self, process_id: str) -> OutputBuffer:
        """Get or create buffer for process"""
        with self.lock:
            if process_id not in self.buffers:
                # Adjust batch interval based on number of active processes
                active_count = len(self.buffers)
                if active_count >= 10:
                    # More processes = longer batch interval to reduce overhead
                    adjusted_interval = self.base_batch_interval * 2.0
                elif active_count >= 5:
                    adjusted_interval = self.base_batch_interval * 1.5
                else:
                    adjusted_interval = self.base_batch_interval

                self.buffers[process_id] = OutputBuffer(
                    batch_interval=adjusted_interval,
                    max_size=500
                    if active_count < 10
                    else 250,  # Reduce buffer size for many processes
                )
            return self.buffers[process_id]

    def remove_buffer(self, process_id: str) -> None:
        """Remove buffer for completed process"""
        with self.lock:
            _ = self.buffers.pop(process_id, None)

    def process_all_batches(self) -> dict[str, ProgressData]:
        """Process all pending batches and return results"""
        results: dict[str, ProgressData] = {}
        with self.lock:
            for process_id, buffer in self.buffers.items():
                results[process_id] = buffer.process_batch()
        return results
