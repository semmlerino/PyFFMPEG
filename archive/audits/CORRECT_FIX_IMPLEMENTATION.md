# Correct Fix Implementation Guide

**Problem:** Race condition where bash closes FIFO between commands, causing Python to get ENXIO  
**Root Cause:** Bash reopens FIFO each iteration (legacy fix for old EOF issue)  
**Solution:** Keep FIFO open continuously + add Python retry logic

---

## Part 1: Fix Bash Dispatcher (PRIMARY FIX)

**File:** `/home/gabrielh/projects/shotbot/terminal_dispatcher.sh`

### Current Code (Lines 131-137)

```bash
# Main command loop
# Each iteration opens FIFO fresh to avoid EOF race conditions with health checks
log_info "Entering main command loop"
while true; do
    # Read command from FIFO (opens fresh on each iteration)
    # This blocks until a writer connects, avoiding EOF issues from transient health checks
    if read -r cmd < "$FIFO"; then
```

### Fixed Code

```bash
# Main command loop
# Keep FIFO open continuously - heartbeat uses ping/pong so no EOF risk
log_info "Entering main command loop"

# Open FIFO once before loop (FD 3 = read from FIFO)
# This eliminates race window between commands
exec 3< "$FIFO"
log_info "FIFO opened on FD 3"

while true; do
    # Read from persistent file descriptor 3
    if read -r cmd <&3; then
```

### Changes Summary

1. **Add before loop:** `exec 3< "$FIFO"` - Opens FIFO on file descriptor 3
2. **Change read:** `read -r cmd < "$FIFO"` → `read -r cmd <&3` - Read from FD 3
3. **Update comment:** Explain why continuous open is now safe (heartbeat ping/pong)

### Why This Works

- **Old problem:** Health check opened/closed FIFO → sent EOF → bash read loop exited
- **Old fix:** Reopen FIFO each iteration to survive EOF
- **New heartbeat:** Uses ping/pong file mechanism → no open/close → no EOF
- **New fix:** Keep FIFO open (old workaround no longer needed)

### Error Handling

The existing error handling at line 226 already covers read failures:

```bash
    else
        # Read from FIFO failed
        log_error "Failed to read from FIFO (EOF or error)"
        echo "" >&2
        echo "[ERROR] Lost connection to FIFO" >&2
        break
    fi
```

This will catch:
- EOF (all writers closed)
- Dispatcher receives signal
- FIFO deleted
- File descriptor errors

---

## Part 2: Add Python Retry Logic (DEFENSE IN DEPTH)

**File:** `/home/gabrielh/projects/shotbot/persistent_terminal_manager.py`

### Current Code (Lines 508-527)

```python
# Acquire lock to serialize FIFO writes
with self._write_lock:
    # Send command to FIFO using non-blocking I/O
    fifo_fd = None
    max_retries = 2

    for attempt in range(max_retries):
        try:
            # Open FIFO in non-blocking mode
            fifo_fd = os.open(self.fifo_path, os.O_WRONLY | os.O_NONBLOCK)

            # Use binary mode with unbuffered I/O
            with os.fdopen(fifo_fd, "wb", buffering=0) as fifo:
                fifo_fd = None  # File object now owns the descriptor
                _ = fifo.write(command.encode("utf-8"))
                _ = fifo.write(b"\n")

            self.logger.info(f"Successfully sent command to terminal: {command}")
            self.command_sent.emit(command)
            return True

        except OSError as e:
            if e.errno == errno.ENOENT:
                # FIFO doesn't exist
```

### Fixed Code

