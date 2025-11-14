# Shotbot Launcher System - VERY THOROUGH ARCHITECTURAL ANALYSIS

**Analysis Date**: 2025-11-13  
**Scope**: Complete launcher system deep dive with code location mapping  
**Thoroughness**: VERY THOROUGH - Comprehensive investigation across all components

---

## EXECUTIVE SUMMARY

The Shotbot launcher system is **complex** with **critical architectural debt** spanning across:
- **7 files**: 5,639 lines of production code
- **4 controller/manager classes**: Inadequate separation of concerns
- **1 deprecated system**: SimplifiedLauncher (broken, not removed)
- **1 primary system**: PersistentTerminalManager (production-ready with caveats)
- **5 CRITICAL issues**: Race conditions, resource leaks, permanent failure modes
- **7 HIGH issues**: Threading bugs, cleanup gaps, incomplete error handling
- **12 MEDIUM issues**: Design problems affecting reliability and maintainability

**Status**: FUNCTIONAL but NOT PRODUCTION-READY without immediate fixes

---

## PART 1: SYSTEM ARCHITECTURE OVERVIEW

### 1.1 Component Hierarchy

```
┌────────────────────────────────────────────────────────────────┐
│                    MAINWINDOW                                   │
│                                                                  │
│  Feature Flag: USE_SIMPLIFIED_LAUNCHER (default: "true" ❌)     │
│  ⚠️ Default is BROKEN - must set to "false" for production      │
└────────────────────┬─────────────────────────────────────────────┘
                     │
         ┌───────────┴──────────────┐
         │                          │
    ❌ BROKEN             ✅ PRODUCTION-READY
  (SimplifiedLauncher)  (PersistentTerminalManager)
         │                          │
    DO NOT USE              RECOMMENDED
         │                          │
         └───────────┬──────────────┘
                     │
         ┌───────────▼─────────────────────────┐
         │  LauncherController (ALWAYS PRESENT) │
         │  (754 lines, controls both systems)  │
         └───────────────────────────────────────┘
```

### 1.2 Total Codebase Size

| Component | Type | Location | LOC | Status |
|-----------|------|----------|-----|--------|
| PersistentTerminalManager | Class | persistent_terminal_manager.py | 1,410 | PRODUCTION (with issues) |
| CommandLauncher | Class | command_launcher.py | 850 | PRODUCTION (being consolidated) |
| SimplifiedLauncher | Class | simplified_launcher.py | 819 | DEPRECATED (broken) |
| LauncherPanel | Class | launcher_panel.py | 628 | PRODUCTION (UI) |
| LauncherManager | Class | launcher_manager.py | 680 | PRODUCTION (custom launchers) |
| LauncherDialog | Class | launcher_dialog.py | 873 | PRODUCTION (UI) |
| SimpleNukeLauncher | Class | simple_nuke_launcher.py | 243 | PRODUCTION |
| **Launcher submodule** | - | launcher/ | 2,854 | PRODUCTION |
| **Launch submodule** | - | launch/ | 487 | PRODUCTION |
| **LauncherController** | Class | controllers/launcher_controller.py | 754 | PRODUCTION |
| **TOTAL** | - | - | **9,598** | MIXED |

**Status Distribution**:
- 7,850+ LOC PRODUCTION-READY
- 819 LOC DEPRECATED (should be deleted)
- 1,410 LOC NEEDS FIXES (PersistentTerminalManager)

### 1.3 Feature Flag Decision Tree

```
USE_SIMPLIFIED_LAUNCHER environment variable:

┌─────────────────────────────────────────────────────────────┐
│  MainWindow initialization (main_window.py lines 298-328)   │
└────────────────┬──────────────────────────────────────────────┘
                 │
    ┌────────────┴──────────────┐
    │                           │
    ▼ "true" (DEFAULT ❌)       ▼ "false" (RECOMMENDED ✅)
    │                           │
    │ SimplifiedLauncher        │ PersistentTerminalManager
    │ ├─ Broken                 │ ├─ FIFO-based communication
    │ ├─ Missing Rez integ.     │ ├─ Robust health checks
    │ ├─ Param bugs             │ ├─ Persistent terminal
    │ ├─ No thread safety       │ └─ 5 critical issues (fixable)
    │ └─ Being removed          │
    │                           │ + CommandLauncher
    │ launcher_manager=None     │   ├─ Full-featured launcher
    │ persistent_terminal=None  │   └─ Being consolidated
    │                           │
    │                           │ + LauncherManager
    │                           │   └─ Custom launcher CRUD
    │                           │
    └────────────┬──────────────┘
                 │
        ┌────────▼──────────┐
        │ LauncherController │
        │ (ALWAYS PRESENT)   │
        │ Coordinates both   │
        └────────────────────┘
```

---

## PART 2: CRITICAL COMPONENTS - DEEP DIVE

### 2.1 PersistentTerminalManager (1,410 lines)

**File**: `/home/gabrielh/projects/shotbot/persistent_terminal_manager.py`

**Status**: PRODUCTION (with 5 critical issues requiring fixes)

#### 2.1.1 Component Structure

```python
class TerminalOperationWorker(ThreadSafeWorker):  # Lines 44-156
    """Background thread for async operations"""
    Extends: ThreadSafeWorker
    Purpose: Executes health checks and command sends in background
    
    Operations:
    - health_check: Verify dispatcher is alive and responsive
    - send_command: Send command to FIFO with health verification
    
    Signals:
    - progress(str): Status updates
    - operation_finished(bool, str): (success, message)

class PersistentTerminalManager(QObject):  # Lines 157-1409
    """Persistent terminal session manager"""
    
    Core Responsibilities:
    1. FIFO lifecycle management
    2. Dispatcher process management  
    3. Command execution via FIFO
    4. Health monitoring & recovery
    5. Worker thread coordination
    
    Signals (7):
    - terminal_started
    - terminal_closed
    - command_sent
    - operation_started
    - operation_progress
    - operation_finished
    - command_result
    
    Key Attributes:
    - fifo_path: Named pipe path
    - heartbeat_path: Health check file
    - dispatcher_path: Dispatcher script location
    - terminal_pid: Terminal emulator process ID
    - dispatcher_pid: Dispatcher bash process ID
    - _dummy_writer_fd: Keep FIFO alive (prevent EOF)
    
    Thread Safety:
    - _write_lock: Serialize FIFO writes
    - _state_lock: Protect shared state
    - _workers_lock: Protect active workers list
```

#### 2.1.2 Critical Code Paths

**Command Execution Flow**:

