# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ShotBot is a PySide6-based GUI application for VFX shot browsing and application launching. It integrates with VFX pipeline tools using the `ws` (workspace) command to list and navigate shots. The application provides a visual interface for artists to browse shots, view thumbnails, and launch VFX applications in the correct shot context.

## Commands

### Running the Application
```bash
# Using virtual environment (recommended)
source venv/bin/activate
python shotbot.py

# Or in rez environment
rez env PySide6_Essentials pillow Jinja2 -- python3 shotbot.py

# Debug mode for verbose logging
SHOTBOT_DEBUG=1 python shotbot.py
```

### Testing
**IMPORTANT**: Always use the `run_tests.py` script, never run pytest directly:

```bash
# Run all tests
python run_tests.py

# Run specific test file
python run_tests.py tests/unit/test_shot_model.py

# Run specific test method
python run_tests.py tests/unit/test_shot_model.py::TestShot::test_shot_creation

# Run with coverage report
python run_tests.py --cov

# Run tests matching a pattern
python run_tests.py -k "test_cache"
```

### Code Quality
```bash
# Activate virtual environment first
source venv/bin/activate

# Format code with ruff
ruff format .

# Check for linting issues
ruff check .

# Fix linting issues automatically
ruff check --fix .

# Type checking
basedpyright
```

### Setting Up Development Environment
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install runtime dependencies
pip install -r requirements.txt

# Install development dependencies
pip install -r requirements-dev.txt
```

## Architecture

### Core System Design

The application follows a Model-View architecture with Qt's signal-slot mechanism for loose coupling:

1. **Data Layer**: Models (`shot_model.py`, `threede_scene_model.py`) handle data fetching and caching
2. **View Layer**: Grid widgets (`shot_grid.py`, `threede_shot_grid.py`) display thumbnails
3. **Control Layer**: Launchers (`command_launcher.py`, `launcher_manager.py`) execute applications
4. **Cache Layer**: `cache_manager.py` manages persistent caching with TTL

### Key Components

#### Main Application
- **`shotbot.py`**: Entry point and application initialization
- **`main_window.py`**: Main window with tabbed interface, integrates all components
- **`config.py`**: Centralized configuration constants (paths, timeouts, defaults)

#### Shot Management
- **`shot_model.py`**: Parses `ws -sg` output, manages shot list with caching
- **`shot_grid.py`**: Thumbnail grid for "My Shots" tab
- **`shot_info_panel.py`**: Displays current shot details and thumbnail
- **`thumbnail_widget.py`**: Individual thumbnail with selection effects

#### 3DE Scene Discovery
- **`threede_scene_finder.py`**: Recursive .3de file discovery in user directories
- **`threede_scene_model.py`**: Model for 3DE scenes with user exclusion
- **`threede_shot_grid.py`**: Grid widget for "Other 3DE scenes" tab
- **`threede_scene_worker.py`**: Background worker thread for scene discovery

#### Custom Launcher System
- **`launcher_manager.py`**: Business logic for custom launchers with thread safety
- **`launcher_dialog.py`**: UI for creating/editing custom launchers
- **`launcher_config.py`**: Configuration for launcher templates
- **`LauncherWorker`**: QThread-based worker for non-blocking command execution
- **`terminal_launcher.py`**: Terminal-based command execution

#### Utilities
- **`utils.py`**: Centralized utilities for path operations, validation, and caching
- **`cache_manager.py`**: TTL-based caching with QPixmap resource cleanup
- **`log_viewer.py`**: Command history viewer
- **`raw_plate_finder.py`**: Discovers raw plate sequences
- **`undistortion_finder.py`**: Finds undistortion .nk files

### Critical Implementation Details

#### Workspace Command (`ws`)
The `ws` command is a **shell function**, not an executable. Must use interactive bash:
```python
subprocess.run(["/bin/bash", "-i", "-c", "ws -sg"], ...)
```

#### QSettings Storage
QByteArray to hex string conversion for geometry storage:
```python
# Correct: Use .data().decode('ascii')
hex_string = byte_array.data().decode('ascii')
# NOT: str(byte_array) or byte_array.hex()
```

#### Thread Safety in LauncherManager
The custom launcher system uses thread-safe process management:
- `threading.RLock()` protects `_active_processes` dictionary
- Unique process keys with timestamp + UUID prevent collisions
- `LauncherWorker` QThread for non-blocking execution

#### Change Detection
`refresh_shots()` returns a tuple for efficient UI updates:
```python
success, has_changes = shot_model.refresh_shots()
if success and has_changes:
    # Update UI only when needed
