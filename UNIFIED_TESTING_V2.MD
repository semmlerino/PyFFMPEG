


## Quick Start

```bash
# Development: parallel for speed
uv run pytest -n 2 --dist=worksteal

# CI/pre-merge: serial to catch leaks
uv run pytest -n 0 --maxfail=1

# Re-run last failed tests
uv run pytest --lf

# Skip performance tests on WSL/CI
uv run pytest -m "not perf"
```

---

## Basic Qt Testing Hygiene

**Five non-negotiable rules for reliable Qt tests:**

### 1. Use pytest-qt's `qapp` fixture
**Never create your own QApplication.** This solves the "Module-Level Qt App Creation" problem before it starts.
```python
# ✅ RIGHT
def test_widget(qapp, qtbot):
    widget = MyWidget()
    qtbot.addWidget(widget)
```

### 2. Always use try/finally for Qt resources
**Guarantee cleanup even on test failure.** Essential for preventing resource leaks.
```python
# ✅ RIGHT
timer = QTimer()
try:
    timer.start(50)
    qtbot.waitUntil(lambda: condition)
finally:
    timer.stop()
    timer.deleteLater()
```

### 3. Use qtbot.waitSignal/waitUntil, never time.sleep()
**The #1 rule for avoiding flaky tests.** Condition-based waiting is non-negotiable.
```python
# ✅ RIGHT
with qtbot.waitSignal(worker.finished, timeout=5000):
    worker.start()

# Or use helper
from tests.helpers.synchronization import wait_for_condition
wait_for_condition(lambda: widget.is_ready, timeout_ms=2000)
```

### 4. Always use tmp_path for filesystem tests
**Simple, clean, perfect isolation.** No cleanup needed, pytest handles it.
```python
# ✅ RIGHT
def test_file_creation(tmp_path):
    test_file = tmp_path / "data.json"
    test_file.write_text('{"key": "value"}')
    assert test_file.exists()
```

**Note on pytest-qt API**: `qtbot.assertNotEmitted()` uses the `wait=` parameter (added years ago as the official API). Use `wait=` in all code (shown in examples below).

### 5. Use monkeypatch for state isolation
**Core pytest pattern for independent tests.** Essential for parallel execution safety.
```python
# ✅ RIGHT
def test_config_path(tmp_path, monkeypatch):
    monkeypatch.setattr("config.Config.SHOWS_ROOT", str(tmp_path))
    # Now your test uses tmp_path instead of real filesystem
```

---

## Key Testing Principles (UNIFIED_TESTING_GUIDE)

### Core Philosophy

1. **Test Behavior, Not Implementation**: Focus on what code does, not how
2. **Use Real Components**: Minimal mocking, real filesystems with tmp_path
3. **Tests Must Be Independent**: Runnable alone, in any order, on any worker
4. **Fix Isolation, Don't Serialize**: Never use xdist_group as a band-aid

---

## Test Isolation and Parallel Execution ⚠️ CRITICAL

### The Golden Rule

**Every test must be runnable**:
- Alone (in isolation)
- In any order
- On any worker (in parallel)
- Multiple times consecutively

### Common Root Causes of Isolation Failures

#### 1. Qt Resource Leaks
**Symptom**: Pass individually, fail intermittently in parallel
```python
# ❌ WRONG - timer leaks if test fails
timer.start(50)
qtbot.waitUntil(lambda: condition)
timer.stop()  # Never reached if waitUntil raises

# ✅ RIGHT - always cleaned up
try:
    timer.start(50)
    qtbot.waitUntil(lambda: condition)
finally:
    timer.stop()
    timer.deleteLater()
```

#### 2. Global/Module-Level State
**Symptom**: Tests see unexpected values from other workers
```python
# ❌ WRONG - shared globally
path = f"{Config.SHOWS_ROOT}/gator/shots"

# ✅ RIGHT - isolated with monkeypatch
monkeypatch.setattr("config.Config.SHOWS_ROOT", str(tmp_path))
```

#### 3. Module-Level Caches
**Fix**: Automatic since 2025-11-04 via `clear_module_caches` autouse fixture
- Clears VersionUtils, path caches, LRU caches before/after each test
- **Default**: Rely on the autouse cache clearer
- **Exception**: If a test mutates persistent cache on disk as part of behavior under test, clean it explicitly in that test

**Implementation** (`tests/conftest.py`):
```python
import functools
import inspect
import pytest

@pytest.fixture(autouse=True)
def clear_module_caches(monkeypatch):
    """Clear common in-memory caches before/after each test."""
    try:
        from src import cache_manager, version_utils  # adjust import paths for your project
        modules_to_clear = (cache_manager, version_utils)
    except (ModuleNotFoundError, ImportError):
        # Module not found or moved - skip clearing for this test
        modules_to_clear = ()

    # Clear LRU caches and other cached functions
    for mod in modules_to_clear:
        for name, obj in inspect.getmembers(mod):
            if hasattr(obj, "cache_clear"):
                obj.cache_clear()

    yield

    # Clear again after test (defense in depth - only needed if tests mutate caches)
    for mod in modules_to_clear:
        for name, obj in inspect.getmembers(mod):
            if hasattr(obj, "cache_clear"):
                obj.cache_clear()
```

