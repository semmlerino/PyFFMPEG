# VERY THOROUGH ERROR HANDLING & EDGE CASES ANALYSIS
## Launcher/Terminal Code Deep Dive

**Analysis Date**: 2025-11-14  
**Files Analyzed**: 
- persistent_terminal_manager.py (1,410 lines)
- command_launcher.py (850 lines)  
- launch/process_executor.py (312 lines)
- launcher_manager.py (680 lines)
- terminal_dispatcher.sh (245 lines)

**Scope**: Error handling patterns, edge cases, missing error recovery, timeout handling

---

## PART 1: CRITICAL ERROR HANDLING GAPS

### 1.0 MISSING SUBPROCESS CLEANUP IN ProcessExecutor
**File**: `launch/process_executor.py`  
**Severity**: CRITICAL - Resource leak  
**Impact**: Subprocess references persist after ProcessExecutor destroyed

```python
# ProcessExecutor.__init__ (lines 64-89)
def __init__(self, persistent_terminal, config, parent=None):
    # Connects to persistent_terminal signals
    _ = self.persistent_terminal.operation_progress.connect(...)
    _ = self.persistent_terminal.command_result.connect(...)
    # ⚠️ NO: self.persistent_terminal.cleanup() in __init__

# ProcessExecutor.cleanup() (lines 287-311)
def cleanup(self):
    """Disconnect signals to prevent memory leaks"""
    # ✅ Properly disconnects signals from terminal
    # ✅ Only handles signal cleanup, not subprocess refs
    # ❌ MISSING: No cleanup of subprocess references
    # ❌ MISSING: No termination of background processes
```

**Root Cause**: ProcessExecutor may hold subprocess references from `execute_in_new_terminal()` (lines 173-216) but never explicitly terminates them.

**Edge Case**: If `execute_in_new_terminal()` spawns a process and returns False/error, subprocess stays running.

**Fix Required**:
```python
def cleanup(self):
    # Disconnect signals
    if self.persistent_terminal:
        # ... disconnect code ...
    
    # ✅ ADD: Cleanup any managed subprocess references
    # Track spawned processes and terminate them
    if hasattr(self, '_managed_processes'):
        for proc in self._managed_processes:
            try:
                proc.terminate()
                proc.wait(timeout=2.0)
            except (subprocess.TimeoutExpired, ProcessLookupError):
                proc.kill()
```

---

### 1.1 CommandLauncher Missing ProcessExecutor Cleanup
**File**: `command_launcher.py`  
**Severity**: CRITICAL - Resource leak  
**Lines**: 150-181 (cleanup method)

```python
# CommandLauncher.__init__ (lines 101-139)
self.process_executor = ProcessExecutor(persistent_terminal, Config)

# CommandLauncher.cleanup() (lines 150-181)
def cleanup(self):
    # Disconnects signals
    _ = self.process_executor.execution_started.disconnect(...)
    # ... other disconnects ...
    
    # ✅ FIXED: Now calls ProcessExecutor.cleanup()
    try:
        self.process_executor.cleanup()
    except (RuntimeError, TypeError, AttributeError):
        pass
```

**Status**: FIXED IN CURRENT CODE ✅

**Historical Issue**: Previous versions didn't call `process_executor.cleanup()`, only disconnected signals. This left ProcessExecutor with active signal connections.

---

### 1.2 PersistentTerminalManager Fallback Mode Never Auto-Reset
**File**: `persistent_terminal_manager.py`  
**Severity**: CRITICAL - Permanent failure state  
**Lines**: 1038-1128 (_ensure_dispatcher_healthy)

```python
# Lines 1056-1058: Setting fallback mode
if self._restart_attempts >= self._max_restart_attempts:
    self._fallback_mode = True
    return False

# Lines 816-820: Checking fallback mode
if fallback_mode:
    self.logger.warning("Persistent terminal in fallback mode")
    return False  # ALL COMMANDS BLOCKED

# Reset method exists (lines 1126-1137) but:
def reset_fallback_mode(self):  # ⚠️ NEVER CALLED FROM ANYWHERE
    with self._state_lock:
        self._fallback_mode = False
```

**Status**: FIXED IN CURRENT CODE ✅

**What was fixed**:
```python
# In _ensure_dispatcher_healthy (lines 1121-1124)
# On successful recovery:
with self._state_lock:
    self._restart_attempts = 0
    self._fallback_mode = False  # ✅ RESET HERE NOW
    return True
```

**Edge Case Not Covered**: If recovery happens BETWEEN calls to `_ensure_dispatcher_healthy()`, fallback mode won't auto-reset. For example:
- Dispatcher crashes → fallback mode activated
- User manually restarts dispatcher in terminal
- Next send_command() call sees fallback mode still True
- Command blocked even though dispatcher is healthy

**Improved Fix Needed**:
```python
def send_command(self, command, ensure_terminal=True):
    # Check if we're in fallback mode but dispatcher recovered
    with self._state_lock:
        fallback_mode = self._fallback_mode
    
    if fallback_mode:
        # Try to detect if dispatcher recovered
        if self._is_dispatcher_healthy():
            with self._state_lock:
                self._fallback_mode = False
                self._restart_attempts = 0
            self.logger.info("Fallback mode disabled - dispatcher recovered")
        else:
            return False
```

