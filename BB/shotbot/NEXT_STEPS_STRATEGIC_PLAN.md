# Strategic Next Steps Plan

## Current State Assessment

### ✅ Completed (High Impact Achieved)
- **Stability**: Fixed critical threading race condition
- **Performance**: Parser improved 37% (2.2M ops/s)
- **Type Safety**: Fixed TYPE_CHECKING imports, replaced Any types
- **Testing**: 100% pass rate achieved

### 📊 Current Metrics
- Type Errors: 1,351 (down from 1,387)
- Code Duplication: ~400 lines in delegates
- MainWindow Size: 2,071 lines (59 methods)
- Model Files: 6 files with significant overlap

## Recommended Implementation Strategy

### Phase 1: Type Safety Completion (4-6 hours)
**Goal**: Reduce type errors below 500 for safer refactoring

#### Task 1: Complete Optional Widget Null Checks ⚠️
**Status**: IN PROGRESS
**Effort**: 2-3 hours
**Impact**: Eliminate ~150 type errors

**Pattern to Apply**:
```python
# Before (unsafe)
window.widget.method()

# After (safe)
if window.widget is not None:
    window.widget.method()
```

**Key Files**:
- `main_window.py` (50+ occurrences)
- `shot_grid_view.py` (20+ occurrences)
- `settings_dialog.py` (15+ occurrences)

#### Task 2: Add Event Handler Type Annotations
**Status**: PENDING
**Effort**: 2-3 hours
**Impact**: Eliminate ~200 type errors

**Patterns to Apply**:
```python
from PySide6.QtGui import QCloseEvent, QPaintEvent, QMouseEvent, QKeyEvent

def closeEvent(self, event: QCloseEvent) -> None:
def paintEvent(self, event: QPaintEvent) -> None:
def mousePressEvent(self, event: QMouseEvent) -> None:
def keyPressEvent(self, event: QKeyEvent) -> None:
```

**Key Files**:
- `shot_grid_delegate.py`
- `threede_grid_delegate.py`
- `thumbnail_widget_base.py`
- All custom widget classes

### Phase 2: Quick Win Refactoring (1 day)
**Goal**: Eliminate code duplication for easier maintenance

#### Task 3: Consolidate Duplicate Delegates 🎯
**Status**: PENDING
**Effort**: 4-6 hours
**Impact**: Eliminate 400 lines of duplication

**Implementation Strategy**:
```python
# Create base class
class BaseThumbnailDelegate(QStyledItemDelegate):
    def __init__(self, config: DelegateConfig):
        self.config = config
        
    def paint(self, painter, option, index):
        # Shared painting logic
        
# Specialize for each use case
class ShotGridDelegate(BaseThumbnailDelegate):
    def __init__(self):
        super().__init__(ShotDelegateConfig())
        
class ThreeDEGridDelegate(BaseThumbnailDelegate):
    def __init__(self):
        super().__init__(ThreeDEDelegateConfig())
```

**Benefits**:
- Single point of maintenance
- Consistent rendering behavior
- Easier to add new grid types

### Phase 3: Architecture Improvements (3-5 days)
**Goal**: Improve maintainability and testability

#### Task 4: Decompose MainWindow 🏗️
**Status**: PENDING
**Effort**: 1-2 days
**Impact**: Transform 2,071 lines into 4-5 focused classes

**Decomposition Plan**:
```python
# Current: Everything in MainWindow
class MainWindow(QMainWindow):  # 2,071 lines, 59 methods!

# Target: Focused managers
class MainWindow(QMainWindow):  # ~400 lines
    def __init__(self):
        self.shot_manager = ShotRefreshManager()
        self.ui_coordinator = UICoordinator()
        self.launcher_coordinator = LauncherCoordinator()
        self.settings_coordinator = SettingsCoordinator()

class ShotRefreshManager:  # ~300 lines
    """Handles shot refresh logic and caching"""
    
class UICoordinator:  # ~400 lines
    """Manages UI setup and tab switching"""
    
class LauncherCoordinator:  # ~300 lines
    """Manages launcher menu and execution"""
    
class SettingsCoordinator:  # ~200 lines
    """Manages settings application and persistence"""
```

#### Task 5: Unify Model Hierarchy
**Status**: PENDING
**Effort**: 2 days
**Impact**: Reduce 6 files to 3, improve type safety

**Strategy**:
```python
# Generic base with type parameters
class BaseItemModel(QAbstractListModel, Generic[T]):
    """Reusable model for any grid view"""
    
class ShotItemModel(BaseItemModel[Shot]):
    """Shot-specific specialization"""
    
class ThreeDEItemModel(BaseItemModel[ThreeDEScene]):
    """3DE scene specialization"""
```

## Decision Matrix

| Task | Effort | Risk | Impact | Priority | ROI |
|------|--------|------|---------|----------|-----|
| Null checks | 3h | Low | High | HIGH | ⭐⭐⭐⭐⭐ |
| Event types | 3h | Low | High | HIGH | ⭐⭐⭐⭐⭐ |
| Delegates | 6h | Low | Medium | MEDIUM | ⭐⭐⭐⭐ |
| MainWindow | 16h | Medium | High | MEDIUM | ⭐⭐⭐ |
| Models | 16h | Medium | Medium | LOW | ⭐⭐ |

## Implementation Timeline

### Day 1 (Today)
- ✅ Morning: Complete optional widget null checks
- Afternoon: Start event handler annotations

### Day 2
- Morning: Complete event handler annotations
- Afternoon: Begin delegate consolidation

### Day 3
- Complete delegate consolidation
- Test thoroughly

### Week 2
- Days 1-2: MainWindow decomposition
- Days 3-4: Model hierarchy (if time permits)
- Day 5: Integration testing

## Success Metrics

### Short Term (End of Week 1)
- [ ] Type errors < 500 (from 1,351)
- [ ] Zero duplicate delegate code
- [ ] All event handlers typed

### Long Term (End of Week 2)
- [ ] MainWindow < 500 lines
- [ ] 4-5 focused manager classes
- [ ] Model files reduced to 3

## Risk Mitigation

1. **Test Coverage**: Run full test suite after each change
2. **Incremental Changes**: Small, focused commits
3. **Feature Flags**: Use config flags for major refactoring
4. **Rollback Plan**: Tag stable version before Phase 3

## Expected Outcomes

### After Phase 1 (Type Safety)
- **Developer Experience**: Better IDE support, fewer runtime errors
- **Confidence**: Type checker catches issues before runtime
- **Documentation**: Types serve as inline documentation

### After Phase 2 (Delegates)
- **Maintainability**: Single source of truth for rendering
- **Consistency**: Uniform behavior across grids
- **Extensibility**: Easy to add new grid types

### After Phase 3 (Architecture)
- **Testability**: Focused classes easier to unit test
- **Onboarding**: New developers understand structure faster
- **Scalability**: Easy to add features without touching core

## Next Action

**Start immediately with**: Complete optional widget null checks (IN PROGRESS)

This provides maximum value with minimum risk while laying groundwork for larger refactoring efforts.