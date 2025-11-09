# Testing Fixtures Guide

## Overview

This guide documents the fixture patterns used in the Shotbot test suite. Understanding when and how to use these fixtures is essential for writing reliable, maintainable tests.

## Quick Reference

| Pattern | When to Use | Example |
|---------|-------------|---------|
| **Factory Fixtures** | Need multiple instances with different configurations | `make_test_shot`, `make_test_filesystem` |
| **Real Components** | Testing core business logic and data integrity | `cache_manager`, `settings_manager` |
| **Mock Components** | Isolating from external dependencies (filesystem, subprocess) | `mock_process_pool_manager` |
| **Autouse Cleanup** | Ensuring Qt state cleanup between tests | `qt_cleanup`, `cleanup_state` |
| **Parameterized Fixtures** | Testing multiple configurations of the same scenario | `@pytest.fixture(params=[...])` |

---

## Fixture Categories

### 1. Factory Fixtures (Reusable Instance Creators)

Factory fixtures return **functions** that create test instances with custom parameters. This pattern is ideal when you need multiple instances with different configurations in a single test.

#### Available Factory Fixtures

##### `make_test_shot`
Creates Shot instances with custom parameters.

```python
def test_multiple_shots(make_test_shot):
    """Example: Creating multiple shots with different configurations."""
    shot1 = make_test_shot(shot_number="010", status="active")
    shot2 = make_test_shot(shot_number="020", status="complete")
    shot3 = make_test_shot(shot_number="030", status="pending")

    assert shot1.shot_number == "010"
    assert shot2.status == "complete"
```

**Parameters:**
- `show`, `sequence`, `shot_number`: Shot identification
- `status`: Shot status (active, complete, pending)
- `frame_range`: Tuple of (start, end) frames
- `resolution`: Tuple of (width, height)
- `camera_name`: Camera identifier
- All other Shot model fields

##### `make_test_filesystem`
Creates VFX directory structures with .3de files.

```python
def test_scene_discovery(make_test_filesystem, tmp_path):
    """Example: Creating realistic VFX filesystem structure."""
    filesystem = make_test_filesystem(
        base_dir=tmp_path,
        shows=["ProjectA", "ProjectB"],
        sequences_per_show=2,
        shots_per_sequence=3,
        users=["alice", "bob"],
        create_3de_files=True,
    )

    # Returns dict with:
    # filesystem["shows"] = ["ProjectA", "ProjectB"]
    # filesystem["threede_files"] = [list of created .3de paths]
    # filesystem["structure"] = {show: {seq: [shots]}}

    assert len(filesystem["threede_files"]) > 0
```

**Parameters:**
- `base_dir`: Root directory (typically `tmp_path`)
- `shows`: List of show names
- `sequences_per_show`: Number of sequences per show
- `shots_per_sequence`: Number of shots per sequence
- `users`: List of user names
- `create_3de_files`: Whether to create .3de files

##### `make_test_launcher`
Creates Launcher instances with optional mocked dependencies.

```python
def test_launcher_behavior(make_test_launcher, qtbot):
    """Example: Testing launcher with different configurations."""
    launcher1 = make_test_launcher(
        mock_subprocess=True,
        mock_filesystem=False,
    )
    launcher2 = make_test_launcher(
        initial_shot=my_shot,
        parent=my_widget,
    )
```

**Parameters:**
- `mock_subprocess`: Mock subprocess calls (default: True)
- `mock_filesystem`: Mock filesystem operations (default: False)
- `initial_shot`: Pre-loaded Shot instance
- `parent`: Qt parent widget

##### `make_real_3de_file`
Creates valid .3de files with realistic content.

```python
def test_3de_file_parsing(make_real_3de_file, tmp_path):
    """Example: Creating .3de file for parser testing."""
    file_path = make_real_3de_file(
        directory=tmp_path,
        show="MyShow",
        sequence="seq010",
        shot="shot020",
        user="alice",
        camera_name="CameraA",
    )

    # File contains valid 3DE data structure
    assert file_path.exists()
    assert file_path.suffix == ".3de"
```

