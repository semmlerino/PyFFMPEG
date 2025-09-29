# ShotBot Personal Tool Refactoring Plan

**⚠️ DO NOT DELETE - IMPLEMENTATION REFERENCE DOCUMENT ⚠️**

## Executive Summary
Total Effort: **3-5 days maximum** (not weeks!)
Focus: Fix only what actually interrupts your VFX workflow
Philosophy: Personal tool, not enterprise software

---

## 🔥 CRITICAL FIXES (Actually Need These)

### Day 1: Fix EXR Thumbnail Blocking ⏰ (8 hours)
**Problem**: UI freezes for 30 seconds per EXR file
**Location**: `cache/thumbnail_processor.py:403-539`
**Impact**: Directly interrupts creative flow

**Implementation**:
```python
# Replace in thumbnail_processor.py
import asyncio
from concurrent.futures import ThreadPoolExecutor

class ThumbnailProcessor:
    async def _process_exr_batch_async(self, exr_files: list[Path]) -> dict[Path, Path]:
        """Process multiple EXR files in parallel without blocking UI"""
        # Use asyncio.gather for parallel processing
        tasks = []
        for exr_file in exr_files:
            task = asyncio.create_task(self._convert_single_exr_async(exr_file))
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)
        return {f: r for f, r in zip(exr_files, results) if not isinstance(r, Exception)}

    async def _convert_single_exr_async(self, exr_path: Path) -> Path:
        """Convert single EXR asynchronously"""
        png_path = self._get_cache_path(exr_path)

        # Run ImageMagick in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        executor = ThreadPoolExecutor(max_workers=4)

        cmd = ["convert", str(exr_path), "-resize", "256x256", str(png_path)]
        await loop.run_in_executor(executor, subprocess.run, cmd)

        return png_path
```

**Qt Integration**:
```python
# Wrapper for Qt
from PySide6.QtCore import QThread, Signal

class AsyncEXRProcessor(QThread):
    progress_updated = Signal(int)
    batch_completed = Signal(dict)

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        results = loop.run_until_complete(self._processor.process_batch())
        self.batch_completed.emit(results)
```

---

### Day 2: Fix Cache LRU O(n) Performance 🚀 (4 hours)
**Problem**: UI freezes during cache cleanup
**Location**: `cache/memory_manager.py:262-327`
**Impact**: Causes UI stutters and poor responsiveness

**Implementation**:
```python
# Replace _evict_lru_items() in memory_manager.py
import heapq
from dataclasses import dataclass

@dataclass
class CacheEntry:
    access_time: float
    path: str
    size_bytes: int

    def __lt__(self, other):
        return self.access_time < other.access_time

class MemoryManager:
    def __init__(self):
        self._eviction_heap: list[CacheEntry] = []
        self._file_sizes: dict[str, int] = {}

    def _evict_lru_items(self, target_size: int) -> int:
        """O(log n) eviction without file system calls"""
        evicted_size = 0

        # Build heap once (no file stats needed)
        if not self._eviction_heap:
            self._rebuild_heap()

        while self._eviction_heap and evicted_size < target_size:
            entry = heapq.heappop(self._eviction_heap)

            # Delete file and update tracking
            try:
                Path(entry.path).unlink()
                evicted_size += entry.size_bytes
                del self._file_sizes[entry.path]
            except FileNotFoundError:
                pass  # Already deleted

        return evicted_size

    def _rebuild_heap(self):
        """Build heap from tracked files (called rarely)"""
        self._eviction_heap = [
            CacheEntry(access_time, path, size)
            for path, (size, access_time) in self._tracked_files.items()
        ]
        heapq.heapify(self._eviction_heap)
```

---

### Day 3: Add Filesystem Coordination 📁 (6 hours)
**Problem**: Multiple workers scan same directories
**Files**: `threede_scene_worker.py:578-677`, `previous_shots_worker.py:104-143`
**Impact**: 50% wasted I/O operations

