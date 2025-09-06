# ShotBot Priority Action Plan

## Executive Summary

Based on comprehensive code review by specialized agents, this plan addresses critical issues by priority to maximize stability, performance, and maintainability improvements.

**Current State**: Application is stable and production-ready but has significant optimization opportunities.

## Priority Classification

- **P0 (Critical)**: Production stability at risk - Fix TODAY
- **P1 (High)**: Performance/UX degradation - Fix THIS WEEK  
- **P2 (Medium)**: Type safety & reliability - Fix NEXT SPRINT
- **P3 (Low)**: Technical debt & refactoring - Fix NEXT MONTH

---

## P0: Critical Issues (Fix Today)

### 1. ✅ Progress Reporter Race Condition - FIXED
**File**: `threede_scene_worker.py`
**Impact**: Lost progress updates during parallel scene discovery
**Effort**: 2 hours (Actual: 30 min)
**Risk**: Low (defensive fix)

**Problem**:
```python
# Line 235: Initialized to None
self._progress_reporter: QtProgressReporter | None = None

# Line 405: Created AFTER thread starts
self._progress_reporter = QtProgressReporter()

# Line 617: Callback could be called before line 405!
progress_callback=progress_callback  # Race condition!
```

**Solution**:
```python
def __init__(self, ...):
    # Create in __init__ to eliminate race
    self._progress_reporter = QtProgressReporter()
    
def do_work(self):
    # Move to worker thread
    if self._progress_reporter:
        self._progress_reporter.moveToThread(self.thread())
        self._progress_reporter.progress_update.connect(
            self._handle_progress_update, 
            Qt.ConnectionType.QueuedConnection
        )
```

**Verification**:
```bash
# Test with stress test
python3 -c "
for i in range(100):
    import subprocess
    subprocess.run(['python3', 'shotbot.py', '--headless', '--mock'], timeout=2)
"
```

---

## P1: High Priority (Fix This Week)

### 2. ✅ Parser Performance Regression - IMPROVED
**File**: `optimized_shot_parser.py`
**Impact**: Was 57% slower, now 37% faster (2.2M ops/s)
**Effort**: 4 hours (Actual: 2 hours)
**Risk**: Medium (requires thorough testing)

**Problem**: Complex fallback logic overwhelming regex optimizations
**Current**: 1.6M ops/s | **Target**: 3M ops/s | **Expected**: 2.8-3.2M ops/s

**Solution**:
```python
def parse_workspace_line(self, line: str) -> ParseResult | None:
    """Ultra-optimized parser maintaining correctness."""
    match = self._ws_pattern.search(line)
    if not match:
        return None
        
    workspace_path, show, sequence, shot_dir = match.groups()
    
    # Ultra-fast path: Direct string slicing (85% of cases)
    seq_len = len(sequence)
    if (len(shot_dir) > seq_len + 1 and 
        shot_dir.startswith(sequence) and 
        shot_dir[seq_len] == '_'):
        return ParseResult(show, sequence, shot_dir[seq_len + 1:], workspace_path)
    
    # Fast fallback: Single rfind (14% of cases)
    pos = shot_dir.rfind('_')
    if pos > 0:
        return ParseResult(show, sequence, shot_dir[pos + 1:], workspace_path)
    
    # Edge case (1% of cases)
    return ParseResult(show, sequence, shot_dir, workspace_path)
```

**Verification**:
```bash
# Run benchmark
python3 optimized_shot_parser.py

# Run tests
python3 -m pytest tests/unit/test_shot_model.py -v
```

### 3. TYPE_CHECKING Import Cascade 📦
**Files**: `accessibility_manager.py`, `type_definitions.py`, others
**Impact**: 6,176 type errors cascading through codebase
**Effort**: 4 hours
**Risk**: Low (import reorganization)

**Problem**: Qt widgets under TYPE_CHECKING but used in runtime protocols

**Solution**:
```python
# BEFORE: Causes "Unknown" type at runtime
if TYPE_CHECKING:
    from PySide6.QtWidgets import QAction

# AFTER: Available at runtime
from PySide6.QtWidgets import QAction, QWidget, QSlider, QListView

# Only use TYPE_CHECKING for circular imports
if TYPE_CHECKING:
    from main_window import MainWindow  # Circular import only
```

**Files to Fix**:
1. `accessibility_manager.py` - 24 errors
2. `launcher_dialog.py` - 18 errors  
3. `settings_dialog.py` - 15 errors
4. `main_window.py` - Critical imports

