# Linux Startup Hang Fix - Final Solution

## Problem
ShotBot was hanging on Linux when creating the second bash session (`workspace_1`) during ProcessPoolManager initialization. The hang occurred specifically during the "draining initial bash output" phase.

## Root Cause
The draining operation was using `read(1024)` which blocks waiting for exactly 1024 bytes of data. When bash's initial output was less than 1024 bytes, the read would block indefinitely, causing the hang.

## Solution
1. **Removed problematic draining code** - The initial output draining was causing more problems than it solved
2. **Simplified initialization** - Added a small 50ms delay to let bash initialize
3. **Use readline() instead of read()** - readline() returns as soon as a complete line is available, preventing blocking
4. **Accumulate output** - Store all output to search for the initialization marker

## Key Changes

### Before (Problematic):
```python
# Draining with blocking read
while time.time() - drain_start < 0.2:
    ready, _, _ = select.select([self._process.stdout], [], [], 0.01)
    if ready:
        chunk = self._process.stdout.read(1024)  # BLOCKS if < 1024 bytes!
```

### After (Fixed):
```python
# Simple delay instead of draining
time.sleep(0.05)

# Use readline() in the main loop
if ready:
    line = self._process.stdout.readline()  # Returns when line is complete
    if line:
        accumulated_output += line
        if marker in accumulated_output:
            found_marker = True
```

## Files Modified
- `process_pool_manager.py` - Fixed session initialization logic

## Testing
Run the test script to verify no hanging:
```bash
python test_session_creation.py
```

Or test the full application:
```bash
SHOTBOT_DEBUG_VERBOSE=1 python shotbot.py
```

## Additional Improvements
- Added verbose debug logging to track initialization progress
- Increased session creation delay from 0.1s between sessions
- Better error reporting with exit codes

## Verification Checklist
- [x] Removed blocking read operations
- [x] Simplified initialization sequence  
- [x] Added proper debug logging
- [x] Created test scripts
- [x] Documented the fix