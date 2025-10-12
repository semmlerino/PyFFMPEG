# Task Completion Checklist

When completing a task, run these commands in order:

## 1. Format Code
```bash
uv run ruff format .
```
Auto-formats all Python files to match project style.

## 2. Lint and Fix Issues
```bash
uv run ruff check --fix .
```
Checks for code quality issues and auto-fixes when possible.

## 3. Type Checking
```bash
uv run basedpyright
```
Verifies type annotations and catches type errors.

## 4. Run Tests
```bash
# Quick test run (recommended for most changes)
uv run pytest tests/unit/ -n auto --timeout=5

# Full test suite (if making significant changes)
uv run pytest tests/ -n auto
```

## Known Issues
- Sequential test execution may timeout due to Qt resource accumulation
- 2-3 tests fail in parallel mode due to isolation issues (pass individually)
- **Always use parallel execution** (`-n auto`) for best results

## Important Notes
- **Test markers**: Use appropriate markers (`@pytest.mark.fast`, `@pytest.mark.unit`, etc.)
- **Type hints**: All public APIs must have complete type annotations
- **Thread safety**: Use QMutex for any shared state
- **Resource cleanup**: Always clean up QThread workers and Qt widgets
- **Import rule**: ALWAYS `from typing_extensions import override` (not `typing`)

## Optional (for major changes)
```bash
# Test specific categories
uv run pytest tests/ -m fast        # Fast tests only
uv run pytest tests/ -m integration # Integration tests

# Coverage report
uv run pytest --cov=. --cov-report=html
```
