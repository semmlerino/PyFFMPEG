# Crash Fix Summary - App Relaunch Issue (Simplified)

## Problem Description
Apps were crashing when launching, closing, and relaunching them. The console showed `[3]+ Stopped` messages, indicating process suspension issues.

## Root Causes Identified

1. **Process Group Signal Propagation**: Child processes weren't isolated from parent, causing signal interference
2. **Pipe Buffer Deadlocks**: GUI apps' stdout/stderr were piped, causing deadlocks when apps closed their streams
3. **Terminal Detachment**: GUI apps weren't properly detached from the launching process
4. **Worker Thread Issues**: Worker threads were trying to read output from GUI apps that don't produce console output

## Implemented Solution - Simplified Approach

### Key Decision: Treat ALL Apps as GUI Apps
Rather than trying to detect which apps are GUI vs CLI, we now treat **ALL launched applications as GUI apps**. This eliminates detection complexity and prevents any possibility of deadlocks.

### LauncherWorker Improvements (`launcher_manager.py`)

#### Unified Process Handling
- **ALL Apps**: Use `subprocess.DEVNULL` for stdout/stderr (no output capture)
- **ALL Apps**: Use `start_new_session=True` for process isolation
- **No Detection Logic**: Removed ~100 lines of GUI detection code
- **Single Code Path**: One execution path for all applications

### Terminal Launch Support
Apps can still specify `launcher.terminal.required = True` to launch in a terminal window:
```python
terminal_commands = [
    ["gnome-terminal", "--", "bash", "-i", "-c", command],
    ["xterm", "-e", f"bash -i -c '{command}'"],
    ["konsole", "-e", "bash", "-i", "-c", command],
]
```

### Enhanced Worker Cleanup
- Disconnects signals to prevent memory leaks
- Handles stuck workers (not running but not finished)
- Uses `deleteLater()` for proper Qt cleanup
- More robust error handling

## Files Modified

1. **`launcher_manager.py`**:
   - Removed GUI detection methods (`_is_gui_command`, `_detect_gui_command`)
   - Simplified `LauncherWorker.run()` to single execution path
   - All processes use DEVNULL and start_new_session
   - Removed `command_output` signal (never used with DEVNULL)
   - Cleaner, more maintainable code

2. **`test_crash_fix.py`**:
   - Updated to reflect unified app handling
   - Removed GUI/CLI distinction in tests

## How the Fix Works

### Simplified Process Flow
1. App launch requested
2. If `terminal.required=True`: Launch in terminal window
3. Otherwise: Use worker thread with DEVNULL for stdout/stderr
4. Process isolation with `start_new_session=True` prevents signal issues
5. No output capture attempts = no deadlock risk

### Benefits of Simplification
- **Zero Detection Errors**: Custom PyQt/PySide apps handled correctly
- **No Deadlocks**: No pipes to block on
- **Cleaner Code**: ~100 lines removed, single execution path
- **More Reliable**: Simpler logic = fewer edge cases
- **Future Proof**: New apps automatically handled safely

## Testing the Fix

### Manual Test
1. Launch the application: `python shotbot.py`
2. Create a custom launcher for any app
3. Launch the app
4. Close the app
5. Relaunch the app
6. **Expected**: App relaunches without crashes or console errors

### Automated Test
Run the test script:
```bash
python test_crash_fix.py
```

This will:
- Create launchers for test applications
- Test launching, closing, and relaunching
- Verify process management
- Report success/failure

## Verification Checklist

✅ All apps treated uniformly (no detection needed)  
✅ Processes are isolated (start_new_session=True)  
✅ No pipe deadlocks (DEVNULL for all apps)  
✅ Worker threads handle all apps correctly  
✅ Cleanup prevents memory leaks  
✅ Apps can be relaunched after closing  
✅ No `[3]+ Stopped` messages  
✅ Simpler, more maintainable code  

## Console Output Examples

### After Fix (Simplified)
```
[17:57:12] Launching Nuke...
[17:57:12] Launched in terminal: gnome-terminal
[17:57:15] Process completed
[17:57:20] Launching Nuke...  # Relaunch works!
[17:57:20] Launched in terminal: gnome-terminal
```

All applications now follow the same safe execution path, eliminating an entire class of bugs while making the code cleaner and more maintainable.