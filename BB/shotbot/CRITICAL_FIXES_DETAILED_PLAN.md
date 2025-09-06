# ShotBot Critical Fixes - Detailed Implementation Plan

## Overview
This document provides a comprehensive plan to address the critical issues discovered by the multi-agent code review. Each issue includes root cause analysis, specific code changes, testing approach, and risk assessment.

---

## 🚨 CRITICAL ISSUE 1: Remaining Hardcoded `/shows` Paths

### Root Cause
During the initial SHOWS_ROOT configuration update, we missed several files that construct regex patterns with hardcoded paths. These patterns are compiled at module load time, making them invisible to simple text searches.

### Affected Files and Line Numbers

#### 1. `shot_finder_base.py` (Lines 40-42)
**Current Code:**
```python
# Line 40-42
self._shot_pattern = re.compile(r"/shows/([^/]+)/shots/([^/]+)/\2_([^/]+)/")
self._shot_pattern_fallback = re.compile(r"/shows/([^/]+)/shots/([^/]+)/([^/]+)/")
```

**Fixed Code:**
```python
# Add import at top
from config import Config
import re

# Line 40-42 (in __init__ method)
shows_root_escaped = re.escape(Config.SHOWS_ROOT)
self._shot_pattern = re.compile(rf"{shows_root_escaped}/([^/]+)/shots/([^/]+)/\2_([^/]+)/")
self._shot_pattern_fallback = re.compile(rf"{shows_root_escaped}/([^/]+)/shots/([^/]+)/([^/]+)/")
```

#### 2. `base_shot_model.py` (Line 70)
**Current Code:**
```python
# Line 70
self._ws_pattern = re.compile(
    r"workspace\s+(/shows/(\w+)/shots/(\w+)/(\w+_\w+))",
    re.MULTILINE
)
```

**Fixed Code:**
```python
# Add import at top if not present
from config import Config
import re

# Line 70-73
shows_root_escaped = re.escape(Config.SHOWS_ROOT)
self._ws_pattern = re.compile(
    rf"workspace\s+({shows_root_escaped}/(\w+)/shots/(\w+)/(\w+_\w+))",
    re.MULTILINE
)
```

### Testing Approach
```python
# test_dynamic_regex_patterns.py
import os
import re
from unittest import mock

def test_regex_patterns_use_config():
    """Verify regex patterns adapt to SHOWS_ROOT configuration."""
    
    # Test with default /shows
    with mock.patch.dict(os.environ, {"SHOWS_ROOT": "/shows"}):
        from shot_finder_base import ShotFinderBase
        finder = ShotFinderBase()
        pattern = finder._shot_pattern.pattern
        assert "/shows" in pattern
        assert r"\/shows\/" not in pattern  # Should be escaped
    
    # Test with mock environment
    with mock.patch.dict(os.environ, {"SHOWS_ROOT": "/tmp/mock_vfx"}):
        from shot_finder_base import ShotFinderBase
        finder = ShotFinderBase()
        pattern = finder._shot_pattern.pattern
        assert r"\/tmp\/mock_vfx\/" in pattern  # Properly escaped
        
        # Test pattern matching
        test_path = "/tmp/mock_vfx/show1/shots/seq1/seq1_010/user/test"
        match = finder._shot_pattern.search(test_path)
        assert match is not None
        assert match.groups() == ("show1", "seq1", "010")
```

### Risk Assessment
- **Impact if not fixed**: Mock environment completely broken, tests fail
- **Risk of fix**: Low - localized change to regex compilation
- **Testing coverage**: Unit tests will verify patterns work with different SHOWS_ROOT values

---

## 🚨 CRITICAL ISSUE 2: Missing PreviousShotsModel Cleanup

### Root Cause
The main window's `closeEvent()` method cleans up many components but omits the `previous_shots_model`, leaving a QThread worker running after application exit. This can cause segmentation faults and prevent clean shutdown.

### Affected File and Line Numbers

