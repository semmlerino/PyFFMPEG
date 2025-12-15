#!/usr/bin/env python3
"""
Process Manager Module for PyMPEG
Handles the creation, management, and monitoring of FFmpeg processes
"""

import os
import subprocess
from collections import deque
from threading import RLock
from typing import Any, ClassVar, Dict, List, Optional, Set, Tuple

from PySide6.QtCore import QObject, QProcess, QRunnable, QThreadPool, Signal
from typing_extensions import override

from config import ProcessConfig
from logging_config import get_logger
from progress_tracker import ProcessProgressTracker


class FFmpegDetectionSignals(QObject):
    """Signals for FFmpeg detection worker."""

    detection_complete: ClassVar[Signal] = Signal(bool, str)  # available, ffmpeg_path or error message


class FFmpegDetectionWorker(QRunnable):
    """Worker to detect FFmpeg availability in a background thread.

    Prevents UI freezes when probing multiple FFmpeg locations on first use.
    """

    def __init__(self, signals: FFmpegDetectionSignals):
        super().__init__()
        self.signals = signals

    @override
    def run(self) -> None:
        """Probe FFmpeg locations and emit result."""
        ffmpeg_commands = [
            "ffmpeg",
            "ffmpeg.exe",
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
        ]

        for cmd in ffmpeg_commands:
            try:
                result = subprocess.run(
                    [cmd, "-version"],
                    check=False,
                    capture_output=True,
                    timeout=2,
                )
                if result.returncode == 0:
                    self.signals.detection_complete.emit(True, cmd)
                    return
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                continue

        self.signals.detection_complete.emit(False, "FFmpeg not found")


