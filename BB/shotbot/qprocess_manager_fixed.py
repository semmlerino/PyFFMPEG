"""Simplified QProcess-based process management with proper threading.

This version fixes the threading issues by:
1. Using QProcess.waitForFinished() with timeout instead of complex timer logic
2. Avoiding cross-thread timer operations
3. Simpler event loop management
"""

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from PySide6.QtCore import (
    QMutex,
    QMutexLocker,
    QObject,
    QProcess,
    QProcessEnvironment,
    QThread,
    Signal,
)

logger = logging.getLogger(__name__)


class ProcessState(Enum):
    """Process lifecycle states."""
    PENDING = "pending"
    STARTING = "starting"
    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"
    TERMINATED = "terminated"
    CRASHED = "crashed"


@dataclass
class ProcessConfig:
    """Configuration for process execution."""
    command: str
    arguments: List[str] = field(default_factory=list)
    working_directory: Optional[str] = None
    environment: Optional[Dict[str, str]] = None
    use_shell: bool = False
    interactive_bash: bool = False
    terminal: bool = False
    terminal_persist: bool = False
    timeout_ms: int = 30000  # 30 seconds default
    capture_output: bool = True
    merge_output: bool = False  # Merge stderr into stdout

    def to_shell_command(self) -> str:
        """Convert to shell command string."""
        if self.arguments:
            import shlex
            args = " ".join(shlex.quote(arg) for arg in self.arguments)
            return f"{self.command} {args}"
        return self.command


@dataclass
class ProcessInfo:
    """Metadata for a running process."""
    process_id: str
    config: ProcessConfig
    state: ProcessState
    pid: Optional[int] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    exit_code: Optional[int] = None
    exit_status: Optional[QProcess.ExitStatus] = None
    error: Optional[str] = None
    output_buffer: List[str] = field(default_factory=list)
    error_buffer: List[str] = field(default_factory=list)

    @property
    def duration(self) -> Optional[float]:
        """Get process duration in seconds."""
        if self.start_time:
            end = self.end_time or time.time()
            return end - self.start_time
        return None

    @property
    def is_active(self) -> bool:
        """Check if process is still active."""
        return self.state in (
            ProcessState.PENDING,
            ProcessState.STARTING,
            ProcessState.RUNNING,
        )


