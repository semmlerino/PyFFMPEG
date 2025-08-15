# Shotbot Startup Hang Fix

## Problem Description
The Shotbot application was hanging immediately after boot on Linux. The application would freeze after creating a persistent bash session, showing only:
```
Created session workspace_0 in pool
```
Then requiring termination with Ctrl+C or kill.

## Root Cause Analysis

### 1. **Pipe Buffer Deadlock in PersistentBashSession**
The primary issue was in `process_pool_manager.py` in the `PersistentBashSession._start_session()` method:
- After starting bash subprocess with pipes, the code wrote `export PS1=''` to stdin
- Then called `time.sleep(0.2)` without reading stdout
- If bash produced any output (startup messages, errors, prompts), it filled the stdout pipe buffer
- When the pipe buffer became full, bash blocked waiting for someone to read
- Python was sleeping and not reading, creating a **deadlock**

### 2. **Immediate Background Refresh Trigger**
The `BackgroundRefreshWorker` in `main_window.py`:
- Started immediately after MainWindow initialization
- After 2 seconds, triggered `refresh_shots()` which called ProcessPoolManager
- This created the first bash session that would hang

## Applied Fixes

### Fix 1: Drain stdout to Prevent Deadlock
**File:** `process_pool_manager.py`
**Location:** `PersistentBashSession._start_session()` method (around line 254-300)

**Changes:**
- Added proper stdout draining after sending initialization commands
- For systems with `fcntl` (Linux/Unix): Use non-blocking I/O with select to drain output
- For systems without `fcntl`: Send a marker command and read until found
- Prevents pipe buffer from filling and causing deadlock

```python
# CRITICAL FIX: Drain any startup output to prevent deadlock
if self._process.stdout:
    try:
        if HAS_FCNTL:
            # Non-blocking read to drain any startup output
            import select
            ready, _, _ = select.select([self._process.stdout], [], [], 0.1)
            if ready:
                chunk = self._process.stdout.read(4096)
                if chunk:
                    logger.debug(f"Drained {len(chunk)} bytes of startup output")
        else:
            # For systems without fcntl, send marker and read until found
            marker = f"SHOTBOT_READY_{uuid.uuid4().hex[:8]}"
            self._process.stdin.write(f"echo '{marker}'\n")
            self._process.stdin.flush()
            # Read until marker found or timeout
```

### Fix 2: Delay Background Refresh Worker
**File:** `main_window.py`
**Location:** Line 128 in `MainWindow.__init__()`

**Changes:**
- Changed from immediate start to delayed start using QTimer
- Gives UI 5 seconds to fully initialize before background operations
- Prevents race conditions during startup

```python
# Before:
self._background_refresh_worker.start()

# After:
# Delay background refresh to avoid startup conflicts
QTimer.singleShot(5000, self._background_refresh_worker.start)
```

## Testing

Created test script `test_pool_fix_complete.py` that verifies:
1. ProcessPoolManager initializes without hanging
2. Commands execute successfully
3. Caching works properly
4. Clean shutdown

Test results show:
- ✅ No hanging during initialization
- ✅ Bash sessions created successfully
- ✅ Commands execute and return results
- ✅ Cache hits working
- ✅ Clean shutdown (with proper process termination)

## Additional Improvements

1. **Better error handling** in stdout draining - continues even if drain fails
2. **Debug logging** added to track startup sequence
3. **Timeout protection** on marker reading to prevent infinite loops
4. **Reduced sleep time** from 0.2s to 0.05s for faster startup

## Impact

These fixes resolve:
- Application hanging on Linux startup
- Deadlock in subprocess communication
- Race conditions during initialization
- Improved startup time and reliability

## Files Modified

1. `/mnt/c/CustomScripts/Python/PyFFMPEG/BB/shotbot/process_pool_manager.py`
2. `/mnt/c/CustomScripts/Python/PyFFMPEG/BB/shotbot/main_window.py`

## Verification

To verify the fix works:
```bash
python3 shotbot.py
# Application should start without hanging
# Check logs for successful session creation
```

Or run the test script:
```bash
python3 test_pool_fix_complete.py
# Should show all tests passing
```
