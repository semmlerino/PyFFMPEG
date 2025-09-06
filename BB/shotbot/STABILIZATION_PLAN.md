# ShotBot Stabilization Plan

## Current State Assessment

### Issues Identified
1. **Threading Issues** (2 remaining from audit)
   - HIGH: Progress reporter initialization race in ThreeDESceneWorker
   - MEDIUM: ThumbnailLoader signal deletion during emission
   
2. **Type Safety** (1,380 errors)
   - Import issues with PySide6 types
   - Optional type handling gaps
   - Missing type annotations
   
3. **Code Quality** (52,249 ruff errors)
   - Import organization issues
   - Missing return type annotations
   - Code style violations

4. **Recent Changes** (Phase 1 optimizations)
   - OptimizedShotParser integration needs validation
   - Cache preloading changes need testing
   - Ensure no regressions introduced

## Stabilization Priority Order

### Priority 1: Critical Stability (Prevent Crashes)
Focus on issues that can cause application crashes or data corruption.

#### 1.1 Fix Threading Race Conditions
**Files to modify:**
- `threede_scene_worker.py` - Add null checks for _progress_reporter
- `cache/thumbnail_loader.py` - Add sip.isdeleted() check before signal emission

**Implementation:**
```python
# threede_scene_worker.py
def _report_progress(self, current: int, total: int, message: str):
    """Report progress safely."""
    if self._progress_reporter is None:
        logger.debug(f"Progress reporter not initialized: {message}")
        return
    try:
        self._progress_reporter(current, total, message)
    except Exception as e:
        logger.warning(f"Progress report failed: {e}")

# cache/thumbnail_loader.py
def _emit_signal_safely(self, signal, *args):
    """Emit signal with deletion check."""
    try:
        import sip
        if not sip.isdeleted(signal):
            signal.emit(*args)
    except RuntimeError as e:
        logger.debug(f"Signal emission failed (object deleted): {e}")
```

#### 1.2 Resource Cleanup Verification
Ensure all resources are properly cleaned up:
- QThread termination with timeout
- Process pool cleanup
- Widget deletion order

### Priority 2: Functional Stability (Ensure Features Work)

#### 2.1 Test Suite Execution
Run comprehensive tests to catch regressions:
```bash
# Quick validation (2 seconds)
python3 tests/utilities/quick_test.py

# Fast tests (50-60 seconds)
./run_fast_tests.sh

# Full suite (100-120 seconds)
python3 -m pytest tests/ -v
```

#### 2.2 Mock Environment Validation
```bash
# Verify mock filesystem
python verify_mock_environment.py

# Test with mock mode
python shotbot_mock.py

# Headless testing
python shotbot.py --headless --mock
```

### Priority 3: Type Safety (Improve Maintainability)

#### 3.1 Fix Critical Type Errors
Focus on errors that block functionality:
- Import issues with QAction
- Optional type handling
- None checks before attribute access

#### 3.2 Systematic Type Fixing Approach
1. Fix imports in TYPE_CHECKING blocks
2. Add proper Optional handling
3. Use type guards for None checks
4. Add missing return type annotations

### Priority 4: Code Quality (Clean Codebase)

#### 4.1 Apply Safe Auto-fixes
```bash
# Auto-fix safe issues
ruff check --fix .

# Format code
ruff format .
```

#### 4.2 Manual Review Required
- Review unsafe fixes before applying
- Check for logic changes
- Validate formatting doesn't break code

## Implementation Timeline

### Day 1: Critical Stability (Today)
**Morning:**
- [ ] Fix _progress_reporter race condition
- [ ] Fix ThumbnailLoader signal deletion issue
- [ ] Run quick tests to verify fixes

**Afternoon:**
- [ ] Run full test suite
- [ ] Fix any test failures
- [ ] Verify mock environment works

### Day 2: Functional Validation
**Morning:**
- [ ] Test Phase 1 optimizations thoroughly
- [ ] Benchmark performance (should see 8.1M ops/s parsing)
- [ ] Verify cache preloading works correctly

**Afternoon:**
- [ ] Fix critical type errors (focus on functionality blockers)
- [ ] Apply safe ruff auto-fixes
- [ ] Re-run tests after fixes

### Day 3: Cleanup and Documentation
**Morning:**
- [ ] Address remaining high-priority type errors
- [ ] Manual code review of changes
- [ ] Performance profiling

**Afternoon:**
- [ ] Create comprehensive test report
- [ ] Document all fixes applied
- [ ] Prepare for deployment

## Success Metrics

### Stability Metrics
- **Zero crashes** during 1-hour stress test
- **All tests passing** (1,114 tests)
- **No thread deadlocks** detected
- **Memory stable** (no leaks over 1 hour)

### Quality Metrics
- **Type errors**: Reduce from 1,380 to <500
- **Ruff errors**: Reduce from 52,249 to <10,000
- **Test coverage**: Maintain >80%
- **Performance**: No regression from Phase 1 gains

### Functional Metrics
- **Shot loading**: <3 seconds for 400+ shots
- **Cache hit rate**: >90% after warmup
- **UI responsiveness**: <100ms for user actions
- **Background operations**: Non-blocking

## Risk Mitigation

### Backup Strategy
- Create git branch before changes: `git checkout -b stabilization`
- Commit after each successful fix
- Tag stable points: `git tag stable-v1`

### Rollback Plan
- If critical issue found: `git checkout main`
- Keep Phase 1 changes separate from stabilization
- Document all changes for easy revert

### Testing Strategy
- Test each fix in isolation
- Run regression tests after each change
- Use mock environment for safe testing
- Validate in headless mode for CI/CD

## Verification Checklist

### Before Deployment
- [ ] All threading issues resolved
- [ ] Zero crashes in stress testing
- [ ] Performance metrics maintained
- [ ] Mock environment fully functional
- [ ] Test suite 100% passing
- [ ] Type errors reduced significantly
- [ ] Code quality improved (ruff)
- [ ] Documentation updated

### After Each Fix
- [ ] Run quick tests
- [ ] Check for regressions
- [ ] Verify functionality
- [ ] Update test results
- [ ] Commit changes

## Notes

### Known Safe Changes
- Adding null checks (defensive programming)
- Signal deletion checks (prevents RuntimeError)
- Type annotations (no runtime impact)
- Import organization (cosmetic)

### Risky Changes to Avoid
- Changing thread synchronization logic
- Modifying signal/slot connections
- Altering cache TTL values
- Changing process pool size

### Dependencies
- Ensure venv is activated for all operations
- Use Python 3.11+ for compatibility
- Qt 6.x required (PySide6)
- Keep mock environment separate from production

## Command Reference

```bash
# Activate environment
source venv/bin/activate

# Run tests
python3 tests/utilities/quick_test.py  # 2 seconds
./run_fast_tests.sh                    # 50-60 seconds
python3 -m pytest tests/ -v            # Full suite

# Check code quality
basedpyright                           # Type checking
ruff check .                           # Linting
ruff format .                          # Formatting

# Test application
python shotbot.py --mock              # Mock mode
python shotbot_mock.py                # With filesystem
python shotbot.py --headless --mock   # CI/CD mode

# Performance testing
python run_mock_demo.py               # Benchmark
python test_headless.py              # Headless test
```