class ProcessWorker(QThread):
    """Simplified worker thread for QProcess execution using waitForFinished."""
    
    # Signals
    started = Signal(str)  # process_id
    output_ready = Signal(str, str)  # process_id, output_line
    error_ready = Signal(str, str)  # process_id, error_line
    finished = Signal(str, int, object)  # process_id, exit_code, status
    failed = Signal(str, str)  # process_id, error_message
    state_changed = Signal(str, object)  # process_id, new_state

    def __init__(
        self, process_id: str, config: ProcessConfig, parent: Optional[QObject] = None
    ):
        super().__init__(parent)
        self.process_id = process_id
        self.config = config
        self._process: Optional[QProcess] = None
        self._should_stop = threading.Event()
        self._state_mutex = QMutex()
        self._cleanup_done = threading.Event()
        self._info = ProcessInfo(
            process_id=process_id, config=config, state=ProcessState.PENDING
        )

    def run(self):
        """Execute the process using waitForFinished with timeout."""
        try:
            self._emit_state_safe(ProcessState.STARTING)
            
            # Create QProcess in this thread
            self._process = QProcess()
            
            # Set up process configuration
            self._setup_process()
            
            # Connect output signals if capturing
            if self.config.capture_output:
                self._process.readyReadStandardOutput.connect(self._read_stdout)
                self._process.readyReadStandardError.connect(self._read_stderr)
            
            # Start the process
            self._info.start_time = time.time()
            
            if self.config.interactive_bash:
                program = "/bin/bash"
                arguments = ["-i", "-c", self.config.to_shell_command()]
            elif self.config.use_shell:
                program = "/bin/sh"
                arguments = ["-c", self.config.to_shell_command()]
            else:
                program = self.config.command
                arguments = self.config.arguments
            
            self._process.start(program, arguments)
            
            # Wait for process to start
            if not self._process.waitForStarted(5000):
                error = self._process.errorString()
                self._emit_error_safe(f"Process failed to start: {error}")
                return
            
            # Process started successfully
            self._info.pid = self._process.processId()
            self._emit_state_safe(ProcessState.RUNNING)
            self.started.emit(self.process_id)
            logger.debug(f"Process {self.process_id} started with PID {self._info.pid}")
            
            # SIMPLIFIED: Use waitForFinished with timeout
            # This blocks the thread but handles timeout properly
            timeout_ms = self.config.timeout_ms if self.config.timeout_ms > 0 else -1
            finished = self._process.waitForFinished(timeout_ms)
            
            if not finished:
                # Timeout occurred
                logger.warning(f"Process {self.process_id} timed out after {timeout_ms}ms")
                self._process.terminate()
                if not self._process.waitForFinished(2000):
                    logger.warning(f"Force killing process {self.process_id}")
                    self._process.kill()
                    self._process.waitForFinished(1000)
                
                self._info.end_time = time.time()
                self._info.exit_code = -1
                self._info.state = ProcessState.TERMINATED
                self.finished.emit(self.process_id, -1, QProcess.ExitStatus.CrashExit)
            else:
                # Process finished normally
                self._info.end_time = time.time()
                self._info.exit_code = self._process.exitCode()
                self._info.exit_status = self._process.exitStatus()
                
                # Read any remaining output
                if self.config.capture_output:
                    self._read_remaining_output()
                
                if self._info.exit_status == QProcess.ExitStatus.CrashExit:
                    self._emit_state_safe(ProcessState.CRASHED)
                elif self._info.exit_code == 0:
                    self._emit_state_safe(ProcessState.FINISHED)
                else:
                    self._emit_state_safe(ProcessState.FAILED)
                
                self.finished.emit(
                    self.process_id, 
                    self._info.exit_code, 
                    self._info.exit_status
                )
                
                logger.debug(
                    f"Process {self.process_id} finished with code {self._info.exit_code} "
                    f"(status: {self._info.exit_status})"
                )
                
        except Exception as e:
            logger.exception(f"Worker exception for {self.process_id}")
            self._emit_error_safe(f"Worker exception: {str(e)}")
        finally:
            self._cleanup_safe()

    def _setup_process(self):
        """Setup QProcess configuration."""
        if not self._process:
            return
            
        # Set environment
        if self.config.environment:
            env = QProcessEnvironment.systemEnvironment()
            for key, value in self.config.environment.items():
                env.insert(key, value)
            self._process.setProcessEnvironment(env)
        
        # Set working directory
        if self.config.working_directory:
            self._process.setWorkingDirectory(self.config.working_directory)
        
        # Configure output channels
        if self.config.merge_output:
            self._process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        elif not self.config.capture_output:
            self._process.setStandardOutputFile(QProcess.nullDevice())
            self._process.setStandardErrorFile(QProcess.nullDevice())

    def _read_stdout(self):
        """Read standard output."""
        if not self._process:
            return
        
        stdout_data = self._process.readAllStandardOutput()
        if stdout_data:
            text = stdout_data.data().decode("utf-8", errors="replace")
            for line in text.splitlines():
                if line:
                    self._info.output_buffer.append(line)
                    self.output_ready.emit(self.process_id, line)

    def _read_stderr(self):
        """Read standard error."""
        if not self._process or self.config.merge_output:
            return
        
        stderr_data = self._process.readAllStandardError()
        if stderr_data:
            text = stderr_data.data().decode("utf-8", errors="replace")
            for line in text.splitlines():
                if line:
                    self._info.error_buffer.append(line)
                    self.error_ready.emit(self.process_id, line)

    def _read_remaining_output(self):
        """Read any remaining output after process finishes."""
        if not self._process:
            return
        
        # Read remaining stdout
        self._read_stdout()
        
        # Read remaining stderr
        if not self.config.merge_output:
            self._read_stderr()

    def stop(self):
        """Request the worker to stop."""
        logger.debug(f"Stop requested for process {self.process_id}")
        self._should_stop.set()
        
        # Terminate the process if still running
        if self._process and self._process.state() != QProcess.ProcessState.NotRunning:
            self._process.terminate()
            if not self._process.waitForFinished(2000):
                self._process.kill()
                self._process.waitForFinished(1000)
        
        # Wait for cleanup
        if not self._cleanup_done.wait(5):
            logger.warning(f"Cleanup timeout for process {self.process_id}")

    def _emit_state_safe(self, state: ProcessState):
        """Thread-safe state emission."""
        with QMutexLocker(self._state_mutex):
            old_state = self._info.state
            if old_state != state:
                self._info.state = state
                self.state_changed.emit(self.process_id, state)

    def _emit_error_safe(self, error_message: str):
        """Thread-safe error emission."""
        logger.error(f"Process {self.process_id}: {error_message}")
        with QMutexLocker(self._state_mutex):
            self._info.error = error_message
            self._info.state = ProcessState.FAILED
        self.failed.emit(self.process_id, error_message)
        self.state_changed.emit(self.process_id, ProcessState.FAILED)

    def _cleanup_safe(self):
        """Thread-safe cleanup of resources."""
        try:
            if self._process:
                # Ensure process is terminated
                if self._process.state() != QProcess.ProcessState.NotRunning:
                    self._process.kill()
                    self._process.waitForFinished(1000)
                
                # Clean up QProcess
                self._process.deleteLater()
                self._process = None
        finally:
            self._cleanup_done.set()

    def get_info(self) -> ProcessInfo:
        """Get current process information."""
        with QMutexLocker(self._state_mutex):
            return self._info


