# Shotbot Comprehensive Architecture Overview

## Executive Summary

Shotbot is a sophisticated PySide6-based VFX production management GUI application with a layered, modular architecture. It demonstrates enterprise-level design patterns including:

- **Separation of Concerns**: Clear boundaries between UI, business logic, and system integration
- **Dependency Injection**: Loosely coupled components for testability
- **Generic Base Classes**: 70-80% code reuse through inheritance hierarchies
- **Multi-threaded Processing**: Async/await patterns with Qt signal/slot coordination
- **Smart Caching Strategies**: Incremental persistent caching with TTL management
- **Plugin Architecture Foundation**: Extensible launcher and renderer systems

---

## 1. OVERALL ARCHITECTURE LAYERS

```
┌─────────────────────────────────────────────────────────────┐
│                    PRESENTATION LAYER (Qt UI)              │
│  MainWindow, Tabs (3), Panels, Dialogs, Grid Views         │
├─────────────────────────────────────────────────────────────┤
│                  CONTROLLER LAYER (Coordination)             │
│  LauncherController, SettingsController, ThreeDEController  │
├─────────────────────────────────────────────────────────────┤
│           MODEL LAYER (Business Logic & Data)                │
│  ShotModel, ThreeDESceneModel, PreviousShotsModel           │
│  BaseItemModel, BaseShotModel (Generic Bases)               │
├─────────────────────────────────────────────────────────────┤
│            SYSTEM INTEGRATION LAYER (I/O & Execution)       │
│  ProcessPoolManager, LauncherProcessManager, LauncherWorker │
│  CacheManager, Workspace Commands, File System Operations   │
├─────────────────────────────────────────────────────────────┤
│                   INFRASTRUCTURE LAYER                       │
│  Threading utilities, Logging, Error handling, Config       │
└─────────────────────────────────────────────────────────────┘
```

### Key Architectural Decisions

1. **Three Independent Tab Systems**: Rather than one unified model with different views, Shotbot implements three separate, parallel data pipelines for "My Shots", "3DE Scenes", and "Previous Shots". Each has its own:
   - Data Source (workspace command, filesystem scan, historical log)
   - Model (ShotModel, ThreeDESceneModel, PreviousShotsModel)
   - Item Model (Qt model for UI binding)
   - View (Grid with custom delegates)
   - Worker Thread (for background operations)

   **Rationale**: Explicit implementations avoid complex conditional logic and allow independent optimization.

2. **Generic Base Classes for Code Reuse**: 
   - `BaseItemModel[T]`: Generic Qt model with lazy thumbnail loading
   - `BaseShotModel`: Common shot parsing and caching logic
   - `BaseGridView`: Shared grid view functionality
   - Custom delegates for rendering

   **Benefit**: ~70-80% code reuse while maintaining explicitness

3. **Subprocess Pool Architecture**: 
   - `ProcessPoolManager`: Singleton managing concurrent command execution
   - Caches workspace command results
   - Round-robin session load balancing
   - Supports batch operations

4. **Process Lifecycle Management**:
   - `LauncherProcessManager`: Tracks active processes and workers
   - `LauncherWorker`: QThread-based command execution
   - Graceful shutdown with cleanup timers
   - Signal-based communication

---

## 2. KEY COMPONENTS & THEIR RESPONSIBILITIES

### 2.1 PRESENTATION LAYER

#### MainWindow (main_window.py)
**Responsibilities**:
- Application window and layout management
- Tab coordination (My Shots, 3DE Scenes, Previous Shots)
- Signal routing between models and UI components
- Session warming and startup optimization
- Crash recovery dialog coordination
- Thumbnail size synchronization across tabs

**Key Attributes**:
- `cache_manager`: CacheManager singleton
- `shot_model`: Workspace-based shots data
- `threede_scene_model`: 3DE filesystem discovery
- `previous_shots_model`: Historical shots
- `launcher_controller`: Application launch coordination
- `threede_controller`: 3DE-specific actions
- `refresh_orchestrator`: Manages periodic data refresh
- `launcher_manager`: Process lifecycle tracking

**Signal Patterns**:
- Emits: `update_status()`, `closing()`
- Listens to: Model changes, filter requests, selection events, tab changes

**Design Notes**:
- Acts as a facade coordinating multiple models and controllers
- Uses property decorators for thread-safe state storage
- Cleanup methods ensure proper shutdown sequence

#### UI Component Stack

