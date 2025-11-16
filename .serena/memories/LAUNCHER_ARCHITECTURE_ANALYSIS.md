# Launcher/Terminal Architecture - Comprehensive Analysis

**Analysis Date**: 2025-11-14  
**Scope**: PersistentTerminalManager, CommandLauncher, Launch System, LauncherProcessManager  
**Depth**: VERY THOROUGH - Critical Production Code

---

## EXECUTIVE SUMMARY

The launcher/terminal architecture is a **complex, multi-layered system** managing command execution in VFX pipelines. It exhibits:

- **Strengths**: Robust error handling, recovery mechanisms, thread-safe design patterns
- **Critical Issues**: Race conditions, deadlock vulnerabilities, thread lifecycle issues
- **Fragility Areas**: FIFO communication, worker lifecycle, state synchronization
- **Estimated Risk Level**: HIGH (Production-critical with edge case failures)

---

## ARCHITECTURE OVERVIEW

### Component Hierarchy

```
┌─────────────────────────────────────────────────────────────┐
│ User Application (Qt GUI - Main Thread)                     │
│  - LauncherController                                       │
│  - CommandLauncher                                          │
└────────────┬────────────────────────────────────────────────┘
             │
┌────────────┴────────────────────────────────────────────────┐
│ Launcher Execution Layer (Multiple Threads)                 │
│ ┌──────────────────────────────────────────────────────────┐│
│ │ PersistentTerminalManager (Singleton)                   ││
│ │  - FIFO-based command dispatch                          ││
│ │  - Terminal process management                          ││
│ │  - Health checking & recovery                           ││
│ │  - Worker thread pool coordination                      ││
│ └──────────────────────────────────────────────────────────┘│
│ ┌──────────────────────────────────────────────────────────┐│
│ │ CommandLauncher (Per-Launch Instance)                   ││
│ │  - Command building & validation                        ││
│ │  - Nuke/3DE/Maya-specific logic                         ││
│ │  - Signal aggregation from terminal                     ││
│ └──────────────────────────────────────────────────────────┘│
│ ┌──────────────────────────────────────────────────────────┐│
│ │ ProcessExecutor (Launch Strategy)                       ││
│ │  - Terminal vs. new window selection                    ││
│ │  - Process verification scheduling                      ││
│ └──────────────────────────────────────────────────────────┘│
└────────────┬────────────────────────────────────────────────┘
             │
┌────────────┴────────────────────────────────────────────────┐
│ System Integration Layer                                     │
│ ┌──────────────────────────────────────────────────────────┐│
│ │ LauncherProcessManager (QObject)                        ││
│ │  - Process/worker tracking                              ││
│ │  - Cleanup coordination                                 ││
│ │  - Qt signal emission                                   ││
│ └──────────────────────────────────────────────────────────┘│
│ ┌──────────────────────────────────────────────────────────┐│
│ │ TerminalOperationWorker (QThread)                       ││
│ │  - Async command execution                              ││
│ │  - Health checks in background                          ││
│ │  - Process verification                                 ││
│ └──────────────────────────────────────────────────────────┘│
│ ┌──────────────────────────────────────────────────────────┐│
│ │ ProcessVerifier (Read-only)                             ││
│ │  - PID file monitoring                                  ││
│ │  - Process existence checking                           ││
│ └──────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
             │
┌────────────┴────────────────────────────────────────────────┐
│ OS/Shell Layer                                               │
│ ┌──────────────────────────────────────────────────────────┐│
│ │ FIFO (Named Pipe)                                       ││
│ │  └─ /tmp/shotbot_commands.fifo                          ││
│ ├──────────────────────────────────────────────────────────┤│
│ │ Terminal Dispatcher (background shell)                  ││
│ │  └─ Reads FIFO, executes commands                       ││
│ └──────────────────────────────────────────────────────────┘│
│ ┌──────────────────────────────────────────────────────────┐│
│ │ Workspace Shells (terminal_dispatcher.sh)               ││
│ │  └─ Individual command execution environment            ││
│ └──────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

### Data Flow: Command Execution

```
1. User Click on "Launch Nuke" (Main Thread)
   │
   ├─→ LauncherController.launch_app()
   │   ├─→ Build command (nuke -c script.py)
   │   ├─→ Add workspace setup (ws /path/to/workspace &&)
   │   └─→ CommandLauncher.launch_app()
   │
   ├─→ CommandLauncher.launch_app() (Main Thread)
   │   ├─→ Validate shot & workspace
   │   ├─→ Construct full command string
   │   └─→ Call _execute_launch()
   │
   ├─→ ProcessExecutor decides: FIFO or New Terminal
   │   ├─→ IF FIFO available: send_command_async()
   │   └─→ ELSE: execute_in_new_terminal()
   │
   ├─→ PersistentTerminalManager.send_command_async() (Main Thread)
   │   ├─→ Validates dummy_writer_ready flag
   │   ├─→ Emits "command_queued" signal
   │   ├─→ Creates TerminalOperationWorker
   │   ├─→ Moves to QThread
   │   └─→ thread.start() → triggers worker.run()
   │
   ├─→ TerminalOperationWorker.run() (Worker Thread)
   │   ├─→ _run_send_command()
   │   ├─→ _ensure_dispatcher_healthy()
   │   ├─→ _send_command_direct() (writes to FIFO)
   │   ├─→ ProcessVerifier.wait_for_process() (polls PID files)
   │   └─→ Emits "operation_finished" signal
   │
   ├─→ Terminal Dispatcher (background shell)
   │   ├─→ Reads command from FIFO
   │   ├─→ Executes: "ws /path && nuke -c script.py"
   │   ├─→ Writes PID to /tmp/shotbot_pids/nuke.pid
   │   └─→ Backgrounds process with "&"
   │
   └─→ Main Thread receives "operation_finished" signal
       ├─→ CommandLauncher emits "command_executed"
       └─→ UI updates with success/error
