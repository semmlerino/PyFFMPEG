# Code Patterns Decision Guide - ShotBot

Use this guide to choose appropriate patterns for different scenarios.

## TESTING DECISION TREE

**Q: What do I need to test?**

### Option 1: Unit - Single Component
- Use: Focused test with mocks
- Fixtures: Component-specific doubles
- Mocking: Mock external dependencies (subprocess, file I/O)
- Assertion: Direct state checking

Example:
```python
def test_launcher_manager_single(mock_subprocess_popen):
    manager = LauncherManagerDouble()
    manager.create_launcher("test", "echo test")
    assert manager.get_created_launcher_count() == 1
```

### Option 2: Integration - Component Interaction
- Use: Multiple components working together
- Fixtures: Real components where possible, mocks for external (subprocess)
- Mocking: Only subprocess, filesystem operations
- Assertion: Signal emissions, state changes

Example:
```python
def test_shot_loading_workflow():
    model = ShotModel()
    cache = CacheManager()
    
    model.load_shots()
    shots = model.get_shots()
    assert len(shots) > 0
```

### Option 3: Qt Widget - Visual Component
- Use: QWidget with parent parameter REQUIRED
- Fixtures: qapp (session-scoped)
- Special: Signal spies for signal testing
- Cleanup: Use deleteLater()

Example:
```python
def test_widget_display(qapp):
    widget = MyWidget(parent=None)
    spy = QSignalSpy(widget.value_changed)
    widget.setValue(42)
    assert len(spy) == 1
    widget.deleteLater()
```

---

## ERROR HANDLING DECISION TREE

**Q: How should I handle this operation?**

### Option 1: Simple Operation with Default
- Use: safe_execute()
- When: Operation might fail, default acceptable
- Log: Always log errors

Example:
```python
def get_user_settings(self):
    return self.safe_execute(
        self._load_settings,
        default={},
        log_error=True
    )
```

### Option 2: File/Path Operation
- Use: safe_file_operation()
- When: Working with filesystem
- Handles: FileNotFoundError, PermissionError, OSError
- Features: Can create parent dirs

Example:
```python
def read_config(self, path):
    return self.safe_file_operation(
        Path.read_text,
        path=path,
        default="{}",
        create_parent=False
    )
```

### Option 3: Block of Operations
- Use: error_context()
- When: Multiple operations, single error handler
- Features: Entry/exit logging, context dict for results

Example:
```python
with self.error_context("database_transaction") as ctx:
    record = db.fetch(query)
    ctx["data"] = record
    db.update(record)
```

### Option 4: Flaky Operation
- Use: retry_on_error()
- When: Intermittent failures (network, locks)
- Features: Exponential backoff

Example:
```python
def connect_to_server(self):
    return self.retry_on_error(
        self._connect,
        max_retries=3,
        delay_seconds=1.0,
        backoff_factor=2.0
    )
```

### Option 5: Specific Error Types
- Use: Explicit try/except
- When: Handling errors differently based on type

Example:
```python
try:
    process.wait(timeout=5)
except subprocess.TimeoutExpired:
    process.kill()
except OSError as e:
    self.logger.error(f"Process error: {e}")
```

---

## LOGGING DECISION TREE

**Q: What information should I log?**

### DEBUG Level
- Use: Development and troubleshooting
- Content: Detailed execution flow
- Frequency: Many lines per operation

Pattern:
```python
self.logger.debug(f"Loading {count} shots from {path}")
if self.logger.isEnabledFor(logging.DEBUG):
    self.logger.debug(f"Full data: {data}")
```

### INFO Level
- Use: User-relevant milestones
- Content: Important state changes
- Frequency: Few lines per operation

Pattern:
```python
self.logger.info(f"Started subprocess for '{name}' (PID: {pid})")
self.logger.info(f"Loaded {count} shots from cache")
```

### WARNING Level
- Use: Potentially problematic situations
- Content: Recovered errors, unusual conditions
- Frequency: Rare

Pattern:
```python
self.logger.warning(f"Worker {key} did not stop gracefully")
self.logger.warning(f"Cache miss for key: {key}")
```

### ERROR Level
- Use: Error events
- Content: What failed and why
- Frequency: Error cases only

Pattern:
```python
self.logger.error(f"Failed to start subprocess: {e}")
self.logger.error(f"Database update failed: {error}")
```

---

## CACHING DECISION TREE

**Q: What type of caching do I need?**

### Option 1: Time-Based (TTL)
- Use: Data that can become stale
- TTL: Expiry time in minutes
- Example: Shot lists (30 min), API responses (5 min)

