# Threading Deadlock Resolution Plan - DO NOT DELETE

## Executive Summary

This document provides a comprehensive plan to resolve critical threading deadlocks and race conditions in the ShotBot application. These issues pose significant risks including application hangs, resource exhaustion, and data corruption in production environments.

**Impact Assessment:**
- **Severity**: CRITICAL
- **Risk**: Application hangs, data loss, poor user experience
- **Affected Components**: LauncherManager, ProcessPoolManager, ThreadSafeWorker, CacheManager
- **Estimated Fix Time**: 3-4 days
- **Testing Time**: 2-3 days

---

## Critical Issues and Solutions

### Issue 1: LauncherManager Cascading QTimer Deadlock

#### Problem Analysis
**Location**: `launcher_manager.py` lines 1620-1624
**Root Cause**: Non-blocking lock acquisition with unbounded QTimer retry can create cascading timer events

```python
# CURRENT PROBLEMATIC CODE
def _cleanup_finished_workers(self):
    if not self._cleanup_lock.acquire(blocking=False):
        logger.debug("Worker cleanup already in progress, scheduling retry")
        QTimer.singleShot(500, self._cleanup_finished_workers)  # ⚠️ CASCADING RISK
        return
```

**Scenario**: If cleanup takes >500ms and multiple triggers occur, QTimer events accumulate leading to:
- Memory exhaustion from queued timers
- Event loop saturation
- Application unresponsiveness

#### Solution Implementation

```python
# FIXED CODE - launcher_manager.py
class LauncherManager(QObject):
    def __init__(self):
        super().__init__()
        self._cleanup_lock = threading.Lock()
        self._cleanup_scheduled = False  # Prevent multiple pending cleanups
        self._cleanup_in_progress = False
        self._cleanup_timer = QTimer()
        self._cleanup_timer.timeout.connect(self._perform_cleanup_with_reset)
        self._cleanup_timer.setSingleShot(True)
        
    def _cleanup_finished_workers(self):
        """Thread-safe worker cleanup with cascading prevention."""
        # Prevent multiple pending cleanup requests
        if self._cleanup_scheduled:
            logger.debug("Cleanup already scheduled, skipping duplicate request")
            return
            
        if not self._cleanup_lock.acquire(blocking=False):
            # Mark cleanup as scheduled before creating timer
            self._cleanup_scheduled = True
            logger.debug("Worker cleanup in progress, scheduling single retry")
            
            # Use a managed timer to prevent cascading
            if not self._cleanup_timer.isActive():
                self._cleanup_timer.start(500)
            return
            
        try:
            self._cleanup_in_progress = True
            self._cleanup_scheduled = False
            
            # Perform actual cleanup
            finished_workers = []
            
            with self._worker_lock:
                for worker_key, worker in list(self._active_workers.items()):
                    try:
                        state = worker.get_state()
                        if state in ["STOPPED", "DELETED"]:
                            finished_workers.append(worker_key)
                    except Exception as e:
                        logger.error(f"Error checking worker {worker_key}: {e}")
                        finished_workers.append(worker_key)
            
            # Remove finished workers
            for worker_key in finished_workers:
                self._remove_worker(worker_key)
                
        finally:
            self._cleanup_in_progress = False
            self._cleanup_lock.release()
            
    def _perform_cleanup_with_reset(self):
        """Timer callback that resets scheduled flag."""
        self._cleanup_scheduled = False
        self._cleanup_finished_workers()
```

#### Unit Test

```python
# test_launcher_manager_cleanup.py
import time
import threading
from unittest.mock import Mock, patch
import pytest
from PySide6.QtCore import QTimer
from launcher_manager import LauncherManager

def test_cascading_timer_prevention(qtbot):
    """Test that rapid cleanup requests don't create cascading timers."""
    manager = LauncherManager()
    qtbot.addWidget(manager)
    
    # Mock the cleanup lock to simulate long-running cleanup
    original_acquire = manager._cleanup_lock.acquire
    acquire_count = [0]
    
    def mock_acquire(blocking=True):
        acquire_count[0] += 1
        if acquire_count[0] == 1:
            return False  # First attempt fails
        return original_acquire(blocking)
    
    manager._cleanup_lock.acquire = mock_acquire
    
    # Trigger multiple cleanup attempts rapidly
    for _ in range(10):
        manager._cleanup_finished_workers()
        
    # Process events
    qtbot.wait(100)
    
    # Verify only one timer was scheduled
    assert manager._cleanup_scheduled == True
    assert manager._cleanup_timer.isActive() == True
    
    # Wait for timer to fire
    qtbot.wait(600)
    
    # Verify cleanup completed and flag reset
    assert manager._cleanup_scheduled == False
    assert acquire_count[0] == 2  # Initial fail + retry
```

---

### Issue 2: ThreadSafeWorker State Transition Race Condition

#### Problem Analysis
**Location**: `thread_safe_worker.py` lines 224-226
**Root Cause**: Direct state assignment bypasses validation logic

```python
# CURRENT PROBLEMATIC CODE
finally:
    # Ensure we transition to STOPPED
    with QMutexLocker(self._state_mutex):
        if self._state != "STOPPED":
            self._state = "STOPPED"  # ⚠️ BYPASSES VALIDATION
```

**Risk**: Invalid state transitions, worker stuck in undefined state, signal emission inconsistency

#### Solution Implementation

