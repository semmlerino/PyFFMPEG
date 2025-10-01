# UNIFIED_TESTING_GUIDE

This document establishes consistent testing patterns and principles for the ShotBot VFX application test suite.

## Core Testing Philosophy

### 1. Test Behavior, Not Implementation
- Focus on what the code does, not how it does it
- Test public interfaces and observable outcomes
- Avoid testing private methods or internal state directly
- Write tests that remain stable when refactoring implementation

### 2. Use Real Components Where Possible
- Prefer real instances over mocks for better integration testing
- Use actual Qt widgets, file systems, and network connections when feasible
- Mock only at system boundaries (time, external APIs, hardware)
- Real components provide better confidence in actual behavior

### 3. Strategic Use of Test Doubles
- **Test Doubles**: Use for behavior verification and isolation
- **Mocks**: Only for external dependencies and system boundaries
- **Stubs**: For predictable responses from complex dependencies
- **Fakes**: For lightweight implementations of heavy dependencies

### 4. Thread Safety in Tests
- All tests must handle Qt's threading model correctly
- Use proper Qt test fixtures for GUI components
- Implement thread-safe cleanup patterns
- Test concurrent operations where applicable

## Testing Patterns by Component Type

### Qt GUI Components
```python
# GOOD: Real Qt components with proper fixtures
from typing import Iterator
from pytestqt.qtbot import QtBot
from PySide6.QtCore import Qt

@pytest.fixture
def main_window(qtbot: QtBot) -> MainWindow:
    """Create MainWindow with Qt lifecycle management."""
    window = MainWindow()
    qtbot.addWidget(window)
    return window

def test_window_behavior(main_window: MainWindow, qtbot: QtBot) -> None:
    """Test actual user interactions with typed parameters."""
    # Test actual user interactions
    qtbot.mouseClick(main_window.button, Qt.LeftButton)
    assert main_window.status_label.text() == "Clicked"
```

### Cache Components
```python
# GOOD: Real cache with temporary directories
from typing import Callable
from pathlib import Path

@pytest.fixture
def cache_manager(tmp_path: Path) -> CacheManager:
    """Create CacheManager with temporary directory."""
    return CacheManager(cache_dir=tmp_path / "cache")

def test_cache_behavior(cache_manager: CacheManager) -> None:
    """Test actual caching operations with type safety."""
    # Test actual caching operations
    result: str = cache_manager.get_or_create("key", lambda: "value")
    assert result == "value"
    assert cache_manager.contains("key")
```

### Process Management
```python
# GOOD: Mock at system boundary
from typing import Any
from unittest.mock import MagicMock

def test_process_execution(mock_subprocess: MagicMock) -> None:
    """Test process execution with mocked subprocess."""
    mock_subprocess.return_value.returncode = 0
    mock_subprocess.return_value.stdout = "success"

    manager = ProcessManager()
    result: ProcessResult = manager.execute(["echo", "test"])
    assert result.success
```

## File Organization Standards

### Test File Structure
```
tests/
├── unit/                    # Pure unit tests
│   ├── test_cache_manager.py
│   ├── test_shot_model.py
│   └── test_thumbnail_processor.py
├── integration/             # Component integration tests
│   ├── test_cache_integration.py
│   └── test_ui_workflow.py
├── fixtures/               # Shared test fixtures
│   ├── conftest.py
│   └── test_data/
└── utilities/              # Test utilities and helpers
    ├── qt_helpers.py
    └── mock_factories.py
```

### Test Naming Conventions
```python
# Test class names: Test + ComponentName
class TestShotModel:
    pass

# Test method names: test_ + behavior_description
def test_shot_loading_updates_model_correctly(self):
    pass

def test_thumbnail_cache_evicts_old_entries_under_pressure(self):
    pass

# Fixture names: component_name or descriptive_purpose
@pytest.fixture
def shot_model():
    pass

@pytest.fixture
def sample_thumbnail_files():
    pass
```

## pytest Configuration

### pyproject.toml Setup

Configure pytest in `pyproject.toml` for consistent test behavior across environments:

