# Code Style and Conventions

## Python Version
- **Minimum**: Python 3.11
- **Target**: Python 3.11+
- **Type Syntax**: Modern union syntax (`str | None`, not `Optional[str]`)

## Critical Import Rule
**ALWAYS** import `override` from `typing_extensions`, NOT `typing`:
```python
# CORRECT (Python 3.11 compatible)
from typing_extensions import override

# WRONG (Python 3.12+ only - will fail!)
from typing import override
```

## Ruff Configuration

### Quick Commands
```bash
# Check for issues
~/.local/bin/uv run ruff check .

# Auto-fix safe issues  
~/.local/bin/uv run ruff check . --fix

# Format code
~/.local/bin/uv run ruff format .
```

### Formatting Standards
- **Line length**: 88 characters (Black-compatible)
- **Indent**: 4 spaces
- **Quote style**: Double quotes
- **Target**: Python 3.11+

### Enabled Rule Categories
- **E, W**: pycodestyle (PEP 8 basics)
- **F**: Pyflakes (syntax errors, undefined names)
- **I**: isort (import sorting)
- **N**: pep8-naming (naming conventions)
- **UP**: pyupgrade (modern Python syntax)
- **B**: flake8-bugbear (common bugs)
- **C4**: flake8-comprehensions (better comprehensions)
- **PT**: flake8-pytest-style (test quality)
- **TCH**: flake8-type-checking (import organization)
- **PL**: Pylint (comprehensive checks)
- **TRY**: tryceratops (exception handling)
- **RUF**: Ruff-specific rules

### Key Disabled Rules
- **E501**: line-too-long (formatter handles it)
- **SLF001**: private-member-access (common in Qt)
- **ARG002**: unused-method-argument (Qt callbacks)
- **T201**: print statements (intentional use)
- **G004**: logging f-strings (readable and fine)
- **D**: pydocstyle (our own style)
- **PLR0913**: too-many-arguments (Qt widgets)
- **FBT001/002/003**: boolean arguments (common in GUI)

### Test-Specific Rules
Tests ignore additional rules:
- **S101**: asserts (the point of tests)
- **ARG001**: unused fixtures
- **PLR2004**: magic values in test data

See `RUFF_CONFIGURATION.md` for full details and rationale.

## Type Annotations
- **Required**: All public functions and methods must have type hints
- **Mode**: basedpyright "recommended" mode
- **Strictness**: Error on unknown types, untyped base classes
- **Patterns**:
  - Optional types: `str | None`
  - Signal declarations: `Signal(str)`, `Signal(dict)`, `Signal()`
  - Qt enums: `Qt.ItemDataRole.UserRole` (not `Qt.UserRole`)

## Naming Conventions
- **Classes**: PascalCase (e.g., `ShotModel`, `MainWindow`)
- **Functions/Methods**: snake_case (e.g., `refresh_shots`, `load_thumbnail`)
- **Constants**: UPPER_SNAKE_CASE (e.g., `MAX_WORKERS`, `DEFAULT_TIMEOUT`)
- **Private**: Single underscore prefix (e.g., `_internal_method`)

## Docstrings
- Use docstring code formatting (enabled in ruff)
- Focus on "why" rather than "what"
- Include type information in signatures, not docstrings

## Qt Patterns
- **Signal-slot**: Loose coupling between components
- **QThread workers**: For background operations
- **Thread safety**: QMutex for shared data
- **Connection type**: `Qt.ConnectionType.QueuedConnection` for cross-thread signals
- **Resource cleanup**: Always call `quit()` and `wait()` on QThread

## Architecture Patterns
- **Generic bases**: Use `BaseItemModel[T]` for type-safe Qt models
- **Dependency injection**: Use factory pattern for testability
- **Separation of concerns**: Each tab has distinct data source and model
- **Type safety**: Explicit interfaces, zero conditional logic based on item type

## Current Status (Post-Ruff Setup)
- **126 automatic fixes applied** ✅
- **~1,100 violations remain** (down from 15,000+)
- **0 F-level errors** ✅
- **All tests passing** ✅