```python
# FIXED CODE - thread_safe_worker.py
from enum import Enum
from PySide6.QtCore import QMutex, QMutexLocker, QWaitCondition

class WorkerState(Enum):
    """Thread-safe worker states."""
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    ERROR = "ERROR"

class ThreadSafeWorker(QThread):
    """Thread worker with atomic state transitions."""
    
    # Valid state transitions
    VALID_TRANSITIONS = {
        WorkerState.IDLE: [WorkerState.RUNNING, WorkerState.STOPPED],
        WorkerState.RUNNING: [WorkerState.PAUSED, WorkerState.STOPPING, WorkerState.ERROR],
        WorkerState.PAUSED: [WorkerState.RUNNING, WorkerState.STOPPING],
        WorkerState.STOPPING: [WorkerState.STOPPED],
        WorkerState.STOPPED: [],  # Terminal state
        WorkerState.ERROR: [WorkerState.STOPPED],
    }
    
    def __init__(self):
        super().__init__()
        self._state = WorkerState.IDLE
        self._state_mutex = QMutex()
        self._state_condition = QWaitCondition()
        self._force_stop = False
        
    def set_state(self, new_state: WorkerState, force: bool = False) -> bool:
        """Atomic state transition with validation.
        
        Args:
            new_state: Target state
            force: Force transition even if invalid (emergency stop)
            
        Returns:
            True if transition successful, False otherwise
        """
        with QMutexLocker(self._state_mutex):
            current_state = self._state
            
            # Check if transition is valid
            if not force and new_state not in self.VALID_TRANSITIONS.get(current_state, []):
                logger.warning(
                    f"Invalid state transition: {current_state.value} -> {new_state.value}"
                )
                return False
            
            # Perform transition
            logger.debug(f"State transition: {current_state.value} -> {new_state.value}")
            self._state = new_state
            
            # Wake waiting threads
            self._state_condition.wakeAll()
            
            # Emit appropriate signal
            if new_state == WorkerState.STOPPED:
                QTimer.singleShot(0, self.worker_stopped.emit)
            elif new_state == WorkerState.ERROR:
                QTimer.singleShot(0, self.worker_error.emit)
                
            return True
    
    def get_state(self) -> WorkerState:
        """Get current state atomically."""
        with QMutexLocker(self._state_mutex):
            return self._state
    
    def wait_for_state(self, target_state: WorkerState, timeout_ms: int = 5000) -> bool:
        """Wait for specific state with timeout."""
        with QMutexLocker(self._state_mutex):
            deadline = QDeadlineTimer(timeout_ms)
            while self._state != target_state:
                if not self._state_condition.wait(self._state_mutex, deadline):
                    return False  # Timeout
            return True
    
    def run(self):
        """Worker thread execution with proper state management."""
        try:
            # Transition to RUNNING
            if not self.set_state(WorkerState.RUNNING):
                logger.error("Failed to start worker")
                return
                
            # Main work loop
            while self.get_state() == WorkerState.RUNNING:
                if self._force_stop:
                    break
                    
                # Check for pause
                if self.get_state() == WorkerState.PAUSED:
                    self.wait_for_state(WorkerState.RUNNING, 100)
                    continue
                    
                # Do actual work
                self._do_work()
                
        except Exception as e:
            logger.exception(f"Worker error: {e}")
            self.set_state(WorkerState.ERROR)
            
        finally:
            # Ensure we transition to STOPPED
            if not self.set_state(WorkerState.STOPPED):
                # Force stop if normal transition fails
                logger.warning("Forcing STOPPED state due to invalid transition")
                self.set_state(WorkerState.STOPPED, force=True)
    
    def safe_stop(self, timeout_ms: int = 5000) -> bool:
        """Safely stop worker with timeout."""
        # Request stop
        if not self.set_state(WorkerState.STOPPING):
            # If can't transition to STOPPING, force it
            self.set_state(WorkerState.STOPPING, force=True)
        
        # Signal thread to stop
        self._force_stop = True
        self._state_condition.wakeAll()
        
        # Wait for thread to finish
        if not self.wait(timeout_ms):
            logger.error(f"Worker failed to stop within {timeout_ms}ms")
            self.terminate()  # Force terminate
            self.wait()  # Wait for termination
            return False
            
        return True
```

#### Unit Test

```python
# test_thread_safe_worker.py
def test_state_transition_validation(qtbot):
    """Test that invalid state transitions are prevented."""
    worker = ThreadSafeWorker()
    
    # Valid transition: IDLE -> RUNNING
    assert worker.set_state(WorkerState.RUNNING) == True
    assert worker.get_state() == WorkerState.RUNNING
    
    # Invalid transition: RUNNING -> IDLE
    assert worker.set_state(WorkerState.IDLE) == False
    assert worker.get_state() == WorkerState.RUNNING
    
    # Valid transition: RUNNING -> PAUSED
    assert worker.set_state(WorkerState.PAUSED) == True
    assert worker.get_state() == WorkerState.PAUSED
    
    # Force transition for emergency stop
    assert worker.set_state(WorkerState.STOPPED, force=True) == True
    assert worker.get_state() == WorkerState.STOPPED

def test_concurrent_state_access(qtbot):
    """Test thread-safe state access under concurrent load."""
    worker = ThreadSafeWorker()
    results = []
    
    def read_state():
        for _ in range(1000):
            state = worker.get_state()
            results.append(state)
    
    def write_state():
        for _ in range(100):
            worker.set_state(WorkerState.RUNNING)
            worker.set_state(WorkerState.PAUSED)
    
    # Start concurrent threads
    threads = []
    for _ in range(5):
        t1 = threading.Thread(target=read_state)
        t2 = threading.Thread(target=write_state)
        threads.extend([t1, t2])
        t1.start()
        t2.start()
    
    # Wait for completion
    for t in threads:
        t.join()
    
    # Verify no invalid states
    valid_states = {WorkerState.IDLE, WorkerState.RUNNING, WorkerState.PAUSED}
    for state in results:
        assert state in valid_states
```