```

---

## CRITICAL THREADING MODEL

### Lock Hierarchy (Lock Ordering Critical for Deadlock Prevention)

**LOCK ORDERING (MUST FOLLOW THIS ORDER):**

```
Priority 1 (Outermost):  _restart_lock  (controls terminal restarts)
Priority 2:               _write_lock    (FIFO write serialization)
Priority 3:               _state_lock    (state snapshot protection)
```

**AB-BA Deadlock Risk**: Critical Bug Fix #23 addresses this

- **Scenario A** (send_command → ensure_dispatcher_healthy):
  - Acquires: _write_lock → _restart_lock ❌ WRONG ORDER
  
- **Scenario B** (restart_terminal):
  - Acquires: _restart_lock → _write_lock ✅ CORRECT ORDER

- **Result**: Thread A blocks on _restart_lock while holding _write_lock. Thread B blocks on _write_lock while holding _restart_lock. **PERMANENT DEADLOCK**.

- **Fix**: `send_command()` acquires locks in correct order:
  1. Call `_ensure_dispatcher_healthy()` WITHOUT _write_lock (may acquire _restart_lock internally)
  2. THEN acquire _write_lock for FIFO write

### Thread Types and Responsibilities

| Thread Type | Owner | Lifecycle | Responsibilities |
|-----------|-------|-----------|------------------|
| **Main** | Qt | App lifetime | UI, signal dispatch, command initiation |
| **TerminalOperationWorker** | PersistentTerminalManager | Per-command | Health checks, FIFO sends, PID verification |
| **Dispatcher** | terminal_dispatcher.sh | Terminal lifetime | FIFO reading, command execution, backgrounding |
| **LauncherWorker** | LauncherProcessManager | Per-launch | Subprocess execution, output capture |
| **QThread** (worker container) | Qt | Worker lifetime | Event loop, signal delivery to worker |

### Signal-Slot Threading Model

**Connection Type Used**: `Qt.ConnectionType.QueuedConnection` (thread-safe)

- **Signal Source**: Worker thread (TerminalOperationWorker, LauncherWorker)
- **Signal Target**: Main thread (PersistentTerminalManager, CommandLauncher)
- **Mechanism**: Qt queues signal emission across thread boundary
- **Safety**: Slots execute in target thread (no mutex needed)

---

## IDENTIFIED ISSUES & RISKS

### TIER 1: CRITICAL RACE CONDITIONS

#### Issue 1.1: Dummy Writer Ready Race (BUG FIX #19)

**Problem**: 
```
Timeline:
T1: Dispatcher starts → FIFO exists but has no readers
T2: Command sent immediately → Opens FIFO writer (success!) but dispatcher not ready
T3: Command writer closes FD → Sends EOF to dispatcher (closes FIFO)
T4: Dummy writer tries to open FIFO → Fails with "no readers" (ENXIO)
Result: Dispatcher has no reader, next command hangs

