# Investigation: test_refresh_shots_with_test_pool Failure Analysis

## Test Location
- File: `/home/gabrielh/projects/shotbot/tests/unit/test_main_window_fixed.py`
- Class: `TestMainWindowNoHang`
- Method: `test_refresh_shots_with_test_pool` (lines 276-297)

## Current Status
**Test passes when run alone or with its test file, but may fail in full suite.**

## Key Findings

### 1. Test Structure
The test is marked with:
```python
pytestmark = [
    pytest.mark.unit,
    pytest.mark.qt,
    pytest.mark.slow,  # Requires complete isolation
]
```

### 2. Critical Singleton Reset Fixture
The test file defines `reset_all_mainwindow_singletons` (lines 55-179) that:
- Runs as autouse fixture on EVERY test
- Resets FIVE critical singletons BOTH before AND after each test:
  1. **NotificationManager** - UI notifications (must be reset FIRST - closes Qt widgets)
  2. **ProgressManager** - progress dialogs  
  3. **ProcessPoolManager** - process pool for background tasks
  4. **QRunnableTracker** - thread pool task tracking
  5. **FilesystemCoordinator** - filesystem operations

### 3. Test Fixture Dependencies
The `safe_main_window` fixture (lines 184-233) depends on:
- `qtbot` - Qt test helper
- `tmp_path` - pytest temporary directory
- `monkeypatch` - pytest monkeypatch
- **`mock_process_pool_manager`** - defined in conftest.py (line 908)

### 4. mock_process_pool_manager Fixture (conftest.py:908)
```python
@pytest.fixture
def mock_process_pool_manager(monkeypatch, test_process_pool):
    """Patch ProcessPoolManager to use test double."""
    monkeypatch.setattr(
        "process_pool_manager.ProcessPoolManager.get_instance",
        lambda: test_process_pool,
    )
```

**Key Issue**: This patches `ProcessPoolManager.get_instance()` to return a test double.

### 5. Global State Management in Test
Test's fixture initialization (safe_main_window, lines 204-216):
1. Sets `Config.SHOWS_ROOT = "/shows"` via monkeypatch
2. Clears shot model cache: `safe_main_window.cache_manager.clear_cache()`
3. Clears shots: `safe_main_window.shot_model.shots = []`
4. Replaces process pool: `main_window.shot_model._process_pool = test_pool`

Test itself (lines 276-297):
1. Gets Config.SHOWS_ROOT (which was patched to "/shows")
2. Sets test pool outputs with absolute path
3. Clears shots again and cache
4. Calls `_refresh_shots()`
5. Asserts `len(shot_model.shots) == 1`

### 6. Root Cause Candidates

#### A. Config.SHOWS_ROOT Singleton Pollution
- `Config` is likely a singleton with module-level state
- Test patches `Config.SHOWS_ROOT = "/shows"` via monkeypatch
- If monkeypatch doesn't fully restore OR if another test pollutes Config state
- The test may fail because:
  - Previous test modified Config.SHOWS_ROOT to different value
  - TargetedShotsFinder cached regex patterns based on old SHOWS_ROOT (line 207 recreates finder)
  - Garbage collection doesn't run between tests

#### B. ProcessPoolManager Singleton Corruption
- Line 185: `safe_main_window` fixture depends on `mock_process_pool_manager`
- But `reset_all_mainwindow_singletons` fixture also resets ProcessPoolManager
- **Order dependency**: If `reset_all_mainwindow_singletons` runs AFTER `safe_main_window`, it may:
  - Reset ProcessPoolManager AFTER the fixture created MainWindow
  - Leave ProcessPoolManager in inconsistent state
  - Next test doesn't get clean ProcessPoolManager

#### C. Test Isolation Issues with MainWindow.__init__()
- MainWindow initializes async operations (line 211: `wait_for_async_load`)
- If async load completes AFTER reset_all_mainwindow_singletons cleanup
- State leaks to next test

#### D. Cache Pollution from Previous Tests
- `cache_manager.clear_cache()` called in test (line 289)
- But global shared cache at `~/.shotbot/cache_test/` may not be cleared
- conftest.py cleanup_state fixture (lines 320-480) DOES clear this
- But fixture order matters for parallel execution

