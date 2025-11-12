# Best Practices Review Checklist
## REFACTORING_PLAN_EPSILON Remediation Items

**Review Date**: November 12, 2025  
**Total Items**: 11 (3 Critical, 5 Medium, 3 Low)  
**Overall Status**: Ready to Execute with Modifications

---

## CRITICAL ISSUES - FIX BEFORE EXECUTION

### [CRITICAL-1] Add Thread Safety to FeatureFlags (Task 2.1)

**Status**: ❌ MUST FIX  
**Severity**: HIGH  
**Impact**: Race condition in multi-threaded code  

**Issue**: 
```python
# Current implementation (UNSAFE)
@classmethod
def from_environment(cls) -> "FeatureFlags":
    if cls._instance is None:
        cls._instance = cls(...)  # Race condition!
    return cls._instance
```

**Solution**:
```python
import threading

class FeatureFlags:
    _instance: ClassVar["FeatureFlags | None"] = None
    _lock = threading.Lock()
    
    @classmethod
    def from_environment(cls) -> "FeatureFlags":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(...)
        return cls._instance
```

**File**: `config/feature_flags.py`  
**Effort**: 30 minutes  
**Verification**:
```bash
# Add thread safety test
python -c "
import threading
from config.feature_flags import FeatureFlags

def create_flags():
    return FeatureFlags.from_environment()

threads = [threading.Thread(target=create_flags) for _ in range(10)]
for t in threads: t.start()
for t in threads: t.join()

# Should only have 1 instance
print('OK' if FeatureFlags._instance else 'FAILED')
"
```

**Checklist**:
- [ ] Add `_lock = threading.Lock()` class variable
- [ ] Wrap initialization with `with cls._lock:`
- [ ] Test with concurrent access
- [ ] Run full test suite: `pytest tests/ -n auto --dist=loadgroup`
- [ ] Type checking passes: `basedpyright`

---

### [CRITICAL-2] Complete Phase 2 Task Specifications (Tasks 2.2-2.7)

**Status**: ❌ MUST FIX  
**Severity**: HIGH  
**Impact**: Cannot execute Phase 2 until completed  

**Issue**: Tasks marked as `[Task X detailed structure...]`
- No code examples
- No API signatures shown
- No test strategies documented
- Inconsistent with Phase 1 detail level

**Solution**: Complete each task with same detail level as Phase 1

**File**: `REFACTORING_PLAN_EPSILON.md`  
**Effort**: 2-3 days  

**Tasks to Complete**:

#### Task 2.2: Extract DependencyFactory
- [ ] Show DependencyFactory class structure
- [ ] List 20+ dependencies being extracted
- [ ] Show method signatures (create_launcher, create_cache, etc.)
- [ ] Add test strategy (how to verify dependencies)
- [ ] Add code examples for MainWindow integration
- [ ] Document dependency graph
- [ ] Add rollback plan
- [ ] Add git commit message template

#### Task 2.3: Extract Shot Selection Handlers
- [ ] Show what gets extracted from _on_shot_selected
- [ ] Show new method signatures
- [ ] Add before/after code examples
- [ ] Include test strategy
- [ ] Show impact metrics
- [ ] Add rollback plan

#### Tasks 2.4-2.6: Extract Cache Components
- [ ] Show ThumbnailCache API structure
- [ ] Show ShotCache API structure
- [ ] Show SceneCache API structure
- [ ] Document which CacheManager methods delegate to each
- [ ] Add integration test strategy
- [ ] Include test examples
- [ ] Show phased migration path

#### Task 2.7: Convert CacheManager to Facade
- [ ] Show facade API structure
- [ ] Document delegation patterns
- [ ] Show old API still works
- [ ] Show new API uses extracted components
- [ ] Include backward compatibility strategy
- [ ] Add test strategy for facade

**Verification**:
- Each task should have explicit success criteria
- Each task should have verification commands
- Each task should have code examples (before/after)
- Each task should have test strategy