```

#### Resource Management
- QPixmap cleanup in `cache_manager.py` prevents memory leaks
- 30-second subprocess timeout prevents hangs
- Proper QThread cleanup with `quit()` and `wait()`

### Signal-Slot Communication

Key signals used throughout the application:
- `shot_model.shots_updated`: Emitted when shot list changes
- `launcher_manager.command_started/finished/output`: Launcher execution events
- `threede_worker.scene_found/scan_progress/scan_finished`: 3DE discovery events
- `thumbnail_widget.shot_selected/shot_double_clicked`: User interaction

### Caching Strategy

- **Shot List**: 30-minute TTL, refreshes every 5 minutes if changed
- **Thumbnails**: Permanent cache, QPixmap resources cleaned up on deletion
- **3DE Scenes**: 30-minute TTL with background refresh
- **Path Validation**: 60-second TTL to reduce filesystem checks

## Common Development Tasks

### Adding a New Application Launcher
Edit the `APPS` dictionary in `config.py`:
```python
APPS = {
    "3de": "3de",
    "nuke": "nuke",
    "maya": "maya",
    "your_app": "your_command",  # Add here
}
```

### Creating a Custom Launcher
Use the `LauncherManager` API:
```python
launcher = CustomLauncher(
    id="my_launcher",
    name="My Tool",
    command="my_command {shot_name}",
    icon="path/to/icon.png"
)
manager.create_launcher(launcher)
```

### Debugging Issues

1. **Enable debug logging**: `SHOTBOT_DEBUG=1 python shotbot.py`
2. **Check process output**: View command history in log viewer
3. **Test workspace command**: `bash -i -c "ws -sg"` in terminal
4. **Verify paths**: Check `utils.py` path validation with debug mode

## Testing Guidelines

### Test Organization
- `tests/unit/`: Unit tests for individual components
- `tests/integration/`: Integration tests for component interactions
- `run_tests.py`: Test runner with proper Qt initialization

### Writing Tests
```python
# Use pytest-qt fixtures
def test_shot_model(qtbot):
    model = ShotModel()
    qtbot.addWidget(model)  # Ensures cleanup
    
    # Test with signals
    with qtbot.waitSignal(model.shots_updated, timeout=1000):
        model.refresh_shots()
```

### Common Test Issues
- **Qt platform errors**: Always use `run_tests.py`, not direct pytest
- **Timeouts**: WSL requires xvfb plugin disabled (handled by runner)
- **Signal testing**: Use `qtbot.waitSignal()` for async operations

## Performance Considerations

### UI Responsiveness
- Background workers for long operations (3DE scanning, shot refresh)
- Adaptive timer intervals based on activity
- Thumbnail loading happens asynchronously

### Memory Management
- QPixmap cache cleanup prevents leaks
- Process output buffering with line-by-line reading
- TTL-based path validation cache reduces filesystem access

### Concurrent Operations
- Thread-safe launcher management with RLock
- Multiple launchers can run simultaneously
- Worker threads for non-blocking operations

## Recent Enhancements

### Custom Launcher System (Latest)
- Thread-safe concurrent launcher execution
- Worker threads prevent UI freezing
- Unique process tracking with timestamp + UUID keys
- Comprehensive process state management
- Real-time output streaming from launched applications

### 3DE Scene Discovery
- Flexible recursive search (no path requirements)
- Intelligent plate name extraction from any path structure
- Automatic user exclusion (current user filtered out)
- Background scanning with progress reporting

### Code Quality Improvements
- Comprehensive error handling and logging
- Resource management with guaranteed cleanup
- Centralized utilities in `utils.py`
- Type hints and documentation throughout
- Performance optimizations with caching