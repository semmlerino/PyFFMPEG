# Terminal Lifecycle Management Issues - Comprehensive Analysis

## Critical Issues Identified

### 1. **SIGNAL CONNECTION LEAK in ProcessExecutor** ⚠️ CRITICAL
**File**: `/home/gabrielh/projects/shotbot/launch/process_executor.py` (lines 83-89)

**Issue**: Signals connected in `__init__` are NEVER disconnected:
- `persistent_terminal.operation_progress.connect(self._on_terminal_progress)`
- `persistent_terminal.command_result.connect(self._on_terminal_command_result)`

**Problem**: ProcessExecutor has NO cleanup/disconnect mechanism:
- No `cleanup()` method
- No `__del__` method
- No signal disconnections before destruction
- Signals remain connected even if ProcessExecutor is destroyed

**Impact**:
- ProcessExecutor instances accumulate signal connections
- Each time CommandLauncher is created/destroyed, new connections leak
- Memory leak: slot handlers remain in memory even after object deletion
- Multiple ProcessExecutor instances may exist in MainWindow lifecycle

**Root Cause**: ProcessExecutor connects to persistent_terminal but never cleans up

---

### 2. **INCOMPLETE TERMINAL CLEANUP in TerminalOperationWorker** ⚠️ HIGH
**File**: `/home/gabrielh/projects/shotbot/persistent_terminal_manager.py` (lines 44-127)

**Issue**: Worker signal connections in `send_command_async()` (lines 905-932):
```python
worker = TerminalOperationWorker(self, "send_command", parent=self)
worker.command = command
_ = worker.progress.connect(on_progress)
_ = worker.operation_finished.connect(self._on_async_command_finished)
# ...
_ = worker.operation_finished.connect(cleanup_worker)
worker.start()
```

**Problems**:
1. Worker signals are connected but cleanup happens in closure
2. Closure captures `worker` variable, creating potential circular reference
3. If signal emission fails, cleanup_worker() closure never executes
4. deleteLater() may not execute if event loop blocked
5. Worker remains in memory until Qt event loop processes deleteLater

**Risk**: If PersistentTerminalManager is destroyed while workers are running:
- Workers continue executing in background
- Workers may try to emit signals to destroyed manager
- Segmentation fault possible

---

### 3. **MISSING SIGNAL CLEANUP in CommandLauncher** ⚠️ HIGH
**File**: `/home/gabrielh/projects/shotbot/command_launcher.py` (lines 125-129)

**Issue**: CommandLauncher connects to ProcessExecutor signals:
```python
_ = self.process_executor.execution_started.connect(self._on_execution_started)
_ = self.process_executor.execution_progress.connect(self._on_execution_progress)
_ = self.process_executor.execution_completed.connect(self._on_execution_completed)
_ = self.process_executor.execution_error.connect(self._on_execution_error)
```

**But ProcessExecutor has NO cleanup()**, so connections are never removed.

**Impact**: 
- CommandLauncher disconnects signals (lines 162-169) but ProcessExecutor signals remain connected
- ProcessExecutor slots continue executing after CommandLauncher destroyed
- Cross-object signal leaks

---

### 4. **RACE CONDITION: Dummy Writer FD Management** ⚠️ MEDIUM
**File**: `/home/gabrielh/projects/shotbot/persistent_terminal_manager.py`

**Issue**: Multiple race conditions with dummy writer FD:

**Scenario 1: Concurrent access to _dummy_writer_fd**
- `_open_dummy_writer()` (line 278) checks and opens under lock
- But `_ensure_fifo()` (line 252) also opens dummy writer
- Both check `self._dummy_writer_fd is None` which is racy if close/open interleave

**Scenario 2: FD leak in restart_terminal()**
- Line 1137: `_close_dummy_writer_fd()` called
- Line 1192: `_open_dummy_writer()` called
- If dispatcher doesn't start (timeout at line 1201), dummy writer left open

