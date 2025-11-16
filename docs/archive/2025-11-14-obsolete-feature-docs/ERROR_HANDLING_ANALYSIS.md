# ERROR HANDLING, RECOVERY, AND EDGE CASE ANALYSIS
## ShotBot Launcher/Terminal/Command System
**Analysis Date:** 2025-11-14 | **Scope:** Very Thorough

---

## EXECUTIVE SUMMARY

The launcher/terminal/command system demonstrates **sophisticated error handling with several strengths but also contains subtle vulnerabilities**:

### Strengths
- Comprehensive FIFO-based communication with retry mechanisms
- Fallback mode with automatic recovery attempts (5-minute cooldown)
- Signal-based Phase 1 & 2 async execution lifecycle
- Extensive thread-safety measures (RLock, state snapshots)
- Resource cleanup with timeout-based worker abandonment

### Critical Issues Identified
1. **Signal/Resource Cleanup Gaps in CommandLauncher**
2. **FIFO Recreation Race Conditions Under High Concurrency**
3. **Worker Abandonment Pattern (Intentional but Risky)**
4. **Error Propagation Through Multi-Layer Stack**
5. **Fallback Retry Logic Can Stack Errors**

---

## 1. ERROR PROPAGATION PATTERNS

### 1.1 CommandLauncher → PersistentTerminalManager → ProcessVerifier

**File:** `command_launcher.py` (Lines 455-625)

```python
# Error flows through callback chain:
send_command_async() 
  → operation_finished signal
    → _on_persistent_terminal_operation_finished()
      → min(self._pending_fallback.keys()) for FIFO retry
```

**Issues:**
- **Missing error context aggregation**: Error messages from PersistentTerminalManager don't include original command context
- **Silent timeout failures**: ProcessVerifier timeout (30s) emits error but CommandLauncher's fallback only retries ONE command from queue
- **FIFO Retry Logic Vulnerability (Lines 370-381)**:
  ```python
  # CRITICAL RACE: Hold lock through entire operation
  with self._fallback_lock:
      if not self._pending_fallback:
          return  # No pending fallback
      
      # Get oldest pending command (FIFO queue)
      oldest_id = min(
          self._pending_fallback.keys(),
          key=lambda k: self._pending_fallback[k][2]  # timestamp
      )
      result = self._pending_fallback.pop(oldest_id, None)
  ```
  - **Gap**: min() throws ValueError if dict becomes empty between empty check and min() call (theoretically with lock held, but comment suggests race consciousness)
  - **Weakness**: Only retries oldest command, potentially dropping newer commands

### 1.2 Terminal Lifecycle Error Propagation

**File:** `persistent_terminal_manager.py` (Lines 1144-1272)

```
send_command()
├─ ensure_terminal=True
│  └─ _ensure_dispatcher_healthy() [CRITICAL PATH]
│     ├─ _is_dispatcher_healthy() [3-point check]
│     │  ├─ _is_dispatcher_alive()
│     │  ├─ _is_dispatcher_running() [heartbeat]
│     │  └─ _send_heartbeat_ping() [optional]
│     └─ _perform_restart_internal() [on failure]
│        └─ restart_terminal() [atomically recreates FIFO]
├─ _send_command_direct() [with 3x retry]
│  └─ ENXIO/ENOENT/EAGAIN handling
└─ emit command_error or command_sent
```

**Error Handling Depth:**
- **Health Check (3 layers):** Process alive, FIFO reader, heartbeat
- **Recovery Attempts:** Max 3 restarts before fallback mode
- **Retry Strategy:** 3 FIFO write attempts with exponential backoff
- **Fallback Cooldown:** 5 minutes before retry

**Weakness:** No error coalescing - each layer logs independently, making root cause analysis difficult.

---

## 2. RECOVERY MECHANISMS

### 2.1 FIFO Atomic Recreation (CRITICAL BUG FIXES #2 & #3)

**File:** `persistent_terminal_manager.py` (Lines 1372-1503)