---

### Issue 3: ProcessPoolManager Subprocess Polling Deadlock

#### Problem Analysis
**Location**: `process_pool_manager.py` lines 376-448
**Root Cause**: Tight polling loop with 0.01s timeout causes CPU spinning

```python
# CURRENT PROBLEMATIC CODE
while time.time() - start_time < timeout:
    ready, _, _ = select.select([self._process.stdout], [], [], 0.01)  # ⚠️ CPU SPINNING
    if ready:
        line = self._process.stdout.readline()
```

**Impact**: High CPU usage, potential deadlock if subprocess doesn't produce expected output

#### Solution Implementation

```python
# FIXED CODE - process_pool_manager.py
import select
import time
from typing import Optional, List

class PersistentBashSession:
    """Bash session with efficient subprocess polling."""
    
    # Polling configuration
    INITIAL_POLL_INTERVAL = 0.01  # 10ms
    MAX_POLL_INTERVAL = 0.5  # 500ms
    POLL_BACKOFF_FACTOR = 1.5
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self._process: Optional[subprocess.Popen] = None
        self._poll_interval = self.INITIAL_POLL_INTERVAL
        self._consecutive_empty_polls = 0
        
    def _read_with_backoff(self, timeout: float = 30.0) -> List[str]:
        """Read subprocess output with exponential backoff polling.
        
        Args:
            timeout: Maximum time to wait for output
            
        Returns:
            List of output lines
        """
        if not self._process or not self._process.stdout:
            return []
            
        lines = []
        start_time = time.time()
        poll_interval = self.INITIAL_POLL_INTERVAL
        
        while time.time() - start_time < timeout:
            remaining_time = timeout - (time.time() - start_time)
            if remaining_time <= 0:
                break
                
            # Use select with adaptive timeout
            try:
                ready, _, _ = select.select(
                    [self._process.stdout],
                    [],
                    [],
                    min(poll_interval, remaining_time)
                )
                
                if ready:
                    # Data available - read it
                    line = self._process.stdout.readline()
                    if line:
                        lines.append(line.strip())
                        # Reset backoff on successful read
                        poll_interval = self.INITIAL_POLL_INTERVAL
                        self._consecutive_empty_polls = 0
                        
                        # Check for completion marker
                        if self._is_completion_marker(line):
                            break
                else:
                    # No data - apply backoff
                    self._consecutive_empty_polls += 1
                    poll_interval = min(
                        poll_interval * self.POLL_BACKOFF_FACTOR,
                        self.MAX_POLL_INTERVAL
                    )
                    
                    # Log if polling for extended time
                    if self._consecutive_empty_polls > 10:
                        logger.debug(
                            f"Session {self.session_id}: No output for "
                            f"{self._consecutive_empty_polls} polls, "
                            f"interval: {poll_interval:.3f}s"
                        )
                        
                    # Yield CPU to other threads
                    if poll_interval > 0.1:
                        time.sleep(0.001)  # Small yield
                        
            except select.error as e:
                if e.args[0] != errno.EINTR:
                    logger.error(f"Select error in session {self.session_id}: {e}")
                    break
                    
            except IOError as e:
                if e.errno == errno.EAGAIN:
                    # Resource temporarily unavailable - normal for non-blocking I/O
                    continue
                else:
                    logger.error(f"I/O error in session {self.session_id}: {e}")
                    break
                    
        return lines
    
    def _initialize_session(self, timeout: float = 10.0) -> bool:
        """Initialize bash session with efficient polling.
        
        Returns:
            True if initialization successful
        """
        try:
            # Start bash process
            self._process = subprocess.Popen(
                ["/bin/bash", "-i"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
                universal_newlines=True,
                close_fds=True,
                preexec_fn=os.setsid  # Create new session
            )
            
            # Set non-blocking mode
            import fcntl
            flags = fcntl.fcntl(self._process.stdout, fcntl.F_GETFL)
            fcntl.fcntl(self._process.stdout, fcntl.F_SETFL, flags | os.O_NONBLOCK)
            
            # Wait for prompt with backoff
            lines = self._read_with_backoff(timeout)
            
            # Check if we got a valid prompt
            for line in lines:
                if self._is_prompt(line):
                    logger.info(f"Session {self.session_id} initialized successfully")
                    return True
                    
            logger.warning(f"Session {self.session_id} initialization timeout")
            return False
            
        except Exception as e:
            logger.error(f"Failed to initialize session {self.session_id}: {e}")
            return False
    
    def execute_command(self, command: str, timeout: float = 30.0) -> tuple[str, int]:
        """Execute command with efficient output reading.
        
        Args:
            command: Command to execute
            timeout: Maximum execution time
            
        Returns:
            Tuple of (output, return_code)
        """
        if not self._process:
            if not self._initialize_session():
                return "", -1
                
        try:
            # Generate unique marker
            marker = f"__DONE_{time.time()}__"
            
            # Send command with marker
            full_command = f"{command}; echo '{marker}:$?'"
            self._process.stdin.write(full_command + "\n")
            self._process.stdin.flush()
            
            # Read output with backoff
            lines = self._read_with_backoff(timeout)
            
            # Parse output and return code
            output_lines = []
            return_code = 0
            
            for line in lines:
                if marker in line:
                    # Extract return code
                    try:
                        return_code = int(line.split(":")[-1])
                    except ValueError:
                        return_code = -1
                    break
                else:
                    output_lines.append(line)
                    
            return "\n".join(output_lines), return_code
            
        except Exception as e:
            logger.error(f"Command execution failed in session {self.session_id}: {e}")
            return "", -1
```