#### 4. Qt Platform Initialization (CRITICAL) 🔴
**Symptom**: Fatal Python error: Aborted, "real widgets" appear
**Fix**: Set at top of `tests/conftest.py` BEFORE Qt imports:
```python
import os
from pathlib import Path

# Use offscreen platform (can override via environment if needed)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Create unique XDG runtime directory per worker (0700 perms to avoid Qt6 warnings/races)
run_id = os.environ.get("PYTEST_XDIST_TESTRUNUID", "solo")
worker = os.environ.get("PYTEST_XDIST_WORKER", "master")
xdg = f"/tmp/xdg-{run_id}-{worker}"
os.makedirs(xdg, mode=0o700, exist_ok=True)
os.chmod(xdg, 0o700)  # Enforce permissions if dir already existed
os.environ.setdefault("XDG_RUNTIME_DIR", xdg)
```
**Why**: Prevents windowing platform from being used in headless/WSL environments. Unique XDG directory per worker prevents Qt6 warnings and races across xdist workers.

#### 5. Speeding up Qt tests with -n (balance speed vs. debuggability) 🔴
**Strategy**: Use parallel execution for development speed; serial for deterministic CI behavior
**Fix**: Fix isolation issues (use try/finally for cleanup, proper Qt resource management)
```bash
# Development: parallel for speed
uv run pytest tests/unit/ -n 2  # ✅ Faster execution (30s vs 60s)

# CI/pre-merge: serial for determinism
pytest tests/unit/ -n 0 --maxfail=1  # ✅ Nightly job for deterministic behavior
```
**Why**: Parallelism surfaces test hygiene bugs more aggressively (dangling signals, lingering threads, shared state). **If tests crash in parallel but pass serially, this is ALWAYS a test hygiene bug, NOT a Qt limitation.** Serial execution makes problems more obvious (they compound deterministically) and is easier to debug (no worker interleaving). NOTE: This is NOT because "Qt accumulates leaks" (see "Large Qt Test Suite Stability" section) — Qt's object model handles cleanup properly. Use `-n` for development speed, serial for catching isolation issues.

**On WSL**: Higher parallelism (`-n 4`, `-n 16`) surfaces isolation bugs more aggressively. It's not Qt's event loop "running out of capacity" — fix the test hygiene issues (dangling signals, lingering threads, shared caches), and use serial runs in CI to make bugs deterministic.

#### 6. Persistent Cache Files
**Problem**: Disk cache persists between tests; memory cleared but not disk
**Default**: Rely on autouse fixture for automatic cleanup
**Exception**: When testing cache behavior itself, explicitly clear:
```python
main_window.shot_model.shots = []  # Memory
cache_manager.clear_cache()         # Disk - only when testing cache behavior
```
**Better**: Use `defer_background_loads=True` in MainWindow to prevent background interference (see section 8 below). This is preferred over manual cache clearing in tests.

#### 6a. Shared Cache Directories 🔴
**Problem**: Tests using `CacheManager()` without `cache_dir` parameter share `~/.shotbot/cache_test` directory, which accumulates data across test runs
**Symptom**: Tests pass in isolation, fail only in full suite with parallel execution
**Discovery**: Bisection shows failure only with full suite, cached data found in shared directory with recent timestamps
**Fix**: Clean shared cache directory in autouse fixture with race condition handling:
```python
# In tests/conftest.py
@pytest.fixture(autouse=True)
def clear_module_caches():
    import shutil
    from pathlib import Path

    # Clear shared cache directory before test
    shared_cache_dir = Path.home() / ".shotbot" / "cache_test"
    if shared_cache_dir.exists():
        try:
            shutil.rmtree(shared_cache_dir)
        except FileNotFoundError:
            # Race condition in pytest-xdist: another worker may have deleted it
            pass

    yield

    # Clear again after test (defense in depth)
    if shared_cache_dir.exists():
        try:
            shutil.rmtree(shared_cache_dir)
        except FileNotFoundError:
            pass
```
**Best Practice**: Always use `tmp_path` for cache directories in tests:
```python
# ✅ RIGHT - isolated cache per test
def test_cache_behavior(tmp_path):
    cache_manager = CacheManager(cache_dir=tmp_path / "cache")

# ❌ WRONG - shares ~/.shotbot/cache_test across all tests
def test_cache_behavior():
    cache_manager = CacheManager()  # Uses default shared directory
```
**Find Violators**: `grep -r "CacheManager()" tests/ | grep -v "cache_dir"`

#### 6b. Debugging Parallel Test Failures 🔴
**Symptom**: Tests crash during parallel execution (`-n 2` or higher) but pass in serial

**Root Cause Identification**:
1. ✅ **This is ALWAYS a test hygiene issue** (dangling signals, lingering threads, shared caches, singleton state)
2. ❌ **This is NEVER "Qt can't handle parallelism" or "event loop exhaustion"**

**Diagnostic Steps**:
1. **Run the failing test file in isolation**:
   ```bash
   pytest path/to/test_file.py -v
   ```
   - If it passes → contamination from another test (dangling signals, shared state)
   - If it fails → internal test hygiene issue within the file

2. **For contamination from another test**:
   - Note which tests run before the failing test in parallel execution
   - Search those tests for signal connections without corresponding disconnections
   - Search for threads that aren't properly stopped
   - Check for singleton state that isn't reset