```toml
[tool.pytest.ini_options]
# Test discovery
testpaths = ["tests"]
python_files = ["test_*.py", "*_test.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]

# Runtime options
addopts = [
    "--strict-markers",          # Enforce marker registration
    "--strict-config",           # Enforce configuration validation
    "-ra",                       # Show summary of all test outcomes
    "--cov=shotbot",             # Coverage for source package
    "--cov-report=html",         # HTML coverage report in htmlcov/
    "--cov-report=term-missing", # Terminal report with missing lines
    "--cov-fail-under=80",       # Minimum 80% coverage required
]

# Custom markers (must be registered)
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "integration: marks tests requiring external resources",
    "unit: fast isolated unit tests",
    "qt: tests requiring Qt application",
]

# Minimum Python version
minversion = "7.0"
```

### Running Tests with Configuration

```bash
# Run all tests with coverage
pytest

# Run only unit tests
pytest -m unit

# Run excluding slow tests
pytest -m "not slow"

# Run specific test file
pytest tests/unit/test_cache_manager.py

# Run in parallel (requires pytest-xdist)
pytest -n auto
```

## Fixture Scopes

Understanding fixture scopes is critical for test performance and isolation.

### Scope Comparison

| Scope | Lifetime | Runs For | Best Use Case | Isolation Risk |
|-------|----------|----------|---------------|----------------|
| **function** (default) | Per test | 100 tests = 100 runs | Mutable state, safest choice | None |
| **class** | Per test class | 5 classes = 5 runs | Expensive setup, read-only | Low |
| **module** | Per file | 1 module = 1 run | Very expensive, immutable | Medium |
| **session** | Entire run | All tests = 1 run | Global constants only | High |

### Function Scope - Safest Default

```python
from pathlib import Path

@pytest.fixture  # scope="function" is default
def temp_cache(tmp_path: Path) -> CacheManager:
    """Created fresh for each test - best isolation."""
    return CacheManager(cache_dir=tmp_path / "cache")

def test_cache_set(temp_cache: CacheManager) -> None:
    temp_cache.set("key", "value")
    assert temp_cache.get("key") == "value"

def test_cache_clear(temp_cache: CacheManager) -> None:
    # Gets NEW cache instance, previous test's data is gone
    assert temp_cache.is_empty()
```

### Session Scope - Performance Critical

```python
from typing import Any

@pytest.fixture(scope="session")
def application_config() -> dict[str, Any]:
    """Created once for entire pytest session.

    Use ONLY for: Truly immutable data needed across all tests.
    Warning: Mutable state will leak between tests!
    """
    return load_application_config()
```

### Best Practices

1. **Default to function scope** - safest choice
2. **Use session scope** only for immutable config/constants
3. **Never share mutable state** in scopes broader than function
4. **Use class/module scopes** sparingly - they can hide test coupling

## Fixture Patterns

### Qt Component Fixtures
```python
@pytest.fixture
def shot_grid_view(qtbot):
    """Create ShotGridView with proper Qt lifecycle management."""
    view = ShotGridView()
    qtbot.addWidget(view)
    yield view
    # Cleanup handled by qtbot

@pytest.fixture
def thumbnail_widget(qtbot, tmp_path):
    """Create ThumbnailWidget with temporary cache directory."""
    cache_dir = tmp_path / "thumbnails"
    cache_dir.mkdir()

    widget = ThumbnailWidget(cache_directory=cache_dir)
    qtbot.addWidget(widget)
    return widget
```

### Data Fixtures
```python
@pytest.fixture
def sample_shots_data():
    """Provide realistic shot data for testing."""
    return [
        {"name": "shot_010", "status": "approved", "frames": 120},
        {"name": "shot_020", "status": "in_progress", "frames": 240},
        {"name": "shot_030", "status": "pending", "frames": 180},
    ]

@pytest.fixture
def mock_workspace_response():
    """Provide mock response for workspace command."""
    return {
        "shots": sample_shots_data(),
        "shows": ["test_show"],
        "timestamp": "2024-01-01T12:00:00Z"
    }
```

### Temporary File Fixtures
```python
@pytest.fixture
def thumbnail_files(tmp_path):
    """Create temporary thumbnail files for testing."""
    thumb_dir = tmp_path / "thumbnails"
    thumb_dir.mkdir()

    files = []
    for i in range(5):
        thumb_file = thumb_dir / f"thumb_{i}.jpg"
        # Create minimal valid JPEG
        thumb_file.write_bytes(
            b"\xff\xd8\xff\xe0" + b"x" * 1000 + b"\xff\xd9"
        )
        files.append(thumb_file)

    return files
```

