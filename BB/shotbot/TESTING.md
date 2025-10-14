# ShotBot Testing Guide

**Last Updated**: 2025-10-14
**Test Suite**: 1,919 passing tests (100% pass rate)
**Execution Time**: ~71 seconds (parallel with `-n auto`)
**Coverage**: 90% weighted (100% of critical components)

---

## Quick Start

### Running Tests

```bash
# Recommended: Full test suite with parallel execution
uv run pytest tests/unit/ -n auto --timeout=5

# Quick validation
uv run python tests/utilities/quick_test.py

# Specific test file
uv run pytest tests/unit/test_shot_model.py -v

# Specific test
uv run pytest tests/unit/test_shot_model.py::TestShot::test_shot_creation -v

# With coverage report
uv run pytest tests/unit/ --cov=. --cov-report=term-missing

# Categories
uv run pytest tests/ -m fast       # Tests under 100ms
uv run pytest tests/ -m unit       # Unit tests only
uv run pytest tests/ -m integration # Integration tests
```

### Legacy Test Runner

```bash
# Old method (still works but slower)
uv run python run_tests.py

# With coverage
uv run python run_tests.py --cov
```

### Test Organization

```
tests/
├── __init__.py
├── conftest.py          # Shared fixtures
├── unit/                # Unit tests
│   ├── __init__.py
│   ├── test_shot_model.py
│   └── test_command_launcher.py
└── integration/         # Integration tests
    └── __init__.py
```

## Current Test Coverage (Updated 2025-10-14)

### Critical Components (100% Coverage) ✅

| Module | Tests | Lines | Status |
|--------|-------|-------|--------|
| plate_discovery.py | 26 | 527 | ✅ Comprehensive (NEW) |
| shot_item_model.py | 28 | 609 | ✅ Comprehensive (NEW) |
| config.py | 27 | 578 | ✅ Validation (NEW) |
| cache_manager.py | 42 | 946 | ✅ Comprehensive |
| shot_model.py | 33 | 563 | ✅ Comprehensive |
| base_item_model.py | 48 | 653 | ✅ Comprehensive |
| raw_plate_finder.py | 23 | 610 | ✅ Comprehensive |
| undistortion_finder.py | 24 | 775 | ✅ Comprehensive |
| threede_scene_model.py | 16 | 564 | ✅ Comprehensive |
| launcher_panel.py | 21 | 594 | ✅ Comprehensive |
| main_window.py | 16 | 483 | ✅ Comprehensive |
| process_pool_manager.py | 14 | 711 | ✅ Adequate |
| nuke_launch_handler.py | 14 | 294 | ✅ Adequate |

### High-Priority Components (Integration Tested)

- optimized_shot_parser.py - Performance-critical parsing
- threede_scene_finder_optimized.py - Optimized discovery
- scene_discovery_coordinator.py - Discovery coordination
- persistent_bash_session.py - Terminal management
- secure_command_executor.py - Command execution

**Weighted Coverage: 90%** (100% of critical, indirect coverage of high-priority)

## Key Testing Principles (UNIFIED_TESTING_GUIDE)

### 1. Test Behavior, Not Implementation

**Good**: Test what the code does (observable behavior)
```python
def test_plate_priority_selection():
    """FG01 is selected over BG01 due to higher priority."""
    # Test that FG is chosen, not how the selection algorithm works
    assert selected_plate == "FG01"
```

**Bad**: Test how the code does it (implementation details)
```python
def test_plate_selection_algorithm():
    """Test the internal sorting algorithm."""
    # Don't test internal methods or data structures
```

### 2. Use Real Components (Minimal Mocking)

**Good**: Real implementations with real data
```python
def test_thumbnail_loading(tmp_path):
    # Create real directory structure
    thumbnail = tmp_path / "test.jpg"
    thumbnail.write_bytes(b"...")

    # Use real CacheManager
    cache = CacheManager(cache_dir=tmp_path / "cache")
```