Implementation:
```python
def get_cached_shots(self):
    cached = self._read_json_cache("shots.json", check_ttl=True)
    if cached is None:
        fresh = self._fetch_shots()
        self.cache_shots(fresh)
        return fresh
    return cached
```

### Option 2: Persistent (No TTL)
- Use: Historical data that doesn't change
- Expiry: Never
- Example: Previous shots, scene history

Implementation:
```python
def get_previous_shots(self):
    # No TTL check - load whatever is cached
    return self._read_json_cache("previous.json", check_ttl=False)
```

### Option 3: Incremental (Merge)
- Use: Data that grows incrementally
- Strategy: Merge cached + fresh discoveries
- Example: 3DE scenes, plate discovery

Implementation:
```python
def discover_scenes(self):
    cached = self._read_json_cache("scenes.json", check_ttl=False)
    fresh = self._filesystem_scan()
    merged = self.merge_scenes_incremental(cached, fresh)
    self._write_json_cache("scenes.json", merged)
    return merged
```

---

## CONFIGURATION DECISION TREE

**Q: Where should I put this setting?**

### Option 1: Hard Constant (Config Class)
- Use: Values that never change at runtime
- Access: `Config.CONSTANT_NAME`
- Override: Environment variable

Example:
```python
# config.py
SHOWS_ROOT = os.environ.get("SHOWS_ROOT", "/shows")
DEFAULT_TIMEOUT = 30

# usage
path = f"{Config.SHOWS_ROOT}/show1"
```

### Option 2: User Setting (QSettings)
- Use: Values user can customize (UI preferences)
- Access: Through SettingsManager
- Persistence: ~/.config/app/settings.ini

Example:
```python
settings = SettingsManager()
window_width = settings.get("window_width", 1200)
settings.set("window_width", new_width)
```

### Option 3: Feature Flag (Config Class)
- Use: Enable/disable features
- Access: `Config.FEATURE_NAME`
- Pattern: Boolean or string options

Example:
```python
# config.py
ENABLE_BACKGROUND_REFRESH = True
USE_PERSISTENT_TERMINAL = True

# usage
if Config.ENABLE_BACKGROUND_REFRESH:
    start_refresh_timer()
```

---

## QT PATTERN DECISION TREE

**Q: How should I structure this Qt code?**

### Option 1: Data + Logic (Model)
- When: Data needs to be displayed in multiple views
- Pattern: Inherit from BaseShotModel or similar
- Signals: Emit when data changes
- Storage: Keep mutable state private

Example:
```python
class ShotModel(BaseShotModel, LoggingMixin):
    shots_changed = Signal(list)
    
    def load_shots(self):
        self._shots = self._fetch_shots()
        self.shots_changed.emit(self._shots)
```

### Option 2: Display Only (View)
- When: Showing data without storage
- Pattern: Inherit from QWidget or QAbstractItemView
- Signals: Connect to model signals
- Storage: None - just display

Example:
```python
class ShotGridView(BaseGridView):
    def __init__(self, model: ShotItemModel, parent=None):
        super().__init__(parent)
        _ = model.rowsInserted.connect(self.update)
```

### Option 3: Coordination (Manager)
- When: Managing component lifecycle and communication
- Pattern: QObject with signals, @final
- Threads: Use QMutex for thread safety
- Cleanup: Explicit shutdown()

Example:
```python
@final
class LauncherProcessManager(LoggingMixin, QObject):
    process_started = Signal(str, str)
    
    def execute_command(self, cmd):
        # Coordinate subprocess + signals
        pass
    
    def shutdown(self):
        # Explicit cleanup
        pass
```

### Option 4: Background Work (Worker)
- When: Long-running task (file I/O, network, processing)
- Pattern: QThread or QRunnable
- Communication: Signals only (thread-safe)
- Lifecycle: Start, wait, cleanup

Example:
```python
class DataLoaderWorker(QThread):
    finished = Signal(list)
    
    def run(self):
        data = self._load_data()
        self.finished.emit(data)

# Usage
worker = DataLoaderWorker()
_ = worker.finished.connect(on_data_loaded)
worker.start()
```

---

## THREADING DECISION TREE

**Q: How should I handle this async operation?**

### Option 1: QThread Worker
- Use: Long-running operations (file I/O, computation)
- Pattern: Subclass QThread
- Signals: For results and progress
- Cleanup: wait(), deleteLater()

Example:
```python
class ScanWorker(QThread):
    progress = Signal(int)
    finished = Signal(list)
    
    def run(self):
        results = []
        for i, item in enumerate(items):
            results.append(process(item))
            self.progress.emit(i)
        self.finished.emit(results)

# Usage
worker = ScanWorker()
_ = worker.progress.connect(update_progress_bar)
_ = worker.finished.connect(on_results)
worker.start()
```