**Grid Views** (ShotGridView, ThreeDEGridView):
- Custom subclass of QListView with model delegation
- Supports pinch/scroll zoom
- Shows/hides filter bars based on context

**Delegates** (ShotGridDelegate, ThreeDEGridDelegate):
- Paint thumbnails with overlays
- Custom size hints for responsive layout
- Hover effects and visual feedback

**Panels**:
- `ShotInfoPanel`: Displays selected shot metadata
- `LauncherPanel`: Application launch buttons and controls
- `LogViewer`: Command execution log display

**Dialogs**:
- `SettingsDialog`: Application preferences
- `LauncherDialog`: Launcher management UI
- `ThreeDERecoveryDialog`: Crash file recovery

### 2.2 CONTROLLER LAYER

#### LauncherController (controllers/launcher_controller.py)
**Responsibilities**:
- Manages application launch coordination
- Builds launch commands based on shot/scene context
- Handles custom launcher configuration
- Communicates with LauncherProcessManager
- Updates launcher UI availability
- Implements retry logic for failed launches

**Key Methods**:
- `launch_app(app_name)`: Main launch entry point
- `set_current_shot(shot)`: Updates context
- `set_current_scene(scene)`: Updates scene context
- `get_launch_options()`: Returns available launch apps
- `update_launcher_menu()`: Updates menu based on available launchers
- `execute_custom_launcher()`: Runs user-configured launchers

**Signal Integration**:
- Connects to: Process manager signals (started, finished, error)
- Emits: launcher availability changes, status updates

**Design Pattern**: 
- Acts as bridge between UI layer and execution layer
- Encapsulates launch logic complexity
- Supports both standard and custom launchers

#### SettingsController
- Manages application preferences
- Persists settings to config files
- Validates user input

#### ThreeDEController
- Handles 3DE-specific actions
- Scene recovery and restoration
- Integration with 3DE file system

### 2.3 MODEL LAYER - DATA & BUSINESS LOGIC

#### Three Parallel Data Pipelines

##### PIPELINE 1: My Shots (Workspace Integration)

**ShotModel** (shot_model.py):
```
Workspace Command (ws -sg)
    ↓
AsyncShotLoader (Background Thread)
    ↓
Shot Parsing (optimized_shot_parser.py)
    ↓
CacheManager (Persistent/Time-based)
    ↓
ShotItemModel (Qt Model)
    ↓
ShotGridView (UI Rendering)
```

**Responsibilities**:
- Executes `ws -sg` command via ProcessPoolManager
- Parses shot data (show, sequence, shot, path, etc.)
- Manages background refresh with change detection
- Caches results with 30-minute TTL
- Emits signals: `background_load_started`, `background_load_finished`, `shots_changed`

**Key Features**:
- Async initialization with `initialize_async()`
- Session pre-warming for performance
- Performance metrics tracking (load time, cache hits/misses)
- Incremental refresh detecting only changed shots

##### PIPELINE 2: 3DE Scenes (Filesystem Discovery)

**ThreeDESceneModel** (threede_scene_model.py):
```
Filesystem Scan (Background Thread)
    ↓
3DE File Discovery (threede_scene_finder.py)
    ↓
Scene Parsing (scene_parser.py)
    ↓
CacheManager (Persistent, No TTL)
    ↓
ThreeDEItemModel (Qt Model with Filtering)
    ↓
ThreeDEGridView (UI Rendering)
```

**Responsibilities**:
- Scans filesystem for .3de files
- Discovers scenes created by all users across all shows
- Maintains persistent incremental cache (no expiration)
- Merges cached scenes with fresh discoveries
- Deduplicates: keeps best scene per shot (mtime + plate priority)

**Caching Strategy**:
- Load persistent cache (no TTL check)
- Discover fresh scenes from filesystem
- Merge: cached + fresh (preserves history)
- Deduplicate: best scene wins
- Write merged result back to cache

**Design Note**: Scene history is preserved even after deletion

##### PIPELINE 3: Previous Shots (Historical Data)

**PreviousShotsModel** (previous_shots_model.py):
```
Workspace Command (Approved/Completed Shots)
    ↓
Historical Analysis (User's previous work)
    ↓
Filtering (Excludes current shots)
    ↓
CacheManager (Persistent)
    ↓
PreviousShotsItemModel (Qt Model)
    ↓
PreviousShotsView (Grid)
```