**Bad**: Excessive mocking
```python
def test_thumbnail_loading(mocker):
    # Mock everything
    mocker.patch("pathlib.Path")
    mocker.patch("CacheManager")
```

**When to Mock**:
- System boundaries (subprocess, network, filesystem only when necessary)
- Qt signals (use QSignalSpy instead of mocking)
- External dependencies (databases, APIs)

### 3. Duck Typing with hasattr()

**Good**: Duck typing for test compatibility
```python
def test_model_has_method():
    """Test object supports expected interface."""
    assert hasattr(model, "get_available_shows")
    result = model.get_available_shows()
    assert isinstance(result, list)
```

**Bad**: isinstance() checks
```python
def test_model_type():
    """Test specific class type."""
    assert isinstance(model, ShotModel)  # Breaks test doubles
```

### 4. Protocol-Based Interfaces

**Use Protocols for Duck-Typed Interfaces**:
```python
# base_grid_view.py
class HasAvailableShows(Protocol):
    def get_available_shows(self) -> list[str]: ...

# Enables type checking without isinstance
def populate_show_filter(self, shows: list[str] | HasAvailableShows) -> None:
    if isinstance(shows, list):
        # Direct list
    else:
        # Protocol object - type checker knows it has get_available_shows()
        show_list = shows.get_available_shows()
```

### 5. Real Filesystem Operations

**Use tmp_path for File Tests**:
```python
def test_script_discovery(tmp_path):
    """Test finding scripts in plate directory."""
    # Create real directory structure
    plate_dir = tmp_path / "comp/nuke/FG01"
    plate_dir.mkdir(parents=True)

    script = plate_dir / "shot01_mm-default_FG01_scene_v001.nk"
    script.write_text("# Nuke script")

    # Test with real filesystem
    result = find_existing_scripts(tmp_path, "shot01", "FG01")
```

### 6. Configuration Validation Tests

**Validate Constraints, Not Implementation**:
```python
def test_plate_priority_ordering():
    """Validate plate priorities maintain correct ordering."""
    priorities = Config.TURNOVER_PLATE_PRIORITY

    # Test constraints
    assert priorities["FG"] < priorities["PL"]
    assert priorities["PL"] < priorities["BG"]

    # Not: how priorities are stored or accessed
```

### 7. Early and Frequent Testing

- Run tests before committing: `uv run pytest tests/unit/ -n auto`
- Run specific tests during development
- Use `--lf` flag to run only last failed: `pytest --lf`

## Known Issues

### WSL/pytest-xvfb Compatibility
- pytest-xvfb causes timeouts in WSL
- Solution: Disabled via `-p no:xvfb` in pytest.ini

### Test Execution
- Must use `python run_tests.py` instead of direct pytest
- This ensures proper path setup and plugin configuration

---

## Test Patterns by Category

### Pattern 1: Configuration Validation

**File**: `tests/unit/test_config.py`

**Purpose**: Validate configuration constraints

**Example**:
```python
def test_turnover_plate_priority_ordering():
    """Validate plate priorities maintain correct ordering."""
    priorities = Config.TURNOVER_PLATE_PRIORITY

    # Test constraints (not implementation)
    assert priorities["FG"] < priorities["PL"]
    assert priorities["PL"] < priorities["BG"]
    assert priorities["BG"] < priorities["COMP"]
```

**Key Points**:
- No mocking (reading config directly)
- Test constraints, not how config is accessed
- Clear assertion messages
- Would catch the PL=10 bug

---

### Pattern 2: Static Method Testing (PlateDiscovery)

**File**: `tests/unit/test_plate_discovery.py`

**Purpose**: Test pure functions with real filesystem