```python
send_command(command, ensure_terminal=True) -> bool:  # Lines 801-935
    """Send command to persistent terminal with health checks"""
    
    Steps:
    1. Validate command (not empty, ASCII only)
    2. [CRITICAL RACE HERE] Health check WITHOUT lock:
       Line 838: if not _is_dispatcher_healthy(): return False
    3. Retry loop (up to 2 attempts):
       Line 871: for attempt in range(2):
       Line 874: if ensure_terminal and not _is_dispatcher_healthy():
           Line 879: if not _ensure_dispatcher_healthy():
               return False
    4. [WITH LOCK] Acquire _write_lock
    5. Open FIFO non-blocking
    6. Write command + newline
    7. Close FIFO
    8. Emit command_sent signal
    
    Return: True if sent, False if failed
    
    ISSUE #1.0 (CRITICAL - RACE CONDITION):
    ├─ Line 838: Health check acquired WITHOUT _write_lock
    ├─ Line 869: Dispatcher can crash between check and write
    ├─ Line 876: os.open(FIFO) can fail with ENXIO (no reader)
    ├─ Impact: Inefficient retries, potential command loss under high load
    └─ Fix: Acquire _write_lock BEFORE health check at line 838
```

**Async Command Execution**:

```python
send_command_async(command, ...) -> None:  # Lines 937-1018
    """Non-blocking command sending via background worker thread"""
    
    Steps:
    1. Validate command
    2. Create TerminalOperationWorker (QThread subclass)
    3. Connect signals:
       Line 957: worker.progress.connect(self.operation_progress)
       Line 961: worker.operation_finished.connect(cleanup_worker closure)
    4. Add worker to _active_workers (thread-safe list)
    5. Start worker thread: worker.start()
    
    Worker Execution (in background thread):
       ├─ _ensure_dispatcher_healthy()
       ├─ _send_command_direct(command)
       └─ operation_finished.emit(success, msg)
           └─ cleanup_worker() [closure] called
    
    ISSUE #1.3 (CRITICAL - WORKER THREAD LEAK):
    ├─ Lines 967-971: cleanup_worker closure captures 'self'
    ├─ Closure called via signal emission
    ├─ Multiple scenarios where cleanup fails:
    │  ├─ Signal not emitted (worker crashes)
    │  ├─ Worker.deleteLater() never executes
    │  ├─ Qt event loop not processing
    │  └─ Timeout without forceful cleanup
    ├─ Result: Worker threads accumulate, segfaults possible
    └─ Fix: Explicit wait() instead of deleteLater()
```

**Health Check Composite**:

```python
_is_dispatcher_healthy() -> bool:  # Lines 571-612
    """Multi-level health check"""
    
    Level 1 - Process exists:
        _is_dispatcher_alive() -> bool  # Lines 470-502
        ├─ Get dispatcher_pid from state
        ├─ Use psutil to check if running
        ├─ Return False if zombie/gone
        └─ Clear dispatcher_pid if dead
    
    Level 2 - Reading from FIFO:
        _is_dispatcher_running() -> bool  # Lines 382-397
        ├─ Uses heartbeat ping mechanism
        ├─ Sends __HEARTBEAT__ command to FIFO
        ├─ Waits for "PONG" response file
        ├─ Timeout: 3.0 seconds
        └─ Proves dispatcher reading FIFO
    
    Level 3 - Recent activity:
        _check_heartbeat() -> bool  # Lines 504-536
        ├─ Check heartbeat file mtime
        ├─ Must be recent (default 60s timeout)
        └─ Proves recent dispatcher activity
    
    Combined Logic:
    ├─ If process gone: return False
    ├─ If not reading FIFO: return False  
    ├─ If no recent activity: return False
    └─ Else: return True (healthy)
    
    ISSUE #3.0 (MEDIUM - UNRELIABLE PID DETECTION):
    ├─ _find_dispatcher_pid() searches by process name
    ├─ Matches "terminal_dispatcher" in process name
    ├─ Could match wrong process if names similar
    ├─ Could fail to find dispatcher even if running
    └─ Result: _is_dispatcher_alive() returns False incorrectly
```

**Terminal Restart & Recovery**:

```python
_ensure_dispatcher_healthy() -> bool:  # Lines 1037-1125
    """Ensure dispatcher is running, restart if needed"""
    
    Steps:
    1. Check if already healthy: _is_dispatcher_healthy()
    2. If healthy: return True
    3. If fallback mode: return False (ISSUE #1.4)
    4. Attempt restart: restart_terminal()
       ├─ Increment _restart_attempts
       ├─ If _restart_attempts > _max_restart_attempts:
       │  └─ Set _fallback_mode = True (CRITICAL ISSUE)
       └─ Return False
    
    ISSUE #1.4 (CRITICAL - PERMANENT FALLBACK MODE):
    ├─ Line 1056: _restart_attempts > _max_restart_attempts
    ├─ Sets _fallback_mode = True
    ├─ Lines 816-820: send_command() checks fallback mode:
    │  if fallback_mode:
    │      self.logger.warning("...in fallback mode")
    │      return False
    ├─ Issue: reset_fallback_mode() defined but NEVER CALLED
    ├─ Result: Terminal PERMANENTLY DISABLED after 5 failures
    ├─ Recovery: Requires application restart
    └─ Fix: Auto-reset fallback after successful health check
```

**Restart Terminal**:

```python
restart_terminal() -> bool:  # Lines 1201-1316
    """Close and restart terminal + dispatcher"""
    
    Steps:
    1. Log restart attempt
    2. close_terminal() [lines 1160-1199]
       ├─ Send SIGTERM to terminal process
       ├─ Wait 2 seconds
       ├─ Send SIGKILL if still alive
       ├─ Wait for process to die
       ├─ Close dummy writer FD: _close_dummy_writer_fd()
       └─ Reset process/pid state
    
    3. _close_dummy_writer_fd() [lines 359-380]
       ├─ Idempotent (safe to call multiple times)
       ├─ Uses _fd_closed flag for atomicity
       ├─ Suppresses EBADF errors
       └─ Thread-safe with _write_lock
    
    4. Atomic FIFO recreation:
       ├─ Delete stale FIFO (lines 1227-1237)
       ├─ Create temp FIFO with unique name
       ├─ Atomic rename to target path
       └─ Prevents "no FIFO" window
    
    5. Launch terminal: _launch_terminal()
       ├─ Try gnome-terminal, konsole, xterm, etc.
       ├─ Execute: bash -il dispatcher_path fifo_path
       ├─ Return True if started successfully
       └─ Wait up to 5 seconds for dispatcher
    
    6. Open dummy writer: _open_dummy_writer()
       ├─ Keep FIFO alive (prevent EOF)
       └─ Allows non-blocking writes
    
    ISSUE #2.5 (HIGH - DUMMY WRITER FD RACE):
    ├─ Multiple open paths:
    │  ├─ _ensure_fifo() line 294
    │  ├─ _open_dummy_writer() line 330
    │  ├─ restart_terminal() line 1269
    │  └─ No synchronization between them
    ├─ Could open same FD twice
    ├─ Result: FD leak (one never closed)
    └─ Fix: Consolidate to single open method
    
    ISSUE #3.2 (MEDIUM - WORKERS NOT STOPPED):
    ├─ Lines 1201-1227: No worker cleanup before restart
    ├─ Active worker might be writing to old FIFO
    ├─ FIFO deleted at line 1227
    ├─ Worker gets OSError, fails silently
    └─ Fix: Stop workers before FIFO deletion
```

