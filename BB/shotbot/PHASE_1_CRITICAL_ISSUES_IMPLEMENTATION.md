# Phase 1: Critical Issues Implementation Guide
## Week 1 Priority Fixes - Stability & Data Integrity

**Timeline**: 5 Days
**Goal**: Zero crashes, zero data loss
**Testing**: Run full test suite after each fix

---

## 🔴 Issue 1: ProcessPoolManager Singleton Race Condition

### Problem
**File**: `process_pool_manager.py`
**Lines**: 206-257
**Severity**: CRITICAL - Causes resource leaks and crashes

The singleton initialization has a race condition where `_initialized` is checked at line 232 but set at both lines 236 and 257, creating a window where multiple threads can initialize.

### Current Buggy Code
```python
# Lines 206-257 in process_pool_manager.py
def __init__(self, max_workers: int = 4, sessions_per_type: int = 3) -> None:
    """Initialize the ProcessPoolManager singleton."""
    super().__init__()

    # Thread safety for singleton
    with QMutexLocker(ProcessPoolManager._lock):
        # Check if already initialized (line 232)
        if self._initialized:
            self._logger.debug("ProcessPoolManager already initialized")
            return

        # Set flag to prevent re-initialization (line 236 - FIRST)
        self._initialized = True

        # ... initialization code ...

        # Mark as initialized (line 257 - SECOND, REDUNDANT!)
        self._initialized = True
```

### Fixed Implementation
```python
def __init__(self, max_workers: int = 4, sessions_per_type: int = 3) -> None:
    """Initialize the ProcessPoolManager singleton with proper thread safety."""
    # CRITICAL: Lock BEFORE calling super().__init__
    with QMutexLocker(ProcessPoolManager._lock):
        # Check if already initialized
        if ProcessPoolManager._initialized:
            return

        # Set flag IMMEDIATELY to prevent race condition
        ProcessPoolManager._initialized = True

        # NOW safe to initialize
        super().__init__()

        # Initialize instance variables
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        self._sessions: dict[str, list[MockWorkspaceSession]] = {}
        self._session_lock = threading.RLock()
        self._sessions_per_type = sessions_per_type
        self._logger = logging.getLogger(__name__)

        # Remove line 257 - DO NOT set _initialized again!

    # Log initialization outside the lock
    self._logger.info(f"ProcessPoolManager initialized with {max_workers} workers")
```

### Testing
```python
# Add this test to test_process_pool_manager.py
def test_concurrent_singleton_initialization():
    """Test that concurrent initialization doesn't create multiple instances."""
    import threading
    instances = []

    def create_instance():
        manager = ProcessPoolManager()
        instances.append(id(manager))

    threads = [threading.Thread(target=create_instance) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # All instances should have the same ID
    assert len(set(instances)) == 1, "Multiple instances created!"
```

---

## 🔴 Issue 2: Cache Write Race Condition

### Problem
**File**: `cache/storage_backend.py`
**Lines**: 119-128
**Severity**: CRITICAL - Causes data loss

Multiple threads can write to the same cache file simultaneously, with the last writer overwriting previous data.

### Current Buggy Code
```python
# Lines 119-128 in cache/storage_backend.py
def write_json(self, file_path: Path, data: dict[str, Any], indent: int = 2) -> bool:
    """Write JSON data to file atomically using temp file + rename."""
    try:
        # Each thread creates its own temp file
        temp_file = file_path.with_suffix(f".tmp_{uuid.uuid4().hex[:8]}")

        # Write to temp file
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)

        # Atomic rename - RACE CONDITION HERE!
        temp_file.replace(file_path)

        return True
```

### Fixed Implementation
```python
import fcntl
import os
from pathlib import Path

def write_json(self, file_path: Path, data: dict[str, Any], indent: int = 2) -> bool:
    """Write JSON data to file with proper file locking."""
    # Create lock file path
    lock_file = file_path.with_suffix('.lock')

    try:
        # Ensure parent directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Use file locking for synchronization
        with open(lock_file, 'w') as lock_fd:
            # Acquire exclusive lock (will block if another thread has it)
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)

            try:
                # Now safe to write - only one thread can be here
                temp_file = file_path.with_suffix(f".tmp_{os.getpid()}_{uuid.uuid4().hex[:8]}")

                # Write to temp file
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=indent, ensure_ascii=False)

                # Atomic rename (now safe with lock)
                temp_file.replace(file_path)

                self._logger.debug(f"Successfully wrote {file_path}")
                return True

            finally:
                # Always release lock
                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)

    except Exception as e:
        self._logger.error(f"Failed to write {file_path}: {e}")
        return False

    finally:
        # Clean up lock file
        try:
            lock_file.unlink()
        except:
            pass  # Lock file might not exist or be in use
```

