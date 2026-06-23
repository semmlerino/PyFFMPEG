#!/usr/bin/env python3
"""
Progress Tracker Module for PyMPEG
Handles parsing ffmpeg output and calculating progress metrics and ETAs
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any

from pympeg.config import CodecIndex, UIConfig
from pympeg.domain.job import BatchState, ProcessState
from pympeg.ffprobe import run_ffprobe
from pympeg.logging_config import get_logger
from pympeg.output_buffer import ProcessOutputManager


class ProcessProgressTracker:
    """Tracks progress for ffmpeg encoding processes"""

    def __init__(self) -> None:
        """Initialize the progress tracker"""
        from pympeg.logging_config import PyFFMPEGLogger

        self.logger: PyFFMPEGLogger = get_logger()
        # Aggregate batch state: counts + per-process state keyed by process_id.
        self.batch: BatchState = BatchState()
        self.batch_start_time: float | None = None
        self._lock: threading.RLock = (
            threading.RLock()
        )  # Reentrant lock for thread safety

        # For ETA smoothing
        self.prev_eta_values: list[float] = []
        self.eta_window_size: int = (
            3  # Use last 3 ETAs for smoothing (reduced for more responsiveness)
        )
        self.last_progress_time: float = 0.0
        self.last_progress_value: float = 0.0
        self.force_eta_update_interval: float = (
            UIConfig.FORCE_UPDATE_INTERVAL
        )  # Force ETA update every N seconds even with small progress

        # Initialize output buffer manager for optimized processing
        self.output_manager: ProcessOutputManager = ProcessOutputManager(
            batch_interval=0.1
        )

        # Cache for overall progress calculation (thread-safe access via _lock)
        self._last_overall_calc_time: float = 0.0
        # Use Any for cached result to match return type flexibility
        self._last_overall_result: dict[str, Any] = {}  # pyright: ignore[reportExplicitAny]

        # Per-process get_process_progress() result cache: process_id -> (result, time)
        self._process_result_cache: dict[str, tuple[dict[str, Any], float]] = {}  # pyright: ignore[reportExplicitAny]

    def start_batch(self, total_files: int) -> None:
        """Start tracking a batch of processes"""
        self.batch_start_time = time.time()
        # Reset counts only; active processes persist (matches legacy behavior where
        # start_batch does not clear the process map).
        self.batch.completed_count = 0
        self.batch.failed_count = 0
        self.batch.total = total_files

        # Reset ETA smoothing state to prevent stale data from previous batches
        self.prev_eta_values.clear()
        self.last_progress_time = 0.0
        self.last_progress_value = 0.0

        # Clear stale tracking data from previous batch
        self._last_overall_calc_time = 0.0
        self._last_overall_result = {}

    def register_process(
        self, process_id: str, path: str, duration: float
    ) -> ProcessState:
        """Register a new process to track"""
        with self._lock:
            now = time.time()
            state = ProcessState(
                path=path,
                duration=duration,
                start_time=now,
                last_fps_time=now,
            )
            self.batch.processes[process_id] = state
            return state

    def force_progress_to_100(self, process_id: str) -> None:
        """Force a process progress to 100% for final display"""
        with self._lock:
            state = self.batch.processes.get(process_id)
            if state is not None:
                state.current_pct = 100

    def complete_process(self, process_id: str, success: bool = True) -> None:
        """Mark a process as completed (successfully or with failure)"""
        with self._lock:
            state = self.batch.processes.get(process_id)
            if state is not None:
                if success:
                    # Force progress to 100% for successful completion
                    state.current_pct = 100
                else:
                    # Track failures separately for UI breakdown
                    self.batch.failed_count += 1

                # ALWAYS count toward completion (including failures)
                # This ensures progress bar reaches 100% even with failures
                self.batch.completed_count += 1

                del self.batch.processes[process_id]
                # Drop the per-process result cache entry alongside the state
                _ = self._process_result_cache.pop(process_id, None)

                # Clean up output buffer
                self.output_manager.remove_buffer(process_id)

    def mark_file_skipped(self) -> None:
        """Mark a file as skipped (counts toward completion for progress tracking).

        Use this when a file is skipped without creating an FFmpeg process
        (e.g., output already exists with overwrite disabled).
        """
        with self._lock:
            self.batch.completed_count += 1

    def mark_file_failed(self) -> None:
        """Mark a file as failed (counts toward completion AND failure tracking).

        Use this when a file fails before an FFmpeg process is created
        (e.g., FFmpeg not available, invalid input file).
        """
        with self._lock:
            self.batch.completed_count += 1
            self.batch.failed_count += 1

    def process_output(self, process_id: str, chunk: str) -> dict[str, Any]:  # pyright: ignore[reportExplicitAny]
        """
        Process ffmpeg output chunk and update progress information
        Returns updated progress data if successful, empty dict otherwise
        """
        # Acquire lock and copy process data to avoid race with complete_process()
        with self._lock:
            state = self.batch.processes.get(process_id)
            if state is None:
                return {}
            duration = state.duration
            start_time = state.start_time
            path = state.path

        # Process buffer outside lock to avoid blocking other threads
        buffer = self.output_manager.get_buffer(process_id)
        buffer.add_output(chunk)

        # Get batch-processed results
        results = buffer.process_batch()

        if not results["has_data"]:
            return {}

        # Calculate percentage based on duration
        if not duration:
            return {}

        elapsed_sec = results["elapsed_sec"]
        fps = results["fps"]

        # Update progress percentage
        pct = min(100, round(elapsed_sec / duration * 100))

        # Calculate remaining time with more precision
        elapsed = time.time() - start_time
        remain = elapsed / pct * (100 - pct) if pct > 0 else 0.0

        # Re-acquire lock to update process state (re-check it still exists)
        with self._lock:
            state = self.batch.processes.get(process_id)
            if state is None:
                return {}  # Process was removed while we were processing
            state.elapsed_sec = elapsed_sec
            state.fps = fps
            state.current_pct = pct

        # Prepare result with formatted times and progress data
        return {
            "process_id": process_id,
            "current_pct": pct,
            "elapsed_sec": elapsed_sec,
            "duration": duration,
            "fps": fps,
            "elapsed": elapsed,
            "elapsed_str": self._format_time(elapsed),
            "remain": remain,
            "remain_str": self._format_time(remain),
            "path": path,
        }

    def force_batch_process_all(self) -> None:
        """Force immediate batch processing for all active processes"""
        with self._lock:
            # Create a list copy to avoid modification during iteration
            process_ids = list(self.batch.processes.keys())
            for process_id in process_ids:
                if process_id in self.batch.processes:  # Check if still exists
                    buffer = self.output_manager.get_buffer(process_id)
                    _ = buffer.force_process()

    def get_overall_progress(self) -> dict[str, Any]:  # pyright: ignore[reportExplicitAny]
        """
        Calculate overall progress metrics for all active processes
        Returns a dictionary with overall stats
        """
        if not self.batch_start_time:
            return {}

        # Use lock for entire calculation to prevent TOCTOU race conditions
        # RLock allows reentrant calls from output_manager
        with self._lock:
            # Check if we need to recalculate (cache for performance)
            current_time = time.time()
            if (
                self._last_overall_calc_time > 0
                and current_time - self._last_overall_calc_time < 0.1  # 100ms cache
            ):
                return self._last_overall_result

            # Batch process all outputs for accurate data
            # Note: output_manager has its own locking, safe to call under our lock
            _ = self.output_manager.process_all_batches()

            # Calculate overall progress percentage (safe iteration under lock)
            process_progress_sum: float = sum(
                state.current_pct for state in self.batch.processes.values()
            )
            active_count = len(self.batch.processes)

            # Calculate weighted progress (completed files count as 100%)
            if self.batch.total > 0:  # Avoid division by zero
                weighted_pct = (
                    process_progress_sum + (self.batch.completed_count * 100)
                ) / self.batch.total
            else:
                weighted_pct = 0

            # Get current time for calculations
            elapsed_total = current_time - self.batch_start_time

            # Calculate time-based progress rate rather than percentage-based
            # This makes the ETA calculation more stable
            current_progress_rate = 0
            if weighted_pct > 0:  # Avoid division by zero
                # Calculate instantaneous rate
                if (
                    self.last_progress_value > 0
                    and current_time > self.last_progress_time
                ):
                    time_diff = current_time - self.last_progress_time
                    progress_diff = weighted_pct - self.last_progress_value

                    # Update ETA in two cases:
                    # 1. When we've made meaningful progress
                    # 2. When it's been a while since our last update
                    should_update = (
                        progress_diff > 0.05 and time_diff > 0.5
                    ) or time_diff > self.force_eta_update_interval

                    if should_update:
                        # Calculate progress rate (%/second)
                        current_progress_rate = progress_diff / time_diff

                        # Always ensure some minimum rate to prevent infinite ETA
                        min_rate = 0.001  # Minimum progress rate of 0.001% per second
                        current_progress_rate = max(current_progress_rate, min_rate)

                        # Calculate raw ETA based on current rate
                        raw_eta = (100 - weighted_pct) / current_progress_rate

                        # Cap the raw ETA at a reasonable maximum
                        max_possible_eta = 3600 * 24  # 24 hours max
                        raw_eta = min(raw_eta, max_possible_eta)

                        # Add to the list of recent ETAs
                        self.prev_eta_values.append(raw_eta)
                        # Keep only the most recent values
                        if len(self.prev_eta_values) > self.eta_window_size:
                            _ = self.prev_eta_values.pop(0)

                # Use fallback calculation if we don't have enough data yet
                if not self.prev_eta_values:
                    total_eta = (elapsed_total / weighted_pct) * (100 - weighted_pct)
                    self.prev_eta_values.append(total_eta)

                # Calculate smoothed ETA using weighted moving average
                # Give more weight to recent values
                weights = [i + 1 for i in range(len(self.prev_eta_values))]
                total_weight = sum(weights)
                smoothed_eta = sum(
                    eta * (w / total_weight)
                    for eta, w in zip(self.prev_eta_values, weights, strict=True)
                )

                # Apply sanity limits to ETA
                # If progress is >90%, ETA shouldn't be more than 10 minutes
                if weighted_pct > 90 and smoothed_eta > 600:
                    smoothed_eta = min(smoothed_eta, 600)

                # Store values for next calculation
                self.last_progress_time = current_time
                self.last_progress_value = weighted_pct
            else:
                smoothed_eta = 0

            result = {
                "weighted_pct": weighted_pct,
                "elapsed_total": elapsed_total,
                "elapsed_str": self._format_time(elapsed_total),
                "total_eta": smoothed_eta,
                "eta_str": self._format_time(smoothed_eta),
                "active_count": active_count,
                "completed_count": self.batch.completed_count,
                "failed_count": self.batch.failed_count,
                "success_count": self.batch.completed_count - self.batch.failed_count,
                "total_count": self.batch.total,
            }

            # Cache the result (already under lock)
            self._last_overall_calc_time = current_time
            self._last_overall_result = result

            return result

    def get_codec_distribution(self, codec_map: dict[str, int]) -> dict[str, int]:
        """Calculate distribution of active encoders by type (GPU/CPU).

        GPU vs CPU classification uses the registry-derived
        ``CodecIndex.GPU_ENCODERS`` so codec facts live in a single place.
        """
        codec_counts = {"GPU": 0, "CPU": 0}

        for state in self.batch.processes.values():
            path = state.path
            if path in codec_map:
                codec_idx = codec_map[path]
                codec_type = "GPU" if codec_idx in CodecIndex.GPU_ENCODERS else "CPU"
                codec_counts[codec_type] += 1

        return codec_counts

    def get_process_progress(self, process_id: str) -> dict[str, Any] | None:  # pyright: ignore[reportExplicitAny]
        """Get progress information for a specific process"""
        with self._lock:
            state = self.batch.processes.get(process_id)
            if state is None:
                return None

            # Check cache first
            current_time = time.time()
            cached = self._process_result_cache.get(process_id)
            if cached is not None and current_time - cached[1] < 0.05:  # 50ms cache
                return cached[0]

            # Get progress data while holding the lock
            elapsed = current_time - state.start_time
            pct = state.current_pct

            # Apply the same smoothing algorithm used in overall progress
            if pct > 0:
                # Calculate instantaneous rate if we have previous data
                last_progress_value = state.last_progress_value
                last_progress_time = state.last_progress_time
                if last_progress_value > 0 and current_time > last_progress_time:
                    time_diff = current_time - last_progress_time
                    progress_diff = pct - last_progress_value

                    # Update more aggressively for individual files
                    should_update = (progress_diff > 0.01) or (time_diff > 2.0)

                    if should_update:
                        # Calculate progress rate (%/second) with minimum threshold
                        current_rate = max(
                            progress_diff / time_diff, 0.0005
                        )  # Ensure some movement

                        # Calculate raw ETA based on current rate
                        raw_eta = (100 - pct) / current_rate

                        # Cap at reasonable maximum
                        raw_eta = min(
                            raw_eta, 3600 * 12
                        )  # Max 12 hours for individual file

                        # Add to the list of recent ETAs for this process
                        state.prev_eta_values.append(raw_eta)
                        # Keep very small window for individual processes to be more responsive
                        if len(state.prev_eta_values) > 2:
                            _ = state.prev_eta_values.pop(0)

                # Use fallback calculation if we don't have enough data yet
                if not state.prev_eta_values:
                    basic_eta = (elapsed / pct) * (100 - pct)
                    state.prev_eta_values.append(basic_eta)

                # Calculate smoothed ETA using weighted moving average
                weights = [
                    i + 1 for i in range(len(state.prev_eta_values))
                ]  # More weight to recent values
                total_weight = sum(weights)
                smoothed_eta = sum(
                    eta * (w / total_weight)
                    for eta, w in zip(state.prev_eta_values, weights, strict=True)
                )

                # Apply sanity check - ETA shouldn't increase significantly when progress is high
                if pct > 80 and len(state.prev_eta_values) > 1:
                    # Don't let ETA increase by more than 20% when we're near the end
                    previous_eta = state.prev_eta_values[-2]
                    if smoothed_eta > previous_eta * 1.2:
                        smoothed_eta = previous_eta * 1.2

                # Store current values for next calculation
                state.last_progress_time = current_time
                state.last_progress_value = pct

                remain = smoothed_eta
            else:
                remain = 0.0

            # Return a copy of the process data with additional calculated fields
            result = {
                "process_id": process_id,
                "current_pct": pct,
                "elapsed_sec": state.elapsed_sec,
                "duration": state.duration,
                "fps": state.fps,
                "elapsed": elapsed,
                "elapsed_str": self._format_time(elapsed),
                "remain": remain,
                "remain_str": self._format_time(remain),
                "path": state.path,
            }

            # Cache the result (still under lock, process guaranteed to exist)
            self._process_result_cache[process_id] = (result, current_time)

            return result

    @staticmethod
    def _format_time(seconds: float) -> str:
        """Format seconds as HH:MM:SS"""
        return time.strftime("%H:%M:%S", time.gmtime(seconds))

    @staticmethod
    def probe_duration(path: str) -> float | None:
        """
        Probe a media file for its duration using ffprobe
        Returns duration in seconds or None if it can't be determined
        """
        out = run_ffprobe(
            [
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            timeout_log_label=f"ffprobe duration probe for {os.path.basename(path)}",
        )
        if out is None:
            return None

        text = out.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