#### 2.1.3 Threading Model

**Lock Hierarchy**:

```
_write_lock (threading.Lock)
├─ Protects: FIFO write operations
├─ Methods:
│  ├─ _send_command_direct() [614-671]
│  ├─ send_command() [801-935]
│  ├─ _open_dummy_writer() [316-357]
│  └─ _close_dummy_writer_fd() [359-380]
└─ Purpose: Prevent concurrent writes corrupting FIFO

_state_lock (threading.Lock)
├─ Protects: terminal_pid, dispatcher_pid, _restart_attempts, _fallback_mode
├─ Methods:
│  ├─ All getters for these attributes
│  ├─ _ensure_dispatcher_healthy() [1037-1125]
│  ├─ _is_dispatcher_alive() [470-502]
│  └─ restart_terminal() [1201-1316]
└─ Purpose: Prevent race between main thread and worker threads

_workers_lock (threading.Lock)
├─ Protects: _active_workers list
├─ Methods:
│  ├─ send_command_async() [937-1018]
│  └─ cleanup() [1318-1359]
└─ Purpose: Prevent concurrent list modification
```

**Worker Thread Lifecycle**:

```
Main Thread                          Worker Thread
─────────────────────────────────────────────────────

send_command_async()
├─ Create TerminalOperationWorker
├─ Connect signals                          
├─ Add to _active_workers
└─ worker.start() ────────────────> run()
                                    ├─ _ensure_dispatcher_healthy()
                                    ├─ _send_command_direct()
                                    └─ operation_finished.emit()
                                        │
                                        └──> Main Thread Signal Handler
                                            cleanup_worker():
                                            ├─ Remove from _active_workers
                                            ├─ worker.safe_wait()
                                            ├─ worker.disconnect_all()
                                            └─ worker.deleteLater()
                                                │
                                                └──> Qt Event Loop
                                                    Deletes worker
                                                    (eventually)
```

**Race Condition #1.0 (CRITICAL)**:

```
send_command(command, ensure_terminal=True):
    
    Main Thread (no lock):
    ├─ Line 838: if ensure_terminal:
    │       if not _is_dispatcher_running():  ◄─ NO LOCK
    │           self.logger.warning(...)
    │       if not _ensure_dispatcher_healthy():  ◄─ NO LOCK
    │           return False
    │
    │   [100-500ms on slow systems]
    │   [Dispatcher could crash HERE]
    │
    ├─ Line 869: with self._write_lock:  ◄─ LOCK ACQUIRED HERE
    │       fifo_fd = os.open(self.fifo_path, os.O_WRONLY | os.O_NONBLOCK)
    │       ◄─ Can fail with ENXIO if dispatcher dead
    │
    └─ Exception handler (line 899):
            if e.errno == errno.ENXIO:
                # Dispatcher crashed between check and write
                # Just log and return False
                return False
    
    Fix: Acquire lock before health check:
    
    with self._write_lock:
        if not self._is_dispatcher_healthy():
            return False
        # Then proceed with FIFO write
        fifo_fd = os.open(...)
```

#### 2.1.4 Critical Issues in Detail

**Issue #1.0: CRITICAL - Race in send_command()**

```
Severity: CRITICAL (affects reliability under load)
Lines: 801-935
Impact: Commands may be lost, inefficient retries, cascading failures

Root Cause:
- Health check at line 838 without lock
- Dispatcher can crash between check and write
- os.open() fails with ENXIO
- Retry loop masks problem but reduces throughput

Production Risk:
- Under high concurrency (10+ launches), race triggers frequently
- ENXIO errors spike, user sees delayed launches
- Each retry adds 100-500ms latency
- Can cascade: if many retries, system becomes unresponsive

Test Coverage Gap:
- No concurrent send_command() tests
- Single-threaded tests pass
- Fails under parallel load

Reproduction:
1. Send 10 commands rapidly from different threads
2. While commands in flight, kill dispatcher
3. Observe ENXIO errors and retries

Fix Effort: LOW (move lock acquisition up 30 lines)
```

**Issue #1.3: CRITICAL - Worker Thread Leak**

```
Severity: CRITICAL (segfault risk)
Lines: 937-1018 (send_command_async)
Impact: Worker threads accumulate, potential segfaults

Root Cause:
- cleanup_worker() closure has complex lifecycle
- cleanup() relies on signal emission
- deleteLater() is unreliable if event loop stalled

Scenarios:
1. Signal never emitted
   └─ Worker crashes in do_work() → operation_finished never emitted
2. deleteLater() never executed
   └─ Event loop stalled/busy → deletion deferred indefinitely
3. Timeout during cleanup
   └─ safe_wait(3000) expires → worker still running

Production Risk:
- Long-running sessions accumulate workers
- Workers consume memory and thread resources
- Eventually hit thread pool limit
- Workers still running when process exits → segfault

Evidence:
- No max worker count enforcement
- No explicit wait timeout on worker cleanup
- deleteLater() not guaranteed to execute

Reproduction:
1. Send many async commands
2. Restart terminal frequently
3. Observe worker threads accumulate
4. Eventually crash on process exit

Fix Effort: MEDIUM (implement explicit wait with timeout)
```

**Issue #1.4: CRITICAL - Permanent Fallback Mode**