## Parametrization Patterns

Parametrization allows testing multiple scenarios efficiently without code duplication.

### Basic Parametrization

```python
import pytest

@pytest.mark.parametrize("status,expected_color", [
    ("approved", "green"),
    ("in_progress", "yellow"),
    ("pending", "gray"),
    ("rejected", "red"),
])
def test_shot_status_color(status: str, expected_color: str) -> None:
    """Test status-to-color mapping for all possible statuses."""
    shot = Shot(status=status)
    assert shot.status_color == expected_color
```

### Parametrization with IDs for Readable Output

Use `ids` parameter for descriptive test names in output:

```python
from typing import Any

@pytest.mark.parametrize(
    "shot_data,expected_valid",
    [
        ({"name": "sh010", "status": "approved", "frames": 120}, True),
        ({"name": "", "status": "approved", "frames": 120}, False),
        ({"name": "sh010", "status": "invalid", "frames": 120}, False),
        ({"name": "sh010", "status": "approved", "frames": -10}, False),
    ],
    ids=["valid", "no_name", "bad_status", "negative_frames"]
)
def test_shot_validation(
    shot_data: dict[str, Any],
    expected_valid: bool
) -> None:
    """Test shot data validation with descriptive test IDs.

    Test output will show: test_shot_validation[valid], test_shot_validation[no_name], etc.
    """
    shot = Shot(**shot_data)
    assert shot.is_valid() == expected_valid
```

## Assertion Patterns

### Behavior Verification
```python
# GOOD: Test observable behavior
def test_shot_refresh_updates_view(shot_model, shot_view):
    shot_model.add_shot("new_shot")
    shot_view.refresh()

    # Verify behavior through public interface
    assert shot_view.shot_count == 1
    assert "new_shot" in shot_view.visible_shots

# AVOID: Testing implementation details
def test_shot_refresh_calls_internal_method(shot_model):
    # Don't test private method calls
    with patch.object(shot_model, '_update_internal_cache'):
        shot_model.refresh()
        shot_model._update_internal_cache.assert_called_once()
```

### Error Condition Testing
```python
def test_thumbnail_loading_handles_missing_file(thumbnail_manager):
    """Test graceful handling of missing thumbnail files."""
    missing_path = Path("/nonexistent/file.jpg")

    result = thumbnail_manager.load_thumbnail(missing_path)

    # Verify graceful failure
    assert result.success is False
    assert "not found" in result.error_message.lower()
    assert result.thumbnail is None
```

### Thread Safety Testing
```python
def test_concurrent_cache_access_thread_safe(cache_manager):
    """Test thread safety of cache operations."""
    import concurrent.futures
    import threading

    results = []

    def cache_operation(thread_id):
        for i in range(100):
            key = f"thread_{thread_id}_item_{i}"
            cache_manager.set(key, f"value_{i}")
            retrieved = cache_manager.get(key)
            results.append(retrieved == f"value_{i}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [
            executor.submit(cache_operation, i) for i in range(5)
        ]
        for future in concurrent.futures.as_completed(futures):
            future.result()

    # All operations should succeed
    assert all(results)
    assert len(results) == 500  # 5 threads × 100 operations
```

## Mock Usage Guidelines

### When to Mock
1. **External Systems**: File systems, networks, databases
2. **Time Dependencies**: datetime.now(), time.sleep()
3. **Hardware**: GPU detection, system resources
4. **Expensive Operations**: Large file processing, network calls

### When NOT to Mock
1. **Business Logic**: Core application algorithms
2. **Qt Components**: Use real widgets with qtbot
3. **Data Structures**: Lists, dicts, custom classes
4. **Simple Dependencies**: Math operations, string processing

### Mock Examples
```python
# GOOD: Mock external system boundary
def test_shot_loading_handles_network_failure():
    with patch("requests.get") as mock_get:
        mock_get.side_effect = requests.ConnectionError("Network unreachable")

        shot_loader = ShotLoader()
        result = shot_loader.load_shots_from_server()

        assert result.success is False
        assert "network" in result.error_message.lower()

# GOOD: Mock time for deterministic testing
def test_cache_expiration():
    with patch("time.time") as mock_time:
        mock_time.return_value = 1000

        cache = TTLCache(ttl_seconds=300)
        cache.set("key", "value")

        # Advance time past expiration
        mock_time.return_value = 1500
        assert cache.get("key") is None
```