**Responsibilities**:
- Maintains history of approved/completed shots
- Excludes currently active shots from "My Shots"
- Auto-refresh when new shots are migrated from My Shots
- Persistent caching (survives application restarts)

#### Base Classes (Generic Infrastructure)

**BaseShotModel** (base_shot_model.py):
- Shared shot parsing logic
- Workspace command execution
- Result caching
- Inherited by ShotModel and PreviousShotsModel

**BaseItemModel[T]** (base_item_model.py):
```python
Generic Qt AbstractListModel with:
- Lazy thumbnail loading
- Visible range optimization (viewport-aware)
- Batch update debouncing
- Selection management
- Custom role data support
- Thread-safe thumbnail caching

Emits: items_updated, thumbnail_loaded, selection_changed
```

**Features**:
- `set_visible_range(start, end)`: Viewport optimization
- `_load_visible_thumbnails()`: Lazy load only visible items
- `_emit_batched_updates()`: Debounce model change notifications
- Custom role support for extensibility

**BaseGridView** (base_grid_view.py):
- Common grid view functionality
- Custom item delegates
- Responsive layout management

### 2.4 SYSTEM INTEGRATION LAYER

#### ProcessPoolManager (process_pool_manager.py)
**Architecture**: Singleton with multi-level pooling

```
Workspace Command Request
    ↓
ProcessPoolManager.execute_workspace_command()
    ↓
Session Round-Robin Load Balancing
    ↓
ThreadPoolExecutor (Python subprocess)
    ↓
Workspace Command Execution
    ↓
Result Caching (CommandCache)
    ↓
Return to Caller
```

**Responsibilities**:
- Maintains thread pool of workspace sessions
- Round-robin load balancing across sessions
- Caches command results to reduce redundant execution
- Batch execution support
- Metrics tracking (hit/miss, execution time)
- Graceful shutdown with thread cleanup

**Key Methods**:
- `execute_workspace_command(cmd)`: Execute with caching
- `batch_execute(commands)`: Parallel execution of multiple commands
- `find_files_python(pattern)`: Python-based file discovery
- `get_metrics()`: Performance metrics
- `shutdown()`: Cleanup and thread termination

**Design Pattern**:
- Lazy initialization of session pools
- Reusable sessions (no recreation per command)
- Exception handling with automatic cleanup
- Thread-safe singleton (double-checked locking)

#### LauncherProcessManager (launcher/process_manager.py)
**Responsibilities**:
- Tracks active processes and workers
- Two execution modes:
  1. Direct subprocess (simple/quick commands)
  2. Threaded worker (long-running processes)
- Automatic cleanup of finished processes
- Periodic cleanup scheduling with retry mechanism
- Signal-based process lifecycle events

**Key Features**:
- `execute_with_subprocess()`: Simple command execution
- `execute_with_worker()`: Threaded execution with full lifecycle tracking
- `terminate_process(process_key)`: Graceful termination
- `stop_all_workers()`: Shutdown all active workers
- Cleanup timers with exponential backoff

**Signal Pattern**:
- `process_started(process_key)`
- `process_finished(process_key, result)`
- `process_error(process_key, error)`
- `worker_created(worker_id)`
- `worker_removed(worker_id)`

#### LauncherWorker (launcher/worker.py)
**Responsibilities**:
- Executes commands in a dedicated QThread
- Command sanitization and security validation
- Process lifecycle management (creation, monitoring, termination)
- Exception handling and error reporting
- Cleanup of resources on completion

**Key Methods**:
- `do_work()`: Main execution loop
- `_sanitize_command()`: Command validation and escaping
- `_terminate_process()`: Graceful process termination
- `request_stop()`: Signal worker to stop

**Design Note**: Uses QThread with moved-to-thread pattern for safety

#### CacheManager (cache_manager.py)
**Multi-level Caching Strategy**:

```
Memory Cache (Runtime)
    ↓
Disk Cache (Persistent)
    ↓
TTL Management (Optional)
    ↓
Incremental Merge (For scenes)
```

**Cache Types**:

1. **Shot Cache**:
   - File: `~/.shotbot/cache/production/shots.json`
   - TTL: 30 minutes (configurable)
   - Strategy: Complete replacement on refresh
   - Data: All shot metadata

2. **Previous Shots Cache**:
   - File: `~/.shotbot/cache/production/previous_shots.json`
   - TTL: None (persistent)
   - Strategy: Incremental accumulation
   - Data: Historical shot records

