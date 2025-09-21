# PLAN ALPHA: Comprehensive Test Suite Optimization Strategy
## DO NOT DELETE - Critical Reference Document

## Executive Summary
The ShotBot test suite has 1,114 tests with significant performance and reliability issues. This plan addresses 68 verified anti-patterns and achieves 70-85% performance improvement through systematic optimization.

## Verified Issues (Confirmed via Analysis)

### 1. Performance Bottlenecks
- **No Parallel Execution**: Tests run serially despite multi-core availability
  - Location: `pytest.ini` line 30 (`-n auto` commented out)
  - Impact: Missing 60-80% potential speedup

- **Type Checking Disabled**: Tests excluded from type safety verification
  - Location: `pyrightconfig.json` line 11 (`tests/**` in exclude)
  - Impact: Type errors accumulate undetected

### 2. Anti-Pattern Analysis (68 Total Issues)
```
📊 Anti-Pattern Distribution:
├── time.sleep() calls: 58 occurrences
│   ├── tests/test_doubles_extended.py: 2 instances
│   ├── tests/integration/test_async_workflow_integration.py: 2 instances
│   ├── tests/moved_from_root/test_persistent_terminal.py: 4 instances
│   └── 48 more across 26 files
├── Mock(spec=) patterns: 4 occurrences
│   └── tests/test_type_safe_patterns.py: 4 instances
├── Assert called patterns: 3 occurrences
│   └── tests/test_type_safe_patterns.py: 3 instances
└── QPixmap threading issues: 3 occurrences
    └── tests/unit/test_thumbnail_widget_qt.py: 3 instances
```

### 3. Qt Concurrency Issues
- **QApplication.processEvents() Race Conditions**: 7+ instances
  - tests/conftest.py: 2 instances (lines 366, 390)
  - tests/thread_tests/test_thread_safety_regression.py: 4 instances
  - tests/test_type_safe_patterns.py: 1 instance
  - Impact: Non-deterministic test behavior, event reordering

### 4. Integration Test Complexity
- **Monolithic Test Methods**: Single tests verifying 3-8 concerns
  - Example: `test_shot_selection_to_launch_workflow` (lines 87-129)
    - Tests shot selection
    - Tests info panel update
    - Tests launcher invocation
    - Tests window state persistence
  - Impact: Poor failure isolation, maintenance burden

## Comprehensive Fix Strategy

### PHASE 1: Quick Performance Wins (1-2 hours implementation)
**Goal**: Achieve immediate 60-80% speedup with minimal risk

#### 1.1 Enable Parallel Test Execution
```ini
# pytest.ini line 30 - CHANGE:
-    # -n auto
+    -n auto
```
**Expected Impact**: 60-80% speedup on multi-core systems (linear scaling)

#### 1.2 Configure Test Type Checking
```json
// Create tests/pyrightconfig.json
{
  "extends": "../pyrightconfig.json",
  "include": ["**/*.py"],
  "exclude": ["**/__pycache__"],
  "typeCheckingMode": "basic",
  "reportUnknownMemberType": "warning",
  "reportUnknownArgumentType": "warning"
}
```

```json
// Modify root pyrightconfig.json line 11
-    "tests/**",
+    "tests/__pycache__/**",
```
**Expected Impact**: Catch type errors before runtime

#### 1.3 Mark Slow Tests for Segregation
```python
# Add markers to tests taking >1 second
@pytest.mark.slow
class TestMainWindowComplete:
    # Tests with MainWindow creation

@pytest.mark.slow
def test_cache_size_limit():
    # I/O intensive tests
```
**Expected Impact**: Enable fast test runs with `pytest -m "not slow"`

### PHASE 2: Eliminate Anti-Patterns (2-3 days implementation)
**Goal**: Fix all 68 identified anti-patterns for reliability

#### 2.1 Replace time.sleep() Calls (58 instances)
```python
# Pattern transformations:

# BAD: Arbitrary sleep
time.sleep(0.05)

# GOOD: Qt-aware waiting
qtbot.wait(50)  # For Qt tests
qtbot.waitUntil(lambda: condition_met(), timeout=1000)  # Condition-based
threading.Event().wait(timeout=0.05)  # Thread synchronization

# File-by-file fixes:
# tests/test_doubles_extended.py:562
- time.sleep(0.01)  # Small sleep to avoid busy wait
+ event.wait(timeout=0.01)  # Thread-safe wait

# tests/test_doubles_extended.py:765
- time.sleep(self.simulated_delay)
+ self.delay_event.wait(timeout=self.simulated_delay)

# tests/integration/test_async_workflow_integration.py:283,288
- time.sleep(0.05)
+ qtbot.wait(50)
```