**Scenario 3: FD not closed on dispatcher crash**
- Dispatcher crashes → PersistentTerminalManager doesn't know
- `_dummy_writer_fd` remains open
- Can't open new dummy writer (FD already exists)
- FIFO becomes uncommunicative

---

### 5. **WORKERS NOT CLEANED UP IN TERMINAL RESTART** ⚠️ MEDIUM
**File**: `/home/gabrielh/projects/shotbot/persistent_terminal_manager.py` (lines 1112-1212)

**Issue**: `restart_terminal()` doesn't wait for/cleanup active workers:
```python
def restart_terminal(self) -> bool:
    # Closes terminal
    _ = self.close_terminal()
    # FIFO recreated
    # BUT: Active workers may still be writing to old FIFO
    if self._launch_terminal():
        # Wait for dispatcher with timeout
        timeout = _DISPATCHER_STARTUP_TIMEOUT_SECONDS
        # ...
        return True
```

**Problem**: 
- Active workers in `_active_workers` list are NOT joined before restart
- Workers may write to old FIFO after it's deleted
- Race condition: FIFO delete vs worker write

**Impact**: 
- Workers get OSError when writing to deleted FIFO
- Command silently fails
- No proper error reporting

---

### 6. **WORKER ZOMBIE PROCESS HANDLING** ⚠️ MEDIUM
**File**: `/home/gabrielh/projects/shotbot/persistent_terminal_manager.py` (lines 905-932)

**Issue**: TerminalOperationWorker lifecycle:
```python
worker = TerminalOperationWorker(self, "send_command", parent=self)
# ...
# Store worker reference
with self._workers_lock:
    self._active_workers.append(worker)

# Connect cleanup signal
def cleanup_worker() -> None:
    with self._workers_lock:
        if worker in self._active_workers:
            self._active_workers.remove(worker)
    worker.deleteLater()

_ = worker.operation_finished.connect(cleanup_worker)
worker.start()
```

**Problems**:
1. Worker parent is PersistentTerminalManager
2. If PersistentTerminalManager is destroyed while workers running:
   - Parent is deleted → Qt auto-deletes children
   - Worker continues running → accessing deleted parent
3. Worker.wait() never called - thread may not finish gracefully
4. deleteLater() requires event loop - if no event loop, worker hangs

**Risk**: Zombie workers writing to destroyed FIFO

---

### 7. **FIFO STALE STATE AFTER CRASH** ⚠️ MEDIUM
**File**: `/home/gabrielh/projects/shotbot/persistent_terminal_manager.py`

**Issue**: Dispatcher crashes but FIFO remains:
- FIFO file exists (created by `_ensure_fifo()`)
- Dummy writer FD still open
- Reader (dispatcher) dead
- Writer (process executor) tries to write → ENXIO error

**Current handling** (line 847-854):
```python
elif e.errno == errno.ENXIO:
    # No reader available
    self.logger.error("No reader available for FIFO...")
    # Mark for health check on next command
    with self._state_lock:
        self.dispatcher_pid = None
```

