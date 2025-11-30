# Test Isolation Case Studies

Deep-dive debugging patterns and case studies for Qt test isolation issues. For quick reference, see [UNIFIED_TESTING_V2.md](../UNIFIED_TESTING_V2.md).

---

## Table of Contents

1. [Debugging Parallel Test Failures](#debugging-parallel-test-failures)
2. [Shared Cache Directory Issues](#shared-cache-directory-issues)
3. [Large Qt Test Suite Stability](#large-qt-test-suite-stability)
4. [Qt Cleanup Patterns](#qt-cleanup-patterns)
5. [Advanced Session Fixtures](#advanced-session-fixtures)
6. [Synchronization Helpers](#synchronization-helpers)
7. [Changelog](#changelog)

---

## Debugging Parallel Test Failures

**Symptom**: Tests crash during parallel execution (`-n 2` or higher) but pass in serial.

### Root Cause Identification

1. **This is ALWAYS a test hygiene issue** (dangling signals, lingering threads, shared caches, singleton state)
2. **This is NEVER "Qt can't handle parallelism" or "event loop exhaustion"**

### Diagnostic Steps

**1. Run the failing test file in isolation:**
```bash
pytest path/to/test_file.py -v
```
- If it passes → contamination from another test
- If it fails → internal test hygiene issue

**2. For contamination from another test:**
- Note which tests run before the failing test in parallel execution
- Search those tests for signal connections without corresponding disconnections
- Search for threads that aren't properly stopped
- Check for singleton state that isn't reset

**3. Common causes:**

**Dangling signal connections:**
```python
# WRONG - handlers leak across tests
model.signal.connect(lambda: do_something())

# RIGHT - stored and disconnected
handler = lambda: do_something()
model.signal.connect(handler)
try:
    # test code
finally:
    model.signal.disconnect(handler)
```

**Other common causes:**
- Threads not properly stopped (background threads still running after test)
- Singleton state not reset (singletons holding references to deleted objects)
- QObjects not properly deleted (missing `deleteLater()` + event loop drain)

**4. Verify the fix:**
```bash
# Run the sequence of tests that were crashing
pytest tests/path1.py tests/path2.py tests/failing.py -v
```

### Key Insight

Parallel execution is a diagnostic tool that reveals test hygiene bugs by making timing non-deterministic. The solution is always to fix the hygiene issue, never to avoid parallelism.

---

## Shared Cache Directory Issues

**Problem**: Tests using `CacheManager()` without `cache_dir` parameter share `~/.shotbot/cache_test` directory, which accumulates data across test runs.

**Symptom**: Tests pass in isolation, fail only in full suite with parallel execution.

**Discovery**: Bisection shows failure only with full suite, cached data found in shared directory with recent timestamps.

### Best Practice: Use tmp_path

```python
# RIGHT - isolated cache per test
def test_cache_behavior(tmp_path):
    cache_manager = CacheManager(cache_dir=tmp_path / "cache")

# WRONG - shares ~/.shotbot/cache_test across all tests
def test_cache_behavior():
    cache_manager = CacheManager()  # Uses default shared directory
```

### Alternative: Session-Scoped Cleanup

If you must use shared directories, clean at session level keyed by run ID:

```python
# In tests/conftest.py - session scope, not per-test
import os
from pathlib import Path

RUN_UID = os.environ.get("PYTEST_XDIST_TESTRUNUID", "solo")

@pytest.fixture(scope="session", autouse=True)
def session_cache_cleanup():
    """Clean shared cache once per session, not per test."""
    shared_cache = Path.home() / ".shotbot" / f"cache_test_{RUN_UID}"
    if shared_cache.exists():
        shutil.rmtree(shared_cache, ignore_errors=True)
    yield
    if shared_cache.exists():
        shutil.rmtree(shared_cache, ignore_errors=True)
```

**Why not per-test autouse?** Recursive `shutil.rmtree` on every test is expensive and hides which tests actually use shared state. Prefer `tmp_path` (zero overhead) or session-scoped cleanup.

**Find violators:** `grep -r "CacheManager()" tests/ | grep -v "cache_dir"`

---

## Large Qt Test Suite Stability

### The Myth: "Qt accumulates C++ memory leaks"

**Short Answer**: No.

Qt doesn't "accumulate C++ memory leaks" simply from creating/deleting lots of widgets. Qt's object model is designed so that when a parent QObject/QWidget is destroyed it deletes its children, preventing leaks ([Qt Object Trees](https://doc.qt.io/qt-6/objecttrees.html)).

Large suites can create and destroy thousands of widgets safely. If you see crashes after many tests, it's almost always test-hygiene issues in your code or lingering global state, not Qt "corrupting itself."

### What Actually Causes Large Serial Qt Test Runs to Crash

**1. Lingering Objects Between Tests**
- Objects left alive between tests (timers, threads, network ops)
- `deleteLater()` without draining the event loop

**Tip**: At test cleanup boundaries, flush deferred deletes:
```python
from PySide6.QtCore import QCoreApplication, QEvent
QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
QCoreApplication.processEvents()
```

**Caution**: Use only at cleanup boundaries, not mid-test. Forced event processing can introduce re-entrancy issues.

**2. Multiple QApplication Instances**
- Repeated construction/destruction of Q(Core|Gui|)Application in one process
- Tests that mutate global Qt state (style, locale, env) without restoring it
- **Solution**: Use pytest-qt's `qapp` fixture; keep tests self-contained

**3. Pixmap/Icon Caches**
- QPixmapCache/QIconCache making memory look like it "leaks"
- That's expected allocator/caching behavior, not a leak
```python
from PySide6.QtGui import QPixmapCache
QPixmapCache.setCacheLimit(...)  # Tune limit
QPixmapCache.clear()              # Clear between tests
```

**4. User Path/Config Contamination**
- Tests touching real user paths/config files
```python
from PySide6.QtCore import QStandardPaths
QStandardPaths.setTestModeEnabled(True)
```

**5. Misinterpreting Allocator Behavior**
- Common allocators don't eagerly return freed memory to OS
- RSS may stay high even without leaks — that's not Qt corruption

### Hardening Checklist for Large Qt Test Suites

- [ ] **One QApplication per test process** - Avoid constructing/destroying repeatedly
- [ ] **Clear ownership for all QObjects** - Give every QObject a parent or manage explicitly
- [ ] **Flush deferred deletes** - After `deleteLater()`, flush at cleanup boundaries
- [ ] **Stop all async operations** - Stop/wait all QThreads; cancel network jobs before teardown
- [ ] **Reset global state** - Reset env vars, style, palette, locale you changed
- [ ] **Make Qt warnings fatal in CI**:
  ```bash
  export QT_FATAL_WARNINGS=1
  export QT_FATAL_CRITICALS=1
  ```
- [ ] **Manage cache churn** - Clear/tune caches like QPixmapCache if memory churn matters

---

## Qt Cleanup Patterns

### Thread Cleanup (Canonical QThread Teardown)

```python
thread = QThread()
worker = MyWorker()
worker.moveToThread(thread)
try:
    thread.start()
    with qtbot.waitSignal(worker.finished, timeout=5000):
        worker.do_work()
finally:
    thread.quit()
    thread.wait(3000)  # Wait up to 3s for clean shutdown
```

### Timer Cleanup

```python
timer = QTimer()
try:
    timer.start(50)
    qtbot.waitUntil(lambda: condition)
finally:
    timer.stop()
    timer.deleteLater()
```

### Signal Connection Cleanup

```python
def mock_launch(app_name: str):
    launch_calls.append(app_name)

original_slot = controller.launch_app
panel.app_launch_requested.disconnect(original_slot)
panel.app_launch_requested.connect(mock_launch)
try:
    button.click()
finally:
    panel.app_launch_requested.disconnect(mock_launch)
    panel.app_launch_requested.connect(original_slot)
```

---

## Advanced Session Fixtures

### Isolating Session Resources with Test-Run UID

Use `PYTEST_XDIST_TESTRUNUID` to isolate shared resources across test runs:

```python
import os
import tempfile
from pathlib import Path

RUN_UID = os.environ.get("PYTEST_XDIST_TESTRUNUID", "solo")
SHARED_DIR = Path(tempfile.gettempdir(), f"tests-shared-{RUN_UID}")
SHARED_DIR.mkdir(exist_ok=True)

@pytest.fixture(scope="session")
def expensive_setup(tmp_path_factory, worker_id):
    if worker_id == "master":
        return create_expensive_resource()

    # Workers share via SHARED_DIR
    data_file = SHARED_DIR / "setup.json"
    with FileLock(str(data_file) + ".lock"):
        if data_file.is_file():
            return json.loads(data_file.read_text())
        data = create_expensive_resource()
        data_file.write_text(json.dumps(data))
        return data
```

---

## Synchronization Helpers

**Location**: `tests/helpers/synchronization.py`

These helpers prevent bare `time.sleep()` and ensure condition-based waiting:

```python
from PySide6.QtCore import QCoreApplication
import time

def wait_for_condition(cond, timeout_ms=1000, step_ms=10):
    """Wait for condition to become true, processing Qt events."""
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        if cond():
            return True
        QCoreApplication.processEvents()
        time.sleep(step_ms / 1000)
    raise TimeoutError(f"Condition not met within {timeout_ms}ms")

def simulate_work_without_sleep(duration_ms):
    """Simulate work without blocking parallel execution."""
    deadline = time.time() + duration_ms / 1000
    while time.time() < deadline:
        QCoreApplication.processEvents()
```

**Usage**:
```python
from tests.helpers.synchronization import wait_for_condition

# Always use condition-based waiting (never bare processEvents() or time.sleep())
wait_for_condition(lambda: widget.is_ready, timeout_ms=2000)
```

---

## Changelog

### 2025-11-05
- **Module-Level Qt App Creation**: Documented that using pytest-qt's `qapp` fixture solves QCoreApplication/QApplication conflicts

### 2025-11-02
- **Qt Platform Crashes**: Added requirement to set `QT_QPA_PLATFORM="offscreen"` at top of conftest.py before Qt imports
