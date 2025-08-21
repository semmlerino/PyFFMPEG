# Test Suite Improvement Plan

## Executive Summary
The test suite requires significant improvements to align with UNIFIED_TESTING_GUIDE best practices. Key issues: 158 mock/patch instances (should be <20), test timeouts, and implementation testing.

## Priority 1: Fix Test Timeouts (BLOCKING)
- [ ] Identify hanging tests using pytest --timeout-method=thread
- [ ] Add proper test timeouts (60s max)
- [ ] Fix or skip problematic tests temporarily

## Priority 2: Reduce Mocking (158 → <20)

### test_command_launcher.py (25+ violations)
Replace subprocess mocking with TestProcessPool:
```python
# ❌ BEFORE
with patch("subprocess.Popen") as mock_popen:
    mock_popen.return_value = Mock(returncode=0)
    
# ✅ AFTER  
launcher._subprocess = TestSubprocess()
launcher._subprocess.set_success("command output")
```

### test_cache_manager.py (10+ violations)
Use real cache with temp directories:
```python
# ❌ BEFORE
with patch("cache.storage_backend.Path.exists"):
    
# ✅ AFTER
cache = CacheManager(tmp_path)  # Real cache, temp storage
```

## Priority 3: Test Behavior, Not Implementation

### Pattern to Fix
```python
# ❌ BAD - Implementation testing
assert mock.called
assert obj._private_attr == value
mock.assert_called_with(args)

# ✅ GOOD - Behavior testing  
assert obj.get_result() == expected
assert len(obj.items) == 3
assert obj.is_valid()
```

### Files to Refactor
1. test_command_launcher.py - 25+ assert_called patterns
2. test_previous_shots_worker.py - 15+ mock assertions
3. test_utils_extended.py - 16+ patches

## Priority 4: Add Qt Widget Tests

Create dedicated widget tests with qtbot:
```python
def test_shot_grid_selection(qtbot):
    grid = ShotGrid()
    qtbot.addWidget(grid)
    
    # Test real widget behavior
    grid.add_shot(TestShot())
    qtbot.mouseClick(grid.item(0), Qt.LeftButton)
    
    assert grid.current_shot is not None
```

## Priority 5: Performance Benchmarks

Add benchmark tests:
```python
@pytest.mark.benchmark
def test_cache_performance(benchmark):
    cache = CacheManager(tmp_path)
    result = benchmark(cache.cache_thumbnail, path, show, seq, shot)
    assert benchmark.stats['mean'] < 0.1  # 100ms target
```

## Metrics for Success

| Metric | Current | Target | 
|--------|---------|--------|
| Mock/Patch Usage | 158 | <20 |
| Test Runtime | Timeout | <60s |
| Implementation Tests | ~40 | 0 |
| Qt Widget Coverage | 30% | 80% |
| Performance Tests | 0 | 10+ |

## Implementation Timeline

### Week 1: Fix Blockers
- Fix test timeouts
- Create test doubles for subprocess

### Week 2: Reduce Mocking
- Refactor test_command_launcher.py
- Refactor test_cache_manager.py
- Update other high-violation files

### Week 3: Behavior Testing
- Replace assert_called patterns
- Remove private attribute testing
- Add real integration tests

### Week 4: Enhance Coverage
- Add Qt widget tests
- Add performance benchmarks
- Create E2E test suite

## Test Double Patterns to Use

### TestProcessPool (subprocess boundary)
```python
pool = TestProcessPool()
pool.set_outputs("workspace /path")
model._process_pool = pool
```

### ThreadSafeTestImage (threading safety)
```python
image = ThreadSafeTestImage(100, 100)
# Safe in any thread, uses QImage internally
```

### TestSignal (non-Qt signals)
```python
signal = TestSignal()
signal.connect(callback)
assert signal.was_emitted
```

## Anti-Patterns to Remove

1. **Mock Everything**: Replace with real components
2. **Patch Internal Methods**: Use test doubles at boundaries
3. **Test Private Attributes**: Test public behavior
4. **Assert Called**: Test actual outcomes
5. **Complex Fixtures**: Use simple setup/teardown

## Expected Outcomes

- **60% faster tests** (no subprocess overhead)
- **75% less maintenance** (fewer mock updates)  
- **200% better bug discovery** (real integration)
- **Zero threading crashes** (proper QImage usage)
- **Reliable CI/CD** (no timeouts)

## Verification Checklist

- [ ] All tests pass within 60 seconds
- [ ] Mock usage reduced to system boundaries only
- [ ] No implementation testing patterns
- [ ] Qt widgets tested with qtbot
- [ ] Performance benchmarks in place
- [ ] Zero QPixmap threading violations
- [ ] Signal race conditions eliminated
- [ ] Worker threads properly cleaned up

---
Generated: 2025-01-21 | Priority: CRITICAL