#### Unit Test

```python
# test_process_pool_polling.py
import time
import subprocess
from unittest.mock import Mock, patch
import pytest

def test_polling_backoff():
    """Test that polling interval increases with exponential backoff."""
    session = PersistentBashSession("test_session")
    
    # Mock select to simulate no data available
    with patch('select.select') as mock_select:
        mock_select.return_value = ([], [], [])
        
        # Track polling intervals
        poll_intervals = []
        
        def record_interval(rlist, wlist, xlist, timeout):
            poll_intervals.append(timeout)
            return ([], [], [])
        
        mock_select.side_effect = record_interval
        
        # Read with timeout
        session._read_with_backoff(timeout=0.5)
        
        # Verify backoff pattern
        assert len(poll_intervals) > 1
        assert poll_intervals[0] == session.INITIAL_POLL_INTERVAL
        
        # Check that intervals increase
        for i in range(1, min(5, len(poll_intervals))):
            expected = min(
                poll_intervals[i-1] * session.POLL_BACKOFF_FACTOR,
                session.MAX_POLL_INTERVAL
            )
            assert abs(poll_intervals[i] - expected) < 0.01

def test_cpu_yield_on_long_polls():
    """Test that CPU is yielded during long polling intervals."""
    session = PersistentBashSession("test_session")
    
    with patch('select.select') as mock_select:
        mock_select.return_value = ([], [], [])
        
        with patch('time.sleep') as mock_sleep:
            # Force high poll interval
            session._consecutive_empty_polls = 20
            session._read_with_backoff(timeout=0.2)
            
            # Verify sleep was called for CPU yield
            mock_sleep.assert_called()
```

---

### Issue 4: Worker Thread Lifecycle Race Condition

#### Problem Analysis
**Location**: `launcher_manager.py` lines 1643-1653
**Root Cause**: Non-atomic checking of worker state and thread running status

```python
# CURRENT PROBLEMATIC CODE
if state in ["STOPPED", "DELETED"]:
    finished_workers.append(worker_key)
    if worker.isRunning():  # ⚠️ RACE: state could change between checks
        logger.warning(f"Worker {worker_key} marked as {state} but still running")
```

#### Solution Implementation

```python
# FIXED CODE - launcher_manager.py
class LauncherManager(QObject):
    """Launcher manager with atomic worker lifecycle management."""
    
    def __init__(self):
        super().__init__()
        self._active_workers = {}
        self._worker_lock = threading.RLock()
        self._worker_states = {}  # Track worker states atomically
        
    def _check_worker_state_atomic(self, worker_key: str) -> tuple[str, bool]:
        """Atomically check worker state and running status.
        
        Returns:
            Tuple of (state, is_running)
        """
        with self._worker_lock:
            worker = self._active_workers.get(worker_key)
            if not worker:
                return ("DELETED", False)
                
            # Access worker's internal mutex for atomic check
            if hasattr(worker, '_state_mutex'):
                with QMutexLocker(worker._state_mutex):
                    state = worker._state.value if hasattr(worker._state, 'value') else str(worker._state)
                    is_running = worker.isRunning()
                    return (state, is_running)
            else:
                # Fallback for workers without state mutex
                try:
                    state = worker.get_state()
                    is_running = worker.isRunning()
                    return (state, is_running)
                except Exception as e:
                    logger.error(f"Failed to check worker {worker_key}: {e}")
                    return ("ERROR", False)
    
    def _cleanup_finished_workers(self):
        """Cleanup finished workers with atomic state checking."""
        finished_workers = []
        inconsistent_workers = []
        
        with self._worker_lock:
            for worker_key in list(self._active_workers.keys()):
                state, is_running = self._check_worker_state_atomic(worker_key)
                
                if state in ["STOPPED", "DELETED", "ERROR"]:
                    if not is_running:
                        # Consistent state - safe to remove
                        finished_workers.append(worker_key)
                    else:
                        # Inconsistent state - needs special handling
                        inconsistent_workers.append((worker_key, state))
                        logger.warning(
                            f"Worker {worker_key} in {state} but thread still running"
                        )
        
        # Remove finished workers
        for worker_key in finished_workers:
            self._remove_worker_safe(worker_key)
        
        # Handle inconsistent workers
        for worker_key, state in inconsistent_workers:
            self._handle_inconsistent_worker(worker_key, state)
    
    def _remove_worker_safe(self, worker_key: str):
        """Safely remove worker with proper cleanup."""
        with self._worker_lock:
            worker = self._active_workers.pop(worker_key, None)
            if not worker:
                return
                
            # Ensure worker is stopped
            if worker.isRunning():
                logger.info(f"Stopping running worker {worker_key}")
                if hasattr(worker, 'safe_stop'):
                    worker.safe_stop(timeout_ms=2000)
                else:
                    worker.quit()
                    if not worker.wait(2000):
                        worker.terminate()
                        worker.wait()
            
            # Disconnect signals
            try:
                worker.disconnect()
            except Exception:
                pass  # Already disconnected
            
            # Clean up resources
            if hasattr(worker, 'cleanup'):
                worker.cleanup()
            
            # Remove from state tracking
            self._worker_states.pop(worker_key, None)
            
            logger.debug(f"Worker {worker_key} removed successfully")
    
    def _handle_inconsistent_worker(self, worker_key: str, reported_state: str):
        """Handle worker with inconsistent state."""
        logger.warning(f"Handling inconsistent worker {worker_key} in state {reported_state}")
        
        with self._worker_lock:
            worker = self._active_workers.get(worker_key)
            if not worker:
                return
            
            # Try graceful stop first
            if hasattr(worker, 'safe_stop'):
                if worker.safe_stop(timeout_ms=1000):
                    logger.info(f"Successfully stopped inconsistent worker {worker_key}")
                    self._remove_worker_safe(worker_key)
                    return
            
            # Force termination if graceful stop fails
            logger.warning(f"Force terminating worker {worker_key}")
            worker.terminate()
            worker.wait(1000)
            self._remove_worker_safe(worker_key)
    
    def get_worker_status(self) -> dict:
        """Get atomic snapshot of all worker states."""
        with self._worker_lock:
            status = {}
            for worker_key in list(self._active_workers.keys()):
                state, is_running = self._check_worker_state_atomic(worker_key)
                status[worker_key] = {
                    "state": state,
                    "is_running": is_running,
                    "consistent": (state == "RUNNING") == is_running or 
                                 (state in ["STOPPED", "DELETED"]) == (not is_running)
                }
            return status
```