**Bug Fix #2 (Write Lock):** Prevents TOCTOU race during FIFO unlink/mkfifo
```python
# CRITICAL: Acquire _write_lock to prevent FIFO unlink race
with self._write_lock:  # Serializes with _send_command_direct()
    if Path(self.fifo_path).exists():
        Path(self.fifo_path).unlink()
    # fsync parent directory
    parent_fd = os.open(str(parent_dir), os.O_RDONLY)
    os.fsync(parent_fd)  # Ensure unlink committed to filesystem
    os.close(parent_fd)
```

**Strengths:**
- Atomic temp → real rename prevents partial FIFO state
- Parent directory fsync ensures filesystem durability
- Stale temp FIFO cleanup prevents mkfifo EEXIST

**Remaining Risks:**
- **Deadlock Potential:** `_write_lock` (RLock) used in restart, also held by `_send_command_direct()`. If worker calls health check during FIFO send, could create nested lock scenario
- **fd leak if fsync fails:** Parent dir open/close not wrapped in try/finally
  ```python
  parent_fd = os.open(str(parent_dir), os.O_RDONLY)
  try:
      os.fsync(parent_fd)
  finally:
      os.close(parent_fd)  # ← Should be guaranteed
  ```

### 2.2 Fallback Mode & Auto-Recovery

**File:** `persistent_terminal_manager.py` (Lines 866-903)

```python
# Fallback mode: 5-minute cooldown before retry
if fallback_mode and self._fallback_entered_at:
    cooldown_seconds = 300
    elapsed = time.time() - self._fallback_entered_at
    
    if elapsed >= cooldown_seconds:
        # Attempt recovery outside state lock
        if self._ensure_dispatcher_healthy():
            with self._state_lock:
                self._fallback_mode = False
                self._restart_attempts = 0
        else:
            # Re-enter cooldown
            with self._state_lock:
                self._fallback_entered_at = time.time()
```

**Strengths:**
- Prevents tight retry loops that exhaust system
- Auto-recovery after cooldown reduces manual intervention
- Restart counter reset on successful recovery

**Issues:**
1. **Cooldown Timing Race:** If multiple threads check cooldown simultaneously:
   ```python
   # Thread A reads fallback_entered_at at t=299s
   # Thread B reads fallback_entered_at at t=301s
   # Both attempt recovery, only one succeeds
   # Both may reset restart counter → lost state
   ```

2. **Fallback Mode Signal Not Emitted:** CommandLauncher checks `is_fallback_mode` but no signal when entering/exiting fallback
   ```python
   if self.persistent_terminal.is_fallback_mode:
       # User sees warning in log only
       self.command_executed.emit(
           timestamp,
           "⚠ Persistent terminal unavailable, launching in new terminal..."
       )
   ```

### 2.3 Dispatcher Health Check Layers

**File:** `persistent_terminal_manager.py` (Lines 630-671)

```python
def _is_dispatcher_healthy(self) -> bool:
    # Check 1: Process exists
    if not self._is_dispatcher_alive():
        return False
    
    # Check 2: FIFO has reader
    if not self._is_dispatcher_running():
        return False
    
    # Check 3: Heartbeat (optional, only if received before)
    if last_heartbeat_time > 0:
        age = time.time() - last_heartbeat_time
        if age > self._heartbeat_timeout:
            if not self._send_heartbeat_ping():  # ← BLOCKS UP TO 3s
                return False
```

**Critical Issues:**
1. **Heartbeat Timeout in Health Check:** Sending heartbeat from health check is blocking (3s timeout)
   - If executed during command send, blocks entire `_write_lock` for 3s
   - Can cause apparent UI freezes

2. **Heartbeat Check Inconsistency:** Only sends heartbeat if one was received before
   - First command after startup skips heartbeat (False negative possible)
   - Subsequent dispatcher crash may not be detected until next heartbeat timeout

3. **Process Existence vs. Responsiveness:** `_is_dispatcher_alive()` uses psutil but doesn't verify FIFO readiness
   - Process could be zombie/unresponsive
   - Heartbeat ping catches this but isn't mandatory

---

## 3. EDGE CASES & RACE CONDITIONS

### 3.1 Stale FIFO from Crash

**File:** `persistent_terminal_manager.py` (Lines 317-381)

**Scenario:** Terminal crashes, old FIFO remains with orphaned reader

