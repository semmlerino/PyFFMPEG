# ShotBot Comprehensive Action Plan

## Executive Summary
Based on multi-agent code review analysis, this action plan addresses critical issues, performance bottlenecks, and quality improvements for the ShotBot VFX application.

**Overall Goal**: Transform ShotBot from B+ to A+ production quality with 80-95% performance improvement and comprehensive test coverage.

## Phase 1: Critical Fixes (Day 1)
**Timeline**: Immediate (4-6 hours)
**Risk**: Application instability if not addressed

### 1.1 Restore Missing Core Component
**Priority**: 🔥 CRITICAL
**Impact**: Unblocks 30% of test suite
```bash
# Execute immediately
cp shot_item_model.py.backup shot_item_model.py

# Verify restoration
python3 -c "from shot_item_model import ShotItemModel, ShotRole"

# Run affected tests
python3 -m pytest tests/unit/test_shot_item_model_comprehensive.py -v
python3 -m pytest tests/integration/test_async_workflow_integration.py -v
```
**Expected Outcome**: 1,114 tests accessible, 99%+ pass rate restored

### 1.2 Apply Threading Fixes
**Priority**: 🔥 CRITICAL  
**Files**: `threede_scene_worker.py`
**Already Implemented**: Race condition fix with QMutex
```bash
# Verify threading fixes
python3 -m pytest tests/thread_tests/ -v

# Run threading audit validation
python3 apply_threading_fixes.py --verify
```
**Expected Outcome**: Eliminate potential crashes from race conditions

### 1.3 Fix ProcessPoolManager Singleton
**Priority**: 🔥 CRITICAL
**File**: `process_pool_manager.py:205-242`
```python
# Apply double-checked locking pattern
def __new__(cls, *args, **kwargs):
    if cls._instance is None:
        with cls._lock:
            if cls._instance is None:  # Double-check
                instance = super().__new__(cls)
                instance._initialized = False
                cls._instance = instance
    return cls._instance
```
**Verification**: 
```bash
python3 -m pytest tests/unit/test_process_pool_manager.py -k "singleton"
```

## Phase 2: Performance Optimization (Week 1)
**Timeline**: 3-5 days
**Goal**: Reduce startup from 2.35s to <0.5s

### 2.1 Implement Async Shot Loading
**Priority**: 🟠 HIGH
**Impact**: 80-95% startup improvement
**File**: `shot_model.py`

```python
# Create new async loading implementation
class AsyncShotModel(BaseShotModel):
    async def load_shots_async(self) -> RefreshResult:
        # Show cached data immediately
        if self.cache_manager.has_cached_shots():
            cached_shots = self.cache_manager.get_cached_shots()
            self.shots = [Shot.from_dict(s) for s in cached_shots]
            self.shots_changed.emit(self.shots)
            
        # Load fresh data in background
        fresh_result = await asyncio.to_thread(self._fetch_fresh_shots)
        if fresh_result.has_changes:
            self.shots_changed.emit(fresh_result.shots)
        return fresh_result
```

**Integration in MainWindow**:
```python
# main_window.py
def __init__(self):
    # Start with cached data
    QTimer.singleShot(0, self._load_cached_shots)
    # Refresh in background
    QTimer.singleShot(100, self._refresh_shots_async)
```

### 2.2 Optimize Regex Patterns
**Priority**: 🟠 HIGH  
**Impact**: 72.7% processing improvement
**Files**: `shot_finder_base.py`, `previous_shots_finder.py`

```python
# Optimized pattern with backreference
class OptimizedShotParser:
    def __init__(self):
        shows_root = re.escape(Config.SHOWS_ROOT)
        # Single-pass extraction with backreference
        self._optimized = re.compile(
            rf"{shows_root}/([^/]+)/shots/([^/]+)/\2_([^/]+)/"
        )
        self._fallback = re.compile(
            rf"{shows_root}/([^/]+)/shots/([^/]+)/([^/]+)/"
        )
```

**Benchmark Verification**:
```bash
python3 -m timeit -s "from shot_finder_base import ShotFinderBase" \
    "finder = ShotFinderBase(); finder._parse_shot_from_path('/shows/demo/shots/seq01/seq01_0010/')"
```

### 2.3 Fix Qt Thread Safety
**Priority**: 🟠 HIGH
**Issue**: QPixmap operations in background threads
**File**: `shot_item_model.py`

