# Launcher Manager Simplification Summary

## Changes Made

This simplification removed all GUI detection logic and treats ALL launched applications as GUI apps, using the safest approach for all processes.

### Key Changes:

1. **Removed GUI Detection Methods**:
   - Removed `_is_gui_command()` method from `LauncherWorker` class
   - Removed `_detect_gui_command()` method from `LauncherManager` class
   - Eliminated all conditional logic based on GUI detection

2. **Simplified LauncherWorker.run() Method**:
   - Single execution path for all applications
   - Always uses `subprocess.DEVNULL` for stdout/stderr to prevent deadlocks
   - Always uses `start_new_session=True` for process isolation
   - No conditional logic for CLI vs GUI apps

3. **Streamlined Execution Methods**:
   - `execute_launcher()`: Simplified to either launch in terminal or use worker thread
   - `execute_in_shot_context()`: Same simplification for shot context execution
   - Removed auto-detection logic that forced terminal mode for GUI apps

4. **Consistent Process Handling**:
   - All processes use `subprocess.DEVNULL` (never capture stdout/stderr)
   - All processes use `start_new_session=True` (always isolated)
   - All processes go through the same validation and tracking

### Benefits:

- **Simpler Code**: Removed ~100 lines of complex detection logic
- **More Reliable**: Single code path reduces edge cases and potential issues
- **Safer**: Always uses most conservative approach (process isolation, no output capture)
- **Maintainable**: Easier to understand and debug without conditional complexity

### Behavior Changes:

- All applications now treated uniformly as GUI applications
- Worker threads never capture stdout/stderr (previously some CLI apps did)
- Consistent process isolation for all launched applications
- Simplified terminal launching logic

The simplified code maintains all thread safety improvements and cleanup mechanisms while being much easier to understand and maintain.