**Current Handling:**
```python
def _ensure_fifo(self, open_dummy_writer: bool = True) -> bool:
    if not Path(self.fifo_path).exists():
        os.mkfifo(self.fifo_path, 0o600)
    
    # Verify it's a FIFO
    if not stat.S_ISFIFO(file_stat.st_mode):
        self.logger.error(f"Path exists but is not a FIFO: {self.fifo_path}")
        return False
```

**Edge Case:** FIFO exists but reader is dead (orphaned process)
- Detection: `_is_dispatcher_running()` sends heartbeat, times out if no reader
- Recovery: `_ensure_dispatcher_healthy()` → `_perform_restart_internal()` → atomic FIFO recreation
- **Gap:** Orphaned reader still writing to old FIFO. After recreation:
  - New reader on new FIFO
  - Old reader still writing to old FIFO (deleted but file descriptors kept alive)
  - Can cause confusion if old reader eventually dies

### 3.2 Process Crashes During FIFO Write

**File:** `persistent_terminal_manager.py` (Lines 673-731, 953-1027)

**Scenario:** Dispatcher crashes between opening FIFO and reading command

```python
# Worker thread context
with self._write_lock:
    fifo_fd = os.open(self.fifo_path, os.O_WRONLY | os.O_NONBLOCK)
    
    # ← DISPATCHER COULD CRASH HERE (EBADF on write)
    
    with os.fdopen(fifo_fd, "wb", buffering=0) as fifo:
        fifo.write(command.encode("utf-8"))
        fifo.write(b"\n")
```

**Error Handling:**
```python
except OSError as e:
    if e.errno == errno.ENXIO:  # No reader available
        # ← This catches dispatcher crash!
        # Retry up to 3 times with 0.5s delay
        continue
    elif e.errno == errno.EAGAIN:
        # Buffer full - backoff retry
        time.sleep(0.1 * (2 ** attempt))
        continue
```

**Weakness:** All retries happen WITHIN `_write_lock`. If dispatcher constantly crashes during startup:
- 3 retry attempts × 0.5s = 1.5s holding write lock
- Blocks health checks from other threads
- Could trigger timeout in healthcheck thread

### 3.3 Worker Abandonment Pattern

**File:** `persistent_terminal_manager.py` (Lines 1505-1550)

**Critical Design:** Workers that don't stop in 10s are ABANDONED (not terminated)

```python
if not thread.wait(10000):  # 10s timeout
    self.logger.error(
        f"Worker {id(worker)} / Thread {id(thread)} did not stop after 10s. "
        "Abandoning worker to prevent deadlock. It may complete later."
    )
    # DO NOT call terminate() - would deadlock
```

**Why Abandoned?**
- Worker may hold `_restart_lock` or `_state_lock`
- Calling `terminate()` kills thread while locks held
- Abandoned thread would try to release locks → deadlock
- Timeout because worker is mid-health-check or I/O

**Risk Analysis:**
- Worker continues in background, still has references to manager
- Manager state could change (FIFO unlinked, thread pool cleared)
- Worker might crash trying to write to unlinked FIFO
- Subprocess spawned by abandoned worker might outlive manager

**Mitigation in Place:**
- State snapshots taken before worker cleanup (lines 1562-1566)
- Abandoned worker can't corrupt shared state
- BUT: Subprocess may keep terminal open longer than expected

### 3.4 Command Double-Execution via Fallback

**File:** `command_launcher.py` (Lines 348-395)

**Scenario:** ProcessVerifier times out before process starts

```python
# Phase 2: Process verification
success, message = self._process_verifier.wait_for_process(
    self.command,
    enqueue_time=enqueue_time,  # Filter stale PID files
)

if success:
    self.manager.command_verified.emit(timestamp, message)
else:
    # VERIFICATION FAILED - might trigger fallback!
    timestamp = datetime.now().strftime("%H:%M:%S")
    self.manager.command_error.emit(timestamp, f"Verification failed: {message}")
```

**Error Chain:**
1. send_command_async() queues command to persistent terminal
2. ProcessVerifier waits 30s for PID file
3. GUI app (e.g., Nuke) takes 20s to start, writes PID at t=20s
4. Verification succeeds... but if it fails:
   - command_error emitted
   - CommandLauncher._on_persistent_terminal_operation_finished() called
   - Falls back to new terminal with SAME command
   - **Result: Nuke launches twice (once in persistent, once in new terminal)**

