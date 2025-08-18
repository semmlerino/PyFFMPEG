# Test Suite Improvement Plan
*Achieving UNIFIED_TESTING_GUIDE Compliance*

## Executive Summary
Transform test suite from 7.6/10 to 9+/10 compliance by eliminating internal mocking, focusing on behavior testing, and using real components with test doubles only at system boundaries.

## Current State Analysis

### Strengths (Keep These)
- ✅ **Qt Threading Safety**: Perfect implementation with ThreadSafeTestImage
- ✅ **Signal Testing**: Proper QSignalSpy usage with real Qt widgets
- ✅ **Gold Standard Examples**: test_stop_after_first_no_mocks.py

### Critical Issues (Fix These)
- ❌ **Over-mocking**: 22 test files use Mock() excessively
- ❌ **Implementation Testing**: Tests verify method calls instead of outcomes
- ❌ **Internal Mocking**: PathUtils/FileUtils mocked instead of using real implementations

## Phase 1: Test Infrastructure (Day 1-2)

### Create `tests/unit/test_doubles.py`
```python
"""Reusable test doubles following UNIFIED_TESTING_GUIDE."""

class TestSignal:
    """Lightweight signal test double for non-Qt components."""
    def __init__(self):
        self.emissions = []
        self.callbacks = []
    
    def emit(self, *args):
        self.emissions.append(args)
        for callback in self.callbacks:
            callback(*args)
    
    def connect(self, callback):
        self.callbacks.append(callback)
    
    @property
    def was_emitted(self):
        return len(self.emissions) > 0

class TestProcessPool:
    """Test double for subprocess operations at system boundary."""
    def __init__(self):
        self.commands = []
        self.outputs = []
        self.should_fail = False
    
    def execute_workspace_command(self, command, **kwargs):
        self.commands.append(command)
        if self.should_fail:
            raise subprocess.CalledProcessError(1, command)
        return self.outputs.pop(0) if self.outputs else ""
    
    def set_outputs(self, *outputs):
        self.outputs = list(outputs)

class TestFileSystem:
    """In-memory filesystem for fast testing without I/O."""
    def __init__(self):
        self.files = {}
    
    def write_file(self, path, content):
        self.files[str(path)] = content
    
    def read_file(self, path):
        return self.files.get(str(path))
    
    def exists(self, path):
        return str(path) in self.files
```

### Update `tests/unit/conftest.py`
```python
@pytest.fixture
def real_cache_manager(tmp_path):
    """Real cache manager with temporary storage."""
    return CacheManager(cache_dir=tmp_path / "cache")

@pytest.fixture
def real_shot_model(tmp_path, real_cache_manager):
    """Real shot model with test doubles for external calls."""
    model = ShotModel(cache_manager=real_cache_manager)
    model._process_pool = TestProcessPool()
    return model

@pytest.fixture
def make_test_shot(tmp_path):
    """Factory for creating real shot objects with files."""
    def _make_shot(show="test", seq="seq01", shot="0010"):
        shot_path = tmp_path / "shows" / show / "shots" / seq / f"{seq}_{shot}"
        shot_path.mkdir(parents=True, exist_ok=True)
        
        # Create real thumbnail
        thumb_path = shot_path / "publish" / "editorial" / "thumbnail.jpg"
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        thumb_path.write_bytes(b"JPG_DATA")
        
        return Shot(show, seq, shot, str(shot_path))
    return _make_shot
```

## Phase 2: High-Priority Refactoring (Day 3-7)

### 1. Fix `test_shot_model.py` (42 tests)

**Before (Bad)**:
```python
@patch("utils.PathUtils.validate_path_exists")
@patch("utils.FileUtils.get_first_image_file")
def test_get_thumbnail_path(mock_get_first_image, mock_validate_path, sample_shot):
    mock_validate_path.return_value = True
    mock_get_first_image.return_value = Path("/path/to/thumbnail.jpg")
    thumbnail_path = sample_shot.get_thumbnail_path()
    mock_validate_path.assert_called_once()  # Implementation detail!
```

**After (Good)**:
```python
def test_get_thumbnail_path(make_test_shot):
    # Create real shot with real files
    shot = make_test_shot("myshow", "seq01", "0010")
    
    # Test actual behavior
    thumbnail_path = shot.get_thumbnail_path()
    assert thumbnail_path.exists()
    assert thumbnail_path.name == "thumbnail.jpg"
    
    # Test caching behavior
    thumbnail_path2 = shot.get_thumbnail_path()
    assert thumbnail_path2 == thumbnail_path  # Same cached result
```

### 2. Fix `test_shot_info_panel.py`

**Before (Bad)**:
```python
def test_update_shot_info(mock_cache_manager):
    panel = ShotInfoPanel(cache_manager=mock_cache_manager)
    mock_cache_manager.get_thumbnail.return_value = Mock()
```