```python
class ThreadSafeThumbnailCache:
    def __init__(self):
        self._image_cache = {}  # QImage (thread-safe)
        self._pixmap_cache = {}  # QPixmap (main thread only)
        self._cache_lock = QMutex()
    
    def get_pixmap(self, key: str) -> QPixmap | None:
        # Assert main thread
        assert QThread.currentThread() == QApplication.instance().thread()
        
        with QMutexLocker(self._cache_lock):
            if key in self._pixmap_cache:
                return self._pixmap_cache[key]
            
            if key in self._image_cache:
                pixmap = QPixmap.fromImage(self._image_cache[key])
                self._pixmap_cache[key] = pixmap
                return pixmap
        return None
```

## Phase 3: Architecture Refactoring (Week 2)
**Timeline**: 5-7 days
**Goal**: Improve maintainability and reduce complexity

### 3.1 Refactor MainWindow
**Priority**: 🟡 MEDIUM
**Current**: 2,058 lines → Target: <500 lines per module
**Files**: Create new modules from `main_window.py`

```python
# main_window_components.py
class MainWindowUI:
    """UI setup and layout management"""
    def setup_ui(self, window: QMainWindow):
        # Extract UI setup code
        pass

# threading_manager.py  
class ThreadingManager:
    """Centralized thread coordination"""
    def __init__(self):
        self._workers: dict[str, QThread] = {}
        self._mutex = QMutex()
    
    def start_worker(self, name: str, worker: QThread):
        with QMutexLocker(self._mutex):
            if name in self._workers:
                self.stop_worker(name)
            self._workers[name] = worker
            worker.start()

# app_launcher_manager.py
class AppLauncherManager:
    """Application launching logic"""
    def launch_app(self, app: str, shot: Shot):
        # Extract launch logic
        pass
```

### 3.2 Implement Unified Cache Strategy
**Priority**: 🟡 MEDIUM
**File**: `cache_manager.py`

```python
class UnifiedCacheManager:
    def __init__(self):
        self._cache = LRUCache(max_size=100_000_000)  # 100MB
        self._prefetch_queue = asyncio.Queue()
        self._prefetch_task = None
    
    def get_with_prefetch(self, key: str, loader: Callable) -> Any:
        # Check cache
        value = self._cache.get(key)
        if value is not None:
            self._schedule_adjacent_prefetch(key)
            return value
        
        # Load and cache
        value = loader()
        self._cache.put(key, value)
        return value
```

## Phase 4: Testing & Quality (Week 3)
**Timeline**: 5-7 days
**Goal**: Achieve 95% unit test coverage

### 4.1 Add Qt Integration Tests
**Priority**: 🟡 MEDIUM
**Files**: Create `tests/integration/test_main_window_complete.py`

```python
class TestMainWindowWorkflow:
    def test_shot_selection_to_launch(self, qtbot, mock_process_pool):
        """End-to-end user workflow test"""
        window = MainWindow()
        qtbot.addWidget(window)
        
        # Select shot
        shot = Shot("demo", "seq01", "0010")
        window.shot_model.select_shot(shot)
        
        # Verify info panel
        assert window.info_panel.current_shot == shot
        
        # Launch application
        with qtbot.waitSignal(window.launcher_manager.command_started):
            window._launch_app("nuke")
        
    def test_drag_drop_operations(self, qtbot):
        """Test drag-and-drop functionality"""
        # Implementation
        pass
```

### 4.2 Add Performance Regression Tests
**Priority**: 🟡 MEDIUM
**Files**: Create `tests/performance/test_benchmarks.py`

```python
@pytest.mark.benchmark
def test_shot_loading_performance(benchmark):
    """Ensure shot loading meets performance targets"""
    model = ShotModel()
    
    def load_shots():
        return model.refresh_shots()
    
    result = benchmark(load_shots)
    assert benchmark.stats['mean'] < 0.5  # 500ms threshold
    assert benchmark.stats['max'] < 1.0   # 1s worst case

@pytest.mark.benchmark  
def test_regex_performance(benchmark):
    """Regex parsing performance benchmark"""
    parser = OptimizedShotParser()
    test_paths = [f"/shows/demo/shots/seq{i:02d}/seq{i:02d}_{j:04d}/" 
                  for i in range(10) for j in range(100)]
    
    def parse_all():
        return [parser.parse_shot_path(p) for p in test_paths]
    
    result = benchmark(parse_all)
    assert benchmark.stats['mean'] < 0.001  # 1ms for 1000 paths
```

