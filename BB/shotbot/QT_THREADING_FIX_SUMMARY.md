# Qt Threading Segmentation Fault Fixes

## Problem
Two tests were causing segmentation faults due to Qt threading violations:
1. `test_process_pool_manager_refactored.py::test_concurrent_access_thread_safety`
2. `test_main_window_coordination.py::test_window_initialization`

## Root Cause
Qt has strict threading rules that were being violated:
- **QPixmap = Main Thread ONLY** (causes Fatal Python error: Aborted)
- **QImage = Any Thread** (thread-safe alternative)
- **QObjects must be created in the thread where they will live**

## Fixes Applied

### 1. test_process_pool_manager_refactored.py
**Issue**: Creating ProcessPoolManager (inherits from QObject) in multiple threads.

**Fix**: Create the singleton instance in the main thread before spawning worker threads.
```python
# BEFORE: Created in each thread (VIOLATION)
def access_manager(index):
    manager = ProcessPoolManager()  # Creates QObject in thread!
    
# AFTER: Created in main thread, accessed from threads
main_manager = ProcessPoolManager()  # Create in main thread
def access_manager(index):
    manager = ProcessPoolManager()  # Returns existing singleton
```

### 2. test_main_window_coordination.py
**Issue**: Creating MainWindow (Qt widgets) without ensuring QApplication exists.

**Fix**: Added `qapp` fixture to ensure QApplication exists before creating widgets.
```python
# BEFORE: No QApplication guarantee
@pytest.fixture
def main_window_with_real_components(qtbot, real_cache_manager):
    window = MainWindow(cache_manager=real_cache_manager)
    
# AFTER: QApplication guaranteed to exist
@pytest.fixture
def main_window_with_real_components(qapp, qtbot, real_cache_manager):
    assert qapp is not None  # Ensure QApplication exists
    window = MainWindow(cache_manager=real_cache_manager)
```

## Key Qt Threading Rules (from UNIFIED_TESTING_GUIDE)

1. **Never use QPixmap in worker threads** - Use ThreadSafeTestImage instead
2. **QObjects must be created in their thread of use**
3. **QApplication must exist before creating any widgets**
4. **Use qtbot.addWidget() for proper cleanup**

## Test Results
Both tests now pass without segmentation faults:
- ✅ test_concurrent_access_thread_safety: PASSED (39.16s)
- ✅ test_window_initialization: PASSED (2.49s)
- ✅ All 28 tests in both files: PASSED (50.09s)

## Prevention Guidelines
When writing Qt tests:
1. Always use `qapp` fixture for widget tests
2. Create QObjects in the main thread only
3. Use ThreadSafeTestImage instead of QPixmap for threading tests
4. Register widgets with qtbot.addWidget() for cleanup
5. Follow UNIFIED_TESTING_GUIDE Qt threading patterns