**Checklist**:
- [ ] Task 2.2 specifications complete
- [ ] Task 2.3 specifications complete
- [ ] Task 2.4 specifications complete
- [ ] Task 2.5 specifications complete
- [ ] Task 2.6 specifications complete
- [ ] Task 2.7 specifications complete
- [ ] All have code examples
- [ ] All have test strategies
- [ ] All have rollback plans

---

### [CRITICAL-3] Clarify Singleton vs Dependency Injection Strategy

**Status**: ⚠️ DECISION REQUIRED  
**Severity**: HIGH  
**Impact**: Long-term code quality and SOLID compliance  

**Issue**: 
- Task 2.1 creates NEW singleton (FeatureFlags)
- Phase 4 researches REDUCING singletons from 11 managers
- Contradiction: "reduce singletons" vs "add new singleton"
- Violates Dependency Inversion Principle (DIP)

**Decision Options**:

**Option A: Keep Singleton + Add Thread Safety** (Recommended for short-term)
- Add thread safety (CRITICAL-1)
- Use reset() method for testing (as per CLAUDE.md)
- Document why singleton for FeatureFlags specifically
- Plan Phase 4 consolidation

**Option B: Switch to Dependency Injection** (Better long-term)
```python
# Instead of singleton:
class FeatureFlags:
    def __init__(self, ...): ...

# In main.py:
flags = FeatureFlags.from_environment()
app = create_app(flags)  # Inject
```

**Option C: Module-Level Singleton** (Middle ground)
```python
# flags.py
_flags = None
def get_flags() -> FeatureFlags:
    global _flags
    if _flags is None:
        _flags = FeatureFlags.from_environment()
    return _flags
```

**Recommendation**: Option A (short-term) → Option B (Phase 4 refactoring)

**File**: Decision document + REFACTORING_PLAN_EPSILON.md  
**Effort**: 1 day discussion  

**Checklist**:
- [ ] Decision made: Singleton vs DI
- [ ] Rationale documented
- [ ] Phase 4 plan updated
- [ ] CLAUDE.md updated if needed

---

## MEDIUM PRIORITY ISSUES - COMPLETE BEFORE PHASE 1 FINISHES

### [MEDIUM-1] Capture Performance Baseline

**Status**: ⚠️ SHOULD FIX  
**Severity**: MEDIUM  
**Impact**: Can't measure refactoring effectiveness  

**Timing**: Before Task 1.1 starts  
**Effort**: 30 minutes  

**Metrics to Capture**:
```bash
# 1. Test execution time
time ~/.local/bin/uv run pytest tests/ -n auto --dist=loadgroup

# 2. Application startup time  
time python -c "from main_window import MainWindow; print('OK')"

# 3. Type checking time
time ~/.local/bin/uv run basedpyright

# 4. Linting time
time ~/.local/bin/uv run ruff check .

# 5. Manual: Shot loading time (select show, measure load time)
# 6. Manual: Launch operation time (select shot → click launch Nuke → Nuke opens)
```

**Storage**: Create `BASELINE_METRICS.txt` with results

**Checklist**:
- [ ] Baseline test time captured
- [ ] Baseline startup time captured
- [ ] Baseline type check time captured
- [ ] Baseline linting time captured
- [ ] Manual timing captured
- [ ] Results stored in BASELINE_METRICS.txt
- [ ] Task 1.6 has comparison metrics

---

### [MEDIUM-2] Add Property-Based Tests (Task 1.3)

**Status**: ⚠️ SHOULD ADD  
**Severity**: MEDIUM  
**Impact**: Prevent subtle bugs in dataclass conversion  

**What**: Use Hypothesis library to verify dataclass exceptions maintain invariants

**Tool**: `hypothesis` (already in project dependencies)

**Test Strategy**:
```python
from hypothesis import given, strategies as st
from exceptions import ShotValidationError

@given(
    message=st.text(min_size=1),
    shot_name=st.one_of(st.none(), st.text())
)
def test_exception_invariants(message, shot_name):
    # Create exception
    exc = ShotValidationError(message, shot_name=shot_name)
    
    # Verify invariants
    assert exc.message == message
    assert exc.shot_name == shot_name
    assert str(exc) == message  # Exception message
    
    # Verify can be raised/caught
    try:
        raise exc
    except ShotValidationError as e:
        assert e.message == message
```