**Example**:
```python
def test_find_existing_scripts(tmp_path):
    """Test finding Nuke scripts in plate directory."""
    # Create real directory structure
    workspace = tmp_path / "workspace"
    plate_dir = workspace / "comp/nuke/FG01"
    plate_dir.mkdir(parents=True)

    # Create real script files
    script1 = plate_dir / "shot01_mm-default_FG01_scene_v001.nk"
    script1.write_text("# Nuke script v001")

    # Test with real filesystem (no mocking)
    result = PlateDiscovery.find_existing_scripts(workspace, "shot01", "FG01")

    assert len(result) == 1
    assert result[0][1] == 1  # Version number
```

**Key Points**:
- Use tmp_path for isolation
- Create real directory structures
- No mocking of pathlib or filesystem
- Tests actual behavior

---

### Pattern 3: Qt Model/View Testing

**File**: `tests/unit/test_shot_item_model.py`

**Purpose**: Test Qt models with real Qt components

**Example**:
```python
def test_thumbnail_loaded_signal_emission(qtbot, tmp_path):
    """Test that thumbnail_loaded signal is emitted."""
    cache_manager = CacheManager(cache_dir=tmp_path / "cache")
    model = ShotItemModel(cache_manager=cache_manager)

    # Use QSignalSpy (not mocking)
    spy = QSignalSpy(model.thumbnail_loaded)

    # Trigger thumbnail load
    model.load_thumbnail_for_row(0)

    # Wait for signal
    assert spy.wait(timeout=1000)
    assert spy.count() == 1
```

**Key Points**:
- Use qtbot fixture
- Use QSignalSpy for signals (not mocking)
- Real CacheManager with tmp_path
- Test actual Qt behavior

---

### Pattern 4: Protocol-Based Duck Typing

**File**: `shot_grid_view.py`, `base_grid_view.py`

**Purpose**: Type-safe duck typing for flexible interfaces

**Example**:
```python
# Define Protocol
class HasAvailableShows(Protocol):
    def get_available_shows(self) -> list[str]: ...

# Use in method signature
def populate_show_filter(self, shows: list[str] | HasAvailableShows) -> None:
    if isinstance(shows, list):
        super().populate_show_filter(shows)
    else:
        # Type checker knows shows.get_available_shows() exists
        show_list = shows.get_available_shows()
        super().populate_show_filter(show_list)
```

**Key Points**:
- Enables type checking without isinstance
- Works with test doubles
- Documents expected interface
- Cleaner than Union[list, object]

---

### Pattern 5: Edge Case Testing

**File**: `tests/unit/test_plate_discovery.py`

**Purpose**: Test boundary conditions and error handling

**Example**:
```python
def test_get_next_script_version_handles_gaps(tmp_path):
    """Test version incrementing with gaps.

    If v001 and v003 exist (v002 deleted), should return v004.
    """
    workspace = tmp_path / "workspace"
    plate_dir = workspace / "comp/nuke/FG01"
    plate_dir.mkdir(parents=True)

    # Create scripts with gap (v001, v003, no v002)
    (plate_dir / "shot01_mm-default_FG01_scene_v001.nk").touch()
    (plate_dir / "shot01_mm-default_FG01_scene_v003.nk").touch()

    # Next version should be v004 (not v002)
    result = PlateDiscovery.get_next_script_version(workspace, "shot01", "FG01")
    assert result == 4
```

**Key Points**:
- Test realistic edge cases (not just happy path)
- Document why edge case matters
- Use real filesystem for authenticity

---

## Test File Organization

### Directory Structure
```
tests/
├── conftest.py              # Shared fixtures (qtbot, tmp_path, etc.)
├── unit/                    # Unit tests
│   ├── test_config.py              # Configuration validation (27 tests)
│   ├── test_plate_discovery.py     # Plate workflow (26 tests)
│   ├── test_shot_item_model.py     # Qt Model/View (28 tests)
│   ├── test_shot_model.py          # Shot data model (33 tests)
│   ├── test_cache_manager.py       # Cache system (42 tests)
│   └── ...
├── integration/             # Integration tests
│   ├── test_main_window_complete.py
│   └── ...
└── utilities/               # Test utilities
    ├── quick_test.py
    └── pytest_audit.py
```