### 7. Known Test Isolation Issues (from CLAUDE.md)
- Qt state cleanup between tests is CRITICAL
- Missing parent parameter in QWidget causes crashes
- Cache cleanup must happen at module level
- Singleton resets must happen in specific order

### 8. Pytest Fixture Execution Order
For `test_refresh_shots_with_test_pool`:
1. `qapp` (session scope) - Qt application
2. `qt_cleanup` (autouse) - Qt event cleanup
3. `cleanup_state` (autouse) - cache and singleton cleanup
4. `cleanup_launcher_manager_state` (autouse) - launcher manager cleanup  
5. `suppress_qmessagebox` (autouse) - dialog suppression
6. `stable_random_seed` (autouse) - random seed
7. `prevent_qapp_exit` (autouse) - prevent QApp.exit()
8. `reset_all_mainwindow_singletons` (autouse) - MAINWINDOW SINGLETONS RESET
9. `cleanup_workers` (autouse) - worker cleanup
10. **`mock_process_pool_manager`** (explicit) - ProcessPool mocking
11. `safe_main_window` - creates MainWindow

### 9. The Smoking Gun: Fixture Order Dependency
**CRITICAL FINDING:**
- `reset_all_mainwindow_singletons` runs BEFORE `mock_process_pool_manager`
- Both try to manage ProcessPoolManager state
- conftest.py `cleanup_state` also resets ProcessPoolManager (line 389)

**Three places resetting ProcessPoolManager:**
1. conftest.py cleanup_state (before test): line 389
2. test_main_window_fixed.py reset_all_mainwindow_singletons (before test): lines 103-111
3. conftest.py cleanup_state (after test): line 452

**When parallel execution runs (pytest -n 2):**
- Different test in worker 1 may have left ProcessPoolManager partially initialized
- Workers share module-level state through import
- monkeypatch in one test may not fully restore in another

## Hypotheses

### H1: ProcessPoolManager Double Reset (Most Likely)
When test runs after certain other tests:
1. Previous test's ProcessPoolManager is partially reset
2. conftest cleanup_state resets it (line 389)
3. reset_all_mainwindow_singletons resets it again (line 103-111)
4. mock_process_pool_manager patches get_instance (line 924-927)
5. But safe_main_window fixture tries to replace `main_window.shot_model._process_pool = test_pool` (line 216)
6. If MainWindow.shot_model already cached a ProcessPoolManager reference, replacement fails

### H2: Config.SHOWS_ROOT Pollution
When running in full suite:
1. Previous test in different file modified Config.SHOWS_ROOT
2. Monkeypatch in safe_main_window tries to set it to "/shows" (line 194)
3. But TargetedShotsFinder caches regex patterns based on SHOWS_ROOT
4. Line 207 recreates finder: `main_window.shot_model._shot_finder = TargetedShotsFinder()`
5. But garbage collector hasn't run, so old finder with old SHOWS_ROOT pattern still referenced
6. Assertion fails because shots don't match expected pattern

### H3: Async Load Timing in Full Suite
When test runs in parallel or after heavy load:
1. Line 211: `main_window.shot_model.wait_for_async_load(timeout_ms=2000)`
2. If timeout_ms insufficient, async load continues after fixture
3. Replaces test pool setup with real ProcessPoolManager
4. _refresh_shots() uses wrong pool

## Test Expectations
- Line 295: `assert len(safe_main_window.shot_model.shots) == 1`
- Line 296: `assert safe_main_window.shot_model.shots[0].shot == "0010"`

Test expects exactly 1 shot loaded from test pool output set at line 284.

## Conftest Global Cleanup (cleanup_state fixture)
Lines 320-480 show:
- Clear utils caches (line 353)
- Clear shared cache dir (line 356-364)
- Disable caching (line 369)
- Reset NotificationManager (line 374)
- Reset ProgressManager (line 381)
- **Reset ProcessPoolManager (line 389)**
- Reset FilesystemCoordinator (line 396)

This happens for EVERY test as autouse fixture.
