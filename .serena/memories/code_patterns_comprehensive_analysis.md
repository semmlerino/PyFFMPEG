# Comprehensive Code Patterns and Conventions - ShotBot

This analysis covers testing patterns, error handling, logging, configuration, code style, Qt patterns, and architectural approaches used throughout the Shotbot codebase.

## 1. TESTING PATTERNS

### 1.1 Test Structure and Organization

**Fixture Scope Strategy:**
- `qapp`: Session-scoped QApplication (created once, reused across all tests)
  - Uses offscreen platform: `QT_QPA_PLATFORM=offscreen` set at module import time
  - Prevents "real widgets" from appearing, avoiding Qt C++ crashes in WSL
  - Validates platform on each access with runtime checks

**Test Markers (pytest):**
- `@pytest.mark.unit` - Fast unit tests
- `@pytest.mark.qt` - Tests requiring Qt components
- `@pytest.mark.integration` - Cross-component tests
- `@pytest.mark.fast` - Tests with no I/O
- Applied at both individual test and module level (pytestmark)

**Test File Organization:**
```
tests/
├── conftest.py              # Global fixtures (qapp, mocking)
├── test_doubles_library.py  # Reusable test doubles
├── unit/
│   ├── test_module.py       # Unit tests (fast, isolated)
│   └── conftest.py          # Unit-specific fixtures
└── integration/
    ├── test_workflows.py    # Cross-component flows
    └── conftest.py          # Integration fixtures
```

### 1.2 Test Doubles and Mocking

**Signal Double (SignalDouble class):**
```python
# Replaces Qt signals in tests
signal = SignalDouble()
signal.emit("arg1", arg2="value")
assert signal.emit_count == 1
assert signal.last_emission == ("arg1",)

# Track callbacks
signal.connect(callback)
signal.disconnect(callback)  # or disconnect all if no arg
signal.reset()  # Clear all tracking
```
**Key Features:**
- Maintains emissions list: `[(arg1, arg2), ...]`
- Tracks callbacks with connect/disconnect
- Provides reset() for test isolation
- API compatible with Qt.Signal

**LauncherManagerDouble (Manager Double):**
```python
# Real behavior with test control points
manager = LauncherManagerDouble()
manager.set_validation_result(command, is_valid=True, error=None)
manager.set_test_command(cmd)
manager.execute_launcher(launcher)  # Returns bool
manager.list_launchers()  # Returns list[TestLauncher]

# Inspection methods
manager.get_created_launcher_count()
manager.was_dry_run_executed()
manager.get_last_created_launcher()
```
**Pattern:**
- Simulates real interface behavior
- Allows injection of test-specific behaviors
- Maintains internal state for assertions
- No threading, no actual subprocess calls

**Subprocess Mocking:**
```python
@pytest.fixture
def mock_subprocess_popen():
    with patch("launcher.process_manager.subprocess.Popen") as mock_popen:
        mock_process = Mock()
        mock_process.pid = 12345
        mock_process.poll.return_value = None  # Running
        mock_process.wait.return_value = 0  # Exit code
        mock_popen.return_value = mock_process
        yield mock_popen, mock_process
```

### 1.3 Fixture Patterns

**Cleanup Pattern:**
```python
@pytest.fixture
def process_manager(qapp):
    manager = LauncherProcessManager()
    try:
        yield manager
    finally:
        # ALWAYS cleanup
        manager.shutdown()
        manager.deleteLater()  # Qt cleanup
```
**Key Points:**
- Try/finally ensures cleanup even if test fails
- Qt.deleteLater() for proper Qt cleanup
- Shutdown methods stop threads/timers

**Autouse Fixtures for Qt Cleanup:**
```python
@pytest.fixture(autouse=True)
def cleanup_qt_state(qtbot):
    """Ensure Qt state cleaned between tests."""
    yield
    qtbot.wait(1)  # Process pending Qt events
```

**Factory Fixtures:**
```python
@pytest.fixture
def make_test_shot():
    """Factory for creating test Shot objects."""
    def _make(show="show1", sequence="seq1", shot="shot1"):
        return Shot(show, sequence, shot)
    return _make

# Usage
def test_something(make_test_shot):
    shot1 = make_test_shot("show1", "seq1", "shot1")
    shot2 = make_test_shot(show="show2")
```

### 1.4 Parametrization Patterns

**Pytest Parametrize:**
```python
@pytest.mark.parametrize("input,expected", [
    ("jpg", True),
    ("png", True),
    ("unknown", False),
])
def test_is_valid_extension(input, expected):
    assert is_valid_extension(input) == expected
```

