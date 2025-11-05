# Shotbot: Detailed Design Decisions & Patterns

## CORE ARCHITECTURAL DECISIONS

### Decision 1: Three Separate Tab Systems vs. Single Unified Model

**Problem**: Manage three different data sources (workspace commands, filesystem, historical) with different update strategies, caching needs, and UI representations.

**Solution Evaluated**:
1. Single model with conditional logic
2. Three separate parallel implementations

**Choice**: THREE SEPARATE IMPLEMENTATIONS

**Rationale**:
- **Explicitness over Cleverness**: Each tab system is self-contained and easy to understand
- **Independent Optimization**: Can tune each system (caching, refresh rate, filtering) independently
- **Reduced Coupling**: Changes to one tab don't affect others
- **70-80% Code Reuse**: Base classes capture common patterns without forced unification
- **Testing Simplicity**: Can test each flow in isolation
- **Maintenance**: Engineers can understand one flow completely without the big picture

**Implementation**:
```
My Shots Tab:
├─ ShotModel (executes ws -sg)
├─ ShotItemModel (Qt model)
├─ ShotGridView (custom grid)
└─ CacheManager (30-min TTL)

3DE Scenes Tab:
├─ ThreeDESceneModel (filesystem scan)
├─ ThreeDEItemModel (Qt model + filtering)
├─ ThreeDEGridView (custom grid)
└─ CacheManager (persistent, no TTL)

Previous Shots Tab:
├─ PreviousShotsModel (historical)
├─ PreviousShotsItemModel (Qt model)
├─ PreviousShotsView (grid)
└─ CacheManager (persistent, no TTL)
```

**Trade-offs**:
- More code overall (3 x base functionality)
- But: No complex conditional branching
- Easier to maintain (can delete one tab without affecting others)
- Easier to extend (add new tab without touching existing ones)

---

### Decision 2: Lazy Thumbnail Loading with Viewport Optimization

**Problem**: Application has potentially thousands of thumbnails. Loading all at once:
- Consumes huge memory
- Blocks UI thread
- Slow startup time

**Solution Evaluated**:
1. Load all thumbnails upfront (unacceptable)
2. Load on-demand as user scrolls (current approach)
3. Pre-calculate what user might scroll to (overly complex)

**Choice**: VIEWPORT-AWARE LAZY LOADING

**Implementation Details**:
```python
class BaseItemModel:
    def set_visible_range(self, start: int, end: int):
        """Called by grid view when viewport changes"""
        if (start, end) == self._last_visible_range:
            return  # No change
        
        self._visible_start = start
        self._visible_end = end
        
        # Debounce to avoid thrashing on rapid scrolls
        self._thumbnail_debounce_timer.start(100)
    
    def _load_visible_thumbnails(self):
        """Load only thumbnails in viewport"""
        # Check memory cache first
        # Then disk cache
        # Then load from source + save to disk
```

**Three-Level Cache**:
1. **Memory Cache** (_pixmap_cache):
   - Fast access
   - Limited size (only visible items + buffer)
   - Evicted on view change

2. **Disk Cache** (CacheManager/thumbnails/):
   - Persistent across sessions
   - Survives application restart
   - Automatically cleaned up if corrupted

3. **Source Files**:
   - Original JPEG, EXR, or PIL-loadable format
   - Conversion on first load (to JPG)
   - Fallback if cache missing

**Performance Impact**:
- Reduces memory from "load all" (GBs) to "visible + buffer" (MBs)
- First scroll slightly slower (building cache)
- Subsequent scrolls very fast (memory cache hits)
- Application startup time reduced 50-70%

**Why Debouncing (100ms)**:
- Rapid scrolling would trigger load for each scroll event
- 100ms debounce collects all scroll events into single batch load
- User can scroll smoothly without waiting for thumbnails

---

### Decision 3: Subprocess Pool with Session Reuse

**Problem**: Workspace commands are expensive:
- Session creation: 500ms-2s
- Command execution: 100-500ms
- Running many commands sequentially: very slow

**Solution Evaluated**:
1. Create new session for each command (slow, resource intensive)
2. Single global session (single point of failure, no parallelism)
3. Pool of reusable sessions (current approach)

**Choice**: SESSION POOL WITH ROUND-ROBIN LOAD BALANCING

