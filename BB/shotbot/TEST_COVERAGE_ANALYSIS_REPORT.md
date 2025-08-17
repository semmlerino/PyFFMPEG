# ShotBot Test Coverage Analysis & Improvement Plan

## Executive Summary

**Current Status**: 5% overall test coverage (critically low for production VFX software)  
**Target**: 80%+ coverage with high-quality tests  
**Primary Issues**: Over-mocking, disabled GUI testing, missing integration tests  

## Current Coverage Analysis

### Coverage by Module (Critical Modules Only)

| Module | Statements | Coverage | Status | Priority |
|--------|-----------|----------|--------|----------|
| **utils.py** | 363 | 94% ✅ | Excellent | Maintain |
| **config.py** | 95 | 100% ✅ | Perfect | Maintain |
| **launcher_manager.py** | 817 | 51% ⚠️ | Medium | Improve to 80% |
| **cache_manager.py** | 500 | 31% ⚠️ | Low | Improve to 85% |
| **shot_model.py** | 179 | 24% ❌ | Critical | Improve to 90% |
| **main_window.py** | 608 | 0% ❌ | Critical | Test core workflows |
| **process_pool_manager.py** | 581 | 0% ❌ | Critical | Test subprocess logic |
| **threede_scene_finder.py** | 704 | 0% ❌ | Critical | Test discovery logic |
| **command_launcher.py** | 159 | 0% ❌ | High | Test launching logic |
| **nuke_script_generator.py** | 187 | 0% ❌ | High | Test VFX workflows |
| **shot_grid.py** | 177 | 0% ❌ | High | Test UI components |
| **raw_plate_finder.py** | 109 | 0% ❌ | Medium | Test file discovery |
| **undistortion_finder.py** | 70 | 0% ❌ | Medium | Test VFX tools |

### Overall Statistics
- **Total Statements**: 14,414
- **Covered Statements**: 712 (5%)
- **Missing Coverage**: 13,702 statements
- **Critical Modules Untested**: 9 core modules (0% coverage)

## Critical Issues Identified

### 1. Over-Mocking Anti-Pattern

**Problem**: Tests heavily mock dependencies, preventing real business logic execution.

**Evidence**:
```python
# Current problematic pattern in shot_model tests
@patch('process_pool_manager.ProcessPoolManager.execute_workspace_command')
def test_refresh_shots_success(self, mock_execute, shot_model):
    mock_execute.return_value = "workspace /shows/test/shots/seq1/seq1_0010\n"
    # This mocks the ENTIRE subprocess execution!
```

**Impact**: Real workspace parsing, error handling, and subprocess management never tested.

### 2. Disabled Qt Testing

**Problem**: pytest-qt plugin disabled, preventing GUI component testing.

**Evidence**:
```ini
# pytest.ini
addopts = -p no:pytestqt  # Disables Qt testing!
```

**Impact**: 608 lines in main_window.py completely untested.

### 3. Missing Integration Tests

**Problem**: Core VFX workflows not tested end-to-end.

**Missing Workflows**:
- Shot discovery → thumbnail loading → application launching
- 3DE scene finding → scene opening → workspace context
- Cache invalidation → refresh → UI updates
- Error recovery → user notification → fallback handling

### 4. Flaky Test Infrastructure

**Evidence**: Multiple tests marked as skipped due to instability:
```python
@pytest.mark.skip("Flaky due to Qt threading")
def test_concurrent_launcher_execution_real_workers(self):
```

### 5. Missing Edge Case Coverage

**Uncovered Scenarios**:
- Disk full during cache operations
- Network timeouts during workspace commands
- Corrupted 3DE files during discovery
- Race conditions in multi-threaded operations
- Memory pressure during thumbnail loading

## Specific Recommendations for 80%+ Coverage

### Phase 1: Fix Test Infrastructure (Week 1)

#### Enable Real Qt Testing
```bash
# 1. Re-enable pytest-qt
pip install pytest-qt
# 2. Update pytest.ini to remove -p no:pytestqt
# 3. Add proper Qt application fixture
```

#### Reduce Over-Mocking
Replace subprocess mocks with real test commands:
```python
# Instead of mocking ProcessPoolManager
def test_shot_model_real_workspace_parsing(tmp_path):
    # Create mock workspace structure
    mock_workspace = tmp_path / "workspace"
    mock_workspace.mkdir()
    
    # Use real ProcessPoolManager with test data
    shot_model = ShotModel()
    result = shot_model.refresh_shots()
    
    # Test real parsing logic
    assert result.success
```

### Phase 2: Core Module Testing (Week 2)

#### Priority 1: shot_model.py (24% → 90%)

**Missing Critical Paths**:
- Lines 229-304: refresh_shots() core logic
- Lines 318-380: workspace output parsing  
- Lines 183-206: ShotModel initialization

**Recommended Tests**:
```python
def test_shot_model_workspace_parsing_real_output():
    """Test parsing with real workspace command output."""
    
def test_shot_model_error_recovery_timeout():
    """Test timeout handling in subprocess calls."""
    
def test_shot_model_change_detection_logic():
    """Test shot list change detection algorithm."""
```

#### Priority 2: process_pool_manager.py (0% → 85%)

**Test Strategy**: Use real subprocess calls with test commands
```python
def test_process_pool_real_bash_session():
    """Test persistent bash session with real commands."""
    
def test_process_pool_caching_behavior():
    """Test command output caching with real data."""
    
def test_process_pool_timeout_handling():
    """Test subprocess timeout enforcement."""
```