**Parametrize with Indirect:**
```python
# Fixtures receive parametrized values
@pytest.fixture
def config_mode(request):
    return request.param  # "production" or "development"

@pytest.mark.parametrize("config_mode", ["production", "development"], indirect=True)
def test_both_modes(config_mode):
    # config_mode fixture receives the parameter
    ...
```

### 1.5 Signal Testing

**QSignalSpy (PyTest-Qt):**
```python
from PySide6.QtTest import QSignalSpy

manager = LauncherProcessManager()
spy = QSignalSpy(manager.process_started)

# Execute operation that emits signal
manager.execute_command("test")

# Assert signal emitted
assert len(spy) == 1
assert spy[0][0] == "expected_launcher_id"  # First signal arg
```

### 1.6 Common Test Assertions

**Qt Signal Assertions:**
```python
# Check signal was emitted N times
assert signal_double.emit_count == 2

# Check last emission arguments
assert signal_double.last_emission == (arg1, arg2)

# Check specific emission
assert signal_double.emissions[0] == (first_arg,)
```

**State Assertions:**
```python
# Manager state checks
assert manager.get_active_process_count() == 1
assert len(manager.get_active_workers_dict()) == 1
```

---

## 2. ERROR HANDLING PATTERNS

### 2.1 ErrorHandlingMixin Usage

**safe_execute() Pattern:**
```python
from error_handling_mixin import ErrorHandlingMixin

class MyService(ErrorHandlingMixin, LoggingMixin):
    def load_config(self):
        # Replaces common try/except pattern
        return self.safe_execute(
            self._read_config_file,
            default=None,
            log_error=True,
            reraise=False  # Catch and log
        )
    
    def _read_config_file(self):
        return json.load(open("config.json"))
```
**Advantages:**
- Eliminates repetitive try/except blocks
- Consistent error logging at mixin level
- Configurable logging level and reraise behavior

**safe_file_operation() Pattern:**
```python
def get_file_content(self, path):
    # Handles FileNotFoundError, PermissionError, OSError
    return self.safe_file_operation(
        Path.read_text,
        path=path,
        default="",
        create_parent=False  # For write operations
    )
```

**error_context() Context Manager:**
```python
def update_database(self):
    with self.error_context(
        "database update",
        reraise=False,
        log_level=logging.WARNING
    ) as ctx:
        # Performs operation
        self.db.update()
        ctx["result"] = "success"
    
    # Access result safely
    return ctx["result"]
```

**retry_on_error() Pattern:**
```python
def fetch_remote_data(self):
    return self.retry_on_error(
        self._fetch_api,
        max_retries=3,
        delay_seconds=1.0,
        backoff_factor=2.0  # 1s, 2s, 4s delays
    )
```

### 2.2 Exception Hierarchy and Handling

**Custom Exception Pattern:**
```python
class QtThreadError(Exception):
    """Qt threading-related error."""
    pass

# Usage
try:
    worker.start()
except QtThreadError as e:
    self.logger.error(f"Worker failed: {e}")
```

**Specific Exception Catching:**
```python
try:
    process_info.process.wait(timeout=5)
except subprocess.TimeoutExpired:
    # Handle timeout specifically
    process_info.process.kill()
    process_info.process.wait(timeout=2)
except (OSError, AttributeError) as e:
    # Handle OS errors
    self.logger.debug(f"Process error: {e}")
```

### 2.3 Graceful Degradation Patterns

**Cleanup with Suppression:**
```python
# Disconnect signals without raising on error
try:
    _ = worker.command_started.disconnect()
    _ = worker.command_finished.disconnect()
except (RuntimeError, TypeError):
    pass  # Already disconnected, no error
```

**Fallback Strategies:**
```python
def load_thumbnail(self):
    # Try primary path
    if (primary := self.get_primary_thumbnail()).exists():
        return primary
    
    # Try fallback path
    if (fallback := self.get_fallback_thumbnail()).exists():
        return fallback
    
    # Use placeholder
    return self.get_placeholder_image()
```

---

## 3. LOGGING PATTERNS

### 3.1 LoggingMixin

**Basic Usage:**
```python
from logging_mixin import LoggingMixin, LoggingConfig

class ShotModel(LoggingMixin):
    def __init__(self):
        super().__init__()  # Initialize mixin chain
    
    def load_shots(self):
        self.logger.info("Loading shots...")
        self.logger.debug(f"Shot count: {len(shots)}")
        self.logger.error("Failed to load shots", exc_info=True)
```

**Logger Naming Hierarchy:**
```
# Logger name: module.ClassName
shotbot.shot_model.ShotModel
shotbot.launcher.process_manager.LauncherProcessManager

# Child classes inherit parent logging context
class AdvancedShotModel(ShotModel):
    # Logger: shotbot.shot_model.AdvancedShotModel
    pass
```