**Architecture**:
```python
class ProcessPoolManager:
    def __init__(self):
        self._session_pools = {}  # Per-command-type pools
        self._session_round_robin = {}  # Round-robin index
        self._executor = ThreadPoolExecutor(max_workers=4)
        self._cache = CommandCache()  # Result caching
    
    def execute_workspace_command(self, cmd: str):
        # Check cache first
        if cached := self._cache.get(cmd):
            return cached
        
        # Round-robin select next session
        pool = self._get_session_pool(cmd_type)
        session = pool[self._round_robin[cmd_type] % len(pool)]
        
        # Execute in thread pool
        result = self._executor.submit(session.execute, cmd)
        
        # Cache and return
        self._cache.put(cmd, result)
        return result
```

**Benefits**:
- **Parallelism**: 4+ commands can execute simultaneously
- **Reusability**: Session creation amortized over many commands
- **Caching**: Identical commands return instantly (cached)
- **Isolation**: Each session isolated, failure doesn't affect others
- **Metrics**: Track cache hit rate, execution time, pool utilization

**Round-Robin Rationale**:
- Distributes load evenly across sessions
- Prevents single session from becoming bottleneck
- Simple, deterministic selection
- No central state beyond counter

**Performance Impact**:
- Typical shot load: 100-200ms (vs 500ms+ with new session)
- Batch operations: 4x faster with parallelism
- Cache hits: near-instant (<1ms)

---

### Decision 4: Persistent Incremental 3DE Scene Caching