Race Window: ~100-500ms (FIFO exists but dispatcher not listening)
```

**Current Fix**: `_dummy_writer_ready` flag
- Set to `False` during restart
- Set to `True` ONLY after dummy writer successfully opens
- Checked in `send_command()` before allowing dispatch

**Remaining Risk**: 
- Flag check not atomic with actual FIFO write (separate lock sections)
- Small window where flag is True but dummy writer closing
- **Mitigation**: Retry logic + health checks (not preventive)

---

#### Issue 1.2: FIFO Unlink Race (BUG FIX #2)

**Problem**:
```
Timeline:
T1: restart_terminal() calls: Path(fifo_path).unlink()
T2: send_command() checks: Path(fifo_path).exists() → True (still exists)
T3: restart_terminal() continues with mkfifo()
T4: send_command() opens FIFO successfully but it's the OLD one
T5: mkfifo() creates NEW FIFO (old deleted)
Result: Commands going to wrong FIFO, dispatcher hanging on old one
```

**Current Fix**: `_write_lock` held during FIFO manipulation in restart_terminal()
- Prevents TOCTOU (Time-Of-Check-Time-Of-Use) race
- `send_command()` must also hold _write_lock during open()

**Remaining Risk**:
- Lock held across multiple operations (unlink → mkfifo → rename)
- High contention if FIFO write blocked (dispatcher slow)
- **Improvement Needed**: Shorter critical section

---

#### Issue 1.3: Stale Temp FIFO Accumulation (BUG FIX #3)

**Problem**:
```
Timeline:
T1: restart_terminal() calls: os.mkfifo(temp_fifo)
T2: Restart fails between mkfifo() and rename()
T3: temp_fifo still exists (/tmp/shotbot_commands.fifo.PID.tmp)
T4: Next restart() tries: os.mkfifo(temp_fifo) → EEXIST error
T5: mkfifo fails, FIFO not created, dispatcher never starts
Result: Terminal permanently broken until manual cleanup
```

**Current Fix**: Clean up stale temp FIFO before mkfifo()
```python
if Path(temp_fifo).exists():
    Path(temp_fifo).unlink()
```

**Remaining Risk**:
- What if unlink() fails due to permissions?
- What if cleanup stale but new mkfifo happens concurrently?
- **Gap**: No retry logic if unlink fails

---

### TIER 2: WORKER LIFECYCLE ISSUES

#### Issue 2.1: Worker Abandonment on Cleanup Timeout

**Problem**:
```python
# In cleanup():
if not thread.wait(10000):  # 10 second timeout
    self.logger.error("Worker did not stop... Abandoning worker")
    # Thread continues running, may still hold locks
```

**Risks**:
1. **Lock Holding**: Abandoned worker may hold `_state_lock`, `_write_lock`
2. **Deadlock Potential**: Subsequent `send_command()` blocks on lock held by zombie worker
3. **Resource Leak**: Worker threads accumulate if cleanup happens frequently
4. **Qt Child Cleanup**: Worker.deleteLater() may not actually delete (still referenced)

**Example Scenario**:
```
1. User closes app
2. cleanup() called
3. Worker stuck in _ensure_dispatcher_healthy() health check
4. wait(10s) times out
5. Thread abandoned while holding _state_lock
6. New command tries send_command() → blocks on _state_lock forever
7. Application hangs on shutdown
```

**Mitigation Status**: INCOMPLETE
- Comment says "may complete later" but no mechanism ensures it
- No way to recover lock if worker truly stuck
- No maximum concurrent abandoned workers tracking

---

#### Issue 2.2: Race Between send_command_async() and cleanup()

**Problem**:
```
Timeline:
T1 (Main): cleanup() sets _shutdown_requested = True
T2 (Main): cleanup() clears _active_workers
T3 (Worker): send_command_async() creates new worker
T4 (Main): worker appended to _active_workers (but cleanup already cleared!)
Result: Worker never stopped during cleanup, resource leak
```

**Current Protection**:
```python
with self._workers_lock:
    if self._shutdown_requested:
        self.logger.warning("Shutdown in progress, rejecting command")
        return
```

**Gap**:
- Lock only held during queue check, not during append
- Worker object created BEFORE checking shutdown flag
- Between flag check and append, main thread could call cleanup()

**Likelihood**: Low (requires specific timing) but POSSIBLE

---

#### Issue 2.3: TerminalOperationWorker Parent Parameter Issue

**Problem**: Workers created WITHOUT Qt parent:
```python
worker = TerminalOperationWorker(self, "send_command")
# No parent parameter passed
```

**Expected Pattern** (from CLAUDE.md):
```python
worker = TerminalOperationWorker(..., parent=self)  # self is QThread parent
```

**Impact**:
- Qt C++ ownership chain broken
- Worker not automatically deleted when thread finishes
- Memory leak if signals not properly disconnected
- Potential crashes during Qt teardown

**Observation**: Code doesn't pass parent to TerminalOperationWorker.__init__()
- Check: Does TerminalOperationWorker accept parent parameter?
- If not: This violates Qt widget guidelines

---

### TIER 3: STATE SYNCHRONIZATION ISSUES

#### Issue 3.1: Dispatcher PID Staleness

**Problem**: `dispatcher_pid` may be stale
```python
with self._state_lock:
    dispatcher_pid = self.dispatcher_pid  # Snapshot under lock ✓
    