**ContextualLogger Features:**
```python
@property
def logger(self) -> ContextualLogger:
    # Automatically:
    # 1. Gets module + class name
    # 2. Caches logger on instance (_contextual_logger)
    # 3. Provides contextual support (operation tracking)
    return self._get_logger()
```

### 3.2 Logging Levels and Usage

**DEBUG Level:**
- Detailed diagnostic info
- Used for development and troubleshooting
```python
self.logger.debug(f"Processing shot: {shot.name}")
self.logger.debug(f"Cache hit for key: {cache_key}")
```

**INFO Level:**
- General informational messages
- User-relevant operations
```python
self.logger.info(f"LauncherProcessManager initialized with cleanup interval {ms}ms")
self.logger.info(f"Started subprocess for launcher '{name}' (PID: {pid})")
```

**WARNING Level:**
- Potentially problematic situations
- Recovered errors
```python
self.logger.warning(f"Worker {key} did not stop gracefully")
self.logger.warning(f"Process/worker {key} not found")
```

**ERROR Level:**
- Error events that might be recoverable
- Operations that failed
```python
self.logger.error(f"Failed to start subprocess: {e}")
self.logger.error(f"Command execution failed: {command}")
```

### 3.3 Contextual Logging

**Operation Tracking:**
```python
# Logs entry/exit of operations
with self.error_context("database update") as ctx:
    # Logs: "Starting database update"
    # Logs: "Completed database update" (success)
    # Logs: "database update failed: {error}" (on error)
    pass
```

**Traceback Logging:**
```python
if self.logger.isEnabledFor(logging.DEBUG):
    self.logger.debug(f"Traceback:\n{traceback.format_exc()}")
```

### 3.4 Log Configuration

**pytest Configuration in conftest.py:**
```python
def pytest_configure(config):
    """Configure pytest logging."""
    # Logging setup for tests
    # Prevents Qt warnings from polluting test output
```

---

## 4. CONFIGURATION PATTERNS

### 4.1 Config Class Structure

**Static Configuration (config.py):**
```python
class Config:
    """Application-wide constants and settings."""
    
    # Simple constants
    APP_NAME: str = "ShotBot"
    APP_VERSION: str = "1.0.2"
    
    # Collections (ClassVar for type safety)
    APPS: ClassVar[dict[str, str]] = {
        "3de": "3de",
        "nuke": "nuke",
        "maya": "maya",
    }
    
    # Environment-aware
    SHOWS_ROOT: str = os.environ.get("SHOWS_ROOT", "/shows")
    
    # Nested configuration
    class Config.ThreadingConfig:
        # Threading-specific settings
        pass
```

### 4.2 Configuration Categories

**UI Settings:**
- Window dimensions: DEFAULT_WINDOW_WIDTH, MIN_WINDOW_WIDTH
- Thumbnail sizes: DEFAULT_THUMBNAIL_SIZE, MIN_THUMBNAIL_SIZE, MAX_THUMBNAIL_SIZE
- Grid layout: THUMBNAIL_SPACING, GRID_COLUMNS

**Performance Settings:**
- Threading: MAX_THUMBNAIL_THREADS, WORKER_STOP_TIMEOUT_MS
- Cache: CACHE_EXPIRY_MINUTES, CACHE_REFRESH_INTERVAL_MINUTES
- Subprocess: SUBPROCESS_TIMEOUT_SECONDS, WS_COMMAND_TIMEOUT_SECONDS

**Path Patterns:**
```python
THUMBNAIL_PATH_PATTERN = "{shows_root}/{show}/shots/{sequence}/{shot}/publish/..."
THUMBNAIL_SEGMENTS = ["publish", "editorial", "cutref", "v001", "jpg", "1920x1080"]
THREEDE_SCENE_SEGMENTS = ["mm", "3de", "mm-default", "scenes", "scene"]
```

**Feature Flags:**
```python
ENABLE_BACKGROUND_REFRESH: bool = True
USE_PERSISTENT_TERMINAL: bool = True
USE_REZ_ENVIRONMENT: bool = True
THREEDE_STOP_AFTER_FIRST: bool = True
```

### 4.3 Configuration Access Patterns

**Direct Import (Simple):**
```python
from config import Config

path = f"{Config.SHOWS_ROOT}/{show}/shots/{sequence}"
timeout = Config.SUBPROCESS_TIMEOUT_SECONDS
```