**File**: `tests/unit/test_exceptions.py`  
**Effort**: 4 hours  

**Checklist**:
- [ ] Property-based tests written for ShotValidationError
- [ ] Tests written for CacheError
- [ ] Tests written for other exceptions (6 more)
- [ ] Tests verify invariants maintained
- [ ] Tests verify exceptions can be raised/caught
- [ ] All tests pass: `pytest tests/unit/test_exceptions.py -v`

---

### [MEDIUM-3] Define Integration Test Strategy (Phase 2)

**Status**: ⚠️ SHOULD PLAN  
**Severity**: MEDIUM  
**Impact**: Catch component interaction bugs  

**What**: Test extracted components work together correctly

**Components to Test**:
1. ThumbnailCache + ShotCache integration
2. CacheManager facade delegates correctly
3. DependencyFactory creates working component graph
4. Extracted handlers work with MainWindow

**Test Structure**:
```python
def test_cache_facade_integration():
    """Verify CacheManager facade delegates correctly."""
    cache = CacheManager()
    
    # ThumbnailCache operations work
    result = cache.get_thumbnail_path(...)
    
    # ShotCache operations work
    result = cache.get_shots(...)
    
    # SceneCache operations work
    result = cache.get_scenes(...)
    
    # All cached correctly
    assert cache.get_thumbnail_path(...) == result  # Cached
```

**File**: `tests/integration/test_cache_facade.py`  
**Effort**: 1 day  

**Checklist**:
- [ ] Integration test file created
- [ ] Tests for cache facade delegation
- [ ] Tests for component interactions
- [ ] Tests for MainWindow integration
- [ ] All tests pass
- [ ] No coverage regression

---

### [MEDIUM-4] Add Logging Verification Tests (Phase 3)

**Status**: ⚠️ SHOULD PLAN  
**Severity**: MEDIUM  
**Impact**: Prevent silent logging breakage  

**What**: Verify logging works after mixin removal

**Test Strategy**:
```python
def test_logger_creation_after_mixin_removal():
    """Verify classes have working loggers after mixin removal."""
    # Sample refactored classes
    classes_to_check = [
        SomeClass,
        AnotherClass,
        # ... others ...
    ]
    
    for cls in classes_to_check:
        instance = cls()
        # Logger exists and works
        assert hasattr(instance, 'logger')
        assert instance.logger.name == cls.__module__ + '.' + cls.__name__
        
        # Logger methods work
        instance.logger.info("test")
        instance.logger.debug("test")
        instance.logger.warning("test")
        instance.logger.error("test")
```

**File**: `tests/unit/test_logger_refactoring.py`  
**Effort**: 1 day  

**Checklist**:
- [ ] Logger creation tests written
- [ ] Tests verify logger.info/debug/warning/error work
- [ ] Spot-check 20+ refactored classes
- [ ] Tests for logger configuration
- [ ] All tests pass
- [ ] No regressions in logging

---

### [MEDIUM-5] Complete Phase 2 Specification Work (Strategy)

**Status**: ⚠️ ONGOING  
**Severity**: MEDIUM  
**Impact**: Enables Phase 2 execution  

**Timeline**: Complete during Phase 1 execution

**Checklist**:
- [ ] Start Phase 2 spec work week 1 of Phase 1
- [ ] Complete by end of Phase 1 (2 days)
- [ ] Have specs ready before Phase 2 starts
- [ ] All 6 tasks (2.2-2.7) fully specified
- [ ] Code examples for each task
- [ ] Test strategies documented
- [ ] Success criteria explicit

---

## LOW PRIORITY ISSUES - NICE TO HAVE

### [LOW-1] Document Dependency Graph

**Status**: ℹ️ NICE TO HAVE  
**Effort**: 4 hours  
**Benefit**: Better understanding of component relationships  

