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
@pytest.fixture
def main_window(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    return window

def test_window_behavior(main_window, qtbot):
    # Test actual user interactions
    qtbot.mouseClick(main_window.button, Qt.LeftButton)
    assert main_window.status_label.text() == "Clicked"
```

### Cache Components
```python
# GOOD: Real cache with temporary directories
@pytest.fixture
def cache_manager(tmp_path):
    return CacheManager(cache_dir=tmp_path / "cache")

def test_cache_behavior(cache_manager):
    # Test actual caching operations
    result = cache_manager.get_or_create("key", lambda: "value")
    assert result == "value"
    assert cache_manager.contains("key")
```

### Process Management
```python
# GOOD: Mock at system boundary
def test_process_execution(mock_subprocess):
    mock_subprocess.return_value.returncode = 0
    mock_subprocess.return_value.stdout = "success"

    manager = ProcessManager()
    result = manager.execute(["echo", "test"])
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

### Exception Handling
```python
def test_invalid_shot_data_raises_appropriate_error():
    """Test error handling for malformed shot data."""
    shot_model = ShotModel()

    invalid_data = {"missing_required_fields": True}

    with pytest.raises(ValidationError) as exc_info:
        shot_model.add_shot_data(invalid_data)

    assert "required fields" in str(exc_info.value)
```

### Graceful Degradation
```python
def test_thumbnail_generation_degrades_gracefully():
    """Test graceful handling when thumbnail generation fails."""
    with patch("PIL.Image.open") as mock_open:
        mock_open.side_effect = PIL.UnidentifiedImageError("Corrupt image")

        thumbnail_manager = ThumbnailManager()
        result = thumbnail_manager.generate_thumbnail("corrupt.jpg")

        # Should provide fallback thumbnail
        assert result.success is True
        assert result.thumbnail is not None
        assert result.is_fallback is True
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

This unified testing guide ensures consistency, reliability, and maintainability across the entire ShotBot test suite while following Qt and Python best practices.