#### Unit Test

```python
# test_worker_lifecycle_race.py
def test_atomic_state_checking(qtbot):
    """Test atomic worker state and running status checking."""
    manager = LauncherManager()
    
    # Create mock worker with state
    mock_worker = Mock()
    mock_worker._state_mutex = QMutex()
    mock_worker._state = WorkerState.RUNNING
    mock_worker.isRunning.return_value = True
    
    # Add worker
    manager._active_workers["test_worker"] = mock_worker
    
    # Check state atomically
    state, is_running = manager._check_worker_state_atomic("test_worker")
    
    assert state == "RUNNING"
    assert is_running == True
    
    # Simulate state change to STOPPED but thread still running
    mock_worker._state = WorkerState.STOPPED
    mock_worker.isRunning.return_value = True
    
    # Check inconsistent state detection
    state, is_running = manager._check_worker_state_atomic("test_worker")
    assert state == "STOPPED"
    assert is_running == True
    
    # Verify cleanup handles inconsistency
    manager._cleanup_finished_workers()
    
    # Worker should be marked for special handling
    status = manager.get_worker_status()
    assert status.get("test_worker", {}).get("consistent") == False

def test_concurrent_worker_cleanup(qtbot):
    """Test thread-safe worker cleanup under concurrent access."""
    manager = LauncherManager()
    
    # Add multiple workers
    for i in range(10):
        worker = Mock()
        worker.get_state.return_value = "RUNNING" if i < 5 else "STOPPED"
        worker.isRunning.return_value = i < 5
        manager._active_workers[f"worker_{i}"] = worker
    
    # Concurrent cleanup attempts
    cleanup_threads = []
    for _ in range(5):
        t = threading.Thread(target=manager._cleanup_finished_workers)
        cleanup_threads.append(t)
        t.start()
    
    # Wait for all cleanups
    for t in cleanup_threads:
        t.join()
    
    # Verify only stopped workers were removed
    assert len(manager._active_workers) == 5
    for key in manager._active_workers:
        assert "worker_" in key
        worker_num = int(key.split("_")[1])
        assert worker_num < 5  # Only running workers remain
```

---

### Issue 5: Cache Thread Synchronization

#### Problem Analysis
**Location**: `cache_manager.py` ThumbnailCacheLoader
**Root Cause**: Async loading returns None immediately without synchronization

```python
# CURRENT PROBLEMATIC CODE
loader = ThumbnailCacheLoader(self, source_path, show, sequence, shot)
pool = QThreadPool.globalInstance()
pool.start(loader)
return None  # ⚠️ Returns before work completes
```

#### Solution Implementation

