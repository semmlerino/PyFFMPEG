# ShotBot - Project Guide

## Purpose

ShotBot is a PySide6-based GUI application for VFX shot browsing and application launching. It integrates with VFX pipeline tools using the `ws` (workspace) command to list and navigate shots. The application provides a visual interface for artists to browse shots, view thumbnails, and launch VFX applications (3DE, Nuke, Maya, RV) in the correct shot context.

## Key Features

- Visual shot browsing with thumbnail grid
- Three-tab interface:
  - **My Shots**: Current shots from `ws -sg` command
  - **Other 3DE Scenes**: Browse 3DE scenes created by other artists
  - **Previous Shots**: Historical shots from user's work
- Launch applications in shot context with proper environment
- Automatic thumbnail loading with multi-format support (JPEG, EXR, PIL)
- Resizable thumbnails with Ctrl+scroll zoom
- Dark theme optimized for VFX workflows
- Show filtering across all tabs
- Background refresh with change detection

## Security Context

This is a **personal VFX pipeline tool running on a secure, isolated network**. Security hardening is NOT a concern. Focus on functionality, performance, and VFX workflow optimization.

## Environment Support

- **Production mode**: Requires VFX environment with `ws` command
- **Mock mode**: Full development environment with 432 production shots simulated
- **Headless mode**: For CI/CD with Qt offscreen rendering

---

## Technology Stack

### Core Technologies

- **Python**: 3.11+ (uses modern union syntax `str | None`)
- **GUI Framework**: PySide6 (Qt for Python)
- **Package Manager**: uv (fast Python package/project manager)

### Key Dependencies

- **PySide6** >= 6.0.0 - Qt GUI framework
- **psutil** >= 5.9.0 - Process and system utilities
- **Pillow** >= 10.0.0 - Image processing
- **Jinja2** >= 3.0.0 - Template engine (for Nuke scripts)
- **OpenEXR** >= 1.3.0 - EXR image support for VFX thumbnails
- **olefile** >= 0.46 - OLE file format support
- **typing_extensions** >= 4.0.0 - Python 3.11 compatibility (@override decorator)

### Development Tools

- **pytest** >= 8.0.0 - Testing framework
- **pytest-qt** >= 4.0.0 - Qt testing support
- **pytest-xdist** >= 3.8.0 - Parallel test execution
- **pytest-timeout** >= 2.0.0 - Test timeout management
- **hypothesis** >= 6.0.0 - Property-based testing
- **ruff** >= 0.1.0 - Fast Python linter and formatter
- **basedpyright** >= 1.31.0 - Type checker (recommended mode)

---

## Development Commands

### Environment Setup

```bash
# Initial setup (creates .venv, installs dependencies)
uv sync

# Add a dependency
uv add package-name

# Add a development dependency
uv add --dev package-name
```

### Running the Application

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

### Testing

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

### Code Quality

```bash
# Format code (auto-fix)
uv run ruff format .

# Lint and auto-fix issues
uv run ruff check --fix .

# Type checking
uv run basedpyright
```

### Mock VFX Environment

```bash
# Recreate VFX filesystem structure (11,386 dirs, 29,335 files)
uv run python recreate_vfx_structure.py vfx_structure_complete.json

# Verify mock environment
uv run python verify_mock_environment.py

# Run with full mock environment
uv run python run_mock_vfx_env.py
```

### System Utilities

Standard Linux commands work normally:
- `git` - Version control
- `ls`, `cd` - File navigation
- `grep`, `find` - File search
- `cat`, `less` - File viewing
