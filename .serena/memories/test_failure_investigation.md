# Test Failure Investigation: test_refresh_shots_success

## ROOT CAUSE IDENTIFIED

There are TWO autouse singleton reset fixtures running in conflict:

### Fixture Conflict
1. **conftest.py** (line 320-399): `cleanup_state` autouse fixture
   - Resets NotificationManager, ProgressManager, ProcessPoolManager
   - Clears shared cache directory `~/.shotbot/cache_test`
   - Disables caching with `disable_caching()`

2. **test_shot_model.py** (line 32-47): `reset_singletons` autouse fixture
   - Also resets NotificationManager, ProgressManager, ProcessPoolManager
   - Uses monkeypatch to set `_instance = None` and `_initialized = False`

### The Problem
When both fixtures run (which they do in the full test suite), they may:
- Clear caches at different times
- Have ordering issues with monkeypatch cleanup
- Cause race conditions in singleton initialization

### Why It Passes in Isolation
- In isolation: Only test_shot_model.py's reset_singletons runs
- In small batches: Both fixtures run but don't have enough prior tests to create pollution
- In full suite: Multiple tests run before test_refresh_shots_success, causing cache/state pollution

### Solution
The `reset_singletons` fixture in test_shot_model.py is REDUNDANT because:
1. conftest.py's cleanup_state already handles singleton reset
2. conftest.py's cleanup_state is more comprehensive (also clears caches, disables caching)
3. Having two fixtures do the same thing causes conflicts

### Recommended Fix
Remove the autouse reset_singletons fixture from test_shot_model.py (lines 32-47).

The conftest.py cleanup_state fixture is sufficient for all singleton cleanup needs and is properly ordered with other autouse fixtures.

## Test Details
- **File**: tests/unit/test_shot_model.py::TestShotModel::test_refresh_shots_success
- **Line**: 306-323
- **Failure**: real_shot_model.shots is empty (0 items) when should have 2
- **Test Sets up**: test_process_pool with outputs, assigns to real_shot_model._process_pool
- **Calls**: real_shot_model.refresh_shots()
- **Expects**: 2 shots to be parsed and stored in real_shot_model.shots