**Implementation**:
```python
# New file: filesystem_coordinator.py
import time
from pathlib import Path
from typing import Optional
from threading import Lock

class FilesystemCoordinator:
    """Singleton coordinator for filesystem operations"""
    _instance: Optional['FilesystemCoordinator'] = None
    _lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        # Cache: path -> (listing, timestamp)
        self._directory_cache: dict[Path, tuple[list[Path], float]] = {}
        self._ttl_seconds = 300  # 5 minutes

    def get_directory_listing(self, path: Path) -> list[Path]:
        """Get cached directory listing or scan if needed"""
        now = time.time()

        # Check cache
        if cached := self._directory_cache.get(path):
            listing, timestamp = cached
            if now - timestamp < self._ttl_seconds:
                return listing

        # Scan and cache
        try:
            listing = list(path.iterdir())
            self._directory_cache[path] = (listing, now)
            return listing
        except (OSError, PermissionError):
            return []

    def invalidate_path(self, path: Path):
        """Invalidate cache for specific path"""
        self._directory_cache.pop(path, None)

    def share_discovered_paths(self, paths: dict[Path, list[Path]]):
        """Share discovered paths from one worker with others"""
        now = time.time()
        for directory, contents in paths.items():
            self._directory_cache[directory] = (contents, now)
```

**Integration in workers**:
```python
# In threede_scene_worker.py
from filesystem_coordinator import FilesystemCoordinator

class ThreeDESceneWorker:
    def __init__(self):
        self.fs_coord = FilesystemCoordinator()

    def _scan_directory(self, path: Path):
        # Use coordinator instead of direct scan
        contents = self.fs_coord.get_directory_listing(path)
        threede_files = [f for f in contents if f.suffix == '.3de']

        # Share discoveries with other workers
        self.fs_coord.share_discovered_paths({path: contents})
```

---

### Day 4-5: MainWindow Cleanup 🧹 (8 hours)
**Problem**: 1,356 lines makes maintenance difficult
**File**: `main_window.py`
**Goal**: Reduce to < 1000 lines by extracting worst offenders

#### Part 1: Extract CleanupManager (lines 1202-1339)
```python
# New file: cleanup_manager.py
from PySide6.QtCore import QObject, Signal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main_window import MainWindow

class CleanupManager(QObject):
    """Manages all cleanup operations for MainWindow"""
    cleanup_started = Signal()
    cleanup_finished = Signal()

    def __init__(self, main_window: 'MainWindow'):
        super().__init__()
        self.main_window = main_window
        self.logger = main_window.logger

    def perform_cleanup(self) -> None:
        """Main cleanup orchestration"""
        self.cleanup_started.emit()

        try:
            self._cleanup_models()
            self._cleanup_workers()
            self._cleanup_cache()
            self._cleanup_ui()
            self._cleanup_managers()
        finally:
            self.cleanup_finished.emit()

    def _cleanup_models(self):
        """Clean up all data models"""
        # Move lines 1217-1245 here
        if hasattr(self.main_window, 'shot_model'):
            self.main_window.shot_model.cleanup()

    def _cleanup_workers(self):
        """Stop all background workers"""
        # Move lines 1246-1270 here
        for worker in [self.main_window.threede_worker,
                      self.main_window.previous_worker]:
            if worker and worker.isRunning():
                worker.stop()
                worker.wait(100)

    def _cleanup_cache(self):
        """Shutdown cache manager"""
        # Move lines 1271-1285 here
        if self.main_window.cache_manager:
            self.main_window.cache_manager.shutdown()

    def _cleanup_ui(self):
        """Clean up UI components"""
        # Move lines 1286-1310 here
        pass

    def _cleanup_managers(self):
        """Clean up singleton managers"""
        # Move lines 1311-1339 here
        from process_pool_factory import ProcessPoolFactory
        ProcessPoolFactory.cleanup()
```

#### Part 2: Extract RefreshOrchestrator (lines 726-843)
```python
# New file: refresh_orchestrator.py
from PySide6.QtCore import QObject, Signal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main_window import MainWindow

class RefreshOrchestrator(QObject):
    """Orchestrates refresh operations across tabs"""
    refresh_started = Signal(int)  # tab_index
    refresh_finished = Signal(int, bool)  # tab_index, success

    def __init__(self, main_window: 'MainWindow'):
        super().__init__()
        self.main_window = main_window

    def refresh_current_tab(self) -> None:
        """Refresh based on current tab"""
        tab_index = self.main_window.tab_widget.currentIndex()
        self.refresh_tab(tab_index)

    def refresh_tab(self, index: int) -> None:
        """Refresh specific tab"""
        self.refresh_started.emit(index)

        if index == 0:  # My Shots
            self._refresh_shots()
        elif index == 1:  # Other 3DE
            self._refresh_threede()
        elif index == 2:  # Previous
            self._refresh_previous()

    def _refresh_shots(self):
        """Refresh My Shots tab"""
        # Move lines 749-785 here
        success, has_changes = self.main_window.shot_model.refresh_shots()
        if success and has_changes:
            self.main_window.shot_grid.refresh_view()
        self.refresh_finished.emit(0, success)

    def _refresh_threede(self):
        """Refresh Other 3DE tab"""
        # Move lines 786-815 here
        self.main_window.threede_model.start_scan()
        self.refresh_finished.emit(1, True)

    def _refresh_previous(self):
        """Refresh Previous Shots tab"""
        # Move lines 816-843 here
        self.main_window.previous_model.refresh()
        self.refresh_finished.emit(2, True)
```