---

### 2. Real Component Fixtures

These fixtures provide **real instances** of core components, properly configured for testing. Use these when testing business logic and data integrity.

#### `cache_manager`
Real CacheManager instance with isolated temporary directory.

```python
def test_cache_persistence(cache_manager):
    """Example: Testing cache behavior with real filesystem."""
    cache_manager.cache_shot(my_shot)

    # Cache is written to temp directory
    cached_shots = cache_manager.get_cached_shots()
    assert len(cached_shots) > 0

    # Cleanup handled automatically by fixture
```

**Features:**
- Uses temporary directory (auto-cleanup)
- Real JSON serialization
- Real file I/O
- Isolated from production cache

#### `settings_manager`
Real SettingsManager instance with isolated settings file.

```python
def test_settings_persistence(settings_manager):
    """Example: Testing settings with real storage."""
    settings_manager.set_value("my_key", "my_value")

    # Settings are written to temp file
    value = settings_manager.get_value("my_key")
    assert value == "my_value"
```

**Features:**
- Uses temporary settings file
- Real QSettings backend
- Isolated from production settings

---

### 3. Mock Component Fixtures

These fixtures provide **mocked versions** of external dependencies. Use these to isolate tests from filesystem, network, or subprocess operations.

#### `mock_process_pool_manager`
Patches ProcessPoolManager for subprocess isolation.

```python
def test_launcher_without_subprocess(mock_process_pool_manager, make_test_launcher):
    """Example: Testing launcher without spawning processes."""
    launcher = make_test_launcher()

    # Subprocess calls are mocked
    launcher.launch_nuke()

    # Verify mock was called
    mock_process_pool_manager.submit_task.assert_called_once()
```

**NOT autouse** - Only used in tests that need subprocess isolation.

#### `monkeypatch` (pytest builtin)
Use for patching specific methods or attributes.

```python
def test_file_dialog_cancel(monkeypatch, main_window):
    """Example: Simulating user canceling a dialog."""
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        lambda *args, **kwargs: "",  # User canceled
    )

    result = main_window.load_images()
    assert result is False  # Load canceled
```

---

### 4. Autouse Cleanup Fixtures

These fixtures run **automatically** for every test to ensure proper cleanup and isolation. You don't need to request them explicitly.

#### `qt_cleanup` (autouse)
Cleans up Qt state after each test.

```python
@pytest.fixture(autouse=True)
def qt_cleanup(qtbot):
    """Ensures Qt event queue is processed and widgets are cleaned."""
    yield
    process_qt_events()  # Flush deleteLater without qtbot.wait()
    # All Qt widgets with parents are auto-deleted
```

**What it does:**
- Processes pending Qt events
- Allows Qt to clean up parented widgets
- Prevents Qt state leakage between tests

**You don't need to:**
- Explicitly delete Qt widgets with parents
- Call `deleteLater()` on parented widgets
- Process events manually at test end

> ℹ️ **`process_qt_events()` helper**  
> Tiny waits (`qtbot.wait(1)`) used to spin pytest-qt's nested event loop and caused
> xdist workers to tear down out of order. Import `process_qt_events` from
> `tests.test_helpers` whenever you need to flush deleteLater()/timers without a real
> timeout:
>
> ```python
> from tests.test_helpers import process_qt_events
>
> def test_refresh_button(qtbot, widget):
>     widget.refresh()
>     process_qt_events()  # replaces qtbot.wait(1)
> ```
>
> The session autouse fixture also patches `qtbot.wait(ms)` so calls with
> `ms <= 5` automatically route through the helper. Anything longer should continue
> to use `qtbot.wait()` or `qtbot.waitUntil()` as appropriate.