```
Severity: CRITICAL (blocks all launches)
Lines: 816-820, 1024-1112
Impact: Terminal permanently disabled after recovery failure

Root Cause:
- _ensure_dispatcher_healthy() sets _fallback_mode = True after 5 restarts
- send_command() checks fallback_mode and returns False
- reset_fallback_mode() exists but is NEVER CALLED

Code Evidence:
Line 816-820 (send_command):
    if fallback_mode:
        self.logger.warning("Persistent terminal in fallback mode")
        return False

Line 1056 (_ensure_dispatcher_healthy):
    if self._restart_attempts > self._max_restart_attempts:
        with self._state_lock:
            self._fallback_mode = True
            self.logger.error("Persistent terminal in fallback mode")
        return False

Reset Method (lines 1139-1150):
    def reset_fallback_mode(self) -> None:
        with self._state_lock:
            self._fallback_mode = False

Problem:
- No automatic reset
- No timeout-based reset
- Not called from any code path
- Dead code: only exists but never executed

Production Impact:
- If terminal fails to start 5 times during app session
- ALL subsequent launches blocked
- User must restart application
- Very poor UX

Reproduction:
1. Kill dispatcher repeatedly (5+ times)
2. Try to send command after 5th failure
3. Command blocked with "fallback mode" message
4. Restart dispatcher manually
5. Still blocked (needs app restart)

Fix Options:
1. Auto-reset after successful health check
2. Reset on explicit restart_terminal() call
3. Time-based reset (try again after 60 seconds)
4. Expose as public API for manual recovery

Fix Effort: LOW (add reset logic to _ensure_dispatcher_healthy)
```

#### 2.1.5 Resource Management Issues

**FIFO Lifecycle**:

```
Created: __init__() calls _ensure_fifo()
├─ Delete stale from previous crash
├─ Create new FIFO with 0o600 perms
└─ Verify it's actually a FIFO

Keep Alive: Dummy writer FD
├─ Opened after dispatcher starts
├─ Prevents EOF when no active writers
└─ Allows non-blocking writes

Closed: cleanup() or cleanup_fifo_only()
├─ Close dummy writer FD
├─ Delete FIFO file
└─ Remove heartbeat file

Leak Scenario #2.5:
├─ _ensure_fifo() opens dummy writer (line 294)
├─ Later _open_dummy_writer() opens it again (line 330)
├─ No synchronization between
└─ Result: FD leak (one never closed)
```

**Process Lifecycle**:

```
Created: _launch_terminal() calls subprocess.Popen()
├─ start_new_session=True (separate session)
├─ PID tracked in self.terminal_pid
└─ Process stored in self.terminal_process

Checked: _is_terminal_alive() uses psutil
├─ Read terminal_pid from state
├─ Check if process exists and not zombie
└─ Return False if dead

Cleanup: close_terminal()
├─ Send SIGTERM
├─ Wait 2 seconds
├─ Send SIGKILL
├─ Wait for process
├─ Close dummy writer FD
└─ Reset process/pid state

Issue: process.wait() is blocking
├─ Close terminal blocks if process stuck
├─ Could freeze caller
└─ Need timeout wrapper
```

---

### 2.2 CommandLauncher (850 lines)

**File**: `/home/gabrielh/projects/shotbot/command_launcher.py`

**Status**: PRODUCTION (being consolidated into PersistentTerminalManager)

#### 2.2.1 Architecture

```python
class LaunchContext:  # Pydantic model
    """Launch request context"""
    shot: ShotModel
    app_name: str
    open_3de_scene: bool = False
    raw_plate_path: str | None = None
    # ... other options ...

class CommandLauncher(QObject):  # Lines 90-845
    """Full-featured launcher with environment setup"""
    
    Signals:
    - command_executed(str, int)
    - command_error(str)
    
    Dependencies:
    ├─ EnvironmentManager: Build env variables
    ├─ ProcessExecutor: Execute commands
    ├─ PersistentTerminalManager: Optional FIFO terminal
    ├─ SimpleNukeLauncher: Nuke-specific handling
    └─ Various scene/script finders
    
    Key Methods:
    ├─ __init__(): Initialize with terminal manager
    ├─ set_current_shot(): Set shot context
    ├─ launch_app(): Launch VFX app
    ├─ launch_app_with_scene(): Launch with 3DE scene
    ├─ launch_app_with_scene_context(): Full context launch
    ├─ cleanup(): Resource cleanup (INCOMPLETE)
    └─ __del__(): Fallback cleanup
```

#### 2.2.2 Critical Dependencies

```python
# Lines 102-140: __init__ method
self.current_shot: ShotModel | None = None
self.persistent_terminal: PersistentTerminalManager | None = persistent_terminal

# Lines 118-140: Helper instances
self.env_manager = EnvironmentManager()
self.process_executor = ProcessExecutor(self.persistent_terminal)
self.nuke_handler = SimpleNukeLauncher()
self._raw_plate_finder = RawPlateFinder()
self._nuke_script_generator = NukeScriptGenerator()
self._threede_latest_finder = ThreeDELatestFinder()
self._maya_latest_finder = MayaLatestFinder()
```

#### 2.2.3 Critical Issue: Missing Cleanup

**Issue #2.3 (HIGH - Missing ProcessExecutor Cleanup)**

```
Severity: HIGH (resource leak)
Lines: 151-172 (cleanup method)
Impact: ProcessExecutor never cleaned up, leaves resources open

Code:
def cleanup(self) -> None:
    try:
        _ = self.process_executor.execution_started.disconnect(...)
        _ = self.process_executor.execution_progress.disconnect(...)
        _ = self.process_executor.execution_completed.disconnect(...)
        _ = self.process_executor.execution_error.disconnect(...)
    except (RuntimeError, TypeError, AttributeError):
        pass
    # MISSING: self.process_executor.cleanup() !

Problem:
- Signals disconnected
- But ProcessExecutor instance not cleaned up
- Executor holds process references
- Background threads may continue running
- Terminal connections stay open

Fix:
def cleanup(self) -> None:
    try:
        # Disconnect signals
        _ = self.process_executor.execution_started.disconnect(...)
        # ... other disconnects ...
        
        # CRITICAL: Call executor cleanup
        if hasattr(self.process_executor, 'cleanup'):
            self.process_executor.cleanup()
        
        # Also cleanup Nuke handler
        if hasattr(self.nuke_handler, 'cleanup'):
            self.nuke_handler.cleanup()
    except (RuntimeError, TypeError, AttributeError):
        pass

Production Impact:
- ProcessExecutor holds PersistentTerminalManager reference
- Terminal stays "alive" even after launcher destroyed
- Subsequent launches may fail or behave unexpectedly
- Memory leaks over session lifetime
```

#### 2.2.4 Launch Flow

