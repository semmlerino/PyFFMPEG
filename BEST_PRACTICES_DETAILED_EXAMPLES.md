# Shotbot Best Practices - Detailed Code Examples

This document provides detailed before/after examples for the issues identified in `BEST_PRACTICES_REVIEW.md`.

---

## Example 1: LoggingMixin Simplification

### Current Code (Overly Complex)

**File:** `notification_manager.py`
```python
# Lines 40-80
from logging_mixin import LoggingMixin

class NotificationManager(LoggingMixin, QObject):
    """Notification system for ShotBot application."""
    
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)  # Calls both LoggingMixin and QObject.__init__
        # LoggingMixin provides self.logger via MRO
        self.logger.info("NotificationManager initialized")
```

**File:** `logging_mixin.py` (What users don't see)
```python
class LoggingMixin:
    """Mixin providing logger attribute."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # This sets up self.logger somewhere in the chain
```

**Problems:**
1. Developer reading `NotificationManager` doesn't see where `self.logger` comes from
2. MRO confusion - which `__init__` gets called first?
3. Type checking struggles with mixin attributes
4. Extra complexity for a 2-line feature

### Simplified Code

```python
# notification_manager.py
import logging
from PySide6.QtWidgets import QObject

class NotificationManager(QObject):
    """Notification system for ShotBot application."""
    
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.info("NotificationManager initialized")
```

**Benefits:**
- Self-documenting: logger initialization is explicit
- No mixin confusion
- Type checkers understand it
- 3 lines vs 20+ with mixin infrastructure

---

## Example 2: Sentinel + RLock Simplification

### Current Code (Over-Cautious Thread Safety)

**File:** `type_definitions.py`
```python
from pathlib import Path
import threading
from typing import cast

# Sentinel object to distinguish "not searched" from "searched and found nothing"
_NOT_SEARCHED = object()

@dataclass(slots=True)
class Shot:
    show: str
    sequence: str
    shot: str
    workspace_path: str
    
    # Sentinel field for lazy loading
    _cached_thumbnail_path: Path | None | object = field(
        default=_NOT_SEARCHED,
        init=False,
        repr=False,
        compare=False,
    )
    
    # Heavy-weight lock for thread safety
    _thumbnail_lock: threading.RLock = field(
        default_factory=threading.RLock,
        init=False,
        repr=False,
        compare=False,
    )

    def get_thumbnail_path(self) -> Path | None:
        """Get first available thumbnail or None."""
        # Double-checked locking pattern (complex!)
        if self._cached_thumbnail_path is not _NOT_SEARCHED:
            return cast("Path | None", self._cached_thumbnail_path)

        with self._thumbnail_lock:  # Acquire lock
            # Check again inside lock
            if self._cached_thumbnail_path is not _NOT_SEARCHED:
                return cast("Path | None", self._cached_thumbnail_path)

            # Expensive operation
            thumbnail = PathUtils.find_shot_thumbnail(
                Config.SHOWS_ROOT,
                self.show,
                self.sequence,
                self.shot,
            )
            self._cached_thumbnail_path = thumbnail
            return thumbnail
```

**Problems:**
1. Sentinel object is cryptic
2. RLock is heavy for a read-heavy operation
3. Double-checked locking is complex concurrency pattern
4. Type confusion: `Path | None | object`
5. 3 conditional checks per access
6. Performance: Two lock acquisitions per first access

### Simplified Code - Option 1 (Simple Boolean)

```python
@dataclass(slots=True)
class Shot:
    show: str
    sequence: str
    shot: str
    workspace_path: str
    
    _cached_thumbnail: Path | None = field(default=None, init=False)
    _thumbnail_loaded: bool = field(default=False, init=False)

    def get_thumbnail_path(self) -> Path | None:
        """Get cached thumbnail path."""
        if not self._thumbnail_loaded:
            self._cached_thumbnail = PathUtils.find_shot_thumbnail(
                Config.SHOWS_ROOT,
                self.show,
                self.sequence,
                self.shot,
            )
            self._thumbnail_loaded = True
        return self._cached_thumbnail
```

**Benefits:**
- Clear semantics: `_thumbnail_loaded` is obvious
- Simple boolean instead of sentinel
- No locks needed (UI is single-threaded)
- Type system is happy: `Path | None`
- 1 check per access

### Simplified Code - Option 2 (Python 3.8+ cached_property)

```python
from functools import cached_property

@dataclass(slots=True)
class Shot:
    show: str
    sequence: str
    shot: str
    workspace_path: str

    @cached_property
    def thumbnail_path(self) -> Path | None:
        """Get cached thumbnail path (cached after first access)."""
        return PathUtils.find_shot_thumbnail(
            Config.SHOWS_ROOT,
            self.show,
            self.sequence,
            self.shot,
        )

# Usage:
shot = Shot(...)
path = shot.thumbnail_path  # First access: expensive lookup
path = shot.thumbnail_path  # Second access: cached, no lookup
```

**Benefits:**
- Pythonic standard library solution
- Zero boilerplate
- Automatically cached
- Type checkers love it
- Works for read-only properties

---

## Example 3: SignalManager Removal

### Current Code (Unnecessary Abstraction)

**File:** `ui_components.py` (typical usage)
```python
from signal_manager import SignalManager

class MyWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Initialize signal manager for this widget
        self.signal_manager = SignalManager(self)
        
        self.button = QPushButton("Click me")
        self.model = SomeDataModel()
        
        # Connect signals through the manager
        self.signal_manager.connect_safely(
            self.button.clicked,
            self.on_button_clicked,
            track=True
        )
        
        self.signal_manager.connect_safely(
            self.model.data_changed,
            self.on_data_changed,
            connection_type=Qt.ConnectionType.QueuedConnection,
            track=True
        )

    def on_button_clicked(self):
        """Handle button click."""
        self.model.update_data()

    def on_data_changed(self):
        """Handle model data changes."""
        self.update_display()

    def cleanup(self):
        """Clean up signal connections."""
        self.signal_manager.disconnect_all()
```

**Problems:**
1. Extra manager object to maintain
2. Tracking is rarely used in practice
3. Qt's built-in mechanism is already thread-safe
4. Adds indirection: `signal_manager.connect_safely()` vs `signal.connect()`
5. Error handling hides real problems

### Simplified Code (Native Qt)

```python
class MyWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.button = QPushButton("Click me")
        self.model = SomeDataModel()
        
        # Direct signal connections (Qt handles thread-safety)
        self.button.clicked.connect(self.on_button_clicked)
        
        self.model.data_changed.connect(
            self.on_data_changed,
            type=Qt.ConnectionType.QueuedConnection
        )

    def on_button_clicked(self) -> None:
        """Handle button click."""
        self.model.update_data()

    @Slot()  # Explicit slot decorator
    def on_data_changed(self) -> None:
        """Handle model data changes."""
        self.update_display()

    # No cleanup needed - Qt handles it via parent/child ownership!
```

**Benefits:**
1. **100 fewer lines of code** (no SignalManager)
2. Qt's proven thread-safe implementation
3. Every developer knows `signal.connect()`
4. Built-in cleanup via parent/child ownership
5. No tracking overhead
6. Problems surface immediately (not silently logged)

---

## Example 4: SettingsManager Refactoring

### Current Code (Over-Engineered)

**File:** `settings_manager.py` (~500 lines)
```python
from PySide6.QtCore import QSettings, Signal, QObject

@final
class SettingsManager(LoggingMixin, QObject):
    """Manages application settings with type safety."""
    
    # Multiple signals
    settings_changed = Signal(str, object)
    category_changed = Signal(str)
    settings_reset = Signal()

    def __init__(self, org="ShotBot", app="ShotBot"):
        super().__init__()
        self.settings = QSettings(org, app)
        self._initialize_defaults()
        self._migrate_old_settings()

    def _get_default_settings(self) -> dict[str, dict[str, object]]:
        """Return 200+ lines of default settings."""
        return {
            "window": {
                "geometry": QByteArray(),
                "state": QByteArray(),
                "size": QSize(1200, 800),
            },
            "preferences": {
                "refresh_interval": 30,
                "background_refresh": True,
                "thumbnail_size": 256,
                # ... 30+ more settings ...
            },
            # ... 4+ more categories ...
        }

    # 50+ getter/setter methods like:
    def get_refresh_interval(self) -> int:
        value = self.settings.value("preferences/refresh_interval", 30)
        return int(value) if value else 30

    def set_refresh_interval(self, value: int) -> None:
        if not (1 <= value <= 1440):
            raise ValueError(f"Invalid: {value}")
        self.settings.setValue("preferences/refresh_interval", value)
        self.settings_changed.emit("refresh_interval", value)

    def get_thumbnail_size(self) -> int:
        value = self.settings.value("preferences/thumbnail_size", 256)
        return int(value) if value else 256

    def set_thumbnail_size(self, value: int) -> None:
        if value < 64:
            raise ValueError(f"Invalid: {value}")
        self.settings.setValue("preferences/thumbnail_size", value)
        self.settings_changed.emit("thumbnail_size", value)

    # ... 40+ more similar methods ...
```

**Problems:**
1. **500 lines for type-safe CRUD** - Should be 50 lines
2. Getter/setter boilerplate for each field
3. Validation scattered across 50 methods
4. Signals rarely used but add noise
5. Defaults defined separately from usage
6. Hard to see all settings at once

### Simplified Code (Dataclass-Based)

```python
from dataclasses import dataclass, field
from PySide6.QtCore import QSettings

@dataclass
class AppSettings:
    """Application settings with validation."""
    
    # Window settings
    window_width: int = 1200
    window_height: int = 800
    
    # Preferences
    refresh_interval: int = 30
    background_refresh: bool = True
    thumbnail_size: int = 256
    
    def __post_init__(self) -> None:
        """Validate settings after initialization."""
        # Validate refresh interval
        if not (1 <= self.refresh_interval <= 1440):
            self.refresh_interval = 30
        
        # Validate thumbnail size
        if self.thumbnail_size < 64:
            self.thumbnail_size = 256

    @classmethod
    def load(cls) -> AppSettings:
        """Load settings from QSettings."""
        qs = QSettings("ShotBot", "ShotBot")
        
        return cls(
            window_width=qs.value("window/width", 1200, int),
            window_height=qs.value("window/height", 800, int),
            refresh_interval=qs.value("preferences/refresh_interval", 30, int),
            background_refresh=qs.value("preferences/background_refresh", True, bool),
            thumbnail_size=qs.value("preferences/thumbnail_size", 256, int),
        )

    def save(self) -> None:
        """Save settings to QSettings."""
        qs = QSettings("ShotBot", "ShotBot")
        
        qs.setValue("window/width", self.window_width)
        qs.setValue("window/height", self.window_height)
        qs.setValue("preferences/refresh_interval", self.refresh_interval)
        qs.setValue("preferences/background_refresh", self.background_refresh)
        qs.setValue("preferences/thumbnail_size", self.thumbnail_size)

# Usage:
settings = AppSettings.load()
settings.refresh_interval = 60  # Direct property access
settings.save()

# In tests - no QSettings needed!
test_settings = AppSettings(refresh_interval=1)
assert test_settings.refresh_interval == 1
```

**Benefits:**
1. **500 lines → 80 lines** (84% reduction!)
2. All settings visible in one place
3. Validation is explicit in `__post_init__`
4. Easy to test (instantiate directly)
5. IDE autocomplete works perfectly
6. Better type checking
7. Can use for both UI and tests

---

## Example 5: Python Idioms - Union Types and Overloads

### Current Code (Over-Complex)

**File:** `cache_manager.py`
```python
def _shot_to_dict(shot: Shot | ShotDict) -> ShotDict:
    """Convert Shot object or ShotDict to ShotDict."""
    if isinstance(shot, dict):
        return shot
    return shot.to_dict()

def _scene_to_dict(scene: object) -> ThreeDESceneDict:
    """Convert ThreeDEScene object or dict to ThreeDESceneDict."""
    if isinstance(scene, dict):
        return cast("ThreeDESceneDict", scene)
    return scene.to_dict()  # pyright: ignore[reportOptionalMemberAccess]
```

**Problems:**
1. Type information lost in `isinstance()` check
2. Using `object` instead of proper type
3. `cast()` needed to placate type checker
4. Type checker can't verify correctness
5. Runtime cost of `isinstance()` checks

### Improved Code (Using @overload)

```python
from typing import overload

@overload
def shot_to_dict(shot: ShotDict) -> ShotDict: ...

@overload
def shot_to_dict(shot: Shot) -> ShotDict: ...

def shot_to_dict(shot: Shot | ShotDict) -> ShotDict:
    """Convert Shot object or dict to ShotDict."""
    if isinstance(shot, dict):
        return shot
    return shot.to_dict()

# Type checker now understands:
shot_dict: ShotDict = {"show": "S01", ...}
result1 = shot_to_dict(shot_dict)  # Returns ShotDict

shot_obj = Shot("S01", "SQ01", "SH01", "/path")
result2 = shot_to_dict(shot_obj)   # Returns ShotDict
```

**Benefits:**
1. Type checker verifies correctness
2. IDE provides better autocomplete
3. Self-documenting API
4. No runtime `cast()` needed
5. Clear overload intent

---

## Example 6: Error Handling Pattern

### Current Code (Hidden Exceptions)

**File:** `error_handling_mixin.py`
```python
class ErrorHandlingMixin(LoggingMixin):
    def safe_execute(
        self,
        operation: Callable[..., T],
        *args: object,
        default: T | None = None,
        log_error: bool = True,
        reraise: bool = False,
        **kwargs: object,
    ) -> T | None:
        """Execute operation with standard error handling."""
        try:
            return operation(*args, **kwargs)
        except Exception as e:  # Catches ALL exceptions!
            if log_error:
                self.logger.error(f"Operation failed: {e}")
            if reraise:
                raise
            return default

# Usage:
class MyClass(ErrorHandlingMixin):
    def load_config(self):
        # Silent exception swallowing!
        return self.safe_execute(
            Path.read_text,
            Path("/config.json"),
            default=""
        )
```

**Problems:**
1. **Catches all exceptions** - Including bugs!
2. FileNotFoundError, PermissionError, etc. all silently return default
3. Can't tell what went wrong without reading logs
4. Hard to test exception paths
5. Hides bugs

### Better Code (Explicit Error Handling)

```python
class MyClass:
    def load_config(self) -> str:
        """Load config from file, return empty string if missing."""
        config_path = Path("/config.json")
        
        try:
            return config_path.read_text()
        except FileNotFoundError:
            # Expected - file doesn't exist yet
            self.logger.warning(f"Config not found: {config_path}")
            return ""
        except PermissionError as e:
            # Real problem - log and raise
            self.logger.error(f"Cannot read config: {e}")
            raise
        except Exception as e:
            # Unexpected - definitely a problem
            self.logger.error(f"Unexpected error reading config: {e}")
            raise
```

**Benefits:**
1. Clear which exceptions are expected
2. Different handling for different errors
3. Bugs surface immediately (not hidden)
4. Easy to test exception paths
5. Explicit is better than implicit

---

## Summary of Patterns

| Pattern | Old (Complex) | New (Simple) | Benefit |
|---------|---------------|-------------|---------|
| Logging | Mixin + MRO | Direct init | Clearer, faster |
| Caching | Sentinel + RLock | Boolean flag | Simpler, clearer types |
| Signals | SignalManager wrapper | Native Qt | Proven, less code |
| Settings | 50 getters/setters | Dataclass | 80% less code |
| Type hints | `object` + cast | @overload | Better IDE support |
| Errors | Generic catch-all | Specific handlers | Bugs surface faster |

