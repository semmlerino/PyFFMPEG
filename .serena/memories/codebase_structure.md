# Codebase Structure

## Entry Points
- **shotbot.py** - Main application entry point
- **shotbot_mock.py** - Mock mode entry point with VFX filesystem
- **main_window.py** - MainWindow class and UI composition

## Core Architecture

### Controllers (Model coordination)
- **controllers/launcher_controller.py** - Application launching coordination
- **controllers/settings_controller.py** - Settings management
- **controllers/threede_controller.py** - 3DE-specific functionality

### Launcher System
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

## Testing
- **tests/unit/** - Unit tests (~1,047 tests)
- **tests/integration/** - Integration tests
- **tests/fixtures/** - Test fixtures
- **tests/conftest.py** - Pytest configuration
- **tests/test_doubles.py** - Mock objects and test helpers

## Key Design Patterns
- Each tab has **distinct data source** and model stack
- **Generic base classes** reduce duplication (70-80%)
- **Explicit implementations** avoid conditional logic
- **Worker pattern** for background operations
- **Dependency injection** for testability
