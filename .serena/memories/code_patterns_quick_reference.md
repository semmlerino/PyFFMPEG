# Code Patterns Quick Reference - ShotBot

## Testing - Common Patterns

```python
# Fixture with cleanup
@pytest.fixture
def process_manager(qapp):
    manager = LauncherProcessManager()
    try:
        yield manager
    finally:
        manager.shutdown()
        manager.deleteLater()

# Parametrized tests
@pytest.mark.parametrize("ext,valid", [(".jpg", True), (".pdf", False)])
def test_valid_ext(ext, valid):
    assert is_valid(ext) == valid

# Signal testing
spy = QSignalSpy(manager.process_started)
manager.execute_command("test")
assert len(spy) == 1
assert spy[0][0] == "expected_id"

# Mocking subprocess
@patch("module.subprocess.Popen")
def test_something(mock_popen):
    mock_popen.return_value.pid = 12345
```

## Error Handling - Common Patterns

```python
# Safe execution
return self.safe_execute(
    self._load_file,
    default=None,
    log_error=True,
    reraise=False
)

# Safe file operation
return self.safe_file_operation(
    Path.read_text,
    path=filepath,
    default="",
    create_parent=True
)

# With context manager
with self.error_context("operation_name") as ctx:
    do_something()
    ctx["result"] = "success"

# Retry with backoff
return self.retry_on_error(
    fetch_api,
    max_retries=3,
    delay_seconds=1.0,
    backoff_factor=2.0
)
```

## Logging - Common Patterns

```python
# Use LoggingMixin
class MyClass(LoggingMixin):
    def method(self):
        self.logger.info("Info message")
        self.logger.debug(f"Debug: {value}")
        self.logger.error(f"Error: {e}")

# Debug conditionally
if self.logger.isEnabledFor(logging.DEBUG):
    self.logger.debug(f"Traceback:\n{traceback.format_exc()}")

# Operation tracking
with self.error_context("database_update") as ctx:
    # Logs: Starting, Completed, or error
    update_db()
```

## Configuration - Common Patterns

```python
# Access constants
from config import Config

timeout = Config.SUBPROCESS_TIMEOUT_SECONDS
path = f"{Config.SHOWS_ROOT}/{show}/shots"

# Environment override
SHOWS_ROOT = os.environ.get("SHOWS_ROOT", "/shows")

# Feature flags
if Config.ENABLE_BACKGROUND_REFRESH:
    start_refresh_timer()
```

## Qt Patterns - Common Mistakes to Avoid

```python
# CORRECT: Always include parent parameter
class MyWidget(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)  # PASS PARENT!

# CORRECT: Use QMutexLocker for thread safety
with QMutexLocker(self._lock):
    self._data[key] = value

# CORRECT: Connect with QueuedConnection for cross-thread
_ = worker.finished.connect(
    on_finished,
    Qt.ConnectionType.QueuedConnection
)

# CORRECT: Use nested function to avoid lambda capture issue
def on_finished(key: str):
    cleanup(key)
_ = worker.finished.connect(on_finished)

# CORRECT: Offscreen platform before Qt imports
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication
```

## Manager/Controller Pattern

```python
@final
class ManagerClass(LoggingMixin, QObject):
    signal1 = Signal(str)  # Declare signals
    signal2 = Signal(int, bool)
    
    def __init__(self):
        super().__init__()
        self._lock = QMutex()
        self._data = {}
        
        # Timer for cleanup
        self._cleanup_timer = QTimer()
        _ = self._cleanup_timer.timeout.connect(self._periodic_cleanup)
        self._cleanup_timer.start(5000)
    
    # Public execution methods
    def execute_operation(self, ...):
        # Work with thread-safe access
        with QMutexLocker(self._lock):
            result = self._do_work()
        self.signal1.emit(result)
    
    # Public query methods
    def get_state(self):
        with QMutexLocker(self._lock):
            return dict(self._data)  # Return copy
    
    # Private maintenance
    def _periodic_cleanup(self):
        # Cleanup finished items
        to_remove = [k for k, v in self._data.items() if v.is_done()]
        with QMutexLocker(self._lock):
            for k in to_remove:
                del self._data[k]
    
    def shutdown(self):
        self._cleanup_timer.stop()
```

## Caching Pattern

