# LauncherManager Integration Guide

This document explains how to integrate the `LauncherManager` business logic layer into ShotBot's custom launcher feature.

## Overview

The `launcher_manager.py` module provides a complete business logic layer for managing custom application launchers in ShotBot. It handles CRUD operations, validation, variable substitution, and execution with proper Qt signal integration.

## Key Components

### LauncherManager Class

The main `LauncherManager` class provides:

- **CRUD Operations**: Create, read, update, delete launchers
- **Validation**: Name uniqueness, command security, path existence
- **Variable Substitution**: Shot context and custom variables
- **Execution**: Local and shot context execution
- **Qt Integration**: Proper signal emission for UI updates

### Data Classes

- **`CustomLauncher`**: Main launcher data structure
- **`LauncherEnvironment`**: Environment configuration (bash, rez, conda)
- **`LauncherTerminal`**: Terminal settings and preferences
- **`LauncherValidation`**: Validation rules and security patterns
- **`LauncherConfig`**: Persistence layer for JSON configuration

## Integration Example

```python
from launcher_manager import LauncherManager
from shot_model import Shot

# Create manager instance
manager = LauncherManager()

# Connect to signals for UI updates
manager.launchers_changed.connect(self.refresh_launcher_list)
manager.validation_error.connect(self.show_error_message)
manager.execution_started.connect(self.show_execution_feedback)

# Create a new launcher
launcher_id = manager.create_launcher(
    name="Launch Nuke",
    command="nuke --nc {workspace_path}/nuke/{shot}_v001.nk",
    description="Launch Nuke with shot-specific script",
    category="compositing"
)

# Execute in shot context
current_shot = Shot(...)
if launcher_id:
    manager.execute_in_shot_context(launcher_id, current_shot)
```

## Qt Signals

The manager emits the following signals for UI integration:

```python
# Launcher management signals
launchers_changed = Signal()           # When launcher list changes
launcher_added = Signal(str)           # When launcher is added (ID)
launcher_updated = Signal(str)         # When launcher is updated (ID)
launcher_deleted = Signal(str)         # When launcher is deleted (ID)

# Validation and error signals
validation_error = Signal(str, str)    # Field name, error message

# Execution signals
execution_started = Signal(str)        # When launcher starts (ID)
execution_finished = Signal(str, bool) # When launcher finishes (ID, success)
```

## Variable Substitution

The manager supports comprehensive variable substitution:

### Shot Context Variables
- `{show}` - Show name
- `{sequence}` - Sequence name
- `{shot}` - Shot name
- `{full_name}` - Combined sequence_shot name
- `{workspace_path}` - Full workspace path

### Environment Variables
- `{HOME}` - User home directory
- `{USER}` - Current username
- `{SHOTBOT_VERSION}` - Application version

### Custom Variables
User-defined variables in the launcher configuration.

## Security Features

The manager includes built-in security validation:

- **Command Validation**: Checks for dangerous patterns (rm, sudo, etc.)
- **Path Validation**: Verifies required files exist
- **Executable Validation**: Confirms executables are available
- **Safe Substitution**: Uses `string.Template` for secure variable replacement

## Configuration Persistence

Launchers are automatically saved to:
```
$HOME/.shotbot/custom_launchers.json
```

The configuration follows the JSON schema documented in `CUSTOM_LAUNCHER_DOCUMENTATION.md`.

## Usage Patterns

### Basic Launcher Creation
```python
launcher_id = manager.create_launcher(
    name="Simple Tool",
    command="my_tool --input={workspace_path}"
)
```

### Complex Environment Setup
```python
from launcher_manager import LauncherEnvironment, LauncherTerminal

launcher_id = manager.create_launcher(
    name="Rez Environment Tool",
    command="studio_tool --shot={full_name}",
    environment=LauncherEnvironment(
        type="rez",
        packages=["maya", "studio_tools"]
    ),
    terminal=LauncherTerminal(
        required=True,
        persist=True,
        title="Studio Tool - {show} {full_name}"
    )
)
```

### Validation and Error Handling
```python
# Connect to validation errors
manager.validation_error.connect(
    lambda field, error: print(f"Error in {field}: {error}")
)

# Create launcher - will emit validation_error if issues found
launcher_id = manager.create_launcher(
    name="",  # Invalid - empty name
    command="dangerous_command"  # May trigger security validation
)
```

### Path Validation
```python
# Validate launcher paths before execution
errors = manager.validate_launcher_paths(launcher_id, current_shot)
if errors:
    print("Validation errors:")
    for error in errors:
        print(f"- {error}")
else:
    # Safe to execute
    manager.execute_in_shot_context(launcher_id, current_shot)
```

## Thread Safety

The `LauncherManager` is designed for single-threaded use within the Qt main thread. All signal emissions are thread-safe when used properly within the Qt event loop.

## Error Handling

The manager provides comprehensive error handling:

- **Validation Errors**: Emitted via `validation_error` signal
- **Execution Errors**: Logged and reported via `execution_finished` signal
- **Configuration Errors**: Logged with fallback to empty configuration
- **Security Errors**: Strict validation prevents dangerous commands

## Testing

Comprehensive unit tests are provided in `tests/unit/test_launcher_manager.py`. The tests cover:

- CRUD operations
- Validation logic
- Variable substitution
- Signal emission
- Error handling
- Security validation
- Path validation

Run tests with:
```bash
python run_tests.py tests/unit/test_launcher_manager.py
```

## Future Enhancements

Potential areas for future development:

1. **Template System**: Pre-built launcher templates for common tools
2. **Dependency Management**: Launcher dependencies and prerequisites
3. **Execution History**: Track and display execution history
4. **Environment Auto-Detection**: Automatic rez package detection
5. **Remote Execution**: Support for remote execution contexts
6. **Plugin Architecture**: Extensible launcher type system

## Files

- **`launcher_manager.py`** - Main implementation
- **`tests/unit/test_launcher_manager.py`** - Comprehensive unit tests
- **`example_launcher_usage.py`** - Usage demonstration
- **`docs/CUSTOM_LAUNCHER_DOCUMENTATION.md`** - Complete feature documentation

This business logic layer provides a solid foundation for ShotBot's custom launcher feature with proper separation of concerns, comprehensive validation, and Qt integration.