3. **Common causes**:
   - **Dangling signal connections**: Lambda/function handlers connected but never disconnected
     ```python
     # ❌ WRONG - handlers leak across tests
     model.signal.connect(lambda: do_something())

     # ✅ RIGHT - stored and disconnected
     handler = lambda: do_something()
     model.signal.connect(handler)
     try:
         # test code
     finally:
         model.signal.disconnect(handler)
     ```
   - **Threads not properly stopped**: Background threads still running after test completes
   - **Singleton state not reset**: Singletons holding references to deleted objects
   - **QObjects not properly deleted**: Missing `deleteLater()` + event loop drain

4. **Verify the fix**:
   ```bash
   # Run the sequence of tests that were crashing
   pytest tests/path1.py tests/path2.py tests/failing.py -v
   ```

**Key Insight**: Parallel execution is a diagnostic tool that reveals test hygiene bugs by making timing non-deterministic. The solution is always to fix the hygiene issue, never to avoid parallelism.

#### 7. Module-Level Qt App Creation 🔴
**Problem**: Creating `QCoreApplication` at module import → conflicts with `QApplication`
**Symptom**: Full suite crashes, individual files work
**Fix**: Only create in fixtures/functions, never at module level. **Use pytest-qt's `qapp` fixture.**
```python
# ❌ WRONG - at module level
app = QCoreApplication.instance() or QCoreApplication([])

# ✅ RIGHT - use pytest-qt's qapp fixture
def test_something(qapp):
    # qapp provides the QApplication instance
    assert qapp is not None

# ✅ ALSO RIGHT - custom fixture if needed (use QApplication, not QCoreApplication)
@pytest.fixture
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])
```
**Find**: `grep -r "QCoreApplication\|QApplication" tests/ | grep -v "def \|class \|@"`

#### 8. Background Async Operations
**Problem**: Background loaders clear data during `qtbot.wait()`
**Symptom**: `len(shots) == 2` becomes `len(shots) == 0` after `qtbot.wait(100)`
**Fix**: Clear cache before setup + reload if cleared
```python
cache_manager.clear_cache()  # Prevent stale cache triggering reload
window.shot_model.shots = [shot1, shot2]
qtbot.wait(100)
if len(window.shot_model.shots) == 0:
    window.shot_model.refresh_shots()  # Reload with mocked pool
```
**Better**: Prefer deferring background loads until after UI is shown in tests (feature flag or constructor arg):
```python
# In production code:
class MainWindow:
    def __init__(self, defer_background_loads=False):
        self.defer_background_loads = defer_background_loads
        if not defer_background_loads:
            self.start_background_loaders()

# In tests:
window = MainWindow(defer_background_loads=True)
# Set up test data without background interference
window.shot_model.shots = [shot1, shot2]
```

### Anti-Patterns

#### xdist_group as Band-Aid
**Wrong**: Using `xdist_group` to "fix" parallel failures
**Right**: Fix the actual isolation issue (resource cleanup, global state)
- xdist_group appropriate ONLY for external constraints (hardware, license server)
- NOT for Qt state, filesystem, or timing issues

#### Autouse for Mocks
**Wrong**: `autouse=True` for global patches → worker isolation failures
**Right**: Explicit fixtures (request what you need)
```python
# ❌ WRONG - significant overhead from global patch
@pytest.fixture(autouse=True)
def mock_subprocess(): ...

# ✅ RIGHT - explicit opt-in
@pytest.fixture
def mock_subprocess(): ...
def test_something(mock_subprocess): ...
```
**Autouse appropriate ONLY for**:
- Qt cleanup (affects 100% of Qt tests)
- Cache clearing (prevents contamination)
- QMessageBox mocking (prevents modal dialogs)
- Random seed stabilization (reproducible tests)
**NOT for**: subprocess, filesystem, database mocking

#### Essential Autouse Fixtures

**Suppress modal QMessageBox dialogs** (`tests/conftest.py`):
```python
import pytest
from PySide6 import QtWidgets

@pytest.fixture(autouse=True)
def suppress_qmessagebox(monkeypatch):
    """Auto-dismiss modal dialogs to prevent blocking tests."""
    def _noop(*args, **kwargs):
        return QtWidgets.QMessageBox.StandardButton.Ok

    # Mock static convenience methods
    for name in ("information", "warning", "critical", "question"):
        monkeypatch.setattr(QtWidgets.QMessageBox, name, _noop, raising=True)

    # Also mock instance-style exec() to catch stray dialogs
    monkeypatch.setattr(QtWidgets.QMessageBox, "exec", _noop, raising=False)
```

**Stabilize random seeds** (`tests/conftest.py`):
```python
@pytest.fixture(autouse=True)
def stable_random_seed():
    """Fix random seeds for reproducible tests (pairs well with pytest-randomly)."""
    import os
    import random

    random.seed(12345)

    try:
        import numpy as np
        np.random.seed(12345)
    except ImportError:
        pass  # numpy not installed

    # Note: pytest-randomly still shuffles test ORDER
    # This fixture makes each test's random values deterministic
```

### Distribution Modes

**Use `--dist=worksteal`** (already in Quick Start and pytest.ini examples above)
- Idle workers steal from busy ones → recommended for varying test durations
- Other modes (`load`, `loadscope`, `loadfile`) may be better for specific fixture-reuse patterns

---