**Prevention:**
- ProcessVerifier.wait_for_process() has 30s timeout (CRITICAL FIX noted)
- enqueue_time filters stale PIDs from previous launches
- But if timeout is EXACTLY 30s and app starts at 29.9s, edge case possible

### 3.5 Signal Connection Memory Leaks

**File:** `command_launcher.py` (Lines 116-173, 234-274)

**Pattern:**
```python
# Signal connections tracked for cleanup
self._signal_connections: list[QMetaObject.Connection] = []

self._signal_connections.append(
    self.process_executor.execution_progress.connect(
        self._on_execution_progress, Qt.ConnectionType.QueuedConnection
    )
)
```

**Cleanup:**
```python
def cleanup(self) -> None:
    if hasattr(self, "_signal_connections"):
        for connection in self._signal_connections:
            try:
                _ = QObject.disconnect(connection)
            except (RuntimeError, TypeError):
                pass
        self._signal_connections.clear()
```

**Gaps:**
1. **Missing ProcessExecutor.cleanup():** ProcessExecutor also connects to PersistentTerminalManager signals but cleanup is shallow
   ```python
   # In ProcessExecutor.__init__
   self.persistent_terminal.operation_progress.connect(self._on_terminal_progress)
   self.persistent_terminal.command_result.connect(self._on_terminal_command_result)
   # ← No way to disconnect these!
   ```

2. **Fallback Cleanup Timer:** Created but cleanup only stops timer
   ```python
   if self._fallback_cleanup_timer is not None:
       self._fallback_cleanup_timer.stop()
       self._fallback_cleanup_timer.deleteLater()
   ```
   - Timer signal connections NOT disconnected first
   - Could fire after deleteLater()

### 3.6 Concurrent Restart Attempts

**File:** `persistent_terminal_manager.py` (Lines 1179-1208)

**Scenario:** Multiple threads detect unhealthy dispatcher simultaneously

```python
# Thread A arrives at _ensure_dispatcher_healthy()
# Thread B arrives at _ensure_dispatcher_healthy()
# Both reach _restart_lock at similar time

with self._restart_lock:
    # Re-check health (another thread may have fixed it)
    if self._is_dispatcher_healthy():
        return True
    
    # Increment attempt counter
    with self._state_lock:
        if self._restart_attempts >= self._max_restart_attempts:
            # Enter fallback
            self._fallback_mode = True
```

**Race Window:** Between health check and lock acquisition:
- Thread A checks health (fails)
- Thread B checks health (fails)
- Thread A acquires _restart_lock, restarts terminal, succeeds
- Thread B acquires _restart_lock, re-checks health (succeeds due to A), returns
- **Result: Only one unnecessary restart (safe)**

**Actual Issue:** Restart counter may be incremented twice for same failure:
1. Thread A: health fails → increments to 1 → restarts
2. Thread B: health fails → increments to 2 → continues
3. If either restart fails → could hit max faster

---

## 4. SIGNAL ERROR HANDLING PATTERNS

### 4.1 Phase 1 & 2 Execution Lifecycle

**File:** `persistent_terminal_manager.py` (Lines 222-226)

```python
# Phase 1: Queuing/Execution
command_queued = Signal(str, str)  # timestamp, command
command_executing = Signal(str)    # timestamp

# Phase 2: Verification
command_verified = Signal(str, str)  # timestamp, message
command_error = Signal(str, str)     # timestamp, error

# Legacy (backward compat)
command_result = Signal(bool, str)   # success, error_message
```

**Error Signal Paths:**
1. **Verification Fails:** command_error emitted (Phase 2)
   ```python
   if success:
       self.manager.command_verified.emit(timestamp, message)
   else:
       self.manager.command_error.emit(timestamp, f"Verification failed: {message}")
   ```

2. **Worker Interrupted:** operation_finished(False, "Operation interrupted")
   ```python
   if self.isInterruptionRequested():
       self.operation_finished.emit(False, "Operation interrupted")
   ```

3. **Health Check Fails:** operation_finished(False, "Terminal recovery failed")
   ```python
   if not self.manager._ensure_dispatcher_healthy(worker=self):
       self.operation_finished.emit(False, "Terminal not healthy")
   ```

