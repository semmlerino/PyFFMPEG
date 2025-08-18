# Cache Isolation Fix for Test Suite

## Problem Description

The test suite had critical cache isolation issues where tests would pass individually but fail when run in a suite. Specifically:

1. **Test Contamination**: Tests like `test_validate_path_exists_cache_expiry` would pass individually but fail in the suite due to shared cache state
2. **Module-Level Cache**: The `_path_cache` dictionary in `utils.py` was a module-level global that persisted between tests
3. **Direct Cache Manipulation**: Tests were directly accessing and manipulating the global cache variables

## Root Cause Analysis

- Tests imported `_path_cache` and `_PATH_CACHE_TTL` directly from `utils.py`
- The `isolated_test_environment` fixture was clearing caches but they would immediately get repopulated
- Multiple test modules shared the same global cache state
- No mechanism to temporarily disable caching for testing

## Solution Implemented

### 1. Enhanced Cache Management (`utils.py`)

Added new functions for test isolation:
```python
_cache_disabled = False  # Test isolation flag

def disable_caching():
    """Disable caching completely - useful for testing."""
    global _cache_disabled
    _cache_disabled = True
    clear_all_caches()

def enable_caching():
    """Re-enable caching after testing."""
    global _cache_disabled
    _cache_disabled = False

class CacheIsolation:
    """Context manager for cache isolation in tests."""
    # Provides complete cache isolation with state restoration
```

### 2. Modified Cache Logic

Updated `PathUtils.validate_path_exists()` to respect the disabled flag:
```python
# Skip caching if disabled (for testing)
if _cache_disabled:
    if not exists:
        logger.debug(f"{description} does not exist (no cache): {path_obj}")
    return exists
```

### 3. Enhanced Test Fixture (`conftest.py`)

Improved the `isolated_test_environment` fixture to:
- Disable caching before each test
- Clear all caches before each test
- Re-enable caching after each test
- Provide complete test isolation

### 4. Fixed Problematic Tests

Modified cache-testing methods in `test_utils.py` to:
- Use `enable_caching()` temporarily when testing cache behavior
- Properly restore cache state with try/finally blocks
- Use direct cache manipulation only when testing cache internals

## Key Changes Made

### `utils.py`
- Added `_cache_disabled` flag and control functions
- Added `CacheIsolation` context manager
- Modified `validate_path_exists()` to respect disabled flag

### `conftest.py`
- Enhanced `isolated_test_environment` fixture with cache disabling
- Added `cache_isolation` fixture for explicit cache control

### `test_utils.py`
- Fixed 6 cache-related tests to use proper isolation
- Removed problematic `time.time()` mocking that interfered with decorators
- Added proper cache state management with try/finally blocks

## Test Results

**Before Fix:**
- Cache tests passed individually: ✅
- Cache tests failed in suite: ❌
- 32+ test failures due to cache contamination

**After Fix:**
- Cache tests pass individually: ✅
- Cache tests pass in suite: ✅
- 0 cache-related test failures
- All cache-related modules (utils, cache_manager, shot_model) pass: ✅ 133/133

## Benefits

1. **Complete Test Isolation**: Tests can no longer contaminate each other through shared cache state
2. **Deterministic Results**: Tests produce consistent results whether run individually or in suite
3. **Performance**: Caching disabled during tests prevents unnecessary filesystem operations
4. **Maintainability**: Clear separation between production caching and test behavior
5. **Debugging**: Better error messages and logging for cache-disabled mode

## Usage for Future Tests

For tests that need to verify caching behavior:
```python
def test_cache_behavior(self):
    from utils import enable_caching, disable_caching
    
    enable_caching()
    try:
        # Test caching functionality
        pass
    finally:
        disable_caching()
```

For tests that need explicit cache control:
```python
def test_with_cache_isolation(self, cache_isolation):
    with cache_isolation():
        # Test with completely isolated cache
        pass
```

## Impact

This fix addresses the fundamental test isolation issue that was causing intermittent failures and makes the test suite robust and reliable. All remaining test failures are now unrelated to caching and can be addressed individually.