## Testing Principles in Detail

### 1. Test Behavior, Not Implementation

**Good**: Test what the code does (observable behavior)
```python
def test_plate_priority_selection():
    """FG01 is selected over BG01 due to higher priority."""
    # Test that FG is chosen, not how the selection algorithm works
    assert selected_plate == "FG01"
```

**Bad**: Test how the code does it (implementation details)
```python
def test_plate_selection_algorithm():
    """Test the internal sorting algorithm."""
    # Don't test internal methods or data structures
```

### 2. Use Real Components (Minimal Mocking)

**Good**: Real implementations with real data
```python
def test_thumbnail_loading(tmp_path):
    # Create real directory structure
    thumbnail = tmp_path / "test.jpg"
    thumbnail.write_bytes(b"...")

    # Use real CacheManager
    cache = CacheManager(cache_dir=tmp_path / "cache")
```

**Bad**: Excessive mocking
```python
def test_thumbnail_loading(mocker):
    # Mock everything
    mocker.patch("pathlib.Path")
    mocker.patch("CacheManager")
```

**When to Use Real vs. Fake**:
- **Integration tests**: Use real components with `tmp_path` for realistic behavior
- **Unit tests**: May use `pyfakefs` or in-memory fakes for speed when I/O is expensive
- **System boundaries**: Mock subprocess, network, external APIs

**When to Mock**:
- System boundaries (subprocess, network, external APIs)
- Qt signals (use QSignalSpy instead of mocking)
- External dependencies (databases, license servers)

### 3. Duck Typing and Protocols

**Prefer testing call site behavior over capability probes**:
```python
# BETTER - Test that the behavior works
def test_populate_show_filter_with_model():
    """Test that populate_show_filter works with model objects."""
    view.populate_show_filter(model)  # Calls model.get_available_shows()
    assert view.show_filter.count() > 0

# OKAY - Capability probe (useful for interface validation)
def test_model_has_method():
    """Test object supports expected interface."""
    assert hasattr(model, "get_available_shows")
    result = model.get_available_shows()
    assert isinstance(result, list)
```
**Warning**: hasattr tests can pass while behavior still breaks. Prefer testing the actual call site.

**Prefer Protocols over isinstance() for type safety**:
```python
# Define interface
class HasAvailableShows(Protocol):
    def get_available_shows(self) -> list[str]: ...

# Use in type hints (enables type checking without isinstance)
def populate_show_filter(self, shows: list[str] | HasAvailableShows) -> None:
    if isinstance(shows, list):
        show_list = shows
    else:
        show_list = shows.get_available_shows()
```

### 4. Time Control Without Sleeps

**Use time-machine or freezegun for time-based logic**:
```python
# Install: pip install time-machine
def test_expiration_logic(tmp_path):
    """Test cache expiration without waiting."""
    import time_machine

    cache.store("key", "value", ttl=60)
    assert cache.get("key") == "value"

    # Jump forward in time (no sleep!)
    with time_machine.travel(time.time() + 61):
        assert cache.get("key") is None  # Expired
```
**Why**: Fast, deterministic time-based tests. Aligns with "minimal mocking" (real logic, controlled time).

### 5. Real Filesystem Operations

**Use tmp_path for File Tests**:
```python
def test_script_discovery(tmp_path):
    """Test finding scripts in plate directory."""
    plate_dir = tmp_path / "comp/nuke/FG01"
    plate_dir.mkdir(parents=True)
    script = plate_dir / "shot01_mm-default_FG01_scene_v001.nk"
    script.write_text("# Nuke script")

    result = find_existing_scripts(tmp_path, "shot01", "FG01")
```

### 6. Parametrization for Coverage

**Use `@pytest.mark.parametrize` for combinatorics** (cheapest way to improve coverage):
```python
@pytest.mark.parametrize("plate_type,priority", [
    ("FG", 10),
    ("PL", 20),
    ("BG", 30),
])
def test_plate_priority_ordering(plate_type, priority):
    """Test priority ordering for different plate types."""
    assert Config.TURNOVER_PLATE_PRIORITY[plate_type] == priority
```
**Why**: Test multiple scenarios without duplicating test logic. Aligns with "test behavior, not implementation."

### 7. Configuration Validation

**Validate constraints, not implementation**:
```python
def test_plate_priority_ordering():
    """Validate plate priorities maintain correct ordering."""
    priorities = Config.TURNOVER_PLATE_PRIORITY
    assert priorities["FG"] < priorities["PL"] < priorities["BG"]
```

### 8. Run Tests Frequently

- Run tests before committing: `uv run pytest tests/unit/ -n auto`
- Run specific tests during development
- Use `--lf` flag to run only last failed: `pytest --lf`

### 9. Pin PySide6 Minor Version

**One-liner tip**: Pin a PySide6 minor version (e.g., `PySide6~=6.7.0`) in dev dependencies to reduce UI test churn from Qt patch updates.
```toml
# pyproject.toml or requirements.txt
PySide6 = "~=6.7.0"  # Allow patches (6.7.1, 6.7.2), block minors (6.8.0)
```


## Advanced Session Fixtures

**See "Isolating Session Resources with Test-Run UID" section in Advanced Testing Infrastructure below for complete pattern with file locks and shared setup across workers.**

---

## Known Issues & Platform-Specific Notes

