# Code Style and Conventions

## Python Version
- **Minimum**: Python 3.11
- **Type Syntax**: Modern union syntax (`str | None`, not `Optional[str]`)

## Critical Import Rule
**ALWAYS** import `override` from `typing_extensions`, NOT `typing`:
```python
# CORRECT (Python 3.11 compatible)
from typing_extensions import override

# WRONG (Python 3.12+ only - will fail!)
from typing import override
```

## Code Formatting (Ruff)
- **Line length**: 88 characters (Black-compatible)
- **Indent**: 4 spaces
- **Quote style**: Double quotes
- **Target**: Python 3.11+

## Type Annotations
- **Required**: All public functions and methods must have type hints
- **Mode**: basedpyright "recommended" mode
- **Strictness**: Error on unknown types, untyped base classes
- **Patterns**:
  - Optional types: `str | None`
  - Signal declarations: `Signal(str)`, `Signal(dict)`, `Signal()`
  - Qt enums: `Qt.ItemDataRole.UserRole` (not `Qt.UserRole`)

## Linting Rules (Ruff)
- **Enabled**: E, F (pycodestyle, Pyflakes), I (isort), UP (pyupgrade), TCH (type-checking), ANN (annotations)
- **Ignored**: E501 (line length), ANN401 (Any in *args/**kwargs), TC003 (stdlib imports)
- **Auto-fix**: All fixable rules enabled

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
