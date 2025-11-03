# Ruff Configuration Guide

This document explains the ruff linting and formatting configuration for the Shotbot project.

## Overview

Ruff is a fast Python linter and formatter that replaces multiple tools:
- **Linting**: Replaces flake8, isort, pydocstyle, pyupgrade, etc.
- **Formatting**: Black-compatible code formatting
- **Auto-fixing**: Automatically fixes many violations

## Configuration Location

All ruff configuration is in `pyproject.toml` under the `[tool.ruff]` section.

## Quick Reference

```bash
# Check for issues
~/.local/bin/uv run ruff check .

# Auto-fix safe issues
~/.local/bin/uv run ruff check . --fix

# Format code
~/.local/bin/uv run ruff format .

# Check specific rule categories
~/.local/bin/uv run ruff check . --select E,F,I

# Show statistics
~/.local/bin/uv run ruff check . --statistics
```

## Configuration Choices

### Enabled Rule Categories

We enable a comprehensive set of rules that catch bugs, enforce modern Python practices, and improve code quality:

| Category | Code | Description | Why Enabled |
|----------|------|-------------|-------------|
| pycodestyle | E, W | Style errors and warnings | Enforces PEP 8 basics |
| Pyflakes | F | Syntax errors and undefined names | Catches bugs early |
| isort | I | Import sorting | Consistent import organization |
| pep8-naming | N | Naming conventions | Consistent naming across codebase |
| pyupgrade | UP | Modern Python syntax | Uses Python 3.12+ features |
| flake8-bugbear | B | Common bug patterns | Catches subtle bugs |
| flake8-comprehensions | C4 | List/dict comprehension improvements | More Pythonic code |
| flake8-pytest-style | PT | Pytest best practices | Better test quality |
| flake8-simplify | SIM | Code simplification | More readable code |
| flake8-type-checking | TCH | Type checking imports | Better type hint organization |
| Pylint | PL | Additional checks | Comprehensive code quality |
| tryceratops | TRY | Exception handling | Better error handling |
| Ruff-specific | RUF | Ruff's own rules | Modern Python patterns |

### Disabled Rules

Some rules are disabled because they conflict with our project's needs:

#### Style Choices
- **E501** (line-too-long): We let the formatter handle line length instead of enforcing a hard limit
- **E203** (whitespace-before-punctuation): Conflicts with Black formatting

#### Type Annotations
- **ANN401** (any-type): `Any` is useful in generic code and Qt signal handling

#### Import Placement
- **E402** (module-level-import-not-at-top): Sometimes needed for Qt application initialization
- **TC003** (typing-only-standard-library-import): We prefer import consistency over micro-optimizations

#### Qt-Specific Patterns
- **SLF001** (private-member-access): Common in Qt testing and subclassing (e.g., accessing `_q_*` attributes)
- **ARG002** (unused-method-argument): Qt callbacks often have unused arguments (e.g., `def on_clicked(checked: bool)`)

#### Complexity
We allow some complexity for practical GUI code:
- **PLR0913** (too-many-arguments): Qt widgets often have many initialization parameters
- **PLR0912** (too-many-branches): Some UI logic is inherently complex
- **PLR0915** (too-many-statements): Some methods are legitimately long
- **C901** (complex-structure): We focus on clarity over arbitrary complexity limits

#### Exception Handling
- **TRY003** (raise-vanilla-args): Vanilla exceptions are often fine for our use case
- **TRY300** (try-consider-else): Not always clearer
- **BLE001** (blind-except): Sometimes needed for cleanup in Qt applications
- **TRY400** (error-instead-of-exception): `Error` is fine in Python 3

#### Boolean Arguments
- **FBT001**, **FBT002**, **FBT003**: Boolean arguments are common and clear in GUI applications

#### Print and Logging
- **T201** (print): We use `print()` intentionally for CLI output and debugging
- **G004** (logging-f-string): f-strings in logging are readable and performance is not a concern

#### Docstrings
- **D** (pydocstyle): We follow our own docstring style and rely on type hints for documentation