## Performance Testing

### Memory Usage Testing
```python
def test_thumbnail_cache_memory_limit_respected(thumbnail_manager):
    """Verify memory limits are enforced."""
    initial_memory = thumbnail_manager.memory_usage_bytes

    # Load thumbnails until near limit
    for i in range(100):
        thumbnail_manager.load_thumbnail(create_test_image(size_mb=1))

    final_memory = thumbnail_manager.memory_usage_bytes
    max_memory = thumbnail_manager.max_memory_bytes

    # Should stay within configured limit
    assert final_memory <= max_memory
    assert final_memory > initial_memory
```

### Timing and Performance
```python
def test_shot_loading_performance_acceptable():
    """Verify shot loading meets performance requirements."""
    shot_model = ShotModel()

    start_time = time.time()
    shot_model.load_shots(count=1000)
    end_time = time.time()

    load_time = end_time - start_time

    # Should load 1000 shots in under 5 seconds
    assert load_time < 5.0
    assert shot_model.shot_count == 1000
```

## Error Handling Testing

### Exception Testing with match Parameter

Use `match` to verify specific error messages with regex:

```python
import pytest

def test_invalid_shot_data_with_specific_message() -> None:
    """Test error handling with precise error message validation."""
    shot_model = ShotModel()
    invalid_data = {"missing_required_fields": True}

    # Use regex pattern to match error message
    with pytest.raises(
        ValidationError,
        match=r"required fields.*missing|missing.*required fields"
    ) as exc_info:
        shot_model.add_shot_data(invalid_data)

    # Access exception for additional checks
    assert exc_info.value.field_name == "name"
```

### Testing Exception Notes (Python 3.11+, PEP 678)

Modern Python supports adding contextual notes to exceptions:

```python
def test_exception_with_notes() -> None:
    """Test that exceptions include helpful context notes (PEP 678)."""
    shot_model = ShotModel()
    invalid_data = {"name": "sh010", "status": "invalid_status"}

    with pytest.raises(ValidationError) as exc_info:
        shot_model.add_shot_data(invalid_data)

    # Check exception notes added via exc.add_note()
    if hasattr(exc_info.value, '__notes__'):
        notes = exc_info.value.__notes__
        assert any("valid statuses" in note for note in notes)
        assert any("approved" in note or "pending" in note for note in notes)
```

### Parametrized Exception Testing

Test multiple error conditions efficiently:

```python
from typing import Any

@pytest.mark.parametrize("invalid_data,expected_exception", [
    ({"frames": -10}, ValueError),
    ({"status": "invalid"}, ValidationError),
    ({}, KeyError),
])
def test_various_error_conditions(
    invalid_data: dict[str, Any],
    expected_exception: type[Exception]
) -> None:
    """Test that different invalid data raises appropriate exceptions."""
    shot_model = ShotModel()
    with pytest.raises(expected_exception):
        shot_model.add_shot_data(invalid_data)
```

## Test Data Management

### Realistic Test Data
```python
# Use realistic data that matches production
SAMPLE_SHOT_DATA = [
    {
        "name": "sh010_comp_v003",
        "status": "approved",
        "frames": {"start": 1001, "end": 1120},
        "resolution": {"width": 2048, "height": 1556},
        "path": "/shows/test_show/sequences/seq010/shots/sh010",
    },
    # More realistic entries...
]
```

### Test Data Factories
```python
def create_test_shot(name=None, status="in_progress", frame_count=120):
    """Factory function for creating test shot data."""
    if name is None:
        name = f"test_shot_{uuid.uuid4().hex[:8]}"

    return {
        "name": name,
        "status": status,
        "frames": {"start": 1001, "end": 1001 + frame_count - 1},
        "path": f"/test/path/{name}",
        "created": datetime.now().isoformat(),
    }
```

## Recommended Pytest Plugins

Leverage the pytest ecosystem to enhance testing capabilities.

### pytest-cov: Coverage Reporting

Track code coverage to identify untested code paths:

```bash
# Install
pip install pytest-cov

# Run with coverage
pytest --cov=shotbot --cov-report=html

# View report
open htmlcov/index.html
```

Configuration in `pyproject.toml`:
```toml
[tool.pytest.ini_options]
addopts = [
    "--cov=shotbot",
    "--cov-report=html",
    "--cov-report=term-missing",
    "--cov-fail-under=80",  # Fail if coverage < 80%
]
```