class ProcessManager(QObject):
    """Manages FFmpeg processes for video conversion"""

    # Signal emitted when process output is available
    output_ready: ClassVar[Signal] = Signal(QProcess, str)

    # Signal emitted when process has finished
    process_finished: ClassVar[Signal] = Signal(QProcess, int, str)

    # Signal emitted when overall progress should be updated
    update_progress: ClassVar[Signal] = Signal()

    # Signal emitted when FFmpeg detection completes (async)
    ffmpeg_detected: ClassVar[Signal] = Signal(bool, str)  # available, path or error message

    # Class-level cache for FFmpeg path
    _ffmpeg_command_cache: Optional[str] = None
    _ffmpeg_available_cache: Optional[bool] = None

    # Process ID counter to avoid collisions
    _process_id_counter = 0

    def __init__(self, parent=None):
        super().__init__(parent)

        # Initialize logger
        self.logger = get_logger()

        # Initialize process tracking
        self.processes: List[Tuple[QProcess, str]] = []
        self.process_widgets: Dict[QProcess, Dict[str, Any]] = {}

        # Use deque for memory-efficient circular buffers
        self.process_logs: Dict[QProcess, deque[str]] = {}  # Circular buffer for logs
        self.process_outputs: Dict[QProcess, deque[str]] = {}  # Circular buffer for outputs
        self._base_max_log_lines = 500  # Base maximum lines per process log
        self._current_max_log_lines = (
            500  # Dynamically adjusted based on active processes
        )
        # Lock to protect buffer operations during resize (prevents race condition)
        self._buffer_lock = RLock()

        # Map QProcess to unique IDs
        self.process_ids: Dict[QProcess, str] = {}

        # Track signal connections for proper cleanup
        self.process_connections: Dict[QProcess, List[Any]] = {}

        # Queue management
        self.queue: List[str] = []
        self.total = 0
        self.completed = 0

        # Progress tracking
        self.progress_tracker = ProcessProgressTracker()
        self.codec_map: Dict[str, int] = {}  # Maps file paths to codec indices
        self.output_map: Dict[str, str] = {}  # Maps input paths to output paths

        # Timer management (simplified with UI update manager)
        self._last_activity_time = 0

        # Conversion state
        self.stopping = False
        self.parallel_enabled = False
        self.max_parallel = 1

        # FFmpeg detection signals for async detection
        self._detection_signals: Optional[FFmpegDetectionSignals] = None

        # Guard against double-cleanup of processes (race condition prevention)
        self._finished_processes: Set[QProcess] = set()

    def detect_ffmpeg_async(self) -> None:
        """Detect FFmpeg availability in a background thread.

        Call this at application startup to avoid UI freezes on first conversion.
        Emits ffmpeg_detected(available, path_or_error) when complete.
        """
        # Skip if already cached
        if ProcessManager._ffmpeg_command_cache is not None:
            self.ffmpeg_detected.emit(True, ProcessManager._ffmpeg_command_cache)
            return
        if ProcessManager._ffmpeg_available_cache is False:
            self.ffmpeg_detected.emit(False, "FFmpeg not found (cached)")
            return

        # Run detection in background
        self._detection_signals = FFmpegDetectionSignals()
        self._detection_signals.detection_complete.connect(self._on_ffmpeg_detected)
        worker = FFmpegDetectionWorker(self._detection_signals)
        QThreadPool.globalInstance().start(worker)

    def _on_ffmpeg_detected(self, available: bool, path_or_error: str) -> None:
        """Handle FFmpeg detection result from background thread."""
        if available:
            ProcessManager._ffmpeg_command_cache = path_or_error
            ProcessManager._ffmpeg_available_cache = True
            self.logger.info(f"Found FFmpeg at: {path_or_error}")
        else:
            ProcessManager._ffmpeg_available_cache = False
            self.logger.warning(path_or_error)
        self.ffmpeg_detected.emit(available, path_or_error)

    def start_batch(
        self,
        file_paths: List[str],
        parallel_enabled: bool = False,
        max_parallel: int = 1,
    ):
        """Start a new batch conversion process"""
        self.queue = list(file_paths)
        self.total = len(self.queue)
        self.completed = 0
        self.stopping = False
        self.parallel_enabled = parallel_enabled
        self.max_parallel = max_parallel

        # Initialize progress tracker
        self.progress_tracker.start_batch(self.total)

    def _get_process_id(self, process: QProcess) -> str:
        """Get or create a unique ID for a process"""
        if process not in self.process_ids:
            ProcessManager._process_id_counter += 1
            self.process_ids[process] = f"process_{ProcessManager._process_id_counter}"
        return self.process_ids[process]

    def _adjust_buffer_sizes(self):
        """Dynamically adjust buffer sizes based on number of active processes.

        Uses RLock to prevent race condition where _handle_process_output writes
        to old deque reference while this method replaces it.
        """
        active_count = len(self.processes)

        if active_count >= 10:
            # Many processes - reduce buffer to conserve memory
            self._current_max_log_lines = 100
        elif active_count >= 5:
            # Moderate processes
            self._current_max_log_lines = 250
        else:
            # Few processes - use full buffer
            self._current_max_log_lines = self._base_max_log_lines

        # Resize existing buffers if needed (protected by lock)
        with self._buffer_lock:
            for process in list(self.process_logs.keys()):
                if (
                    process in self.process_logs
                    and self.process_logs[process].maxlen != self._current_max_log_lines
                ):
                    # Create new deque with adjusted size and copy last N items
                    old_data = list(self.process_logs[process])[
                        -self._current_max_log_lines :
                    ]
                    self.process_logs[process] = deque(
                        old_data, maxlen=self._current_max_log_lines
                    )

            for process in list(self.process_outputs.keys()):
                if (
                    process in self.process_outputs
                    and self.process_outputs[process].maxlen
                    != self._current_max_log_lines
                ):
                    # Create new deque with adjusted size and copy last N items
                    old_data = list(self.process_outputs[process])[
                        -self._current_max_log_lines :
                    ]
                    self.process_outputs[process] = deque(
                        old_data, maxlen=self._current_max_log_lines
                    )

    def start_process(
        self,
        path: str,
        ffmpeg_args: List[str],
        codec_idx: int = -1,
        duration: Optional[float] = None,
        output_path: Optional[str] = None,
    ) -> QProcess:
        """
        Start a new FFmpeg process for the given file

        Args:
            path: Path to the input file
            ffmpeg_args: List of FFmpeg command arguments
            codec_idx: The codec index used (0-6 for GPU/CPU encoders, -1 if unknown)
            duration: Pre-probed duration in seconds. If None, will probe (blocking)
            output_path: Path to the output file. Stored for post-process verification.

        Returns the created process object
        """
        # Create process
        process = QProcess()
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)

        # Set up signals and track connections for cleanup
        connections = []

        # Output handling connection
        def output_handler(p=process):
            return self._handle_process_output(p)

        process.readyReadStandardOutput.connect(output_handler)
        connections.append(("readyReadStandardOutput", output_handler))

        # Error handling connection
        def error_handler(error, p=process, path=path):
            return self._handle_process_error(error, p, path)

        process.errorOccurred.connect(error_handler)
        connections.append(("errorOccurred", error_handler))

        # Finished handling connection - this is critical for marking completion
        def finished_handler(exit_code, _exit_status, p=process, process_path=path):
            return self.mark_process_finished(p, process_path, exit_code)

        process.finished.connect(finished_handler)
        connections.append(("finished", finished_handler))

        # Store connections for cleanup
        self.process_connections[process] = connections

        # Start the process with error checking
        self.logger.log_ffmpeg_start(path, ffmpeg_args)

        # Use cached FFmpeg command
        ffmpeg_cmd = self._get_ffmpeg_command()
        if not ffmpeg_cmd:
            self.logger.error(
                "FFmpeg not found in system PATH",
                suggestion="Install FFmpeg and ensure it's in your system PATH. Visit https://ffmpeg.org/download.html",
            )
            return process

        # Log the actual arguments being passed
        self.logger.debug(f"Starting {ffmpeg_cmd} with args: {ffmpeg_args}")

        # Add to tracking structures BEFORE starting process
        self.processes.append((process, path))

        # Adjust buffer sizes for current process count
        self._adjust_buffer_sizes()

        # Initialize circular buffers BEFORE starting process to prevent race condition
        # (readyReadStandardOutput can fire immediately after start())
        self.process_logs[process] = deque(maxlen=self._current_max_log_lines)
        self.process_outputs[process] = deque(maxlen=self._current_max_log_lines)

        # Start process without manual quoting - Qt handles this automatically
        process.start(ffmpeg_cmd, ffmpeg_args)

        # Wait for process to actually start (up to 5 seconds)
        if not process.waitForStarted(ProcessConfig.PROCESS_START_TIMEOUT * 1000):
            self.logger.log_process_timeout(
                f"FFmpeg process for {os.path.basename(path)}",
                ProcessConfig.PROCESS_START_TIMEOUT,
            )
            # Still continue with tracking so we can handle the error properly

        # Register with progress tracker (use 0.0 for unknown duration)
        # Use pre-probed duration if provided, otherwise probe (blocking call)
        if duration is None:
            duration = self.progress_tracker.probe_duration(path) or 0.0
        process_id = self._get_process_id(process)
        # Always register, even with unknown duration - this ensures progress reaches 100%
        self.progress_tracker.register_process(process_id, path, duration)

        # Store codec information for this file (using passed codec_idx, not parsed from args)
        if codec_idx >= 0:
            self.codec_map[path] = codec_idx

        # Store output path for post-process verification (avoids reconstruction errors)
        if output_path:
            self.output_map[path] = output_path

        return process

    def stop_all_processes(self):
        """Stop all running processes"""
        self.stopping = True

        # Kill any running QProcess
        for process, _ in self.processes:
            if process.state() != QProcess.ProcessState.NotRunning:
                process.kill()

        # Reset the progress tracker
        self.progress_tracker.start_batch(0)

        # Clear the queue
        self.queue = []

        return self.processes.copy()

    # Duplicate process_finished removed to resolve mypy no-redef error.

    def _handle_process_output(self, process: QProcess):
        """Process output from an FFmpeg process.

        Uses RLock to prevent race condition during buffer resize operations.
        """
        if process.bytesAvailable() > 0:
            data = process.readAllStandardOutput()
            # Ensure data.data() is bytes before decoding to satisfy mypy
            buf = data.data()
            if isinstance(buf, memoryview):
                chunk = buf.tobytes().decode("utf-8", errors="replace")
            else:
                chunk = buf.decode("utf-8", errors="replace")

            # Protected buffer writes to prevent race with _adjust_buffer_sizes
            with self._buffer_lock:
                # Check if process buffers still exist (may have been cleaned up)
                if process not in self.process_logs or process not in self.process_outputs:
                    return

                # Check for MPEGTS timing errors
                if (
                    "start time for stream" in chunk
                    and "is not set in estimate_timings_from_pts" in chunk
                ):
                    # Log this warning for UI display
                    self.process_logs[process].append(
                        "⚠️ MPEGTS timing warning detected. Consider adding -fflags +genpts to source."
                    )

                # Store the output
                self.process_outputs[process].append(chunk)
                self.process_logs[process].append(chunk)

            # Process the output with the progress tracker
            path = next((p for proc, p in self.processes if proc == process), None)
            if path:
                process_id = self._get_process_id(process)
                progress_data = self.progress_tracker.process_output(process_id, chunk)

                # Signal that we have progress
                if progress_data:
                    # The update_progress signal will be handled by main window
                    self.update_progress.emit()

            # Emit signal for UI handling
            self.output_ready.emit(process, chunk)

    def _using_windows_ffmpeg(self) -> bool:
        """Check if we're using Windows FFmpeg executable"""
        ffmpeg_cmd = self._get_ffmpeg_command()
        if not ffmpeg_cmd:
            return False
        # Check if it's an exe or contains Windows/Program Files paths
        return (
            ffmpeg_cmd.endswith(".exe")
            or "Windows" in ffmpeg_cmd
            or "Program Files" in ffmpeg_cmd
            or ffmpeg_cmd.startswith("C:\\")
        )

    def _get_ffmpeg_command(self) -> Optional[str]:
        """Get cached FFmpeg command or detect it"""
        # Return cached value if available
        if ProcessManager._ffmpeg_command_cache is not None:
            return ProcessManager._ffmpeg_command_cache

        # Try different FFmpeg locations (Windows-focused)
        ffmpeg_commands = [
            "ffmpeg",
            "ffmpeg.exe",
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
        ]

        for cmd in ffmpeg_commands:
            try:
                result = subprocess.run(
                    [cmd, "-version"],
                    check=False, capture_output=True,
                    timeout=2,  # Reduced timeout
                )
                if result.returncode == 0:
                    ProcessManager._ffmpeg_command_cache = cmd
                    ProcessManager._ffmpeg_available_cache = True
                    self.logger.info(f"Found FFmpeg at: {cmd}")
                    return cmd
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                continue

        ProcessManager._ffmpeg_available_cache = False
        return None

    def is_ffmpeg_available(self) -> bool:
        """Check if FFmpeg is available in PATH. Uses cached result."""
        return self._get_ffmpeg_command() is not None

    def is_process_tracked(self, process: QProcess) -> bool:
        """Check if a process is still being tracked (not yet cleaned up).

        Use this to avoid creating widgets for processes that have already
        finished and been cleaned up (e.g., fast-failing processes).
        """
        return any(p is process for p, _ in self.processes)

    def _handle_process_error(self, error, process: QProcess, path: str) -> None:
        """Enhanced error handling for process errors"""
        error_names = {
            QProcess.ProcessError.FailedToStart: "FailedToStart",
            QProcess.ProcessError.Crashed: "Crashed",
            QProcess.ProcessError.Timedout: "Timedout",
            QProcess.ProcessError.WriteError: "WriteError",
            QProcess.ProcessError.ReadError: "ReadError",
            QProcess.ProcessError.UnknownError: "UnknownError",
        }

        error_name = error_names.get(error, f"Unknown({error})")
        error_string = process.errorString()

        # Get more context
        program = process.program()
        arguments = process.arguments()

        # Log full command for debugging
        full_command = f"{program} {' '.join(arguments)}"

        self.logger.error(
            f"QProcess error occurred: ProcessError.{error_name} - {error_string}",
            extra_info={
                "file": os.path.basename(path),
                "program": program,
                "arguments": " ".join(arguments[:5]) + "..."
                if len(arguments) > 5
                else " ".join(arguments),
                "error_code": error,
                "process_state": process.state(),
                "full_command": full_command
                if len(full_command) < 500
                else full_command[:500] + "...",
            },
            suggestion="Check if FFmpeg is properly installed and accessible. Try running 'ffmpeg -version' in terminal.",
        )

        # If process crashed, try to get exit code
        if error == QProcess.ProcessError.Crashed:
            exit_code = process.exitCode() if hasattr(process, "exitCode") else -1
            exit_status = process.exitStatus() if hasattr(process, "exitStatus") else -1
            self.logger.error(
                f"Process crashed with exit code: {exit_code}, exit status: {exit_status}"
            )

            # Try to run the command directly to get better error info
            if arguments and len(arguments) < 50:  # Only for reasonable sized commands
                try:
                    ffmpeg_cmd = self._get_ffmpeg_command()
                    if ffmpeg_cmd:
                        test_result = subprocess.run(
                            [ffmpeg_cmd, *arguments[:5]],  # Test with just first few args
                            check=False, capture_output=True,
                            text=True,
                            timeout=2,
                        )
                        if test_result.stderr:
                            self.logger.error(
                                f"FFmpeg stderr: {test_result.stderr[:500]}"
                            )
                except Exception as e:
                    self.logger.error(f"Failed to test FFmpeg command: {e}")

        # CRITICAL: For FailedToStart, the finished signal never fires, so we must
        # manually mark the process as failed and emit finished to continue the queue
        # Check both that error is FailedToStart AND process is still tracked (not cleaned up)
        if error == QProcess.ProcessError.FailedToStart and any(
            p is process for p, _ in self.processes
        ):
            self.logger.warning(
                f"Process failed to start for {os.path.basename(path)}, marking as failed"
            )
            # Mark as failed and emit finished signal to continue queue
            self.mark_process_finished(process, path, -1)

    def get_overall_progress(self) -> Dict[str, Any]:
        """Get overall progress information"""
        return self.progress_tracker.get_overall_progress()

    def get_codec_distribution(self) -> Dict[str, int]:
        """Get distribution of active encoders by type"""
        return self.progress_tracker.get_codec_distribution(self.codec_map)

    def get_process_progress(self, process: QProcess) -> Optional[Dict[str, Any]]:
        """Get progress information for a specific process"""
        process_id = self._get_process_id(process)
        return self.progress_tracker.get_process_progress(process_id)

    def mark_process_finished(
        self, process: QProcess, process_path: str, exit_code: int
    ) -> None:
        """Mark process as finished, update tracker, and emit finished signal.

        This method is guarded against double-cleanup: if the process has already
        been marked as finished (e.g., from both errorOccurred and finished signals),
        subsequent calls are no-ops.
        """
        # Guard against double-cleanup race condition
        # This can happen when both errorOccurred (FailedToStart) and finished signals fire
        if process in self._finished_processes:
            return
        self._finished_processes.add(process)

        process_id = self._get_process_id(process)

        # For successful completion, force progress to 100% and emit update before cleanup
        if exit_code == 0:
            self.progress_tracker.force_progress_to_100(process_id)
            # Emit progress update to show 100% completion in UI
            self.update_progress.emit()

        # Guaranteed cleanup for this process
        self._cleanup_process_resources(process)

        # Mark as completed in progress tracker
        self.progress_tracker.complete_process(process_id, success=(exit_code == 0))
        # Emit process finished signal
        self.process_finished.emit(process, exit_code, process_path)

    def _cleanup_process_resources(self, process: QProcess) -> None:
        """Guaranteed cleanup of all resources associated with a process"""
        # Find process path before removing from list
        process_path = None
        for p, path in self.processes:
            if p == process:
                process_path = path
                break

        # Disconnect all signals for this process to prevent memory leaks
        if process in self.process_connections:
            try:
                for signal_name, handler in self.process_connections[process]:
                    if signal_name == "readyReadStandardOutput":
                        process.readyReadStandardOutput.disconnect(handler)
                    elif signal_name == "errorOccurred":
                        process.errorOccurred.disconnect(handler)
                    elif signal_name == "finished":
                        process.finished.disconnect(handler)
            except Exception as e:
                self.logger.warning(f"Error disconnecting signals: {e}")
            finally:
                del self.process_connections[process]

        # Remove from tracking list
        self.processes = [(p, path) for (p, path) in self.processes if p != process]

        # Adjust buffer sizes after removing process
        self._adjust_buffer_sizes()

        # Clean up logs and outputs (deques automatically handle memory)
        if process in self.process_logs:
            self.process_logs.pop(process)  # Deque is already size-limited

        if process in self.process_outputs:
            self.process_outputs.pop(process)  # Deque is already size-limited

        # Remove from codec mapping
        if process_path and process_path in self.codec_map:
            del self.codec_map[process_path]

        # Remove from output mapping
        if process_path and process_path in self.output_map:
            del self.output_map[process_path]

        # Remove process ID mapping
        if process in self.process_ids:
            del self.process_ids[process]

        # Clean up finished guard set (prevents memory leak over many conversions)
        self._finished_processes.discard(process)

    def cleanup_all_resources(self) -> None:
        """Emergency cleanup of all resources - called on shutdown"""
        # Kill any remaining processes
        for process, _ in self.processes:
            if process.state() != QProcess.ProcessState.NotRunning:
                process.kill()
                process.waitForFinished(3000)  # Wait up to 3 seconds

        # Clear all tracking structures
        self.processes.clear()
        self.process_logs.clear()
        self.process_outputs.clear()
        self.codec_map.clear()
        self.output_map.clear()
        self.process_ids.clear()
        self.process_connections.clear()
        self._finished_processes.clear()

    def get_available_vram(self) -> int:
        """Get available GPU VRAM in MB. Returns 0 if unable to detect."""
        return 0  # Simplified - VRAM monitoring disabled

    def can_start_gpu_encode(self) -> bool:
        """Check if there's enough VRAM to start a new GPU encode."""
        return True  # Always allow GPU encode - no VRAM monitoring

    def set_process_priority(self, process: QProcess, priority: str) -> None:
        """Set process priority. Priority can be 'high', 'normal', or 'low'."""
        try:
            if os.name == "nt":  # Windows
                priority_classes = {
                    "high": subprocess.HIGH_PRIORITY_CLASS,
                    "normal": subprocess.NORMAL_PRIORITY_CLASS,
                    "low": subprocess.IDLE_PRIORITY_CLASS,
                }
                import ctypes

                handle = ctypes.windll.kernel32.OpenProcess(
                    0x0200, False, process.processId()
                )
                if handle:
                    ctypes.windll.kernel32.SetPriorityClass(
                        handle,
                        priority_classes.get(
                            priority, subprocess.NORMAL_PRIORITY_CLASS
                        ),
                    )
                    ctypes.windll.kernel32.CloseHandle(handle)
            else:  # Linux/Unix
                nice_values = {"high": -10, "normal": 0, "low": 10}
                nice_value = nice_values.get(priority, 0)
                pid = process.processId()
                if pid > 0:
                    # Use setpriority to change the CHILD process priority, not the parent
                    os.setpriority(os.PRIO_PROCESS, pid, nice_value)
        except Exception as e:
            self.logger.warning(f"Failed to set process priority: {e}")