**Problem**: 3DE scene discovery is expensive (filesystem scan) but needs:
- Discovery of all scenes (could be thousands)
- Support for deleted scenes (preserve history)
- Deduplication (one scene per shot, best by mtime)
- Incremental updates (don't rescan everything)

**Solution Evaluated**:
1. Rescan filesystem every refresh (slow, I/O intensive)
2. Simple cached list, replace on refresh (loses history)
3. Persistent incremental with merge (current approach)

**Choice**: PERSISTENT INCREMENTAL MERGE WITH DEDUPLICATION

**Algorithm**:
```python
def merge_scenes_incremental(cached_scenes: List[Scene], 
                            fresh_scenes: List[Scene]) -> List[Scene]:
    """Merge cached (old) scenes with fresh (discovered) scenes"""
    
    # Start with cached scenes (preserves history)
    merged = {scene.key: scene for scene in cached_scenes}
    
    # Add/update with fresh discoveries
    for fresh in fresh_scenes:
        key = (show, sequence, shot)  # Unique per shot
        
        if key in merged:
            # Keep newer scene (by mtime)
            if fresh.mtime > merged[key].mtime:
                merged[key] = fresh
        else:
            # New discovery
            merged[key] = fresh
    
    return list(merged.values())
```

**Key Features**:
- **History Preservation**: Deleted scenes remain in cache
  - User can still recover deleted .3de files
  - Historical record of work
  - No loss of information

- **Deduplication**: One scene per shot
  - Key: (show, sequence, shot)
  - Winner: Most recent by mtime
  - Can also prefer "plate" versions

- **Incremental**: Only new scenes processed
  - First scan: full discovery
  - Subsequent: only new/modified found
  - Scales to thousands of scenes

**Cache Structure**:
```json
{
  "scenes": [
    {
      "shot_key": ["show", "sequence", "shot"],
      "file_path": "/path/to/scene.3de",
      "mtime": 1699300000,
      "created_by": "artist_name",
      "has_plates": true,
      "plate_version": "v3"
    }
  ],
  "last_scan": 1699300000,
  "scan_duration_ms": 2341
}
```

**Why No TTL**:
- Scenes don't become invalid with time
- .3de files are persistent assets
- Preserved even after deletion
- Only rescan when explicitly requested

**Performance Impact**:
- First scan: 2-5 seconds (full filesystem scan)
- Subsequent scans: 500ms-1s (new files only)
- Incremental merge: <100ms
- Total load: Cache + incremental scan

---

### Decision 5: Qt Signal/Slot Coordination

**Problem**: Multi-threaded application needs safe inter-thread communication:
- Models run on worker threads
- UI runs on main thread
- Can't directly modify Qt objects from worker threads

**Solution Evaluated**:
1. Polling/busy-waiting (bad: blocks, inefficient)
2. Manual thread synchronization (error-prone)
3. Qt signal/slot system (current approach)

**Choice**: SIGNAL/SLOT WITH MOVED-TO-THREAD PATTERN

**Implementation Pattern**:
```python
class AsyncShotLoader(QObject):
    shots_loaded = pyqtSignal(list)  # Declare signals in QObject
    load_failed = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.moveToThread(worker_thread)  # Move to worker thread
        
        # Connect to do_load which will run on worker thread
        self.do_load_shots.connect(self._on_do_load)
    
    def _on_do_load(self):
        """Run on worker thread"""
        try:
            shots = self.pool.execute_command("ws -sg")
            self.shots_loaded.emit(shots)  # Signal back to main
        except Exception as e:
            self.load_failed.emit(str(e))

# In MainWindow (main thread):
loader = AsyncShotLoader()
loader.shots_loaded.connect(self._on_shots_loaded)  # Main thread slot
loader.do_load_shots.emit()  # Trigger on worker thread
```

**Why This Approach**:
- **Thread Safe**: Qt guarantees signal/slot delivers to correct thread
- **No Locks Needed**: Qt handles synchronization
- **Asynchronous**: Doesn't block either thread
- **Decoupled**: Loader doesn't know about UI
- **Qt Native**: Uses framework's built-in mechanisms

**Signal Queue Depth**:
- Signals are queued, not dropped
- Worker can emit many signals
- Main thread processes in order
- No loss of data

**Performance Implications**:
- Minimal overhead (Qt optimized)
- Main thread not blocked during work
- Can emit signals frequently (batched updates)
- Natural flow of control

---

### Decision 6: Dependency Injection for Testability

**Problem**: Models tightly coupled to:
- ProcessPoolManager (subprocess execution)
- CacheManager (persistent storage)
- Makes unit testing difficult

**Solution Evaluated**:
1. Create real pool/cache in tests (slow, side effects)
2. Mock at module level (hard to swap)
3. Dependency injection (current approach)

**Choice**: CONSTRUCTOR/PROPERTY INJECTION

**Implementation**:
```python
class ShotModel(BaseShotModel):
    def __init__(self, 
                 pool: ProcessPoolManager,
                 cache: CacheManager):
        self.pool = pool  # Injected dependency
        self.cache = cache

# In production:
pool = ProcessPoolManager.get_instance()
cache = CacheManager()
model = ShotModel(pool, cache)

# In tests:
mock_pool = MockProcessPoolManager()
mock_cache = MockCacheManager()
model = ShotModel(mock_pool, mock_cache)  # Use mocks!
```

**Benefits**:
- **Testability**: Easy to inject mocks
- **Flexibility**: Can swap implementations
- **Clarity**: Dependencies explicit in constructor
- **Type Safety**: Type hints show what's needed

**Design Trade-off**:
- More constructor parameters (ok for tests)
- Explicit passing (not magic global state)
- Well worth the testing benefit

---

### Decision 7: Periodic Cleanup with Retry Mechanism

**Problem**: Finished processes need cleanup:
- File handles must be released
- Memory must be freed
- But cleanup can fail (process still running, file locks)

**Solution Evaluated**:
1. Immediate cleanup (fails silently, resource leak)
2. Single cleanup attempt (same problem)
3. Periodic cleanup with retry (current approach)

**Choice**: SCHEDULED CLEANUP WITH EXPONENTIAL BACKOFF

**Implementation**:
```python
class LauncherProcessManager:
    CLEANUP_INTERVAL_MS = 100  # Check every 100ms
    CLEANUP_RETRY_DELAY_MS = 500  # Retry after 500ms on failure
    
    def __init__(self):
        self._cleanup_timer = QTimer()
        self._cleanup_timer.timeout.connect(self._periodic_cleanup)
        self._cleanup_timer.start(self.CLEANUP_INTERVAL_MS)
        
        self._cleanup_in_progress = False
        self._cleanup_scheduled = False
    
    def _periodic_cleanup(self):
        if self._cleanup_in_progress:
            return  # Already cleaning, schedule retry
        
        self._cleanup_in_progress = True
        self._cleanup_finished_processes()
        self._cleanup_finished_workers()
        
        if cleanup_failed:
            # Reschedule cleanup
            self._cleanup_retry_timer.start(self.CLEANUP_RETRY_DELAY_MS)
        
        self._cleanup_in_progress = False
```

**Why Periodic**:
- Don't block on cleanup
- Can retry transient failures
- Doesn't depend on process completion signals
- Graceful handling of stuck processes

**Why Retry**:
- Some processes still cleaning up
- File system delays in releasing resources
- Network drives might be slow
- Retries eventually succeed

**Performance Consideration**:
- 100ms interval: responsive cleanup
- Doesn't spawn new timers (single persistent timer)
- Low CPU usage (only checks when needed)

---

### Decision 8: Qt Parent-Child Ownership Model

**Critical Issue**: All QWidget subclasses MUST accept parent parameter:

```python
class MyWidget(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)  # CRITICAL: Pass parent!
```

**Why This Matters**:
- Qt uses parent pointers for object lifecycle
- Without proper parent, Qt C++ internals crash
- Memory not released → C++ segfault in some cases
- Affects even serial test execution

**Real Impact**: 36+ test failures resolved by adding parent parameter

**Design Pattern**:
```
Main Window (top-level)
├─ Central Widget (parent=window)
│  ├─ Tab Widget (parent=central)
│  │  ├─ Shot Grid (parent=tab)
│  │  │  └─ Grid Delegates (parent=grid)
│  │  └─ 3DE Grid (parent=tab)
│  └─ Panel (parent=central)
│     └─ Info Label (parent=panel)
└─ Dialogs (parent=window)
```

**Ownership Benefit**:
- Automatic cleanup when parent destroyed
- No manual delete needed
- Memory safety guaranteed
- Proper signal disconnection

---

### Decision 9: Mixin-Based Functionality

**Problem**: Models and controllers need various cross-cutting concerns:
- Logging
- Performance tracking
- Accessibility support
- Versioning
- Error handling

**Solution Evaluated**:
1. Inheritance from multiple base classes (confusion)
2. Composition (excessive delegation)
3. Mixins (current approach)

**Choice**: MIXIN-BASED COMPOSITION

**Example**:
```python
class LauncherProcessManager(QObject, LoggingMixin, VersionMixin):
    """Combines functionality from multiple mixins"""
    
    def __init__(self):
        super().__init__()
        self.logger = self.get_logger()  # From LoggingMixin
        self.version = self.get_version()  # From VersionMixin
```

**Available Mixins**:
- **LoggingMixin**: Provides get_logger()
- **VersionMixin**: Provides get_version()
- **ProgressMixin**: Progress reporting
- **QtWidgetMixin**: Qt widget utilities
- **ErrorHandlingMixin**: Exception handling

**Benefits**:
- Reusable functionality
- Clean MRO (method resolution order)
- Optional features (only include what needed)
- Testable in isolation

---

### Decision 10: Configuration Through Schema Validation

**Problem**: User settings can be invalid:
- Wrong types
- Missing required fields
- Incompatible combinations
- Out-of-range values

**Solution Evaluated**:
1. No validation (user can break app with bad config)
2. Runtime checks (error-prone, incomplete)
3. Schema validation (current approach)

**Choice**: JSON SCHEMA WITH VALIDATION

**Implementation**:
```python
class SettingsManager:
    SCHEMA = {
        "type": "object",
        "properties": {
            "custom_launchers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "command": {"type": "string"},
                        "enabled": {"type": "boolean"}
                    },
                    "required": ["name", "command"]
                }
            },
            "cache_ttl_minutes": {
                "type": "integer",
                "minimum": 1,
                "maximum": 1440
            }
        },
        "required": ["custom_launchers"]
    }
    
    def load(self, settings_file):
        data = json.load(open(settings_file))
        jsonschema.validate(data, self.SCHEMA)
        return data
```

**Benefits**:
- **Type Safety**: Enforced at load time
- **Completeness**: Required fields checked
- **Range Validation**: Min/max constraints
- **Clear Errors**: Schema tells what's wrong
- **Documentation**: Schema is formal spec

**User Experience**:
- Load fails with clear error message
- User knows exactly what's wrong
- Can fix and reload (no restart)
- Fallback to defaults if needed

---

## SUMMARY OF KEY DESIGN DECISIONS

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Multiple tab systems | 3 separate implementations | Explicitness, independent optimization, easy testing |
| Thumbnail loading | Lazy viewport-aware | Memory efficiency, responsive UI, scalable |
| Subprocess management | Session pool + round-robin | Parallelism, reusability, performance |
| 3DE scene caching | Persistent incremental merge | History preservation, scalability, deduplication |
| Threading | Qt signal/slot + QThread | Thread safety, Qt-native, asynchronous |
| Dependencies | Constructor injection | Testability, flexibility, clarity |
| Process cleanup | Periodic with retry | Graceful failures, resource cleanup |
| Widget ownership | Parent parameters everywhere | Qt C++ safety, automatic cleanup |
| Cross-cutting concerns | Mixins | Reusability, clean composition |
| Configuration | JSON schema validation | Type safety, completeness, clarity |

**Overarching Philosophy**: 
- **Clarity over cleverness**
- **Explicit over implicit**
- **Composable over monolithic**
- **Testable over fragile**
- **Performant without premature optimization**
