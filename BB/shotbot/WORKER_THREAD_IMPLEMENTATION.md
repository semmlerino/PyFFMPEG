# Qt Worker Thread Implementation for Custom Launcher Execution

## Overview

This implementation adds a Qt-based worker thread pattern to the launcher system to prevent UI blocking during subprocess execution. The system maintains full compatibility with the existing LauncherManager API while providing non-blocking execution for better UI responsiveness.

## Key Components

### 1. LauncherWorker (QThread)
- **Location**: `launcher_manager.py`
- **Purpose**: Executes subprocess commands in a separate thread
- **Features**:
  - Executes processes with DEVNULL for stdout/stderr (prevents deadlocks)
  - Uses start_new_session for process isolation
  - Emits Qt signals for UI updates
  - Supports graceful termination
  - Handles working directory changes

### 2. Worker Integration in LauncherManager
- **New Methods**:
  - `_execute_with_worker()`: Creates and starts worker threads
  - `_on_worker_finished()`: Handles worker completion
  - `_cleanup_finished_workers()`: Cleans up completed workers
  - `stop_all_workers()`: Stops all active workers during shutdown

- **Modified Methods**:
  - `execute_launcher()`: Added `use_worker` parameter (default: True)
  - `execute_in_shot_context()`: Added `use_worker` parameter (default: True)
  - `get_active_process_count()`: Now includes worker count
  - `_periodic_cleanup()`: Also cleans up finished workers
  - `shutdown()`: Stops all workers before process cleanup

### 3. Signal-Slot Integration
The worker emits these signals:
- `command_started(launcher_id, command)`: When execution begins
- `command_finished(launcher_id, success, return_code)`: On completion
- `command_error(launcher_id, error_message)`: On errors

Note: `command_output` signal has been removed as all apps now use DEVNULL for stdout/stderr to prevent deadlocks.

These are connected to appropriate handlers in LauncherManager.

### 4. UI Integration Updates
- **MainWindow**: Updated `closeEvent()` to call `launcher_manager.shutdown()`
- Ensures proper cleanup of worker threads on application exit

## Usage

### Basic Usage (Automatic)
```python
# By default, non-terminal commands use worker threads
launcher_manager.execute_launcher(launcher_id)  # Uses worker
```

### Explicit Control
```python
# Force worker thread usage
launcher_manager.execute_launcher(launcher_id, use_worker=True)

# Disable worker thread (use direct subprocess)
launcher_manager.execute_launcher(launcher_id, use_worker=False)
```

### Terminal Commands
Commands with `terminal.required = True` always use direct subprocess execution, even when `use_worker=True`.

## Benefits

1. **UI Responsiveness**: Long-running commands don't freeze the UI
2. **Process Monitoring**: Can capture and display output in real-time
3. **Better Error Handling**: Exceptions in worker threads are caught and reported
4. **Resource Management**: Automatic cleanup with Qt timers
5. **Backward Compatibility**: Existing code continues to work without changes

## Testing

Two test files are provided:

1. **test_launcher_worker.py**: Basic worker functionality tests
2. **test_worker_ui_integration.py**: Interactive UI test showing non-blocking behavior

Run the UI test to see the counter continue updating while a long command executes.

## Implementation Details

### Thread Safety
- Uses `threading.RLock()` for thread-safe access to shared data
- Worker references stored in `_active_workers` dictionary
- Periodic cleanup via QTimer (every 30 seconds)

### Process Lifecycle
1. Worker created and started
2. Subprocess executed in worker thread
3. Output captured and emitted via signals
4. Worker marked as finished
5. Cleanup scheduled via QTimer
6. Worker removed from active list

### Error Handling
- Worker exceptions caught and logged
- Failed processes emit `execution_finished` with `success=False`
- Graceful termination with timeout support
- Force kill as last resort

## Future Enhancements

1. **Output Buffering**: Add option to buffer output for better performance
2. **Progress Reporting**: Parse output for progress indicators
3. **Cancel Support**: Add UI cancel button that stops workers
4. **Output Display**: Add dedicated output widget in UI
5. **Priority Queue**: Implement priority-based execution queue