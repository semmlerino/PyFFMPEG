# PersistentBashSession Pytest Timeout Fix

## Problem
The `PersistentBashSession.execute()` method's timeout recovery mechanism was hanging when run through pytest but worked correctly in standalone Python scripts. The specific test `test_session_timeout_handling` would hang indefinitely in pytest environments.

## Root Cause
The issue was caused by `select.select()` not working reliably in pytest environments due to:

1. **I/O Redirection**: Pytest captures stdout/stderr which can interfere with select() on subprocess file descriptors
2. **File Descriptor Wrapping**: Pytest may wrap file descriptors in ways that break select.select()
3. **Terminal Detection**: Different TTY detection in pytest vs standalone execution

The problematic code was using `select.select()` to poll for data availability:
```python
ready, _, _ = select.select([self._process.stdout], [], [], min(0.1, remaining_time))
```

## Solution
Replaced the `select.select()` approach with non-blocking I/O:

1. **Set stdout to non-blocking mode** after creating the subprocess:
```python
# Set stdout to non-blocking mode to avoid hanging in pytest
if hasattr(os, 'set_blocking'):
    os.set_blocking(self._process.stdout.fileno(), False)
else:
    # Fallback for older Python
    import fcntl
    fd = self._process.stdout.fileno()
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
```

2. **Use non-blocking reads** instead of select():
```python
try:
    # Read available data
    chunk = self._process.stdout.read(4096)
    if chunk:
        buffer += chunk
        # Process complete lines...
except (IOError, OSError) as e:
    # EAGAIN means no data available (expected for non-blocking)
    import errno
    if e.errno != errno.EAGAIN:
        raise
```

3. **Changed buffering mode** from unbuffered to line-buffered:
```python
bufsize=1,  # Line buffered instead of unbuffered
```

## Key Changes Made

### process_pool_manager.py
1. Added `import fcntl` for non-blocking I/O support
2. Changed subprocess creation to use line buffering (`bufsize=1`)
3. Set stdout to non-blocking mode after process creation
4. Replaced select.select() loop with non-blocking read loop
5. Added proper handling for EAGAIN errno (no data available)
6. Added small sleep (0.01s) to avoid busy waiting

## Benefits
- **Pytest Compatibility**: Tests now run correctly in pytest environments
- **More Robust**: Non-blocking I/O is more portable across different environments
- **Better Error Handling**: Clearer error messages and recovery paths
- **Performance**: Small sleep prevents CPU spinning while waiting for data

## Test Results
- `test_session_timeout_handling` now passes in ~8 seconds (expected behavior)
- Session properly recovers after timeout
- No regression in standalone execution
- Compatible with both pytest and normal Python execution

## Files Modified
- `/mnt/c/CustomScripts/Python/PyFFMPEG/BB/shotbot/process_pool_manager.py`

## Original Behavior
- Standalone: ✅ Worked correctly
- Pytest: ❌ Hung indefinitely

## Fixed Behavior
- Standalone: ✅ Still works correctly
- Pytest: ✅ Now works correctly