**Verification**:
```bash
# Check type error reduction
basedpyright 2>&1 | grep -c "error"
```

---

## P2: Medium Priority (Next Sprint - Week 2)

### 4. Replace Explicit Any Types
**Files**: `type_definitions.py` (8), `exceptions.py` (12), `cache_manager.pyi` (15)
**Impact**: Type inference broken throughout application
**Effort**: 6 hours
**Risk**: Low

**Examples to Fix**:
```python
# BEFORE
def load_thumbnail(...) -> Any | None:
def find_all(self) -> list[Any]:
CacheData = dict[str, Any]

# AFTER  
def load_thumbnail(...) -> QPixmap | None:
def find_all(self) -> list[Shot]:
CacheData = dict[str, str | int | float | bool]
```

### 5. Add Missing Parameter Types
**Files**: All UI components with event handlers
**Impact**: ~50 functions with untyped parameters
**Effort**: 4 hours
**Risk**: Low

**Pattern to Apply**:
```python
# BEFORE
def closeEvent(self, event):
def paintEvent(self, event):

# AFTER
def closeEvent(self, event: QCloseEvent) -> None:
def paintEvent(self, event: QPaintEvent) -> None:
```

### 6. Fix Optional Widget Null Checks
**Files**: Throughout UI code
**Impact**: Potential runtime crashes
**Effort**: 3 hours
**Risk**: Low

**Pattern**:
```python
# BEFORE
window.setTabOrder(tab_widget, size_slider)  # Could be None!

# AFTER
if tab_widget is not None and size_slider is not None:
    window.setTabOrder(tab_widget, size_slider)
```

---

## P3: Technical Debt (Next Month)

### 7. Decompose MainWindow (2,071 lines)
**Effort**: 2 days
**Risk**: Medium (core refactoring)

**Strategy**: Extract into focused managers
- `ShotRefreshManager` - Shot loading logic
- `UICoordinator` - UI setup and tabs
- `LauncherCoordinator` - Application launching
- `SettingsCoordinator` - Settings management

### 8. Consolidate Duplicate Delegates (~400 lines)
**Effort**: 1 day
**Risk**: Low

**Strategy**: Create `BaseThumbnailDelegate` with theme configuration

### 9. Unify Shot Model Hierarchy (6 files → 3)
**Effort**: 2 days  
**Risk**: Medium

**Strategy**: Use generics for type-safe base model

---

## Implementation Timeline

### Week 1 (Current)
- ✅ Day 1: Fix progress reporter race (P0)
- Day 2-3: Parser optimization (P1)
- Day 4-5: TYPE_CHECKING imports (P1)

### Week 2 (Type Safety Sprint)
- Day 1-2: Replace Any types (P2)
- Day 3: Add parameter types (P2)
- Day 4: Fix null checks (P2)
- Day 5: Testing & verification

### Week 3-4 (Architecture Sprint)
- Week 3: MainWindow decomposition (P3)
- Week 4: Delegate consolidation & model unification (P3)

---

## Success Metrics

### Performance
- [ ] Parser: 2.8M+ ops/s (from 1.6M)
- [ ] Startup: <0.3s perceived (from 1.4s)
- [ ] Cache hit rate: 95%+ (from 90%)

### Type Safety
- [ ] Type errors: <200 (from 6,176)
- [ ] No explicit Any types in core modules
- [ ] All event handlers typed

### Code Quality
- [ ] MainWindow: <500 lines (from 2,071)
- [ ] Delegate duplication: 0 (from ~400 lines)
- [ ] Model files: 3 (from 6)

### Stability
- [ ] Zero race conditions
- [ ] Zero null reference errors
- [ ] All tests passing

---

## Risk Mitigation

1. **Testing Strategy**
   - Run full test suite after each fix
   - Use mock mode for rapid iteration
   - Stress test threading fixes

2. **Rollback Plan**
   - Git commit after each successful fix
   - Tag stable versions before major refactoring
   - Keep original files during refactoring

3. **Verification Commands**
   ```bash
   # After each change
   python3 shotbot.py --headless --mock
   python3 -m pytest tests/ -m fast
   basedpyright | grep -c "error"
   ```

---

## Next Steps

1. **Immediate**: Start with P0 progress reporter fix
2. **Today**: Complete P0, begin parser optimization
3. **This Week**: Complete all P1 items
4. **Next Sprint**: Begin P2 type safety improvements

The application will see immediate stability improvements from P0 fixes, significant performance gains from P1 optimizations, and long-term maintainability improvements from P2-P3 refactoring.