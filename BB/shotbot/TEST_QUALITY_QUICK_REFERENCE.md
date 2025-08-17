# Test Quality Quick Reference Card

## 🎯 Testing Philosophy: Real Components First

### ✅ DO: Use Real Components
```python
# ✅ GOOD: Real filesystem operations
def test_thumbnail_discovery(tmp_path):
    shot_dir = tmp_path / "show" / "seq" / "shot"
    shot_dir.mkdir(parents=True)
    
    thumb_file = shot_dir / "publish" / "editorial" / "frame.1001.jpg"
    thumb_file.write_bytes(VALID_JPEG_BYTES)
    
    shot = Shot("show", "seq", "shot", str(shot_dir))
    result = shot.get_thumbnail_path()  # Real discovery logic
    
    assert result == thumb_file

# ✅ GOOD: Real Qt widgets and signals
def test_shot_grid_selection(qtbot):
    grid = ShotGrid()  # Real Qt widget
    qtbot.addWidget(grid)
    
    with qtbot.waitSignal(grid.shot_selected):
        grid.select_shot_by_index(0)  # Real user interaction
```

### ❌ DON'T: Over-Mock Business Logic
```python
# ❌ BAD: Mocking core business logic
@patch('shot_model.Shot')
@patch('utils.PathUtils.validate_path_exists')
@patch('utils.FileUtils.get_first_image_file')
def test_shot_parsing(mock_file, mock_path, mock_shot):
    # This tests mocks, not real code!
    pass

# ❌ BAD: Mocking Qt components
@patch('PySide6.QtWidgets.QWidget')
def test_ui_component():
    # This doesn't test real Qt behavior!
    pass
```

## 🚀 Quick Coverage Boosters

### 1. Replace Mock with Real Test Data
```python
# Before: 0% coverage (mocked away)
@patch('process_pool_manager.ProcessPoolManager.execute_workspace_command')
def test_refresh_shots(mock_execute):
    mock_execute.return_value = "mocked output"

# After: 70%+ coverage (real parsing tested)
def test_refresh_shots_real_parsing(real_shot_model):
    test_workspace_output = """workspace /shows/test1/shots/seq1/seq1_0010
workspace /shows/test2/shots/seq2/seq2_0020"""
    
    with patch.object(real_shot_model._process_pool, 'execute_workspace_command', return_value=test_workspace_output):
        result = real_shot_model.refresh_shots()  # Real parsing logic executed
        assert len(real_shot_model.shots) == 2
```

### 2. Test Error Paths with Real Errors
```python
# ✅ GOOD: Real error scenarios
def test_timeout_handling():
    with patch.object(session, 'execute_command', side_effect=TimeoutError("Real timeout")):
        result = shot_model.refresh_shots()
        assert result.success is False  # Real error handling tested

# ✅ GOOD: Real filesystem errors
def test_cache_disk_full(tmp_path):
    # Fill up disk space (in test environment)
    cache_manager = CacheManager(cache_dir=tmp_path)
    
    with patch('pathlib.Path.write_text', side_effect=OSError("No space left")):
        result = cache_manager.cache_shots(large_shot_list)
        # Test real error recovery
```

### 3. Use Real Qt Components
```python
# ✅ GOOD: Real Qt testing
def test_main_window_workflow(qtbot, cache_manager):
    window = MainWindow(cache_manager=cache_manager)  # Real MainWindow
    qtbot.addWidget(window)
    
    # Test real signal connections
    with qtbot.waitSignal(window.shot_model.shots_updated):
        window.refresh_shots()
    
    # Test real UI state
    assert window.shot_grid.rowCount() > 0
```

## 🎯 Coverage Target Priorities

### Phase 1: Core Business Logic (80%+ each)
1. **shot_model.py** - Shot parsing and caching
2. **process_pool_manager.py** - Subprocess management
3. **cache_manager.py** - Data persistence

### Phase 2: VFX Workflows (70%+ each)
4. **threede_scene_finder.py** - Scene discovery
5. **nuke_script_generator.py** - Script generation
6. **raw_plate_finder.py** - Plate discovery

### Phase 3: UI Components (60%+ each)
7. **main_window.py** - Application integration
8. **shot_grid.py** - Grid widgets
9. **launcher_manager.py** - Application launching

## 🔧 Quick Test Creation Templates

### Basic Test Structure
```python
"""Test {MODULE_NAME} with real components."""

import pytest
from pathlib import Path
from {MODULE_NAME} import {CLASS_NAME}

class Test{CLASS_NAME}:
    """Test {CLASS_NAME} functionality with minimal mocking."""
    
    def test_{method}_happy_path(self, tmp_path):
        """Test normal operation with real filesystem."""
        # Arrange: Create real test data
        # Act: Execute real business logic
        # Assert: Verify real results
        
    def test_{method}_error_handling(self):
        """Test error conditions with real error scenarios."""
        
    def test_{method}_edge_cases(self):
        """Test boundary conditions."""
        
    def test_{method}_performance(self, benchmark):
        """Test performance with realistic data sizes."""
```

