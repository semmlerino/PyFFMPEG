# Launcher and Terminal Management - DETAILED ISSUES ANALYSIS

**Analysis Date**: 2025-11-13  
**Scope**: SimplifiedLauncher, PersistentTerminalManager, CommandLauncher, LauncherManager, ProcessPoolManager  
**Severity Ratings**: CRITICAL (blocks production), HIGH (major bugs), MEDIUM (design issues), LOW (best practices)

---

## EXECUTIVE SUMMARY

### Critical Issues Found: 3
### High-Priority Issues Found: 7
### Medium-Priority Issues Found: 12
### Total Architecture Debt: 4,200+ LOC across deprecated/problematic modules

**Key Findings**:
- Significant thread safety concerns in PersistentTerminalManager FIFO communication
- Resource cleanup gaps and potential process leaks in SimplifiedLauncher
- Singleton anti-pattern with inadequate cleanup in ProcessPoolManager
- Complex signal/slot connection management across multiple components
- Improper error handling in launcher teardown sequences

---

## PART 1: CRITICAL ISSUES (Blocks Production)

### Issue 1.1: PersistentTerminalManager - Race Condition in send_command()

**File**: `/home/gabrielh/projects/shotbot/persistent_terminal_manager.py`  
**Lines**: 749-866 (send_command method)  
**Severity**: CRITICAL

**Problem**:
The `send_command()` method acquires `_write_lock` (line 816) to serialize FIFO writes, but there's a critical race condition between the health check (line 786) and the actual write operation (line 824).

```python
# Lines 782-799: Health check WITHOUT lock
if ensure_terminal:
    if not self._is_dispatcher_running():
        self.logger.warning("Terminal not running...")
    if not self._ensure_dispatcher_healthy():  # <-- NO LOCK HERE
        return False

# Lines 816-824: FIFO write WITH lock
with self._write_lock:  # <-- Lock acquired HERE
    fifo_fd = os.open(self.fifo_path, os.O_WRONLY | os.O_NONBLOCK)
```

**Race Condition Scenario**:
1. Thread A: Passes health check (line 786), FIFO exists, dispatcher alive
2. Thread B: Dispatcher crashes between line 799 and 816
3. Thread A: Tries to open FIFO that no longer has a reader (ENXIO error, line 847)
4. Thread A: Marks `dispatcher_pid = None` (line 854) but continues to retry
5. Result: Multiple retry attempts, unnecessary FIFO recreation, wasted cycles