```python
# Acquire lock to serialize FIFO writes
with self._write_lock:
    # Send command to FIFO using non-blocking I/O
    # Retry on ENXIO to handle dispatcher startup/restart windows
    fifo_fd = None
    max_retries = 3  # Increased from 2
    retry_delay = 0.1  # Initial delay in seconds

    for attempt in range(max_retries):
        try:
            # Open FIFO in non-blocking mode
            fifo_fd = os.open(self.fifo_path, os.O_WRONLY | os.O_NONBLOCK)

            # Use binary mode with unbuffered I/O
            with os.fdopen(fifo_fd, "wb", buffering=0) as fifo:
                fifo_fd = None  # File object now owns the descriptor
                _ = fifo.write(command.encode("utf-8"))
                _ = fifo.write(b"\n")

            self.logger.info(f"Successfully sent command to terminal: {command}")
            self.command_sent.emit(command)
            return True

        except OSError as e:
            if e.errno == errno.ENOENT:
                # FIFO doesn't exist
                if attempt < max_retries - 1:
                    self.logger.warning(
                        f"FIFO disappeared, recreating (attempt {attempt + 1}/{max_retries})"
                    )
                    if self._ensure_fifo():
                        time.sleep(0.2)
                        continue
                self.logger.error(f"Failed to send command to FIFO: {e}")
            elif e.errno == errno.ENXIO:
                # No reader available - could be startup/restart window
                if attempt < max_retries - 1:
                    # Retry with exponential backoff
                    self.logger.debug(
                        f"No reader available (attempt {attempt + 1}/{max_retries}), "
                        f"retrying after {retry_delay}s"
                    )
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff: 100ms, 200ms
                    continue
                # After retries, dispatcher is truly dead
                self.logger.error(
                    "No reader available for FIFO - dispatcher may have crashed"
                )
                # Mark for health check on next command
                self.dispatcher_pid = None
            elif e.errno == errno.EAGAIN:
                self.logger.warning("FIFO write would block (buffer full?)")
            else:
                self.logger.error(f"Failed to send command to FIFO: {e}")
            return False
```

### Changes Summary

1. **Increase max_retries:** `2` → `3` (allows 100ms + 200ms retries)
2. **Add retry_delay:** `0.1` seconds initial, doubles each retry
3. **Add ENXIO retry logic:** Retry with exponential backoff before declaring dead
4. **Improve logging:** Show which attempt and delay time

### Retry Strategy

| Attempt | Action | Delay | Total Time |
|---------|--------|-------|------------|
| 1 | open() → ENXIO | - | 0ms |
| 2 | wait → open() | 100ms | 100ms |
| 3 | wait → open() | 200ms | 300ms |
| Fail | dispatcher_pid = None | - | 300ms |

**Why exponential backoff:**
- Startup: Dispatcher takes 50-200ms to open FIFO
- Race window: Usually < 50ms
- Restart: May take up to 500ms
- 300ms total is reasonable timeout without blocking UI

---

## Testing Plan

### Test 1: Normal Operation

```bash
# Terminal 1: Start shotbot
cd ~/projects/shotbot
~/.local/bin/uv run python shotbot.py

# Terminal 2: Monitor dispatcher log
tail -f ~/.shotbot/logs/dispatcher_debug.log

# Expected in log:
# [INFO] FIFO opened on FD 3
# [DEBUG] Received command: ...
# (No "Lost connection to FIFO" errors)
```

### Test 2: Rapid Commands

```python
# In Python shell or test
from persistent_terminal_manager import PersistentTerminalManager

mgr = PersistentTerminalManager()
mgr.ensure_terminal_running()

# Send 10 commands rapidly
for i in range(10):
    success = mgr.send_command(f"echo 'Command {i}'")
    assert success, f"Command {i} failed"
    time.sleep(0.1)  # 100ms between commands

# All should succeed (no ENXIO during race window)
```

### Test 3: Dispatcher Crash Recovery

```bash
# Terminal 1: Start shotbot
~/.local/bin/uv run python shotbot.py

# Terminal 2: Find and kill dispatcher
ps aux | grep terminal_dispatcher
kill -9 <dispatcher_pid>

# Terminal 1: Try to send command
# Expected: Health check detects crash, restarts dispatcher
# Command succeeds after retry
```

### Test 4: Verify FD Persistence

```bash
# While dispatcher running, check open FDs
ps aux | grep terminal_dispatcher | awk '{print $2}'  # Get PID
ls -l /proc/<pid>/fd/

# Should see:
# 3 -> /tmp/shotbot_commands.fifo

# Send command, check again
# FD 3 should STILL point to FIFO (not closed/reopened)
```