# Later, OUTSIDE lock:
if self._is_dispatcher_alive():  # May use stale dispatcher_pid
    # Dispatcher crashed, new one started
    # We're checking the OLD dispatcher PID → Always says "healthy"
```

**Scenario**:
1. Dispatcher (PID 12345) crashes
2. Terminal restarts, new Dispatcher (PID 12346) starts
3. `dispatcher_pid` still = 12345
4. Health check: "Is PID 12345 alive?" → Maybe yes (new different process)
5. Send command to FIFO → Dispatched to wrong process

**Mitigation Status**: PARTIAL
- Periodic re-discovery of dispatcher PID
- Health check re-finds PID if current one dead
- But gap between discovery and use

---

#### Issue 3.2: Restart Attempt Counter Race

**Problem**:
```
Timeline:
T1 (Worker A): if restart_attempts >= max_attempts
T2 (Worker B): if restart_attempts >= max_attempts
T3 (Worker A): _restart_attempts += 1  (now 4/3)
T4 (Worker B): _restart_attempts += 1  (now 5/3)
Result: Exceeded max_attempts counter, fallback mode entered
```

**Current Fix**: `_restart_lock` serializes increments
```python
with self._restart_lock:
    if self._restart_attempts >= self._max_restart_attempts:
        return False  # ✓ Only one thread increments
```

**Status**: FIXED (lock acquired before check & increment)

---

#### Issue 3.3: Fallback Mode Auto-Recovery Timing

**Problem**: Fallback cooldown may not work as expected
```python
if elapsed >= cooldown_seconds:  # 300s (5 minutes)
    if self._ensure_dispatcher_healthy():
        self._fallback_mode = False  # Recovery succeeded
    else:
        self._fallback_entered_at = time.time()  # Re-enter cooldown
```

**Risks**:
1. **Spurious Timeout**: Health check succeeds briefly, then dispatcher crashes again
   - Fallback disabled, send_command() fails with no recovery
   - User thinks app is broken
   
2. **Cooldown Reset**: Every failed recovery resets 5-minute timer
   - If recovery attempted every 30s, cooldown becomes infinite
   - User may be stuck in fallback for hours

3. **No User Notification**: User doesn't know app is in fallback mode
   - Commands silently fail (error signal emitted but UI might not show)

---

### TIER 4: COMMAND & FIFO RELIABILITY

#### Issue 4.1: Non-ASCII Command Handling

**Problem**:
```python
try:
    _ = command.encode("ascii")  # Just checks, doesn't convert
except UnicodeEncodeError:
    self.logger.warning(f"Command contains non-ASCII: {command!r}")
    # Continues anyway! Writes UTF-8 to FIFO
```

**Issue**: 
- Warning logged but command proceeds
- UTF-8 bytes written to FIFO
- Dispatcher shell expects ASCII/UTF-8 encoding
- Risk: FIFO receives malformed bytes

**Gap**: No validation that FIFO actually accepts UTF-8 bytes
- Dispatcher might expect ASCII only
- Script paths with non-ASCII characters could break

---

#### Issue 4.2: FIFO Buffer Overflow (EAGAIN)

**Problem**:
```python
except OSError as e:
    if e.errno == errno.EAGAIN:  # Buffer full
        backoff = 0.1 * (2 ** attempt)  # 0.1s, 0.2s, 0.4s
        time.sleep(backoff)
        continue
```

**Issues**:
1. **Blocking on I/O**: User clicks launch, main thread blocks on FIFO write
   - UI freezes for up to 0.7 seconds (sum of backoffs)
   - Should use async I/O or non-blocking writes

2. **Exponential Backoff**: Why 0.1s → 0.2s → 0.4s?
   - FIFO typically empties in milliseconds (dispatcher reads continuously)
   - Backoff delays longer than actual queue time
   - Better: Fixed 10ms waits

3. **Max 3 Attempts**: After 0.7s total delay, gives up
   - What if dispatcher just temporarily slow?
   - No retry loop available (send_command fails, user must retry)

**Observation**: `send_command_async()` used instead of blocking calls
- This partially mitigates main thread blocking
- But underlying FIFO write still synchronous

---

#### Issue 4.3: FIFO Reader Detection (ENXIO)

**Problem**:
```python
except OSError as e:
    if e.errno == errno.ENXIO:  # No reader
        self.logger.error("No reader available... dispatcher may have crashed")
        with self._state_lock:
            self.dispatcher_pid = None  # Reset for re-detection
