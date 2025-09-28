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
source venv/bin/activate

# Recommended: Full test suite with parallel execution (~67 seconds)
python3 -m pytest tests/unit/ -n auto --timeout=5

# Quick validation
python3 tests/utilities/quick_test.py

# Specific test files (sequential)
python3 -m pytest tests/unit/test_shot_model.py -v

# Categories
python3 -m pytest tests/ -m fast       # Tests under 100ms
python3 -m pytest tests/ -m unit       # Unit tests only
python3 -m pytest tests/ -m integration # Integration tests
```

**Known Issues:**
- Sequential execution may timeout due to Qt resource accumulation
- 2-3 tests fail in parallel mode due to isolation issues (pass when run individually)
- Use parallel execution (`-n auto`) for best results

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

#### 2. Three Independent Model/View Stacks

Each tab maintains its own architecture optimized for its data source:

**My Shots (Workspace Integration)**
- ShotModel: Executes `ws -sg` via ProcessPool with command-level caching (30s TTL)
- ShotItemModel: QAbstractListModel for Qt view integration
- ShotGridView: QListView with custom delegate for thumbnails
- Refresh: Synchronous with progress indication

**Other 3DE Scenes (Filesystem Discovery)**
- ThreeDESceneModel: Manages discovered .3de files
- ThreeDEItemModel: Provides filtered view of scenes
- ThreeDEGridView: Similar to ShotGridView but scene-focused (NOTE: Not threede_shot_grid.py)
- ThreeDESceneWorker: QThread for non-blocking filesystem scan
- Refresh: Asynchronous with progressive batch updates

**Previous Shots (Historical Data)**
- PreviousShotsModel: Finds user's approved/completed shots
- PreviousShotsItemModel: Filters out currently active shots
- PreviousShotsView: Display with auto-refresh timer
- PreviousShotsWorker: Background thread for filesystem traversal
- Refresh: Asynchronous with 5-minute auto-refresh

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
- **Show Filter Signals (added to all tabs)**:
  - `shot_grid.show_filter_requested` → `_on_shot_show_filter_requested`
  - `threede_grid.show_filter_requested` → `_on_show_filter_requested`
  - `previous_shots_grid.show_filter_requested` → `_on_previous_show_filter_requested`

## Tab Architecture: Three Distinct Data Sources

The application's three tabs are NOT different views of the same data. They represent fundamentally different data sources:

### My Shots Tab
- **Data Source**: `ws -sg` command via ProcessPoolManager
- **Performance**: Fast (cached subprocess call)
- **Update Pattern**: On-demand with user-triggered refresh
- **Caching**: 30-second TTL at command level
- **Model Stack**: ShotModel → ShotItemModel → ShotGridView

### Other 3DE Scenes Tab
- **Data Source**: Filesystem scanning for .3de files
- **Performance**: Slow (I/O intensive, thousands of directories)
- **Update Pattern**: Progressive updates during scan
- **Caching**: Permanent until invalidated
- **Model Stack**: ThreeDESceneModel → ThreeDEItemModel → ThreeDEGridView

### Previous Shots Tab
- **Data Source**: Filesystem scanning for user work directories
- **Performance**: Medium (targeted filesystem search)
- **Update Pattern**: 5-minute auto-refresh
- **Caching**: Session-based
- **Model Stack**: PreviousShotsModel → PreviousShotsItemModel → PreviousShotsView

## Why Three Separate Architectures?

This separation is intentional and beneficial:

1. **Different Performance Characteristics** - Each data source has unique I/O patterns
2. **Different Update Requirements** - Sync vs async, progressive vs batch
3. **Different Caching Strategies** - TTL vs permanent vs session-based
4. **Domain-Specific Optimizations** - Each tab can evolve independently
5. **Testability** - Each stack can be tested in isolation with appropriate mocks

The apparent "duplication" is actually proper separation of concerns for distinct workflows.

## Feature Implementation Map

### Show Filtering (Recently Added to All Tabs)
- **My Shots**: shot_grid_view.py → shot_item_model.py → base_shot_model.py
- **Other 3DE**: threede_grid_view.py → threede_item_model.py → threede_scene_model.py
- **Previous**: previous_shots_view.py → previous_shots_item_model.py → previous_shots_model.py
- **Signal handlers**: main_window.py (lines 1260-1300)

### Data Refresh Paths
- **My Shots**: shot_model.py:refresh_strategy() → ProcessPool.execute_workspace_command()
- **Other 3DE**: threede_scene_worker.py → ThreeDESceneFinder (parallel filesystem scan)
- **Previous**: previous_shots_worker.py → ParallelShotsFinder.find_user_shots()

### Cross-Tab Features
- **Synchronized thumbnail sizing**: All tabs share slider synchronization
- **Show filter**: Available on all tabs with consistent UI (QComboBox)
- **Cache manager**: Shared instance across all tabs

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
- **Tab-specific caching strategies**:
  - My Shots: 30-second TTL for `ws -sg` command results
  - Other 3DE: Permanent cache until manually invalidated
  - Previous Shots: Session-based caching with 5-minute refresh
  - Thumbnails: Permanent cache across all tabs
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

- **1,047 tests** (1,044 pass = 99.7% pass rate)
- **Markers**: `fast`, `slow`, `unit`, `integration`, `qt`, `gui`, `critical`
- **Execution time**: ~67 seconds with parallel execution (`-n auto`)
- **Recent fixes**:
  - Removed all `pytest.skip()` tests
  - Fixed MRO issues in `launcher_panel.py` (duplicate LoggingMixin)
  - Optimized Qt cleanup fixtures (reduced timeouts to 0.1s)
  - Fixed ProcessPoolManager `_mutex` attribute and shutdown

## Type System

- Uses `RefreshResult` NamedTuple for clear return types
- `Union[str, Path]` for flexible path APIs
- Comprehensive `Optional[QWidget]` handling
- Type checking: `basedpyright` (config in `tests/pyrightconfig.json`)

## Bundling and Distribution System

Automated post-commit hooks create base64-encoded releases in `encoded-releases/` branch.

### Configuration
**File:** `transfer_config.json` - Controls which files get bundled
- **Include**: `*.py`, `*.json`, `*.md`, `wrapper/*` (for extension-less scripts)
- **Exclude**: `test_*.py`, `*_test.py`, `tests/`, `venv*/`

### Critical Issue Fixed
**Bug**: Pattern `test_*.py` matched ANY file containing "test" (e.g., `threede_latest_finder.py`)
**Fix**: Anchored regex patterns to start: `test_*.py` → `^test_.*\.py$` not `test_.*\.py$`

### Debugging Commands
```bash
# Verify file inclusion before committing
python3 bundle_app.py --list-files -c transfer_config.json | grep "your_file"

# Test specific file
python3 -c "from bundle_app import ApplicationBundler; print(ApplicationBundler('transfer_config.json').should_include_file('file.py'))"
```

### Bundle Verification
- Expected: ~189 files, ~1.8MB compressed
- Always verify new files appear in bundle after adding them
- Extension-less files need explicit directory patterns (`wrapper/*`)