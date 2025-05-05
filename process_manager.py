#!/usr/bin/env python3
"""
Process Manager Module for PyMPEG
Handles the creation, management, and monitoring of FFmpeg processes
"""

import os
import sys
import time
from typing import Dict, List, Tuple, Any, Optional, Callable

from PySide6.QtCore import (
    QProcess,
    QTimer,
    QObject,
    Signal
)

from progress_tracker import ProcessProgressTracker


class ProcessManager(QObject):
    """Manages FFmpeg processes for video conversion"""
    
    # Signal emitted when process output is available
    output_ready = Signal(QProcess, str)
    
    # Signal emitted when process has finished
    process_finished = Signal(QProcess, int, str)
    
    # Signal emitted when overall progress should be updated
    update_progress = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Initialize process tracking
        self.processes: List[Tuple[QProcess, str]] = []
        self.process_widgets: Dict[QProcess, Dict] = {}
        self.process_logs: Dict[QProcess, List[str]] = {}
        self.process_outputs: Dict[QProcess, List[str]] = {}
        
        # Queue management
        self.queue: List[str] = []
        self.total = 0
        self.completed = 0
        
        # Progress tracking
        self.progress_tracker = ProcessProgressTracker()
        self.codec_map: Dict[str, int] = {}  # Maps file paths to codec indices
        
        # UI update timer
        self.ui_update_timer = QTimer()
        self.ui_update_timer.timeout.connect(self._emit_update_progress)
        
        # Conversion state
        self.stopping = False
        self.parallel_enabled = False
        self.max_parallel = 1
    
    def start_batch(self, file_paths: List[str], parallel_enabled: bool = False, max_parallel: int = 1):
        """Start a new batch conversion process"""
        self.queue = list(file_paths)
        self.total = len(self.queue)
        self.completed = 0
        self.stopping = False
        self.parallel_enabled = parallel_enabled
        self.max_parallel = max_parallel
        
        # Initialize progress tracker
        self.progress_tracker.start_batch(self.total)
        
        # Start UI update timer
        if not self.ui_update_timer.isActive():
            self.ui_update_timer.start(500)  # Update UI every 500ms
    
    def start_process(self, path: str, ffmpeg_args: List[str]) -> QProcess:
        """
        Start a new FFmpeg process for the given file
        Returns the created process object
        """
        # Create process
        process = QProcess()
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        
        # Set up signals
        process.readyReadStandardOutput.connect(
            lambda p=process: self._handle_process_output(p)
        )
        
        # Set up error handling
        process.errorOccurred.connect(
            lambda error, p=process: print(f"Process error: {error} - {p.errorString()}")
        )
        
        # Start the process with error checking
        print(f"Starting ffmpeg with args: {' '.join(ffmpeg_args)}")
        process.start("ffmpeg", ffmpeg_args)
        
        # Add a small delay to see if process immediately errors
        if process.state() == QProcess.ProcessState.NotRunning:
            print(f"Process failed to start: {process.errorString()}")
            # Still continue with tracking so we can handle the error properly
        
        # Add to tracking structures
        self.processes.append((process, path))
        self.process_logs[process] = []
        self.process_outputs[process] = []
        
        # Register with progress tracker
        duration = self.progress_tracker.probe_duration(path)
        if duration:
            self.progress_tracker.register_process(str(id(process)), path, duration)
        
        # Store codec information for this file
        codec_idx = ffmpeg_args.index("-c:v") + 1 if "-c:v" in ffmpeg_args else -1
        if codec_idx >= 0 and codec_idx < len(ffmpeg_args):
            self.codec_map[path] = codec_idx
        
        return process
    
    def stop_all_processes(self):
        """Stop all running processes"""
        self.stopping = True
        
        # Kill any running QProcess
        for process, _ in self.processes:
            if process.state() != QProcess.ProcessState.NotRunning:
                process.kill()
        
        # Stop the UI update timer
        if self.ui_update_timer.isActive():
            self.ui_update_timer.stop()
        
        # Reset the progress tracker
        self.progress_tracker.start_batch(0)
        
        # Clear the queue
        self.queue = []
        
        return self.processes.copy()
    
    # Duplicate process_finished removed to resolve mypy no-redef error.
    
    def _handle_process_output(self, process: QProcess):
        """Process output from an FFmpeg process"""
        if process.bytesAvailable() > 0:
            data = process.readAllStandardOutput()
            # Ensure data.data() is bytes before decoding to satisfy mypy
            buf = data.data()
            if isinstance(buf, memoryview):
                chunk = buf.tobytes().decode('utf-8', errors='replace')
            else:
                chunk = buf.decode('utf-8', errors='replace')
            
            # Store the output
            self.process_outputs[process].append(chunk)
            self.process_logs[process].append(chunk)
            
            # Process the output with the progress tracker
            path = next((p for proc, p in self.processes if proc == process), None)
            if path:
                self.progress_tracker.process_output(str(id(process)), chunk)
            
            # Emit signal for UI handling
            self.output_ready.emit(process, chunk)
    
    def _emit_update_progress(self):
        """Emit signal to update UI with progress"""
        self.update_progress.emit()
    
    def get_overall_progress(self) -> Dict[str, Any]:
        """Get overall progress information"""
        return self.progress_tracker.get_overall_progress()
    
    def get_codec_distribution(self) -> Dict[str, int]:
        """Get distribution of active encoders by type"""
        return self.progress_tracker.get_codec_distribution(self.codec_map)
    
    def get_process_progress(self, process: QProcess) -> Optional[Dict[str, Any]]:
        """Get progress information for a specific process"""
        return self.progress_tracker.get_process_progress(str(id(process)))

    def mark_process_finished(self, process: QProcess, process_path: str) -> None:
        """Mark process as finished, update tracker, and emit finished signal."""
        exit_code = process.exitCode() if hasattr(process, 'exitCode') else -1
        # Remove from tracking
        self.processes = [(p, path) for (p, path) in self.processes if p != process]
        # Clean up logs and outputs
        self.process_logs.pop(process, None)
        self.process_outputs.pop(process, None)
        # Mark as completed in progress tracker
        self.progress_tracker.complete_process(str(id(process)), success=(exit_code == 0))
        # Emit process finished signal
        self.process_finished.emit(process, exit_code, process_path)