```

**Issues**:
1. **Delayed Detection**: ENXIO only detected when trying to WRITE
   - Gap between dispatcher crash and error detection
   - May send 1-2 commands to stale FIFO before detecting

2. **Silent Failures**: If FIFO exists but reader gone:
   - `open(..., O_WRONLY | O_NONBLOCK)` succeeds
   - `write()` succeeds (kernel buffers data)
   - But no reader, so data lost
   - Command disappeared, user thinks app launched

3. **No Reader Detection**: Difference between:
   - Dispatcher crashed (FIFO exists, no reader)
   - FIFO deleted (FIFO doesn't exist)
   - Both treated as "health check failure"

---

### TIER 5: EDGE CASES & UNCLEAR BEHAVIOR

#### Issue 5.1: What happens when Terminal Window Closes?

**Question**: User closes terminal window (with dispatcher inside)

1. Terminal process exits (sends SIGTERM to dispatcher)
2. Dispatcher exits (releases FIFO reader)
3. `send_command()` gets ENXIO (no reader)
4. Fallback mode entered
5. User sees error: "terminal in fallback mode"
6. In 5 minutes, auto-recovery attempted

**Gap**: 
- No signal for "terminal closed by user"
- UI should show "Terminal Closed" instead of "Fallback Mode"
- User might try to re-open terminal manually

---

#### Issue 5.2: Multiple PersistentTerminalManager Instances

**Problem**: Code has test tracking:
```python
_test_instances = []  # Track all instances for cleanup
_test_instances_lock = threading.Lock()
```

**Risk**: What if two instances created in production?
- Two independent FIFO paths?
- Two independent dispatcher processes?
- Race condition in FIFO creation?

**Current Pattern**: 
```python
@classmethod
def cleanup_all_instances(cls):
    with cls._test_instances_lock:
        for instance in cls._test_instances:
            instance.cleanup()
```

**Gap**: 
- Only cleans up tracked instances (test instances)
- Production assumes singleton pattern
- No enforcement (no singleton class pattern)

---

#### Issue 5.3: Terminal Dispatcher Script Reliability

**Problem**: `terminal_dispatcher.sh` is external process

**Assumptions Made**:
1. Dispatcher correctly reads FIFO line-by-line
2. Dispatcher backgrounds GUI apps with `&`
3. Dispatcher writes PID files to /tmp/shotbot_pids/
4. Dispatcher handles SIGTERM gracefully
5. Dispatcher doesn't hang on malformed input

**Verification Gap**:
- No automated tests for dispatcher script behavior
- No fallback if dispatcher has bugs
- If dispatcher crashes, fallback mode activated (5 min cooldown)

---

### TIER 6: ERROR HANDLING PATTERNS

#### Issue 6.1: Silent Command Failures (BUG FIX #22)

**Pattern Introduced**:
```python
if not self._dummy_writer_ready:
    error_msg = "Dummy writer not ready yet"
    timestamp = datetime.now().strftime("%H:%M:%S")
    self.command_error.emit(timestamp, error_msg)  # Emit error signal
    return False
```

**Good**: Signal emitted for UI feedback

**Issue**: 
- What if UI doesn't listen to `command_error` signal?
- Signal emitted but caller never checked return value?
- Silent failure: "command sent successfully" returns False

**Observation**: Multiple error emission patterns:
1. Some paths emit `command_error` signal
2. Some paths return False (caller must check)
3. Some paths log warning only

**Inconsistency**: No unified error handling strategy

---

#### Issue 6.2: Fallback Cleanup Stale Entries

**Code**:
```python
def _cleanup_stale_fallback_entries(self) -> None:
    with self._fallback_lock:
        # Clean up entries older than 5 seconds
        cutoff = time.time() - 5.0
        self._pending_fallback = {
            k: v for k, v in self._pending_fallback.items()
            if v > cutoff
        }
```

**Gap**:
- Cutoff value (5s) hardcoded, not configurable
- Not called automatically, requires timer setup
- If cleanup timer not triggered, dict grows unbounded
- Risk: Memory leak if many failed launches

---

## SYNCHRONIZATION PATTERNS

### Positive Patterns

✅ **Lock Ordering Enforcement**: Documented lock hierarchy prevents deadlock

✅ **Thread-Safe Snapshots**: Locks held only during state read:
```python
with self._state_lock:
    snapshot = {
        'terminal_pid': self.terminal_pid,
        'dispatcher_pid': self.dispatcher_pid,
    }
