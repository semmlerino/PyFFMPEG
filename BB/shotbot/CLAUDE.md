# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## IMPORTANT: Security Context

**This is a personal VFX pipeline tool running on a secure, isolated network.** Security hardening is NOT a concern. See `SECURITY_CONTEXT.md` for details.

**DO NOT raise security issues about:**
- Command validation or subprocess execution patterns
- The launcher system's command whitelist implementation  
- Shell command execution
- Any "vulnerabilities" in `launcher/worker.py` or related files

Focus on functionality, performance, and VFX workflow optimization instead.

## Project Overview

ShotBot is a PySide6-based GUI application for VFX shot browsing and application launching. It integrates with VFX pipeline tools using the `ws` (workspace) command to list and navigate shots. The application provides a visual interface for artists to browse shots, view thumbnails, and launch VFX applications in the correct shot context.

## Python Compatibility

### Supported Versions
- **Minimum**: Python 3.11
- **Recommended**: Python 3.12+
- **Tested**: Python 3.11, 3.12

### Important Compatibility Notes

#### Type Annotations
This codebase uses modern type annotations with union syntax (`str | None`) which requires Python 3.10+. All type annotations are compatible with Python 3.11.

#### Override Decorator
The `@override` decorator is used for better type safety. For Python 3.11 compatibility:
- **DO NOT** import from `typing.override` (Python 3.12+ only)
- **DO** import from `typing_extensions.override` (works with 3.11+)

```python
# Correct (Python 3.11+ compatible)
from typing_extensions import override

# Incorrect (Python 3.12+ only)
from typing import override  # Will fail on Python 3.11!
```

#### Threading and Performance
Recent improvements include:
- Parallel filesystem scanning with `concurrent.futures.ThreadPoolExecutor`
- Proper `@Slot` decorators on all QThread `run()` methods
- Thread-safe singleton initialization for `ProcessPoolManager`

These features are fully compatible with Python 3.11+.

#### Dependencies
The `typing_extensions` package is required and included in requirements.txt. This provides backports of typing features for older Python versions.

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

See **UNIFIED_TESTING_GUIDE_DO_NOT_DELETE.md** for comprehensive testing documentation including:
- WSL-optimized strategies
- Test organization and best practices  
- Qt-specific testing patterns
- Common issues and solutions

**DO NOT** create scripts to automate fixes, as those tend to create more issues. Only if you are absolutely suer it won't cause issues, you can run a dry test to see what it would do exactly, and it would fix a lot of easy and simple issues at once. 