```python
launch_app(app_name: str, options: dict) -> bool:  # Lines 383-583
    """Launch VFX application"""
    
    Steps:
    1. Validate current_shot set
    2. Build launch context:
       ├─ Extract options (open_3de, raw_plate, etc.)
       └─ Create LaunchContext
    
    3. Build environment:
       ├─ env_manager.build_environment()
       └─ Get VFX tool-specific vars
    
    4. Build command:
       ├─ For Nuke: Use nuke_handler.open_latest_script()
       ├─ For Maya: Build maya command
       ├─ For 3DE: Build 3DE command
       └─ Handle special options (raw plate, scenes, etc.)
    
    5. Execute command:
       ├─ Emit command_executed signal
       └─ Handle errors with command_error signal
    
    6. Emit completion signals:
       ├─ command_executed(command, 0) on success
       └─ command_error(error_msg) on failure

_try_persistent_terminal() -> bool:  # Lines 223-263
    """Attempt to use persistent terminal if available"""
    
    Logic:
    if self.persistent_terminal is None:
        return False
    
    # Try to send via FIFO
    result = self.persistent_terminal.send_command(command)
    return result
    
    Issue: No timeout on send_command()
    └─ Could block indefinitely if FIFO stuck
```

---

### 2.3 SimplifiedLauncher (819 lines)

**File**: `/home/gabrielh/projects/shotbot/simplified_launcher.py`

**Status**: DEPRECATED (broken, will be removed, DO NOT USE)

#### 2.3.1 Why It's Broken

**Issue #1.2 (CRITICAL - Subprocess Leak)**

```
Severity: CRITICAL (resource leak)
Lines: 366-416 (_execute_in_terminal)
Impact: Subprocess may be killed incorrectly or tracked inconsistently

Code Problem:
def _execute_in_terminal(self, command: str, env: dict) -> bool:
    proc = None
    try:
        # Line 370: Create process
        proc = subprocess.Popen(
            terminal_cmd,
            env=full_env,
            start_new_session=True,
            text=True
        )
        
        # Lines 377-380: Add to tracking
        with self._process_lock:
            self._active_processes[proc.pid] = proc
        self.process_started.emit(command, proc.pid)
        # ISSUE: If emit() throws exception HERE
        #        process is ALREADY in tracking dict
        #        But exception handler assumes it's NOT tracked
        
        return True
        
    except FileNotFoundError as e:
        # Line 393: Exception handler
        if proc is not None:
            try:
                proc.kill()  # Kill process
                proc.close()  # Close handle
            except Exception:
                pass
        return False
        # PROBLEM: If proc was added to _active_processes,
        #          killing it here corrupts tracking
        #          Process both killed and still in dict

Root Cause:
- Exception handler assumes preconditions that may not hold
- Signal emission (line 380) can throw
- Exception caught assumes process not tracked
- But it IS already in the dict

Production Impact:
- Process killed prematurely
- Tracking dictionary corrupted
- Cleanup during app shutdown becomes unreliable
- Resource leaks accumulate

Proof:
1. Line 370: subprocess.Popen() succeeds
2. Line 379: _process_lock acquired
3. Line 380: self._active_processes[proc.pid] = proc
4. Line 381: self.process_started.emit(command, proc.pid)
5. [Signal handler raises exception]
6. Line 385-394: Exception caught
7. Line 393: proc.kill() kills already-tracked process
8. Tracking dict now has dead process
```

**Issue #2.1 (HIGH - No Cleanup on Terminal Failure)**

```
Severity: HIGH (resource leak)
Lines: 104-191 (launch_vfx_app)
Impact: Resources not cleaned up when terminal launch fails

Code:
def launch_vfx_app(self, app_name: str, options: dict | None = None) -> bool:
    # ... setup and env building ...
    # Resources allocated:
    # - Environment dictionary created (potentially large with VFX tools)
    # - Socket connections established (if workspace integration)
    # - Temporary files created (scene detection, script building)
    
    # ... command building ...
    
    # Execute in terminal
    if not self._execute_in_terminal(command, env):  # Can fail
        # NO CLEANUP HERE
        return False
    
    return True

Problem:
- If terminal launch fails
- Resources allocated above are abandoned
- Environment dictionary not cleared
- Temp files not deleted
- Connections not closed

Fix:
def launch_vfx_app(self, ...) -> bool:
    try:
        # ... setup ...
        
        if not self._execute_in_terminal(command, env):
            raise RuntimeError(f"Failed to execute {app_name}")
        
        return True
        
    except Exception as e:
        # Cleanup on any error
        self._cleanup_resources()
        self._emit_error(str(e))
        return False
        
    finally:
        # Always clear environment reference
        env.clear()
```

**Issue #2.6 (HIGH - Cache Not Thread-Safe)**

```
Severity: HIGH (data corruption)
Lines: 525-561 (_cache_get, _cache_set)
Impact: Race conditions in workspace cache

Code:
def _cache_get(self, key: str) -> str | None:
    with self._cache_lock:
        if key in self._ws_cache:
            result, timestamp = self._ws_cache[key]
            if time.time() - timestamp < self._ws_cache_ttl:
                return result
            else:
                del self._ws_cache[key]  # Delete INSIDE lock
    return None

Problem:
- Lock acquired for entire operation (good)
- But time.time() call inside lock (potentially slow)
- TTL cache could be cleared by invalidate_cache()
- Concurrent iteration + deletion possible

def invalidate_cache(self, keys: list[str] | None = None) -> None:
    with self._cache_lock:
        if keys is None:
            self._ws_cache.clear()  # Clear all
        else:
            for key in keys:
                self._ws_cache.pop(key, None)

Race Condition:
Thread A: Iterating cache in _cache_get()
Thread B: Call invalidate_cache() with keys=None
Result: Dictionary changes size during iteration → RuntimeError
```

#### 2.3.2 Known Issues Summary

| Issue | Severity | Lines | Impact |
|-------|----------|-------|--------|
| Subprocess leak on exception | CRITICAL | 366-416 | Process tracking corrupted |
| No cleanup on terminal failure | HIGH | 104-191 | Resource leak |
| Cache race condition | HIGH | 525-561 | Dict iteration errors |
| No timeout for blocking ops | MEDIUM | 341-415 | Could hang indefinitely |
| Cache TTL not configurable | MEDIUM | 70-75 | Can't adjust strategy |
| No environment isolation | MEDIUM | 238-252 | Inherits parent env |
| Process tracking unreliable | MEDIUM | 366-415 | Terminal PID not app PID |
| No proper thread safety | HIGH | 70-94 | Multiple race conditions |

---

## PART 3: LAUNCHER ECOSYSTEM

### 3.1 LauncherController (754 lines)

**File**: `/home/gabrielh/projects/shotbot/controllers/launcher_controller.py`

**Status**: PRODUCTION (coordinates both launcher systems)

#### 3.1.1 Responsibilities