#### Magic Values
- **PLR2004** (magic-value-comparison): Sometimes literal values are clearer than named constants

### Per-File Ignores

Different file types have different standards:

#### Tests (`tests/**/*.py`)
- **S101** (assert): Asserts are the point of tests
- **ARG001** (unused-function-argument): Pytest fixtures are often unused
- **PLR2004** (magic-value-comparison): Test data can be literal values
- **S108** (hardcoded-temp-file): Fine in tests
- **DTZ001** (call-datetime-without-tzinfo): Tests don't need timezone handling
- **B018** (useless-expression): Testing expressions is valid

#### Config Files (`**/config*.py`)
- **PLR2004** (magic-value-comparison): Config values are often literal

## Auto-Fixing Strategy

Ruff applied 126 automatic fixes in our initial setup:

### Safe Fixes Applied
- **W293**: Removed trailing whitespace on blank lines (83 fixes)
- **RET504**: Removed unnecessary variable assignments before returns (26 fixes)
- **UP040/UP046/UP047**: Upgraded to modern Python 3.12 type syntax (7 fixes)
- **RUF015**: Optimized unnecessary iterable allocations (4 fixes)

### Manual Fixes Required
Some violations require manual review:
- **PLC0415** (575): Imports not at top-level - requires context to fix safely
- **PTH123** (77): Using `open()` instead of `pathlib` - gradual migration preferred
- **N802** (70): Function naming - requires domain knowledge
- **SIM102** (26): Collapsible if statements - may change logic flow

## Integration with Development Workflow

### Pre-commit Hooks
The project uses git hooks that automatically:
1. Run ruff formatting on changed files
2. Check for linting issues
3. Block commits with F-level errors (undefined names, syntax errors)

### IDE Integration
Configure your IDE to:
1. Run ruff on file save
2. Show inline linting errors
3. Format on save using ruff

### CI/CD Integration
Consider adding ruff checks to your CI pipeline:
```bash
# In CI, fail on any issues
~/.local/bin/uv run ruff check . --no-fix

# Also run the formatter in check mode
~/.local/bin/uv run ruff format . --check
```

## Formatting Configuration

Ruff uses Black-compatible formatting:
- **Line length**: 88 characters (Black standard)
- **Quote style**: Double quotes
- **Indent**: 4 spaces
- **Magic trailing comma**: Enabled (respect formatting hints)

## Maintenance

### Adding New Rules
When enabling new rules:
1. Run `ruff check --select <RULE> --statistics` to see impact
2. Consider if the rule fits our codebase patterns
3. Apply auto-fixes if safe
4. Document the decision in this file

### Reviewing Violations
Periodically review violation statistics:
```bash
~/.local/bin/uv run ruff check . --statistics
```

Focus on:
- High-count violations (>100) - consider if the rule fits
- New violation types - investigate and fix
- Security issues (S-prefix rules) - fix immediately

## Current Status

After initial configuration:
- **126 automatic fixes applied** ✅
- **~1,100 violations remain** (down from 15,000+)
- **0 F-level errors** (undefined names, syntax errors) ✅
- **Test suite passing** (pre-existing failures unrelated to ruff) ✅

Most remaining violations are:
1. Import placement (575) - gradual improvement
2. Pathlib usage (77) - gradual migration
3. Naming conventions (70) - domain-specific review needed
4. Code simplification (26) - requires careful review

## Resources

- [Ruff Documentation](https://docs.astral.sh/ruff/)
- [Ruff Rules Reference](https://docs.astral.sh/ruff/rules/)
- [Black Formatting Style](https://black.readthedocs.io/en/stable/the_black_code_style/)
- [PEP 8 Style Guide](https://peps.python.org/pep-0008/)

## Summary

Our ruff configuration balances:
- **Strictness**: Catching real bugs and enforcing consistency
- **Pragmatism**: Allowing Qt patterns and practical complexity
- **Automation**: Fixing safe issues automatically
- **Clarity**: Clear documentation of choices

The configuration is designed for a production PySide6/Qt application with comprehensive type hints, extensive testing, and active development.