```python
# FIXED CODE - cache_manager.py
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Optional
import threading

class ThumbnailCacheResult:
    """Result container for async thumbnail caching."""
    
    def __init__(self):
        self.future: Future = Future()
        self.cache_path: Optional[Path] = None
        self.error: Optional[str] = None
        self._complete_event = threading.Event()
        
    def set_result(self, cache_path: Path):
        """Set successful result."""
        self.cache_path = cache_path
        self.future.set_result(cache_path)
        self._complete_event.set()
        
    def set_error(self, error: str):
        """Set error result."""
        self.error = error
        self.future.set_exception(Exception(error))
        self._complete_event.set()
        
    def wait(self, timeout: Optional[float] = None) -> bool:
        """Wait for completion.
        
        Returns:
            True if completed within timeout
        """
        return self._complete_event.wait(timeout)
        
    def get_result(self, timeout: Optional[float] = None) -> Optional[Path]:
        """Get result with optional timeout.
        
        Returns:
            Cached path or None if failed/timeout
        """
        try:
            return self.future.result(timeout=timeout)
        except Exception:
            return None

class ThumbnailCacheLoader(QRunnable):
    """Async thumbnail loader with synchronization."""
    
    class Signals(QObject):
        loaded = Signal(str, str, str, Path)  # show, sequence, shot, cache_path
        failed = Signal(str, str, str, str)  # show, sequence, shot, error_msg
        
    def __init__(
        self,
        cache_manager: 'CacheManager',
        source_path: Path,
        show: str,
        sequence: str,
        shot: str,
        result: Optional[ThumbnailCacheResult] = None
    ):
        super().__init__()
        self.cache_manager = cache_manager
        self.source_path = source_path
        self.show = show
        self.sequence = sequence
        self.shot = shot
        self.signals = self.Signals()
        self.result = result or ThumbnailCacheResult()
        self.setAutoDelete(True)
        
    def run(self):
        """Execute thumbnail caching with result synchronization."""
        try:
            # Perform actual caching
            cache_path = self.cache_manager.cache_thumbnail_direct(
                self.source_path,
                self.show,
                self.sequence,
                self.shot
            )
            
            if cache_path:
                # Set successful result
                self.result.set_result(cache_path)
                
                # Emit signal if still valid
                if hasattr(self, 'signals') and self.signals:
                    try:
                        self.signals.loaded.emit(
                            self.show,
                            self.sequence,
                            self.shot,
                            cache_path
                        )
                    except RuntimeError:
                        pass  # Signals deleted
                        
                logger.debug(f"Successfully cached thumbnail for {self.shot}")
            else:
                # Set error result
                error_msg = f"Cache operation returned None for {self.shot}"
                self.result.set_error(error_msg)
                
                if hasattr(self, 'signals') and self.signals:
                    try:
                        self.signals.failed.emit(
                            self.show,
                            self.sequence,
                            self.shot,
                            error_msg
                        )
                    except RuntimeError:
                        pass
                        
                logger.warning(error_msg)
                
        except Exception as e:
            # Set exception result
            error_msg = f"Exception caching thumbnail for {self.shot}: {e}"
            self.result.set_error(str(e))
            
            if hasattr(self, 'signals') and self.signals:
                try:
                    self.signals.failed.emit(
                        self.show,
                        self.sequence,
                        self.shot,
                        str(e)
                    )
                except RuntimeError:
                    pass
                    
            logger.error(error_msg)

class CacheManager(QObject):
    """Enhanced cache manager with synchronization support."""
    
    def __init__(self, cache_dir: Optional[Path] = None):
        super().__init__()
        self.cache_dir = cache_dir or (Path.home() / ".shotbot" / "cache")
        self._lock = threading.RLock()
        self._active_loaders: dict[str, ThumbnailCacheResult] = {}
        self._loader_executor = ThreadPoolExecutor(max_workers=4)
        
    def cache_thumbnail(
        self,
        source_path: Path,
        show: str,
        sequence: str,
        shot: str,
        wait: bool = False,
        timeout: Optional[float] = None
    ) -> Optional[Union[Path, ThumbnailCacheResult]]:
        """Cache thumbnail with optional synchronization.
        
        Args:
            source_path: Source image path
            show: Show name
            sequence: Sequence name
            shot: Shot name
            wait: If True, wait for completion
            timeout: Maximum wait time in seconds
            
        Returns:
            If wait=True: Cached path or None
            If wait=False: ThumbnailCacheResult for async waiting
        """
        # Check if already cached
        cache_key = f"{show}_{sequence}_{shot}"
        
        with self._lock:
            # Check if already being loaded
            if cache_key in self._active_loaders:
                result = self._active_loaders[cache_key]
                if wait:
                    return result.get_result(timeout)
                return result
                
            # Check if already cached on disk
            cache_path = self.get_cached_thumbnail(show, sequence, shot)
            if cache_path:
                return cache_path
                
            # Create new loader with result container
            result = ThumbnailCacheResult()
            self._active_loaders[cache_key] = result
            
            # Check if on main thread
            app = QApplication.instance()
            is_main_thread = app and QThread.currentThread() == app.thread()
            
            if is_main_thread:
                # Use thread pool for background loading
                loader = ThumbnailCacheLoader(
                    self,
                    source_path,
                    show,
                    sequence,
                    shot,
                    result
                )
                
                # Connect cleanup
                loader.signals.loaded.connect(
                    lambda *args: self._cleanup_loader(cache_key)
                )
                loader.signals.failed.connect(
                    lambda *args: self._cleanup_loader(cache_key)
                )
                
                # Start async loading
                QThreadPool.globalInstance().start(loader)
            else:
                # Direct execution in current thread
                cache_path = self.cache_thumbnail_direct(
                    source_path,
                    show,
                    sequence,
                    shot
                )
                result.set_result(cache_path) if cache_path else result.set_error("Failed")
                self._cleanup_loader(cache_key)
                
        # Return based on wait parameter
        if wait:
            return result.get_result(timeout)
        return result
        
    def _cleanup_loader(self, cache_key: str):
        """Remove completed loader from tracking."""
        with self._lock:
            self._active_loaders.pop(cache_key, None)
            
    def cache_multiple_thumbnails(
        self,
        thumbnails: List[tuple[Path, str, str, str]],
        max_concurrent: int = 4
    ) -> dict[str, ThumbnailCacheResult]:
        """Cache multiple thumbnails concurrently.
        
        Args:
            thumbnails: List of (source_path, show, sequence, shot) tuples
            max_concurrent: Maximum concurrent operations
            
        Returns:
            Dictionary mapping cache keys to results
        """
        results = {}
        semaphore = threading.Semaphore(max_concurrent)
        
        def cache_with_semaphore(item):
            source_path, show, sequence, shot = item
            cache_key = f"{show}_{sequence}_{shot}"
            
            with semaphore:
                result = self.cache_thumbnail(
                    source_path,
                    show,
                    sequence,
                    shot,
                    wait=False
                )
                results[cache_key] = result
                
        # Start all caching operations
        threads = []
        for item in thumbnails:
            t = threading.Thread(target=cache_with_semaphore, args=(item,))
            threads.append(t)
            t.start()
            
        # Wait for all to complete
        for t in threads:
            t.join()
            
        return results
    
    def shutdown(self):
        """Graceful shutdown with loader cleanup."""
        logger.info("CacheManager shutting down...")
        
        with self._lock:
            # Wait for active loaders with timeout
            for cache_key, result in self._active_loaders.items():
                if not result.wait(timeout=2.0):
                    logger.warning(f"Loader {cache_key} failed to complete during shutdown")
                    
            # Clear active loaders
            self._active_loaders.clear()
            
            # Shutdown executor
            self._loader_executor.shutdown(wait=True, timeout=5.0)
            
        logger.info("CacheManager shutdown complete")
```