## Phase 5: Type Safety Migration (Week 4)
**Timeline**: 3-5 days
**Goal**: Achieve type safety with basedpyright

### 5.1 Configure Gradual Type Checking
**File**: `pyrightconfig.json`
```json
{
  "typeCheckingMode": "basic",
  "reportUnknownMemberType": "warning",
  "reportUnknownArgumentType": "warning", 
  "reportUnknownVariableType": "warning",
  "reportMissingTypeStubs": false,
  "pythonVersion": "3.11"
}
```

### 5.2 Add Type Annotations
**Priority by module**:
1. `shot_model.py` - Core data model
2. `cache_manager.py` - Critical caching logic
3. `process_pool_manager.py` - Subprocess management
4. `main_window.py` - UI components

```python
# Example type improvements
from typing import TypedDict, Protocol

class ShotDict(TypedDict):
    show: str
    seq: str
    shot: str
    workspace_path: str

class CacheProtocol(Protocol):
    def get(self, key: str) -> Any | None: ...
    def put(self, key: str, value: Any) -> None: ...
    def invalidate(self, pattern: str | None = None) -> None: ...
```

## Phase 6: Documentation & Monitoring (Week 5)
**Timeline**: 3-5 days
**Goal**: Production readiness

### 6.1 Add Performance Monitoring
**File**: Create `performance_monitor.py`

```python
class PerformanceMonitor:
    def __init__(self):
        self._metrics = {}
        self._start_times = {}
    
    def start_timer(self, operation: str):
        self._start_times[operation] = time.perf_counter()
    
    def end_timer(self, operation: str):
        if operation in self._start_times:
            elapsed = time.perf_counter() - self._start_times[operation]
            self._metrics[operation] = elapsed
            logger.info(f"Performance: {operation} took {elapsed:.3f}s")
            
    def get_metrics(self) -> dict[str, float]:
        return self._metrics.copy()
```

### 6.2 Create Operations Runbook
**File**: `OPERATIONS_RUNBOOK.md`
- Startup procedures
- Performance baselines
- Troubleshooting guide
- Mock environment setup
- Testing procedures

## Success Metrics

### Performance Targets
| Metric | Current | Target | Achieved |
|--------|---------|--------|----------|
| Startup Time | 2.35s | <0.5s | [ ] |
| Shot Refresh | 2.45s | <0.2s | [ ] |
| Regex Processing | 912K ops/s | 3M+ ops/s | [ ] |
| Memory Usage | 47MB | <40MB | [ ] |
| Cache Hit Rate | Variable | >85% | [ ] |

### Quality Targets
| Metric | Current | Target | Achieved |
|--------|---------|--------|----------|
| Test Count | 236 | 1,114 | [ ] |
| Test Pass Rate | 99.4% | >99% | [ ] |
| Type Coverage | ~30% | >90% | [ ] |
| Code Complexity | High | Medium | [ ] |
| Thread Safety | B+ | A | [ ] |

## Risk Mitigation

### Backup Strategy
- Create git branch: `code-review-improvements`
- Backup critical files before changes
- Test each phase independently
- Maintain backwards compatibility

### Rollback Plan
- Each phase tagged in git
- Feature flags for new implementations
- Parallel testing of old vs new code paths
- Gradual rollout with monitoring

## Timeline Summary

| Week | Phase | Critical Tasks | Expected Outcome |
|------|-------|---------------|------------------|
| Day 1 | Critical Fixes | Restore files, fix threading | Stable application |
| Week 1 | Performance | Async loading, regex optimization | <0.5s startup |
| Week 2 | Architecture | MainWindow refactor, unified cache | Improved maintainability |
| Week 3 | Testing | Qt tests, performance benchmarks | 95% coverage |
| Week 4 | Type Safety | Annotations, gradual checking | Type-safe codebase |
| Week 5 | Production | Monitoring, documentation | Production ready |

## Conclusion

This comprehensive action plan addresses all critical issues identified by the multi-agent code review. Following this plan will:

1. **Immediately stabilize** the application (Day 1)
2. **Dramatically improve performance** (80-95% faster startup)
3. **Enhance maintainability** through refactoring
4. **Ensure reliability** with comprehensive testing
5. **Achieve type safety** for long-term stability

The plan is structured for incremental delivery with measurable outcomes at each phase, ensuring continuous improvement while maintaining production stability.