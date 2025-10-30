# Integrating Fixtures with conftest.py

## Current State

The project currently has fixtures in two locations:
1. **tests/conftest.py** - Main conftest with many established fixtures
2. **tests/fixtures/** - New organized fixture directory (this directory)

## Integration Pattern

To make fixtures from this directory available to all tests, import them in `tests/conftest.py`:

```python
# At the end of tests/conftest.py, add:

# Import organized fixtures from fixtures/ directory
pytest_plugins = [
    "tests.fixtures.paths",
    "tests.fixtures.test_doubles",
    # Add more as created
]
```

## Migration Strategy

**DO NOT migrate existing fixtures immediately.** Instead:

1. **New fixtures** → Add to appropriate file in `tests/fixtures/`
2. **Duplicated fixtures** → Consider extracting to `tests/fixtures/`
3. **Complex fixtures** → Leave in `tests/conftest.py` if they have dependencies

## Example: Adding a New Fixture

### Step 1: Choose the right file

- Model-related? → `fixtures/models.py`
- Path-related? → `fixtures/paths.py`
- Test double? → `fixtures/test_doubles.py`
- Qt widget? → `fixtures/qt_fixtures.py` (create if needed)

### Step 2: Write the fixture

```python
# tests/fixtures/models.py
import pytest

@pytest.fixture
def make_scene():
    \"\"\"Factory to create test Scene objects.\"\"\"
    def _create(name: str, path: str):
        from threede_scene_model import Scene
        return Scene(name=name, path=path)
    return _create
```

### Step 3: Register in conftest.py

```python
# tests/conftest.py
pytest_plugins = [
    "tests.fixtures.paths",
    "tests.fixtures.test_doubles",
    "tests.fixtures.models",  # Add new module
]
```

### Step 4: Use in tests

```python
# tests/unit/test_something.py
def test_scene_creation(make_scene):
    scene = make_scene("test", "/path")
    assert scene.name == "test"
```

## Benefits

- ✅ Better organization and discoverability
- ✅ Easier to find related fixtures
- ✅ Reduces conftest.py complexity over time
- ✅ Clear separation by domain
- ✅ Follows UNIFIED_TESTING_GUIDE principles