Quick commands:
```bash
python3 quick_test.py              # Quick validation (2 seconds)
python3 run_tests_wsl.py --fast    # Fast tests only (30 seconds)
python run_tests.py                # Standard runner with Qt setup
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
4. **Cache Layer**: Modular cache system with specialized components (see Cache Architecture section)

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

#### Previous Shots (Approved/Completed)
- **`previous_shots_finder.py`**: Finds shots user has worked on that are no longer active (approved)
- **`previous_shots_model.py`**: Qt model managing approved shots with thread-safe refresh
- **`previous_shots_grid.py`**: Grid widget displaying approved shots with resize debouncing
- **`previous_shots_worker.py`**: Background worker for filesystem scanning (uses finder)

#### Custom Launcher System
- **`launcher_manager.py`**: Business logic for custom launchers with thread safety
- **`launcher_dialog.py`**: UI for creating/editing custom launchers
- **`launcher_config.py`**: Configuration for launcher templates
- **`LauncherWorker`**: QThread-based worker for non-blocking command execution
- **`terminal_launcher.py`**: Terminal-based command execution

#### Cache System (Refactored Architecture)
- **`cache_manager.py`**: Facade maintaining backward compatibility with modular components
- **`cache/`**: Modular cache package with specialized components:
  - **`storage_backend.py`**: Atomic file I/O operations with fallback handling
  - **`failure_tracker.py`**: Exponential backoff for failed thumbnail operations  
  - **`memory_manager.py`**: Memory usage tracking with LRU eviction
  - **`thumbnail_processor.py`**: Multi-format image processing (Qt/PIL/OpenEXR)
  - **`shot_cache.py`**: Shot data caching with TTL validation
  - **`threede_cache.py`**: 3DE scene caching with metadata support
  - **`cache_validator.py`**: Cache consistency validation and repair
  - **`thumbnail_loader.py`**: Async thumbnail loading with QRunnable

#### Utilities
- **`utils.py`**: Centralized utilities for path operations, validation, and caching
- **`log_viewer.py`**: Command history viewer
- **`raw_plate_finder.py`**: Discovers raw plate sequences
- **`undistortion_finder.py`**: Finds undistortion .nk files

### Cache Architecture (Refactored 2025-08-20)

Refactored from monolithic 1,476-line class into modular SOLID architecture with 100% backward compatibility:

```
cache_manager.py (Facade - 369 lines)
├── StorageBackend (150 lines) - Atomic file operations
├── FailureTracker (150 lines) - Exponential backoff logic  
├── MemoryManager (100 lines) - Memory tracking & LRU eviction
├── ThumbnailProcessor (300 lines) - Multi-format image processing
├── ShotCache (100 lines) - Shot data caching with TTL
├── ThreeDECache (100 lines) - 3DE scene caching with metadata
├── CacheValidator (100 lines) - Consistency validation & repair
└── ThumbnailLoader (100 lines) - Async QRunnable processing
```

**Key Features:**
- Exponential backoff for failures (5min → 15min → 45min → 2hr)
- LRU eviction at 100MB memory limit
- Multi-format support (Qt/PIL/OpenEXR) with HDR tone mapping
- TTL-based expiration (30 minutes default)
- Atomic operations prevent corruption
- Zero breaking changes - existing code works unchanged

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


## Changelog

### 2025-08-20: Previous Shots Feature
- Added view for approved/completed shots with filesystem scanning
- Thread-safe refresh with background worker, 30-minute TTL caching
- UI resize debouncing (100ms) for performance

### 2025-08-12: Nuke Script Generator Fix
- Fixed colorspace quoting for names with spaces (e.g., "Input - Sony - S-Gamut3.Cine - Linear")
- Added temporary file cleanup and shot name sanitization

### 2025-08-08: Type System Improvements
- Added RefreshResult NamedTuple for clear operation results
- Union types for flexible path APIs (str|Path)
- Comprehensive Optional handling for Qt widgets

### 2025-08-07: Raw Plate Finder & UI Fixes
- Dynamic colorspace detection from actual files
- Non-blocking folder opening with QRunnable
- 3DE scene deduplication by modification time
- **BREAKING**: `PathUtils.build_raw_plate_path()` now returns base path without plate name

## Type System

### Key Patterns
- **RefreshResult NamedTuple**: Replaces ambiguous tuple returns
  ```python
  class RefreshResult(NamedTuple):
      success: bool
      has_changes: bool
  ```
- **Union[str, Path]**: Flexible path APIs accepting both types
- **Optional[QWidget]**: Proper nullable Qt widget handling
- **Typed Signals**: `Signal()`, `Signal(str)`, `Signal(dict)` declarations

### Type Checking
```bash
# Run type checking with basedpyright (uses tests/pyrightconfig.json)
basedpyright

# From tests directory for enhanced configuration
cd tests && basedpyright

# WSL compatibility if needed
basedpyright --typeshedpath venv/lib/python3.12/site-packages/basedpyright/dist/typeshed-fallback
```

**Type Checker Configuration**: The project uses `tests/pyrightconfig.json` for comprehensive type checking settings including:
- Basic type checking mode with Python 3.12 target
- Enhanced reporting for type issues (unknown members, arguments, etc.)
- Strict error reporting for unnecessary type ignore comments