3. **3DE Scenes Cache**:
   - File: `~/.shotbot/cache/production/threede_scenes.json`
   - TTL: None (persistent)
   - Strategy: Persistent incremental with deduplication
   - Data: Scene metadata, file paths, creation timestamps

4. **Thumbnail Cache**:
   - Directory: `~/.shotbot/cache/thumbnails/`
   - Format: JPG (converted from various formats)
   - Caching: Direct file-based with path hashing

5. **Generic Data Cache**:
   - Key-value pairs with optional expiration
   - Thread-safe access with locks

**Key Methods**:
- `get_cached_shots()`: Load shots from cache
- `cache_shots(shots)`: Save shots with TTL
- `get_persistent_threede_scenes()`: Load 3DE cache without TTL check
- `merge_scenes_incremental(cached, fresh)`: Intelligent merge
- `cache_thumbnail(shot, pixmap)`: Store image with compression
- `clear_cache()`: Full cache invalidation

**Thread Safety**:
- Uses RLock for concurrent access
- JSON serialization is atomic
- Thumbnail operations are synchronized

---

## 3. DATA FLOW PATTERNS

### 3.1 Shot Loading Flow (My Shots)

```
User Clicks Tab
    ↓
MainWindow._on_tab_changed()
    ↓
ShotModel.load_shots()
    ↓
CacheManager.get_cached_shots()
        ├─ Cache Hit → Return immediately
        └─ Cache Miss → Continue to fetch
    ↓
ProcessPoolManager.execute_workspace_command("ws -sg")
    ↓
AsyncShotLoader (Background Thread)
    ├─ optimized_shot_parser.parse_shots(ws_output)
    └─ Emit: background_load_finished(shots)
    ↓
ShotModel._on_shots_loaded(shots)
    ├─ Validate shots
    ├─ Emit: background_load_finished(shots)
    └─ Cache results
    ↓
MainWindow._on_shots_loaded(shots)
    ├─ ShotItemModel.set_items(shots)
    └─ Emit: items_updated
    ↓
ShotGridView (Qt Rendering)
    ├─ Creates item delegates
    └─ Lazy load thumbnails on viewport change
```

### 3.2 Thumbnail Loading Flow

```
ShotGridView Scrolls / Viewport Changes
    ↓
BaseItemModel.set_visible_range(start, end)
    ↓
BaseItemModel._load_visible_thumbnails()
    ├─ Debounce timer (100ms)
    └─ Call: _do_load_visible_thumbnails()
    ↓
For Each Visible Item:
    ├─ Check Memory Cache (_pixmap_cache)
    │   ├─ Hit → Use pixmap immediately
    │   └─ Miss → Continue to disk cache
    ├─ Check Disk Cache (CacheManager)
    │   ├─ Hit → Load from disk, cache in memory
    │   └─ Miss → Continue to source file
    ├─ Load from Source (JPEG, EXR, PIL)
    │   ├─ Scale to thumbnail size
    │   ├─ Convert to JPG
    │   └─ Save to disk cache
    ├─ Load into Memory Cache
    └─ Emit: thumbnail_loaded(index)
    ↓
MainWindow._on_tab_changed()
    └─ ShotItemModel.data(index, DisplayRole)
        └─ Return cached pixmap
    ↓
ShotGridView Delegate Renders Pixmap
```

### 3.3 Application Launch Flow

```
User Selects Shot & Clicks App Button
    ↓
MainWindow._on_shot_selected(shot)
    ├─ Set shot in LauncherController
    └─ Update launcher panel
    ↓
LauncherPanel.launch_app(app_name)
    ↓
MainWindow.launch_app(app_name)
    ↓
LauncherController.launch_app(app_name)
    ├─ get_launch_options() → Get available apps
    ├─ Build launch command based on app & shot context
    └─ LauncherProcessManager.execute_with_worker()
    ↓
LauncherWorker (QThread)
    ├─ _sanitize_command() → Validate & escape
    └─ Popen(command, ..., shell=True)
    ↓
External Application Starts
    ├─ Emit: command_started(launcher_id)
    └─ Monitor process until completion
    ↓
LauncherProcessManager._on_worker_finished()
    ├─ Emit: process_finished(key, result)
    └─ Schedule cleanup
    ↓
LauncherController._on_launcher_finished()
    └─ LogViewer.append_log(result)
```

### 3.4 Refresh Orchestration

