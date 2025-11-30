#!/usr/bin/env python3
"""
Conversion Controller Module for PyMPEG
Handles the core conversion logic, process management, and conversion workflow
"""

import os
import time
from typing import Dict, List, Optional

from PySide6.QtCore import QObject, QProcess, QRunnable, QThreadPool, Signal

from codec_helpers import CodecHelpers
from config import EncodingConfig
from logging_config import get_logger
from process_manager import ProcessManager
from progress_tracker import ProcessProgressTracker


class PrepSignals(QObject):
    """Signals for ConversionPrepWorker to communicate with main thread."""

    prep_complete = Signal(str, float, list, str)  # path, duration, audio_args, msg


class ConversionPrepWorker(QRunnable):
    """Worker to run blocking probe operations off the main thread.

    Moves probe_duration() and get_audio_codec_args() to a background thread
    to prevent UI freezes during conversion preparation.
    """

    def __init__(self, file_path: str, codec_idx: int):
        super().__init__()
        self.file_path = file_path
        self.codec_idx = codec_idx
        self.signals = PrepSignals()

    def run(self) -> None:
        """Execute probe operations in background thread."""
        # These subprocess calls can take up to 30s each - run off main thread
        duration = ProcessProgressTracker.probe_duration(self.file_path) or 0.0
        audio_args, audio_msg = CodecHelpers.get_audio_codec_args(
            self.file_path, self.codec_idx
        )
        self.signals.prep_complete.emit(
            self.file_path, duration, audio_args, audio_msg
        )


