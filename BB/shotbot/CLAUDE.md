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

ShotBot is a PySide6-based GUI application for VFX shot browsing and application launching. It integrates with VFX pipeline tools using the `ws` (workspace) command to list and navigate shots. The application provides a visual interface for artists to browse shots, view thumbnails, and launch VFX applications (3DE, Nuke, Maya, RV) in the correct shot context.

## Critical Commands

### Running the Application

```bash
# Production mode (requires VFX environment)
source venv/bin/activate
python shotbot.py

# Mock mode (no VFX infrastructure needed - 432 production shots)
python shotbot.py --mock
# Or better, with recreated VFX filesystem:
python shotbot_mock.py

# Headless mode (for CI/CD)
python shotbot.py --headless --mock

# Debug mode
SHOTBOT_DEBUG=1 python shotbot.py
```

### Mock VFX Environment

The project includes a sophisticated mock environment system:

```bash
# Recreate VFX filesystem structure (11,386 dirs, 29,335 files)
python recreate_vfx_structure.py vfx_structure_complete.json

# Verify mock environment (shows 432 real production shots)
python verify_mock_environment.py

# Run with full mock environment
python run_mock_vfx_env.py
```

### Testing

```bash
# Quick validation (2 seconds)
python3 tests/utilities/quick_test.py

# Fast test suite (50-60 seconds)
./run_fast_tests.sh

# Full test suite (100-120 seconds, 1,114 tests)
python3 -m pytest tests/

# Specific categories
python3 -m pytest tests/ -m fast       # Tests under 100ms
python3 -m pytest tests/ -m unit       # Unit tests only
python3 -m pytest tests/ -m integration # Integration tests

# Run specific test
python3 -m pytest tests/unit/test_shot_model.py -v
```

### Code Quality

```bash
source venv/bin/activate

# Format code
ruff format .

# Lint and auto-fix
ruff check --fix .

# Type checking
basedpyright
```

## Python Compatibility

- **Minimum**: Python 3.11
- **Uses**: Modern type annotations with union syntax (`str | None`)
- **Critical**: Import `override` from `typing_extensions`, NOT `typing`

```python
# CORRECT (Python 3.11 compatible)
from typing_extensions import override

# WRONG (Python 3.12+ only)
from typing import override  # Will fail on Python 3.11!
```

## High-Level Architecture

### Core Design Pattern: Model-View with Qt Signal-Slot

The application uses Qt's signal-slot mechanism for loose coupling between components. This is critical for understanding how data flows through the application.

### Key Architectural Components

#### 1. Process Pool Management with Dependency Injection
- **`ProcessPoolManager`**: Singleton that manages all subprocess calls with caching and session pooling
- **`ProcessPoolFactory`**: Factory pattern for dependency injection (allows mock injection)
- **`MockWorkspacePool`**: Sophisticated mock that simulates 432 real production shots
- **Critical**: The `ws` command is a shell function, requires interactive bash: `["/bin/bash", "-i", "-c", "ws -sg"]`

#### 2. Model/View Architecture for Shot Display
- **Models** implement `QAbstractItemModel` for efficient data handling
- **Views** use custom delegates for optimized painting
- **Shot flow**: `ws -sg` → `ProcessPool` → `ShotModel` → `ShotItemModel` → `ShotGridView`
- Models emit signals when data changes, views automatically update

#### 3. Cache System (Modular Architecture)
```
cache_manager.py (Facade - maintains backward compatibility)
├── StorageBackend - Atomic file operations
├── FailureTracker - Exponential backoff (5min→15min→45min→2hr)
├── MemoryManager - LRU eviction at 100MB limit
├── ThumbnailProcessor - Multi-format (Qt/PIL/OpenEXR) with HDR
├── ShotCache/ThreeDECache - TTL-based caching (30min default)
└── ThumbnailLoader - Async QRunnable processing
```
- **Cache directories are mode-separated**: production, mock, test (see `cache_config.py`)

#### 4. Thread-Safe Background Operations
- **Workers**: `ThreeDESceneWorker`, `PreviousShotsWorker` use `QThread` for background scanning
- **Thread safety**: All shared data protected with `threading.RLock()`
- **Signal connections**: Use `Qt.ConnectionType.QueuedConnection` for cross-thread
- **Resource cleanup**: Workers properly disconnect signals and delete on completion

#### 5. Launcher System
- **`LauncherManager`**: Manages custom launchers with thread-safe process tracking
- **Process keys**: Timestamp + UUID prevent collisions
- **Terminal integration**: Uses gnome-terminal/konsole for command execution

### Critical Implementation Details

#### QSettings Storage Pattern
```python
# CORRECT - Use .data().decode('ascii')
hex_string = byte_array.data().decode('ascii')
# WRONG - Will corrupt settings
str(byte_array) or byte_array.hex()
```

#### Change Detection Pattern
```python
# refresh_shots() returns RefreshResult(success, has_changes)
success, has_changes = shot_model.refresh_shots()
if success and has_changes:
    # Update UI only when needed
```

#### Resource Management
- QPixmap cleanup prevents memory leaks
- 30-second subprocess timeout prevents hangs
- QThread cleanup with `quit()` and `wait()`

### Key Signals for Component Communication
- `shot_model.shots_updated` → UI refreshes shot grid
- `launcher_manager.command_started/finished` → Progress indicators
- `threede_worker.scene_found` → Progressive UI updates
- `thumbnail_widget.shot_selected` → Updates info panel

## Mock Environment System

The project includes a complete VFX environment simulation:

1. **Capture**: `capture_vfx_structure.py` runs on VFX workstation, outputs JSON
2. **Recreate**: `recreate_vfx_structure.py` rebuilds structure locally
3. **Mock Pool**: `MockWorkspacePool` simulates `ws -sg` with 432 real shots
4. **Dependency Injection**: `ProcessPoolFactory` cleanly swaps implementations
5. **Headless Mode**: Full Qt offscreen support for CI/CD

The mock environment includes:
- 3 shows: broken_eggs (190 shots), gator (69 shots), jack_ryan (173 shots)
- Complete directory structure from production
- Placeholder thumbnails and 3DE files
- Separate cache directories prevent contamination

## Performance Optimizations

- **Parallel filesystem scanning** with `ThreadPoolExecutor`
- **Adaptive UI timers** adjust update frequency based on activity
- **Caching strategy**: 30-min TTL for shots, permanent for thumbnails
- **Progressive loading**: UI shows immediately, data loads in background
- **Optimized painting**: Custom delegates minimize redraws

## Common Development Tasks

### Adding a New Application Launcher
Edit `APPS` in `config.py`:
```python
APPS = {
    "3de": "3de",
    "nuke": "nuke",
    "maya": "maya",
    "your_app": "your_command",  # Add here
}
```

### Debugging Issues
1. Enable debug: `SHOTBOT_DEBUG=1 python shotbot.py`
2. Check process output in log viewer
3. Test workspace: `bash -i -c "ws -sg"`
4. Verify mock environment: `python verify_mock_environment.py`

## Test Organization

- **1,114 tests** with 99.9% pass rate
- **Markers**: `fast`, `slow`, `unit`, `integration`, `qt`, `gui`, `critical`
- **WSL optimizations** in `run_tests_wsl.py`
- **Common issues**: Usually environment setup, not code problems

## Type System

- Uses `RefreshResult` NamedTuple for clear return types
- `Union[str, Path]` for flexible path APIs
- Comprehensive `Optional[QWidget]` handling
- Type checking: `basedpyright` (config in `tests/pyrightconfig.json`)