### pytest-mock: Enhanced Mocking

Provides `mocker` fixture with cleaner syntax than `unittest.mock`:

```python
from pytest_mock import MockerFixture

def test_with_mocker(mocker: MockerFixture) -> None:
    """Use pytest-mock for cleaner mocking syntax."""
    # Patch with mocker fixture
    mock_get = mocker.patch("requests.get")
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {"data": "value"}

    # Automatic cleanup, no context managers needed
    result = fetch_data()
    assert result == {"data": "value"}
    mock_get.assert_called_once()
```

### pytest-benchmark: Performance Testing

Benchmark code performance with statistical analysis:

```python
from pytest_benchmark.fixture import BenchmarkFixture

def test_cache_performance(benchmark: BenchmarkFixture) -> None:
    """Benchmark cache operations."""
    cache = CacheManager()

    # Benchmark the operation
    result = benchmark(cache.get_or_create, "key", lambda: "value")

    assert result == "value"
    # Benchmark fixture handles timing, statistics, comparisons
```

### pytest-qt: Qt Testing (Already Covered)

Provides `qtbot` fixture for Qt application testing. See Qt Component Fixtures section for detailed examples.

### pytest-xdist: Parallel Execution (Already Covered)

Run tests in parallel for faster execution. See Parallel Test Execution section for comprehensive coverage.

### pytest-timeout: Prevent Hanging Tests

Automatically fail tests that run too long:

```bash
pip install pytest-timeout

# Run with global timeout
pytest --timeout=60  # 60 seconds per test
```

```python
import pytest

@pytest.mark.timeout(5)  # 5 second timeout for this test
def test_fast_operation() -> None:
    """Test that must complete within 5 seconds."""
    result = perform_operation()
    assert result.success
```

### pytest-order: Control Test Execution Order

Control test execution order when needed (use sparingly):

```python
import pytest

@pytest.mark.order(1)
def test_database_setup() -> None:
    """Run first to set up database."""
    setup_database()

@pytest.mark.order(2)
def test_database_operations() -> None:
    """Run after setup."""
    perform_operations()
```

**Note:** Tests should be independent; only use ordering for true dependencies.

## Continuous Integration Considerations

### Test Isolation
- Each test should be completely independent
- No shared state between tests
- Proper setup and teardown for each test

### Resource Cleanup
```python
@pytest.fixture
def resource_manager():
    """Example of proper resource management in fixtures."""
    manager = ResourceManager()
    try:
        yield manager
    finally:
        manager.cleanup_all_resources()
```

### Deterministic Testing
- Use fixed seeds for random operations
- Mock time-dependent functionality
- Ensure tests pass consistently across environments

## Parallel Test Execution with pytest-xdist

### QApplication Isolation Pattern

Enhance `qapp` fixture with worker cleanup to prevent Qt state leakage:

```python
@pytest.fixture
def qapp(qapp, request):
    """Add xdist worker-specific cleanup."""
    try:
        from xdist import is_xdist_worker
        in_worker = is_xdist_worker(request)
    except (ImportError, TypeError):
        in_worker = False

    yield qapp

    if in_worker:
        qapp.processEvents()
        QTimer.singleShot(0, lambda: None)
        qapp.processEvents()
```

### Dynamic Timeouts

Adapt timeouts for parallel execution resource contention:

```python
def test_worker_operation(qtbot):
    try:
        from xdist import is_xdist_worker
        timeout = 60000 if is_xdist_worker(qtbot._request) else 30000
    except (ImportError, TypeError, AttributeError):
        timeout = 30000

    with qtbot.waitSignal(worker.finished, timeout=timeout):
        worker.start()
```

### Grouping Qt Tests

Use `xdist_group` markers to run related tests in the same worker:

```python
pytestmark = [
    pytest.mark.qt,
    pytest.mark.xdist_group("qt_state"),  # Reduces context switches
]
```

### Running in Parallel

```bash
pytest tests/ -n auto              # Auto-detect CPU cores
pytest tests/ -n auto --dist=loadscope  # Group by test scope
```

### Common Issues and Solutions

| Issue | Symptom | Solution |
|-------|---------|----------|
| QApplication conflicts | "Instance already exists" crash | Use enhanced `qapp` fixture above |
| Timing failures | Timeouts only in parallel | Use dynamic timeouts |
| Shared state | Pass individually, fail parallel | Use `tmp_path`, avoid shared state |

