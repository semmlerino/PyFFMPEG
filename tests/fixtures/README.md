# Test Fixtures Organization

This directory contains reusable test fixtures organized by category for better discoverability and maintenance.

## Structure

```
tests/fixtures/
├── README.md           # This file
├── __init__.py         # Makes fixtures importable
├── models.py           # Domain model fixtures (Shot, Scene, etc.)
├── test_doubles.py     # Test doubles and mocks
├── qt_fixtures.py      # Qt-specific fixtures (widgets, signals)
└── paths.py            # Path and filesystem fixtures
```

## Usage

Fixtures in this directory are automatically discovered by pytest through `tests/conftest.py`.

### Example: Using a fixture from this directory

```python
# tests/unit/test_example.py
import pytest

def test_something(make_shot):  # Fixture from fixtures/models.py
    shot = make_shot("show", "seq", "shot", "/path")
    assert shot.show == "show"
```

## Guidelines

1. **Organization by Domain**
   - Place model-related fixtures in `models.py`
   - Place test doubles in `test_doubles.py`
   - Place Qt fixtures in `qt_fixtures.py`

2. **Factory Fixtures**
   - Use `make_*` naming for factory fixtures
   - Example: `make_shot()`, `make_launcher()`

3. **Scope**
   - Use `scope="session"` for expensive, immutable fixtures
   - Use `scope="function"` (default) for isolation
   - Use `scope="module"` for shared state within a module

4. **Dependencies**
   - Keep fixtures loosely coupled
   - Use composition over inheritance
   - Prefer real components over mocks

## Migration Notes

Many fixtures are currently in `tests/conftest.py`. New fixtures should be added to the appropriate file in this directory. Existing fixtures can be gradually migrated as needed.