**Environment Variable Override:**
```python
# Config.py
SHOWS_ROOT: str = os.environ.get("SHOWS_ROOT", "/shows")

# At runtime: SHOWS_ROOT=/custom/path python shotbot.py
```

**Settings Manager (for Persistent User Settings):**
```python
# For settings that change at runtime
class SettingsManager:
    def get_setting(self, key: str, default):
        return self.settings.value(key, default)
    
    def set_setting(self, key: str, value):
        self.settings.setValue(key, value)
```

---

## 5. CODE STYLE AND CONVENTIONS

### 5.1 Naming Conventions

**Classes (PascalCase):**
```python
class ShotModel
class LauncherProcessManager
class BaseItemModel
class ThreeDESceneWorker
```

**Functions/Methods (snake_case):**
```python
def load_shots()
def cache_thumbnail()
def execute_with_subprocess()
def _on_worker_finished()  # Private methods with underscore
```

**Constants (UPPER_SNAKE_CASE):**
```python
DEFAULT_THUMBNAIL_SIZE = 350
MAX_WORKERS = 4
CLEANUP_INTERVAL_MS = 5000
THREAD_POOL_SIZE = 8
```

**Private Members (_prefix):**
```python
class Manager:
    def __init__(self):
        self._cache = {}  # Private (single underscore)
        self._active_processes: dict[str, ProcessInfo] = {}
    
    def _internal_method(self):  # Private method
        pass
```

### 5.2 Type Hints (PEP 604 - Python 3.10+)

**Modern Union Syntax:**
```python
# CORRECT (Python 3.10+)
def get_shot(self, shot_id: str) -> Shot | None:
    pass

# WRONG (deprecated)
from typing import Optional
def get_shot(self, shot_id: str) -> Optional[Shot]:
    pass
```

**Generics with TypeVar:**
```python
from typing import TypeVar, Generic

T = TypeVar("T")

class BaseItemModel(Generic[T]):
    def add_item(self, item: T) -> None:
        pass
    
    def get_item(self, index: int) -> T | None:
        pass
```

**Function Annotations:**
```python
def execute(
    self,
    operation: Callable[..., T],
    *args: object,
    default: T | None = None,
    **kwargs: object,
) -> T | None:
    """Execute operation with standard error handling."""
```

**TYPE_CHECKING for Circular Imports:**
```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication
    from pytestqt.qtbot import QtBot

# These imports are only for type checking, not runtime
```

### 5.3 Docstring Patterns

**Module Docstrings:**
```python
"""Unit tests for LauncherProcessManager.

Testing the process lifecycle management, signal emissions, and resource cleanup.
Following UNIFIED_TESTING_GUIDE best practices:
- Test behavior, not implementation
- Use real Qt components with signal testing
- Mock subprocess calls to avoid launching actual apps
- Thread safety validation
- Proper resource cleanup
"""
```

**Class Docstrings:**
```python
class ErrorHandlingMixin(LoggingMixin):
    """Mixin providing standardized error handling patterns.

    This mixin consolidates common error handling patterns found throughout
    the codebase, reducing duplicate try/except blocks and standardizing
    error logging and recovery.
    """
```

**Method Docstrings (Google Style):**
```python
def execute_with_worker(
    self,
    launcher_id: str,
    launcher_name: str,
    command: str,
    working_dir: str | None = None,
) -> bool:
    """Execute command using a worker thread.

    Args:
        launcher_id: ID of the launcher
        launcher_name: Name of the launcher
        command: Command to execute
        working_dir: Optional working directory

    Returns:
        True if worker started successfully, False otherwise
    """
```

### 5.4 Ruff Configuration (Black-compatible)

**Formatting:**
- Line length: 88 characters
- Indent: 4 spaces
- Quotes: Double quotes
- Target: Python 3.11+

**Enabled Rules:**
- E, W: PEP 8 basics
- F: Undefined names, syntax errors
- I: isort (import sorting)
- N: pep8-naming
- UP: pyupgrade (modern syntax)
- B: flake8-bugbear (common bugs)
- C4: flake8-comprehensions
- PT: flake8-pytest-style
- TCH: flake8-type-checking
- PL: Pylint (comprehensive)
- TRY: tryceratops (exception handling)
- RUF: Ruff-specific rules

