# Immediate Coverage Improvement Plan

## Quick Start (30 Minutes)

### Step 1: Fix Test Infrastructure
```bash
# Activate environment
source venv/bin/activate

# Install missing test dependencies
pip install pytest-qt hypothesis pytest-benchmark pytest-timeout mutmut

# Fix pytest configuration
cp pytest.ini pytest.ini.backup
```

Edit `pytest.ini`:
```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = 
    -v
    --strict-markers
    --tb=short
    # Remove: -p no:pytestqt  <-- DELETE THIS LINE
    # Remove: -p no:xdist     <-- DELETE THIS LINE
markers =
    unit: Unit tests
    integration: Integration tests
    slow: Slow running tests
    gui: GUI tests requiring display
    performance: Performance regression tests
    real: Tests using real components (no mocking)
    edge_cases: Edge case and boundary tests
```

### Step 2: Baseline Coverage Check
```bash
# Run current tests to establish baseline
python run_tests.py --cov --cov-report=html --cov-report=term-missing

# Check baseline - should show ~5%
echo "Baseline coverage established in htmlcov/index.html"
```

### Step 3: Identify Quick Wins
```bash
# Test individual modules to find coverage gaps
python run_tests.py tests/unit/test_shot_model.py --cov=shot_model --cov-report=term-missing
python run_tests.py tests/unit/test_cache_manager.py --cov=cache_manager --cov-report=term-missing
python run_tests.py tests/unit/test_launcher_manager.py --cov=launcher_manager --cov-report=term-missing
```

## Day 1: Fix Critical Over-Mocking (2 Hours)

### Priority 1: shot_model.py (24% → 70%)

Create `tests/unit/test_shot_model_improved.py`:
```python
"""Improved shot_model tests with minimal mocking."""

import pytest
from pathlib import Path
from unittest.mock import patch
from shot_model import ShotModel, Shot, RefreshResult

class TestShotModelImproved:
    """Tests using real components where possible."""
    
    @pytest.fixture
    def real_shot_model(self, cache_manager):
        """ShotModel with real cache, only mocking external commands."""
        return ShotModel(cache_manager=cache_manager, load_cache=False)
    
    def test_refresh_shots_real_parsing(self, real_shot_model):
        """Test with real workspace parsing - no parser mocking."""
        # Only mock the external command, not the parsing logic
        mock_output = '''workspace /shows/test1/shots/seq1/seq1_0010
workspace /shows/test2/shots/seq2/seq2_0020
workspace /shows/test3/shots/seq3/seq3_0030'''
        
        with patch.object(real_shot_model._process_pool, 'execute_workspace_command', return_value=mock_output):
            result = real_shot_model.refresh_shots()
            
            # Test real parsing logic execution
            assert isinstance(result, RefreshResult)
            assert result.success is True
            assert len(real_shot_model.shots) == 3
            
            # Verify real Shot objects created
            shot = real_shot_model.shots[0]
            assert shot.show == "test1"
            assert shot.sequence == "seq1"
            assert shot.shot == "0010"
    
    def test_error_handling_real_errors(self, real_shot_model):
        """Test with real error scenarios."""
        with patch.object(real_shot_model._process_pool, 'execute_workspace_command', side_effect=TimeoutError("Real timeout")):
            result = real_shot_model.refresh_shots()
            
            assert result.success is False
            assert result.has_changes is False
    
    def test_cache_integration_real_persistence(self, real_shot_model, tmp_path):
        """Test cache with real file operations."""
        shots = [Shot("test", "seq", "0010", "/path")]
        real_shot_model.cache_manager.cache_shots(shots)
        
        # Verify real cache file created
        cache_file = real_shot_model.cache_manager.shots_cache_file
        assert cache_file.exists()
        
        # Test real cache loading
        cached = real_shot_model.cache_manager.get_cached_shots()
        assert len(cached) == 1
        assert cached[0]["show"] == "test"
```

Run improved test:
```bash
python run_tests.py tests/unit/test_shot_model_improved.py --cov=shot_model --cov-report=term-missing
# Expected: 50-70% coverage (significant improvement)
```

### Priority 2: Enable GUI Testing