### Qt Component Test Template
```python
def test_qt_component(qtbot, cache_manager):
    """Test Qt component with real widgets."""
    widget = SomeQtWidget(cache_manager=cache_manager)
    qtbot.addWidget(widget)
    
    # Test real user interactions
    qtbot.mouseClick(widget.refresh_button, Qt.LeftButton)
    
    # Test real signal emissions
    with qtbot.waitSignal(widget.data_updated):
        widget.load_data()
    
    # Test real state changes
    assert widget.isVisible()
```

### Filesystem Test Template
```python
def test_filesystem_operation(tmp_path):
    """Test with real filesystem operations."""
    # Create realistic directory structure
    test_dir = tmp_path / "realistic" / "vfx" / "structure"
    test_dir.mkdir(parents=True)
    
    # Create real test files
    test_file = test_dir / "test.3de"
    test_file.write_text("real test data")
    
    # Test real file operations
    result = finder.find_files(test_dir)
    assert test_file in result
```

## 🚨 Anti-Patterns to Avoid

### ❌ Don't Mock What You Should Test
```python
# ❌ BAD: Mocking the code under test
@patch('shot_model.ShotModel.refresh_shots')
def test_shot_refresh(mock_refresh):
    mock_refresh.return_value = True
    # This tests nothing!

# ✅ GOOD: Test the real method
def test_shot_refresh_real():
    result = shot_model.refresh_shots()
    assert isinstance(result, RefreshResult)
```

### ❌ Don't Use Magic Mock for Complex Objects
```python
# ❌ BAD: Magic mock for Qt widgets
mock_widget = MagicMock()
mock_widget.isVisible.return_value = True

# ✅ GOOD: Real Qt widget
widget = QWidget()
qtbot.addWidget(widget)
widget.show()
assert widget.isVisible()
```

### ❌ Don't Skip Integration Tests
```python
# ❌ BAD: Only unit tests with mocks
def test_shot_model_alone():
    # Tests shot model in isolation
    
# ✅ GOOD: Integration test with real components
def test_shot_workflow_integration():
    # Tests shot_model + cache_manager + ui together
```

## 🎯 Coverage Commands

### Daily Coverage Check
```bash
# Quick module coverage
python run_tests.py tests/unit/test_shot_model.py --cov=shot_model --cov-report=term-missing

# Full coverage report
python run_tests.py --cov --cov-report=html

# Coverage with performance
python run_tests.py --cov --benchmark-only
```

### Coverage Quality Check
```bash
# Mutation testing (test effectiveness)
mutmut run --paths-to-mutate=shot_model.py

# Property-based testing
python run_tests.py -m hypothesis

# Performance regression testing
python run_tests.py tests/performance/
```

## 🏆 Success Metrics

### Code Coverage Targets
- **Critical modules**: 80%+ each
- **VFX workflows**: 70%+ each  
- **UI components**: 60%+ each
- **Overall project**: 80%+

### Quality Metrics
- **Test execution**: <2 minutes full suite
- **Flaky tests**: <2% failure rate
- **Mutation score**: 70%+ (test effectiveness)
- **Memory leaks**: 0 in thumbnail operations

### Weekly Goals
- **Week 1**: 5% → 35% (+30%)
- **Week 2**: 35% → 55% (+20%)
- **Week 3**: 55% → 70% (+15%)
- **Week 4**: 70% → 80% (+10%)

## 🛠️ Emergency Coverage Fixes

### "My Test Isn't Covering Code" Checklist
1. ✅ Are you mocking the code under test?
2. ✅ Is the mock preventing real execution?
3. ✅ Are you testing the interface, not implementation?
4. ✅ Is the test actually calling the target method?
5. ✅ Are exceptions being swallowed?

### "My Test Is Flaky" Checklist
1. ✅ Using `qtbot.waitSignal()` for async operations?
2. ✅ Using `tmp_path` for filesystem operations?
3. ✅ Cleaning up Qt widgets with `qtbot.addWidget()`?
4. ✅ Avoiding `time.sleep()` in tests?
5. ✅ Using deterministic test data?

### "My Test Is Slow" Checklist
1. ✅ Using small, focused test data?
2. ✅ Avoiding real network calls?
3. ✅ Using `tmp_path` instead of system paths?
4. ✅ Mocking only external dependencies?
5. ✅ Running expensive operations once per test class?

Remember: **Test behavior, not implementation. Use real components, mock only boundaries.**