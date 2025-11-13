# ShotBot - Development Standards

## Codebase Structure

### Entry Points

- **shotbot.py** - Main application entry point
- **shotbot_mock.py** - Mock mode entry point with VFX filesystem
- **main_window.py** - MainWindow class and UI composition

### Core Architecture

#### Controllers (Model coordination)

- **controllers/launcher_controller.py** - Application launching coordination
- **controllers/settings_controller.py** - Settings management
- **controllers/threede_controller.py** - 3DE-specific functionality

#### Launcher System

- **launcher/worker.py** - Command execution worker
- **launcher/process_manager.py** - Process lifecycle management
- **launcher/validator.py** - Command validation
- **launcher/models.py** - Domain models
- **launcher/repository.py** - Process state storage
- **launcher/result_types.py** - Result type definitions

### Model Layer (Three Distinct Data Sources)

**My Shots Tab** (Workspace Integration):
- **shot_model.py** - BaseShotModel: `ws -sg` command execution
- **shot_item_model.py** - ShotItemModel: Qt model with lazy thumbnails
- **shot_grid_view.py** - ShotGridView: Custom view and delegate

**Other 3DE Scenes Tab** (Filesystem Discovery):
- **threede_scene_model.py** - ThreeDESceneModel: Manages discovered .3de files
- **threede_item_model.py** - ThreeDEItemModel: Filtered view with progressive loading
- **threede_grid_view.py** - ThreeDEGridView: Custom delegate for scene metadata
- **threede_scene_worker.py** - QThread for non-blocking filesystem scan

**Previous Shots Tab** (Historical Data):
- **previous_shots_model.py** - PreviousShotsModel: Finds user's approved/completed shots
- **previous_shots_item_model.py** - PreviousShotsItemModel: Filters out active shots
- **previous_shots_view.py** - Display with auto-refresh timer
- **previous_shots_worker.py** - Background thread for filesystem traversal

### Base Classes (Shared Infrastructure)

- **base_item_model.py** - BaseItemModel[T]: Generic Qt model with lazy thumbnails
- **base_shot_model.py** - BaseShotModel: Common shot parsing and caching
- **base_grid_view.py** - Base grid view functionality
- **base_thumbnail_delegate.py** - Custom thumbnail rendering

### Utilities

- **cache_manager.py** - Simplified caching for thumbnails and data
- **process_pool_manager.py** - Singleton subprocess pool with caching
- **mock_workspace_pool.py** - Mock implementation (432 production shots)
- **config.py** - Configuration constants
- **utils.py** - Utility functions
- **optimized_shot_parser.py** - High-performance shot parsing

### UI Components

- **thumbnail_widget.py** - Thumbnail display widget
- **shot_info_panel.py** - Shot information display
- **launcher_panel.py** - Application launcher UI
- **log_viewer.py** - Command log viewer
- **settings_dialog.py** - Settings UI

### Finders (Domain-specific Discovery)

- **threede_scene_finder.py** - Find .3de files
- **threede_latest_finder.py** - Find latest 3DE scenes
- **previous_shots_finder.py** - Find user's previous shots
- **raw_plate_finder.py** - Find raw plates for Nuke
- **undistortion_finder.py** - Find undistortion data

### Nuke Integration

- **nuke_workspace_manager.py** - Nuke workspace setup
- **nuke_script_generator.py** - Generate Nuke scripts
- **nuke_script_templates.py** - Jinja2 templates
- **nuke_media_detector.py** - Media file detection
- **nuke_undistortion_parser.py** - Parse undistortion data

### Testing

- **tests/unit/** - Unit tests (~1,047 tests)
- **tests/integration/** - Integration tests
- **tests/fixtures/** - Test fixtures
- **tests/conftest.py** - Pytest configuration
- **tests/test_doubles.py** - Mock objects and test helpers

---

## Code Style & Conventions

### Python Version

- **Minimum**: Python 3.11
- **Target**: Python 3.11+
- **Type Syntax**: Modern union syntax (`str | None`, not `Optional[str]`)

### Critical Import Rule

**ALWAYS** import `override` from `typing_extensions`, NOT `typing`:

```python
# CORRECT (Python 3.11 compatible)
from typing_extensions import override

# WRONG (Python 3.12+ only - will fail!)
from typing import override
```

### Ruff Configuration

#### Quick Commands

```bash
# Check for issues
~/.local/bin/uv run ruff check .

# Auto-fix safe issues  
~/.local/bin/uv run ruff check . --fix

# Format code
~/.local/bin/uv run ruff format .
```

#### Formatting Standards

- **Line length**: 88 characters (Black-compatible)
- **Indent**: 4 spaces
- **Quote style**: Double quotes
- **Target**: Python 3.11+

#### Enabled Rule Categories

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

#### Key Disabled Rules

- **E501**: line-too-long (formatter handles it)
- **SLF001**: private-member-access (common in Qt)
- **ARG002**: unused-method-argument (Qt callbacks)
- **T201**: print statements (intentional use)
- **G004**: logging f-strings (readable and fine)
- **D**: pydocstyle (our own style)
- **PLR0913**: too-many-arguments (Qt widgets)
- **FBT001/002/003**: boolean arguments (common in GUI)

#### Test-Specific Rules

Tests ignore additional rules:
- **S101**: asserts (the point of tests)
- **ARG001**: unused fixtures
- **PLR2004**: magic values in test data

See `RUFF_CONFIGURATION.md` for full details and rationale.

### Type Annotations

- **Required**: All public functions and methods must have type hints
- **Mode**: basedpyright "recommended" mode
- **Strictness**: Error on unknown types, untyped base classes
- **Patterns**:
  - Optional types: `str | None`
  - Signal declarations: `Signal(str)`, `Signal(dict)`, `Signal()`
  - Qt enums: `Qt.ItemDataRole.UserRole` (not `Qt.UserRole`)

### Naming Conventions

- **Classes**: PascalCase (e.g., `ShotModel`, `MainWindow`)
- **Functions/Methods**: snake_case (e.g., `refresh_shots`, `load_thumbnail`)
- **Constants**: UPPER_SNAKE_CASE (e.g., `MAX_WORKERS`, `DEFAULT_TIMEOUT`)
- **Private**: Single underscore prefix (e.g., `_internal_method`)

### Docstrings

- Use docstring code formatting (enabled in ruff)
- Focus on "why" rather than "what"
- Include type information in signatures, not docstrings

### Qt Patterns

- **Signal-slot**: Loose coupling between components
- **QThread workers**: For background operations
- **Thread safety**: QMutex for shared data
- **Connection type**: `Qt.ConnectionType.QueuedConnection` for cross-thread signals
- **Resource cleanup**: Always call `quit()` and `wait()` on QThread

### Current Status (Post-Ruff Setup)

- **126 automatic fixes applied** ✅
- **~1,100 violations remain** (down from 15,000+)
- **0 F-level errors** ✅
- **All tests passing** ✅

---

## Architecture Patterns

### Key Design Principles

- **Distinct Data Sources**: Each tab has its own data source and model stack
- **Generic Base Classes**: `BaseItemModel[T]` reduces duplication (70-80%)
- **Explicit Implementations**: Avoid conditional logic based on item type
- **Type Safety**: Explicit interfaces throughout
- **Worker Pattern**: QThread workers for background operations
- **Dependency Injection**: Factory pattern for testability (e.g., ProcessPoolFactory)
- **Separation of Concerns**: Clear boundaries between model, view, controller
- **Model-View**: Qt's signal-slot mechanism for loose coupling
- **Singleton**: ProcessPoolManager for subprocess management