#### 2.2 Fix QApplication.processEvents() Race Conditions (7 instances)
```python
# Pattern transformations:

# BAD: Race-prone event processing
app.processEvents()

# GOOD: Deterministic waiting
qtbot.wait(10)  # Brief pause
qtbot.waitSignal(signal, timeout=1000)  # Signal-based
qtbot.waitExposed(widget)  # Widget visibility

# conftest.py:366,390
- app.processEvents()
+ qtbot.wait(10)  # Minimal event processing delay

# tests/thread_tests/test_thread_safety_regression.py:366,392,447,451
- self.app.processEvents()
+ QTest.qWait(10)  # Thread-safe Qt waiting
```

#### 2.3 Replace Mock(spec=) Patterns (4 instances)
```python
# Pattern transformations:

# BAD: Implementation testing
mock = MagicMock(spec=ProcessPoolProtocol)
mock.assert_called_with()

# GOOD: Behavior testing with test doubles
from tests.test_doubles_library import TestProcessPool
test_pool = TestProcessPool()
assert test_pool.get_last_command() == expected

# tests/test_type_safe_patterns.py:236
- mock = MagicMock(spec=ProcessPoolProtocol)
+ test_pool = TestProcessPool()

# tests/test_type_safe_patterns.py:252
- mock = MagicMock(spec=LauncherProtocol)
+ test_launcher = TestLauncherManager()
```

### PHASE 3: Architectural Refactoring (3-5 days implementation)
**Goal**: Improve maintainability and test isolation

#### 3.1 Split Monolithic Integration Tests
```python
# Current monolithic test (lines 87-129):
def test_shot_selection_to_launch_workflow(self, qtbot, main_window, test_shots):
    """Test end-to-end user workflow: shot selection → info display → launch."""
    # Tests 5+ concerns in one method

# Refactored into focused tests:
class TestShotSelection:
    def test_shot_selection_emits_signal(self, qtbot, main_window):
        """Test that selecting a shot emits the correct signal."""

    def test_shot_selection_updates_info_panel(self, qtbot, main_window):
        """Test that info panel updates when shot is selected."""

class TestApplicationLaunching:
    def test_launch_button_triggers_launcher(self, qtbot, main_window):
        """Test that launch button invokes launcher manager."""

    def test_window_remains_responsive_after_launch(self, qtbot, main_window):
        """Test that main window stays functional after launch."""
```

#### 3.2 Optimize Fixture Architecture
```python
# Current: Heavy autouse fixture
@pytest.fixture(autouse=True)
def mock_gui_blocking_components(monkeypatch):
    # 126 lines of setup for EVERY test

# Optimized: Opt-in fixture
@pytest.fixture
def mock_gui_components(monkeypatch):
    # Same logic, but only when needed

@pytest.mark.usefixtures("mock_gui_components")
class TestMainWindow:
    # Only GUI tests use this fixture
```

#### 3.3 Implement Shared Resource Pattern
```python
# Current: MainWindow created per test
@pytest.fixture
def main_window(qtbot):
    return MainWindow()  # Expensive creation

# Optimized: Shared with reset
@pytest.fixture(scope="class")
def shared_main_window(qtbot):
    window = MainWindow()
    yield window
    # Cleanup after class

@pytest.fixture
def clean_main_window(shared_main_window):
    shared_main_window.reset_state()  # Light reset
    return shared_main_window
```

### PHASE 4: Quality Assurance Integration (1 day implementation)
**Goal**: Prevent regression of fixed issues

#### 4.1 Configure Pre-commit Hook
```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: check-test-antipatterns
        name: Check test anti-patterns
        entry: python check_test_antipatterns.py
        language: system
        files: ^tests/.*\.py$
        pass_filenames: false
        stages: [commit]
```

#### 4.2 Create CI/CD Test Strategy
```yaml
# .github/workflows/test.yml (or equivalent)
test-fast:
  run: pytest -m "not slow" -n auto --durations=20

test-slow:
  run: pytest -m "slow" -n 2 --timeout=300

test-types:
  run: basedpyright tests/
```