**Weakness:** No unified error codes - strings are unique, hard to match patterns
- CommandLauncher can't distinguish "verification failed" from "terminal recovery failed"
- Same handler processes both, may apply wrong fallback strategy

### 4.2 Error Handler in CommandLauncher

**File:** `command_launcher.py` (Lines 337-346, 348-395)

```python
def _on_command_error_internal(self, timestamp: str, error: str) -> None:
    self.logger.warning(f"[{timestamp}] Command error: {error}")
    # Emit to log viewer
    self.command_error.emit(timestamp, error)
    # ← No fallback triggered here!

def _on_persistent_terminal_operation_finished(
    self, operation: str, success: bool, message: str
) -> None:
    if success:
        self._cleanup_stale_fallback_entries()
        return
    
    # Operation failed - attempt fallback
    with self._fallback_lock:
        if not self._pending_fallback:
            return  # No pending fallback
        
        # Get oldest and retry in new terminal
        oldest_id = min(self._pending_fallback.keys(), ...)
        result = self._pending_fallback.pop(oldest_id, None)
    
    self._launch_in_new_terminal(full_command, app_name, ...)
```

**Issue:** Two different handlers, inconsistent behavior:
- `_on_command_error_internal()` - just logs, no fallback
- `_on_persistent_terminal_operation_finished()` - might fallback

Should probably check operation type and consolidate.

---

## 5. RESOURCE CLEANUP ANALYSIS

### 5.1 File Descriptor Leaks

**File:** `persistent_terminal_manager.py` (Lines 701-731, 1020-1024)

**Good Pattern (Dual Path Cleanup):**
```python
fd = None  # Track FD for cleanup
try:
    fd = os.open(self.fifo_path, os.O_WRONLY | os.O_NONBLOCK)
    
    with os.fdopen(fd, "wb", buffering=0) as fifo:
        fd = None  # fdopen took ownership
        fifo.write(command.encode("utf-8"))

except OSError as e:
    # ✅ Clean up fd if fdopen never took ownership
    if fd is not None:
        try:
            os.close(fd)
        except OSError:
            pass
```

**Duplicate Pattern (Less Safe):**
```python
# Lines 954-1024: send_command() method
for attempt in range(max_retries):
    try:
        fifo_fd = os.open(...)
        with os.fdopen(fifo_fd, "wb", buffering=0) as fifo:
            fifo_fd = None
            fifo.write(...)
    except OSError as e:
        # ...
    finally:
        if fifo_fd is not None:
            with contextlib.suppress(OSError):
                os.close(fifo_fd)
```

**Improvements:**
- Both patterns are correct
- Could benefit from single helper function to reduce duplication
- Exception in fdopen() itself would leak (rare but possible)

### 5.2 Worker Thread Cleanup

**File:** `persistent_terminal_manager.py` (Lines 1515-1553)