### ✅ FIXED Issues (Historical Reference)
1. **Module-Level Qt App Creation** (2025-11-05) - Use pytest-qt's `qapp` fixture. See "Common Root Causes" → section 7.
2. **Qt Platform Crashes** (2025-11-02) - Set `QT_QPA_PLATFORM="offscreen"` in conftest.py. See section 4 above.

### WSL-Specific Notes
- **pytest-xvfb**: Disabled via `-p no:xvfb` in pytest.ini (causes timeouts)
- **Performance tests**: 4 tests marked `@pytest.mark.perf` are skipped in WSL/CI (use `pytest -m "not perf"`)
- **Expected results**: 2,276-2,281 passed, 5 skipped

---

## Advanced Testing Infrastructure

### Test Order Randomization
**Recommended**: Use `pytest-randomly` to surface hidden test coupling
```bash
pip install pytest-randomly
pytest tests/ --randomly-seed=auto  # Different order each run
```
**Why**: Tests must pass under random order. Pair with `--maxfail=1` to catch the first failure.

### Test Timeouts
**Recommended**: Add `pytest-timeout` to kill hung async/Qt tests deterministically
```bash
pip install pytest-timeout
```
```ini
# In pytest.ini:
[pytest]
timeout = 120  # 2 minutes per test (use 60-120s for snappier feedback)
timeout_method = thread
```

### Strict Markers & CI Configuration
**Recommended pytest.ini settings**:
```ini
# pytest.ini
[pytest]
addopts =
    --strict-markers
    -ra  # Show all test summary info (includes short summary, warnings, errors)
    --durations=20  # Show slowest 20 tests
    -n auto  # Parallel by default locally
    --dist=worksteal  # Recommended load balancing for varying test durations
    # In CI: override with -n 0 for serial leak detection
    # Note: -q (quiet mode) omitted for personal apps - context is valuable

markers =
    perf: Performance comparison tests (may be skipped in CI/WSL)
    slow: Tests taking >1 second
    fast: Tests under 100ms
    integration: Integration tests requiring full setup
```

**Note**: If using `pyproject.toml` instead, use `[tool.pytest.ini_options]` as the section header.

### Coverage & Type Gates
**Recommended CI checks**:
```bash
# Branch coverage (optional gate - use locally or for critical modules only)
pytest --cov=src --cov-branch --cov-report=term-missing
# For personal apps: --cov-fail-under=85 can create churn; use as optional local target

# Type checking (close the loop with Protocols)
mypy src/ --strict
# or
basedpyright src/
```

### Flaky Test Policy
**Approach**: Fix root cause, don't mask with retries
```python
# ❌ WRONG - Masks the problem
@pytest.mark.flaky(reruns=3)
def test_sometimes_fails():
    ...

# ✅ RIGHT - Fix the isolation issue
def test_fixed(qtbot, monkeypatch):
    # Proper cleanup, state isolation, condition-based waiting
    ...
```
**Exception**: External service flakiness may warrant `@pytest.mark.flaky`, but document why.

### Large Qt Test Suite Stability 🔴

**Common Misconception**: "Qt accumulates C++ memory leaks in large test suites"

**Short Answer**: No — not as a general rule.