# Use snapshot outside lock ✓
```

✅ **Signal-Based Communication**: Qt signals for cross-thread updates (thread-safe)

✅ **Atomic FIFO Replacement**: Uses temporary file + rename for atomic swap

---

### Anti-Patterns & Vulnerabilities

❌ **Snapshot Staleness**: 
```python
# Under lock: snapshot taken
# Outside lock: snapshot used (may be stale)
# Risk: State changed between snapshot and use
```

❌ **Deadlock-Prone Nested Locks**:
```python
with self._state_lock:
    if self._restart_flag:
        with self._restart_lock:  # Nested lock (OK if ordered correctly)
            self._perform_restart()
```

❌ **Lock Held Across Long Operations**:
```python
with self._write_lock:
    # Unlink FIFO (OS call, can block)
    # mkfifo (OS call, can block)
    # Rename (OS call, can block)
    # Total: potentially 100ms+ of lock holding
```

---

## PROCESS VERIFICATION STRATEGY

### How It Works

1. **Command Sent**: Worker sends command to FIFO
2. **Dispatcher Receives**: Terminal dispatcher reads FIFO
3. **App Launches**: Dispatcher executes "nuke ..." in background
4. **PID Written**: Dispatcher writes PID to `/tmp/shotbot_pids/nuke.pid`
5. **Verification Waits**: Worker polls for PID file (30s timeout)
6. **Verification Checks**: psutil verifies process exists

### Reliability Issues

**Issue P1: PID File Timing**
- GUI apps (Nuke, Maya) take 8-15 seconds to write PID files
- ProcessVerifier timeout set to 30s (VERIFICATION_TIMEOUT_SEC)
- Risk: If timeout < startup time, false negative

**Issue P2: Multiple Instances**
- If app launched twice, multiple PID files may exist
- ProcessVerifier finds ANY matching file (not latest)
- Verification succeeds for wrong instance

**Issue P3: Stale PID Files**
- Previous launch crashed, PID file still exists
- New launch writes new PID
- Verifier might find old PID file (different app instance)
- `enqueue_time` filter attempts to prevent this

**Issue P4: PID File Directory Permissions**
- `/tmp/shotbot_pids/` created automatically
- Risk: Permissions might be too restrictive (dispatcher can't write)
- Verification fails even though app launched

---

## PROCESS POOL MANAGER ANALYSIS

### Architecture

- **Type**: Singleton with periodic cleanup
- **Tracking**: Two dictionaries
  - `_active_processes`: Subprocess.Popen objects
  - `_active_workers`: LauncherWorker threads
- **Cleanup**: Timer-based (every 5 seconds)
- **Locking**: QMutex (Qt-safe, recursive)

### Issues

**Issue PM1: Worker Cleanup Race**
```python
def _on_worker_finished(self, worker_key: str, ...):
    worker = None
    with QMutexLocker(self._process_lock):
        if worker_key in self._active_workers:
            worker = self._active_workers[worker_key]
            del self._active_workers[worker_key]  # Remove FIRST
    
    # Disconnect signals OUTSIDE lock
    _ = worker.command_started.disconnect()  # ← worker may be deleted by Qt
```

**Risk**: Between del() and disconnect(), Qt may delete worker
- Signal disconnect() then crashes (worker already deleted)

**Fix**: Already correct (store reference, delete from dict, disconnect outside lock)

**Issue PM2: Timer-Based Cleanup Delay**

- Cleanup runs every 5 seconds
- Worker finish signals received immediately
- But tracking dict not cleaned until next timer fire
- Risk: Accumulation of finished workers in dict

**Improvement**: Should clean up immediately in `_on_worker_finished()` callback

---

## COMMAND LAUNCHER INTEGRATION

### Flow Analysis

1. **launch_app()** called on main thread
2. Validates shot, workspace, app name
3. Builds command string (workspace + rez + app + args)
4. Calls `_execute_launch(command, app_name)`

### Nuke-Specific Handling

**Issue N1: Script Generation**
- NukeLaunchHandler generates Python script
- Script path embedded in command
- If path contains spaces: Command breaks
- Fix: CommandBuilder.validate_path() should quote paths

**Issue N2: Raw Plate Discovery**
- If `include_raw_plate=True`, searches for plate files
- Discovery can be slow (filesystem scan)
- Blocks main thread (should be async)

---

## FALLBACK MODE MECHANICS

### When Fallback Activated

1. Max restart attempts exceeded (3 attempts)
2. Health check keeps failing
3. _fallback_mode = True
4. _fallback_entered_at = current_time

### Fallback Behavior

- All new commands immediately rejected
- Error: "Terminal in fallback mode"
- User cannot launch apps
- After 5 minutes (300s), auto-recovery attempted

### Issues with Fallback

**Issue F1: User Can't Recover**
- 5-minute wait with no way to manually recover
- Should provide "Retry Now" button in UI
- Or shorter cooldown (30s instead of 300s)

**Issue F2: No User Notification**
- Fallback mode entered silently
- Error signal emitted but UI might not show
- User thinks app is broken

**Issue F3: Cooldown Reset Bug**
```python
if self._ensure_dispatcher_healthy():
    self._fallback_mode = False  # Recovery succeeded
