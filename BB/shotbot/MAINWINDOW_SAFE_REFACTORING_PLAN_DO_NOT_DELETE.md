# Safe MainWindow Refactoring Plan - DO NOT DELETE

## Analysis Complete: MainWindow Method Groups Identified

After analyzing the 1,965-line MainWindow class with 50+ methods, I've identified **5 distinct controller extraction opportunities** with clear risk levels and extraction order.

## Method Group Analysis

### Group 1: Settings Controller (SAFEST - Start Here)
**Risk Level: LOW** 🟢
**Methods to Extract:**
- `_load_settings()` (line 1571)
- `_save_settings()` (line 1617)
- `_apply_ui_settings()` (line 1809)
- `_apply_cache_settings()` (line 1830)
- `_apply_dark_theme()` (line 1848)
- `_show_preferences()` (line 1854)
- `_on_settings_applied()` (line 1868)
- `_import_settings()` (line 1894)
- `_export_settings()` (line 1917)
- `_reset_layout()` (line 1938)

**Why Safest:**
- Well-contained functionality
- Clear interface with SettingsManager
- No complex signal chains
- Easy to mock/test
- Non-critical for core app functionality

### Group 2: UI Setup Controller (LOW-MEDIUM Risk)
**Risk Level: LOW-MEDIUM** 🟡
**Methods to Extract:**
- `_setup_ui()` (line 254)
- `_setup_menu()` (line 370)
- `_setup_accessibility()` (line 457)

**Why Second:**
- Called once during initialization
- Creates widgets but doesn't manage ongoing state
- Clear separation of concerns
- Easy to test in isolation

### Group 3: 3DE Scene Controller (MEDIUM Risk)
**Risk Level: MEDIUM** 🟠
**Methods to Extract:**
- `_refresh_threede_scenes()` (line 660)
- `_on_threede_discovery_started()` (line 772)
- `_on_threede_discovery_progress()` (line 781)
- `_on_threede_discovery_finished()` (line 808)
- `_on_threede_discovery_error()` (line 912)
- `_on_threede_batch_ready()` (line 931)
- `_on_threede_scan_progress()` (line 945)
- `_on_threede_discovery_paused()` (line 966)
- `_on_threede_discovery_resumed()` (line 970)
- `_on_scene_selected()` (line 1151)
- `_on_scene_double_clicked()` (line 1186)
- `_launch_app_with_scene()` (line 1250)
- `_launch_app_with_scene_context()` (line 1258)

**Complex Signal Chains:**
- ThreeDESceneWorker signals → UI updates
- Progress reporting through multiple signals
- Thread coordination required

### Group 4: Shot Management Controller (HIGH Risk)
**Risk Level: HIGH** 🔴
**Methods to Extract:**
- `_refresh_shots()` (line 647)
- `_refresh_shot_display()` (line 976)
- `_on_shots_loaded()` (line 982)
- `_on_shots_changed()` (line 993)
- `_on_refresh_started()` (line 1004)
- `_on_refresh_finished()` (line 1009)
- `_on_shot_error()` (line 1047)
- `_trigger_previous_shots_refresh()` (line 1056)
- `_on_model_shot_selected()` (line 1074)
- `_on_shot_selected()` (line 1089)
- `_on_shot_double_clicked()` (line 1147)
- `_on_show_filter_requested()` (line 1192)

**Why High Risk:**
- Core app functionality
- Complex model-view interactions
- Multiple signal chains
- Cache interactions

### Group 5: Launcher Coordinator (HIGHEST Risk)
**Risk Level: HIGHEST** 🔴🔴
**Methods to Extract:**
- `_launch_app()` (line 1206)
- `_on_launcher_started()` (line 1384)
- `_on_launcher_finished()` (line 1390)
- `_show_launcher_manager()` (line 1440)
- `_update_launcher_menu()` (line 1450)
- `_update_launcher_menu_availability()` (line 1511)
- `_execute_custom_launcher()` (line 1523)
- `_update_custom_launcher_buttons()` (line 1648)
- `_enable_custom_launcher_buttons()` (line 1655)

**Why Highest Risk:**
- Critical user-facing functionality
- Complex process management
- Terminal integration
- Race condition potential

## Safe Extraction Strategy