```
Timer Trigger OR User Action (Refresh Button)
    ↓
RefreshOrchestrator Coordinates:
    ├─ ShotModel.refresh_strategy()
    │   ├─ Check for changes vs cached
    │   ├─ Load fresh shots
    │   └─ Emit: shots_changed(diff)
    ├─ ThreeDESceneModel refresh
    │   ├─ Scan filesystem
    │   ├─ Merge with cache
    │   └─ Emit: scenes_changed
    └─ PreviousShotsModel refresh
        └─ Emit: previous_shots_updated
    ↓
MainWindow Signal Handlers
    ├─ _on_shots_changed() → Update shot view
    ├─ Update status bar with change count
    └─ Optionally migrate shots to previous
```

---

## 4. DEPENDENCY PATTERNS & INJECTION

### Component Dependency Graph

```
MainWindow
├── CacheManager (singleton)
├── ProcessPoolManager (singleton)
├── RefreshOrchestrator
│   ├── ShotModel
│   │   ├── ProcessPoolManager
│   │   └── CacheManager
│   ├── ThreeDESceneModel
│   │   ├── ThreadPool (worker)
│   │   └── CacheManager
│   └── PreviousShotsModel
│       ├── ProcessPoolManager
│       └── CacheManager
├── ShotItemModel (Qt Model)
│   ├── ShotModel (data source)
│   ├── BaseItemModel
│   │   ├── CacheManager
│   │   └── ThreadPool (thumbnail loading)
│   └── ShotGridView (UI)
│       └── ShotGridDelegate
├── LauncherController
│   └── LauncherProcessManager (singleton)
│       ├── ThreadPool (execution)
│       └── LauncherWorker (QThread-based)
├── SettingsController
│   └── SettingsManager
└── ThreeDEController
    └── ThreeDESceneModel
```

### Dependency Injection Patterns

1. **Constructor Injection** (Models):
```python
class ShotModel(BaseShotModel):
    def __init__(self, pool: ProcessPoolManager, cache: CacheManager):
        self.pool = pool
        self.cache = cache
```

2. **Property Injection** (Controllers):
```python
class LauncherController:
    def __init__(self, window: MainWindow):
        self.window = window  # Access to managers via window
```

3. **Singleton Access** (Shared Resources):
```python
pool = ProcessPoolManager.get_instance()
cache = CacheManager()  # Thread-local instance
```

### Loose Coupling Benefits

- Models don't know about UI layer
- Controllers mediate between models and UI
- Easy to test with mock implementations
- Swap implementations without changing callers

---

## 5. PLUGIN/EXTENSION POINTS

### 5.1 Launcher System Extensibility

**Custom Launcher Configuration** (settings_manager.py):
```json
{
  "custom_launchers": [
    {
      "name": "Custom App",
      "command": "custom_cmd {shot_path} {workspace}",
      "enabled": true
    }
  ]
}
```

**Extension Point**: `LauncherController.execute_custom_launcher()`
- Reads config from settings
- Variable substitution ({shot_path}, {workspace}, etc.)
- Executes via LauncherProcessManager

### 5.2 Finder System

**Architecture**: Abstract base class + specific implementations

```
BaseFinder (Abstract)
├── ThreeDESceneFinder
│   ├── Filesystem scanning
│   └── File filtering
├── ThreeDELatestFinder
│   └── Returns most recent scene
├── PreviousShotsFinder
│   └── Historical analysis
├── RawPlateFinder
│   └── Media file discovery
└── UndistortionFinder
    └── Calibration data discovery
```

**Extension Point**: Implement custom Finder subclass

### 5.3 Renderer/Model Extensibility

**New Tab Support**: 
1. Create new Model (inherit from BaseShotModel or implement protocol)
2. Create ItemModel (inherit from BaseItemModel[T])
3. Create GridView (inherit from BaseGridView)
4. Register in MainWindow._setup_ui()

**Example**: Adding "Render Queue" tab would follow same pattern

### 5.4 Configuration Extensibility

**Settings Management** (settings_manager.py):
- Validates against schema
- Supports import/export
- Observable changes (signals)

**Plugin Settings**: Add new sections to settings schema

---

## 6. CONFIGURATION MANAGEMENT

### Config Files

**Location**: `~/.shotbot/`

```
~/.shotbot/
├── cache/              # Runtime cache data
│   ├── thumbnails/    # Image cache
│   └── production/     # JSON caches
├── settings.json       # User preferences
├── custom_launchers.json  # User-defined commands
└── session_state.json  # Window geometry, selections
```