else:
    self._fallback_entered_at = time.time()  # Cooldown reset
```

- If recovery attempted but health check fails, cooldown resets
- If recovery attempted frequently (every 30s), cooldown becomes effectively infinite

---

## CRITICAL BUG FIXES APPLIED

| # | Issue | Fix | Status |
|---|-------|-----|--------|
| 1 | Zombie process accumulation on SIGKILL | Call process.wait() after kill() | ✅ Applied |
| 2 | FIFO unlink race condition | Hold _write_lock during unlink/mkfifo | ✅ Applied |
| 3 | Stale temp FIFO accumulation | Clean up temp files before mkfifo | ✅ Applied |
| 19 | Dummy writer ready race | Check flag before write, set atomically | ✅ Applied |
| 20 | Signal cleanup memory leak | Track connections, disconnect all | ✅ Applied |
| 22 | Silent command failures | Emit error signal for invalid state | ✅ Applied |
| 23 | AB-BA deadlock in send_command | Acquire locks in correct order | ✅ Applied |

**All critical fixes appear to be applied correctly.**

---

## ARCHITECTURAL PATTERNS

### Pattern 1: Health Check & Recovery

```
send_command() or async worker:
  1. Check health
  2. If unhealthy:
    a. Acquire restart lock
    b. Try up to 3 restarts
    c. If all fail: Enter fallback mode
  3. Send command
```

**Evaluation**: SOLID, allows graceful degradation

### Pattern 2: Dummy Writer FIFO Protection

```
Initialization:
  1. Create FIFO
  2. Open dummy writer (read mode) to keep FIFO reader open
  3. When command sent, dispatcher receives and reads
  4. Even if command writer closes, FIFO has dummy reader
  5. Dummy reader prevents EOF propagation
```

**Evaluation**: CLEVER, prevents race condition at FIFO boundary

### Pattern 3: Process Verification via PID Files

```
1. Command sent to FIFO
2. Dispatcher launches app and writes PID
3. Worker polls for PID file
4. Verifies process exists with psutil
5. Returns success/failure
```

**Evaluation**: ROBUST, but dependent on dispatcher correctness

---

## DATA FLOW: Error Scenarios

### Scenario 1: Dispatcher Crash During Send

```
1. send_command() calls _ensure_dispatcher_healthy() ✓ OK
2. Dispatcher healthy, proceeds with send
3. [DISPATCHER CRASHES]
4. open() to FIFO succeeds (FIFO still exists)
5. write() to FIFO succeeds (kernel buffers)
6. Function returns True (send succeeded)
7. Worker polling: PID file never appears (app never launched)
8. Verification fails after 30s timeout
9. Error emitted, user sees "Verification failed"

PROBLEM: "Send succeeded" but app never launched
IDEAL: Should detect dispatcher death immediately
```

---

### Scenario 2: FIFO Permission Change

```
1. File permissions on FIFO changed by admin
2. PersistentTerminalManager loses write permission
3. next send_command(): open() fails with PermissionError
4. Retry logic doesn't help (permission unchanged)
5. User sees error: "Failed to send command"
6. Fallback mode NOT entered (permission error different from health check)
7. Next attempt also fails

PROBLEM: Permanent failure but no fallback
IDEAL: Detect permission issues, trigger recovery
```

---

### Scenario 3: Queue Too Long

```
1. User clicks 10 apps to launch simultaneously
2. Each send_command_async() creates worker thread
3. Workers queue commands to FIFO
4. Dispatcher reads 1 command at a time
5. By time 10th command arrives, 9 ahead in queue
6. 10th command waits ~9 seconds for dispatcher
7. ProcessVerifier timeout = 30s (succeeds anyway)
8. But user sees massive delay