#### Unit Test

```python
# test_cache_synchronization.py
def test_synchronous_caching(qtbot):
    """Test synchronous thumbnail caching."""
    cache_manager = CacheManager()
    
    # Create test image
    test_image = Path("/tmp/test_image.jpg")
    test_image.write_bytes(b"fake_image_data")
    
    # Cache with wait
    result = cache_manager.cache_thumbnail(
        test_image,
        "show1",
        "seq1",
        "shot1",
        wait=True,
        timeout=5.0
    )
    
    assert result is not None
    assert isinstance(result, Path)
    assert result.exists()

def test_asynchronous_caching(qtbot):
    """Test asynchronous thumbnail caching with future."""
    cache_manager = CacheManager()
    
    # Create test image
    test_image = Path("/tmp/test_image.jpg")
    test_image.write_bytes(b"fake_image_data")
    
    # Cache without wait
    result = cache_manager.cache_thumbnail(
        test_image,
        "show2",
        "seq2",
        "shot2",
        wait=False
    )
    
    assert isinstance(result, ThumbnailCacheResult)
    
    # Wait for completion
    cache_path = result.get_result(timeout=5.0)
    assert cache_path is not None
    assert cache_path.exists()

def test_concurrent_caching(qtbot):
    """Test concurrent thumbnail caching."""
    cache_manager = CacheManager()
    
    # Create test images
    thumbnails = []
    for i in range(10):
        test_image = Path(f"/tmp/test_image_{i}.jpg")
        test_image.write_bytes(f"image_{i}".encode())
        thumbnails.append((test_image, "show", "seq", f"shot{i}"))
    
    # Cache concurrently
    results = cache_manager.cache_multiple_thumbnails(
        thumbnails,
        max_concurrent=4
    )
    
    assert len(results) == 10
    
    # Wait for all results
    for cache_key, result in results.items():
        cache_path = result.get_result(timeout=5.0)
        assert cache_path is not None
```

---

## Testing Strategy

### Unit Testing

1. **Individual Component Tests**
   - Test each fix in isolation
   - Mock external dependencies
   - Verify state transitions
   - Test timeout behaviors

2. **Concurrency Tests**
   - Race condition detection
   - Thread safety verification
   - Deadlock prevention tests
   - Resource leak detection

3. **Integration Tests**
   - End-to-end workflow testing
   - Multi-component interaction
   - Real subprocess testing
   - Performance regression tests

### Test Implementation

```python
# test_threading_comprehensive.py
import pytest
import threading
import time
from unittest.mock import Mock, patch

class TestThreadingFixes:
    """Comprehensive test suite for threading fixes."""
    
    @pytest.fixture
    def thread_monitor(self):
        """Monitor for thread leaks."""
        initial_threads = threading.active_count()
        yield
        # Wait for threads to finish
        time.sleep(0.5)
        final_threads = threading.active_count()
        assert final_threads <= initial_threads + 1, "Thread leak detected"
    
    def test_no_deadlocks(self, thread_monitor):
        """Test that fixes prevent deadlocks."""
        manager = LauncherManager()
        
        # Simulate high concurrency
        threads = []
        for _ in range(100):
            t = threading.Thread(target=manager._cleanup_finished_workers)
            threads.append(t)
            t.start()
        
        # All threads should complete within timeout
        for t in threads:
            t.join(timeout=5.0)
            assert not t.is_alive(), "Deadlock detected"
    
    def test_no_resource_leaks(self, thread_monitor):
        """Test that resources are properly cleaned up."""
        import resource
        
        # Get initial resource usage
        initial_fds = len(os.listdir('/proc/self/fd'))
        
        # Perform operations
        cache_manager = CacheManager()
        for i in range(100):
            cache_manager.cache_thumbnail(
                Path(f"/tmp/test_{i}.jpg"),
                "show",
                "seq",
                f"shot{i}"
            )
        
        cache_manager.shutdown()
        
        # Check resource usage
        final_fds = len(os.listdir('/proc/self/fd'))
        assert final_fds <= initial_fds + 5, "File descriptor leak detected"
```

---

## Implementation Timeline

### Phase 1: Critical Fixes (Day 1)
**Morning (4 hours)**
- [ ] Fix LauncherManager cascading timers
- [ ] Fix ThreadSafeWorker state transitions
- [ ] Write unit tests for both fixes

**Afternoon (4 hours)**
- [ ] Fix ProcessPoolManager polling
- [ ] Implement exponential backoff
- [ ] Performance testing

### Phase 2: Race Condition Fixes (Day 2)
**Morning (4 hours)**
- [ ] Fix worker lifecycle race conditions
- [ ] Implement atomic state checking
- [ ] Add inconsistent state handling

**Afternoon (4 hours)**
- [ ] Fix cache synchronization
- [ ] Implement Future/Promise pattern
- [ ] Write integration tests