### Configuration Components

**config.py**:
- Application constants
- Default paths
- UI dimensions
- Cache settings

**SettingsManager** (settings_manager.py):
- Loads/saves settings from JSON
- Validates settings schema
- Emits change signals
- Supports import/export

**EnvironmentConfig**:
- VFX environment detection (Maya, Nuke paths, etc.)
- Production/mock mode handling
- Workspace command customization

### Customization Points

1. **Cache TTL**: Adjustable per cache type
2. **Thumbnail Size**: User-configurable with zoom
3. **Launcher Commands**: Custom app definitions
4. **Refresh Intervals**: Periodic update timing
5. **Search Paths**: 3DE scene scanning locations

---

## 7. THREADING & CONCURRENCY

### Threading Architecture

```
Main Thread (Qt Event Loop)
├── UI Updates
├── Signal Emission
└── Model Coordination

Worker Threads:
├── AsyncShotLoader (Load shots from workspace)
├── ThreeDESceneWorker (Filesystem scan)
├── PreviousShotsWorker (Historical analysis)
├── LauncherWorker (Command execution)
└── Thumbnail Loaders (Image processing)

Thread Pool:
└── ProcessPoolManager (Workspace command execution)
```

### Synchronization Strategy

1. **Qt Signals**: Cross-thread communication
2. **Locks/Mutexes**: Protected shared state
   - CacheManager uses RLock
   - ProcessPoolManager uses threading.Lock
3. **Queue-based**: Batch updates to avoid flooding

### Data Flow Safety

- Models run on main or worker threads
- Results returned via signals
- UI updates always on main thread
- Cache access is thread-safe

---

## 8. DESIGN PATTERNS USED

### 1. **Model-View-Controller (MVC)**
- Model: ShotModel, ThreeDESceneModel, etc.
- View: Grid views and custom delegates
- Controller: LauncherController, SettingsController

### 2. **Singleton**
- ProcessPoolManager: Global subprocess pool
- CacheManager: Per-application instance

### 3. **Factory**
- OptimizedShotParser: Creates Shot objects
- ThumbnailCacheLoader: Creates thumbnail objects

### 4. **Observer/Signals**
- Qt signal/slot for async communication
- Models emit changes, UI listens

### 5. **Strategy**
- Different refresh strategies per model
- Plugin launchers vs built-in launchers
- Scene deduplication strategies

### 6. **Template Method**
- BaseShotModel defines flow, subclasses implement specifics
- BaseItemModel defines Qt model protocol

### 7. **Facade**
- MainWindow coordinates multiple systems
- LauncherController abstracts launch complexity

### 8. **Command**
- LauncherWorker wraps command execution
- Supports undo/redo patterns (not currently used)

### 9. **Decorator**
- Custom delegates add rendering to base Qt models
- Mixins add functionality (logging, versioning, etc.)

### 10. **Lazy Initialization**
- ProcessPoolManager creates sessions on-demand
- Thumbnails load on viewport change
- Settings loaded only when accessed

---

## 9. KEY PERFORMANCE OPTIMIZATIONS

### Caching Strategies

1. **Multi-level Thumbnail Caching**:
   - Memory cache (fast, limited)
   - Disk cache (persistent)
   - Source files (slow, original quality)

2. **Incremental Scene Caching**:
   - Preserve deleted scenes in cache
   - Only merge new discoveries
   - Deduplication per shot

3. **Command Result Caching**:
   - Cache workspace command results
   - Avoid redundant execution
   - 30-minute TTL for safety

### Viewport Optimization

1. **Lazy Thumbnail Loading**:
   - Only load visible items
   - Debounce rapid scrolling
   - Parallel loading where safe

2. **Batch Update Debouncing**:
   - Collect changes in 100ms window
   - Emit single update signal
   - Reduces Qt model notification overhead

### Computation Optimization

1. **Session Pool Reuse**:
   - Create workspace sessions once
   - Reuse across multiple commands
   - Reduce session creation overhead

2. **Optimized Parsing**:
   - optimized_shot_parser.py uses regex
   - Minimal object creation
   - Direct data extraction

### Memory Management

1. **Pixmap Caching**:
   - Keep only visible thumbnails in memory
   - Evict on view change
   - Regular cleanup cycles