#### `main_window.py` (Lines 1780-1890)
**Current closeEvent() cleanup sequence:**
```python
def closeEvent(self, event: QCloseEvent) -> None:
    """Handle application close event."""
    # Line 1780-1867: Various cleanups
    # MISSING: previous_shots_model cleanup!
```

**Fixed Code - Insert after line 1867:**
```python
def closeEvent(self, event: QCloseEvent) -> None:
    """Handle application close event with complete cleanup.
    
    Cleanup order is critical to prevent race conditions:
    1. Set closing flag to prevent new operations
    2. Stop all worker threads (with timeout)
    3. Clean up models (which stop their internal workers)
    4. Clean up views (which may have timers)
    5. Disconnect remaining signals
    6. Delete objects with deleteLater()
    7. Shutdown singleton managers
    """
    try:
        logger.info("MainWindow closing, performing cleanup...")
        self._is_closing = True
        
        # ... existing cleanup code ...
        
        # ADD THIS SECTION after line 1867:
        # Clean up previous shots model (stops auto-refresh timer and worker)
        if hasattr(self, 'previous_shots_model') and self.previous_shots_model:
            logger.debug("Cleaning up PreviousShotsModel")
            try:
                self.previous_shots_model.cleanup()
            except Exception as e:
                logger.error(f"Error cleaning up PreviousShotsModel: {e}")
        
        # Also clean up the item model if it exists
        if hasattr(self, 'previous_shots_item_model') and self.previous_shots_item_model:
            logger.debug("Cleaning up PreviousShotsItemModel")
            try:
                if hasattr(self.previous_shots_item_model, 'cleanup'):
                    self.previous_shots_item_model.cleanup()
            except Exception as e:
                logger.error(f"Error cleaning up PreviousShotsItemModel: {e}")
        
        # ... rest of existing cleanup code ...
```

### Testing Approach
```python
# test_mainwindow_cleanup.py
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from main_window import MainWindow

def test_previous_shots_cleanup():
    """Verify PreviousShotsModel is properly cleaned up on close."""
    app = QApplication.instance() or QApplication(sys.argv)
    
    # Create main window
    window = MainWindow()
    window.show()
    
    # Verify previous_shots_model exists
    assert hasattr(window, 'previous_shots_model')
    assert window.previous_shots_model is not None
    
    # Get reference to check cleanup
    prev_model = window.previous_shots_model
    
    # Check worker is running
    if hasattr(prev_model, '_worker'):
        initial_worker = prev_model._worker
    
    # Close window
    window.close()
    
    # Verify cleanup was called
    assert prev_model._refresh_timer.isActive() is False
    if initial_worker:
        assert prev_model._worker is None  # Worker should be cleared
    
    # No threads should be left running
    from PySide6.QtCore import QThread
    active_threads = []
    for thread in QThread.currentThread().children():
        if isinstance(thread, QThread) and thread.isRunning():
            active_threads.append(thread)
    assert len(active_threads) == 0, f"Threads still running: {active_threads}"
```

### Risk Assessment
- **Impact if not fixed**: Segmentation faults on exit, zombie threads
- **Risk of fix**: Low - adding cleanup call to existing sequence
- **Testing coverage**: Can verify no threads remain after closeEvent()

---

## 🚨 CRITICAL ISSUE 3: Thumbnail Cache Race Condition

### Root Cause
Multiple threads can trigger cache cleanup simultaneously when the cache size limit is reached, leading to potential corruption or crashes. The current implementation checks size and removes items without atomic operations.

### Affected File and Line Numbers

#### `shot_item_model.py` (Lines 427-434)
**Current Code:**
```python
# Line 427-434
if len(self._thumbnail_cache) >= MAX_CACHE_SIZE:
    oldest_key = next(iter(self._thumbnail_cache))
    del self._thumbnail_cache[oldest_key]
```