**Disabled Rules (for Qt projects):**
- SLF001: private-member-access (common in Qt)
- ARG002: unused-method-argument (Qt callbacks)
- ARG001: unused fixtures (pytest)
- E501: line-too-long (handled by formatter)
- D: pydocstyle (project's own style)
- PLR0913: too-many-arguments (Qt widgets)
- FBT001/002/003: boolean arguments (common in GUI)

---

## 6. QT PATTERNS

### 6.1 Widget Parent Requirement (CRITICAL)

**MUST Accept Optional Parent:**
```python
# CORRECT - All QWidget subclasses must accept parent
class MyWidget(QtWidgetMixin, QWidget):
    def __init__(
        self,
        cache_manager: CacheManager | None = None,
        parent: QWidget | None = None,  # REQUIRED
    ) -> None:
        super().__init__(parent)  # REQUIRED - pass to Qt
        # ... rest of initialization

# WRONG - Crashes with Qt C++ error
class MyWidget(QtWidgetMixin, QWidget):
    def __init__(self, cache_manager: CacheManager | None = None):
        super().__init__()  # ERROR - no parent passed!
```

**Why This Matters:**
- Missing parent causes: `Fatal Python error: Aborted` at Qt C++ level
- Error manifests in logging_mixin.py:269 → qt_widget_mixin.py:63 → Qt C++
- Crashes occur even with serial (non-parallel) test execution
- Affects 36+ tests when implemented incorrectly

**Qt Ownership Model:**
```python
# Parent owns children - deletes them on cleanup
parent = MainWindow()
child1 = QWidget(parent)  # parent owns child1
child2 = QWidget(parent)  # parent owns child2
parent.deleteLater()  # Deletes child1, child2 automatically
```

### 6.2 Signal Declaration and Usage

**Signal Declaration (Module Level):**
```python
from PySide6.QtCore import Signal, QObject

class LauncherProcessManager(QObject):
    # Declare signals at class level
    process_started = Signal(str, str)  # launcher_id, command
    process_finished = Signal(str, bool, int)  # id, success, return_code
    process_error = Signal(str, str)  # launcher_id, error_message
    
    def execute_command(self, cmd: str) -> None:
        # Emit signal
        self.process_started.emit(launcher_id, cmd)
```

**Signal Connection (Type-Safe):**
```python
# Qt.ConnectionType for thread safety
_ = worker.command_finished.connect(
    on_finished,
    Qt.ConnectionType.QueuedConnection,  # Cross-thread safe
)

# Note: Use QueuedConnection for cross-thread signals
# Direct connection: Same thread signals
# QueuedConnection: Cross-thread signals (safer)
```

**Lambda with Closures (Capture Issue):**
```python
# WRONG - lambda captures variable by reference
for worker_key in worker_keys:
    _ = worker.finished.connect(lambda: cleanup(worker_key))
    # All lambdas reference SAME worker_key (last iteration value)

# CORRECT - use nested function with immutable capture
def on_finished(key: str) -> None:
    cleanup(key)

_ = worker.finished.connect(on_finished)
# OR use default argument to capture by value
_ = worker.finished.connect(
    lambda k=worker_key: cleanup(k),
    Qt.ConnectionType.QueuedConnection,
)
```

### 6.3 Thread Safety Patterns

**QMutex for Synchronization:**
```python
from PySide6.QtCore import QMutex, QMutexLocker

class ProcessManager:
    def __init__(self):
        self._process_lock = QMutex()
        self._active_processes: dict[str, ProcessInfo] = {}
    
    def add_process(self, key: str, info: ProcessInfo):
        # Automatic lock/unlock via context manager
        with QMutexLocker(self._process_lock):
            self._active_processes[key] = info
    
    def get_processes(self) -> dict[str, ProcessInfo]:
        # Thread-safe snapshot
        with QMutexLocker(self._process_lock):
            return dict(self._active_processes)  # Copy, not reference
```

**QRecursiveMutex for Nested Locking:**
```python
from PySide6.QtCore import QRecursiveMutex

class Manager:
    def __init__(self):
        # Allow same thread to acquire lock multiple times
        self._lock = QRecursiveMutex()
    
    def method1(self):
        with QMutexLocker(self._lock):
            self.method2()  # Can acquire same lock
    
    def method2(self):
        with QMutexLocker(self._lock):
            # This would deadlock with regular QMutex
            pass
```

**Safe Snapshot Pattern:**
```python
def cleanup(self):
    # Get snapshot outside lock
    with QMutexLocker(self._process_lock):
        snapshot = list(self._active_processes.items())
    
    # Process outside lock (prevents deadlock)
    for key, info in snapshot:
        self._process_cleanup(key, info)
```

### 6.4 QTimer Usage

**Single-Shot Timer (One-Time Trigger):**
```python
from PySide6.QtCore import QTimer

# Timer that fires once then stops
timer = QTimer()
timer.setSingleShot(True)
_ = timer.timeout.connect(self._do_something)
timer.start(5000)  # Fire in 5 seconds, once
```

**Periodic Timer (Repeating):**
```python
# Cleanup timer that fires repeatedly
cleanup_timer = QTimer()
cleanup_timer.timeout.connect(self._periodic_cleanup)
cleanup_timer.start(5000)  # Fire every 5 seconds

# Later, stop it
cleanup_timer.stop()
```

### 6.5 Qt Offscreen Platform for Testing

**Environment Setup (MUST be before any Qt imports):**
```python
# conftest.py (TOP OF FILE, before any Qt imports)
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
```

**Why Offscreen is Critical:**
- Prevents actual windows from appearing during tests
- Avoids Qt C++ initialization crashes in WSL
- Speeds up test execution (no display overhead)
- Prevents resource exhaustion from creating hundreds of widgets

---

## 7. MANAGER AND CONTROLLER PATTERNS

### 7.1 Manager Class Structure

**LauncherProcessManager Pattern:**
```python
from typing import final

@final  # Prevent subclassing
class LauncherProcessManager(LoggingMixin, QObject):
    # Signals at class level
    process_started = Signal(str, str)
    process_finished = Signal(str, bool, int)
    
    def __init__(self):
        super().__init__()
        # Thread-safe data structures
        self._active_processes: dict[str, ProcessInfo] = {}
        self._process_lock = QRecursiveMutex()
        
        # Qt timers for cleanup
        self._cleanup_timer = QTimer()
        _ = self._cleanup_timer.timeout.connect(self._periodic_cleanup)
        self._cleanup_timer.start(5000)
    
    # Public methods (execution)
    def execute_with_subprocess(self, ...):
        """Execute as subprocess."""
        process = subprocess.Popen(...)
        with QMutexLocker(self._process_lock):
            self._active_processes[key] = process_info
        self.process_started.emit(launcher_id, command)
    
    def execute_with_worker(self, ...):
        """Execute as worker thread."""
        worker = LauncherWorker(...)
        _ = worker.finished.connect(self._on_worker_finished)
        with QMutexLocker(self._process_lock):
            self._active_workers[key] = worker
        worker.start()
    
    # Public query methods
    def get_active_process_count(self) -> int:
        with QMutexLocker(self._process_lock):
            return len(self._active_processes)
    
    # Private maintenance methods
    def _periodic_cleanup(self):
        """Remove finished processes periodically."""
        finished = self._find_finished_processes()
        with QMutexLocker(self._process_lock):
            for key in finished:
                del self._active_processes[key]
    
    def shutdown(self):
        """Clean shutdown."""
        self._cleanup_timer.stop()
        self.stop_all_workers()
```

**Key Manager Patterns:**
- **Thread Safety**: QMutex for all shared state
- **Signal/Slot**: Emit signals for state changes
- **Cleanup**: Timer for periodic maintenance, explicit shutdown()
- **Snapshot Pattern**: Get thread-safe copies for iteration
- **Final Class**: Use @final to prevent subclassing

### 7.2 CacheManager Pattern

**Persistent Caching Strategy:**
```python
class CacheManager(LoggingMixin):
    def __init__(self, cache_dir: Path | None = None):
        super().__init__()
        self.cache_dir = cache_dir or Path.home() / ".shotbot/cache"
        self._lock = threading.Lock()  # Thread-safe cache access
    
    # Time-based cache with TTL
    def get_cached_shots(self) -> list[Shot] | None:
        """Load from cache if not expired."""
        if self._is_cache_valid("shots"):
            return self._read_json_cache("shots.json")
        return None
    
    # Incremental caching (merge pattern)
    def merge_shots_incremental(
        self,
        cached: list[Shot],
        fresh: list[Shot],
    ) -> ShotMergeResult:
        """Merge cached + fresh, preserve history."""
        # Build lookup by key
        cached_by_key = {_get_shot_key(s): s for s in cached}
        fresh_by_key = {_get_shot_key(s): s for s in fresh}
        
        # Identify changes
        updated = fresh_by_key - cached_by_key.keys()  # New
        removed = cached_by_key.keys() - fresh_by_key  # Gone
        
        # Return merge result
        return ShotMergeResult(
            merged=fresh + [cached_by_key[k] for k in removed],
            updated=updated,
            removed=removed,
        )
    
    # Data persistence
    def cache_data(self, key: str, data: dict) -> bool:
        """Save data to cache file."""
        with self._lock:
            return self._write_json_cache(f"{key}.json", data)
    
    def get_cached_data(self, key: str) -> dict | None:
        """Load cached data."""
        with self._lock:
            return self._read_json_cache(f"{key}.json")
```

**Key Caching Patterns:**
- **Thread Safety**: Lock for all read/write operations
- **TTL Support**: Check expiry before returning cached data
- **Incremental Merge**: Preserve deleted items (history)
- **JSON Serialization**: Simple, portable cache format
- **Metadata Tracking**: Timestamps for expiry checks

---

## 8. ARCHITECTURAL PATTERNS

### 8.1 Model-View Separation

**Model Pattern (Data + Logic):**
```python
class ShotModel(BaseShotModel, LoggingMixin):
    """Model for shot data."""
    
    def __init__(self):
        super().__init__()
        self._shots: list[Shot] = []
        self._cache_manager = CacheManager()
    
    def load_shots(self) -> bool:
        """Load shots from cache or command."""
        # Try cache first
        cached = self._cache_manager.get_cached_shots()
        if cached:
            self._shots = cached
            return True
        
        # Fall back to command
        shots = self._execute_ws_command()
        self._cache_manager.cache_shots(shots)
        self._shots = shots
        return True
    
    def get_shots(self) -> list[Shot]:
        """Access current shots."""
        return self._shots.copy()  # Return copy for safety
```

**View Pattern (UI Display):**
```python
class ShotGridView(BaseGridView):
    """View for shot grid display."""
    
    def __init__(self, model: ShotItemModel, parent: QWidget | None = None):
        super().__init__(parent)
        self.model = model
        
        # Connect model signals to view updates
        _ = model.rowsInserted.connect(self._on_rows_inserted)
    
    def _on_rows_inserted(self):
        """Update view when model data changes."""
        self.update()
        self.resizeToContents()
```

### 8.2 Generic Base Classes

**Generic Model Base:**
```python
from typing import TypeVar, Generic

T = TypeVar("T")

class BaseItemModel(Generic[T]):
    """Generic Qt model for any item type."""
    
    def add_item(self, item: T) -> None:
        """Add item to model."""
        pass
    
    def get_item(self, index: int) -> T | None:
        """Get item by index."""
        pass
    
    def get_all_items(self) -> list[T]:
        """Get all items."""
        return self._items.copy()
```

**Subclass Specialization:**
```python
class ShotItemModel(BaseItemModel[Shot]):
    """Specialized model for Shot items."""
    
    def load_from_file(self, path: Path) -> None:
        # Type-safe: Shot objects only
        shot = Shot.from_file(path)
        self.add_item(shot)

class ThreeDESceneItemModel(BaseItemModel[ThreeDEScene]):
    """Specialized model for 3DE Scene items."""
    
    def load_from_file(self, path: Path) -> None:
        # Type-safe: ThreeDEScene objects only
        scene = ThreeDEScene.from_file(path)
        self.add_item(scene)
```

### 8.3 Dependency Injection

**Constructor Injection Pattern:**
```python
class ShotGridView(BaseGridView):
    """View with injected dependencies."""
    
    def __init__(
        self,
        model: ShotItemModel,
        cache_manager: CacheManager,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.model = model
        self.cache = cache_manager
        # All dependencies are testable

# In tests
@pytest.fixture
def shot_grid_view(qapp):
    mock_model = Mock(spec=ShotItemModel)
    mock_cache = Mock(spec=CacheManager)
    view = ShotGridView(mock_model, mock_cache)
    yield view
    view.deleteLater()
```

**Factory Pattern:**
```python
class ViewFactory:
    """Factory for creating views with dependencies."""
    
    @staticmethod
    def create_shot_view(
        model: ShotItemModel,
        cache: CacheManager,
    ) -> ShotGridView:
        """Create configured shot view."""
        view = ShotGridView(model, cache)
        return view
```

---

## 9. CACHING PATTERNS

### 9.1 Cache Strategies

**Time-Based Expiry (TTL):**
```python
def _read_json_cache(self, cache_file: Path, check_ttl=True) -> dict | None:
    """Read cache, respecting TTL."""
    if not cache_file.exists():
        return None
    
    if check_ttl:
        age = (time.time() - cache_file.stat().st_mtime) / 60
        if age > self.CACHE_EXPIRY_MINUTES:
            cache_file.unlink()
            return None
    
    return json.load(cache_file.open())
```

**Persistent Cache (No Expiry):**
```python
def get_persistent_previous_shots(self) -> list[Shot]:
    """Load previous shots (persistent, no TTL)."""
    # No TTL check - data persists indefinitely
    return self._read_json_cache(
        self.previous_shots_cache_file,
        check_ttl=False  # Persistent
    )
```

**Incremental Cache (Merge Strategy):**
```python
def merge_scenes_incremental(
    self,
    cached: list[ThreeDEScene],
    fresh: list[ThreeDEScene],
) -> SceneMergeResult:
    """Merge cache + discovery results."""
    # Preserve deleted scenes in cache (history)
    # Add new discoveries
    # Update existing scenes
    
    cached_by_key = {_get_scene_key(s): s for s in cached}
    fresh_by_key = {_get_scene_key(s): s for s in fresh}
    
    # Merge: keep cached deleted items, add fresh new items
    merged = []
    merged.extend(fresh)  # Fresh discoveries
    for key, scene in cached_by_key.items():
        if key not in fresh_by_key:
            merged.append(scene)  # Preserve deleted
    
    return SceneMergeResult(merged=merged, ...)
```

### 9.2 Cache File Organization

**Directory Structure:**
```
~/.shotbot/cache/
├── production/
│   ├── shots.json                 # My Shots (TTL: 30 min)
│   ├── previous_shots.json        # Previous Shots (persistent)
│   ├── threede_scenes.json        # 3DE Scenes (persistent)
│   └── migrated_shots.json        # Migrated shots (persistent)
└── thumbnails/
    ├── show1/
    │   └── seq1/
    │       └── shot1/
    │           └── thumb.jpg
    └── show2/
        └── ...
```

**Cache Metadata:**
```python
CACHE_DATA = {
    "data": [...actual_data...],
    "metadata": {
        "timestamp": 1234567890,
        "version": "1.0.2",
        "count": 42,
    }
}
```

---

## 10. ANTI-PATTERNS TO AVOID

### 10.1 Common Mistakes

**WRONG: No parent for QWidget:**
```python
# Causes crash!
class MyWidget(QWidget):
    def __init__(self):
        super().__init__()  # ERROR: No parent
```

**WRONG: Capturing in lambda inside loop:**
```python
# All lambdas capture same final value!
for key in keys:
    _ = signal.connect(lambda: cleanup(key))  # BUG
```

**WRONG: Try/except that's too broad:**
```python
try:
    result = risky_operation()
except:  # NEVER do this!
    pass  # Hides all errors

# CORRECT:
try:
    result = risky_operation()
except (ValueError, OSError) as e:
    self.logger.error(f"Operation failed: {e}")
```

**WRONG: Not using context managers:**
```python
# Prone to leaks
lock = QMutex()
lock.lock()
try:
    do_something()
finally:
    lock.unlock()

# CORRECT:
with QMutexLocker(lock):
    do_something()
```

**WRONG: Synchronous I/O on main thread:**
```python
# Freezes UI!
def load_data(self):
    self.data = json.load(open(path))  # BLOCKS

# CORRECT: Use worker thread
worker = DataLoaderWorker(path)
_ = worker.finished.connect(self._on_data_loaded)
worker.start()
```

### 10.2 Performance Anti-Patterns

**WRONG: Excessive logging:**
```python
# Too verbose, slows down execution
for item in large_list:
    self.logger.debug(f"Processing {item}")  # 1000s of logs
    process(item)

# CORRECT: Log summary
self.logger.debug(f"Processing {len(items)} items")
for item in large_list:
    process(item)
self.logger.debug(f"Completed {len(items)} items")
```

**WRONG: Creating widgets in loop:**
```python
# Slow and memory-intensive
for shot in shots:
    widget = ShotWidget(shot)  # Repeats initialization
    self.layout.addWidget(widget)

# CORRECT: Use model-view pattern
model = ShotItemModel(shots)
view = ShotGridView(model)
self.layout.addWidget(view)
```

**WRONG: Full data copy everywhere:**
```python
# Unnecessary memory usage
shots = self.model.get_shots()  # Returns copy
for shot in shots:  # Iterate copy
    cache.add(shot)  # Copy again

# CORRECT: Return references when safe
shots = self.model._shots  # Direct reference (const)
for shot in shots:
    cache.add(shot)
```

---

## SUMMARY OF KEY PRINCIPLES

1. **Testing**: Use test doubles, fixtures with cleanup, signal spies
2. **Error Handling**: Use ErrorHandlingMixin for consistency, catch specific exceptions
3. **Logging**: Use LoggingMixin, appropriate levels, contextual info
4. **Configuration**: Static Config class, environment overrides, feature flags
5. **Code Style**: PEP 604 unions, descriptive names, comprehensive type hints
6. **Qt Patterns**: ALWAYS include parent parameter, use QMutex for thread safety, offscreen platform for tests
7. **Managers**: Thread-safe state, signal-based communication, cleanup timers
8. **Caching**: TTL for temporary data, merge for incremental updates, persistent for history
9. **Architecture**: Dependency injection, generic base classes, model-view separation
10. **Performance**: Worker threads for I/O, incremental loads, minimal UI locks
