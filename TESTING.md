# ShotBot Testing Guide

**Last Updated**: 2025-11-01
**Test Suite**: 1,975 passing tests (100% pass rate)
**Execution Time**: ~60 seconds (parallel with `-n auto`)
**Coverage**: 90% weighted (100% of critical components)

**Recent Improvements**:
- **2025-11-01**: Enhanced with official pytest-xdist best practices
  - ✅ Added distribution modes guide (worksteal, loadscope, etc.)
  - ✅ Added session-scoped fixtures for parallel execution (file locks pattern)
  - ✅ Added parallel debugging tools (--setup-plan, worker_id, environment tracing)
- **2025-10-31**: Fixed test isolation issues
  - ✅ Fixed 3 flaky tests with proper isolation
  - ✅ Removed problematic `xdist_group` markers
  - ✅ All tests now pass consistently in parallel (verified 5+ consecutive runs)

---

## Quick Start

### Running Tests

```bash
# Recommended: Full test suite with parallel execution
uv run pytest tests/unit/ -n auto --timeout=5

# Quick validation
uv run python tests/utilities/quick_test.py

# Specific test file
uv run pytest tests/unit/test_shot_model.py -v

# Specific test
uv run pytest tests/unit/test_shot_model.py::TestShot::test_shot_creation -v

# With coverage report
uv run pytest tests/unit/ --cov=. --cov-report=term-missing

# Categories
uv run pytest tests/ -m fast       # Tests under 100ms
uv run pytest tests/ -m unit       # Unit tests only
uv run pytest tests/ -m integration # Integration tests
```

### Legacy Test Runner

```bash
# Old method (still works but slower)
uv run python run_tests.py

# With coverage
uv run python run_tests.py --cov
```

### Test Organization

```
tests/
├── __init__.py
├── conftest.py          # Shared fixtures
├── unit/                # Unit tests
│   ├── __init__.py
│   ├── test_shot_model.py
│   └── test_command_launcher.py
└── integration/         # Integration tests
    └── __init__.py
```

## Current Test Coverage (Updated 2025-10-14)

### Critical Components (100% Coverage) ✅

| Module | Tests | Lines | Status |
|--------|-------|-------|--------|
| plate_discovery.py | 26 | 527 | ✅ Comprehensive (NEW) |
| shot_item_model.py | 28 | 609 | ✅ Comprehensive (NEW) |
| config.py | 27 | 578 | ✅ Validation (NEW) |
| cache_manager.py | 42 | 946 | ✅ Comprehensive |
| shot_model.py | 33 | 563 | ✅ Comprehensive |
| base_item_model.py | 48 | 653 | ✅ Comprehensive |
| raw_plate_finder.py | 23 | 610 | ✅ Comprehensive |
| undistortion_finder.py | 24 | 775 | ✅ Comprehensive |
| threede_scene_model.py | 16 | 564 | ✅ Comprehensive |
| launcher_panel.py | 21 | 594 | ✅ Comprehensive |
| main_window.py | 16 | 483 | ✅ Comprehensive |
| process_pool_manager.py | 14 | 711 | ✅ Adequate |
| nuke_launch_handler.py | 14 | 294 | ✅ Adequate |

### High-Priority Components (Integration Tested)

- optimized_shot_parser.py - Performance-critical parsing
- threede_scene_finder_optimized.py - Optimized discovery
- scene_discovery_coordinator.py - Discovery coordination
- persistent_bash_session.py - Terminal management
- secure_command_executor.py - Command execution

**Weighted Coverage: 90%** (100% of critical, indirect coverage of high-priority)

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

**Problem**: QTimer, QThread, or other Qt objects continue running after test
**Symptom**: Tests pass individually, fail intermittently in parallel

```python
# ❌ WRONG - timer may leak if test fails
def test_qt_timer(qtbot):
    timer = QTimer()
    timer.start(50)
    qtbot.waitUntil(lambda: condition, timeout=500)
    timer.stop()  # Never reached if waitUntil raises

# ✅ RIGHT - timer always cleaned up
def test_qt_timer(qtbot):
    timer = QTimer(parent_object)
    timer.start(50)
    try:
        qtbot.waitUntil(lambda: condition, timeout=500)
        assert condition
    finally:
        timer.stop()
        timer.deleteLater()
```

#### 2. Global/Module-Level State

**Problem**: Class attributes or module globals modified by parallel tests
**Symptom**: Tests see unexpected values from other tests

