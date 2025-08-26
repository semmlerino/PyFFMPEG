# Test Suite Completion Plan

## Current Status (2025-08-25)
- **Tests Collected**: 1,133 (up from 0)
- **Tests Passing**: 468+ unit tests (97.5% pass rate)
- **Mock() Instances Remaining**: 73 across 19 files
- **Failing Tests**: 12 unit tests
- **Critical Issues Fixed**: Qt threading violations, syntax errors, import errors

## Success Criteria
1. **Zero Mock() instances** - All replaced with proper test doubles
2. **100% test collection** - No syntax or import errors
3. **100% test pass rate** - All tests green
4. **Full UNIFIED_TESTING_GUIDE compliance** - Following all best practices
5. **No Qt threading violations** - Thread-safe testing patterns
6. **Reasonable test execution time** - No timeouts or hangs

## Phase 1: High-Impact Mock Replacement (Day 1)
**Goal**: Replace 61 Mock() instances in highest-priority files
**Timeline**: 6-8 hours with concurrent agents

### Priority Files (Deploy 3 agents concurrently):
1. **test_launcher_dialog.py** (11 Mock instances)
   - Replace with QDialogDouble and LauncherManagerDouble
   - Validate signal-slot connections
   - Test actual dialog behavior

2. **test_shotbot.py** (7 Mock instances)
   - Replace with comprehensive test doubles
   - Ensure proper application initialization
   - Validate settings persistence

3. **test_main_window_widgets.py** (7 Mock instances)
   - Replace with Qt widget doubles
   - Test actual widget interactions
   - Verify layout and signals

### Secondary Files (Deploy 2 agents):
4. **test_shot_grid_widget.py** (6 Mock instances)
5. **test_threede_scene_worker.py** (6 Mock instances)

## Phase 2: Fix Failing Tests (Day 1-2)
**Goal**: Resolve 12 failing unit tests
**Timeline**: 3-4 hours

### Known Issues:
1. **MockModule.quote AttributeError** in test_command_launcher
   - Selective import mocking needed
   - Validate actual command execution

2. **Async/threading issues** in test_launcher_manager
   - Ensure proper thread cleanup
   - Fix race conditions

3. **Qt widget failures**
   - Verify QApplication exists
   - Proper widget cleanup

## Phase 3: Integration Tests (Day 2)
**Goal**: Validate and fix all integration tests
**Timeline**: 4-5 hours

### Test Suites:
1. **test_shot_workflow_integration.py**
   - End-to-end shot management
   - Cache consistency
   - UI updates

2. **test_launcher_workflow_integration.py**
   - Command execution
   - Process management
   - Output handling

3. **test_cache_integration.py**
   - Thumbnail processing
   - Memory management
   - Failure recovery

## Phase 4: Final Validation (Day 2-3)
**Goal**: Complete validation and documentation
**Timeline**: 2-3 hours

### Actions:
1. Run full test suite with coverage
2. Verify no Mock() instances remain
3. Validate UNIFIED_TESTING_GUIDE compliance
4. Update documentation

## Parallelization Strategy

### Concurrent Agent Deployment:
- **Agent 1**: High Mock() count files (test_launcher_dialog.py)
- **Agent 2**: Qt widget tests (test_main_window_widgets.py)
- **Agent 3**: Worker/model tests (test_threede_scene_worker.py)
- **Agent 4**: Integration test fixes
- **Agent 5**: Documentation and validation

### File Assignment Rules:
1. One agent per file to avoid conflicts
2. Prioritize by Mock() count and complexity
3. Group related files for context sharing
4. Stagger integration test work

## Risk Mitigation

### Potential Issues:
1. **Qt Thread Safety**
   - Always use qapp fixture
   - QPixmap main thread only
   - ThreadSafeTestImage for workers

2. **Race Conditions**
   - Add proper waits/delays
   - Use QSignalSpy for signals
   - Ensure cleanup order

3. **Test Interdependencies**
   - Run tests in isolation first
   - Fix shared state issues
   - Reset singletons properly

## Estimated Timeline

### Day 1 (8-10 hours):
- Phase 1: Replace 61 Mock() instances
- Phase 2: Start fixing failing tests

### Day 2 (6-8 hours):
- Phase 2: Complete test fixes
- Phase 3: Integration test validation

### Day 3 (2-4 hours):
- Phase 4: Final validation
- Documentation updates
- Completion verification

## Total Estimate: 2.5-3 days

## Next Immediate Actions

1. **Deploy 3 agents NOW for Phase 1 high-priority files**
2. **Run quick_test.py to verify current state**
3. **Start with test_launcher_dialog.py (highest Mock count)**
4. **Monitor progress and adjust strategy**

## Command Reference

```bash
# Quick validation
python3 quick_test.py

# Fast tests only
python3 run_tests_wsl.py --fast

# Full test suite
python3 run_tests.py

# Specific file
pytest tests/unit/test_launcher_dialog.py -xvs

# With coverage
pytest --cov=. --cov-report=term-missing
```

## Success Metrics

- **Before**: 0 tests collected, 0% passing
- **Current**: 1,133 tests collected, 468 passing (41%)
- **Target**: 1,200+ tests collected, 100% passing
- **Mock() Reduction**: 180 → 73 → 0
- **Execution Time**: < 60 seconds for fast tests