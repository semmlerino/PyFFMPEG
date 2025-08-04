# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with the shotbot repository.

## Project Overview

ShotBot is a PySide6-based GUI application for VFX shot browsing and application launching. It integrates with VFX pipeline tools using the `ws` (workspace) command to list and navigate shots.

## Key Features

- Visual shot browsing with thumbnail grid
- Launch applications (3de, Nuke, Maya, RV, Publish) in shot context  
- Shot information panel with thumbnails
- Caching system for shots and thumbnails
- Background refresh with change detection
- Persistent settings using Qt's QSettings

## Architecture

### Core Components

- **`shotbot.py`** - Main entry point
- **`main_window.py`** - Main application window with shot info panel integration
- **`shot_model.py`** - Shot data model with caching and change detection
- **`shot_grid.py`** - Thumbnail grid widget
- **`thumbnail_widget.py`** - Individual thumbnail display
- **`command_launcher.py`** - Application launching using `ws` command
- **`log_viewer.py`** - Command history display
- **`shot_info_panel.py`** - Current shot information display
- **`cache_manager.py`** - Thumbnail and shot list caching with QPixmap resource cleanup
- **`config.py`** - Centralized configuration constants
- **`utils.py`** - Utility modules for path handling, validation, and common operations

### Finder Modules

- **`raw_plate_finder.py`** - Discovers raw plate sequences in shot directories
- **`undistortion_finder.py`** - Finds undistortion files and sequences
- **`threede_scene_finder.py`** - Discovers 3DE scene files from other users
- **`threede_scene_model.py`** - Model for managing 3DE scenes with caching

### Key Implementation Details

1. **Workspace Command**: Uses `ws` shell function (not an executable) via `bash -i -c`
2. **Settings Storage**: QByteArray hex conversion using `.data().decode('ascii')`
3. **Change Detection**: `refresh_shots()` returns tuple `(success, has_changes)`
4. **Caching**: Shots cached for 30 minutes, thumbnails cached permanently
5. **Background Refresh**: Every 5 minutes, only updates UI if changes detected
6. **Path Handling**: Centralized in `utils.py` with caching and validation
7. **Logging**: Comprehensive logging throughout using Python's logging module
8. **Error Handling**: Specific exception types instead of generic exceptions
9. **Resource Management**: Proper QPixmap cleanup to prevent memory leaks
10. **Dynamic User Detection**: Current user automatically detected from environment

### 3DE Scene Discovery

The "Other 3DE scenes" tab uses flexible recursive search:

1. **No Path Requirements**: Finds .3de files anywhere in user directories
2. **Intelligent Grouping**: Extracts meaningful "plate" names from paths:
   - Recognizes patterns like `bg01`, `fg01`, `plate01`
   - Uses directory context (e.g., after "scenes/" or "3de/")
   - Falls back to meaningful directory names
3. **User Segmentation**:
   - "My Shots" tab: Shows current user's shots (from `ws` command)
   - "Other 3DE scenes" tab: Shows .3de files from all OTHER users
   - Current user automatically excluded from "Other 3DE scenes"
4. **Examples of Found Files**:
   ```
   user/alice/mm/3de/scenes/bg01/*.3de         → Plate: bg01
   user/bob/matchmove/3de/shot010/*.3de        → Plate: shot010
   user/charlie/work/3de_files/final/*.3de     → Plate: 3de_files
   user/dave/personal/tracking/*.3de           → Plate: tracking
   ```

## Testing

**IMPORTANT**: Always run tests through the `run_tests.py` script to avoid Qt initialization issues and timeouts:

```bash
# Run all tests
python run_tests.py

# Run specific test file
python run_tests.py tests/unit/test_shot_model.py

# Run specific test
python run_tests.py tests/unit/test_shot_model.py::TestShot::test_shot_creation

# Run with coverage
python run_tests.py --cov

# Run tests matching a pattern
python run_tests.py -k "test_cache"
```

**Do NOT run pytest directly** as it will cause timeouts and Qt platform errors. The `run_tests.py` script properly configures the environment and disables xvfb plugin for WSL compatibility.

## Development Guidelines

### Running the Application

```bash
# In rez environment
rez env PySide6_Essentials pillow Jinja2 -- python3 shotbot.py

# Or with virtual environment
source venv/bin/activate
python shotbot.py
```

### Code Quality

```bash
# Run linting
source venv/bin/activate
ruff check .
ruff format .

# Type checking (if basedpyright is installed)
basedpyright
```

### Dependencies

```bash
# Core dependencies
pip install PySide6 pillow

# Development dependencies
pip install pytest pytest-qt pytest-cov ruff basedpyright
```

### Common Issues

1. **"ws command not found"**: The `ws` command is a shell function, not an executable. Use `bash -i -c` to invoke it.

2. **Qt platform errors**: Use `run_tests.py` for testing, not direct pytest invocation.

3. **Settings hex conversion**: Use `.data().decode('ascii')` for QByteArray to hex string conversion.

4. **3DE scenes not loading**: 
   - As of latest update, the search is now **flexible and recursive**
   - Finds ALL .3de files in any subdirectory under user folders
   - No specific path structure required
   - Check debug logs with `SHOTBOT_DEBUG=1` to see what's being scanned

## Utils Module

The `utils.py` module provides centralized utilities for common operations:

### PathUtils
- `build_path()` - Safe path construction with validation
- `build_plate_path()` - Constructs standard plate directory paths
- `build_undistortion_path()` - Constructs undistortion directory paths
- `build_threede_scene_path()` - Constructs 3DE scene directory paths
- `validate_path_exists()` - Validates path existence with caching
- `resolve_symlink()` - Safe symlink resolution
- `get_path_type()` - Determines if path is file, directory, or symlink

### VersionUtils
- `extract_version_from_path()` - Extracts version numbers from paths
- `is_valid_version()` - Validates version format (e.g., "v001")
- `get_latest_version()` - Finds the latest version in a directory

### FileUtils
- `get_sequence_pattern()` - Builds regex patterns for file sequences
- `find_sequence_files()` - Finds files matching a sequence pattern
- `get_thumbnail_path()` - Constructs thumbnail paths with proper extensions

### ImageUtils
- `check_image_bounds()` - Validates image dimensions are within memory limits
- `is_valid_image_file()` - Checks if file is a valid image format

### ValidationUtils
- `validate_shot_components()` - Validates show/sequence/shot names
- `get_current_username()` - Gets current user from environment
- `get_excluded_users()` - Returns set of users to exclude (auto-includes current user)

## Recent Changes

- **Major refactoring**: Implemented comprehensive code improvements across three phases:
  - Phase 1: Enhanced error handling, logging, and resource management
  - Phase 2: Extracted common utilities and centralized configuration
  - Phase 3: Performance optimizations and code standardization
- **Flexible 3DE scene search**: 
  - No longer requires specific directory structure
  - Recursively finds ALL .3de files in user directories
  - Intelligent plate/grouping extraction from arbitrary paths
  - Works with any VFX pipeline directory layout
- **Dynamic user exclusion**: Current user automatically detected and excluded
- **Enhanced logging**: Debug mode with `SHOTBOT_DEBUG=1` environment variable
- **Improved resource management**: Fixed QPixmap memory leaks with proper cleanup
- **Path operation caching**: Improved performance with TTL-based caching