```python
# ❌ WRONG - Config.SHOWS_ROOT is shared globally
def test_path_parsing():
    path = f"{Config.SHOWS_ROOT}/gator/shots"

# ✅ RIGHT - monkeypatch isolates this test's view
def test_path_parsing(monkeypatch):
    original_shows_root = Config.SHOWS_ROOT
    monkeypatch.setattr("config.Config.SHOWS_ROOT", original_shows_root)
    path = f"{Config.SHOWS_ROOT}/gator/shots"
```

#### 3. Module-Level Caches

**Problem**: Cached values from previous tests contaminate current test
**Fix**: Clear caches FIRST, before any other operations

```python
# ❌ WRONG - cache cleared after contamination possible
def test_thumbnail_path(tmp_path, monkeypatch):
    shows_root = tmp_path / "shows"
    from utils import clear_all_caches
    clear_all_caches()  # Too late

# ✅ RIGHT - cache cleared BEFORE operations
def test_thumbnail_path(tmp_path, monkeypatch):
    from utils import clear_all_caches
    clear_all_caches()  # FIRST operation
    shows_root = tmp_path / "shows"
```

### The xdist_group Anti-Pattern

**Common Misconception**: Using `xdist_group` to fix parallel test failures
**Reality**: `xdist_group` is a band-aid that masks isolation problems

```python
# ❌ WRONG - using xdist_group as a band-aid
@pytest.mark.xdist_group("qt_state")
def test_with_leak():
    timer = QTimer()
    timer.start()  # Leaks into next test in group

# ✅ RIGHT - fix the leak, remove the marker
def test_with_proper_cleanup():
    timer = QTimer()
    timer.start()
    try:
        # test code
    finally:
        timer.stop()
        timer.deleteLater()
```

**Why xdist_group fails**:
1. Forces tests onto same worker, concentrating state pollution
2. Doesn't guarantee cleanup between tests in the group
3. Makes failures intermittent instead of consistent
4. Hides the root cause (shared state, improper cleanup)

**When xdist_group is actually appropriate** (rare):
- Tests that *must* run serially due to external constraints (hardware device, license server)
- NOT for fixing Qt state issues
- NOT for shared filesystem issues
- NOT for timing issues

**See Also**: `docs/TEST_ISOLATION_CASE_STUDIES.md` for real debugging examples

### Distribution Modes for Parallel Execution

pytest-xdist offers multiple distribution strategies. The default (`load`) works well, but other modes can optimize specific scenarios:

#### Available Distribution Modes

```bash
# Default: Simple load balancing (recommended for most cases)
uv run pytest -n auto --dist=load

# Group by module/class: Better fixture reuse
uv run pytest -n auto --dist=loadscope

# Worksteal: Best for tests with varying durations
uv run pytest -n auto --dist=worksteal

# Group by file: All tests in same file run on same worker
uv run pytest -n auto --dist=loadfile

# Group by marker: Tests with same xdist_group run together (rarely needed)
uv run pytest -n auto --dist=loadgroup
```

#### When to Use Different Modes

**`--dist=load` (default)**:
- ✅ Best for most test suites
- Tests distributed randomly to workers
- Simple and effective

**`--dist=worksteal`**:
- ✅ Use when test durations vary significantly (e.g., some tests take 5s, others take 50ms)
- Workers with fewer tests "steal" from busier workers
- Better CPU utilization than `load`
- **Recommended**: Try this if your test suite has uneven execution times

**`--dist=loadscope`**:
- ✅ Groups tests by module (for functions) or class (for methods)
- Better fixture reuse when session/module-scoped fixtures are expensive
- Use when setup/teardown costs are high

**`--dist=loadfile`**:
- ✅ All tests in a file run on same worker
- Use when tests in a file share expensive setup
- Less efficient than `loadscope` but simpler to reason about

**`--dist=loadgroup`**:
- ⚠️ Requires `@pytest.mark.xdist_group` markers
- Rarely needed - usually indicates isolation problems
- See "The xdist_group Anti-Pattern" above