class QProcessManager(QObject):
    """Central manager for all QProcess instances (simplified)."""
    
    # Signals
    process_started = Signal(str, object)  # process_id, info
    process_finished = Signal(str, object)  # process_id, info
    process_output = Signal(str, str)  # process_id, line
    process_error = Signal(str, str)  # process_id, line
    process_state_changed = Signal(str, object)  # process_id, state

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._processes: Dict[str, ProcessInfo] = {}
        self._workers: Dict[str, ProcessWorker] = {}
        self._lock = threading.RLock()
        logger.info("QProcessManager initialized (simplified version)")

    def execute(
        self,
        command: str,
        arguments: Optional[List[str]] = None,
        working_directory: Optional[str] = None,
        environment: Optional[Dict[str, str]] = None,
        interactive_bash: bool = False,
        capture_output: bool = True,
        timeout_ms: Optional[int] = None,
        process_id: Optional[str] = None,
    ) -> Optional[str]:
        """Execute a process with the given configuration."""
        # Generate process ID if not provided
        if not process_id:
            process_id = f"proc_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"

        # Create configuration
        config = ProcessConfig(
            command=command,
            arguments=arguments or [],
            working_directory=working_directory,
            environment=environment,
            interactive_bash=interactive_bash,
            timeout_ms=timeout_ms or 30000,
            capture_output=capture_output,
        )

        # Create and start worker
        return self._launch_worker(process_id, config)

    def execute_shell(
        self,
        command: str,
        working_directory: Optional[str] = None,
        environment: Optional[Dict[str, str]] = None,
        capture_output: bool = True,
        timeout_ms: Optional[int] = None,
        process_id: Optional[str] = None,
    ) -> Optional[str]:
        """Execute a shell command."""
        if not process_id:
            process_id = f"shell_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"

        config = ProcessConfig(
            command=command,
            working_directory=working_directory,
            environment=environment,
            use_shell=True,
            capture_output=capture_output,
            timeout_ms=timeout_ms or 30000,
        )

        return self._launch_worker(process_id, config)

    def _launch_worker(self, process_id: str, config: ProcessConfig) -> str:
        """Launch a worker thread for process execution."""
        # Create worker
        worker = ProcessWorker(process_id, config, parent=self)

        # Connect signals
        worker.started.connect(
            lambda pid: self._on_process_started(pid, worker.get_info())
        )
        worker.finished.connect(self._on_process_finished)
        worker.failed.connect(self._on_process_failed)
        worker.state_changed.connect(self._on_state_changed)

        if config.capture_output:
            worker.output_ready.connect(self.process_output.emit)
            worker.error_ready.connect(self.process_error.emit)

        # Store references
        with self._lock:
            self._processes[process_id] = worker.get_info()
            self._workers[process_id] = worker

        # Start worker
        worker.start()

        logger.debug(f"Started worker for process {process_id}")
        return process_id

    def _on_process_started(self, process_id: str, info: ProcessInfo):
        """Handle process started event."""
        with self._lock:
            self._processes[process_id] = info
        self.process_started.emit(process_id, info)

    def _on_process_finished(
        self, process_id: str, exit_code: int, exit_status: QProcess.ExitStatus
    ):
        """Handle process finished event."""
        with self._lock:
            if process_id in self._processes:
                info = self._processes[process_id]
                info.exit_code = exit_code
                info.exit_status = exit_status
                info.end_time = time.time()
                self.process_finished.emit(process_id, info)

    def _on_process_failed(self, process_id: str, error: str):
        """Handle process failure."""
        with self._lock:
            if process_id in self._processes:
                info = self._processes[process_id]
                info.error = error
                info.state = ProcessState.FAILED
                info.end_time = time.time()
                self.process_finished.emit(process_id, info)

    def _on_state_changed(self, process_id: str, state: ProcessState):
        """Handle process state change."""
        with self._lock:
            if process_id in self._processes:
                self._processes[process_id].state = state
        self.process_state_changed.emit(process_id, state)

    def get_process_info(self, process_id: str) -> Optional[ProcessInfo]:
        """Get information about a process."""
        with self._lock:
            return self._processes.get(process_id)