Create `tests/unit/test_main_window_basic.py`:
```python
"""Basic MainWindow tests with Qt integration."""

import pytest
from PySide6.QtWidgets import QApplication
from main_window import MainWindow

class TestMainWindowBasic:
    """Basic MainWindow functionality tests."""
    
    def test_main_window_initialization(self, qtbot, cache_manager):
        """Test MainWindow initializes without crashes."""
        window = MainWindow(cache_manager=cache_manager)
        qtbot.addWidget(window)
        
        # Basic widget structure tests
        assert window.shot_grid is not None
        assert window.threede_shot_grid is not None
        assert window.shot_info_panel is not None
    
    def test_shot_refresh_workflow(self, qtbot, cache_manager):
        """Test shot refresh workflow integration."""
        window = MainWindow(cache_manager=cache_manager)
        qtbot.addWidget(window)
        
        # Mock only external workspace command
        with patch.object(window.shot_model._process_pool, 'execute_workspace_command', return_value="workspace /test/shot"):
            # Trigger refresh through UI
            window.refresh_shots()
            
            # Wait for async operations
            qtbot.waitUntil(lambda: len(window.shot_model.shots) > 0, timeout=1000)
            
            assert len(window.shot_model.shots) == 1
```

Run GUI test:
```bash
python run_tests.py tests/unit/test_main_window_basic.py -v
# Should pass if Qt testing is enabled
```

## Week 1: Core Module Coverage (10-15 Hours)

### Day 2-3: process_pool_manager.py (0% → 60%)

Create `tests/unit/test_process_pool_real.py`:
```python
"""ProcessPoolManager tests with real subprocess operations."""

import pytest
import subprocess
from process_pool_manager import ProcessPoolManager, PersistentBashSession

class TestProcessPoolReal:
    """Test ProcessPool with real subprocess operations."""
    
    def test_persistent_bash_session_real_commands(self):
        """Test bash session with real, safe commands."""
        session = PersistentBashSession()
        
        # Test real command execution
        result = session.execute_command("echo 'test output'")
        assert "test output" in result
        
        # Test command caching
        result2 = session.execute_command("echo 'test output'")
        assert result2 == result  # Should be cached
        
        session.close()
    
    def test_workspace_command_integration(self):
        """Test workspace command integration with real environment."""
        pool = ProcessPoolManager.get_instance()
        
        # Use safe test command instead of real 'ws -sg'
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.stdout = "workspace /test/path"
            mock_run.return_value.returncode = 0
            
            result = pool.execute_workspace_command()
            assert "workspace" in result
    
    def test_timeout_handling_real_timeout(self):
        """Test timeout with real subprocess timeout."""
        session = PersistentBashSession()
        
        # Use sleep command to test real timeout
        with pytest.raises(subprocess.TimeoutExpired):
            session.execute_command("sleep 5", timeout=1)
        
        session.close()
```

### Day 4-5: threede_scene_finder.py (0% → 70%)

Create `tests/unit/test_threede_scene_finder_real.py`:
```python
"""ThreeDE scene finder tests with real filesystem."""

import pytest
from pathlib import Path
from threede_scene_finder import ThreeDESceneFinder

class TestThreeDESceneFinderReal:
    """Test 3DE scene discovery with real filesystem."""
    
    def test_scene_discovery_real_filesystem(self, tmp_path):
        """Test scene discovery with real directory structure."""
        # Create realistic 3DE scene structure
        user_dir = tmp_path / "users" / "testuser"
        project_dir = user_dir / "projects" / "testproject"
        project_dir.mkdir(parents=True)
        
        # Create 3DE scene files
        scene1 = project_dir / "shot_001.3de"
        scene2 = project_dir / "shot_002.3de"
        scene1.write_text("3DE scene data")
        scene2.write_text("3DE scene data")
        
        finder = ThreeDESceneFinder()
        
        # Test real directory scanning
        scenes = finder.find_scenes_in_directory(user_dir)
        
        assert len(scenes) == 2
        assert any("shot_001.3de" in str(scene) for scene in scenes)
        assert any("shot_002.3de" in str(scene) for scene in scenes)
    
    def test_plate_name_extraction_realistic(self, tmp_path):
        """Test plate name extraction with realistic VFX paths."""
        # Realistic VFX directory structure
        scene_paths = [
            tmp_path / "projects" / "film_project" / "sequences" / "seq010" / "shot_0010" / "matchmove" / "seq010_0010_v003.3de",
            tmp_path / "projects" / "film_project" / "shots" / "BG01" / "seq020_0020_BG01_v001.3de",
            tmp_path / "work" / "current" / "simple_scene.3de"
        ]
        
        finder = ThreeDESceneFinder()
        
        for scene_path in scene_paths:
            scene_path.parent.mkdir(parents=True)
            scene_path.write_text("3DE scene")
            
            # Test real plate extraction logic
            plate_name = finder.extract_plate_name(scene_path)
            
            # Should extract meaningful plate names
            assert plate_name is not None
            assert len(plate_name) > 0
```