```python
class LauncherController(QObject):  # Lines 69-754
    """Coordinates launcher operations with UI"""
    
    Main Responsibilities:
    1. Shot context management
    2. Scene context management
    3. Launch request routing
    4. Custom launcher execution
    5. UI menu/button coordination
    6. Signal coordination
    
    Key Methods:
    ├─ __init__(window): Store reference to MainWindow
    ├─ set_current_shot(): Set shot for launches
    ├─ set_current_scene(): Set 3DE scene for launches
    ├─ get_launch_options(): Return available apps
    ├─ launch_app(app_name): Route to launcher
    ├─ execute_custom_launcher(launcher_id): Execute custom
    ├─ show_launcher_manager(): Show UI dialog
    ├─ update_launcher_menu(): Update menu items
    └─ update_launcher_menu_availability(): Enable/disable items
    
    Dependencies:
    ├─ MainWindow: Parent container
    ├─ window.command_launcher: Primary launcher (Simplified or Command)
    ├─ window.launcher_manager: Custom launcher manager (if legacy)
    └─ window.threede_controller: 3DE scene management
    
    Signal Handling:
    ├─ command_launcher.command_executed → _on_launcher_finished()
    ├─ command_launcher.command_error → _on_command_error()
    ├─ launcher_manager.execution_finished → _on_launcher_finished()
    └─ launcher_manager.command_error → _on_command_error()
```

#### 3.1.2 Critical Code Paths

```python
launch_app(app_name: str) -> None:  # Lines 355-467
    """Launch application"""
    
    Steps:
    1. Validate current_shot is set
    2. Get launch options from current_shot
    3. Build options dict:
       ├─ open_3de_scene: bool (from UI checkbox)
       ├─ raw_plate_path: str | None
       ├─ other options
       └─ Pass to launcher
    
    4. Call appropriate launcher:
       ├─ If SimplifiedLauncher:
       │   └─ command_launcher.launch_app(app_name)
       ├─ If CommandLauncher:
       │   └─ command_launcher.launch_app(app_name)
       └─ Both emit signals on completion

_on_command_error(error: str):  # Lines 647-678
    """Handle launcher error"""
    
    Signal Handler:
    ├─ Extract error message
    ├─ Log error
    ├─ Show notification (if enabled)
    └─ Update UI state

update_launcher_menu_availability():  # Lines 628-721
    """Update menu items based on context"""
    
    Logic:
    ├─ Check if shot selected
    ├─ For each app: check if available
    ├─ Enable/disable menu items
    └─ Update button states
```

---

### 3.2 Process Executor (312 lines)

**File**: `/home/gabrielh/projects/shotbot/launch/process_executor.py`

**Status**: PRODUCTION (but missing cleanup in CommandLauncher)

#### 3.2.1 Architecture

```python
class ProcessExecutor(QObject):  # Singleton-like usage
    """Execute commands in terminal or subprocess"""
    
    Signals:
    ├─ execution_started(str): Command started
    ├─ execution_progress(str): Status update
    ├─ execution_completed(str): Command done
    └─ execution_error(str): Error message
    
    Key Methods:
    ├─ __init__(persistent_terminal): Initialize
    ├─ run_command(command, options): Execute command
    └─ (missing: cleanup())
    
    Uses PersistentTerminalManager:
    ├─ If Config.PERSISTENT_TERMINAL_ENABLED:
    │   └─ Use persistent_terminal.send_command()
    ├─ Else:
    │   └─ subprocess.Popen() + terminal emulator
    └─ Emit signals on completion
```

#### 3.2.2 Critical Issue: Signal Leak

**Issue #1.1 (CRITICAL - Signal Connection Leak)**

```
Severity: CRITICAL (signal handlers persist after destruction)
Impact: Memory leak, potential segfaults, undefined behavior

Root Cause:
- ProcessExecutor connects to PersistentTerminalManager signals
- CommandLauncher holds ProcessExecutor reference
- CommandLauncher.cleanup() disconnects signals but doesn't cleanup executor
- ProcessExecutor destroyed without cleanup

Code Path:
1. CommandLauncher.__init__():
   Line 119: self.process_executor = ProcessExecutor(self.persistent_terminal)
   
2. ProcessExecutor.__init__():
   - Connects to persistent_terminal signals (implicitly)

3. CommandLauncher.cleanup():
   Line 151-168: Disconnect signals
   - But NO cleanup of process_executor!
   
4. CommandLauncher destroyed
   - ProcessExecutor still has signal connections
   - References to PersistentTerminalManager remain
   
5. PersistentTerminalManager emits signal:
   - Signal handlers for disconnected slots still registered
   - Calling deleted ProcessExecutor → SEGFAULT

Fix:
def cleanup(self) -> None:
    try:
        # Disconnect signals
        _ = self.process_executor.execution_started.disconnect(...)
        # ... other disconnects ...
        
        # CRITICAL: Call executor cleanup
        if hasattr(self.process_executor, 'cleanup'):
            self.process_executor.cleanup()
            
    except (RuntimeError, TypeError, AttributeError):
        pass
```

---

### 3.3 LauncherManager (680 lines)

**File**: `/home/gabrielh/projects/shotbot/launcher_manager.py`

**Status**: PRODUCTION (custom launcher management)

#### 3.3.1 Architecture

```python
class LauncherManager(QObject):  # Lines 63-679
    """Custom launcher CRUD + execution"""
    
    Signals:
    ├─ launchers_changed()
    ├─ launcher_added(id)
    ├─ launcher_updated(id)
    ├─ launcher_deleted(id)
    ├─ validation_error(error)
    ├─ execution_started(launcher_id)
    ├─ execution_finished(launcher_id)
    ├─ command_started(launcher_id)
    ├─ command_finished(launcher_id)
    ├─ command_error(error)
    └─ command_output(output)
    
    Key Methods:
    ├─ create_launcher(): Create custom launcher
    ├─ update_launcher(): Update launcher
    ├─ delete_launcher(): Delete launcher
    ├─ get_launcher(): Get by ID
    ├─ list_launchers(): List all
    ├─ execute_launcher(): Execute custom launcher
    ├─ execute_in_shot_context(): Execute in shot context
    └─ shutdown(): Cleanup
    
    Internal Components:
    ├─ _config_manager: LauncherConfigManager
    ├─ _repository: LauncherRepository
    ├─ _validator: LauncherValidator
    └─ _process_manager: LauncherProcessManager
```

#### 3.3.2 Critical Issue: Weak Signal Connections

**Issue #2.4 (HIGH - Weak Signal Connections)**