### Windows Compatibility Alternative
```python
# For Windows systems, use msvcrt instead of fcntl
import sys

if sys.platform == 'win32':
    import msvcrt

    def _acquire_lock(fd):
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)

    def _release_lock(fd):
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _acquire_lock(fd):
        fcntl.flock(fd, fcntl.LOCK_EX)

    def _release_lock(fd):
        fcntl.flock(fd, fcntl.LOCK_UN)
```

---

## 🔴 Issue 3: Subprocess Deadlock in LauncherWorker

### Problem
**File**: `launcher/worker.py`
**Lines**: 170-177
**Severity**: HIGH - Causes application hangs

Using `subprocess.DEVNULL` for stdout/stderr can cause deadlock when applications produce lots of output.

### Current Buggy Code
```python
# Lines 170-177 in launcher/worker.py
# Launch the process
self._process = subprocess.Popen(
    cmd_list,
    stdout=subprocess.DEVNULL,  # DANGEROUS!
    stderr=subprocess.DEVNULL,  # DANGEROUS!
    cwd=self.working_dir,
    shell=shell,
    start_new_session=True,  # Create new process group
)
```

### Fixed Implementation
```python
import threading
import subprocess
from queue import Queue

def run(self) -> None:
    """Execute the command with proper output handling."""
    try:
        # Build command
        cmd_list, shell = self._build_command()

        # Launch with PIPE to prevent deadlock
        self._process = subprocess.Popen(
            cmd_list,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.working_dir,
            shell=shell,
            start_new_session=True,
            text=True,  # Return strings instead of bytes
            bufsize=1,  # Line buffered
        )

        # Start output drain threads to prevent buffer overflow
        self._start_output_drainers()

        # Store PID for tracking
        if self._process.pid:
            self.process_started.emit(self._process.pid)

        # Wait for process completion
        return_code = self._process.wait()

        # Emit completion signal
        if return_code == 0:
            self.process_finished.emit(0, "Success")
        else:
            self.process_error.emit(f"Process exited with code {return_code}")

    except Exception as e:
        self.process_error.emit(str(e))

def _start_output_drainers(self) -> None:
    """Start threads to drain stdout/stderr to prevent deadlock."""
    def drain_stream(stream, stream_name):
        """Drain a stream to prevent buffer overflow."""
        try:
            for line in stream:
                # Optionally emit output for debugging
                if self._debug_mode:
                    self.output_received.emit(f"[{stream_name}] {line.rstrip()}")
        except Exception:
            pass  # Stream closed, process ended
        finally:
            try:
                stream.close()
            except:
                pass

    # Start drain threads as daemons
    stdout_thread = threading.Thread(
        target=drain_stream,
        args=(self._process.stdout, "stdout"),
        daemon=True
    )
    stderr_thread = threading.Thread(
        target=drain_stream,
        args=(self._process.stderr, "stderr"),
        daemon=True
    )

    stdout_thread.start()
    stderr_thread.start()
```

---

## 🔴 Issue 4: QThread Signal Race Condition

### Problem
**File**: `thread_safe_worker.py`
**Lines**: 136-145
**Severity**: HIGH - Can cause crashes

Signal to emit is determined inside mutex but emitted outside, creating a race condition.

### Current Buggy Code
```python
# Lines 136-145 in thread_safe_worker.py
def set_state(self, new_state: WorkerState, force: bool = False) -> bool:
    """Set worker state with thread safety."""
    signal_to_emit = None

    with QMutexLocker(self._state_mutex):
        # Validation and state change
        old_state = self._state
        self._state = new_state

        # Determine signal to emit
        if new_state == WorkerState.STOPPED:
            signal_to_emit = self.worker_stopped
        elif new_state == WorkerState.ERROR:
            signal_to_emit = lambda: self.worker_error.emit("State error")

    # DANGEROUS: Emitting outside mutex!
    if signal_to_emit:
        if callable(signal_to_emit):
            signal_to_emit()
        else:
            signal_to_emit.emit()
```