### Option 2: QTimer
- Use: Periodic tasks (cleanup, refresh)
- Pattern: setSingleShot(False) for repeating, True for one-time
- Cleanup: stop() before deletion

Example:
```python
self._refresh_timer = QTimer()
_ = self._refresh_timer.timeout.connect(self._periodic_refresh)
self._refresh_timer.start(30000)  # Every 30 seconds

# Later
self._refresh_timer.stop()
```

### Option 3: Direct Subprocess
- Use: Launching external applications
- Pattern: subprocess.Popen with start_new_session
- Cleanup: Check periodically, terminate on shutdown

Example:
```python
process = subprocess.Popen(
    command,
    shell=False,
    stdout=subprocess.DEVNULL,
    start_new_session=True  # Don't inherit signals
)
# Later
if process.poll() is None:  # Still running
    process.terminate()
```

---

## COMMON DECISION SCENARIOS

### Scenario: Loading Data from Network
1. Create Worker thread (QThread)
2. Add progress signals
3. Connect to UI update slots
4. Handle timeout/error in worker
5. Cache successful result

### Scenario: Processing Large File List
1. Use Worker thread (QThread)
2. Emit progress() signal periodically
3. Implement cancellation with stop flag
4. Batch process to avoid memory spikes
5. Cache results

### Scenario: Periodic Cleanup
1. Create QTimer (not threading)
2. setSingleShot(False)
3. Connect timeout to cleanup method
4. Stop timer on shutdown
5. Use QMutex for shared state

### Scenario: User Settings Dialog
1. Create QDialog subclass
2. Pass SettingsManager to constructor
3. Load current settings in __init__
4. Save on Accept
5. Include parent parameter

### Scenario: Lazy-Loaded Grid View
1. Create Model with lazy-loading
2. Create View with custom delegate
3. Emit signals for item changes
4. Load items on demand (scroll visibility)
5. Cache loaded items

---

## PATTERN SELECTION FLOWCHART

```
START: Need to implement a feature?

├─ Is it a TEST?
│  ├─ Single component → Unit test with doubles
│  ├─ Multiple components → Integration test
│  └─ Qt widget → Qt test with parent required
│
├─ Is it ERROR HANDLING?
│  ├─ Simple operation → safe_execute()
│  ├─ File operation → safe_file_operation()
│  ├─ Block of work → error_context()
│  ├─ Flaky operation → retry_on_error()
│  └─ Specific errors → try/except
│
├─ Is it LOGGING?
│  ├─ Diagnostic detail → DEBUG
│  ├─ Important milestone → INFO
│  ├─ Potential problem → WARNING
│  └─ Error event → ERROR
│
├─ Is it CACHING?
│  ├─ Can become stale → TTL-based
│  ├─ Never changes → Persistent
│  └─ Grows incrementally → Merge
│
├─ Is it Qt CODE?
│  ├─ Stores data → Model
│  ├─ Shows data → View
│  ├─ Coordinates components → Manager
│  └─ Long-running work → Worker thread
│
└─ Is it ASYNC WORK?
   ├─ Long operation → QThread
   ├─ Periodic task → QTimer
   └─ Launch app → subprocess.Popen
```

---

## VALIDATION CHECKLIST

Before submitting code:

### Testing
- [ ] Fixtures have proper cleanup (try/finally)
- [ ] QWidget tests include parent parameter
- [ ] Mock external dependencies (subprocess, I/O)
- [ ] Signal assertions use QSignalSpy or doubles
- [ ] Tests are isolated (no shared state)

### Error Handling
- [ ] All operations have error handling
- [ ] Specific exception types caught (not bare except)
- [ ] Errors logged with context
- [ ] Graceful degradation/fallback provided

### Logging
- [ ] Appropriate log levels used
- [ ] No excessive logging in loops
- [ ] Contextual info included
- [ ] DEBUG logs for troubleshooting

### Qt Patterns
- [ ] All QWidget subclasses have parent parameter
- [ ] Thread-safe access with QMutex
- [ ] Signals properly declared and connected
- [ ] No blocking operations on main thread

### Performance
- [ ] Long operations use worker threads
- [ ] No synchronous I/O on main thread
- [ ] Caching used for repeated operations
- [ ] Incremental loading for large data

### Code Quality
- [ ] Type hints on all public methods
- [ ] Docstrings on classes and methods
- [ ] Naming follows conventions (PascalCase/snake_case)
- [ ] No obvious performance issues (loops in loops, etc.)