### Phase 3: Testing & Validation (Day 3)
**Morning (4 hours)**
- [ ] Run comprehensive test suite
- [ ] Performance benchmarking
- [ ] Stress testing with high concurrency

**Afternoon (4 hours)**
- [ ] Fix any issues found
- [ ] Documentation updates
- [ ] Code review preparation

### Phase 4: Monitoring & Deployment (Day 4)
**Morning (4 hours)**
- [ ] Add monitoring instrumentation
- [ ] Deploy to test environment
- [ ] Monitor for 24 hours

**Afternoon (4 hours)**
- [ ] Analyze monitoring data
- [ ] Final adjustments
- [ ] Production deployment preparation

---

## Monitoring and Validation

### Thread Health Monitoring

```python
# thread_monitor.py
import threading
import time
from collections import defaultdict
from typing import Dict, List

class ThreadHealthMonitor:
    """Monitor thread health and detect issues."""
    
    def __init__(self):
        self.thread_states: Dict[str, dict] = {}
        self.deadlock_threshold = 30.0  # seconds
        self.monitor_thread = None
        self.running = False
        
    def start(self):
        """Start monitoring threads."""
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        
    def _monitor_loop(self):
        """Main monitoring loop."""
        while self.running:
            self._check_thread_health()
            self._detect_deadlocks()
            self._check_resource_usage()
            time.sleep(1.0)
            
    def _check_thread_health(self):
        """Check health of all threads."""
        for thread in threading.enumerate():
            thread_id = thread.ident
            thread_name = thread.name
            
            if thread_id not in self.thread_states:
                self.thread_states[thread_id] = {
                    "name": thread_name,
                    "start_time": time.time(),
                    "last_activity": time.time(),
                    "stuck_count": 0
                }
            else:
                # Update activity if thread is active
                if thread.is_alive():
                    self.thread_states[thread_id]["last_activity"] = time.time()
                    
    def _detect_deadlocks(self):
        """Detect potential deadlocks."""
        current_time = time.time()
        
        for thread_id, state in self.thread_states.items():
            if current_time - state["last_activity"] > self.deadlock_threshold:
                state["stuck_count"] += 1
                
                if state["stuck_count"] > 3:
                    logger.error(
                        f"Potential deadlock detected in thread {state['name']} "
                        f"(ID: {thread_id}), stuck for "
                        f"{current_time - state['last_activity']:.1f}s"
                    )
                    
    def _check_resource_usage(self):
        """Check resource usage."""
        thread_count = threading.active_count()
        
        if thread_count > 50:
            logger.warning(f"High thread count: {thread_count}")
            
        # Check file descriptors
        try:
            fd_count = len(os.listdir('/proc/self/fd'))
            if fd_count > 100:
                logger.warning(f"High file descriptor count: {fd_count}")
        except Exception:
            pass  # Not on Linux
            
    def get_report(self) -> dict:
        """Get health report."""
        return {
            "thread_count": threading.active_count(),
            "thread_states": self.thread_states,
            "potential_deadlocks": [
                thread_id for thread_id, state in self.thread_states.items()
                if state["stuck_count"] > 0
            ]
        }
        
    def stop(self):
        """Stop monitoring."""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5.0)
```

### Validation Checklist

#### Functional Validation
- [ ] No application hangs under normal usage
- [ ] No application hangs under high load
- [ ] Worker cleanup completes successfully
- [ ] Subprocess commands execute properly
- [ ] Thumbnails cache correctly

#### Performance Validation
- [ ] CPU usage remains below 50% during polling
- [ ] Memory usage stable over time
- [ ] No thread accumulation
- [ ] No file descriptor leaks
- [ ] Response times within SLA

#### Stress Testing
- [ ] 100 concurrent workers
- [ ] 1000 rapid cleanup requests
- [ ] 10000 subprocess commands
- [ ] 24-hour endurance test
- [ ] Resource exhaustion testing

---

## Prevention Guidelines

### Threading Best Practices

1. **Always use timeout**
   ```python
   # Good
   thread.join(timeout=5.0)
   lock.acquire(timeout=5.0)
   
   # Bad
   thread.join()
   lock.acquire()
   ```

2. **Avoid nested locks**
   ```python
   # Bad - deadlock risk
   with lock1:
       with lock2:
           pass
   
   # Good - single lock or ordered locking
   with single_lock:
       pass
   ```

3. **Use atomic operations**
   ```python
   # Good
   with lock:
       state = self.state
       running = self.is_running
       
   # Bad
   state = self.state
   running = self.is_running  # Race condition
   ```

4. **Implement graceful shutdown**
   ```python
   def shutdown(self):
       self.running = False
       self.condition.notify_all()
       if self.thread:
           self.thread.join(timeout=5.0)
   ```

### Code Review Checklist

- [ ] All locks have timeouts
- [ ] No nested lock acquisition
- [ ] State checks are atomic
- [ ] Resources properly cleaned up
- [ ] Graceful shutdown implemented
- [ ] Thread leaks prevented
- [ ] Deadlock detection in place
- [ ] Performance monitoring added

---

## Conclusion

This comprehensive plan addresses all identified threading issues in the ShotBot application. The fixes are designed to be implemented incrementally with thorough testing at each stage. The monitoring and validation strategies ensure that the fixes work correctly and prevent regression.

**Total Estimated Time**: 4 days
**Risk Level**: Medium (with proper testing)
**Impact**: High (prevents production failures)

The implementation should proceed in phases with continuous monitoring to ensure system stability throughout the process.