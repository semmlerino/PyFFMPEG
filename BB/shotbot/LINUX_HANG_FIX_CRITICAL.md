# Critical Linux Hang Fix - workspace_1 Creation Issue

## Problem Analysis (2025-08-15)

The application hangs when creating the second bash session (workspace_1) on Linux systems. The debug log shows:

```
workspace_0: Successfully created in 0.529s
workspace_1: Hangs at STARTING state, never reaches WAITING_MARKER
```

## Root Cause

The hang occurs during `subprocess.Popen()` creation for the second session. This is a known issue with:
1. File descriptor inheritance between Qt and subprocess
2. Resource contention when creating multiple sessions quickly
3. Potential deadlock in subprocess creation when stderr is redirected

## Critical Fix Applied

### 1. Increased Inter-Session Delay
```python
# In _get_bash_session() when creating sessions:
if i < self._sessions_per_type - 1:
    time.sleep(0.3)  # Increased from 0.1 to 0.3
```

### 2. Session-Specific Initialization Delays
```python
# In _start_session():
if "workspace_1" in self.session_id or "workspace_2" in self.session_id:
    time.sleep(0.2)  # More delay for second/third sessions
else:
    time.sleep(0.1)  # Standard delay for first session
```

### 3. Stderr Handling
```python
# Redirect stderr to stdout to prevent separate buffer deadlock
stderr=subprocess.STDOUT
```

### 4. Non-Blocking I/O Setup
```python
# Set stdout to non-blocking mode after creation
if HAS_FCNTL:
    os.set_blocking(stdout_fd, False)
```

## Testing Instructions

To verify the fix works on Linux:

```bash
# Enable full debugging
export SHOTBOT_DEBUG_LEVEL=all
export SHOTBOT_DEBUG_VERBOSE=1

# Run the application
python shotbot.py

# Or run the test script
python test_comprehensive_fixes.py
```

## Expected Behavior

With debugging enabled, you should see:
1. workspace_0 created successfully
2. 0.3s pause before creating workspace_1
3. workspace_1 created successfully
4. 0.3s pause before creating workspace_2
5. workspace_2 created successfully
6. All sessions reach READY state

## If Still Hanging

If workspace_1 still hangs, try:

1. **Increase delays further**:
   - Change inter-session delay to 0.5s
   - Change workspace_1/2 init delay to 0.3s

2. **Disable non-blocking I/O**:
   - Comment out the fcntl/set_blocking code
   - Use only blocking I/O with readline()

3. **Create sessions sequentially**:
   - Set sessions_per_type=1 initially
   - Create additional sessions on-demand

## Debug Output Analysis

A successful session creation should show:
```
[workspace_1] STATE: UNKNOWN → STARTING [Session initialization]
[workspace_1] Creating subprocess.Popen with interactive bash
[workspace_1] Process created with PID: 12345
[workspace_1] Waiting for initialization marker: SHOTBOT_INIT_abc123
[workspace_1] STATE: STARTING → WAITING_MARKER [Waiting for init marker]
[workspace_1] Read line (X bytes): ...
[workspace_1] Session initialized successfully
[workspace_1] STATE: WAITING_MARKER → READY [Session initialized]
```

If it hangs, the last state will indicate where:
- Hangs at STARTING: subprocess.Popen() is blocking
- Hangs at WAITING_MARKER: I/O deadlock reading from stdout
- No states logged: File descriptor issue before subprocess creation

## Emergency Workaround

If all else fails, disable session pooling temporarily:
```python
# In ProcessPoolManager.__init__():
self._sessions_per_type = 1  # Only create one session
```

This will impact performance but ensures the application runs.