#### Priority 3: main_window.py (0% → 70%)

**Test Strategy**: Focus on core workflows, not UI pixels
```python
def test_main_window_shot_refresh_workflow(qtbot):
    """Test shot refresh workflow integration."""
    
def test_main_window_launcher_execution_flow(qtbot):
    """Test application launching workflow."""
    
def test_main_window_settings_persistence(qtbot):
    """Test UI state persistence across sessions."""
```

### Phase 3: VFX Workflow Testing (Week 3)

#### threede_scene_finder.py (0% → 85%)
```python
def test_scene_discovery_real_filesystem(tmp_path):
    """Test 3DE scene discovery with real file structure."""

def test_plate_extraction_various_naming_conventions():
    """Test plate name extraction robustness."""

def test_performance_with_large_directory_trees():
    """Test performance with realistic VFX directory sizes."""
```

#### nuke_script_generator.py (0% → 80%)
```python
def test_nuke_script_generation_real_templates():
    """Test Nuke script generation with real templates."""

def test_colorspace_handling_edge_cases():
    """Test colorspace detection and quoting."""

def test_script_validation_against_nuke_parser():
    """Validate generated scripts can be parsed by Nuke."""
```

### Phase 4: Performance & Edge Cases (Week 4)

#### Memory Management Testing
```python
def test_cache_manager_memory_pressure():
    """Test cache behavior under memory pressure."""

def test_thumbnail_loading_memory_leaks():
    """Test QPixmap cleanup prevents memory leaks."""
```

#### Error Handling Testing  
```python
def test_disk_full_error_recovery():
    """Test graceful handling of disk full conditions."""

def test_network_timeout_fallback_behavior():
    """Test fallback when workspace commands timeout."""

def test_corrupted_cache_file_recovery():
    """Test recovery from corrupted cache files."""
```

### Phase 5: Property-Based & Stress Testing (Week 5)

#### Add Hypothesis for Robust Testing
```python
from hypothesis import given, strategies as st

@given(st.text(min_size=1))
def test_shot_parsing_arbitrary_workspace_paths(workspace_path):
    """Test shot parsing with arbitrary workspace paths."""

@given(st.lists(st.text(), min_size=1, max_size=100))
def test_cache_manager_arbitrary_shot_lists(shot_names):
    """Test cache with arbitrary shot name lists."""
```

## Expected Coverage Targets by Phase

| Phase | Target Coverage | Key Modules | Duration |
|-------|----------------|-------------|----------|
| Phase 1 | 15% | Infrastructure fixes | 1 week |
| Phase 2 | 45% | Core modules (shot_model, process_pool) | 1 week |
| Phase 3 | 65% | VFX workflows (3DE, Nuke, plates) | 1 week |
| Phase 4 | 75% | Performance & edge cases | 1 week |
| Phase 5 | 80%+ | Property-based & stress tests | 1 week |

## Implementation Commands

### Quick Start (Day 1)
```bash
# Fix pytest configuration
sed -i 's/-p no:pytestqt//g' pytest.ini

# Install missing test dependencies  
source venv/bin/activate
pip install pytest-qt hypothesis pytest-benchmark

# Run baseline coverage
python run_tests.py --cov --cov-report=html

# Focus on highest-impact module first
python run_tests.py tests/unit/test_shot_model.py --cov=shot_model --cov-report=term-missing
```

### Test Creation Template
```python
# Template for new test files
"""Test module for {MODULE_NAME}.

This test suite follows TDD principles and minimizes mocking to ensure
real business logic is tested. Uses real Qt components and filesystem
operations where possible.
"""

import pytest
from pathlib import Path
from {MODULE_NAME} import {CLASS_NAME}

class Test{CLASS_NAME}:
    """Test {CLASS_NAME} core functionality with real components."""
    
    def test_{method_name}_happy_path(self, tmp_path):
        """Test normal operation with real filesystem."""
        # Use real files, real Qt components
        
    def test_{method_name}_error_handling(self):
        """Test error conditions with real error scenarios."""
        
    def test_{method_name}_edge_cases(self):
        """Test boundary conditions and edge cases."""
```

## Risk Mitigation

### High-Risk Areas
1. **Qt Threading**: Use `qtbot.waitUntil()` for async operations
2. **Subprocess Timeouts**: Set conservative timeouts in tests  
3. **File System Operations**: Use `tmp_path` fixture religiously
4. **Memory Leaks**: Monitor QPixmap cleanup in thumbnail tests

### Continuous Monitoring
```bash
# Add to CI/CD pipeline
python run_tests.py --cov --cov-fail-under=80
mutmut run  # Mutation testing for test quality
python -m pytest --benchmark-only  # Performance regression detection
```

## Success Metrics

### Coverage Goals
- **Overall**: 80%+ statement coverage
- **Critical modules**: 85%+ coverage each
- **Branch coverage**: 75%+ for complex logic paths
- **Mutation score**: 70%+ (test effectiveness)

### Quality Goals
- **Test execution time**: <2 minutes for full suite
- **Flaky test rate**: <2% (eliminate skipped tests)
- **Memory usage**: No memory leaks in thumbnail operations
- **Performance**: No regression in VFX workflow speed

This plan provides a systematic approach to achieving production-quality test coverage while maintaining the real-world testing philosophy essential for VFX pipeline software.