PROBLEM: No feedback on queue status
IDEAL: Show "X commands queued" in UI
```

---

## INTEGRATION POINTS & FAILURE MODES

### MainWindow → LauncherController → CommandLauncher → PersistentTerminalManager

**Breaking Points**:

1. **If CommandLauncher.cleanup() not called**:
   - Signal connections not disconnected
   - Memory leak in long-running sessions

2. **If PersistentTerminalManager.cleanup() not called**:
   - Workers abandoned (still running)
   - FIFO not removed
   - Subsequent app restarts fail (FIFO exists)

3. **If ProcessExecutor.cleanup() not called**:
   - Terminal signals not disconnected
   - Memory leak

**Risk**: Three separate cleanup() methods, any one missed = problems

---

## RECOMMENDATIONS

### HIGH PRIORITY

1. **Add Deadlock Detection**
   - Monitor thread wait times
   - Warn if any lock held >1 second
   - Log warning: "Possible deadlock: Lock X held for Y seconds"

2. **Implement Graceful Worker Abandonment**
   - If worker doesn't stop in 10s, try requesting interruption
   - Collect stack traces of hung threads for debugging
   - Provide debugging tools to identify lock holders

3. **Reduce FIFO Write Lock Duration**
   - Extract state snapshot before acquiring lock
   - Hold lock only during FIFO unlink → rename
   - Move mkdir() outside lock

4. **Add Terminal State Monitoring**
   - Monitor dispatcher process actively
   - Detect crashes immediately (don't wait for next command)
   - Emit signal: "terminal_crashed" for UI notification

### MEDIUM PRIORITY

5. **Improve Fallback Mode UX**
   - Shorter cooldown (30s instead of 300s)
   - Add "Retry Now" button in UI
   - Show remaining cooldown time in UI

6. **Add Process Verification Robustness**
   - Track spawned PIDs to avoid stale file matches
   - Add app-specific verification (e.g., "nuke" window appears)
   - Cache PID file timestamps for ordering

7. **Implement Worker Lifecycle Timeout Tracking**
   - Log warning if worker busy >30 seconds
   - Identify slow health checks vs. slow FIFO writes
   - Collect metrics for performance optimization

### LOW PRIORITY (Architectural Improvements)

8. **Extract FIFO Layer**
   - Create FIFOWriter class encapsulating all FIFO operations
   - Centralize retry logic, error handling
   - Simplify PersistentTerminalManager

9. **Add Dispatcher Health Monitoring**
   - Periodic heartbeat from dispatcher to manager
   - Detect stuck dispatcher (doesn't respond to heartbeat)
   - Faster recovery than waiting for next command send

10. **Consolidate Cleanup Methods**
    - One unified cleanup() for all managers
    - Called automatically by Qt parent-child cleanup
    - Fewer manual cleanup points = fewer bugs

---

## TESTING GAPS

**Critical Test Coverage Missing**:

1. ✗ Dispatcher crash during async command send
2. ✗ FIFO unlink race with concurrent send_command()
3. ✗ Multiple workers triggering restarts simultaneously
4. ✗ Abandoned worker recovery (if thread never stops)
5. ✗ Permission change on FIFO during operation
6. ✗ Dispatcher stuck (reads FIFO but doesn't execute)
7. ✗ Worker abandonment at various checkpoints
8. ✗ Fallback mode auto-recovery success/failure
9. ✗ Terminal window close by user (dispatcher exits)
10. ✗ Very long command strings (>4KB FIFO buffer)

---

## SUMMARY TABLE

| Category | Rating | Status | Risk |
|----------|--------|--------|------|
| **Architecture** | A- | Well-designed, multi-layered | Low |
| **Threading Model** | B+ | Correct but complex, deadlock-prone | Medium |
| **Error Handling** | B | Good recovery, but incomplete fallback | Medium |
| **FIFO Reliability** | B- | Robust but race-prone at boundaries | Medium-High |
| **Process Verification** | B | Works but timing-dependent | Medium |
| **Code Clarity** | B- | Complex state machine, many edge cases | Medium |
| **Test Coverage** | D | Missing critical concurrency tests | High |
| **Production Readiness** | B- | Mature but requires operator care | Medium-High |

**Overall Assessment**: Production-grade system with critical edge cases. Requires:
- Operator awareness of fallback mode
- Monitoring for deadlock conditions
- Regular cleanup/restart cycles
- Testing of failure scenarios

---

## CONCLUSION

The launcher/terminal architecture demonstrates **sophisticated design** with proper threading, signal handling, and recovery mechanisms. However, the system exhibits **significant complexity** that creates opportunities for subtle race conditions and deadlocks, particularly around:

1. FIFO lifecycle management (creation/deletion races)
2. Worker thread lifecycle (abandonment on timeout)
3. Lock ordering (deadlock prevention requires strict discipline)
4. State synchronization (snapshot staleness)

The applied critical bug fixes (BUGs 1-3, 19-23) address known issues, but the system would benefit from:

- **Reduced lock contention** via shorter critical sections
- **Simplified worker lifecycle** with guaranteed cleanup
- **Monitoring/observability** for detecting hidden failures
- **Test coverage** of concurrency edge cases

For a production VFX pipeline, this system is **usable with caveats**: operators should monitor for fallback mode activation and understand the 5-minute recovery cooldown. Automated remediation (shorter cooldown, retry buttons) would improve user experience significantly.