#### Part 3: Update MainWindow
```python
# In main_window.py
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # ... existing init ...

        # Add managers
        self.cleanup_manager = CleanupManager(self)
        self.refresh_orchestrator = RefreshOrchestrator(self)

        # Connect signals
        self.refresh_orchestrator.refresh_started.connect(self._on_refresh_started)
        self.refresh_orchestrator.refresh_finished.connect(self._on_refresh_finished)

    def closeEvent(self, event):
        """Simplified cleanup"""
        self.cleanup_manager.perform_cleanup()
        event.accept()

    def _refresh(self):
        """Simplified refresh"""
        self.refresh_orchestrator.refresh_current_tab()
```

---

## ❌ COMPLETELY IGNORE THESE (Over-Engineering)

### Type Safety Issues
- 31,393 errors from broken PySide6 stubs
- **Time to fix**: Weeks
- **Value**: Zero for personal tool
- **Verdict**: Complete waste of time

### Security Hardening
- Command injection tests
- Input validation improvements
- **Context**: Isolated VFX network, you control inputs
- **Verdict**: Pointless

### Test Coverage
- Replacing assert True statements
- Adding integration tests
- **Reality**: If it works, it works
- **Verdict**: Only test the tricky bits

### Singleton Refactoring
- Dependency injection conversion
- **Reality**: Works fine for single-user app
- **Verdict**: Academic concern

### Mixin Simplification
- Removing LoggingMixin hierarchy
- **Reality**: Not causing bugs
- **Verdict**: If it works, leave it

### Protocol Abstractions
- Adding more Protocol definitions
- **Reality**: Over-abstraction for 1-2 implementations
- **Verdict**: Unnecessary

### Cache Architecture Rebuild
- Consolidating 9 files to 4
- **Reality**: Works reliably as-is
- **Verdict**: Don't fix what isn't broken

### DRY Violations
- Eliminating all duplication
- **Reality**: Some duplication is clearer
- **Verdict**: Only fix if causing bugs

---

## 📊 Success Metrics

✅ **Day 1**: EXR thumbnails no longer block UI (30s → <1s)
✅ **Day 2**: Cache cleanup doesn't freeze interface
✅ **Day 3**: Filesystem scanning 50% faster
✅ **Day 4-5**: MainWindow under 1000 lines
✅ **Total Time**: Less than 5 days actual work

---

## 🎯 Implementation Strategy

1. **Start with performance** (Days 1-3)
   - Immediate quality-of-life improvements
   - Measurable impact on daily workflow
   - Low risk changes

2. **Then code organization** (Days 4-5)
   - Only extract the most painful parts
   - Stop when it feels manageable
   - Don't over-architect

3. **Skip everything else**
   - Academic concerns don't affect personal tools
   - Type perfection is not needed
   - Security on isolated network is irrelevant

---

## 📁 Files to Create

1. `filesystem_coordinator.py` - Shared filesystem cache
2. `cleanup_manager.py` - Extract from MainWindow
3. `refresh_orchestrator.py` - Extract from MainWindow

## 📝 Testing Approach

Only test the critical paths:
- Async EXR processing doesn't lose files
- Cache eviction actually frees memory
- Filesystem coordinator returns correct results
- Cleanup manager doesn't leave resources hanging

Skip:
- 100% coverage
- Security tests
- Type checking
- Performance benchmarks

---

## 🏁 When You're Done

After 3-5 days you'll have:
- No more UI freezes
- Faster filesystem operations
- Manageable MainWindow size
- Same functionality as before
- More time for actual VFX work

**Remember**: Perfect is the enemy of good. This tool helps you create VFX art, not win code quality awards.

---

**⚠️ DO NOT DELETE THIS DOCUMENT - IMPLEMENTATION REFERENCE ⚠️**