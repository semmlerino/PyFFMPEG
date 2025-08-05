# Terminal Launcher Module

The `terminal_launcher.py` module provides cross-platform terminal launching functionality for ShotBot's custom launcher feature.

## Overview

This module enables ShotBot to execute custom commands in new terminal windows across Linux, macOS, and Windows platforms. It supports multiple terminal emulators, environment variable injection, working directory control, and secure command execution.

## Key Features

- **Cross-platform support**: Linux, macOS, and Windows
- **Multiple terminal emulators**: Automatically detects and uses available terminals
- **Variable substitution**: Dynamic command generation with `{variable}` syntax
- **Environment management**: Custom environment variables and working directories
- **Security validation**: Command validation and injection protection
- **Signal integration**: Qt signals for execution status and logging
- **Flexible configuration**: Rich launcher configuration options

## Supported Terminals

### Linux
- gnome-terminal (preferred)
- konsole
- xterm
- x-terminal-emulator
- alacritty
- terminator

### macOS
- Terminal.app
- iTerm2

### Windows
- cmd.exe
- PowerShell
- Windows Terminal (wt.exe)

## Basic Usage

```python
from terminal_launcher import Launcher, TerminalLauncher

# Create terminal launcher
launcher_manager = TerminalLauncher()

# Create a simple launcher
launcher = Launcher(
    name="Echo Test",
    command="echo 'Hello {user}!'",
    description="Simple echo command",
    persist_terminal=True
)

# Execute with variables
variables = {"user": "gabriel-h"}
result = launcher_manager.execute_launcher(launcher, variables)

if result.success:
    print(f"Launched successfully with PID: {result.process_id}")
else:
    print(f"Launch failed: {result.error_message}")
```

## Advanced Configuration

```python
# Complex launcher with environment and validation
launcher = Launcher(
    name="Custom VFX Tool",
    command="rez env my_tool -- my_tool --shot={full_name} --path='{workspace_path}'",
    description="Launch VFX tool in rez environment",
    category="pipeline",
    working_directory="{workspace_path}",
    environment_vars={
        "SHOT_ROOT": "{workspace_path}",
        "CURRENT_SHOT": "{full_name}"
    },
    terminal_title="VFX Tool - {full_name}",
    terminal_geometry="100x30+200+100",
    persist_terminal=True,
    timeout_seconds=60,
    validate_command=False  # Skip validation for complex rez commands
)
```

## Variable Substitution

Built-in variables are automatically available:
- `{user}`: Current username
- `{home}`: User home directory  
- `{timestamp}`: Current timestamp (YYYY-MM-DD_HH-MM-SS)
- `{date}`: Current date (YYYY-MM-DD)
- `{time}`: Current time (HH:MM:SS)

Custom variables can be passed via the `variables` parameter:
- `{workspace_path}`: Shot workspace directory
- `{full_name}`: Full shot name
- `{show}`, `{sequence}`, `{shot}`: Shot components

## Security Features

The module includes several security measures:

1. **Command validation**: Checks if executables exist
2. **Basic injection protection**: Warns about potentially dangerous commands
3. **Path validation**: Ensures paths exist before execution
4. **Timeout handling**: Prevents hung processes
5. **Environment isolation**: Controlled environment variable injection

## Integration with ShotBot

The module integrates with ShotBot's existing architecture:

```python
# In command_launcher.py
class CommandLauncher(QObject):
    def __init__(self):
        super().__init__()
        self.terminal_launcher = TerminalLauncher()
    
    def launch_custom_app(self, launcher_id, shot_context):
        """Launch custom application in shot context."""
        launcher = self.get_custom_launcher(launcher_id)
        result = self.terminal_launcher.execute_launcher(launcher, shot_context)
        return result.success
```

## Error Handling

The module provides comprehensive error handling:

- `LaunchResult` objects contain success status and error messages
- Qt signals are emitted for success and failure cases
- Detailed logging for debugging and monitoring
- Graceful fallbacks when preferred terminals are unavailable

## Platform-Specific Behavior

### Linux
- Uses standard terminal emulators with command-line arguments
- Supports geometry, titles, and working directories
- Falls back through available terminals automatically

### macOS
- Uses AppleScript (osascript) for Terminal.app and iTerm2
- Integrates with macOS application launching
- Handles app bundle paths correctly

### Windows
- Supports cmd.exe, PowerShell, and Windows Terminal
- Uses platform-appropriate command syntax
- Handles Windows path conventions

## Examples

See `examples/custom_launcher_integration.py` for a complete integration example showing:
- Custom launcher definitions
- Variable substitution examples
- Integration patterns with ShotBot
- Practical VFX pipeline use cases

## Testing

Run the test suite with:
```bash
python run_tests.py tests/unit/test_terminal_launcher.py
```

The module includes comprehensive unit tests covering:
- Platform detection
- Terminal discovery
- Command building
- Variable substitution
- Error handling
- Signal emission

## Dependencies

- Python 3.8+
- PySide6 (for Qt signals and QObject inheritance)
- Standard library modules: `subprocess`, `platform`, `shutil`, `os`, `pathlib`

## Thread Safety

The module is designed to be thread-safe for Qt applications:
- Inherits from QObject for proper Qt integration
- Uses Qt signals for cross-thread communication
- Process launching uses subprocess.Popen safely

## Performance Considerations

- Terminal detection is cached after initial discovery
- Command validation can be disabled for performance-critical scenarios
- Variable substitution is lightweight and fast
- Process launching is non-blocking

## Future Enhancements

Potential areas for expansion:
- Configuration file support (JSON/YAML)
- Plugin system for custom terminal types
- Advanced command templates
- Process monitoring and lifecycle management
- Integration with external process managers