## Performance & Memory Testing

### Add Performance Benchmarks
Create `tests/performance/test_cache_performance.py`:
```python
"""Performance tests for cache operations."""

import pytest
from cache_manager import CacheManager
from shot_model import Shot

class TestCachePerformance:
    """Performance benchmarks for cache operations."""
    
    def test_large_shot_list_caching(self, benchmark, tmp_path):
        """Benchmark caching large shot lists."""
        cache_manager = CacheManager(cache_dir=tmp_path)
        
        # Generate large shot list (realistic VFX production size)
        large_shot_list = [
            Shot(f"show_{i//100}", f"seq_{i//10}", f"shot_{i}", f"/path/{i}")
            for i in range(1000)
        ]
        
        # Benchmark cache operation
        result = benchmark(cache_manager.cache_shots, large_shot_list)
        
        # Verify performance requirements
        assert len(cache_manager.get_cached_shots()) == 1000
    
    def test_thumbnail_cache_memory_usage(self, cache_manager, tmp_path):
        """Test thumbnail cache memory management."""
        # Create multiple test images
        for i in range(50):
            image_file = tmp_path / f"thumb_{i}.jpg"
            image_file.write_bytes(b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9')
            
            shot = Shot("test", "seq", f"shot_{i}", "/path")
            cache_manager.cache_thumbnail(shot, image_file)
        
        # Verify memory usage is reasonable
        memory_usage = cache_manager.get_memory_usage()
        assert memory_usage < 50 * 1024 * 1024  # Under 50MB for 50 thumbnails
```

Run performance tests:
```bash
python run_tests.py tests/performance/ --benchmark-only
```

## Monitoring & CI Integration

### Add Coverage Monitoring
Create `scripts/check_coverage.sh`:
```bash
#!/bin/bash
set -e

echo "Running comprehensive coverage check..."

# Activate environment
source venv/bin/activate

# Run tests with coverage
python run_tests.py --cov --cov-report=term-missing --cov-report=html --cov-fail-under=60

# Generate coverage badge
coverage-badge -o coverage_badge.svg

# Check for coverage regressions
echo "Coverage check complete. Report available in htmlcov/index.html"

# Run mutation testing for test quality
echo "Running mutation testing for test quality..."
mutmut run --paths-to-mutate=shot_model.py,cache_manager.py --tests-dir=tests/

echo "Test quality check complete."
```

### Add to CI/CD Pipeline
Create `.github/workflows/coverage.yml` (if using GitHub):
```yaml
name: Coverage Check
on: [push, pull_request]

jobs:
  coverage:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v2
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: 3.12
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        pip install -r requirements-dev.txt
    
    - name: Run tests with coverage
      run: |
        python run_tests.py --cov --cov-report=xml --cov-fail-under=80
    
    - name: Upload coverage to Codecov
      uses: codecov/codecov-action@v1
```

## Expected Results

### Week 1 Targets:
- **shot_model.py**: 24% → 70% (+46%)
- **cache_manager.py**: 31% → 65% (+34%)
- **main_window.py**: 0% → 40% (+40%)
- **process_pool_manager.py**: 0% → 60% (+60%)
- **Overall**: 5% → 35% (+30%)

### Week 2 Targets:
- **threede_scene_finder.py**: 0% → 70% (+70%)
- **command_launcher.py**: 0% → 60% (+60%)
- **nuke_script_generator.py**: 0% → 55% (+55%)
- **Overall**: 35% → 55% (+20%)

### Success Metrics:
```bash
# Daily coverage check
python run_tests.py --cov --cov-report=term-missing | grep "TOTAL"
# Target: TOTAL coverage increasing by 5-10% daily

# Test execution speed
time python run_tests.py
# Target: Under 2 minutes for full suite

# Test stability
python run_tests.py --count=3
# Target: No flaky test failures
```

This plan provides immediate, actionable steps to dramatically improve test coverage while maintaining the real-world testing philosophy essential for VFX pipeline software reliability.