class ConversionController(QObject):
    """Controls the conversion process workflow and codec management"""

    # Signals for communication with UI
    conversion_started = Signal()
    conversion_finished = Signal()
    conversion_stopped = Signal()
    log_message = Signal(str)  # For main log messages
    progress_updated = Signal()  # For UI progress updates

    def __init__(self, process_manager: ProcessManager, parent=None):
        super().__init__(parent)
        self.logger = get_logger()
        self.process_manager = process_manager
        self.process_monitor = None  # Will be set later
        self.file_list_widget = None  # Will be set later

        # Conversion state
        self.is_converting = False
        self.auto_balance_enabled = False
        self.file_codec_assignments: Dict[str, int] = {}
        self.queue: List[str] = []
        self.current_path: Optional[str] = None
        self.batch_start_time: Optional[float] = None

        # Conversion settings (set when conversion starts)
        self.codec_idx: int = 0
        self.hwdecode_idx: int = 0
        self.crf_value: int = EncodingConfig.DEFAULT_CRF_H264
        self.parallel_enabled: bool = False
        self.max_parallel: int = 1
        self.delete_source: bool = False
        self.overwrite_mode: bool = False
        self.preset_idx: int = 0
        self.hevc_10bit: bool = False
        self.threads: int = 0  # 0 = auto
        self.priority_idx: int = 1  # 0=high, 1=normal, 2=low
        self.smart_buffer: bool = True

        # Thread pool for async prep work (probe duration, audio codec detection)
        self._prep_thread_pool = QThreadPool()
        # Track pending prep workers: path -> (codec_idx, ...)
        self._pending_preps: Dict[str, int] = {}

        # Connect process manager signals
        self.process_manager.process_finished.connect(self._on_process_finished)
        self.process_manager.update_progress.connect(self.progress_updated.emit)

    def set_process_monitor(self, process_monitor):
        """Set the process monitor after it's created"""
        self.process_monitor = process_monitor

    def set_file_list_widget(self, file_list_widget):
        """Set the file list widget for status updates"""
        self.file_list_widget = file_list_widget

    def start_conversion(
        self,
        file_paths: List[str],
        codec_idx: int,
        hwdecode_idx: int,
        crf_value: int,
        parallel_enabled: bool,
        max_parallel: int,
        delete_source: bool,
        overwrite_mode: bool,
        preset_idx: int = 0,
        hevc_10bit: bool = False,
        threads: int = 0,
        priority_idx: int = 1,
        smart_buffer: bool = True,
    ) -> bool:
        """Start the conversion process with given parameters"""
        if self.is_converting:
            self.log_message.emit("⚠️ Conversion already in progress")
            return False

        if not file_paths:
            self.log_message.emit("⚠️ No files selected for conversion")
            return False

        self.is_converting = True
        self.queue = list(file_paths)
        self.batch_start_time = time.time()

        # Perform auto-balance if enabled
        if self.auto_balance_enabled:
            self._auto_balance_workload(file_paths, codec_idx)

        # Start batch in process manager
        self.process_manager.start_batch(file_paths, parallel_enabled, max_parallel)

        # Store conversion settings
        self.codec_idx = codec_idx
        self.hwdecode_idx = hwdecode_idx
        self.crf_value = crf_value
        self.parallel_enabled = parallel_enabled
        self.max_parallel = max_parallel
        self.delete_source = delete_source
        self.overwrite_mode = overwrite_mode
        self.preset_idx = preset_idx
        self.hevc_10bit = hevc_10bit
        self.threads = threads
        self.priority_idx = priority_idx
        self.smart_buffer = smart_buffer

        self.log_message.emit(f"🚀 Starting conversion of {len(file_paths)} files...")
        self.conversion_started.emit()

        # Start processing
        self._process_next()
        return True

    def stop_conversion(self) -> None:
        """Stop the current conversion process"""
        if not self.is_converting:
            return

        self.log_message.emit("🛑 Stopping conversion...")
        self.is_converting = False

        # Clear pending prep workers (they'll check is_converting on completion)
        self._pending_preps.clear()

        # Stop all processes
        stopped_processes = self.process_manager.stop_all_processes()
        self.log_message.emit(f"Stopped {len(stopped_processes)} processes")

        self.conversion_stopped.emit()

    def cleanup(self) -> None:
        """Clean up resources before destruction."""
        # Wait for any in-flight prep workers to finish
        self._prep_thread_pool.waitForDone(5000)

    def _process_next(self) -> None:
        """Process the next file in the queue"""
        if not self.is_converting or not self.queue:
            if self.is_converting and not self.queue:
                self._finish_conversion()
            return

        # For parallel processing, process multiple files up to the limit
        while self.queue and self.parallel_enabled:
            # Check if we can start more processes
            active_count = len(self.process_manager.processes)
            if active_count >= self.max_parallel:
                break  # Wait for a process to finish

            # Process one file
            self._process_single_file()

        # For non-parallel processing, process just one file
        if not self.parallel_enabled and self.queue:
            active_count = len(self.process_manager.processes)
            if active_count < self.max_parallel:
                self._process_single_file()

    def _process_single_file(self) -> None:
        """Process a single file from the queue"""
        if not self.queue:
            return

        # Pre-flight check: Verify FFmpeg is available BEFORE popping from queue
        if not self.process_manager.is_ffmpeg_available():
            self.log_message.emit("❌ FFmpeg not found in PATH - cannot process files")
            # Mark all remaining files as failed
            for remaining_path in self.queue:
                if self.file_list_widget:
                    self.file_list_widget.set_status(remaining_path, "failed")
            self.queue.clear()
            self._finish_conversion()
            return

        # Get next file
        file_path = self.queue.pop(0)
        self.current_path = file_path

        # Determine codec for this file
        codec_idx = self._get_codec_for_path(file_path)

        # Pre-check: Skip file if output exists and overwrite is disabled
        # This provides clear feedback instead of FFmpeg's silent -n behavior
        if not self.overwrite_mode:
            output_ext = CodecHelpers.get_output_extension(codec_idx)
            input_name = os.path.splitext(os.path.basename(file_path))[0]
            output_path = os.path.join(
                os.path.dirname(file_path), f"{input_name}_RC{output_ext}"
            )
            if os.path.exists(output_path):
                self.log_message.emit(
                    f"⏭️ Skipped (output exists): {os.path.basename(file_path)}"
                )
                if self.file_list_widget:
                    self.file_list_widget.set_status(file_path, "skipped")
                self._process_next()
                return

        self.log_message.emit(f"📂 Preparing: {os.path.basename(file_path)}")

        # Update file list status to processing
        if self.file_list_widget:
            self.file_list_widget.set_status(file_path, "processing")

        # Queue async prep worker to avoid blocking UI with subprocess calls
        # Worker will probe duration and detect audio codec in background
        self._pending_preps[file_path] = codec_idx
        worker = ConversionPrepWorker(file_path, codec_idx)
        worker.signals.prep_complete.connect(self._on_prep_complete)
        self._prep_thread_pool.start(worker)

    def _on_prep_complete(
        self, file_path: str, duration: float, audio_args: List[str], audio_msg: str
    ) -> None:
        """Handle completion of async prep work and start the actual FFmpeg process."""
        # Check if conversion was stopped while prep was running
        if not self.is_converting or file_path not in self._pending_preps:
            return

        codec_idx = self._pending_preps.pop(file_path)

        # Build FFmpeg arguments using pre-fetched audio configuration
        ffmpeg_args = self._build_ffmpeg_args_with_audio(
            file_path, codec_idx, audio_args, audio_msg
        )

        self.log_message.emit(f"🚀 Starting: {os.path.basename(file_path)}")

        # Start the process with pre-probed duration to avoid another blocking call
        process = self.process_manager.start_process(
            file_path, ffmpeg_args, codec_idx, duration=duration
        )

        # Apply process priority if process started successfully
        if process.state() != QProcess.ProcessState.NotRunning:
            priority_names = {0: "high", 1: "normal", 2: "low"}
            priority = priority_names.get(self.priority_idx, "normal")
            self.process_manager.set_process_priority(process, priority)

        # Create process widget if monitor is available and process is still tracked
        # (fast-failing processes may have already been cleaned up by this point)
        if (
            self.process_monitor
            and process.state() != QProcess.ProcessState.NotRunning
            and self.process_manager.is_process_tracked(process)
        ):
            self.process_monitor.create_process_widget(process, file_path)

    def _build_ffmpeg_args(self, input_path: str, codec_idx: int) -> List[str]:
        """Build FFmpeg command arguments for the given file and codec.

        NOTE: This method includes a blocking subprocess call (get_audio_codec_args).
        For non-blocking operation, use _build_ffmpeg_args_with_audio instead.
        """
        # Get audio codec configuration (blocking subprocess call)
        audio_args, audio_message = CodecHelpers.get_audio_codec_args(
            input_path, codec_idx
        )
        return self._build_ffmpeg_args_with_audio(
            input_path, codec_idx, audio_args, audio_message
        )

    def _build_ffmpeg_args_with_audio(
        self,
        input_path: str,
        codec_idx: int,
        audio_args: List[str],
        audio_message: str,
    ) -> List[str]:
        """Build FFmpeg args using pre-fetched audio configuration (non-blocking).

        Args:
            input_path: Path to input video file
            codec_idx: Codec index to use
            audio_args: Pre-fetched audio codec arguments
            audio_message: Pre-fetched audio message for logging
        """
        # Add overwrite flag based on setting (-y to overwrite, -n to skip existing)
        args = ["-y"] if self.overwrite_mode else ["-n"]

        # Add hardware acceleration if enabled
        hw_args, hw_message = CodecHelpers.get_hardware_acceleration_args(
            self.hwdecode_idx
        )
        args.extend(hw_args)
        if hw_message:
            self.log_message.emit(f"🔧 {hw_message}")

        # Input file
        args.extend(["-i", input_path])

        # Add pre-fetched audio configuration
        args.extend(audio_args)
        if audio_message:
            self.log_message.emit(f"🎵 {audio_message}")

        # Get video encoder configuration
        # Use user-specified threads if non-zero, otherwise auto-calculate
        thread_count = (
            self.threads if self.threads > 0 else self._optimize_threads_for_codec(codec_idx)
        )
        encoder_args, encoder_message = CodecHelpers.get_encoder_configuration(
            codec_idx, thread_count, self.parallel_enabled, self.crf_value,
            hevc_10bit=self.hevc_10bit,
            preset_idx=self.preset_idx,
        )
        args.extend(encoder_args)
        if encoder_message:
            self.log_message.emit(f"🎬 {encoder_message}")

        # Output file
        output_ext = CodecHelpers.get_output_extension(codec_idx)
        input_name = os.path.splitext(os.path.basename(input_path))[0]
        output_path = os.path.join(
            os.path.dirname(input_path), f"{input_name}_RC{output_ext}"
        )
        args.append(output_path)

        return args

    def _get_codec_for_path(self, path: str) -> int:
        """Get the codec index for a specific path (auto-balance or default)"""
        if self.auto_balance_enabled and path in self.file_codec_assignments:
            return self.file_codec_assignments[path]
        return self.codec_idx

    def _optimize_threads_for_codec(self, codec_idx: Optional[int] = None) -> int:
        """Optimize thread count based on codec and parallel processing"""
        if codec_idx is None:
            codec_idx = self.codec_idx

        return CodecHelpers.optimize_threads_for_codec(
            codec_idx, self.parallel_enabled, self.file_codec_assignments
        )

    def _auto_balance_workload(self, file_paths: List[str], default_codec: int) -> None:
        """Auto-balance workload between GPU and CPU encoders

        Uses the user's selected codec as a base:
        - If user selected a GPU codec (NVENC/QSV/VAAPI), GPU files use that codec
        - CPU files always use x264 (codec index 3) for software encoding
        - AV1 NVENC (codec 2) requires RTX 40 series; falls back to H.264 NVENC if unavailable
        """
        self.log_message.emit("⚖️ Auto-balancing workload between GPU and CPU...")

        total_files = len(file_paths)
        gpu_count = int(total_files * EncodingConfig.GPU_RATIO_DEFAULT)
        cpu_count = total_files - gpu_count

        # Determine GPU codec based on user's selection
        # GPU codecs: 0=H.264 NVENC, 1=HEVC NVENC, 2=AV1 NVENC, 5=H.264 QSV, 6=H.264 VAAPI
        # CPU codecs: 3=x264, 4=ProRes
        gpu_codec_indices = (0, 1, 2, 5, 6)
        # Use user's GPU codec if selected, otherwise fallback to H.264 NVENC
        gpu_codec = default_codec if default_codec in gpu_codec_indices else 0

        # AV1 NVENC (codec 2) requires RTX 40 series GPU
        if gpu_codec == 2 and not CodecHelpers.detect_rtx40_series():
            self.log_message.emit(
                "⚠️ AV1 NVENC requires RTX 40 series - falling back to H.264 NVENC"
            )
            gpu_codec = 0  # Fallback to H.264 NVENC

        # Assign codecs based on position in queue
        for i, path in enumerate(file_paths):
            if i < gpu_count:
                # Use user's selected GPU codec
                self.file_codec_assignments[path] = gpu_codec
            else:
                # Use software x264 for CPU (codec index 3)
                self.file_codec_assignments[path] = 3

        codec_names = {
            0: "H.264 NVENC", 1: "HEVC NVENC", 2: "AV1 NVENC",
            5: "H.264 QSV", 6: "H.264 VAAPI"
        }
        gpu_name = codec_names.get(gpu_codec, "GPU")
        self.log_message.emit(f"📊 Balanced: {gpu_count} {gpu_name}, {cpu_count} x264 CPU")

    def _on_process_finished(
        self, process: QProcess, exit_code: int, process_path: str
    ) -> None:
        """Handle process completion"""
        if exit_code == 0:
            self.log_message.emit(f"✅ Completed: {os.path.basename(process_path)}")

            # Update file list status to completed
            if self.file_list_widget:
                # Ensure progress shows 100% before marking as completed
                self.file_list_widget.update_progress(process_path, 100)
                self.file_list_widget.set_status(process_path, "completed")

            # Handle source file deletion if enabled - with output verification
            if self.delete_source:
                # Build expected output path to verify it exists
                codec_idx = self.process_manager.codec_map.get(process_path, self.codec_idx)
                output_ext = CodecHelpers.get_output_extension(codec_idx)
                input_name = os.path.splitext(os.path.basename(process_path))[0]
                output_path = os.path.join(
                    os.path.dirname(process_path), f"{input_name}_RC{output_ext}"
                )

                # Verify output exists and has reasonable size before deleting source
                if os.path.exists(output_path):
                    output_size = os.path.getsize(output_path)
                    try:
                        input_size = os.path.getsize(process_path)
                    except OSError:
                        input_size = 0
                    # Output should be at least 1KB or 1% of input (whichever is larger)
                    min_size = max(1024, int(input_size * 0.01))

                    if output_size >= min_size:
                        try:
                            os.remove(process_path)
                            self.log_message.emit(
                                f"🗑️ Deleted source: {os.path.basename(process_path)}"
                            )
                        except OSError as e:
                            self.log_message.emit(
                                f"⚠️ Could not delete {process_path}: {e}"
                            )
                    else:
                        self.log_message.emit(
                            f"⚠️ Output too small ({output_size}B), keeping source: "
                            f"{os.path.basename(process_path)}"
                        )
                else:
                    self.log_message.emit(
                        f"⚠️ Output not found, keeping source: "
                        f"{os.path.basename(process_path)}"
                    )
        else:
            self.log_message.emit(
                f"❌ Failed: {os.path.basename(process_path)} (exit code: {exit_code})"
            )

            # Update file list status to failed
            if self.file_list_widget:
                self.file_list_widget.set_status(process_path, "failed")

        # Continue processing (handles both parallel and sequential modes)
        # Always call _process_next() to properly detect conversion completion
        # and handle cleanup even if conversion was stopped mid-process
        self._process_next()

    def _finish_conversion(self) -> None:
        """Finish the conversion process"""
        # Log batch performance metrics
        if self.batch_start_time:
            batch_duration = time.time() - self.batch_start_time
            self.logger.log_performance(
                "batch_conversion",
                batch_duration,
                {
                    "total_files": len(self.file_codec_assignments)
                    if self.file_codec_assignments
                    else 0
                },
            )

        self.is_converting = False
        self.current_path = None
        self.queue.clear()
        self.file_codec_assignments.clear()
        self.batch_start_time = None

        self.log_message.emit("🎉 Conversion completed!")
        self.conversion_finished.emit()

    def enable_auto_balance(self, enabled: bool) -> None:
        """Enable or disable auto-balance mode"""
        self.auto_balance_enabled = enabled
        if enabled:
            self.log_message.emit("⚖️ Auto-balance mode enabled")
        else:
            self.log_message.emit("⚖️ Auto-balance mode disabled")
            self.file_codec_assignments.clear()
