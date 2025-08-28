# Option A: Remaining Work Plan (Days 3-5)

## Executive Summary
**Time Remaining**: 1.5-2 days (10-15 hours)
**Critical Path**: Fix tests → Validate changes → Cleanup
**Current Status**: Type system modernized, 51 files updated, critical runtime issues resolved

## Day 3: Test Foundation (6 hours)

### Priority 1: Fix 5 Failing Integration Tests (2 hours)
**Issue**: Mock objects not configured to return iterables
**Location**: `tests/integration/test_feature_flag_switching.py`

**Root Cause**:
```python
# Current (broken):
mock_cache.get_cached_shots.return_value = Mock()  # Not iterable!

# Fix:
mock_cache.get_cached_shots.return_value = []  # Empty list
mock_cache.get_cached_threede_scenes.return_value = []
```

**Specific Tests to Fix**:
1. `test_standard_model_when_flag_not_set`
2. `test_optimized_model_when_flag_set`
3. `test_flag_values_recognized`
4. `test_window_initialization_with_standard_model`
5. `test_window_initialization_with_optimized_model`

**Action Items**:
- [ ] Fix mock configuration in test setup
- [ ] Add thread cleanup to prevent timeouts
- [ ] Verify all 5 tests pass
- [ ] Document fix pattern for future tests

### Priority 2: Cache Module Tests - Critical Components (4 hours)

#### 2.1 thumbnail_processor.py (8.7% → 60%)
**Missing Coverage**: 315/345 lines
**Critical Functions to Test**:
- `load_thumbnail()` - Multi-format support (Qt/PIL/OpenEXR)
- `_tone_map_hdr()` - HDR to SDR conversion
- `_resize_with_pil()` - PIL fallback resizing
- `_handle_corrupt_image()` - Error recovery

**Test Cases**:
```python
def test_load_thumbnail_qt_format():
    # Test JPG/PNG loading with Qt
    
def test_load_thumbnail_pil_fallback():
    # Test EXR/TIFF with PIL resize
    
def test_hdr_tone_mapping():
    # Test HDR to SDR conversion
    
def test_corrupt_image_handling():
    # Test graceful failure
```

#### 2.2 storage_backend.py (34.4% → 60%)
**Missing Coverage**: 82/125 lines
**Critical Functions to Test**:
- `atomic_write()` - Atomic file operations
- `safe_read()` - Read with fallback
- `cleanup_temp_files()` - Temp file cleanup
- Concurrent access patterns

## Day 4: Comprehensive Testing (6 hours)

### Priority 3: Complete Cache Module Coverage (2 hours)

#### Modules to Test:
1. **failure_tracker.py** (36.8% → 60%)
   - Exponential backoff logic (5min → 15min → 45min → 2hr)
   - Failure persistence
   - Recovery mechanisms

2. **memory_manager.py** (33.3% → 60%)
   - LRU eviction at 100MB limit
   - Memory tracking accuracy
   - Concurrent access safety

3. **threede_cache.py** (21.4% → 60%)
   - 3DE scene caching
   - TTL expiration (30 minutes)
   - Metadata support

4. **thumbnail_loader.py** (24.5% → 60%)
   - Async QRunnable loading
   - Signal emission
   - Error handling

### Priority 4: Command Launcher Tests (4 hours)
**Current**: 0% coverage (159 lines uncovered)
**Target**: 80% coverage

**Core Functions to Test**:
```python
class TestCommandLauncher:
    def test_launch_nuke_in_shot_context():
        # Test Nuke launch with shot variables
        
    def test_launch_with_plate_discovery():
        # Test plate path discovery
        
    def test_launch_with_undistortion():
        # Test undistortion file discovery
        
    def test_command_validation():
        # Test command sanitization
        
    def test_error_handling():
        # Test failure scenarios
```

**Critical Paths**:
- Shot context variable substitution
- Plate discovery and colorspace detection
- Undistortion file finding
- Terminal command execution
- Error signal emission

## Day 5: Finalization (3 hours)

### Priority 5: Centralize Magic Numbers (2 hours)

**Locations to Check**:
```python
# Current (scattered):
cache_manager.py:99: self._validation_interval_minutes = 30
shot_model_optimized.py:62: cache_ttl=300, timeout=30
utils.py:22: _PATH_CACHE_TTL = 300.0

# Target (centralized):
class CacheConfig:
    VALIDATION_INTERVAL_MINUTES = 30
    DEFAULT_TTL_SECONDS = 300
    PATH_CACHE_TTL_SECONDS = 300
```

**Files with Magic Numbers**:
- `cache_manager.py` - Cache intervals
- `utils.py` - Path cache TTL
- `shot_model_optimized.py` - Timeouts
- `debug_utils.py` - Debug thresholds
- `bundle_app.py` - File size limits

### Priority 6: Final Validation (1 hour)

**Validation Checklist**:
- [ ] Run full test suite: `pytest -xvs`
- [ ] Check coverage: `pytest --cov=. --cov-report=term-missing`
- [ ] Type check: `basedpyright .`
- [ ] Verify no runtime errors in main app
- [ ] Document remaining issues

## Success Metrics

### Test Coverage Targets
| Component | Current | Target | Priority |
|-----------|---------|--------|----------|
| Integration Tests | 5 failing | 100% pass | Critical |
| Cache Modules | ~30% avg | 60% min | High |
| Command Launcher | 0% | 80% | High |
| Overall Coverage | 9.8% | 40%+ | Medium |

### Type Safety Targets
| Metric | Current | Target |
|--------|---------|--------|
| Type Errors | 16 | <5 |
| Type Warnings | 84 | <20 |
| Unknown Types | Some | 0 |

## Risk Mitigation

### Known Risks
1. **Threading Issues**: Tests may timeout due to QThread cleanup
   - Mitigation: Mock thread operations, add proper cleanup

2. **Mock Complexity**: Complex Qt signal/slot mocking
   - Mitigation: Use test doubles instead of mocks where possible

3. **Time Constraints**: 15 hours of work in 2 days
   - Mitigation: Focus on critical paths, defer nice-to-haves

## Next Steps After Completion

1. **Performance Optimization** (Week 3)
   - Implement signal batching (40% overhead reduction)
   - Add lazy loading (<500ms startup target)
   - Lock-free queue communication

2. **Documentation**
   - Update README with test instructions
   - Document architectural decisions
   - Create developer onboarding guide

3. **CI/CD Integration**
   - Set up automated testing
   - Add type checking to CI
   - Coverage reporting

---

*This plan prioritizes test stability and validation over cleanup tasks. Magic number centralization is deferred to Day 5 since it doesn't block critical functionality. The focus is on achieving a stable, testable codebase with adequate coverage to validate the Week 2 changes.*