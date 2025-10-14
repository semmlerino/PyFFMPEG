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

## Development Philosophy & Scope

**Personal VFX Tool**: This is a single-user desktop application for personal VFX workflow needs. While it follows professional coding standards (type safety, testing, clean architecture), it optimizes for maintainability and pragmatic solutions over enterprise concerns.

**What still matters:**
- **Code quality**: Type safety, readable code, proper architecture (future-you deserves good code)
- **Testing**: Comprehensive tests prevent regressions and enable confident refactoring
- **Performance**: Responsive UI, efficient algorithms (this is interactive software)
- **Maintainability**: Clear patterns, good documentation, low technical debt
- **Robustness**: Handle corrupt files, validate inputs, graceful error recovery

**Not applicable (single-user desktop context):**
- **Enterprise security**: No authentication, authorization, or adversarial threat modeling
- **Scale engineering**: No distributed systems, cloud deployment, or ops infrastructure
- **Multi-user patterns**: No concurrent access, locking, or team coordination features
- **Runtime extensibility**: No plugin systems or runtime module loading

**Decision-making guidance**: When choosing between solutions, prefer:
- Simple and working over theoretically perfect
- Pragmatic over defensive (e.g., trust local filesystem, validate user input but not for adversarial attacks)
- Readable over clever (but don't sacrifice performance where it matters)
- "Good enough for single-user" over "scales to enterprise"
- **Example**: Direct JSON serialization is fine; you don't need schema versioning, migration systems, or backward-compatibility layers unless there's a specific reason.

**Professional-quality code for a personal tool, not enterprise software.**

**See also**: `SECURITY_CONTEXT.md` for security-specific guidance on this isolated VFX network environment.

## Critical Commands

### Running the Application

```bash
# Production mode (requires VFX environment)
uv run python shotbot.py

# Mock mode (no VFX infrastructure needed - 432 production shots)
uv run python shotbot.py --mock
# Or better, with recreated VFX filesystem:
uv run python shotbot_mock.py

# Headless mode (for automated testing)
uv run python shotbot.py --headless --mock

# Debug mode
SHOTBOT_DEBUG=1 uv run python shotbot.py
```

### Mock VFX Environment

The project includes a sophisticated mock environment system:

```bash
# Recreate VFX filesystem structure (11,386 dirs, 29,335 files)
uv run python recreate_vfx_structure.py vfx_structure_complete.json

# Verify mock environment (shows 432 real production shots)
uv run python verify_mock_environment.py

# Run with full mock environment
uv run python run_mock_vfx_env.py
```

### Testing

```bash
# Recommended: Full test suite with parallel execution (~67 seconds)
uv run pytest tests/unit/ -n auto --timeout=5

# Quick validation
uv run python tests/utilities/quick_test.py

# Specific test files (sequential)
uv run pytest tests/unit/test_shot_model.py -v

# Categories
uv run pytest tests/ -m fast       # Tests under 100ms
uv run pytest tests/ -m unit       # Unit tests only
uv run pytest tests/ -m integration # Integration tests
```

**Known Issues:**
- Sequential execution may timeout due to Qt resource accumulation
- 2-3 tests fail in parallel mode due to isolation issues (pass when run individually)
- Use parallel execution (`-n auto`) for best results

### Code Quality

```bash
# Format code
uv run ruff format .

# Lint and auto-fix
uv run ruff check --fix .

# Type checking
uv run basedpyright
```

**Configuration**: All tool settings are centralized in `pyproject.toml`:
- `[tool.ruff]` - Linting and formatting rules
- `[tool.basedpyright]` - Type checking configuration (includes Qt-specific suppressions)
- `[tool.pytest.ini_options]` - Test runner settings
- `[tool.coverage.*]` - Coverage configuration

**Do not create** separate config files (`pyrightconfig.json`, `.ruff.toml`, `pytest.ini`) - use `pyproject.toml` instead.

### Development Environment Setup

```bash
# Initial setup (creates .venv, installs dependencies, generates uv.lock)
uv sync

# Add a new dependency
uv add package-name

# Add a development dependency
uv add --dev package-name

# Update all dependencies
uv lock --upgrade

# Update specific package
uv lock --upgrade-package package-name
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

#### 2. Unified Model/View Architecture

The application uses a layered Qt Model/View architecture with shared base classes to eliminate duplication while preserving tab-specific optimizations.

**Architecture Layers:**
```
Data Layer (domain models)
  ↓
BaseItemModel[T] (generic Qt model infrastructure)
  ↓
Specific Item Models (explicit, focused implementations)
  - ShotItemModel
  - ThreeDEItemModel
  - PreviousShotsItemModel
  ↓
View Layer (grid views with custom delegates)
```

**BaseItemModel[T]** - Generic base providing common Qt Model/View infrastructure:
- Atomic thumbnail loading (eliminates race conditions with check-and-mark in single lock)
- Lazy thumbnail loading with visibility tracking
- Thread-safe caching (QMutex-protected QImage storage)
- Selection management and show filtering
- Reduces code duplication by 70-80% across models

**Specific Item Models** - Three explicit, focused implementations:
- **ShotItemModel**: Shot-specific model with shots_updated signal
- **ThreeDEItemModel**: 3DE scene model with loading progress tracking
- **PreviousShotsItemModel**: Previous shots with underlying model integration
- Each model is ~200 lines of clear, single-purpose code
- Zero conditional logic based on item type
- Type-safe with explicit interfaces

**BaseShotModel** - Abstract base for shot data sources:
- Common shot parsing, caching, and performance metrics
- Shared signals and filtering infrastructure
- Uses OptimizedShotParser for performance

**Tab-Specific Stacks:**

**My Shots (Workspace Integration)**
- ShotModel (extends BaseShotModel): Executes `ws -sg` via ProcessPool (30s TTL)
- ShotItemModel: Qt model integration with lazy thumbnails
- ShotGridView: QListView with custom delegate
- Refresh: Synchronous with progress indication

**Other 3DE Scenes (Filesystem Discovery)**
- ThreeDESceneModel: Manages discovered .3de files
- ThreeDEItemModel: Provides filtered view with progressive loading
- ThreeDEGridView: Custom delegate for scene metadata
- ThreeDESceneWorker: QThread for non-blocking filesystem scan
- Refresh: Asynchronous with progressive batch updates

**Previous Shots (Historical Data)**
- PreviousShotsModel (extends BaseShotModel): Finds user's approved/completed shots
- PreviousShotsItemModel: Filters out currently active shots
- PreviousShotsView: Display with auto-refresh timer
- PreviousShotsWorker: Background thread for filesystem traversal
- Refresh: Asynchronous with 5-minute auto-refresh

#### 3. Cache System (Simplified Architecture)

**CacheManager** - Streamlined cache for local VFX tool:
- **API**: Maintains full backward compatibility with all public methods
- **Implementation**: Simplified for secure network environment (no platform-specific locking, atomic writes, or complex failure tracking)
- **Thumbnail Support**: Multi-format (Qt/PIL/OpenEXR) with HDR for VFX workflows
- **Caching Strategy**:
  - Shot/3DE/Previous data: Fixed 30-minute TTL
  - Thumbnails: Persistent cache with on-demand generation
  - Thread-safe: Basic QMutex protection
- **Cache directories**: Mode-separated (production, mock, test via `SHOTBOT_MODE` env var)
- **Storage**: Direct JSON I/O and PIL/OpenEXR processing

#### 4. Thread-Safe Background Operations
- **Workers**: `ThreeDESceneWorker`, `PreviousShotsWorker` use `QThread` for background scanning
- **Thread safety**: Qt components use `QMutex`/`QMutexLocker` for basic thread protection
- **Signal connections**: Use `Qt.ConnectionType.QueuedConnection` for cross-thread communication
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

Each tab has its own data source and optimized architecture:

- **My Shots**: `ws -sg` command (fast, 30s TTL, sync refresh)
- **Other 3DE Scenes**: Filesystem scan (slow, permanent cache, async/progressive)
- **Previous Shots**: User work directories (medium, session cache, 5min auto-refresh)

## Feature Implementation Map

### Show Filtering
- **Implementation**: Pure functional filters in `shot_filter.py` (Protocol-based, composable)
- **My Shots**: shot_grid_view.py → shot_item_model.py → base_shot_model.py → shot_filter.py
- **Other 3DE**: threede_grid_view.py → threede_item_model.py → threede_scene_model.py
- **Previous**: previous_shots_view.py → previous_shots_item_model.py → previous_shots_model.py → shot_filter.py
- **Signal handlers**: main_window.py

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

- **Atomic thumbnail loading**: Eliminates duplicate loads with bulk check-and-mark in single lock
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

- **1,047 tests** (1,044 pass = 99.7% pass rate) - comprehensive coverage enables confident refactoring
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
- Type checking: `basedpyright` (config in `pyproject.toml` under `[tool.basedpyright]`)

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