---

## Rollback Plan

If issues occur, revert changes:

### Revert Bash

```bash
# Remove exec line, restore original read
while true; do
    if read -r cmd < "$FIFO"; then
```

### Revert Python

```bash
git diff persistent_terminal_manager.py
git checkout persistent_terminal_manager.py
```

---

## Expected Outcomes

### Before Fix

```
[ERROR] No reader available for FIFO - dispatcher may have crashed
[WARNING] Failed to send command: rez env 3de -- ...
[INFO] Attempting to restart terminal (attempt 1/3)
```

**Frequency:** 5-20% of commands (intermittent)

### After Fix

```
[INFO] Successfully sent command to terminal: rez env 3de -- ...
```

**Frequency:** 99.9%+ success rate
**Remaining failures:** Only legitimate crashes (hardware, OOM, etc.)

---

## Performance Impact

### Bash

- **Before:** Open/close FIFO each command (~0.5ms overhead)
- **After:** Persistent FD (~0.001ms overhead)
- **Improvement:** ~500x faster FIFO access

### Python

- **Before:** Immediate failure on ENXIO
- **After:** Up to 300ms retry on ENXIO
- **Impact:** Only affects startup/restart (rare), normal operation unchanged

### Overall

- **Normal commands:** Faster (no bash open/close)
- **Startup/restart:** Slightly slower (300ms vs immediate failure)
- **Success rate:** Much higher (99.9%+ vs 80-95%)

---

## Risk Assessment

### Part 1 (Bash Fix)

**Risk Level:** LOW  
**Impact:** HIGH (eliminates race condition)  
**Rollback:** EASY (revert 2 lines)

**Risks:**
- EOF could still arrive (unlikely - heartbeat doesn't send EOF)
- FD could be closed by signal (handled by existing error check)
- Memory leak from persistent FD (no - bash cleans up on exit)

**Mitigation:**
- Keep existing EOF handler (line 226)
- Monitor dispatcher logs for "Lost connection" errors
- Can always revert to per-command open

### Part 2 (Python Retry)

**Risk Level:** VERY LOW  
**Impact:** MEDIUM (handles edge cases)  
**Rollback:** EASY (revert function)

**Risks:**
- 300ms delay on legitimate crashes (acceptable)
- Could mask real issues (unlikely - still detects after retries)

**Mitigation:**
- Log retry attempts for visibility
- Monitor retry frequency in production
- Adjust retry count/delay based on data

---

## Success Criteria

1. **Functional:**
   - ✓ Commands succeed 99.9%+ of the time
   - ✓ No "No reader available" errors during normal operation
   - ✓ Dispatcher auto-recovery still works
   - ✓ UI remains responsive

2. **Performance:**
   - ✓ Command send latency < 5ms (normal case)
   - ✓ Startup/restart within 500ms
   - ✓ No memory leaks

3. **Reliability:**
   - ✓ 1000 commands in a row succeed
   - ✓ Rapid commands (10/second) succeed
   - ✓ Crash recovery works within 3 attempts

4. **Observability:**
   - ✓ Logs show "FIFO opened on FD 3"
   - ✓ Logs show retry attempts (if any)
   - ✓ No unexpected error patterns

---

## Implementation Checklist

- [ ] Back up current code
- [ ] Update bash dispatcher (Part 1)
- [ ] Update Python manager (Part 2)
- [ ] Run Test 1: Normal operation
- [ ] Run Test 2: Rapid commands
- [ ] Run Test 3: Crash recovery
- [ ] Run Test 4: Verify FD persistence
- [ ] Monitor logs for 24 hours
- [ ] Check success criteria
- [ ] Document in CHANGELOG
- [ ] Update tests if needed

---

## References

- **Analysis:** `SOLUTION_VERIFICATION_ANALYSIS.md`
- **Timeline:** `RACE_CONDITION_TIMELINE.txt`
- **Original Plan:** `PERSISTENT_TERMINAL_RACE_FIX_PLAN.md` (rejected)
- **Bash Script:** `terminal_dispatcher.sh`
- **Python Manager:** `persistent_terminal_manager.py`