---

### 1.3 Race Condition: Health Check Before Lock in send_command()
**File**: `persistent_terminal_manager.py`  
**Severity**: HIGH - Race condition under load  
**Lines**: 838-868, 869-935

```python
# ORIGINAL PROBLEM (pre-fix):
# Line 838: Check without lock
if not self._is_dispatcher_running():
    self.logger.warning("Terminal not running...")
if not self._ensure_dispatcher_healthy():
    return False

# [100-500ms delay on slow systems]
# [Dispatcher could crash HERE]

# Line 869: Lock acquired here
with self._write_lock:
    fifo_fd = os.open(self.fifo_path, ...)  # Can fail with ENXIO

# STATUS: FIXED ✅
# Lock is now properly acquired BEFORE health check
# (Verified in current code - health check is now within state checks)
```

**Status**: Partially fixed but not perfectly in current code

**Current Implementation** (lines 801-935):
- Line 816-820: Fallback mode check WITH lock ✅
- Line 824-833: Command validation NO lock ✅ (doesn't need lock)
- Line 838-843: Health check WITHOUT proper lock ⚠️
- Line 869: FIFO write WITH lock ✅

**Issue**: Health check at line 838-843 happens BEFORE acquiring `_write_lock`:
```python
if ensure_terminal:
    if not self._is_dispatcher_running():  # ⚠️ NO LOCK
        self.logger.warning(...)
    if not self._ensure_dispatcher_healthy():  # ⚠️ NO LOCK
        # Health check can fail due to transient issues
        return False
```

**Edge Case**: Between health check and FIFO write, dispatcher can crash:
```
1. send_command("nuke shot") called
2. ensure_terminal=True
3. _is_dispatcher_running() returns True (no lock)
4. _ensure_dispatcher_healthy() returns True (no lock)
5. [Dispatcher crashes due to segfault or signal 9]
6. Lock acquired for FIFO write
7. os.open(FIFO) fails with ENXIO
8. Retry loop kicks in
9. Latency added, potential cascading failures under high load
```

**Workaround in Code**: Retry loop (lines 871-930) mitigates impact but doesn't prevent race.

**Better Fix Needed**:
```python
def send_command(self, command, ensure_terminal=True):
    # ... validation ...
    
    # Acquire lock FIRST
    with self._write_lock:
        # Now health check AND FIFO write are atomic
        if ensure_terminal:
            if not self._is_dispatcher_healthy():
                return False
        
        # Immediately write before dispatcher can crash
        fifo_fd = os.open(self.fifo_path, ...)
        # ... rest of write ...
```

---

### 1.4 FIFO Write Error Handling: Incomplete Recovery
**File**: `persistent_terminal_manager.py`  
**Lines**: 876-930 (error handling in send_command)

```python
# Current error handling:
try:
    fifo_fd = os.open(self.fifo_path, os.O_WRONLY | os.O_NONBLOCK)
    # ... write ...
except OSError as e:
    if e.errno == errno.ENOENT:
        # FIFO doesn't exist
        if attempt < max_retries - 1:
            if self._ensure_fifo():
                time.sleep(_CLEANUP_POLL_INTERVAL_SECONDS)
                continue  # RETRY
        self.logger.error(...)
    elif e.errno == errno.ENXIO:
        # No reader available
        if attempt < max_retries - 1:
            with self._state_lock:
                self.dispatcher_pid = None  # ✅ Clear cached PID
            time.sleep(_CLEANUP_POLL_INTERVAL_SECONDS)
            continue  # RETRY
        else:
            self.logger.error("No reader available after retries")
            with self._state_lock:
                self.dispatcher_pid = None  # ✅ Clear cached PID
    elif e.errno == errno.EAGAIN:
        self.logger.warning("FIFO write would block (buffer full?)")
    else:
        self.logger.error(...)
    break  # Exit retry loop
```

**Edge Cases Not Fully Handled**:

#### 1.4.1: EINTR (Interrupted System Call)
- **Symptom**: `os.open()` interrupted by signal
- **Current Handling**: Falls through to generic error handler
- **Should Do**: Retry without consuming retry count
- **Impact**: Signal during write could trigger false failure

```python
# ❌ MISSING HANDLER:
elif e.errno == errno.EINTR:
    # Signal interrupted - don't count as real failure
    self.logger.debug("Interrupted system call, retrying...")
    continue  # RETRY without count
```

#### 1.4.2: EBADF (Bad File Descriptor)
- **Symptom**: Somehow got invalid FD from prior call
- **Current Handling**: Generic error message
- **Should Do**: Log as fatal, don't retry
- **Impact**: Waste retry attempts on unrecoverable error

```python
# ❌ MISSING HANDLER:
elif e.errno == errno.EBADF:
    self.logger.error("Bad file descriptor - likely programming error")
    break  # Don't retry, exit immediately
```

#### 1.4.3: EACCES (Permission Denied)
- **Symptom**: FIFO exists but no write permission
- **Current Handling**: Generic error message
- **Should Do**: Log as fatal, don't retry
- **Impact**: Permission error will never succeed on retry

```python
# ❌ MISSING HANDLER:
elif e.errno == errno.EACCES:
    self.logger.error("Permission denied on FIFO - check permissions")
    break  # Don't retry
```

#### 1.4.4: ENOSPC (No Space Left)
- **Symptom**: Disk full or FIFO buffer full
- **Current Handling**: Only handles EAGAIN
- **Should Do**: Log warning, don't retry
- **Impact**: Retry loop wastes time on no-space condition

```python
# ❌ MISSING HANDLER:
elif e.errno == errno.ENOSPC:
    self.logger.error("No space available - disk or FIFO buffer full")
    break  # Don't retry
```

---

### 1.5 FIFO Recreation Race During Restart
**File**: `persistent_terminal_manager.py`  
**Lines**: 1204-1289 (restart_terminal)

```python
# Current flow:
def restart_terminal(self):
    # Close existing terminal
    _ = self.close_terminal()
    time.sleep(_TERMINAL_RESTART_DELAY_SECONDS)
    
    # Close dummy writer
    self._close_dummy_writer_fd()
    
    # Stop workers BEFORE FIFO cleanup ✅ FIXED
    with self._workers_lock:
        workers_to_stop = list(self._active_workers)
    
    for worker in workers_to_stop:
        if worker.isRunning():
            if not worker.safe_stop(3000):
                worker.safe_terminate()
    
    # Atomic FIFO replacement ✅ GOOD
    # Delete old FIFO
    if Path(self.fifo_path).exists():
        Path(self.fifo_path).unlink()
        # fsync parent directory ✅
    
    # Create temp FIFO and atomic rename ✅
```

**Status**: WELL-DESIGNED ✅

**Edge Case Not Covered**: What if FIFO parent directory doesn't exist?

```python
# Current code (lines 1218-1222):
# Ensure parent directory exists
parent_dir = Path(self.fifo_path).parent
parent_dir.mkdir(parents=True, exist_ok=True)  # ✅ Good

# But what if it fails?
# No try/except around this
```

**Could fail if**:
- Parent directory is read-only (permission denied)
- Parent path is on restricted filesystem
- Path traversal issues

**Better implementation**:
```python
try:
    parent_dir = Path(self.fifo_path).parent
    parent_dir.mkdir(parents=True, exist_ok=True)
except OSError as e:
    self.logger.error(f"Cannot create parent directory for FIFO: {e}")
    return False
```

---

### 1.6 Timeout Handling: No Maximum Bounds
**File**: `persistent_terminal_manager.py`  
**Lines**: Various timeout operations

```python
# Timeout constants:
_TERMINAL_RESTART_DELAY_SECONDS = 0.5  ✅
_DISPATCHER_STARTUP_TIMEOUT_SECONDS = 5.0  ✅
_HEARTBEAT_SEND_TIMEOUT_SECONDS = 3.0  ✅

# But check these operations:

# 1. Process wait in close_terminal (lines 1163-1202):
def close_terminal(self):
    if self._is_dispatcher_running():
        _ = self.send_command("EXIT_TERMINAL", ensure_terminal=False)
        time.sleep(_TERMINAL_RESTART_DELAY_SECONDS)  # Fixed delay
    
    if self._is_terminal_alive():
        os.kill(pid, signal.SIGTERM)
        time.sleep(_TERMINAL_RESTART_DELAY_SECONDS)  # Fixed delay
        if self._is_terminal_alive():
            os.kill(pid, signal.SIGKILL)
    
    # ❌ NO WAIT FOR PROCESS TO DIE
    # os.wait() or os.waitpid() never called
```

**Edge Case**: SIGKILL sent but process is zombie (parent not reaped it):
```
1. os.kill(pid, SIGKILL) succeeds
2. Process is terminated
3. Process becomes zombie (no parent reaped status)
4. _is_terminal_alive() uses os.kill(pid, 0) to check
5. Zombie process still responds to signal 0
6. _is_terminal_alive() returns True (false positive!)
7. Launcher tries to kill already-dead process
8. Zombie persists indefinitely
```

**Better implementation**:
```python
def close_terminal(self) -> bool:
    # ... send EXIT_TERMINAL ...
    
    if self._is_terminal_alive():
        pid = self.terminal_pid
        try:
            os.kill(pid, signal.SIGTERM)
            time.sleep(0.5)
            
            # Actually wait for process with timeout
            try:
                os.waitpid(pid, os.WNOHANG)  # Non-blocking reap
            except ChildProcessError:
                pass  # Already reaped
            
            if self._is_terminal_alive():
                os.kill(pid, signal.SIGKILL)
                time.sleep(0.1)
                # Try to reap zombie
                try:
                    os.waitpid(pid, os.WNOHANG)
                except ChildProcessError:
                    pass
        except ProcessLookupError:
            pass
```

---

### 1.7 Heartbeat File Timing Attack
**File**: `persistent_terminal_manager.py`  
**Lines**: 504-536 (_check_heartbeat)

```python
def _check_heartbeat(self) -> bool:
    try:
        heartbeat_file = Path(self.heartbeat_path)
        if not heartbeat_file.exists():
            return False
        
        content = heartbeat_file.read_text().strip()
        if not content or content != "PONG":
            return False
        
        mtime = heartbeat_file.stat().st_mtime
        age = time.time() - mtime  # ⚠️ Relies on system clock
        
        if age < self._heartbeat_timeout:  # Default 60s
            # Update last heartbeat timestamp
            with self._state_lock:
                self._last_heartbeat_time = mtime
            return True
        return False
    except Exception as e:
        self.logger.debug(f"Error checking heartbeat: {e}")
        return False
```

**Edge Case**: System clock adjustment
```
1. Dispatcher writes heartbeat at 10:00:00
2. File mtime = 10:00:00
3. System clock jumps backward to 09:59:00 (NTP correction)
4. Current time.time() = 09:59:00
5. age = 09:59:00 - 10:00:00 = negative!
6. age < 60 is True (even though heartbeat is ancient)
7. Dispatcher marked as healthy when actually stale
```

**Better implementation**:
```python
def _check_heartbeat(self) -> bool:
    try:
        heartbeat_file = Path(self.heartbeat_path)
        if not heartbeat_file.exists():
            return False
        
        content = heartbeat_file.read_text().strip()
        if not content or content != "PONG":
            return False
        
        mtime = heartbeat_file.stat().st_mtime
        current_time = time.time()
        age = current_time - mtime
        
        # Guard against negative age (clock skew)
        if age < 0:
            self.logger.warning(f"Negative heartbeat age ({age}s) - system clock may have changed")
            age = self._heartbeat_timeout + 1  # Treat as expired
        
        if age < self._heartbeat_timeout:
            with self._state_lock:
                self._last_heartbeat_time = mtime
            return True
        return False
    except Exception as e:
        self.logger.debug(f"Error checking heartbeat: {e}")
        return False
```

---

## PART 2: TIMEOUT & BLOCKING OPERATION ISSUES

### 2.0 Timeout Handling: No Timeout on Critical Waits
**Locations**: Various

#### Issue 2.0.1: process.wait() in Popen Without Timeout
**File**: `persistent_terminal_manager.py` (implicit, via subprocess)

```python
# Example: If we had explicit wait() call
proc = subprocess.Popen(terminal_cmd, start_new_session=True)

# ❌ MISSING: proc.wait() call to actually wait for process death
# Without wait(), process becomes zombie until parent process exits

# ✅ Should have:
try:
    proc.wait(timeout=2.0)
except subprocess.TimeoutExpired:
    proc.kill()
    proc.wait()
```

**Current workaround in close_terminal**:
- Uses `os.kill()` to send signals
- Uses `_is_terminal_alive()` to check if process died
- But doesn't actually reap the process with `wait()`/`waitpid()`

#### Issue 2.0.2: No Timeout on FIFO Operations
**File**: `persistent_terminal_manager.py`, various lines

```python
# In _ensure_fifo (lines 239-314):
os.mkfifo(self.fifo_path, 0o600)  # ⚠️ No timeout

# In _send_command_direct (lines 614-671):
fd = os.open(self.fifo_path, os.O_WRONLY | os.O_NONBLOCK)  # ✅ Non-blocking is good
with os.fdopen(fd, "wb", buffering=0) as fifo:
    _ = fifo.write(command.encode("utf-8"))  # ⚠️ Could block if buffer full

# In _launch_terminal (lines 673-799):
# Uses timeout-based polling loop ✅ Good pattern
while elapsed < timeout:
    if self._is_dispatcher_running():
        break
    time.sleep(poll_interval)
    elapsed += poll_interval
```

**Edge Case**: `fifo.write()` on FIFO with full buffer:
```
1. FIFO created with default buffer (64KB)
2. send_command() opens it with O_WRONLY | O_NONBLOCK
3. If buffer full, write() could fail with EAGAIN
4. Current code handles this with error message but no retry
```

Current implementation seems OK (non-blocking write), but edge cases exist.

---

### 2.1 Worker Cleanup Timeout Handling
**File**: `persistent_terminal_manager.py`  
**Lines**: 1323-1364 (cleanup), 937-1019 (send_command_async)

```python
# In cleanup() (lines 1323-1364):
for worker in workers_to_stop:
    if not worker.safe_stop(3000):  # 3 second timeout ✅
        self.logger.warning(...)
        worker.safe_terminate()

# In send_command_async cleanup (lines 980-990):
def cleanup_worker():
    with self._workers_lock:
        if worker in self._active_workers:
            self._active_workers.remove(worker)
    
    if not worker.safe_wait(3000):  # 3 second timeout ✅
        self.logger.warning(f"Worker did not finish in time")
        worker.safe_terminate()
```

**Status**: Timeout handling looks good ✅

**Potential Edge Case**: What if safe_wait(3000) times out during application shutdown?
```
1. Application is shutting down
2. cleanup() called on PersistentTerminalManager
3. Worker cleanup loop timeout expires
4. safe_terminate() called
5. Worker thread killed forcefully
6. deleteLater() scheduled but event loop may not process
7. Worker still in _active_workers if removal failed
8. Program tries to exit
9. Could cause segfault if worker thread still running
```

**Better implementation**:
```python
def cleanup(self):
    with self._workers_lock:
        workers_to_stop = list(self._active_workers)
    
    for worker in workers_to_stop:
        if not worker.safe_stop(3000):
            worker.safe_terminate()
        
        # Always wait, even if stop failed
        worker.wait()  # Blocking wait (can be longer than safe_wait)
        
        worker.disconnect_all()
        worker.deleteLater()
    
    with self._workers_lock:
        self._active_workers.clear()
```

---

## PART 3: EDGE CASES IN DISPATCHER/TERMINAL LIFECYCLE

### 3.0 Dispatcher PID Detection Unreliability
**File**: `persistent_terminal_manager.py`  
**Lines**: 421-468 (_find_dispatcher_pid)

```python
def _find_dispatcher_pid(self):
    # Get terminal process
    terminal_proc = psutil.Process(terminal_pid)
    
    # Look for bash child running dispatcher
    for child in terminal_proc.children(recursive=True):
        if "bash" not in child.name().lower():
            continue
        
        cmdline = child.cmdline()
        # Match against full path or basename
        if any(self.dispatcher_path in arg or dispatcher_name in arg for arg in cmdline):
            return child.pid
    
    return None
```

**Edge Cases**:

#### 3.0.1: Multiple Bash Processes
**Issue**: Terminal might spawn multiple bash processes
```
1. gnome-terminal launches bash -il dispatcher.sh
2. dispatcher.sh sources .bashrc which runs commands in bash subshells
3. Terminal has multiple bash processes
4. First one matching path name is returned
5. Could return wrong PID if dispatcher forks subshells
```

**Better matching**:
```python
# Use full command line matching, not just name/path containment
for child in terminal_proc.children(recursive=True):
    if "bash" not in child.name().lower():
        continue
    
    cmdline = child.cmdline()
    
    # Better: Check exact pattern
    # cmdline should be like: ['bash', '-il', '/path/to/dispatcher.sh', '/tmp/fifo']
    if (len(cmdline) >= 3 and
        cmdline[0] in ['bash', '/bin/bash'] and
        '-il' in cmdline and
        self.dispatcher_path in cmdline[-2:]):  # Should be one of last args
        return child.pid
```

#### 3.0.2: Dispatcher Spawned in Subshell
**Issue**: `ps aux` might not show exact dispatcher command
```
1. bash -il dispatcher.sh spawns dispatcher
2. Dispatcher writes `exec 3< $FIFO` to redirect FD
3. Process exec happens, bash is replaced
4. cmdline might become just the dispatcher script content
5. Path matching might fail
```

**Better approach**:
```python
# Instead of matching on cmdline, use:
# 1. Check if process has open FD for our FIFO
for child in terminal_proc.children(recursive=True):
    try:
        # Get open file descriptors
        fds = child.open_files()
        for fd_info in fds:
            if fd_info.path == self.fifo_path:
                return child.pid  # Process has our FIFO open
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
```

---

### 3.1 Terminal Emulator Selection Doesn't Validate Installation
**File**: `persistent_terminal_manager.py`  
**Lines**: 673-799 (_launch_terminal)

```python
# Current approach:
terminal_commands = [
    ["gnome-terminal", "--title=...", "--", "bash", "-il", ...],
    ["konsole", "--title", "...", "-e", "bash", "-il", ...],
    ["xterm", "-title", "...", "-e", "bash", "-il", ...],
    ["x-terminal-emulator", "-e", "bash", "-il", ...],
]

for cmd in terminal_commands:
    try:
        proc = subprocess.Popen(cmd, start_new_session=True)
        # ... success ...
    except FileNotFoundError:
        continue  # Try next emulator
```

**Edge Case**: What if terminal starts but dispatcher fails to run?
```
1. gnome-terminal starts successfully
2. bash process starts with dispatcher script
3. dispatcher script fails to execute (e.g., syntax error)
4. bash exits silently
5. _launch_terminal() returns True (terminal started)
6. But dispatcher_pid never found
7. Health checks fail repeatedly
8. Users think terminal is broken when it's just dispatcher script
```

**Better validation**:
```python
def _launch_terminal(self):
    # ... launch terminal ...
    
    # Wait for dispatcher to actually be running
    timeout = _DISPATCHER_STARTUP_TIMEOUT_SECONDS
    start = time.time()
    
    while time.time() - start < timeout:
        if self._is_dispatcher_running():
            return True  # Real success
        time.sleep(0.1)
    
    # Dispatcher never started
    self.logger.error("Terminal started but dispatcher never became ready")
    
    # Try to close terminal since it's not working
    self.close_terminal()
    return False
```

---

### 3.2 Dispatcher Script Error Handling
**File**: `terminal_dispatcher.sh`  
**Lines**: Various

```bash
# Good error handling in dispatcher:
trap handle_error ERR  # Catches errors
trap handle_exit EXIT  # Cleanup on exit

# But edge cases:

# 1. What if read from FIFO fails?
while read -r cmd <&3; do
    # ⚠️ If read fails (pipe broken), script exits
    # No recovery mechanism
done

# 2. What if command evaluation fails?
eval "$cmd"  # Could fail silently in subshell
result=$?    # Error code captured

# But if dispatcher itself has fatal error:
# No way for launcher to detect that eval() crashed dispatcher
```

**Better dispatcher error handling**:
```bash
# Current structure:
while read -r cmd <&3; do
    # Execute command
    eval "$cmd" 2>&1
    result=$?
done

# Better with error context:
while read -r cmd <&3 || {
    log_error "FIFO read failed"
    break
}; do
    if ! eval "$cmd" 2>&1; then
        log_error "Command failed: $cmd"
        # Don't exit, keep reading
        # Send error response back to launcher (optional)
    fi
done
```

---

### 3.3 FIFO Existing But No Reader
**File**: `persistent_terminal_manager.py`  
**Scenario**: Race condition where FIFO exists but dispatcher crashed

```python
# Scenario:
1. send_command("nuke") called
2. FIFO exists
3. _send_command_direct() opens FIFO with O_WRONLY | O_NONBLOCK
4. Write succeeds (no error)
5. But dispatcher is dead, FIFO never read
6. Next health check detects no reader
7. Restart triggered

# Current handling:
# - Retry loop in send_command() (lines 871-930)
# - Health check eventually detects via _send_heartbeat_ping()

# Status: ✅ Handled adequately
```

**Could be improved**: Explicit check if write actually succeeded and was read:
```python
def _send_command_direct(self, command):
    # After write succeeds:
    # Send heartbeat ping immediately after
    # If no response, assume command won't be read
    
    if not self._send_heartbeat_ping(timeout=0.5):
        # Dispatcher not reading
        self.logger.warning("Command sent but dispatcher not reading")
        return False  # Let caller know dispatcher unresponsive
```

---

## PART 4: CONCURRENT OPERATION EDGE CASES

### 4.0 Multiple Concurrent send_command() Calls
**File**: `persistent_terminal_manager.py`  
**Scenario**: GUI spawning 5 commands simultaneously

```python
# Scenario:
# Main thread calls: send_command("nuke a")
# Worker thread 1 calls: send_command_async("maya b")
# Worker thread 2 calls: send_command_async("3de c")
# Main thread calls: send_command("houdini d")

# How they interleave:
Thread 1 (main):
  ├─ Check fallback_mode (no lock) - reads stale value
  ├─ Validate command (no lock)
  ├─ Health check WITHOUT lock ← RACE HERE
  ├─ Acquire _write_lock
  └─ Write to FIFO

Thread 2 (worker):
  ├─ send_command_async spawns worker
  ├─ Worker calls _ensure_dispatcher_healthy()
  ├─ Gets _write_lock for FIFO operations
  └─ Writes to FIFO
```

**Edge Case**: Multiple health checks cause multiple terminal restarts
```
1. Dispatcher crashes
2. Thread 1 calls _ensure_dispatcher_healthy() - acquires lock
3. Starts restarting terminal
4. Thread 2 calls _ensure_dispatcher_healthy() - waits for lock
5. Lock released by thread 1
6. Thread 2 tries to restart AGAIN (already restarting!)
7. Duplicate restart attempts cascade
```

**Better implementation**:
```python
def _ensure_dispatcher_healthy(self):
    # Check if already healthy
    if self._is_dispatcher_healthy():
        return True
    
    # Use double-checked locking pattern
    with self._state_lock:
        if self._is_restarting:
            # Already restarting, wait for completion
            # Or return False to let caller retry
            return False
        
        self._is_restarting = True
    
    try:
        if not self.restart_terminal():
            return False
        
        # Wait for dispatcher to come up
        timeout = 5.0
        while timeout > 0:
            if self._is_dispatcher_healthy():
                return True
            time.sleep(0.1)
            timeout -= 0.1
        
        return False
    finally:
        with self._state_lock:
            self._is_restarting = False
```

---

### 4.1 Worker Thread Doesn't Respect Cancellation
**File**: `persistent_terminal_manager.py`  
**Lines**: 937-1019 (send_command_async), 75-87 (do_work)

```python
# In TerminalOperationWorker.do_work():
try:
    if self.operation == "send_command":
        self._run_send_command()
except Exception as e:
    self.operation_finished.emit(False, f"Operation failed: {e}")

# In _run_send_command():
if self.should_stop():
    return  # ✅ Checks cancellation
self.progress.emit(...)
if self.should_stop():
    return  # ✅ Checks again
if not self.manager._ensure_dispatcher_healthy():
    self.operation_finished.emit(False, "Terminal not healthy")
    return
if self.should_stop():
    return  # ✅ Checks again
if not self.manager._send_command_direct(self.command):
    self.operation_finished.emit(False, "Failed to send command")
```

**Status**: Good cancellation checks ✅

**Edge Case**: What if manager._ensure_dispatcher_healthy() is interrupted?
```
1. Worker calls _ensure_dispatcher_healthy()
2. This calls restart_terminal()
3. restart_terminal() sleeps for 0.5 seconds
4. User requests worker stop
5. should_stop() check can't happen (inside other method)
6. Worker blocks in sleep
7. Application shutdown hangs
```

**Better implementation**:
```python
def _run_send_command(self):
    if self.should_stop():
        return
    
    self.progress.emit(f"Sending command: {self.command[:50]}...")
    
    if self.should_stop():
        return
    
    # Set timeout on health check
    if not self.manager._ensure_dispatcher_healthy_with_timeout(timeout=2.0):
        # ✅ NEW: Timeout instead of blocking indefinitely
        self.operation_finished.emit(False, "Timeout ensuring dispatcher healthy")
        return
    
    if self.should_stop():
        return
    
    if not self.manager._send_command_direct(self.command):
        self.operation_finished.emit(False, "Failed to send command")
```

---

### 4.2 Signal Emission From Worker Thread
**File**: `persistent_terminal_manager.py`  
**Lines**: 937-1019, 75-87

```python
# In do_work() running in worker thread:
self.operation_finished.emit(success, message)

# In cleanup_worker() on main thread:
def cleanup_worker():
    # Remove from list
    with self._workers_lock:
        if worker in self._active_workers:
            self._active_workers.remove(worker)
    
    # Wait for worker
    if not worker.safe_wait(3000):
        worker.safe_terminate()
```

**Current implementation** (lines 957-963):
```python
# Connection uses QueuedConnection
_ = worker.operation_finished.connect(
    self._on_async_command_finished, Qt.ConnectionType.QueuedConnection
)

# ✅ GOOD: Explicit QueuedConnection prevents DirectConnection deadlocks
```

**Status**: Looks good ✅

---

## PART 5: SIGNAL/SLOT CONNECTION EDGE CASES

### 5.0 Signal Connection Cleanup Gaps
**File**: `command_launcher.py`, `launcher_manager.py`

#### 5.0.1: CommandLauncher Signal Cleanup
```python
# In CommandLauncher.__init__ (lines 101-139):
_ = self.process_executor.execution_started.connect(...)
_ = self.process_executor.execution_progress.connect(...)
_ = self.process_executor.execution_completed.connect(...)
_ = self.process_executor.execution_error.connect(...)

# In CommandLauncher.cleanup() (lines 150-181):
try:
    _ = self.process_executor.execution_started.disconnect(self._on_execution_started)
    _ = self.process_executor.execution_progress.disconnect(self._on_execution_progress)
    _ = self.process_executor.execution_completed.disconnect(self._on_execution_completed)
    _ = self.process_executor.execution_error.disconnect(self._on_execution_error)
except (RuntimeError, TypeError, AttributeError):
    pass

# ✅ FIXED: Now also calls process_executor.cleanup()
try:
    self.process_executor.cleanup()
except (RuntimeError, TypeError, AttributeError):
    pass
```

**Status**: Fixed ✅

#### 5.0.2: ProcessExecutor Signal Cleanup
```python
# In ProcessExecutor.__init__ (lines 64-89):
if self.persistent_terminal:
    _ = self.persistent_terminal.operation_progress.connect(self._on_terminal_progress)
    _ = self.persistent_terminal.command_result.connect(self._on_terminal_command_result)

# In ProcessExecutor.cleanup() (lines 287-311):
def cleanup(self):
    if self.persistent_terminal:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=RuntimeWarning, ...)
            try:
                _ = self.persistent_terminal.operation_progress.disconnect(self._on_terminal_progress)
                _ = self.persistent_terminal.command_result.disconnect(self._on_terminal_command_result)
            except (RuntimeError, TypeError):
                pass
```

**Status**: Looks good ✅

---

### 5.1 LauncherManager Signal Connection Fragility
**File**: `launcher_manager.py`  
**Lines**: 122-131

```python
def __init__(self, ...):
    # Try to connect ALL signals together
    try:
        _ = self._process_manager.process_started.connect(self.command_started)
        _ = self._process_manager.process_finished.connect(self.command_finished)
        _ = self._process_manager.process_error.connect(self.command_error)
        self._signals_connected = True
    except (AttributeError, RuntimeError) as e:
        self.logger.debug(f"Could not connect process manager signals: {e}")
        self._signals_connected = False  # ALL marked as failed
```

**Edge Case**: If second signal connection fails:
```
1. process_started.connect() - SUCCESS
2. process_finished.connect() - FAILS (signal doesn't exist)
3. Exception caught
4. self._signals_connected = False (even though first succeeded!)
5. In shutdown(), code assumes NO signals connected
6. First signal never disconnected
7. Memory leak: first signal still fires but handler might be destroyed
```

**Better implementation**:
```python
def __init__(self, ...):
    self._signal_connections: dict[str, bool] = {}
    
    # Try each signal individually
    for signal_name, handler_name in [
        ("process_started", "command_started"),
        ("process_finished", "command_finished"),
        ("process_error", "command_error"),
    ]:
        try:
            signal = getattr(self._process_manager, signal_name)
            handler = getattr(self, handler_name)
            _ = signal.connect(handler)
            self._signal_connections[signal_name] = True
        except (AttributeError, RuntimeError) as e:
            self.logger.debug(f"Could not connect {signal_name}: {e}")
            self._signal_connections[signal_name] = False

def shutdown(self):
    # Only disconnect signals that were connected
    for signal_name, was_connected in self._signal_connections.items():
        if was_connected:
            try:
                signal = getattr(self._process_manager, signal_name)
                _ = signal.disconnect()
            except (RuntimeError, TypeError, AttributeError):
                pass
```

---

## PART 6: RESOURCE EXHAUSTION EDGE CASES

### 6.0 No Maximum Worker Count
**File**: `persistent_terminal_manager.py`  
**Lines**: 937-1019 (send_command_async)

```python
def send_command_async(self, command):
    # Create worker
    worker = TerminalOperationWorker(self, "send_command", parent=None)
    
    # Store in list
    with self._workers_lock:
        self._active_workers.append(worker)  # ⚠️ No maximum!
    
    # Start thread
    worker.start()
```

**Edge Case**: Exhaustion scenario
```
1. User clicks "Launch nuke" 50 times rapidly
2. 50 workers created
3. All stored in _active_workers
4. Each worker spawns QThread
5. System runs out of threads (typical max: 1024)
6. New worker.start() fails with OSError
7. Application hangs or crashes
```

**Better implementation**:
```python
def send_command_async(self, command):
    MAX_WORKERS = 10
    
    with self._workers_lock:
        if len(self._active_workers) >= MAX_WORKERS:
            self.logger.warning(f"Too many active workers ({len(self._active_workers)})")
            self.command_result.emit(False, "Too many concurrent operations")
            return
        
        worker = TerminalOperationWorker(self, "send_command", parent=None)
        self._active_workers.append(worker)
    
    try:
        worker.start()
    except Exception as e:
        # Worker failed to start
        with self._workers_lock:
            if worker in self._active_workers:
                self._active_workers.remove(worker)
        self.command_result.emit(False, f"Failed to start worker: {e}")
        return
```

---

### 6.1 No Maximum Retry Count in send_command
**File**: `persistent_terminal_manager.py`  
**Lines**: 871-930

```python
max_retries = 2

for attempt in range(max_retries):
    try:
        # Attempt to open and write
    except OSError as e:
        if e.errno == errno.ENOENT:
            if attempt < max_retries - 1:
                if self._ensure_fifo():  # Recreate FIFO
                    time.sleep(_CLEANUP_POLL_INTERVAL_SECONDS)
                    continue  # RETRY
```

**Status**: Max 2 retries is reasonable ✅

**But edge case**: FIFO recreation could loop:
```
1. FIFO doesn't exist
2. Attempt 0: Recreate FIFO, retry
3. FIFO recreation succeeds but immediately disappears (race)
4. Attempt 1: Recreate FIFO again, retry
5. Same race happens again
6. Both retries exhausted
```

**Better implementation**:
```python
for attempt in range(max_retries):
    try:
        fifo_fd = os.open(self.fifo_path, os.O_WRONLY | os.O_NONBLOCK)
        # ... write ...
    except OSError as e:
        if e.errno == errno.ENOENT:
            if attempt < max_retries - 1:
                # Only recreate if FIFO actually missing
                if not Path(self.fifo_path).exists():
                    if self._ensure_fifo():
                        time.sleep(_CLEANUP_POLL_INTERVAL_SECONDS)
                        continue
                else:
                    # FIFO exists but can't open - permission issue
                    self.logger.error("FIFO exists but cannot be opened")
                    break
```

---

## PART 7: SUMMARY OF CRITICAL GAPS

### Missing Error Handling For:

1. **✅ ENXIO (No reader)** - Handled with retry
2. **✅ ENOENT (FIFO missing)** - Handled with recreation
3. **✅ EAGAIN (Buffer full)** - Handled with warning
4. **❌ EINTR (Interrupted)** - NOT handled (should retry)
5. **❌ EBADF (Bad FD)** - NOT handled (should fail fast)
6. **❌ EACCES (Permission denied)** - NOT handled (should fail fast)
7. **❌ ENOSPC (No space)** - NOT handled (should fail fast)
8. **❌ EIO (I/O error)** - NOT handled (generic handler)
9. **❌ EPIPE (Broken pipe)** - NOT handled (should retry)

### Missing Edge Case Handling For:

1. **Worker thread exhaustion** - No maximum worker count
2. **Fallback mode auto-reset** - ✅ Now fixed
3. **Race condition in send_command** - ⚠️ Partially mitigated
4. **Zombie process reaping** - No explicit waitpid()
5. **System clock skew** - Negative heartbeat age possible
6. **Multiple concurrent restarts** - Could cascade
7. **Dispatcher PID detection** - Could match wrong process
8. **Signal connection partial failure** - All-or-nothing approach
9. **Terminal emulator validation** - Doesn't verify dispatcher started

### Missing Timeout Handling For:

1. **Process wait() in close_terminal()** - No explicit wait with timeout
2. **FIFO operations** - Non-blocking but no operation timeout
3. **Worker cleanup on shutdown** - Has timeout ✅
4. **_ensure_dispatcher_healthy in worker** - Could block indefinitely
5. **Health check retries** - No backoff, immediate retry

---

## CONCLUSION

The launcher/terminal system has:
- **Good foundation** with most critical paths handled
- **Recent fixes** for fallback mode and ProcessExecutor cleanup
- **Remaining gaps** in error recovery for specific errno values
- **Resource exhaustion** protection could be better
- **Timeout handling** mostly adequate with minor gaps
- **Concurrent operation** race conditions partially mitigated

**Production readiness**: **MEDIUM** - Works for normal cases, but edge cases under stress conditions need hardening.

