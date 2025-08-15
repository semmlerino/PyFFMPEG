# File Descriptor Inheritance Fix for Linux Subprocess Hang

## Critical Issue Resolved (2025-08-15)

### Problem
The application was hanging when creating the second bash session (`workspace_1`) on Linux systems. The hang occurred during the `subprocess.Popen()` call itself, not during initialization.

### Root Cause
**File Descriptor Inheritance**: When Qt creates the subprocess without `close_fds=True`, all file descriptors from the parent process (including Qt's internal event loop FDs) are inherited by the child process. This causes a deadlock when creating the second subprocess because:

1. Qt has internal file descriptors for its event loop
2. First subprocess (workspace_0) inherits these FDs
3. When creating second subprocess (workspace_1), the fork() system call tries to duplicate FDs
4. This creates a deadlock between Qt's event loop and subprocess creation

### The Fix
Added three critical parameters to `subprocess.Popen()`:

```python
self._process = subprocess.Popen(
    ["/bin/bash", "-i"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1,
    env=os.environ.copy(),
    # CRITICAL Linux fixes
    close_fds=True,          # Close all FDs except stdin/stdout/stderr
    start_new_session=True,  # Create new process group (POSIX only)
    restore_signals=True,    # Reset signal handlers to defaults
)
```

### Why Each Parameter Matters

1. **`close_fds=True`** (MOST IMPORTANT)
   - Closes all file descriptors except stdin, stdout, stderr before exec
   - Prevents Qt's internal FDs from being inherited
   - This is THE critical fix for the deadlock

2. **`start_new_session=True`**
   - Creates a new session and process group
   - Isolates the subprocess from the parent's process group
   - Safer than using `preexec_fn=os.setsid` in threaded environments
   - Only works on POSIX systems (ignored on Windows)

3. **`restore_signals=True`**
   - Resets all signal handlers to default values
   - Prevents Qt's custom signal handlers from interfering
   - Important for proper SIGCHLD handling

## Testing the Fix

Run the test script to verify:
```bash
python test_fd_inheritance_fix.py
```

Expected output:
```
✅ Session test_workspace_0 created in 0.XXXs
✅ Session test_workspace_1 created in 0.XXXs  # <-- This was hanging before
✅ Session test_workspace_2 created in 0.XXXs
✅ ALL TESTS PASSED - FD inheritance fix is working!
```

## Platform Compatibility

- **Linux**: All three parameters work and fix the issue
- **macOS**: Parameters work (POSIX compliant)
- **Windows**: `start_new_session` and `restore_signals` are ignored (no harm)

## Debug Evidence

Before fix (hanging at workspace_1):
```
[workspace_0] STATE: UNKNOWN → STARTING → WAITING_MARKER → READY ✓
[workspace_1] STATE: UNKNOWN → STARTING [hangs here forever] ✗
```

After fix:
```
[workspace_0] STATE: UNKNOWN → STARTING → WAITING_MARKER → READY ✓
[workspace_1] STATE: UNKNOWN → STARTING → WAITING_MARKER → READY ✓
[workspace_2] STATE: UNKNOWN → STARTING → WAITING_MARKER → READY ✓
```

## Technical Background

### Why Qt + subprocess = problems on Linux

1. Qt applications use an event loop with internal file descriptors
2. These FDs include:
   - Event notification pipes
   - Timer FDs
   - Signal handling FDs
   - X11/Wayland connection sockets

3. When `fork()` is called without `close_fds=True`:
   - Child process inherits ALL parent FDs
   - Child tries to duplicate Qt's event loop FDs
   - Parent Qt event loop and child process deadlock

### The fork() + exec() dance

On Linux, `subprocess.Popen()` uses:
1. `fork()` - Creates child process (inherits everything)
2. Between fork and exec - Critical moment where FDs matter
3. `exec()` - Replaces child process with new program

The deadlock happens in step 2 if FDs aren't closed.

## References

- [Python subprocess documentation on close_fds](https://docs.python.org/3/library/subprocess.html#subprocess.Popen)
- [Qt and fork() issues](https://doc.qt.io/qt-6/qprocess.html#fork-safety)
- [Linux file descriptor inheritance](https://man7.org/linux/man-pages/man2/fork.2.html)

## Summary

**One line fix**: Add `close_fds=True` to subprocess.Popen()
**Result**: No more hanging on Linux when creating multiple subprocesses from Qt applications