#### `cleanup_state` (autouse)
Resets singleton state after each test.

```python
@pytest.fixture(autouse=True)
def cleanup_state():
    """Resets all singletons to pristine state."""
    yield
    # Reset all singletons
    ProgressManager.reset()
    NotificationManager.reset()
    ProcessPoolManager.reset()
    FilesystemCoordinator.reset()
    # Clear caches
    CacheManager.clear_cache()
```

**What it does:**
- Resets all singleton instances
- Clears all caches
- Ensures fresh state for each test

**You don't need to:**
- Manually reset singletons in tests
- Clear caches between tests
- Worry about singleton pollution

#### `clear_module_caches` (autouse)
Clears LRU caches and other module-level caches.

```python
@pytest.fixture(autouse=True)
def clear_module_caches():
    """Clears all LRU caches and importlib caches."""
    yield
    # Clear LRU caches (e.g., @lru_cache decorators)
    # Clear importlib caches
```

#### `prevent_qapp_exit` (autouse)
Prevents QApplication.exit() from terminating test suite.

```python
@pytest.fixture(autouse=True)
def prevent_qapp_exit(monkeypatch):
    """Prevents QApplication.exit() from killing pytest."""
    monkeypatch.setattr(QApplication, "exit", lambda *args: None)
```

#### `suppress_qmessagebox` (autouse, integration tests only)
Auto-dismisses QMessageBox dialogs in integration tests.

```python
@pytest.fixture(autouse=True)
def suppress_qmessagebox(monkeypatch):
    """Auto-dismisses message boxes to prevent test hangs."""
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.Ok)
```