2. **Cleanup Timers**:
   - Periodic process cleanup
   - Deferred worker termination
   - Prevents resource leaks

---

## 10. ERROR HANDLING & RECOVERY

### Error Hierarchy

```
VFX Environment Error
├── Workspace Not Found
├── Command Execution Failed
└── Scene Parsing Error

Application Error
├── Cache Corruption
├── File System Error
└── Resource Exhaustion

UI Error
├── Invalid Selection
├── Missing Dependencies
└── Configuration Error
```

### Recovery Mechanisms

1. **Graceful Degradation**:
   - Fall back to empty cache on JSON error
   - Continue with available data
   - Log errors for debugging

2. **Retry Logic**:
   - Workspace commands: retry with backoff
   - Process cleanup: scheduled retries
   - Thumbnail loading: skip failed items

3. **User Recovery**:
   - Crash recovery dialog for 3DE files
   - Manual cache clearing
   - Settings reset to defaults

4. **Logging**:
   - Comprehensive logging throughout
   - Performance metrics tracking
   - Error diagnostics in log files

---

## 11. TESTING ARCHITECTURE

### Test Structure

```
tests/
├── unit/              # Isolated component tests
│   ├── test_shot_model.py
│   ├── test_cache_manager.py
│   ├── test_base_item_model.py
│   └── ...
├── integration/       # Multi-component tests
│   ├── test_user_workflows.py
│   ├── test_launcher_integration.py
│   └── ...
├── fixtures/          # Shared test data & mocks
│   ├── conftest.py
│   └── test_doubles.py
└── test_doubles.py    # Mock implementations
```

### Testing Patterns

1. **Dependency Injection**: Models accept mock pool/cache
2. **Mock Workspace**: MockWorkspacePool simulates workspace
3. **Qt Testing**: pytest-qt for widget tests
4. **Async Testing**: Fixtures for background loader testing

### Coverage

- 755+ tests passing
- Comprehensive coverage of:
  - Core business logic (models)
  - Controllers and managers
  - UI components (Qt widgets)
  - Integration scenarios

---

## 12. DEPLOYMENT & EXTENSIBILITY

### Deployment Mechanism

```
Development (master branch)
    ↓
Post-commit Hook
├── Type checking (basedpyright)
├── Linting (ruff)
└── Bundle creation (bundle_app.py)
    ↓
Encoded Release Bundle
├── Base64-encoded tar.gz
├── Transfer config included
└── Metadata JSON
    ↓
GitHub (encoded-releases branch)
    ↓
Remote VFX Server
├── Decode bundle
└── Extract and run
```

### Extension Points for New Features

1. **New Tab/Data Source**:
   - Implement model following ShotModel pattern
   - Create ItemModel, GridView, Delegates
   - Register in MainWindow

2. **New Launcher Type**:
   - Add to custom_launchers config
   - Or implement custom finder

3. **New Cache Type**:
   - Add to CacheManager methods
   - Define TTL and merge strategy

4. **New Controller Functionality**:
   - Extend existing controller or create new
   - Register signals in MainWindow
   - Add UI components as needed

---

## 13. KEY METRICS & MONITORING

### Performance Metrics Tracked

1. **Shot Loading**:
   - Initial load time
   - Cache hit/miss ratio
   - Background load duration

2. **Process Execution**:
   - Command execution time
   - Worker creation/cleanup time
   - Active process count

3. **Cache Efficiency**:
   - Memory usage
   - Thumbnail cache hit rate
   - Command cache hit rate

4. **UI Responsiveness**:
   - Thumbnail load latency
   - Model update frequency
   - Viewport change responsiveness

### Debugging Support

- Verbose logging in DEBUG_VERBOSE mode
- Performance profiling hooks
- Memory usage tracking
- Process lifecycle logging

---

## SUMMARY

Shotbot demonstrates a **mature, enterprise-grade architecture** with:

✅ **Clear separation of concerns** across layers
✅ **Flexible, extensible design** through inheritance and composition
✅ **Smart caching** with multiple strategies
✅ **Thread-safe operations** with proper synchronization
✅ **Comprehensive error handling** and recovery
✅ **Excellent testability** through dependency injection
✅ **Performance optimization** at every level
✅ **User customization** through configuration
✅ **Graceful degradation** when issues occur

The codebase is suitable for:
- Production VFX pipelines
- Team collaboration (multiple scenes, users)
- Long-running sessions (robust cleanup)
- Future enhancement (extension points)