### Shared Resources Pattern

```python
from filelock import FileLock

@pytest.fixture(scope="session")
def shared_resource(tmp_path_factory, request):
    """Share expensive resource across workers with file locking."""
    root_tmp_dir = tmp_path_factory.getbasetemp().parent
    resource_file = root_tmp_dir / "resource.json"

    with FileLock(str(resource_file) + ".lock"):
        if resource_file.exists():
            return load_resource(resource_file)
        resource = create_resource()
        save_resource(resource_file, resource)
        return resource
```

### Best Practices

**DO:**
- Enhance `qapp` fixture with worker cleanup
- Use dynamic timeouts for Qt operations
- Group Qt-heavy tests with `xdist_group`
- Use `tmp_path` for test isolation

**DON'T:**
- Share mutable state between tests
- Use session-scoped fixtures for Qt widgets
- Rely on test execution order
- Assume sequential timing

This unified testing guide ensures consistency, reliability, and maintainability across the entire ShotBot test suite while following Qt, Python, and parallel execution best practices.

## References and Further Reading

### Official Documentation

- **[Pytest Documentation](https://docs.pytest.org)** - Official pytest guide and reference
- **[Pytest Best Practices](https://docs.pytest.org/en/stable/explanation/goodpractices.html)** - Official best practices guide
- **[pytest-qt Documentation](https://pytest-qt.readthedocs.io/)** - Qt testing with pytest
- **[pytest-xdist Documentation](https://pytest-xdist.readthedocs.io/)** - Parallel test execution
- **[pytest-cov Documentation](https://pytest-cov.readthedocs.io/)** - Coverage reporting
- **[pytest-mock Documentation](https://pytest-mock.readthedocs.io/)** - Enhanced mocking utilities

### Python Enhancement Proposals (PEPs)

Testing-related Python standards and improvements:

- **[PEP 484](https://peps.python.org/pep-0484/)** - Type Hints for better code analysis
- **[PEP 585](https://peps.python.org/pep-0585/)** - Type Hinting Generics (list[T] vs List[T])
- **[PEP 604](https://peps.python.org/pep-0604/)** - Union Types (X | Y vs Union[X, Y])
- **[PEP 678](https://peps.python.org/pep-0678/)** - Enriching Exceptions with Notes (Python 3.11+)
- **[PEP 612](https://peps.python.org/pep-0612/)** - Parameter Specification Variables for typed decorators
- **[PEP 3148](https://peps.python.org/pep-3148/)** - futures - concurrent.futures module

### Testing Tools and Plugins

- **[pytest-benchmark](https://pytest-benchmark.readthedocs.io/)** - Performance testing and benchmarking
- **[pytest-timeout](https://pypi.org/project/pytest-timeout/)** - Test timeout management
- **[pytest-order](https://pytest-order.readthedocs.io/)** - Control test execution order
- **[Hypothesis](https://hypothesis.readthedocs.io/)** - Property-based testing framework
- **[Coverage.py](https://coverage.readthedocs.io/)** - Code coverage measurement
- **[tox](https://tox.wiki/)** - Testing across multiple Python environments

### Qt Testing Resources

- **[Qt Test Framework](https://doc.qt.io/qt-6/qttest-index.html)** - Official Qt testing documentation
- **[Qt Threading Basics](https://doc.qt.io/qt-6/threads-technologies.html)** - Qt threading technologies
- **[PySide6 Documentation](https://doc.qt.io/qtforpython-6/)** - Official PySide6 documentation

### Best Practices and Patterns

- **[Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)** - Comprehensive Python style guide
- **[Testing Best Practices (RealPython)](https://realpython.com/pytest-python-testing/)** - Pytest tutorial and patterns
- **[Effective Python Testing](https://testdriven.io/blog/testing-python/)** - Modern Python testing approaches

### Books and In-Depth Resources

- **"Python Testing with pytest" by Brian Okken** - Comprehensive pytest guide
- **"Test-Driven Development with Python" by Harry Percival** - TDD methodology
- **"Effective Python" by Brett Slatkin** - Modern Python best practices

This guide incorporates best practices from these authoritative sources to ensure your ShotBot test suite follows industry standards and modern Python conventions.