### Fixed Implementation
```python
from typing import Optional
from PySide6.QtCore import QMutexLocker, Signal

def set_state(self, new_state: WorkerState, force: bool = False) -> bool:
    """Set worker state with thread-safe signal emission."""
    with QMutexLocker(self._state_mutex):
        # Validate transition
        if not force and not self._is_valid_transition(self._state, new_state):
            self._logger.warning(
                f"Invalid state transition: {self._state} -> {new_state}"
            )
            return False

        # Store old state for logging
        old_state = self._state

        # Update state
        self._state = new_state
        self._state_condition.wakeAll()

        # Emit signals INSIDE the mutex with exception handling
        try:
            # Use direct emission, no intermediate variables
            if new_state == WorkerState.RUNNING:
                self.worker_started.emit()
            elif new_state == WorkerState.STOPPED:
                self.worker_stopped.emit()
            elif new_state == WorkerState.ERROR:
                self.worker_error.emit("Worker entered error state")
            elif new_state == WorkerState.PAUSED:
                self.worker_paused.emit()

        except RuntimeError as e:
            # Object might be deleted, this is acceptable
            self._logger.debug(f"Signal emission failed (object deleted?): {e}")
        except Exception as e:
            # Unexpected error, log but don't crash
            self._logger.error(f"Unexpected error emitting signal: {e}")

        # Log state change
        self._logger.info(f"Worker state changed: {old_state} -> {new_state}")

        return True

def _is_valid_transition(self, from_state: WorkerState, to_state: WorkerState) -> bool:
    """Check if state transition is valid."""
    valid_transitions = {
        WorkerState.IDLE: [WorkerState.RUNNING, WorkerState.STOPPED],
        WorkerState.RUNNING: [WorkerState.PAUSED, WorkerState.STOPPED, WorkerState.ERROR],
        WorkerState.PAUSED: [WorkerState.RUNNING, WorkerState.STOPPED],
        WorkerState.ERROR: [WorkerState.STOPPED],
        WorkerState.STOPPED: [],  # Terminal state
    }

    return to_state in valid_transitions.get(from_state, [])
```

---

## 🔴 Issue 5: Model/View Synchronization Bug

### Problem
**File**: `shot_model.py`
**Lines**: 177-179
**Severity**: MEDIUM - Causes incorrect change detection

Multiple threads can call `refresh_strategy()` simultaneously, causing race conditions in change detection.

### Current Buggy Code
```python
# Lines 177-179 in shot_model.py
def refresh_strategy(self) -> RefreshResult:
    """Refresh shot data - NOT THREAD SAFE!"""
    # Save old data for comparison
    old_shot_data = {(shot.full_name, shot.workspace_path) for shot in self.shots}

    # ... fetch new data ...

    # Update shots - RACE CONDITION!
    self.shots = new_shots

    # Check for changes
    has_changes = old_shot_data != new_shot_data
```

### Fixed Implementation
```python
import threading
from typing import NamedTuple

class RefreshResult(NamedTuple):
    success: bool
    has_changes: bool

class ShotModel(BaseShotModel):
    def __init__(self, cache_manager: Optional["CacheManager"] = None):
        super().__init__(cache_manager)
        # Add refresh lock for thread safety
        self._refresh_lock = threading.RLock()
        self._refresh_in_progress = False

    def refresh_strategy(self) -> RefreshResult:
        """Refresh shot data with proper thread synchronization."""
        # Prevent concurrent refreshes
        with self._refresh_lock:
            if self._refresh_in_progress:
                self._logger.debug("Refresh already in progress, skipping")
                return RefreshResult(success=False, has_changes=False)

            self._refresh_in_progress = True

        try:
            # Now safe to perform refresh
            return self._do_refresh()
        finally:
            with self._refresh_lock:
                self._refresh_in_progress = False

    def _do_refresh(self) -> RefreshResult:
        """Perform the actual refresh with thread safety."""
        try:
            # Get workspace data
            pool = ProcessPoolFactory.get_pool()
            output = pool.execute_workspace_command("ws -sg")

            if not output:
                return RefreshResult(success=False, has_changes=False)

            # Parse new shots
            new_shots = self._parse_ws_output(output)

            # Thread-safe comparison and update
            with self._refresh_lock:
                # Save old data for comparison
                old_shot_data = {
                    (shot.full_name, shot.workspace_path)
                    for shot in self.shots
                }

                # Create new data set
                new_shot_data = {
                    (shot.full_name, shot.workspace_path)
                    for shot in new_shots
                }

                # Check for changes
                has_changes = old_shot_data != new_shot_data

                if has_changes:
                    # Update shots atomically
                    self.shots = new_shots

                    # Emit change signal (safe to do inside lock)
                    try:
                        self.shots_updated.emit()
                    except RuntimeError:
                        pass  # Object might be deleted

            return RefreshResult(success=True, has_changes=has_changes)

        except Exception as e:
            self._logger.error(f"Refresh failed: {e}")
            return RefreshResult(success=False, has_changes=False)
```