**After (Good)**:
```python
def test_update_shot_info(qtbot, real_cache_manager, make_test_shot):
    # Real components
    panel = ShotInfoPanel(cache_manager=real_cache_manager)
    qtbot.addWidget(panel)
    
    # Real shot with real thumbnail
    shot = make_test_shot()
    
    # Test actual UI behavior
    panel.update_shot_info(shot)
    assert panel.shot_label.text() == "seq01_0010"
    assert not panel.thumbnail_label.pixmap().isNull()
```

### 3. Fix `test_threede_scene_model.py`

**Before (Bad)**:
```python
@patch.object(ThreeDESceneFinder, "find_all_scenes_in_shows_efficient")
def test_refresh(mock_find_scenes):
    mock_find_scenes.return_value = [mock_scene1, mock_scene2]
```

**After (Good)**:
```python
def test_refresh(tmp_path, real_cache_manager):
    # Create real 3DE files
    scene_path = tmp_path / "shows" / "test" / "shots" / "seq01" / "0010" / "user" / "artist" / "3de"
    scene_path.mkdir(parents=True, exist_ok=True)
    (scene_path / "scene.3de").write_text("3DE content")
    
    # Real model with real finder
    model = ThreeDESceneModel(cache_manager=real_cache_manager)
    
    # Test actual discovery
    result = model.refresh_scenes()
    assert result.success
    assert len(model.get_scenes()) == 1
    assert model.get_scenes()[0].file_path.name == "scene.3de"
```

## Phase 3: Medium-Priority Updates (Day 8-12)

### Files to Update
1. **test_raw_plate_finder.py** - Already good, minor tweaks
2. **test_launcher_manager.py** - Standardize TestProcessPool usage
3. **test_cache_manager.py** - Ensure all use real cache
4. **Integration tests** - Minimize mocking to subprocess only

### Pattern Application Checklist
- [ ] No @patch for internal utilities
- [ ] Real components with tmp_path
- [ ] Test doubles only at system boundaries
- [ ] Verify behavior, not method calls
- [ ] Use factory fixtures for consistency

## Phase 4: Validation & Metrics (Day 13-14)

### Success Criteria
| Metric | Current | Target |
|--------|---------|--------|
| Mock() usage | 200+ | < 40 |
| @patch decorators | 150+ | < 20 |
| Behavior tests | 60% | 100% |
| Test speed | 2+ min | < 60s |
| Compliance score | 7.6/10 | 9+/10 |

### Validation Steps
```bash
# 1. Run individual test files
python run_tests.py tests/unit/test_shot_model.py

# 2. Check for remaining mocks
grep -r "Mock()" tests/unit/*.py | wc -l

# 3. Verify no internal patches
grep -r "@patch.*PathUtils" tests/unit/*.py

# 4. Run full suite
python run_tests.py --cov

# 5. Measure compliance
python evaluate_test_compliance.py
```

## Implementation Priority

### Week 1: Foundation
1. Create test_doubles.py
2. Update conftest.py with fixtures
3. Refactor test_shot_model.py (highest impact)

### Week 2: Core Components
1. Fix test_shot_info_panel.py
2. Fix test_threede_scene_model.py
3. Update test_raw_plate_finder.py

### Week 3: Polish
1. Standardize remaining tests
2. Update integration tests
3. Documentation

### Week 4: Validation
1. Full test suite validation
2. Performance testing
3. Compliance measurement

## Example Transformations

### From Mock to Real
```python
# ❌ OLD WAY
mock_shot = Mock()
mock_shot.get_thumbnail_path.return_value = "/fake/path"

# ✅ NEW WAY
shot = make_test_shot()  # Real shot with real files
```

### From Implementation to Behavior
```python
# ❌ OLD WAY
mock_refresh.assert_called_with("arg")

# ✅ NEW WAY
result = model.refresh()
assert result.success
assert model.state == expected_state
```

### From Patch to Test Double
```python
# ❌ OLD WAY
@patch("subprocess.run")
def test_something(mock_run):
    mock_run.return_value.stdout = "output"

# ✅ NEW WAY
def test_something():
    model._process_pool = TestProcessPool()
    model._process_pool.set_outputs("output")
```

## Risk Mitigation

1. **Gradual Migration**: Fix one file at a time
2. **Maintain Coverage**: Ensure no test coverage loss
3. **Parallel Development**: Keep old tests until new ones proven
4. **Review Process**: Each refactored file reviewed before merge

## Expected Outcomes

- **60% faster test execution** (less mocking overhead)
- **200% better bug discovery** (real integration testing)
- **75% less maintenance** (fewer mock updates)
- **100% behavior coverage** (what users experience)

## Conclusion

This plan transforms our test suite from "mock-heavy implementation testing" to "real component behavior testing" following UNIFIED_TESTING_GUIDE best practices. The investment will pay dividends in:

1. **Reliability**: Tests catch real bugs, not mock misconfigurations
2. **Speed**: Less overhead from excessive mocking
3. **Maintainability**: Tests survive refactoring
4. **Confidence**: Tests validate actual user experience

Start with Phase 1 infrastructure, then systematically refactor starting with highest-impact files. Measure progress weekly and adjust as needed.