**Fixed Code:**
```python
# Line 427-440 (expanded with proper locking)
def _enforce_cache_size_limit(self) -> None:
    """Thread-safe cache size enforcement with atomic operations."""
    with QMutexLocker(self._cache_mutex):
        # Double-check size inside lock
        while len(self._thumbnail_cache) >= MAX_CACHE_SIZE:
            try:
                # Get oldest key safely
                if self._thumbnail_cache:
                    oldest_key = next(iter(self._thumbnail_cache))
                    # Remove with verification
                    if oldest_key in self._thumbnail_cache:
                        old_image = self._thumbnail_cache.pop(oldest_key, None)
                        # Ensure proper cleanup of QImage
                        if old_image and not old_image.isNull():
                            del old_image
                else:
                    break  # Cache is empty
            except (StopIteration, RuntimeError) as e:
                # Handle concurrent modification
                logger.debug(f"Cache cleanup race condition handled: {e}")
                break
```

**Additional Fix - Atomic Cache Operations:**
```python
# Line 450-470 (in load_thumbnail method)
def load_thumbnail(self, shot_full_name: str) -> QImage | None:
    """Thread-safe thumbnail loading with atomic cache operations."""
    # Check cache first (with lock)
    with QMutexLocker(self._cache_mutex):
        if shot_full_name in self._thumbnail_cache:
            return self._thumbnail_cache[shot_full_name]
    
    # Load thumbnail (outside lock to avoid blocking)
    thumbnail = self._load_thumbnail_from_disk(shot_full_name)
    
    if thumbnail:
        # Add to cache with atomic operation
        with QMutexLocker(self._cache_mutex):
            # Check if another thread added it while we were loading
            if shot_full_name not in self._thumbnail_cache:
                # Enforce size limit before adding
                self._enforce_cache_size_limit()
                self._thumbnail_cache[shot_full_name] = thumbnail
            else:
                # Another thread added it, use theirs
                del thumbnail
                thumbnail = self._thumbnail_cache[shot_full_name]
    
    return thumbnail
```

### Testing Approach
```python
# test_concurrent_cache_access.py
import threading
import time
from shot_item_model import ShotItemModel
from PySide6.QtGui import QImage

def test_concurrent_cache_operations():
    """Test cache safety under concurrent access."""
    model = ShotItemModel()
    
    # Pre-fill cache near limit
    for i in range(98):  # MAX_CACHE_SIZE is 100
        model._thumbnail_cache[f"shot_{i}"] = QImage(100, 100, QImage.Format.RGB888)
    
    # Concurrent threads trying to add to cache
    errors = []
    completed = []
    
    def add_to_cache(thread_id):
        try:
            for j in range(10):
                shot_name = f"thread_{thread_id}_shot_{j}"
                # This should trigger cache cleanup
                model.load_thumbnail(shot_name)
                time.sleep(0.001)  # Small delay to increase contention
            completed.append(thread_id)
        except Exception as e:
            errors.append((thread_id, str(e)))
    
    # Launch concurrent threads
    threads = []
    for i in range(10):
        t = threading.Thread(target=add_to_cache, args=(i,))
        threads.append(t)
        t.start()
    
    # Wait for completion
    for t in threads:
        t.join(timeout=5.0)
    
    # Verify no errors
    assert len(errors) == 0, f"Cache errors occurred: {errors}"
    assert len(completed) == 10, "Not all threads completed"
    
    # Verify cache integrity
    assert len(model._thumbnail_cache) <= 100, "Cache size exceeded limit"
    
    # Verify no null entries
    for key, value in model._thumbnail_cache.items():
        assert value is not None, f"Null value in cache for {key}"
        assert not value.isNull(), f"Invalid QImage in cache for {key}"
```

### Risk Assessment
- **Impact if not fixed**: Memory corruption, crashes under load
- **Risk of fix**: Medium - changes to core caching logic
- **Testing coverage**: Concurrent access tests, stress testing

---

## 📊 PERFORMANCE ISSUE: Subprocess-Heavy Operations

### Root Cause
Using subprocess `find` commands for filesystem traversal is extremely inefficient, causing 60-120 second scan times. Native Python pathlib operations are 3x faster.

### Quick Win Solution
**Replace subprocess calls with pathlib in targeted locations:**