```python
class CacheManager(LoggingMixin):
    def __init__(self):
        super().__init__()
        self._lock = threading.Lock()
    
    # TTL cache
    def get_cached(self, key: str) -> dict | None:
        with self._lock:
            cached = self._read_json(f"{key}.json")
        
        if self._is_expired(cached):
            return None
        return cached
    
    # Persistent cache (no TTL)
    def get_persistent(self, key: str) -> dict | None:
        with self._lock:
            # No expiry check
            return self._read_json(f"{key}.json")
    
    # Incremental merge
    def merge_incremental(self, cached: list, fresh: list):
        cached_by_key = {get_key(item): item for item in cached}
        fresh_by_key = {get_key(item): item for item in fresh}
        
        # Result: fresh + deleted from cache
        merged = list(fresh)
        for key, item in cached_by_key.items():
            if key not in fresh_by_key:
                merged.append(item)  # Preserve deleted
        
        return merged
    
    # Write cache
    def cache_data(self, key: str, data: dict) -> bool:
        with self._lock:
            return self._write_json(f"{key}.json", data)
```

## Type Hints - Modern Syntax

```python
# Union types (Python 3.10+)
def func(x: int | None) -> str | None:
    pass

# Generic with TypeVar
from typing import TypeVar, Generic
T = TypeVar("T")

class Container(Generic[T]):
    def add(self, item: T) -> None:
        pass

# Function type
from typing import Callable
def process(fn: Callable[[int], str]) -> str:
    return fn(42)

# Avoid circular imports
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from pyside6.QtWidgets import QApplication
```

## Naming Conventions

```python
# Classes: PascalCase
class ShotModel
class LauncherProcessManager

# Functions/Methods: snake_case
def load_shots()
def execute_command()

# Constants: UPPER_SNAKE_CASE
DEFAULT_SIZE = 350
MAX_WORKERS = 4

# Private: _prefix
def _internal_method()
self._cache = {}
```

## Docstring Template

```python
"""Module docstring with clear purpose."""

class ClassName:
    """Class docstring explaining role.
    
    Additional context about usage and design.
    """
    
    def method(self, param1: str, param2: int = 0) -> bool:
        """Method docstring.
        
        Args:
            param1: Description
            param2: Description with default
        
        Returns:
            Description of return value
        
        Raises:
            ValueError: When parameter is invalid
        """
```

## Signal Declaration and Emission

```python
from PySide6.QtCore import Signal, QObject

class MyObject(QObject):
    # Declare at class level
    my_signal = Signal(str)  # One arg
    my_signal2 = Signal(str, int, bool)  # Multiple args
    
    def do_something(self):
        # Emit signal
        self.my_signal.emit("value")
        self.my_signal2.emit("text", 42, True)

# Connect in another class
obj = MyObject()
_ = obj.my_signal.connect(self.on_signal)
# or with lambda (capture by default arg)
_ = obj.my_signal.connect(
    lambda x: self.on_signal(x),
    Qt.ConnectionType.QueuedConnection
)
```

## Thread Safety - Snapshot Pattern

```python
def cleanup_finished(self):
    # Get snapshot while holding lock
    with QMutexLocker(self._lock):
        snapshot = list(self._active_items.items())
    
    # Process outside lock (prevents deadlock)
    for key, item in snapshot:
        if item.is_finished():
            with QMutexLocker(self._lock):
                del self._active_items[key]
```

## Property Pattern (with parent requirement)

```python
class MyWidget(QWidget):
    def __init__(
        self,
        initial_value: str = "",
        parent: QWidget | None = None,  # REQUIRED
    ) -> None:
        super().__init__(parent)  # REQUIRED
        self._value = initial_value
    
    @property
    def value(self) -> str:
        return self._value
    
    @value.setter
    def value(self, new_value: str) -> None:
        if self._value != new_value:
            self._value = new_value
```

## Override Decorator (Python 3.11+)

```python
from typing_extensions import override  # NOT typing!

class Base:
    def method(self):
        pass

class Derived(Base):
    @override
    def method(self):
        super().method()
        # Additional implementation
```

## Common Assertion Patterns

```python
# Qt signals
assert signal.emit_count == 1
assert signal.last_emission == (expected_arg,)
assert signal.emissions[0] == (first_arg,)

# State
assert manager.get_active_count() == 0
assert len(manager.get_data()) == 42

# Cache
assert cache.get("key") is not None
assert not cache.has_valid_data("key")
```

## Disable Pytest Collection

```python
class SignalDouble:
    # Prevent pytest from collecting this as a test class
    __test__ = False
```

## Test Isolation - Qt Cleanup

```python
@pytest.fixture(autouse=True)
def cleanup_qt(qtbot):
    """Automatic Qt cleanup after each test."""
    yield
    qtbot.wait(1)  # Process pending events
```