**Problem**: Only sets dispatcher_pid to None. Doesn't:
- Close dummy writer FD (so next dispatcher can't open it)
- Clean up stale FIFO
- Force restart

**Impact**: FIFO remains in broken state until `cleanup()` called

---

### 8. **MISSING SIGNAL CLEANUP IN LAUNCHER MANAGER** ⚠️ MEDIUM  
**File**: `/home/gabrielh/projects/shotbot/launcher_manager.py`

**Issue**: LauncherManager connects to signals but no guarantee they're all disconnected:
- `_process_manager.process_started.disconnect()` (line 648)
- `_process_manager.process_finished.disconnect()` (line 652)
- `_process_manager.process_error.disconnect()` (line 656)

**Problem**: 
- Used `disconnect()` with no slot specified (disconnects all slots)
- But uses `contextlib.suppress(RuntimeError, TypeError)` - swallows real errors
- If signal wasn't connected, no error raised (silent success)
- Works but fragile - relies on error suppression

---

### 9. **HEADLESS TERMINAL LAUNCH DOES NOT CLEAN UP** ⚠️ MEDIUM
**File**: `/home/gabrielh/projects/shotbot/persistent_terminal_manager.py` (lines 697-748)

**Issue**: Terminal process lifecycle:
```python
for cmd in terminal_commands:
    try:
        proc = subprocess.Popen(cmd, start_new_session=True)
        pid = proc.pid
        
        # Store under lock
        with self._state_lock:
            self.terminal_process = proc
            self.terminal_pid = pid
        
        # Give terminal time to start
        time.sleep(_TERMINAL_RESTART_DELAY_SECONDS)
        
        if self._is_terminal_alive():
            # Success - return
            return True
```

**Problems**:
1. `subprocess.Popen` object stored but never `.wait()` called
2. On cleanup, calls `os.kill()` but doesn't reap zombie process
3. Process handle remains open until garbage collected
4. If terminal crashes, PID becomes zombie until `os.kill()` called

**Impact**: 
- Zombie terminal processes on crash recovery
- Process handles leak until cleanup called

---

### 10. **NO CLEANUP ON FALLBACK MODE** ⚠️ MEDIUM
**File**: `/home/gabrielh/projects/shotbot/persistent_terminal_manager.py`

**Issue**: When `_ensure_dispatcher_healthy()` enters fallback mode (line 983):
```python
if self._restart_attempts >= self._max_restart_attempts:
    self.logger.error(
        f"Exceeded maximum restart attempts ({self._max_restart_attempts}) - "
        f"entering fallback mode. Terminal will not auto-recover."
    )
    self._fallback_mode = True
    return False
```

**Problem**: 
- Sets `_fallback_mode = True` but doesn't:
  - Close dummy writer FD
  - Kill existing terminal process
  - Clean FIFO
- Resources left dangling
- Terminal still running but unreachable
- FD still holding reference to FIFO

**Impact**: Resource leak on repeated failures

---

### 11. **SIGNAL DEADLOCK POTENTIAL** ⚠️ LOW (but possible)
**File**: `/home/gabrielh/projects/shotbot/persistent_terminal_manager.py`

**Issue**: Signal emission while holding locks:

Example:
```python
def send_command(self, ...):
    with self._state_lock:
        fallback_mode = self._fallback_mode
    
    if fallback_mode:
        return False
    
    # ...FIFO write...
    
    self.command_sent.emit(command)  # Emits signal
```

**Problem**: 
- Signal emission is NOT under lock
- Receiver might call methods that acquire locks
- Risk of deadlock if receiver calls back into PersistentTerminalManager

**Risk Level**: Low because receivers are typically slot handlers that don't recurse

---

## Cleanup Verification Status

### What DOES get cleaned up:
✅ PersistentTerminalManager.cleanup() - closes terminal and removes FIFO
✅ CleanupManager._cleanup_terminal() - calls persistent_terminal.cleanup()
✅ CommandLauncher.cleanup() - disconnects process_executor signals
✅ LauncherManager.shutdown() - stops workers and disconnects signals

### What DOES NOT get cleaned up:
❌ ProcessExecutor signals to PersistentTerminalManager - never disconnected
❌ TerminalOperationWorker signals - rely on deleteLater() in closure
❌ ProcessExecutor signals to CommandLauncher - CommandLauncher disconnects its side but ProcessExecutor doesn't
❌ Dummy writer FD on fallback mode entry
❌ Zombie terminal process until os.kill() called

---

## Integration Test Coverage

Tests exist for:
- test_persistent_terminal_manager.py
- test_terminal_integration.py
- test_launcher_workflow_integration.py

But may not cover:
- Signal disconnection verification
- Worker thread cleanup on manager destruction
- FD leak in fallback mode
- Concurrent restart while workers active