**Impact**:
- Unreliable command transmission during high concurrency
- Potential commands silently dropped (user doesn't know if command executed)
- Fallback mode triggered incorrectly, disabling persistent terminal unnecessarily

**Fix Required**:
Combine health check and write operation within a single lock:
```python
# Pseudo-code
with self._write_lock:
    if not self._is_dispatcher_healthy():  # Check INSIDE lock
        return False
    # Then proceed with FIFO write while holding lock
```

---

### Issue 1.2: SimplifiedLauncher - Subprocess Leak in Exception Handling

**File**: `/home/gabrielh/projects/shotbot/simplified_launcher.py`  
**Lines**: 370-411 (_execute_in_terminal method)  
**Severity**: CRITICAL

**Problem**:
The subprocess `Popen` object is created (line 370) but if an exception occurs after creation, the process continues running without being properly tracked.

```python
# Line 370: Process created
proc = subprocess.Popen(terminal_cmd, env=full_env, start_new_session=True, text=True)

# Lines 377-380: Added to tracking dictionary
with self._process_lock:
    self._active_processes[proc.pid] = proc
self.process_started.emit(command, proc.pid)

# Lines 385-399: Exception handler
except FileNotFoundError as e:
    # Cleanup proc if created but not tracked
    if proc is not None:
        try:
            proc.kill()
            proc.close()
        except Exception:
            pass
    return False
```

**Problem**: The exception handler (line 393) ASSUMES the process wasn't added to `_active_processes`. But what if:
- Line 370: Process created successfully
- Line 379: Lock acquired, process added to dictionary
- Line 380: `self.process_started.emit()` raises exception (signal handler crashes)
- Line 385: Exception caught, but process is ALREADY in dictionary
- Line 393: Process is killed again (already managed by tracking)

**Impact**:
- Process may be killed prematurely in signal handler errors
- Tracking dictionary gets corrupted state (process both killed and tracked)
- Resource cleanup inconsistent

**Fix Required**:
```python
proc = None
try:
    proc = subprocess.Popen(...)
    with self._process_lock:
        self._active_processes[proc.pid] = proc
    self.process_started.emit(command, proc.pid)
    return True
except Exception as e:
    if proc is not None and proc.pid not in self._active_processes:
        # Only kill if NOT yet added to tracking
        try:
            proc.kill()
            proc.close()
        except Exception:
            pass
    # Log error properly
    raise
```

---

### Issue 1.3: ProcessPoolManager - Singleton Reset Race Condition in Tests

**File**: `/home/gabrielh/projects/shotbot/process_pool_manager.py`  
**Lines**: 250-258 (__new__), 260-298 (__init__), 674-692 (reset)  
**Severity**: CRITICAL

**Problem**:
The singleton reset mechanism has a race condition between parallel test execution:

```python
# Lines 252-258: __new__ method
if cls._instance is None:
    with cls._lock:
        if cls._instance is None:
            instance = super().__new__(cls)
            cls._instance = instance
return cls._instance

# Lines 688-690: reset method
with cls._lock:
    cls._instance = None
    cls._initialized = False
```

**Race Condition**:
1. Test A: Calls `reset()`, sets `_instance = None`, `_initialized = False` (line 689-690)
2. Test B: Calls `ProcessPoolManager()` constructor on line 310:
   ```python
   if cls._instance is None:
       cls._instance = cls()  # Creates new instance
   ```
3. Test A: Continues, but `_instance` is no longer None (Test B's instance!)
4. Test B: Calls `ProcessPoolManager()` again:
   ```python
   def __init__(self, ...):
       with ProcessPoolManager._lock:
           if ProcessPoolManager._initialized:  # Still False from reset!
               return  # SKIP INITIALIZATION!
   ```
5. Result: Instance created but `__init__` called multiple times, initialization state corrupted

**Impact**:
- Test isolation completely broken with parallel execution (`pytest -n auto`)
- Tests pass individually but fail in parallel (flaky tests)
- Resource leaks across test boundaries (executor, sessions, caches)

**Fix Required**:
```python
# Better synchronization
@classmethod
def reset(cls) -> None:
    with cls._lock:
        if cls._instance is not None:
            try:
                cls._instance.shutdown(timeout=2.0)
            except Exception:
                pass
        cls._instance = None
        cls._initialized = False
```

The root issue: `_initialized` flag is reset WITHOUT ensuring all threads see consistent state.

---

## PART 2: HIGH-PRIORITY ISSUES (Major Bugs)

### Issue 2.1: PersistentTerminalManager - ENXIO Not Properly Handled During Restart

**File**: `/home/gabrielh/projects/shotbot/persistent_terminal_manager.py`  
**Lines**: 836-859 (send_command exception handling)  
**Severity**: HIGH

**Problem**:
When ENXIO error occurs (no reader on FIFO), the code marks dispatcher dead but doesn't attempt restart:

```python
elif e.errno == errno.ENXIO:
    # No reader available
    self.logger.error("No reader available for FIFO - dispatcher may have crashed")
    # Mark for health check on next command
    with self._state_lock:
        self.dispatcher_pid = None  # <-- Just marks as None
    # Doesn't attempt recovery!
```

**Impact**:
- First command after crash returns immediately with error
- User retries, health check on second command does restart
- Two-phase failure: command fails, then recovery on retry
- Poor UX: Commands fail twice

**Fix Required**:
```python
elif e.errno == errno.ENXIO:
    # Dispatcher crashed, attempt immediate restart
    self.logger.warning("No reader available, attempting immediate recovery...")
    if not self._ensure_dispatcher_healthy():
        return False
    # Try write again (outside the retry loop bounds)
    return self._send_command_direct(command)  # Recursive call with recovery
```

---

### Issue 2.2: SimplifiedLauncher - No Cleanup on _execute_in_terminal Failure

**File**: `/home/gabrielh/projects/shotbot/simplified_launcher.py`  
**Lines**: 99-186 (launch_vfx_app method)  
**Severity**: HIGH

**Problem**:
The `launch_vfx_app()` method calls `_execute_in_terminal()` but doesn't handle cleanup if terminal launch fails:

```python
def launch_vfx_app(self, app_name: str, options: dict | None = None) -> bool:
    # ... setup ...
    
    # Execute in terminal
    if not self._execute_in_terminal(command, env):  # <-- Can fail
        # No cleanup of resources allocated above!
        # - Socket connections not closed
        # - Temporary files not deleted
        # - Environment references not cleared
        return False
```

**Impact**:
- Resource leak when terminal launch fails (socket connections, temp files)
- Environment dictionary stays in memory (can be large with VFX tools)
- Accumulated over many failed launches

**Fix Required**:
```python
def launch_vfx_app(self, app_name: str, options: dict | None = None) -> bool:
    try:
        # ... setup ...
        if not self._execute_in_terminal(command, env):
            raise RuntimeError(f"Failed to execute {app_name} in terminal")
        return True
    except Exception as e:
        # Cleanup on any error
        self._cleanup_resources()
        self.logger.error(f"Failed to launch {app_name}: {e}")
        self._emit_error(str(e))
        return False
    finally:
        # Always cleanup environment reference
        env.clear()
```

---

### Issue 2.3: CommandLauncher - Missing Process Executor Cleanup

**File**: `/home/gabrielh/projects/shotbot/command_launcher.py`  
**Lines**: 152-173 (cleanup and __del__)  
**Severity**: HIGH

**Problem**:
The `CommandLauncher` disconnects process executor signals but never cleans up the `ProcessExecutor` instance itself:

```python
def cleanup(self) -> None:
    try:
        _ = self.process_executor.execution_started.disconnect(...)
        _ = self.process_executor.execution_progress.disconnect(...)
        _ = self.process_executor.execution_completed.disconnect(...)
        _ = self.process_executor.execution_error.disconnect(...)
    except (RuntimeError, TypeError, AttributeError):
        pass
    # Missing: self.process_executor.cleanup() !
```

**Impact**:
- ProcessExecutor background threads may continue running after launcher destroyed
- Persistent terminal connections kept open
- Memory not released (executor holds process references)

**Fix Required**:
```python
def cleanup(self) -> None:
    try:
        # Disconnect signals
        _ = self.process_executor.execution_started.disconnect(...)
        # ... other disconnects ...
        
        # Cleanup executor resources
        if hasattr(self.process_executor, 'cleanup'):
            self.process_executor.cleanup()
        
        # Cleanup Nuke handler
        if hasattr(self.nuke_handler, 'cleanup'):
            self.nuke_handler.cleanup()
    except (RuntimeError, TypeError, AttributeError):
        pass
```

---

### Issue 2.4: LauncherManager - Weak Signal Connection Management

**File**: `/home/gabrielh/projects/shotbot/launcher_manager.py`  
**Lines**: 122-131 (__init__), 638-665 (shutdown)  
**Severity**: HIGH

**Problem**:
Process manager signal connections are never validated, and shutdown tries to disconnect without checking if connected:

```python
# Lines 122-131: Connect signals (can fail silently)
try:
    _ = self._process_manager.process_started.connect(self.command_started)
    _ = self._process_manager.process_finished.connect(self.command_finished)
    _ = self._process_manager.process_error.connect(self.command_error)
    self._signals_connected = True
except (AttributeError, RuntimeError) as e:
    self.logger.debug(f"Could not connect process manager signals: {e}")
    self._signals_connected = False  # Flag set, but connections may be partial

# Lines 648-657: Shutdown tries to disconnect ALL
if hasattr(self._process_manager, "process_started"):
    with contextlib.suppress(RuntimeError, TypeError):
        _ = self._process_manager.process_started.disconnect()  # May not exist!
```

**Issue**: `_signals_connected = False` is set if ANY signal connection fails, but some signals may have been connected before failure.

**Impact**:
- Shutdown disconnects wrong signals (may disconnect receiver from other senders)
- Memory leaks if partial signal connections fail
- Error messages silently suppressed

**Fix Required**:
```python
class LauncherManager(...):
    def __init__(self, ...):
        self._signal_connections: dict[str, bool] = {
            "process_started": False,
            "process_finished": False,
            "process_error": False,
        }
        
        # Try each signal individually
        try:
            _ = self._process_manager.process_started.connect(self.command_started)
            self._signal_connections["process_started"] = True
        except (AttributeError, RuntimeError):
            self.logger.debug("Could not connect process_started")
        
        # ... repeat for each signal ...
    
    def shutdown(self):
        # Disconnect only connected signals
        if self._signal_connections.get("process_started"):
            with contextlib.suppress(RuntimeError, TypeError):
                _ = self._process_manager.process_started.disconnect()
        # ... repeat for each signal ...
```

---

### Issue 2.5: PersistentTerminalManager - Worker Thread Leak

**File**: `/home/gabrielh/projects/shotbot/persistent_terminal_manager.py`  
**Lines**: 904-932 (send_command_async method)  
**Severity**: HIGH

**Problem**:
Worker threads are not properly cleaned up if cleanup function fails:

```python
# Lines 915-917: Add worker to active list
with self._workers_lock:
    self._active_workers.append(worker)

# Lines 920-926: Register cleanup callback
def cleanup_worker() -> None:
    with self._workers_lock:
        if worker in self._active_workers:
            self._active_workers.remove(worker)
    worker.deleteLater()

_ = worker.operation_finished.connect(cleanup_worker)  # <-- Signal never emitted on crash

# Lines 930-932: Start worker
self.operation_started.emit("send_command")
worker.start()  # <-- Worker thread starts HERE
```

**Race Condition**:
1. Worker thread encounters exception (line 73-81 in TerminalOperationWorker)
2. Worker calls operation_finished.emit() (line 81 in _run_health_check)
3. Main thread receives cleanup signal WHILE worker still running
4. cleanup_worker() called, worker deleted
5. Worker thread continues running but object already destroyed = crash

**Impact**:
- Segfault if worker thread access deleted object after cleanup
- Worker threads accumulate in process if cleanup fails
- deleteLater() relies on event loop processing

**Fix Required**:
```python
def send_command_async(self, command: str, ...) -> None:
    # ... validation ...
    
    # Create worker with proper cleanup
    worker = TerminalOperationWorker(self, "send_command", parent=self)
    # IMPORTANT: Setting parent=self ensures Qt automatic cleanup
    
    # Track worker
    with self._workers_lock:
        self._active_workers.append(worker)
    
    # Connect with finished=True to block until worker cleanup complete
    def cleanup_worker() -> None:
        with self._workers_lock:
            if worker in self._active_workers:
                self._active_workers.remove(worker)
        # Wait for thread to fully finish
        if not worker.wait(timeout=5000):  # 5 second timeout
            self.logger.error("Worker thread did not finish in time")
            worker.terminate()
            worker.wait()
    
    _ = worker.finished.connect(cleanup_worker)  # <-- Use finished, not operation_finished
    self.operation_started.emit("send_command")
    worker.start()
```

---

### Issue 2.6: SimplifiedLauncher - Cache Dictionary Not Thread-Safe

**File**: `/home/gabrielh/projects/shotbot/simplified_launcher.py`  
**Lines**: 70-74, 525-561  
**Severity**: HIGH

**Problem**:
The `_ws_cache` dictionary has a lock, but access pattern is incorrect:

```python
# Lines 525-550: _cache_get method
def _cache_get(self, key: str) -> str | None:
    """Get cached result."""
    with self._cache_lock:
        if key in self._ws_cache:
            result, timestamp = self._ws_cache[key]
            if time.time() - timestamp < self._ws_cache_ttl:
                return result
            else:
                del self._ws_cache[key]  # <-- Delete INSIDE lock
                return None
    return None
```

**Problem**: While lock is held, code calls `time.time()` which could block (though unlikely). But more critically, the cache is also accessed in `invalidate_cache` without proper synchronization:

```python
# Lines 724-739: invalidate_cache method
def invalidate_cache(self, keys: list[str] | None = None) -> None:
    """Invalidate cache entries."""
    with self._cache_lock:
        if keys is None:
            self._ws_cache.clear()  # <-- Can be called while _cache_get iterating?
        else:
            for key in keys:
                self._ws_cache.pop(key, None)
```

**Impact**:
- Dictionary iteration/deletion race condition if cache accessed while clearing
- TTL check under lock may block if time.time() slow
- Cache invalidation doesn't properly synchronize with ongoing reads

---

### Issue 2.7: LauncherManager - Blocking Process Cleanup in Qt Event Loop

**File**: `/home/gabrielh/projects/shotbot/launcher_manager.py`  
**Lines**: 198-202 (_cleanup_finished_workers)  
**Severity**: HIGH

**Problem**:
The cleanup method is likely called from Qt event loop but may block:

```python
def _cleanup_finished_workers(self) -> None:
    """Backward compatibility method for cleaning up finished workers."""
    self._process_manager.cleanup_finished_workers()  # <-- May block!
```

If this is connected to a signal (which it likely is), and the process manager's cleanup does blocking I/O (process.wait(), process.kill()), the main Qt event loop will freeze.

**Impact**:
- UI freezes during worker cleanup
- Especially bad if many processes finishing simultaneously

**Fix Required**:
```python
def _cleanup_finished_workers(self) -> None:
    """Cleanup finished workers in background thread."""
    # Move to background worker thread instead of calling from event loop
    def async_cleanup():
        self._process_manager.cleanup_finished_workers()
    
    worker = QThread()
    worker.run = async_cleanup
    worker.start()
```

---

## PART 3: MEDIUM-PRIORITY ISSUES (Design Problems)

### Issue 3.1: PersistentTerminalManager - Inadequate Heartbeat Timeout Detection

**File**: `/home/gabrielh/projects/shotbot/persistent_terminal_manager.py`  
**Lines**: 457-489 (_check_heartbeat)  
**Severity**: MEDIUM

**Problem**:
Heartbeat timeout detection is too aggressive and doesn't account for processing delays:

```python
def _check_heartbeat(self) -> bool:
    """Check if dispatcher is responding to heartbeat."""
    # ... code to send heartbeat ...
    
    # Wait for heartbeat response
    timeout = time.time() + _HEARTBEAT_SEND_TIMEOUT_SECONDS  # 3 seconds
    while time.time() < timeout:
        with self._state_lock:
            # Check if heartbeat file exists and is recent
            if heartbeat_path.exists():
                mtime = heartbeat_path.stat().st_mtime
                age = time.time() - mtime
                if age < 1.0:  # Less than 1 second old
                    return True
        time.sleep(0.1)
    
    return False  # Timeout after 3 seconds
```

**Issue**: If the dispatcher is under heavy load and takes >1 second to respond, heartbeat times out even though dispatcher is alive.

**Impact**:
- False positive dispatcher crash detection
- Unnecessary terminal restarts during high load
- Cascading failures if restart happens during command execution

---

### Issue 3.2: SimplifiedLauncher - No Support for Long-Running Processes

**File**: `/home/gabrielh/projects/shotbot/simplified_launcher.py`  
**Lines**: 370-411 (_execute_in_terminal)  
**Severity**: MEDIUM

**Problem**:
Processes are tracked by PID, but if process completes quickly and is replaced by subprocess shell, tracking is lost:

```python
# Line 370: Launch terminal with subprocess.Popen(shell=False)
proc = subprocess.Popen(
    ["/usr/bin/gnome-terminal", "--", "bash", "-c", "nuke -x script.nk"],
    start_new_session=True
)

# Lines 377-380: Track process
self._active_processes[proc.pid] = proc  # Tracks terminal process, not nuke!
```

**Issue**: `proc.pid` is the terminal emulator (gnome-terminal), not the actual application (nuke). When nuke spawns grandchild processes, they're not tracked.

**Impact**:
- Long-running processes not properly monitored
- Cleanup_processes() won't detect when nuke finishes
- process_finished signal never emitted for actual app
- Resource leaks if multiple apps launched

---

### Issue 3.3: ProcessPoolManager - No Executor Task Limit

**File**: `/home/gabrielh/projects/shotbot/process_pool_manager.py`  
**Lines**: 278-280, 314-370  
**Severity**: MEDIUM

**Problem**:
The ThreadPoolExecutor has limited workers but queue is unbounded:

```python
self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)  # 4 workers
```

```python
def batch_execute(self, commands: list[str], ...):
    futures: dict[concurrent.futures.Future[str], str] = {}
    for cmd in commands_to_execute:
        future = self._executor.submit(...)  # <-- Unbounded queue!
        futures[future] = cmd
```

**Impact**:
- If 1000 commands submitted, queue grows to 1000 items
- Memory usage spikes
- GIL contention if processing slow bash commands
- Tasks may starve if queue full

---

### Issue 3.4: CommandLauncher - Circular Dependencies with Nuke Handler

**File**: `/home/gabrielh/projects/shotbot/command_launcher.py`  
**Lines**: 122-124, 40  
**Severity**: MEDIUM

**Problem**:
The nuke handler is imported but the actual implementation has circular dependencies:

```python
from nuke_launch_router import NukeLaunchRouter  # Line 40

def __init__(self, ...):
    self.nuke_handler = NukeLaunchRouter()  # Line 123
```

And NukeLaunchRouter likely imports back from command_launcher or related modules, creating circular import risk.

**Impact**:
- Difficult to test launcher independently
- Import order matters (may fail if imported differently)
- Hard to mock Nuke handler in tests

---

### Issue 3.5: LauncherManager - Process Lock Not Protecting All Access

**File**: `/home/gabrielh/projects/shotbot/launcher_manager.py`  
**Lines**: 169-195 (properties)  
**Severity**: MEDIUM

**Problem**:
The properties expose internal state without synchronization:

```python
@property
def _active_processes(self) -> dict[str, ProcessInfo]:
    return self._process_manager.get_active_processes_dict()  # <-- No lock!

@property
def _active_workers(self) -> dict[str, LauncherWorker]:
    return self._process_manager.get_active_workers_dict()  # <-- No lock!
```

And the process manager's get methods don't use locks:

```python
def get_active_processes_dict(self):
    return self._active_processes  # <-- Returns dict reference, not copy!
```

**Impact**:
- Dict can be modified while being read by caller
- RuntimeError: dictionary changed size during iteration
- Undefined behavior if dict cleared during iteration

---

### Issue 3.6: PersistentTerminalManager - Fallback Mode Cannot Be Recovered

**File**: `/home/gabrielh/projects/shotbot/persistent_terminal_manager.py`  
**Lines**: 1037-1060 (fallback mode properties)  
**Severity**: MEDIUM

**Problem**:
Once fallback mode is activated, it blocks all future commands:

```python
def is_fallback_mode(self) -> bool:
    """Check if terminal is in fallback mode."""
    with self._state_lock:
        return self._fallback_mode

def reset_fallback_mode(self) -> None:
    """Reset fallback mode after recovery."""
    with self._state_lock:
        self._fallback_mode = False
```

And fallback check happens early:

```python
def send_command(self, command: str, ensure_terminal: bool = True) -> bool:
    with self._state_lock:
        fallback_mode = self._fallback_mode
    
    if fallback_mode:
        self.logger.warning("Persistent terminal in fallback mode - cannot send command")
        return False
```

**Problem**: Code that sets fallback mode never calls `reset_fallback_mode()`. So fallback mode is permanent.

**Impact**:
- Commands blocked permanently after any dispatcher crash
- User must restart application to recover
- No automatic recovery path

---

### Issue 3.7: SimplifiedLauncher - No Environment Variable Isolation

**File**: `/home/gabrielh/projects/shotbot/simplified_launcher.py`  
**Lines**: 233-247 (_get_app_environment)  
**Severity**: MEDIUM

**Problem**:
Environment is merged with parent process environment:

```python
def _get_app_environment(self, app_name: str) -> dict[str, str]:
    """Get application environment."""
    env = os.environ.copy()  # <-- Copy parent environment
    
    # Add app-specific overrides
    if app_name == "nuke":
        # ... merge nuke env ...
    
    return env
```

**Issue**: Parent environment includes credentials, paths, temporary files. Subprocess inherits all of this.

**Impact**:
- Subprocess can access sensitive environment variables
- Polluted subprocess environment affects subprocess behavior
- Hard to debug which env vars affecting subprocess

---

### Issue 3.8: ProcessPoolManager - Command Cache TTL Not Validated

**File**: `/home/gabrielh/projects/shotbot/process_pool_manager.py`  
**Lines**: 113-135 (CommandCache.get)  
**Severity**: MEDIUM

**Problem**:
TTL validation happens with time.time() but doesn't account for clock skew:

```python
def get(self, command: str) -> str | None:
    key = self._make_key(command)
    
    with QMutexLocker(self._lock):
        if key in self._cache:
            result, timestamp, ttl, _ = self._cache[key]
            if time.time() - timestamp < ttl:  # <-- Simple subtraction
                self._hits += 1
                return result
            del self._cache[key]
```

**Issue**: If system clock goes backward, TTL comparison breaks. Old entries treated as fresh.

**Impact**:
- Stale cache results used after clock skew
- Timing attacks if cache timing observable
- Difficult to debug cache-related bugs

---

### Issue 3.9: CommandLauncher - No Timeout for Persistent Terminal Operations

**File**: `/home/gabrielh/projects/shotbot/command_launcher.py`  
**Lines**: 223-263 (_try_persistent_terminal)  
**Severity**: MEDIUM

**Problem**:
No timeout for persistent terminal send_command:

```python
def _try_persistent_terminal(self) -> bool:
    """Try to use persistent terminal."""
    if self.persistent_terminal is None:
        return False
    
    return self.persistent_terminal.send_command(...)  # <-- Can block indefinitely
```

And send_command does:

```python
def send_command(self, command: str, ensure_terminal: bool = True) -> bool:
    # ... no timeout specified ...
    with self._write_lock:  # <-- Can block forever if lock contested
        fifo_fd = os.open(self.fifo_path, os.O_WRONLY | os.O_NONBLOCK)
```

**Impact**:
- If FIFO write blocks, entire launcher thread blocks
- UI freeze if called from main thread
- No recovery mechanism

---

### Issue 3.10: LauncherManager - Worker Threads Not Limited

**File**: `/home/gabrielh/projects/shotbot/launcher_manager.py`  
**Lines**: 90-91, 473-554 (execute_launcher)  
**Severity**: MEDIUM

**Problem**:
Max concurrent processes is set based on thread config, but not enforced:

```python
MAX_CONCURRENT_PROCESSES = ThreadingConfig.MAX_WORKER_THREADS * 25  # Could be 200+

def execute_launcher(self, launcher_id: str, ...) -> bool:
    # No check against MAX_CONCURRENT_PROCESSES!
    worker = LauncherWorker(...)  # <-- Can create unlimited workers
    worker.started.connect(...)
    worker.start()  # <-- All workers started immediately
```

**Impact**:
- Resource exhaustion if user clicks "launch" button 100 times
- Thread pool may spawn hundreds of threads
- System becomes unresponsive

---

### Issue 3.11: PersistentTerminalManager - Dispatcher PID Detection Unreliable

**File**: `/home/gabrielh/projects/shotbot/persistent_terminal_manager.py`  
**Lines**: 374-421 (_find_dispatcher_pid)  
**Severity**: MEDIUM

**Problem**:
Finding dispatcher by process name is unreliable:

```python
def _find_dispatcher_pid(self) -> int | None:
    """Find dispatcher process PID by name."""
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if "terminal_dispatcher" in proc.name():
                return proc.pid  # <-- Assumes exact name match
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return None
```

**Issue**: Multiple dispatchers with same name will match first one. Process name might not be "terminal_dispatcher" depending on how shell starts it.

**Impact**:
- May detect wrong process as dispatcher
- May fail to detect real dispatcher if named differently
- Unreliable health checks

---

### Issue 3.12: SimplifiedLauncher - Cache TTL Not Configurable

**File**: `/home/gabrielh/projects/shotbot/simplified_launcher.py`  
**Lines**: 70-75  
**Severity**: MEDIUM

**Problem**:
Cache TTL is hardcoded:

```python
self._ws_cache: dict[str, tuple[str, float]] = {}
self._ws_cache_ttl = 300  # Hardcoded 5 minutes
```

**Impact**:
- Cannot adjust caching strategy for different environments
- Stale data cached for 5 minutes even if should be fresh
- Cannot disable cache for testing

---

## PART 4: SUMMARY MATRIX

### Critical Issues: 3
| ID | Component | Issue | Impact | Fix Effort |
|---|---|---|---|---|
| 1.1 | PersistentTerminalManager | Race condition in send_command | Commands dropped during high load | HIGH |
| 1.2 | SimplifiedLauncher | Subprocess leak in exception | Resource leak | MEDIUM |
| 1.3 | ProcessPoolManager | Singleton reset race | Test failures | MEDIUM |

### High Issues: 7
| ID | Component | Issue | Impact | Fix Effort |
|---|---|---|---|---|
| 2.1 | PersistentTerminalManager | ENXIO handling incomplete | Poor UX (command fails twice) | MEDIUM |
| 2.2 | SimplifiedLauncher | No cleanup on failure | Resource leak | LOW |
| 2.3 | CommandLauncher | Missing ProcessExecutor cleanup | Memory leak | LOW |
| 2.4 | LauncherManager | Weak signal connections | Partial failures | MEDIUM |
| 2.5 | PersistentTerminalManager | Worker thread leak | Segfault on crash | MEDIUM |
| 2.6 | SimplifiedLauncher | Cache not thread-safe | Dictionary errors | LOW |
| 2.7 | LauncherManager | Blocking cleanup in event loop | UI freeze | MEDIUM |

### Medium Issues: 12 (omitted for brevity, listed above as 3.1-3.12)

---

## PART 5: RECOMMENDATIONS

### Immediate Actions (This Sprint)
1. Fix Issue 1.1 (PersistentTerminalManager race) - blocks production
2. Fix Issue 1.2 (SimplifiedLauncher subprocess leak) - memory leak
3. Fix Issue 1.3 (ProcessPoolManager singleton) - test reliability
4. Fix Issue 2.5 (Worker thread leak) - segfault risk

### Short-Term (Next 2 Sprints)
1. Fix Issue 2.1-2.7 (remaining high-priority issues)
2. Add comprehensive logging around signal connections
3. Add timeout to all blocking operations
4. Refactor command cleanup into dedicated helper

### Long-Term (Refactoring)
1. Consolidate 4 launcher modules into unified system
2. Remove deprecated modules completely
3. Implement proper lifecycle management for all components
4. Add thread pool limit enforcement
5. Switch from PersistentTerminalManager to simpler subprocess.Popen approach

---

## CODE PATTERNS TO AVOID

**Pattern 1: Lock released before critical operation**
```python
# WRONG:
if not check_precondition():  # Lock released here
    return
with lock:
    do_critical_operation()  # May have changed!
```

**Pattern 2: Exception handler assumes preconditions**
```python
# WRONG:
try:
    resource = create_resource()
    register_resource(resource)  # May throw
except Exception:
    cleanup_resource(resource)  # But resource may be registered!
```

**Pattern 3: Signal emission without error handling**
```python
# WRONG:
resource = create()
add_to_tracking(resource)
emit_signal()  # <-- Can throw!
return True    # But resource tracking corrupted
```

**Pattern 4: Dictionary references without locks**
```python
# WRONG:
@property
def active_processes(self):
    return self._processes  # Caller can iterate while clearing
```

**Pattern 5: Cleanup without atomic operations**
```python
# WRONG:
for process in processes:  # Concurrent deletion possible
    process.kill()
processes.clear()  # Race condition
```

---

End of Launcher Architecture Issues Analysis