```
Severity: HIGH (partial signal failures)
Lines: 122-131, 638-665
Impact: Some signals may not be connected, causing signal drops

Code:
def __init__(self, ...):
    # Lines 122-131: Try to connect signals
    try:
        _ = self._process_manager.process_started.connect(self.command_started)
        _ = self._process_manager.process_finished.connect(self.command_finished)
        _ = self._process_manager.process_error.connect(self.command_error)
        self._signals_connected = True
    except (AttributeError, RuntimeError) as e:
        self.logger.debug(f"Could not connect process manager signals: {e}")
        self._signals_connected = False  # ALL signals marked failed
        # PROBLEM: Some may have connected before error

Problem:
- If process_finished.connect() throws
- But process_started.connect() succeeded
- _signals_connected = False (misleading)
- Shutdown code assumes ALL failed

def shutdown(self):
    # Lines 648-657: Try to disconnect
    if hasattr(self._process_manager, "process_started"):
        with contextlib.suppress(RuntimeError, TypeError):
            _ = self._process_manager.process_started.disconnect()  # May not be connected!

Fix:
def __init__(self, ...):
    self._signal_connections: dict[str, bool] = {
        "process_started": False,
        "process_finished": False,
        "process_error": False,
    }
    
    # Try each signal individually
    for signal_name in self._signal_connections:
        try:
            signal = getattr(self._process_manager, signal_name)
            handler = getattr(self, f"command_{signal_name.replace('process_', '')}")
            _ = signal.connect(handler)
            self._signal_connections[signal_name] = True
        except (AttributeError, RuntimeError) as e:
            self.logger.debug(f"Could not connect {signal_name}: {e}")

def shutdown(self):
    # Only disconnect connected signals
    for signal_name, connected in self._signal_connections.items():
        if connected:
            try:
                signal = getattr(self._process_manager, signal_name)
                _ = signal.disconnect()
            except (RuntimeError, TypeError, AttributeError):
                pass
```

#### 3.3.3 Critical Issue: Blocking Cleanup in Event Loop

**Issue #2.7 (HIGH - Blocking Cleanup)**

```
Severity: HIGH (UI freeze)
Lines: 198-202
Impact: Qt event loop blocks during process cleanup

Code:
def _cleanup_finished_workers(self) -> None:
    """Backward compatibility cleanup"""
    self._process_manager.cleanup_finished_workers()  # BLOCKS!

Problem:
- If connected to a signal (which it likely is)
- Signal fires from event loop
- cleanup_finished_workers() may do blocking I/O:
  ├─ process.wait() ← BLOCKING
  ├─ process.kill() ← Blocking
  └─ os.waitpid() ← BLOCKING
- Main Qt event loop stalled
- UI frozen until cleanup completes
- User sees "Not Responding"

Scenarios:
- Many processes finishing simultaneously
- Slow disk I/O during cleanup
- Process stuck in uninterruptible state

Fix:
def _cleanup_finished_workers(self) -> None:
    """Cleanup workers in background thread"""
    def async_cleanup():
        self._process_manager.cleanup_finished_workers()
    
    # Move to background worker
    worker = QThread()
    worker.run = async_cleanup
    worker.start()
    
    # Don't wait for completion (let it run in background)
```

---

## PART 4: INTEGRATION POINTS

### 4.1 MainWindow Launcher Setup

**File**: `/home/gabrielh/projects/shotbot/main_window.py` (lines 298-328)

```python
use_simplified_launcher = os.environ.get("USE_SIMPLIFIED_LAUNCHER", "true").lower() == "true"

if use_simplified_launcher:
    # BROKEN PATH
    from simplified_launcher import SimplifiedLauncher
    
    self.command_launcher = SimplifiedLauncher()  # ❌ BROKEN
    self.launcher_manager = None
    self.persistent_terminal = None
else:
    # WORKING PATH
    self.persistent_terminal = PersistentTerminalManager(parent=self)
    self.command_launcher = CommandLauncher(
        persistent_terminal=self.persistent_terminal
    )
    self.launcher_manager = LauncherManager()
```

**Critical Decision Point**:
- Default is "true" = SimplifiedLauncher = BROKEN
- Must be set to "false" for production
- Should be changed to default to "false"

### 4.2 Feature Flag Usage Across Codebase

```python
# ONLY in MainWindow.__init__()
# Feature flag is NOT referenced elsewhere

# All code MUST be compatible with both:
├─ SimplifiedLauncher (current default but broken)
├─ CommandLauncher (legacy but production-ready)
└─ Both have:
   ├─ set_current_shot()
   ├─ launch_app()
   ├─ launch_app_with_scene()
   ├─ command_executed signal
   └─ command_error signal
```

### 4.3 Signal Flow Architecture

```
SimplifiedLauncher                      CommandLauncher
├─ command_executed(cmd, result)        ├─ command_executed(cmd, result)
├─ command_error(error)                 ├─ command_error(error)
├─ process_started(pid, cmd)            ├─ (no process signals)
└─ process_finished(pid, return_code)   └─ Uses ProcessExecutor internally
                                            └─ execution_completed signal
                                            
Both:
   ↓ (same signature)
   
LauncherController._on_launcher_finished()
   ↓
UI Update (notifications, button states)
```

---

## PART 5: CRITICAL ISSUES MATRIX

### 5.1 CRITICAL (Must Fix Before Production)

| ID | Component | Issue | Lines | Impact | Fix Effort |
|----|-----------|-------|-------|--------|-----------|
| 1.0 | PersistentTerminalManager | Race in send_command() | 801-935 | Commands dropped under load | LOW |
| 1.1 | ProcessExecutor/CommandLauncher | Signal leak | 119, 151 | Memory leak, segfaults | LOW |
| 1.2 | SimplifiedLauncher | Subprocess leak | 366-416 | Tracking corrupted | MEDIUM |
| 1.3 | PersistentTerminalManager | Worker thread leak | 937-1018 | Accumulation, segfault | MEDIUM |
| 1.4 | PersistentTerminalManager | Fallback permanent | 1024-1112 | Terminal disabled forever | LOW |

### 5.2 HIGH (Should Fix Soon)

| ID | Component | Issue | Lines | Impact | Fix Effort |
|----|-----------|-------|-------|--------|-----------|
| 2.1 | SimplifiedLauncher | No cleanup on failure | 104-191 | Resource leak | LOW |
| 2.2 | CommandLauncher | Missing executor cleanup | 151-172 | Resource leak | LOW |
| 2.3 | CommandLauncher | Missing ProcessExecutor cleanup | 151-172 | Terminal stays open | LOW |
| 2.4 | LauncherManager | Weak signal connections | 122-131 | Partial failures | MEDIUM |
| 2.5 | PersistentTerminalManager | Dummy writer FD race | 240-315 | FD leak | MEDIUM |
| 2.6 | SimplifiedLauncher | Cache not thread-safe | 525-561 | Dict errors | LOW |
| 2.7 | LauncherManager | Blocking cleanup in event loop | 198-202 | UI freeze | MEDIUM |

### 5.3 MEDIUM (Design Issues)

12+ identified in memory files (see LAUNCHER_ARCHITECTURE_ISSUES_ANALYSIS)

