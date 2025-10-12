# Suggested Development Commands

## Environment Setup
```bash
# Initial setup (creates .venv, installs dependencies)
uv sync

# Add a dependency
uv add package-name

# Add a development dependency
uv add --dev package-name
```

## Running the Application
```bash
# Production mode (requires VFX environment)
uv run python shotbot.py

# Mock mode (no VFX infrastructure needed - 432 production shots)
uv run python shotbot.py --mock

# Better: with recreated VFX filesystem
uv run python shotbot_mock.py

# Headless mode (for CI/CD)
uv run python shotbot.py --headless --mock

# Debug mode
SHOTBOT_DEBUG=1 uv run python shotbot.py
```

## Testing
```bash
# Recommended: Full test suite with parallel execution (~67 seconds)
uv run pytest tests/unit/ -n auto --timeout=5

# Quick validation
uv run python tests/utilities/quick_test.py

# Specific test file
uv run pytest tests/unit/test_shot_model.py -v

# Test categories
uv run pytest tests/ -m fast       # Tests under 100ms
uv run pytest tests/ -m unit       # Unit tests only
uv run pytest tests/ -m integration # Integration tests
```

## Code Quality
```bash
# Format code (auto-fix)
uv run ruff format .

# Lint and auto-fix issues
uv run ruff check --fix .

# Type checking
uv run basedpyright
```

## Mock VFX Environment
```bash
# Recreate VFX filesystem structure (11,386 dirs, 29,335 files)
uv run python recreate_vfx_structure.py vfx_structure_complete.json

# Verify mock environment
uv run python verify_mock_environment.py

# Run with full mock environment
uv run python run_mock_vfx_env.py
```

## System Utilities
Standard Linux commands work normally:
- `git` - Version control
- `ls`, `cd` - File navigation
- `grep`, `find` - File search
- `cat`, `less` - File viewing