#### 4.3 Implement Test Categorization
```ini
# Enhanced pytest.ini markers
markers =
    # Speed tiers
    fast: Tests completing in <100ms (run frequently)
    medium: Tests completing in 100ms-1s
    slow: Tests taking >1s (run separately)

    # Architecture tiers
    unit: Pure logic tests (no I/O, no GUI)
    component: Single component integration
    integration: Multi-component coordination
    e2e: Full user workflow simulation

    # Resource requirements
    gui_heavy: Creates MainWindow or complex widgets
    filesystem: Performs real I/O operations
    network: Requires network access
    thread_intensive: Creates multiple threads/workers
```

## Performance Projections

### Baseline (Current State)
- 1,114 tests running serially
- Estimated total time: 100-120 seconds
- Flaky test rate: ~5-10% (timing issues)

### After Phase 1
- Parallel execution on 8 cores
- Expected time: 15-25 seconds (75% reduction)
- Same flaky test rate

### After Phase 2
- All timing anti-patterns fixed
- Expected time: 12-20 seconds (additional 20% from removing sleeps)
- Flaky test rate: <1%

### After Phase 3
- Optimized fixtures and shared resources
- Expected time: 10-15 seconds (additional 20% from fixture optimization)
- Better failure isolation

### After Phase 4
- Segregated test runs (fast/slow)
- Fast suite: 5-8 seconds for development
- Full suite: 15-20 seconds for CI
- Zero regression on fixed issues

## Success Metrics

1. **Performance**
   - [ ] Test suite completes in <20 seconds (from ~100 seconds)
   - [ ] Fast test subset runs in <8 seconds
   - [ ] Parallel execution scaling factor >0.7

2. **Reliability**
   - [ ] Zero time.sleep() in test code
   - [ ] Zero QApplication.processEvents() in tests
   - [ ] Flaky test rate <1%

3. **Maintainability**
   - [ ] All tests pass type checking
   - [ ] Integration tests focus on single concern
   - [ ] Pre-commit prevents anti-pattern introduction

4. **Developer Experience**
   - [ ] Clear test categorization (fast/slow/unit/integration)
   - [ ] Meaningful test failure messages
   - [ ] Fast feedback loop (<10s for most changes)

## Risk Mitigation

### Parallel Execution Risks
- **Risk**: Tests may have hidden dependencies
- **Mitigation**: Run with `--dist=loadgroup` initially, fix any failures

### Fixture Sharing Risks
- **Risk**: State leakage between tests
- **Mitigation**: Implement thorough reset_state() methods, use deepcopy where needed

### Type Checking Introduction
- **Risk**: Many type errors initially
- **Mitigation**: Start with warnings, gradually increase strictness

## Implementation Timeline

- **Week 1**: Phase 1 + Phase 2.1 (Quick wins + time.sleep fixes)
- **Week 2**: Phase 2.2-2.3 (Qt fixes + mock replacement)
- **Week 3**: Phase 3.1-3.2 (Test refactoring)
- **Week 4**: Phase 3.3 + Phase 4 (Optimization + QA integration)

## Long-term Recommendations

1. **Adopt Property-based Testing**: Use Hypothesis for edge case discovery
2. **Implement Mutation Testing**: Ensure test effectiveness
3. **Add Performance Benchmarks**: Prevent performance regressions
4. **Create Test Style Guide**: Maintain consistency across team
5. **Monitor Test Metrics**: Track execution time, flaky rate, coverage

## Appendix: File-by-File Change List

### Critical Files (Most Impact)
1. `pytest.ini` - Enable parallelization
2. `pyrightconfig.json` - Include tests in type checking
3. `conftest.py` - Fix processEvents, remove autouse
4. `tests/integration/test_main_window_complete.py` - Split workflows
5. `check_test_antipatterns.py` - Add to pre-commit

### High Priority Files (58 time.sleep instances)
[Full list of 29 files with line numbers available in anti-pattern report]

### Medium Priority Files (Mock patterns)
1. `tests/test_type_safe_patterns.py` - 7 total issues
2. `tests/unit/test_previous_shots_item_model.py` - 1 issue
3. `tests/unit/test_threede_item_model.py` - 1 issue

---
Document Version: 1.0
Date: 2025-01-20
Status: APPROVED FOR IMPLEMENTATION