Qt doesn't "accumulate C++ memory leaks" simply from creating/deleting lots of widgets. Qt's object model is designed so that when a parent QObject/QWidget is destroyed it deletes its children, preventing leaks ([Qt Object Trees](https://doc.qt.io/qt-6/objecttrees.html)); large suites can create and destroy thousands of widgets safely. If you see crashes after many tests, it's almost always test-hygiene issues in your code or lingering global state, not Qt "corrupting itself."

**What Actually Causes Large Serial Qt Test Runs to Crash**:

1. **Lingering Objects Between Tests**
   - Objects left alive between tests (timers, threads, network ops)
   - `deleteLater()` without draining the event loop → dangling signals/slots and use-after-free
   - **Tip**: At test cleanup boundaries, flush deferred deletes:
     ```python
     from PySide6.QtCore import QCoreApplication, QEvent
     QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
     QCoreApplication.processEvents()
     ```
   - **Caution**: Use only at cleanup boundaries (teardown, autouse fixture cleanup), not mid-test or in production code. Forced event processing can introduce re-entrancy issues. Qt's event loop normally processes `DeferredDelete` events automatically; this manual flush is for ensuring deletion when you need certainty (e.g., end of test).

2. **Multiple QApplication Instances**
   - Repeated construction/destruction of Q(Core|Gui|)Application in one process
   - Tests that mutate global Qt state (style, locale, env) without restoring it
   - **Solution**: Use Qt Test best practices; keep tests self-contained ([Qt Test Tutorial](https://doc.qt.io/qt-6/qtest-tutorial.html))
   - **Or**: Split suites into multiple binaries so each runs in a fresh process

3. **Pixmap/Icon Caches**
   - QPixmapCache/QIconCache making memory look like it "leaks"
   - That's expected allocator/caching behavior, not a leak
   - **Solution**: Tune or clear between tests if needed:
     ```python
     from PySide6.QtGui import QPixmapCache
     QPixmapCache.setCacheLimit(...)  # Tune limit
     QPixmapCache.clear()              # Clear between tests
     ```
   - **Reference**: [QPixmapCache Documentation](https://doc.qt.io/qt-6/qpixmapcache.html)

4. **User Path/Config Contamination**
   - Tests touching real user paths/config files
   - **Solution**: Enable test mode so writes go to temp locations:
     ```python
     from PySide6.QtCore import QStandardPaths
     QStandardPaths.setTestModeEnabled(True)
     ```
   - **Reference**: [QStandardPaths Test Mode](https://doc.qt.io/qt-6/qstandardpaths.html#setTestModeEnabled)

5. **Misinterpreting Allocator Behavior**
   - Common allocators don't eagerly return freed memory to OS
   - RSS may stay high even without leaks — that's not Qt corruption
   - **Reference**: [Understanding Memory Usage](https://stackoverflow.com/questions/tagged/memory-management)

**Hardening Checklist for Large Qt Test Suites**:

✅ **One QApplication per test process**
- Avoid constructing/destroying it repeatedly
- Use separate test executables for different needs
- **Reference**: [QApplication Documentation](https://doc.qt.io/qt-6/qapplication.html)

✅ **Clear ownership for all QObjects**
- Give every QObject a clear owner (parent) or manage lifetime explicitly
- Avoid raw, unparented heap widgets
- **Reference**: [Object Trees & Ownership](https://doc.qt.io/qt-6/objecttrees.html)

✅ **Flush deferred deletes**
- After `deleteLater()`, flush deferred deletes (see tip in #1 above)

✅ **Stop all async operations**
- Stop and `wait()` all QThreads
- Stop timers; cancel network jobs before teardown

✅ **Reset global state**
- Reset global state you changed (env vars, style, palette, locale)
- Enable QStandardPaths test mode
- **Reference**: [QStandardPaths Test Mode](https://doc.qt.io/qt-6/qstandardpaths.html#setTestModeEnabled)

✅ **Make Qt warnings fatal in CI**
- Catch problems where they happen:
  ```bash
  export QT_FATAL_WARNINGS=1
  export QT_FATAL_CRITICALS=1
  pytest tests/
  ```
- **Reference**: [Qt Environment Variables](https://doc.qt.io/qt-6/qtglobal.html#environment-variables)

✅ **Manage cache churn**
- Clear/tune caches like QPixmapCache if memory churn matters
- Consider running tests in separate processes to avoid cross-test interference

### Qt Testing Hygiene Checklist
**Always follow these patterns for Qt tests**:
1. **Parent QObjects**: Always parent to a fixture-owned parent for automatic cleanup
   ```python
   @pytest.fixture
   def main_widget(qtbot):
       widget = QWidget()
       qtbot.addWidget(widget)  # Ensures cleanup
       return widget
   ```
2. **Use qtbot.waitSignal**: Never use raw time.sleep()
   ```python
   with qtbot.waitSignal(worker.finished, timeout=5000):
       worker.start()
   ```
3. **Use qtbot.assertNotEmitted**: Verify signals don't fire
   ```python
   with qtbot.assertNotEmitted(app.error_signal, wait=500):
       app.do_safe_operation()
   ```
4. **Try/finally for resources**: Guarantee cleanup even on failure
   ```python
   timer = QTimer()
   try:
       timer.start(50)
       qtbot.waitUntil(lambda: condition)
   finally:
       timer.stop()
       timer.deleteLater()
   ```

**Thread cleanup pattern** (canonical QThread teardown):
```python
# In fixture or inline in tests that start threads
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

### Smoke Check for Module Import Side-Effects

**Add one-test smoke check** that importing top-level package has no side-effects:
```python
# tests/test_import_safety.py
def test_import_has_no_side_effects():
    """Importing shotbot module should not start QApplication or spawn threads."""
    import threading
    from PySide6.QtWidgets import QApplication

    thread_count_before = threading.active_count()
    app_before = QApplication.instance()

    # Import top-level package
    import shotbot  # noqa: F401

    # Should not create QApplication
    assert QApplication.instance() == app_before, "Import created QApplication!"

    # Should not spawn threads
    thread_count_after = threading.active_count()
    assert thread_count_after == thread_count_before, (
        f"Import spawned threads! Before: {thread_count_before}, After: {thread_count_after}"
    )
```
**Why**: Reinforces "never create apps at module scope" principle. Catches accidental side-effects early.

### Cross-Platform Matrix Testing
**Recommended CI matrix**:
```yaml
# .github/workflows/test.yml
strategy:
  matrix:
    os: [ubuntu-latest, windows-latest]
    python-version: ["3.11", "3.12"]
    pyside6-version: ["6.6", "6.7"]  # Current and previous minor
```
**Why**: Qt behavior varies across platforms. Catch platform-specific issues early.

### Setup Plan Debugging
**Quick diagnostic for fixture order issues**:
```bash
pytest tests/unit/test_file.py --setup-plan
```
This shows fixture execution order without running tests. Useful for understanding complex fixture dependencies.

### Isolating Session Resources with Test-Run UID
**Pattern**: Use `PYTEST_XDIST_TESTRUNUID` to isolate shared resources across test runs:
```python
import os
import tempfile
from pathlib import Path

# In conftest.py or test setup
RUN_UID = os.environ.get("PYTEST_XDIST_TESTRUNUID", "solo")
SHARED_DIR = Path(tempfile.gettempdir(), f"tests-shared-{RUN_UID}")
SHARED_DIR.mkdir(exist_ok=True)

# Use with file-lock pattern for session-scoped fixtures
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

### Synchronization Helpers Reference
**Location**: `tests/helpers/synchronization.py`

These helpers prevent bare `time.sleep()` and ensure condition-based waiting:

```python
# tests/helpers/synchronization.py
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
    # Use busy-wait or yield pattern instead of sleep
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

## Test Organization & Running Specific Tests

**Directory structure**: `tests/{unit,integration}/test_*.py`, shared fixtures in `tests/conftest.py`

**Run specific tests**:
```bash
# Single file
pytest tests/unit/test_config.py -v

# Specific class
pytest tests/unit/test_config.py::TestClassName -v

# By marker
pytest -m fast  # or -m "not perf"

# Pattern matching
pytest tests/unit/test_*model.py -v
```

---

## Debugging Test Failures

### Passes Alone, Fails in Parallel? → Isolation Issue

**Diagnose**:
1. Reproduce: `for i in {1..10}; do pytest path/to/test.py -n auto || break; done`
2. Identify pattern: Qt objects? Config/globals? Caches?
3. Fix: try/finally for Qt, monkeypatch for globals, verify autouse cache clearing
4. Remove xdist_group if present
5. Verify: `for i in {1..20}; do pytest path/to/test.py -n auto -q || break; done`

### Fatal Python Error: Qt C++ Crash 🔴

**Symptom**: "Fatal Python error: Aborted" in Qt widget `__init__`
**Fix**: Set `os.environ["QT_QPA_PLATFORM"] = "offscreen"` at TOP of conftest.py BEFORE Qt imports
**Verify**: `head -20 tests/conftest.py | grep QT_QPA_PLATFORM`

**Enable crash forensics**: Get C-level backtraces on hard crashes:
```python
# At top of conftest.py (session start)
import faulthandler
faulthandler.enable()
```
Or set environment variable: `export PYTHONFAULTHANDLER=1` in CI/shell.

### Common Commands

```bash
pytest path/to/test.py::test_name -vv       # Full output
pytest path/to/test.py::test_name -vv -l    # With local vars
pytest path/to/test.py::test_name -v -s     # With prints
pytest path/to/test.py::test_name --pdb     # Debugger
pytest --lf                                  # Last failed
```

### Debugging Parallel Execution

```bash
# Fixture execution order (see "Setup Plan Debugging" section for details)
pytest tests/unit/test_file.py --setup-plan

# Identify worker assignment
def test_debug(worker_id):
    print(f"Running on: {worker_id}")  # "master" or "gw0", "gw1"...

# Check environment vars
echo $PYTEST_XDIST_WORKER        # Worker name
echo $PYTEST_XDIST_WORKER_COUNT  # Total workers
echo $PYTEST_XDIST_TESTRUNUID    # Unique test run ID

# Trace state contamination
@pytest.fixture(autouse=True)
def trace_state(request, worker_id):
    before = Config.SHOWS_ROOT
    yield
    if Config.SHOWS_ROOT != before:
        print(f"[{worker_id}] {request.node.name} changed SHOWS_ROOT")
```

---

## Qt Testing Patterns (Context7-Validated)

Based on official pytest-qt documentation, use these patterns for reliable Qt testing:

### Qt Signal Mocking 🔴

**Problem**: `patch.object(..., side_effect=mock)` doesn't disconnect Qt signals → still calls original
**Solution**: Disconnect/reconnect signals directly

```python
# ❌ WRONG - side_effect doesn't affect signal connection
with patch.object(controller, "launch_app", side_effect=mock):
    button.click()  # Still executes original + mock

# ✅ RIGHT - replace signal connection (reconnect in teardown to avoid bleed-over)
def mock_launch(app_name: str):
    launch_calls.append(app_name)

original_slot = controller.launch_app
panel.app_launch_requested.disconnect(original_slot)
panel.app_launch_requested.connect(mock_launch)
try:
    button.click()  # Only mock executes
finally:
    # Reconnect original to avoid bleed-over to other tests
    panel.app_launch_requested.disconnect(mock_launch)
    panel.app_launch_requested.connect(original_slot)
```

**When to use**:
- Testing signal flow without business logic
- Avoiding validation/subprocess in integration tests
- Testing UI without backend

**When NOT to use**:
- Unit tests of actual business logic
- Testing validation itself
- System boundary mocks (use test doubles)

### Other Qt Patterns

```python
# Wait for signals (not time.sleep)
with qtbot.waitSignal(worker.finished, timeout=5000):
    worker.start()

# Assert signal NOT emitted
with qtbot.assertNotEmitted(app.error_signal, wait=500):
    app.do_safe_operation()

# Capture Qt exceptions (from virtual methods)
with qtbot.captureExceptions():
    widget.some_qt_method()

# Capture Qt logging (requires pytest-qt ≥ 1.4)
assert any("WARNING" in r.message for r in qtlog.records)

# Log assertions for your own logger (keeps tests behavioral)
def test_logging_behavior(caplog):
    """Test that operation logs expected message."""
    with caplog.at_level(logging.WARNING):
        perform_risky_operation()
    assert "deprecated API" in caplog.text
```

---

## Writing New Tests

### Checklist

1. **Choose the right pattern**:
   - Configuration? → Validation pattern
   - Static methods? → Real filesystem pattern
   - Qt components? → QSignalSpy pattern
   - Duck typing? → Protocol pattern

2. **Use appropriate fixtures**:
   - `tmp_path` for filesystem tests
   - `qtbot` for Qt tests
   - `real_cache_manager` for cache tests

3. **Write clear test names**:
   ```python
   # Good
   def test_pl_preferred_over_bg():
       """PL01 chosen over BG01 due to higher priority."""

   # Bad
   def test_plate_selection():
       """Test plate selection."""
   ```

4. **Add docstrings**:
   - Explain what behavior is tested
   - Document edge cases
   - Reference relevant bugs/issues

5. **Test behavior, not implementation**:
   - Focus on observable outcomes
   - Don't test internal methods
   - Use duck typing (hasattr) not isinstance

6. **Run tests to verify**:
   ```bash
   uv run pytest tests/unit/test_yourfile.py -v
   ```

---

## Related Documentation

- **Test Isolation Case Studies**: `docs/TEST_ISOLATION_CASE_STUDIES.md` - Real debugging examples with solutions
- **Configuration**: `docs/CONFIG_VALIDATION.md` - Configuration testing details
- **Plate Workflow**: `docs/NUKE_PLATE_WORKFLOW.md` - Plate discovery testing
- **Coverage Report**: `CLAUDE.md` - Full test coverage breakdown

---

## Best Practices Summary

### DO: ✅
1. **Use `-n 2` for speed, serial for determinism** - Parallel (30s) vs serial (60s); run serially in CI to catch isolation issues deterministically
2. **Set QT_QPA_PLATFORM & XDG_RUNTIME_DIR FIRST** - At top of conftest.py before ANY Qt imports (prevents crashes)
3. **Use explicit fixtures over autouse** - Only use autouse for true cross-cutting concerns (NEW 2025-11-04)
4. **Use real components** - CacheManager, tmp_path, QSignalSpy (minimal mocking)
5. **Test behavior, not implementation** - Focus on observable outcomes
6. **Use try/finally for Qt resources** - Guarantee cleanup always happens
7. **Isolate global state with monkeypatch** - Protect from parallel test contamination
8. **Let autouse fixture clear caches** - Automatic since 2025-11-04, don't clear manually
9. **Prefer behavior tests; use hasattr only for interface validation** - Test call sites, not just capabilities
10. **Write clear, descriptive test names** - Self-documenting test suites
11. **Add docstrings** - Explain what behavior is tested and why
12. **Run tests frequently** - During development to catch issues early
13. **Use Protocols** - For type-safe duck typing
14. **Use qtbot.waitSignal()** - For async Qt testing (not time.sleep)
15. **Use qtbot.assertNotEmitted()** - To verify signals don't fire (use `wait=` parameter)
16. **Use testrun_uid for session fixtures** - Prevents resource collisions across workers
17. **Use --dist=worksteal** - Recommended load balancing for varying test durations
18. **Disconnect/reconnect Qt signals for mocking** - Don't use patch side_effect for signals (NEW 2025-11-05)
19. **Prefer defer_background_loads=True in tests** - Prevent background loaders from interfering; fall back to cache clearing if needed (NEW 2025-11-05)
20. **Never create Qt apps at module level** - Only in fixtures/functions (NEW 2025-11-05)
21. **Use pytest-randomly for order randomization** - Surface hidden test coupling with `--randomly-seed=auto`
22. **Add pytest-timeout for hung tests** - Kill async/Qt tests that hang deterministically
23. **Prefer call site behavior tests over hasattr** - Test actual behavior, not just interface presence
24. **Use @pytest.mark.perf for performance tests** - Skip in CI/WSL with `-m "not perf"`
25. **Run --setup-plan for fixture debugging** - Diagnose fixture order issues quickly

### DON'T: ❌
1. **Use autouse for mocks** - Causes worker isolation failures and significant overhead (CRITICAL NEW 2025-11-04)
2. **Mock everything** - Only mock at system boundaries (subprocess, network)
3. **Use xdist_group as a band-aid** - Fix isolation problems instead
4. **Test private methods** - Test public API and observable behavior
5. **Use isinstance() for duck-typed objects** - Breaks test doubles
6. **Use time.sleep() or processEvents()** - Use synchronization helpers
7. **Write tests without docstrings** - Tests should be self-explanatory
8. **Commit without running tests** - Catch issues before pushing
9. **Skip edge case testing** - Edge cases are where bugs hide
10. **Ignore test failures** - Fix them immediately, don't defer
11. **Manually clear caches in tests** - Autouse fixture handles it automatically (since 2025-11-04)
12. **Use patch side_effect for Qt signals** - Doesn't disconnect real signal, still calls original (NEW 2025-11-05)
13. **Create Qt apps at module level** - Crashes full suite with QCoreApplication/QApplication conflict (NEW 2025-11-05)
14. **Ignore background async operations** - MainWindow initialization triggers loaders that clear data (NEW 2025-11-05)
15. **Use bare processEvents() without conditions** - Causes race conditions; wrap in condition-based wait
16. **Use platform-wide skips for performance tests** - Use @pytest.mark.perf instead
17. **Test hasattr without testing behavior** - Tests can pass while actual behavior breaks
18. **Use @pytest.mark.flaky to mask problems** - Fix root cause (isolation issues) instead

---
 