#### `previous_shots_finder.py` (Lines 83-106)
**Current Code:**
```python
cmd = ["find", str(shows_root), "-type", "d", "-path", f"*{self.user_path_pattern}", "-maxdepth", "8"]
result = subprocess.run(cmd, stdout=subprocess.PIPE, ...)
```

**Optimized Code:**
```python
def find_user_shots_native(self, shows_root: Path | None = None) -> list[Shot]:
    """Native Python implementation - 3x faster than subprocess."""
    from pathlib import Path
    
    if shows_root is None:
        shows_root = Path(Config.SHOWS_ROOT)
    
    shots = []
    pattern = f"*{self.user_path_pattern}"
    
    # Use rglob for recursive search (much faster than subprocess)
    for user_dir in shows_root.rglob(pattern):
        if user_dir.is_dir():
            shot = self._parse_shot_from_path(str(user_dir))
            if shot and shot not in shots:
                shots.append(shot)
    
    return shots
```

### Long-term Solution
**Always use TargetedShotsFinder instead of ParallelShotsFinder:**
- 95% performance improvement (5-10s vs 60-120s)
- Already implemented and tested
- Just needs to be the default everywhere

---

## 🛠️ Implementation Order & Time Estimates

### Phase 1: Critical Path Fixes (2-3 hours)
1. **Fix hardcoded paths** (30 min)
   - Update shot_finder_base.py
   - Update base_shot_model.py
   - Run tests to verify

2. **Add PreviousShotsModel cleanup** (20 min)
   - Update main_window.py closeEvent()
   - Test application shutdown

3. **Fix cache race condition** (1 hour)
   - Implement atomic cache operations
   - Add _enforce_cache_size_limit method
   - Test concurrent access

### Phase 2: Automated Cleanup (30 min)
4. **Run ruff auto-fixes** (10 min)
   ```bash
   source venv/bin/activate
   ruff check . --fix
   ```

5. **Verify type checking** (20 min)
   ```bash
   basedpyright
   ```

### Phase 3: Testing & Validation (1 hour)
6. **Create comprehensive test suite** (45 min)
   - test_dynamic_regex_patterns.py
   - test_mainwindow_cleanup.py
   - test_concurrent_cache_access.py

7. **Run full test suite** (15 min)
   ```bash
   python -m pytest tests/ -v
   ```

### Phase 4: Documentation (15 min)
8. **Update documentation**
   - Update SHOTBOT_ACTION_PLAN.md
   - Update IMPLEMENTATION_PROGRESS.md
   - Create release notes

---

## 🎯 Success Criteria

### Critical Issues Resolution
- [ ] Mock environment works with any SHOWS_ROOT value
- [ ] Application closes cleanly without zombie threads
- [ ] Cache operations are thread-safe under load
- [ ] All tests pass

### Performance Improvements
- [ ] Shot finding < 10 seconds for all operations
- [ ] No subprocess calls for basic file operations
- [ ] Memory usage stable under 200MB

### Code Quality
- [ ] Zero basedpyright errors in modified files
- [ ] Ruff issues reduced by 100+ through auto-fix
- [ ] All critical functions have type annotations

---

## 🚀 Quick Start Commands

```bash
# 1. Activate virtual environment
source venv/bin/activate

# 2. Create backup branch
git checkout -b critical-fixes-phase2
git add . && git commit -m "Backup before critical fixes"

# 3. Run automated fixes first
ruff check . --fix

# 4. Implement manual fixes (follow sections above)

# 5. Run tests
python -m pytest tests/ -v -m critical

# 6. Verify type checking
basedpyright

# 7. Run mock environment test
python shotbot.py --mock
```

---

## 📝 Notes

- All line numbers are from the current codebase state
- Test files should be created in the `tests/` directory
- Use `SHOTBOT_DEBUG=1` for verbose logging during testing
- The TargetedShotsFinder is already production-ready and should be the default

This plan addresses all critical issues with specific, actionable steps and comprehensive testing approaches.