**Only active in tests/integration/** - Unit tests can test actual dialog behavior.

---

### 5. Qt-Specific Fixtures

#### `qtbot`
pytest-qt fixture for Qt event processing and widget interaction.

```python
def test_button_click(qtbot):
    """Example: Testing button click with qtbot."""
    button = QPushButton("Click me")
    qtbot.addWidget(button)  # Auto-cleanup

    with qtbot.waitSignal(button.clicked, timeout=1000):
        qtbot.mouseClick(button, Qt.LeftButton)
```

**Common operations:**
- `qtbot.addWidget(widget)` - Track widget for cleanup
- `qtbot.mouseClick(widget, button)` - Simulate mouse click
- `qtbot.keyClick(widget, key)` - Simulate key press
- `qtbot.waitSignal(signal, timeout)` - Wait for signal emission
- `qtbot.wait(ms)` - Process events for duration

#### `qapp`
QApplication instance (created once per test session).

```python
def test_qt_functionality(qapp):
    """Example: Testing code that needs QApplication."""
    # qapp is already running
    widget = QWidget()
    assert qapp.activeWindow() is None
```

**Bootstrap behavior:** `tests/conftest.py` instantiates the QApplication as soon as the
module is imported via `_GLOBAL_QAPP`. This guarantees that heavy integration helpers
that create widgets during import see a live Qt stack, preventing the historical
`Fatal Python error: Aborted` crash when running `pytest tests/`.

**Usage notes:**
- Most tests don't need to explicitly request `qapp`—it already exists.
- Request it explicitly only when you need direct QApplication access (e.g., for
  monkeypatching or querying global Qt state).

---

## Best Practices

### 1. Prefer Real Components for Business Logic

```python
# ✅ GOOD: Testing cache with real filesystem
def test_cache_persistence(cache_manager):
    cache_manager.cache_shot(my_shot)
    cached = cache_manager.get_cached_shots()
    assert len(cached) == 1

# ❌ BAD: Mocking the thing you're trying to test
def test_cache_persistence_mocked(mocker):
    mock_cache = mocker.Mock()
    mock_cache.cache_shot.return_value = None
    # Not actually testing anything!
```

### 2. Use Mocks for External Dependencies

```python
# ✅ GOOD: Mocking subprocess to avoid side effects
def test_launcher_start(mock_process_pool_manager, make_test_launcher):
    launcher = make_test_launcher()
    launcher.launch_nuke()
    mock_process_pool_manager.submit_task.assert_called_once()

# ❌ BAD: Spawning real subprocess in test
def test_launcher_start_real():
    launcher = Launcher()
    launcher.launch_nuke()  # Spawns real Nuke process!
```

### 3. Always Parent Qt Widgets

```python
# ✅ GOOD: Widget with parent (auto-cleanup)
def test_widget_creation(qtbot):
    parent = QWidget()
    qtbot.addWidget(parent)

    child = QWidget(parent)  # Parent handles cleanup
    assert child.parent() == parent

# ❌ BAD: Unparented widget (memory leak)
def test_widget_creation_bad():
    widget = QWidget()  # No parent, no cleanup!
    # Memory leak in test suite
```

### 4. Use Factory Fixtures for Multiple Instances

```python
# ✅ GOOD: Factory fixture for multiple instances
def test_shot_comparison(make_test_shot):
    shot1 = make_test_shot(shot_number="010")
    shot2 = make_test_shot(shot_number="020")
    shot3 = make_test_shot(shot_number="030")

    assert shot1.shot_number < shot2.shot_number < shot3.shot_number

# ❌ BAD: Manual instance creation (verbose, error-prone)
def test_shot_comparison_bad():
    shot1 = Shot(show="MyShow", sequence="seq010", shot_number="010", ...)
    shot2 = Shot(show="MyShow", sequence="seq010", shot_number="020", ...)
    # Lots of repetition, easy to make mistakes
```

### 5. Don't Request Autouse Fixtures

```python
# ✅ GOOD: Autouse fixtures run automatically
def test_state_isolation():
    # qt_cleanup, cleanup_state, etc. run automatically
    manager = ProgressManager.get_instance()
    assert manager is not None

# ❌ UNNECESSARY: Explicitly requesting autouse fixture
def test_state_isolation_redundant(qt_cleanup, cleanup_state):
    # These run automatically anyway!
    manager = ProgressManager.get_instance()
```

---

## Common Patterns

### Pattern 1: Testing with Temporary Filesystem

```python
def test_filesystem_operations(make_test_filesystem, tmp_path):
    """Create VFX directory structure for testing."""
    filesystem = make_test_filesystem(
        base_dir=tmp_path,
        shows=["ProjectA"],
        sequences_per_show=1,
        shots_per_sequence=2,
        users=["alice"],
        create_3de_files=True,
    )

    # Test file discovery
    threede_files = filesystem["threede_files"]
    assert len(threede_files) == 2  # 1 seq × 2 shots × 1 user
```

### Pattern 2: Testing Qt Signals

```python
def test_signal_emission(qtbot, make_test_launcher):
    """Wait for signal emission with qtbot."""
    launcher = make_test_launcher()

    with qtbot.waitSignal(launcher.scene_loaded, timeout=1000):
        launcher.load_scene("path/to/scene.3de")

    # Signal was emitted successfully
```

### Pattern 3: Testing User Input

```python
def test_user_cancels_dialog(monkeypatch, main_window):
    """Simulate user canceling a file dialog."""
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        lambda *args, **kwargs: "",  # User canceled
    )

    result = main_window.load_images()
    assert result is False
```

### Pattern 4: Testing with Real Cache

```python
def test_cache_expiration(cache_manager, make_test_shot):
    """Test cache TTL with real CacheManager."""
    shot = make_test_shot()

    # Cache with 1-second TTL
    cache_manager.cache_shot(shot, ttl_seconds=1)

    # Immediate retrieval should work
    cached = cache_manager.get_cached_shots()
    assert len(cached) == 1

    # Wait for expiration
    time.sleep(1.1)

    # Cache should be expired
    cached_after = cache_manager.get_cached_shots()
    assert len(cached_after) == 0
```

### Pattern 5: Testing Thread Safety

```python
@pytest.mark.concurrency
def test_thread_safe_singleton(qtbot):
    """Test singleton thread safety."""
    results = []

    def worker():
        instance = MySingleton.get_instance()
        results.append(id(instance))

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # All threads got same instance
    assert len(set(results)) == 1
```

---

## Fixture Reference

### Main Conftest (`tests/conftest.py`)

| Fixture | Autouse | Scope | Returns | Purpose |
|---------|---------|-------|---------|---------|
| `qapp` | No | session | QApplication | Qt application instance |
| `qtbot` | No | function | QtBot | Qt testing utilities |
| `qt_cleanup` | **Yes** | function | None | Qt state cleanup |
| `cleanup_state` | **Yes** | function | None | Singleton reset |
| `clear_module_caches` | **Yes** | function | None | LRU cache clearing |
| `prevent_qapp_exit` | **Yes** | function | None | Prevent suite termination |
| `stable_random_seed` | **Yes** | function | None | Reproducible randomness |
| `isolated_test_environment` | No | function | None | Combined cleanup |
| `make_test_shot` | No | function | Callable | Shot factory |
| `make_test_filesystem` | No | function | Callable | Filesystem factory |
| `make_test_launcher` | No | function | Callable | Launcher factory |
| `make_real_3de_file` | No | function | Callable | .3de file factory |
| `cache_manager` | No | function | CacheManager | Real cache instance |
| `settings_manager` | No | function | SettingsManager | Real settings instance |
| `mock_process_pool_manager` | No | function | Mock | Subprocess mock |

### Integration Conftest (`tests/integration/conftest.py`)

| Fixture | Autouse | Scope | Returns | Purpose |
|---------|---------|-------|---------|---------|
| `suppress_qmessagebox` | **Yes** | function | None | Auto-dismiss dialogs |
| `integration` | **Yes** | class | None | Mark integration tests |

---

## Troubleshooting

### Problem: Qt widget not cleaning up

**Solution:** Ensure widget has a parent.

```python
# ✅ GOOD
parent = QWidget()
qtbot.addWidget(parent)
child = QWidget(parent)  # Parent handles cleanup

# ❌ BAD
widget = QWidget()  # No parent, no cleanup
```

### Problem: Singleton state leaking between tests

**Solution:** Verify singleton has `reset()` method and is in `cleanup_state` fixture.

```python
# In your singleton class
@classmethod
def reset(cls) -> None:
    """Reset singleton for testing."""
    with cls._lock:
        cls._instance = None

# In tests/conftest.py cleanup_state fixture
MySingleton.reset()
```

### Problem: Test fails only when run with others

**Solution:** Test has state pollution. Check for:
1. Unparented Qt widgets
2. Singleton state not being reset
3. Module-level caches not being cleared
4. File handles not being closed

### Problem: Mock not being used

**Solution:** Ensure fixture is requested if not autouse.

```python
# ✅ GOOD
def test_with_mock(mock_process_pool_manager):
    # Mock is active

# ❌ BAD
def test_without_mock():
    # mock_process_pool_manager not requested, real calls made
```

---

## Summary

- **Use factory fixtures** (`make_test_*`) for creating multiple configured instances
- **Use real components** (`cache_manager`, `settings_manager`) for business logic tests
- **Use mocks** (`mock_process_pool_manager`) for external dependencies
- **Trust autouse fixtures** - they handle cleanup automatically
- **Always parent Qt widgets** - prevents memory leaks
- **Follow the patterns** in this guide for consistent, reliable tests

See also:
- [UNIFIED_TESTING_V2.MD](./UNIFIED_TESTING_V2.MD) - Comprehensive testing guide
- [tests/conftest.py](/home/gabrielh/projects/shotbot/tests/conftest.py) - Fixture implementations
- [CLAUDE.md](./CLAUDE.md) - Qt Widget Guidelines section