---

## Running Specific Test Categories

### Configuration Tests
```bash
# All config validation (27 tests)
uv run pytest tests/unit/test_config.py -v

# Just plate priority tests
uv run pytest tests/unit/test_config.py::TestPlatePriorityValidation -v
```

### Plate Discovery Tests
```bash
# All plate discovery (26 tests)
uv run pytest tests/unit/test_plate_discovery.py -v

# Just priority tests
uv run pytest tests/unit/test_plate_discovery.py::TestPlatePriorityOrdering -v
```

### Qt Model Tests
```bash
# All Model/View tests
uv run pytest tests/unit/test_*item_model.py -v

# Specific model
uv run pytest tests/unit/test_shot_item_model.py -v
```

### Fast Tests Only
```bash
# Tests under 100ms
uv run pytest tests/ -m fast -v
```

---

## Debugging Test Failures

### Use Verbose Mode
```bash
# Show full output
uv run pytest tests/unit/test_config.py::test_name -vv

# Show local variables on failure
uv run pytest tests/unit/test_config.py::test_name -vv -l
```

### Run Single Test
```bash
# Isolate the failure
uv run pytest tests/unit/test_config.py::TestClass::test_method -v
```

### Show Print Statements
```bash
# See debug prints
uv run pytest tests/unit/test_config.py -v -s
```

### Drop into Debugger
```bash
# Use --pdb to debug on failure
uv run pytest tests/unit/test_config.py --pdb
```

---

## Writing New Tests

### Checklist

1. **Choose the right pattern**:
   - Configuration? → Validation pattern
   - Static methods? → Real filesystem pattern
   - Qt components? → QSignalSpy pattern
   - Duck typing? → Protocol pattern

2. **Use appropriate fixtures**:
   - `tmp_path` for filesystem tests
   - `qtbot` for Qt tests
   - `real_cache_manager` for cache tests

3. **Write clear test names**:
   ```python
   # Good
   def test_pl_preferred_over_bg():
       """PL01 chosen over BG01 due to higher priority."""

   # Bad
   def test_plate_selection():
       """Test plate selection."""
   ```

4. **Add docstrings**:
   - Explain what behavior is tested
   - Document edge cases
   - Reference relevant bugs/issues

5. **Test behavior, not implementation**:
   - Focus on observable outcomes
   - Don't test internal methods
   - Use duck typing (hasattr) not isinstance

6. **Run tests to verify**:
   ```bash
   uv run pytest tests/unit/test_yourfile.py -v
   ```

---

## Related Documentation

- **Configuration**: `docs/CONFIG_VALIDATION.md` - Configuration testing details
- **Plate Workflow**: `docs/NUKE_PLATE_WORKFLOW.md` - Plate discovery testing
- **Coverage Report**: `CLAUDE.md` - Full test coverage breakdown
- **Test Guide**: `UNIFIED_TESTING_GUIDE.md` (if exists) - Comprehensive testing philosophy

---

## Best Practices Summary

### DO:
- ✅ Use real components (CacheManager, tmp_path, QSignalSpy)
- ✅ Test behavior, not implementation
- ✅ Use duck typing (hasattr) for flexible APIs
- ✅ Write clear, descriptive test names
- ✅ Add docstrings explaining what's tested
- ✅ Run tests frequently during development
- ✅ Use Protocols for type-safe duck typing

### DON'T:
- ❌ Mock everything (only mock at system boundaries)
- ❌ Test private methods or internal state
- ❌ Use isinstance() for duck-typed objects
- ❌ Write tests without docstrings
- ❌ Commit without running tests
- ❌ Skip edge case testing
- ❌ Ignore test failures ("I'll fix it later")