**Our default** (configured in `pytest.ini`): `--dist=loadgroup` with `-n auto`
- Respects any xdist_group markers (though we've removed most)
- Falls back to load balancing for unmarked tests

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

**When to Mock**:
- System boundaries (subprocess, network, filesystem only when necessary)
- Qt signals (use QSignalSpy instead of mocking)
- External dependencies (databases, APIs)

### 3. Duck Typing and Protocols

**Use hasattr() for flexible interfaces**:
```python
def test_model_has_method():
    """Test object supports expected interface."""
    assert hasattr(model, "get_available_shows")
    result = model.get_available_shows()
    assert isinstance(result, list)
```

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

### 4. Real Filesystem Operations

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

### 5. Configuration Validation

**Validate constraints, not implementation**:
```python
def test_plate_priority_ordering():
    """Validate plate priorities maintain correct ordering."""
    priorities = Config.TURNOVER_PLATE_PRIORITY
    assert priorities["FG"] < priorities["PL"] < priorities["BG"]
```

### 6. Run Tests Frequently

- Run tests before committing: `uv run pytest tests/unit/ -n auto`
- Run specific tests during development
- Use `--lf` flag to run only last failed: `pytest --lf`

## Anti-Pattern Replacements

### ❌ DON'T: Use time.sleep()
```python
# WRONG - blocks parallel execution
time.sleep(0.1)
```

### ✅ DO: Use synchronization helpers
```python
# RIGHT - non-blocking simulation
from tests.helpers.synchronization import simulate_work_without_sleep
simulate_work_without_sleep(100)  # milliseconds
```

### ❌ DON'T: Use QApplication.processEvents()
```python
# WRONG - causes race conditions
app.processEvents()
```

### ✅ DO: Use process_qt_events()
```python
# RIGHT - thread-safe event processing
from tests.helpers.synchronization import process_qt_events
process_qt_events(app, 10)  # milliseconds
```

### ❌ DON'T: Use bare waits
```python
# WRONG - unreliable timing
widget.do_something()
time.sleep(1)
assert widget.is_done
```

### ✅ DO: Use condition-based waiting
```python
# RIGHT - waits only as long as needed
from tests.helpers.synchronization import wait_for_condition
widget.do_something()
wait_for_condition(lambda: widget.is_done, timeout_ms=1000)
```

---

## Advanced: Session-Scoped Fixtures for Parallel Execution

### Problem: Expensive Setup Across Workers

When running tests with `-n auto`, each worker gets its own Python process. Session-scoped fixtures run once per worker, which can be wasteful for expensive operations like:
- Setting up mock VFX environments
- Initializing large test databases
- Generating test data that takes seconds

### Solution: Shared Setup with File Locks

Use file locks to coordinate workers so the setup happens exactly once:

```python
import json
import pytest
from filelock import FileLock

@pytest.fixture(scope="session")
def expensive_vfx_setup(tmp_path_factory, worker_id):
    """Set up mock VFX environment once across all workers.

    The first worker creates the environment, others wait and reuse it.
    """
    if worker_id == "master":
        # Not running with xdist (no parallel workers)
        return create_vfx_environment()

    # Get temp directory shared by all workers
    root_tmp_dir = tmp_path_factory.getbasetemp().parent
    data_file = root_tmp_dir / "vfx_setup.json"

    # Use file lock to coordinate access
    with FileLock(str(data_file) + ".lock"):
        if data_file.is_file():
            # Another worker already did the setup
            data = json.loads(data_file.read_text())
        else:
            # We're first - do the expensive setup
            data = create_vfx_environment()
            data_file.write_text(json.dumps(data))

    return data


def create_vfx_environment():
    """Expensive operation: create mock shows, shots, thumbnails."""
    # ... expensive setup code ...
    return {"shows_root": "/tmp/vfx", "shot_count": 432}
```

### Key Points

1. **`worker_id` fixture**: Returns `"master"` for non-parallel runs, or `"gw0"`, `"gw1"`, etc. for workers
2. **`tmp_path_factory.getbasetemp().parent`**: Gets the shared temp directory visible to all workers
3. **`FileLock`**: Ensures only one worker does the setup, others wait
4. **JSON for data sharing**: Workers communicate via shared files

### When to Use This Pattern

✅ **Use for**:
- Mock environment setup (VFX filesystem, databases)
- Generating large test datasets
- One-time expensive computations
- Any setup taking >1 second that's shared across tests

❌ **Don't use for**:
- Test isolation (use proper cleanup instead)
- Working around state contamination (fix the isolation)
- Avoiding proper test design

### Real-World Usage

This pattern is used in ShotBot for:
- Mock VFX environment setup (`recreate_vfx_structure.py`)
- ProcessPool initialization (see `conftest.py`)
- Shared test data generation

---

## Known Issues

### WSL/pytest-xvfb Compatibility
- pytest-xvfb causes timeouts in WSL
- Solution: Disabled via `-p no:xvfb` in pytest.ini

### Test Execution
- Must use `python run_tests.py` instead of direct pytest
- This ensures proper path setup and plugin configuration

---

## Test Patterns by Category

Refer to actual test files for implementation examples. The principles above are applied throughout the test suite:

### Configuration Validation
**File**: `tests/unit/test_config.py` (27 tests)
- Validates configuration constraints without mocking
- Tests relationships (e.g., plate priority ordering)
- Would catch configuration bugs like PL=10

### Static Method Testing
**File**: `tests/unit/test_plate_discovery.py` (26 tests)
- Uses tmp_path for real filesystem operations
- No mocking of pathlib or file operations
- Tests pure functions with realistic data

### Qt Model/View Testing
**File**: `tests/unit/test_shot_item_model.py` (28 tests)
- Uses qtbot fixture and QSignalSpy
- Real CacheManager instances with tmp_path
- Tests actual Qt behavior, not mocks

### Protocol-Based Interfaces
**Files**: `shot_grid_view.py`, `base_grid_view.py`, `threede_grid_view.py`
- Type-safe duck typing with Protocol classes
- Enables type checking without isinstance()
- See `HasAvailableShows` Protocol for example

### Edge Case Testing
**File**: `tests/unit/test_plate_discovery.py`
- Tests boundary conditions (version gaps, empty directories, permissions)
- Documents why each edge case matters
- Uses realistic scenarios

---

## Test File Organization

### Directory Structure
```
tests/
├── conftest.py              # Shared fixtures (qtbot, tmp_path, etc.)
├── unit/                    # Unit tests
│   ├── test_config.py              # Configuration validation (27 tests)
│   ├── test_plate_discovery.py     # Plate workflow (26 tests)
│   ├── test_shot_item_model.py     # Qt Model/View (28 tests)
│   ├── test_shot_model.py          # Shot data model (33 tests)
│   ├── test_cache_manager.py       # Cache system (42 tests)
│   └── ...
├── integration/             # Integration tests
│   ├── test_main_window_complete.py
│   └── ...
└── utilities/               # Test utilities
    ├── quick_test.py
    └── pytest_audit.py
```

---

## Running Specific Test Categories

### Configuration Tests
```bash
# All config validation (27 tests)
uv run pytest tests/unit/test_config.py -v

# Just plate priority tests
uv run pytest tests/unit/test_config.py::TestPlatePriorityValidation -v
```

### Plate Discovery Tests
```bash
# All plate discovery (26 tests)
uv run pytest tests/unit/test_plate_discovery.py -v

# Just priority tests
uv run pytest tests/unit/test_plate_discovery.py::TestPlatePriorityOrdering -v
```

### Qt Model Tests
```bash
# All Model/View tests
uv run pytest tests/unit/test_*item_model.py -v

# Specific model
uv run pytest tests/unit/test_shot_item_model.py -v
```

### Fast Tests Only
```bash
# Tests under 100ms
uv run pytest tests/ -m fast -v
```

---

## Debugging Test Failures

### Quick Diagnosis: Passes Alone but Fails in Parallel?

This is a **test isolation issue**. Follow this workflow:

#### 1. Reproduce the failure
```bash
# Run flaky test 10 times in parallel
for i in {1..10}; do uv run pytest path/to/test.py -n auto || break; done
```

#### 2. Verify it passes individually
```bash
uv run pytest path/to/test.py::test_name -v
```

#### 3. Identify the pattern
- **Qt objects?** → Resource leak (see Test Isolation section)
- **Config/globals?** → State contamination
- **Caches?** → Module-level pollution

#### 4. Apply the fix
- Add try/finally for Qt resources
- Add monkeypatch for global state
- Clear caches FIRST

#### 5. Remove xdist_group if present
It's probably masking the real issue

#### 6. Verify the fix
```bash
# Run 20+ times to prove stability
for i in {1..20}; do uv run pytest path/to/test.py -n auto -q || break; done
```

### Standard Debugging Commands

```bash
# Show full output
uv run pytest tests/unit/test_config.py::test_name -vv

# Show local variables on failure
uv run pytest tests/unit/test_config.py::test_name -vv -l

# Isolate the failure
uv run pytest tests/unit/test_config.py::TestClass::test_method -v

# See debug prints
uv run pytest tests/unit/test_config.py -v -s

# Drop into debugger
uv run pytest tests/unit/test_config.py --pdb

# Run last failed tests only
uv run pytest --lf
```

### Debugging Parallel Execution

When tests fail only in parallel, these tools help identify the issue:

#### Visualize Fixture Execution Order

Use `--setup-plan` to see fixture execution order without running tests:

```bash
# Show fixture execution plan
uv run pytest tests/unit/test_shot_model.py --setup-plan

# Verbose mode includes all fixtures (even private ones)
uv run pytest tests/unit/test_shot_model.py::test_specific --setup-plan -v
```

**Output shows**:
- Which fixtures are used by each test
- Fixture scope (session, module, function)
- Execution order and dependencies
- Helpful for understanding why fixtures aren't isolated

**Example output**:
```
SETUP    S tmp_path_factory
SETUP    S worker_id
  SETUP    F monkeypatch
  SETUP    F tmp_path (fixtures used by test_cache_manager)
        tests/unit/test_cache_manager.py::test_cache_save
  TEARDOWN F tmp_path
  TEARDOWN F monkeypatch
```

#### Identify Which Worker is Running a Test

Use the `worker_id` fixture to track which worker executes each test:

```python
def test_debug_worker_assignment(worker_id):
    """Debug test to identify worker assignment."""
    print(f"Running on worker: {worker_id}")
    # In non-parallel: worker_id == "master"
    # In parallel: worker_id in ["gw0", "gw1", "gw2", ...]
```

**Run with output**:
```bash
uv run pytest tests/unit/test_config.py::test_debug_worker_assignment -v -s
```

**Useful for**:
- Debugging intermittent failures
- Seeing if certain tests always fail on same worker
- Verifying xdist_group behavior (if using)

#### Check Worker Environment Variables

pytest-xdist sets environment variables automatically:

```python
import os
import pytest

def test_worker_environment():
    """Check xdist environment variables."""
    worker = os.environ.get("PYTEST_XDIST_WORKER", "master")
    worker_count = os.environ.get("PYTEST_XDIST_WORKER_COUNT", "1")
    testrun_uid = os.environ.get("PYTEST_XDIST_TESTRUNUID", "local")

    print(f"Worker: {worker}")
    print(f"Total workers: {worker_count}")
    print(f"Test run UID: {testrun_uid}")
```

#### Advanced: Trace State Contamination

Add temporary logging to trace state changes across tests:

```python
# Add to conftest.py temporarily
@pytest.fixture(autouse=True)
def trace_config_state(request, worker_id):
    """Trace Config.SHOWS_ROOT changes."""
    from config import Config
    before = Config.SHOWS_ROOT
    print(f"[{worker_id}] Before {request.node.name}: SHOWS_ROOT={before}")

    yield

    after = Config.SHOWS_ROOT
    if before != after:
        print(f"[{worker_id}] ⚠️  {request.node.name} changed SHOWS_ROOT: {before} → {after}")
```

**Run with output**:
```bash
uv run pytest tests/unit/ -n 4 -v -s | grep "SHOWS_ROOT"
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
1. **Use real components** - CacheManager, tmp_path, QSignalSpy (minimal mocking)
2. **Test behavior, not implementation** - Focus on observable outcomes
3. **Use try/finally for Qt resources** - Guarantee cleanup always happens
4. **Isolate global state with monkeypatch** - Protect from parallel test contamination
5. **Clear caches FIRST** - Before any operations that might use them
6. **Use duck typing (hasattr)** - For flexible APIs without isinstance()
7. **Write clear, descriptive test names** - Self-documenting test suites
8. **Add docstrings** - Explain what behavior is tested and why
9. **Run tests frequently** - During development to catch issues early
10. **Use Protocols** - For type-safe duck typing

### DON'T: ❌
1. **Mock everything** - Only mock at system boundaries (subprocess, network)
2. **Use xdist_group as a band-aid** - Fix isolation problems instead
3. **Test private methods** - Test public API and observable behavior
4. **Use isinstance() for duck-typed objects** - Breaks test doubles
5. **Use time.sleep() or processEvents()** - Use synchronization helpers
6. **Write tests without docstrings** - Tests should be self-explanatory
7. **Commit without running tests** - Catch issues before pushing
8. **Skip edge case testing** - Edge cases are where bugs hide
9. **Ignore test failures** - Fix them immediately, don't defer