**What**: Visual diagram or text showing dependency relationships

**Format Options**:
1. ASCII diagram in documentation
2. Graphviz/Mermaid diagram
3. Text description of dependencies

**Example**:
```
MainWindow
  ├── FeatureFlags (config)
  ├── SimplifiedLauncher
  │   ├── CacheManager (facade)
  │   │   ├── ThumbnailCache
  │   │   ├── ShotCache
  │   │   └── SceneCache
  │   └── ProcessPoolManager
  ├── LauncherController
  ├── SettingsManager
  └── ... (18 more)
```

**Checklist**:
- [ ] Dependency graph documented
- [ ] Format chosen (ASCII/diagram/text)
- [ ] Added to REFACTORING_PLAN_EPSILON.md
- [ ] DependencyFactory signature shows all 20+ dependencies

---

### [LOW-2] Show Phased Migration Path

**Status**: ℹ️ NICE TO HAVE  
**Effort**: 4 hours  
**Benefit**: Clearer upgrade path for users  

**What**: Timeline and strategy for old → new code migration

**Content**:
- When old API deprecated
- Timeline for removal (3-6 months?)
- Deprecation warnings in code
- Migration guide for users
- Examples of old vs new usage

**Checklist**:
- [ ] Migration strategy documented
- [ ] Deprecation timeline specified
- [ ] Deprecation warnings planned
- [ ] Migration guide written
- [ ] Examples provided

---

### [LOW-3] Document Protocol-Based DI Alternative

**Status**: ℹ️ NICE TO HAVE  
**Effort**: 2 hours  
**Benefit**: Reference for future improvements  

**What**: Show Protocol-based DI as alternative for better type safety

**Example**:
```python
from typing import Protocol

class LauncherProvider(Protocol):
    """Protocol for launcher creation."""
    def create_launcher(self, parent) -> SimplifiedLauncher: ...

class MainWindow:
    def __init__(self, factory: LauncherProvider):
        self.launcher = factory.create_launcher(self)
```

**Checklist**:
- [ ] Protocol-based DI documented
- [ ] Example code provided
- [ ] Comparison with current approach
- [ ] When to use which pattern
- [ ] Added to documentation

---

## SUMMARY CHECKLIST

### Before Phase 1 Execution
- [ ] CRITICAL-1: Add thread safety to FeatureFlags
- [ ] CRITICAL-2 START: Begin Phase 2 specifications
- [ ] CRITICAL-3: Make singleton vs DI decision
- [ ] MEDIUM-1: Capture performance baseline
- [ ] All prerequisites met

### During Phase 1 Execution
- [ ] CRITICAL-2 COMPLETE: Finish Phase 2 specifications
- [ ] MEDIUM-2: Add property-based tests (Task 1.3)
- [ ] MEDIUM-3: Plan integration tests (Phase 2)
- [ ] MEDIUM-4: Plan logging tests (Phase 3)

### Before Phase 2 Execution
- [ ] CRITICAL-2: Phase 2 specs fully complete
- [ ] MEDIUM-3: Integration test strategy finalized
- [ ] LOW-1: Dependency graph documented (optional)
- [ ] LOW-2: Migration path documented (optional)

### Before Phase 3 Execution
- [ ] MEDIUM-4: Logging verification tests ready
- [ ] Phase 2 complete and validated

### Phase 4 (Research)
- [ ] CRITICAL-3: Singleton consolidation research
- [ ] LOW-3: Protocol-based DI documented

---

## VERIFICATION

After completing this checklist:

```bash
# Verify all changes work
pytest tests/ -n auto --dist=loadgroup
basedpyright
ruff check .

# Review updated documents
cat BEST_PRACTICES_REVIEW_EPSILON.md
cat BEST_PRACTICES_REVIEW_SUMMARY.txt
cat REFACTORING_PLAN_EPSILON.md
```

---

**Document Status**: READY FOR TRACKING  
**Last Updated**: November 12, 2025  
**Next Review**: After Phase 1 completion