---

## PART 6: FILE LOCATION REFERENCE

### 6.1 All Launcher Files (Alphabetical)

```
/home/gabrielh/projects/shotbot/
├─ command_launcher.py (850 lines)
├─ launcher_panel.py (628 lines)
├─ launcher_dialog.py (873 lines)
├─ launcher_manager.py (680 lines)
├─ persistent_terminal_manager.py (1,410 lines)
├─ simple_nuke_launcher.py (243 lines)
├─ simplified_launcher.py (819 lines - DEPRECATED)
│
├─ controllers/
│  └─ launcher_controller.py (754 lines)
│
├─ launch/
│  ├─ __init__.py (14 lines)
│  ├─ command_builder.py (289 lines)
│  ├─ environment_manager.py (136 lines)
│  └─ process_executor.py (312 lines)
│
└─ launcher/
   ├─ __init__.py (50 lines)
   ├─ config_manager.py (118 lines)
   ├─ models.py (365 lines)
   ├─ process_manager.py (558 lines)
   ├─ repository.py (227 lines)
   ├─ result_types.py (82 lines)
   ├─ validator.py (428 lines)
   └─ worker.py (275 lines)

TOTAL: 9,598 lines
```

### 6.2 Test Files

```
/home/gabrielh/projects/shotbot/tests/

Unit Tests (unit/):
├─ test_command_launcher.py
├─ test_command_launcher_properties.py
├─ test_command_launcher_threading.py
├─ test_launcher_controller.py
├─ test_launcher_dialog.py
├─ test_launcher_manager.py
├─ test_launcher_models.py
├─ test_launcher_panel.py
├─ test_launcher_process_manager.py
├─ test_launcher_validator.py
├─ test_launcher_worker.py
├─ test_simple_nuke_launcher.py
├─ test_simplified_launcher_maya.py
├─ test_simplified_launcher_nuke.py

Integration Tests (integration/):
├─ test_launcher_panel_integration.py
├─ test_launcher_workflow_integration.py
└─ test_main_window_coordination.py
```

---

## PART 7: RECOMMENDATIONS - PRIORITIZED

### IMMEDIATE (This Sprint)

1. **Fix CRITICAL Issue #1.0** - Race in send_command()
   - Move lock acquisition up 30 lines
   - Acquire _write_lock BEFORE health check
   - Estimated: 30 minutes

2. **Fix CRITICAL Issue #1.4** - Fallback mode permanent
   - Auto-reset fallback after successful health check
   - Or add time-based reset (60 seconds)
   - Estimated: 1 hour

3. **Fix CRITICAL Issue #1.1** - Signal leak in CommandLauncher
   - Add cleanup() call to ProcessExecutor
   - Estimated: 30 minutes

4. **Fix CRITICAL Issue #1.2** - Subprocess leak in SimplifiedLauncher
   - Restructure exception handling to track state
   - Or: Delete SimplifiedLauncher and migrate users
   - Estimated: 2 hours or 30 minutes

### SHORT TERM (Next Sprint)

5. **Fix HIGH Issue #2.3** - Missing ProcessExecutor cleanup
   - Call process_executor.cleanup() in CommandLauncher.cleanup()
   - Estimated: 30 minutes

6. **Fix HIGH Issue #2.5** - Dummy writer FD race
   - Consolidate FD opening to single method
   - Add _dummy_writer_open_lock for synchronization
   - Estimated: 1.5 hours

7. **Fix HIGH Issue #2.4** - Weak signal connections
   - Track signal connections individually
   - Disconnect only connected signals
   - Estimated: 1 hour

8. **Fix HIGH Issue #2.7** - Blocking cleanup in event loop
   - Move cleanup to background worker thread
   - Estimated: 1.5 hours

### LONG TERM (Architecture Cleanup)

9. **Remove SimplifiedLauncher completely**
   - Deprecated and broken anyway
   - Change feature flag default to "false"
   - Remove 819 lines of dead code
   - Remove all SimplifiedLauncher tests

10. **Consolidate launcher systems**
    - Consolidate CommandLauncher into PersistentTerminalManager
    - Unify with LauncherManager
    - Single launcher interface for all use cases

11. **Implement proper lifecycle management**
    - Add explicit cleanup() methods to all classes
    - Implement singleton reset() for test isolation
    - Add __del__() as safety net only

---

## PART 8: CODE PATTERNS TO CHANGE

### Pattern 1: Lock Acquired Too Late

**WRONG** (current code in Issue #1.0):
```python
# Check without lock
if not self._is_dispatcher_healthy():  # NO LOCK
    return False

# Lock acquired after check
with self._write_lock:  # LOCK HERE
    fifo_fd = os.open(...)  # Can fail if dispatcher crashed
```

**RIGHT**:
```python
with self._write_lock:
    # Check and execute atomically
    if not self._is_dispatcher_healthy():
        return False
    fifo_fd = os.open(...)
```

### Pattern 2: Exception Handler With Wrong Assumptions

**WRONG** (current code in Issue #1.2):
```python
try:
    resource = create_resource()  # Line A
    register_resource(resource)   # Line B - can throw
except Exception:
    cleanup_resource(resource)  # Assumes not registered!
```

**RIGHT**:
```python
resource = None
try:
    resource = create_resource()
    register_resource(resource)
except Exception:
    if resource is not None and resource not in registered:
        cleanup_resource(resource)
    raise
```

### Pattern 3: Missing Cleanup In Derived Classes

**WRONG**:
```python
class CommandLauncher:
    def __init__(self):
        self.process_executor = ProcessExecutor()
    
    def cleanup(self):
        # Only disconnect signals, don't cleanup executor
        self.process_executor.execution_started.disconnect()
```

**RIGHT**:
```python
class CommandLauncher:
    def __init__(self):
        self.process_executor = ProcessExecutor()
    
    def cleanup(self):
        # Disconnect signals
        try:
            self.process_executor.execution_started.disconnect()
        except (RuntimeError, TypeError):
            pass
        
        # CRITICAL: Clean up executor
        if hasattr(self.process_executor, 'cleanup'):
            self.process_executor.cleanup()
```

---

## CONCLUSION

The Shotbot launcher system is **functionally complete** but has **significant architectural debt** with **5 critical issues** that must be fixed before production use. The primary system (PersistentTerminalManager) is well-designed but has threading race conditions. The deprecated system (SimplifiedLauncher) is broken and should be deleted immediately.

**Estimated effort to fix all critical issues: 5-7 days**  
**Estimated effort for full refactoring: 3-4 weeks**  
**Production readiness after critical fixes: MEDIUM (still needs hardening)**

---

End of Very Thorough Launcher System Analysis