### Phase 1: Settings Controller (Week 1)
**Target**: Extract settings management into `SettingsController`

**Approach:**
1. Create `SettingsController` class with constructor accepting widget references
2. Move all `_*settings*` and `_*preferences*` methods
3. Create interface protocol: `SettingsTarget` with required widget properties
4. Implement controller as composition, not inheritance
5. Add comprehensive unit tests for settings persistence

**Interface Design:**
```python
class SettingsController:
    def __init__(self,
                 settings_manager: SettingsManager,
                 main_window: SettingsTarget) -> None:
        self.settings_manager = settings_manager
        self.window = main_window

    def load_settings(self) -> None:
        # Move _load_settings logic here

    def save_settings(self) -> None:
        # Move _save_settings logic here
```

**Success Criteria:**
- All existing settings tests pass
- No regression in settings persistence
- Clean separation of concerns

### Phase 2: UI Setup Controller (Week 2)
**Target**: Extract UI creation into `UISetupController`

**Approach:**
1. Create `UISetupController` with methods returning created widgets
2. Extract setup methods to return widget references instead of setting instance variables
3. MainWindow calls controller and stores returned widgets
4. Ensure all widget references are properly maintained

**Interface Design:**
```python
class UISetupController:
    @staticmethod
    def setup_main_ui(parent: QMainWindow) -> tuple[QSplitter, QTabWidget, ...]:
        # Return all created widgets for parent to store

    @staticmethod
    def setup_menu_bar(parent: QMainWindow) -> QMenuBar:
        # Create and return menu bar
```

### Phase 3: 3DE Scene Controller (Week 3)
**Target**: Extract 3DE functionality into `ThreeDEController`

**Approach:**
1. Create controller with clear signal interface
2. Connect controller signals to MainWindow slots
3. Pass required view/model references to controller
4. Maintain existing thread safety patterns

**Critical Considerations:**
- Preserve all signal connections
- Maintain thread safety with QMutex patterns
- Keep worker thread management intact
- Ensure progress reporting continues working

### Phase 4: Shot Management Controller (Week 4)
**Target**: Extract shot management into `ShotController`

**Most Complex Extraction:**
- Multiple model interactions (ShotModel, ShotItemModel)
- Cache manager integration
- Previous shots coordination
- Filter management

**Approach:**
1. Create controller with all required model references
2. Carefully preserve signal-slot chains
3. Maintain cache integration points
4. Extensive testing of all shot workflows

### Phase 5: Launcher Coordinator (Week 5)
**Target**: Extract launcher functionality into `LauncherCoordinator`

**Final Extraction:**
- Complex process management
- Terminal integration via PersistentTerminalManager
- Custom launcher management
- Menu state management

## Implementation Principles

### 1. Composition Over Inheritance
All controllers will be composed into MainWindow, not inherited from it.

### 2. Clear Interfaces
Each controller will define Protocol interfaces for their dependencies.

### 3. Signal Preservation
All existing Qt signal-slot connections must be maintained exactly.

### 4. Incremental Testing
Each extraction must pass all existing tests before proceeding.

### 5. Rollback Strategy
Keep original methods commented out until extraction is proven stable.

## Mediator Pattern Implementation

After all controllers are extracted, implement `MainWindowMediator`:

```python
class MainWindowMediator:
    def __init__(self,
                 settings: SettingsController,
                 ui_setup: UISetupController,
                 threede: ThreeDEController,
                 shots: ShotController,
                 launcher: LauncherCoordinator) -> None:
        # Coordinate between controllers
        # Handle cross-controller communication
```

## Risk Mitigation

1. **Feature Flags**: Toggle between old/new implementations during transition
2. **Backup Strategy**: Keep original methods until fully proven
3. **Test Coverage**: Comprehensive testing at each extraction step
4. **Incremental Deployment**: Extract one controller at a time
5. **Signal Monitoring**: Verify all signals still connect properly

## Success Metrics

- **Code Size**: MainWindow reduced from 1,965 lines to <500 lines
- **Method Count**: MainWindow methods reduced from 50+ to <15
- **Test Coverage**: All existing 106 test files continue passing
- **Performance**: No degradation in startup time or responsiveness
- **Maintainability**: Each controller can be developed/tested independently

---
*Plan Created: 2025-01-14*
*Next Review: After Phase 1 Completion*