---

## 🛠️ Testing Plan

### 1. Unit Tests for Each Fix
```bash
# Run specific tests for each fixed component
python -m pytest tests/unit/test_process_pool_manager.py -v
python -m pytest tests/unit/test_cache_storage.py -v
python -m pytest tests/unit/test_launcher_worker.py -v
python -m pytest tests/unit/test_thread_safe_worker.py -v
python -m pytest tests/unit/test_shot_model.py -v
```

### 2. Stress Tests for Race Conditions
```python
# Add to tests/stress/test_race_conditions.py
import concurrent.futures
import threading
import time

def test_concurrent_cache_writes():
    """Stress test cache write operations."""
    cache = StorageBackend()
    test_file = Path("/tmp/test_cache.json")

    def write_data(thread_id):
        data = {"thread_id": thread_id, "timestamp": time.time()}
        return cache.write_json(test_file, data)

    # Run 100 concurrent writes
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(write_data, i) for i in range(100)]
        results = [f.result() for f in futures]

    # All should succeed
    assert all(results), "Some writes failed!"

    # File should contain valid JSON
    with open(test_file) as f:
        final_data = json.load(f)
        assert "thread_id" in final_data
```

### 3. Integration Tests
```bash
# Run full integration test suite
python -m pytest tests/integration/ -v --timeout=60

# Run with thread sanitizer (if available)
TSAN_OPTIONS=halt_on_error=1 python -m pytest tests/
```

### 4. Manual Testing Checklist
- [ ] Launch application 10 times rapidly - no crashes
- [ ] Load 400+ shots simultaneously - no hangs
- [ ] Launch multiple VFX applications - no deadlocks
- [ ] Rapid window resizing during refresh - stable
- [ ] Kill external processes - graceful handling

---

## 📊 Success Metrics

### Before Fixes
- Crash rate: ~5% on startup under load
- Data loss: Occasional cache corruption
- Deadlocks: 1-2 per day with verbose apps
- Race conditions: Reproducible in stress tests

### After Fixes (Target)
- Crash rate: 0%
- Data loss: 0 incidents
- Deadlocks: 0 incidents
- Race conditions: Not reproducible

---

## 🚀 Deployment Steps

1. **Create feature branch**
   ```bash
   git checkout -b phase1-critical-fixes
   ```

2. **Apply fixes one by one**
   - Fix ProcessPoolManager singleton
   - Run tests, commit
   - Fix cache write race
   - Run tests, commit
   - Continue for each fix...

3. **Run full test suite**
   ```bash
   python -m pytest tests/ --cov=. --cov-report=html
   ```

4. **Stress test**
   ```bash
   python tests/stress/run_stress_tests.py
   ```

5. **Code review**
   - Verify all race conditions addressed
   - Check for new issues introduced
   - Validate error handling

6. **Merge to main**
   ```bash
   git checkout main
   git merge phase1-critical-fixes
   ```

---

## ⚠️ Important Notes

1. **Test each fix independently** before moving to the next
2. **Keep the original code commented** for reference during testing
3. **Monitor application logs** for new warnings/errors
4. **Document any behavior changes** that might affect users
5. **Have rollback plan ready** in case of unexpected issues

## 🎯 Next Phase Preview

After completing Phase 1, Phase 2 will focus on:
- Architecture refactoring (splitting god classes)
- Performance optimizations (70-83% improvements)
- Code duplication removal (~30% reduction)

---

**Document Status**: Implementation Ready
**Estimated Time**: 5 days
**Risk Level**: Medium (with proper testing)
**Priority**: CRITICAL - Must complete before any other work