**Process:**
1. Set `_shutdown_requested = True` → block new workers
2. Snapshot `_active_workers` list
3. Clear list immediately
4. For each worker:
   - Disconnect signals
   - Request interruption
   - Quit event loop
   - Wait 10 seconds
   - If timeout: abandon (don't terminate)
   - Call deleteLater()

**Issues:**
1. **deleteLater() Called Even If wait() Times Out**
   - Object scheduled for deletion but thread still running
   - Thread might try to emit signals to deleted object
   - Qt handles this with "no-op" but fragile

2. **No Wait for deleteLater() Completion**
   - Thread deleted, but worker object might not be
   - Background operations might continue

3. **Signal Disconnection Before Stop Request**
   - Lines 1526-1533: Disconnect signals first
   - Lines 1536-1537: Then request interruption
   - **Gap:** Worker might check interruption flag BETWEEN disconnect and request, continuing with signal emission

### 5.3 FIFO Cleanup on Error

**File:** `persistent_terminal_manager.py` (Lines 1449-1458)

```python
try:
    os.mkfifo(temp_fifo, 0o600)
    os.rename(temp_fifo, self.fifo_path)
except OSError as e:
    self.logger.error(f"Failed to create FIFO atomically: {e}")
    # ✅ CLEANUP: Ensure temp file removed on error
    if Path(temp_fifo).exists():
        try:
            Path(temp_fifo).unlink()
        except OSError as cleanup_error:
            self.logger.warning(f"Failed to clean up temp FIFO: {cleanup_error}")
    return False
```

**Good Pattern:** Explicit cleanup of temp FIFO on error
- Handles EEXIST from previous failed attempts
- Prevents mkfifo failures on retry

---

## 6. COMMAND-LINE INJECTION & PATH VALIDATION

### 6.1 Command Path Escaping

**File:** `command_launcher.py` (Lines 765-778, 830-843)

```python
try:
    safe_workspace_path = CommandBuilder.validate_path(
        self.current_shot.workspace_path
    )
    ws_command = f"ws {safe_workspace_path} && {env_fixes}{command}"
except ValueError as e:
    self._emit_error(f"Invalid workspace path: {e!s}")
    return False
```

**Pattern:** CommandBuilder.validate_path() used before shell execution
- Prevents basic injection from unescaped paths
- But reliance on external validation class

**Risk:** What if `env_fixes` contains shell metacharacters?
```python
# From nuke_handler - could contain special chars?
env_fixes = self.nuke_handler.get_environment_fixes()  # ← NO VALIDATION
ws_command = f"ws {safe_workspace_path} && {env_fixes}{command}"
```

### 6.2 Error Context in Command Execution

**File:** `command_launcher.py` (Lines 596-601)

```python
except Exception as e:
    # Fallback for unexpected errors
    self.env_manager.reset_cache()
    self._emit_error(f"Failed to launch {app_name}{error_context}: {e!s}")
    return False
```

**Good:** Caches reset on failure (terminal might be uninstalled)

---

## 7. TIMEOUT SCENARIOS

### 7.1 Health Check Timeout Under Load

**Config:** `config.py` (Lines 132-134)

```python
HEARTBEAT_TIMEOUT: float = 60.0  # seconds
HEARTBEAT_CHECK_INTERVAL: float = 30.0
MAX_TERMINAL_RESTART_ATTEMPTS: int = 3
```

**Scenario:** System under heavy load
- Heartbeat check timeout: 3 seconds (line 456, `_HEARTBEAT_SEND_TIMEOUT_SECONDS = 3.0`)
- Dispatcher busy executing command
- Heartbeat write blocks for 3+ seconds
- Holding `_write_lock` → other commands queued
- Health check from next command blocks entire chain

**No Exponential Backoff:** Health checks use fixed 2s timeout regardless of retry count

### 7.2 ProcessVerifier Timeout

**File:** `launch/process_verifier.py` (Lines 49-50)

```python
VERIFICATION_TIMEOUT_SEC: float = 30.0  # Increased from 5.0
POLL_INTERVAL_SEC: float = 0.2
```

**History:** Increased from 5s to 30s to prevent double-execution
- GUI apps (Nuke, Maya) take 8-15s to start
- 5s timeout would trigger fallback, spawning duplicate
- **Fixed but tight:** 30s might be insufficient for slow systems

**Edge Case:** Nuke takes 29.9s to write PID
- ProcessVerifier polls every 0.2s
- Last poll at 29.8s → not ready
- Next poll at 30.0s → timeout
- PID appears at 30.2s but too late
- Fallback launches duplicate

---

## 8. CONCURRENCY HAZARDS

### 8.1 Lock Ordering

**File:** `persistent_terminal_manager.py` (Lines 274-289)

**Lock Hierarchy (Strict):**
1. `_restart_lock` (outer) - Serializes restart operations
2. `_write_lock` (inner) - Serializes FIFO writes and health checks
3. `_state_lock` (leaf) - Protects shared state snapshots
4. `_workers_lock` (leaf) - Protects worker list

**Safe Pattern:**
```
_restart_lock
  ├─ _write_lock
  │   ├─ _state_lock
  │   └─ _workers_lock
```

**Danger Zone:** Never acquire in reverse order
- Current code follows hierarchy
- New code must maintain order

### 8.2 Heartbeat Race in Health Check

**File:** `persistent_terminal_manager.py` (Lines 656-668)

```python
# Check heartbeat age
if last_heartbeat_time > 0:
    age = time.time() - last_heartbeat_time
    if age > self._heartbeat_timeout:
        # Try sending a ping to verify
        if not self._send_heartbeat_ping():  # ← BLOCKING 3s
            return False
```

**Issue:** Holding no lock while checking `last_heartbeat_time`
- Another thread might update timestamp between check and sleep
- Repeated pings if multiple threads enter health check

**Better:** Snapshot heartbeat time under lock
```python
with self._state_lock:
    last_heartbeat_time = self._last_heartbeat_time

if last_heartbeat_time > 0:
    age = time.time() - last_heartbeat_time
    # ...
```

---

## 9. IDENTIFIED GAPS & RECOMMENDATIONS

### Critical (Security/Stability)

| Issue | File | Line | Severity | Fix |
|-------|------|------|----------|-----|
| Parent dir fsync not guaranteed cleanup | persistent_terminal_manager.py | 1434-1438 | HIGH | Wrap in try/finally |
| fsync fd leak if FIFO doesn't exist | persistent_terminal_manager.py | 1434 | MED | Check parent existence first |
| Worker abandonment on timeout (by design) | persistent_terminal_manager.py | 1543-1548 | MED | Document subprocess cleanup |
| Signal connections leak in ProcessExecutor | launch/process_executor.py | ~82-87 | MED | Add cleanup() method |
| Signal disconnect before interruption request | persistent_terminal_manager.py | 1526-1536 | MED | Reverse order |
| Fallback cleanup timer signal not disconnected | command_launcher.py | 1438-1441 | MED | Disconnect timeout signal |

### Important (Reliability)

| Issue | File | Line | Severity | Recommendation |
|-------|------|------|----------|---|
| Heartbeat timeout blocks write lock | persistent_terminal_manager.py | 667 | HIGH | Move heartbeat check out of health check, use async |
| Error codes as strings (no pattern matching) | persistent_terminal_manager.py | 183 | MED | Use Enum for error types |
| Double command execution edge case | launch/process_verifier.py | 49 | MED | Document timeout tuning, add telemetry |
| Concurrent cooldown recovery | persistent_terminal_manager.py | 872-896 | LOW | Add generation counter for cooldown |
| Fallback retry only first command | command_launcher.py | 376-378 | LOW | Retry all pending commands |

### Minor (Code Quality)

| Issue | File | Line | Suggestion |
|-------|------|------|---|
| Duplicate FIFO write error handling | persistent_terminal_manager.py | 701-731 vs 953-1027 | Extract helper method |
| No unified error handler in CommandLauncher | command_launcher.py | 337-346 vs 348-395 | Consolidate handlers |
| ProcessVerifier uses regex for app detection | launch/process_verifier.py | 138 | Could use config.GUI_APPS set |

---

## 10. TEST COVERAGE GAPS

**Files:** `tests/unit/test_persistent_terminal_manager.py`, `tests/unit/test_command_launcher.py`

**What's Tested:**
- ✅ FIFO creation and validation
- ✅ Terminal launch fallback (emulator types)
- ✅ Signal emission
- ✅ Async worker lifecycle

**What's NOT Tested:**
- ❌ Stale FIFO from crash scenario
- ❌ Concurrent restart attempts (race conditions)
- ❌ Worker abandonment timeout (10s wait)
- ❌ Fallback cooldown recovery
- ❌ Signal cleanup after disconnect
- ❌ Double command execution edge case
- ❌ High concurrency (10+ simultaneous commands)
- ❌ ProcessVerifier timeout edge cases
- ❌ Heartbeat timeout under load

---

## CONCLUSION

The launcher/terminal system demonstrates **solid engineering** with comprehensive error handling for common failure modes. However, subtle **concurrency hazards** and **resource cleanup gaps** exist that could manifest under high load or edge conditions:

1. **Immediate Actions:**
   - Add try/finally for fsync fd cleanup
   - Disconnect timer signals in CommandLauncher cleanup
   - Document worker abandonment behavior

2. **Next Sprint:**
   - Async heartbeat check (move out of health check)
   - Unified error codes (Enum instead of strings)
   - Signal cleanup verification tests

3. **Future Improvements:**
   - Lock-free state management for hot paths
   - Metrics/observability for error rates
   - Comprehensive edge case test suite
