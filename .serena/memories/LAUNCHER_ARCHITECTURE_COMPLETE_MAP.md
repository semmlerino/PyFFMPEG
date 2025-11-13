# Shotbot Application Launching System - Complete Map

## Overview

**⚠️ CRITICAL: SimplifiedLauncher is broken (missing Rez/workspace setup, parameter bugs, no thread safety) and will be removed soon. Use legacy CommandLauncher until fixed.**

Shotbot has a dual-launcher architecture: **SimplifiedLauncher (broken, will be removed)** vs **Legacy Launcher Stack (working, use this)**. This document comprehensively maps all launching-related code.

---

## 1. MAIN ENTRY POINTS

### 1.1 Primary Launcher in MainWindow
**File**: `/home/gabrielh/projects/shotbot/main_window.py`

**Class**: `MainWindow` (lines 176-1560)

**Key attributes (lines 310-350)**:
- `command_launcher`: Primary launcher interface (SimplifiedLauncher or CommandLauncher)
- `launcher_manager`: Custom launcher management (legacy only, None with SimplifiedLauncher)
- `persistent_terminal`: Terminal manager (legacy only, None with SimplifiedLauncher)
- `launcher_controller`: Controller managing launcher operations
- `launcher_panel`: UI for launching apps

**Feature flag (lines 298-328)**:
```python
use_simplified_launcher = os.environ.get("USE_SIMPLIFIED_LAUNCHER", "true").lower() == "true"
```
- **Default**: SimplifiedLauncher (true)
- **Fallback**: Legacy stack (set to false)

**Initialization logic**:
1. Check feature flag
2. If true: Create SimplifiedLauncher instance
3. If false: Create CommandLauncher + LauncherManager + PersistentTerminalManager (deprecated)

---

## 2. CURRENT DEFAULT: SIMPLIFIED LAUNCHER (⚠️ BROKEN - USE LEGACY INSTEAD)

**⚠️ WARNING: SimplifiedLauncher is broken and will be removed. Set `USE_SIMPLIFIED_LAUNCHER=false` to use working CommandLauncher.**

### 2.1 SimplifiedLauncher
**File**: `/home/gabrielh/projects/shotbot/simplified_launcher.py`

**Class**: `SimplifiedLauncher` (lines 38-609)

**Status**: BROKEN - Missing Rez/workspace integration, parameter forwarding bugs, no thread safety

**Description**: Attempted streamlined launcher (610 lines vs 3,153 lines for legacy) but critically incomplete

### 2.1.1 SimplifiedLauncher Flow Diagram

```
User Action
    ↓
LauncherController.launch_app("nuke")
    ↓
MainWindow.command_launcher.set_current_shot(shot)
    ↓
SimplifiedLauncher.launch_app()
    ├─→ _build_app_command()
    │   └─→ CommandBuilder (workspace integration)
    │
    ├─→ _get_app_environment()
    │   └─→ EnvironmentManager
    │
    ├─→ _find_latest_scene() (if 3DE)
    │   └─→ Cache + filesystem scan
    │
    ├─→ SimpleNukeLauncher (if Nuke)
    │   └─→ Script generation + setup
    │
    └─→ ProcessExecutor
        ├─→ _execute_in_terminal()
        │   └─→ Open new terminal + run command
        │
        └─→ _execute_background()
            └─→ Run without terminal

    ↓
Emit Signals:
├─→ command_executed
├─→ command_error
├─→ process_started
└─→ process_finished

    ↓
UI Updated
```

**Signals** (lines 50-53):
- `command_executed`: Command successfully executed
- `command_error`: Command failed
- `process_started`: Process started
- `process_finished`: Process finished

**Core methods**:
- `__init__()`: Initialize launcher with Nuke handler
- `set_current_shot(shot)`: Set context for launches (line 76)
- `launch_vfx_app(app_name, use_raw_plate=False, open_latest_3de=False)`: Main launch method (line 84)
- `launch_app()`: Legacy alias (line 593)
- `launch_app_with_scene()`: Launch with scene context (line 589)
- `execute_ws_command()`: Execute workspace command (line 229)
- `launch_custom_command()`: Execute custom launcher (line 285)

**Helper methods**:
- `_build_app_command()`: Build command for app (line 166)
- `_get_app_environment()`: Get environment vars (line 211)
- `_execute_in_terminal()`: Run in new terminal (line 314)
- `_execute_background()`: Run background process (line 343)
- `_find_latest_scene()`: Find latest 3DE scene (line 381)
- `_find_latest_nuke_workspace_script()`: Find latest Nuke workspace script (line 421)

**Process management**:
- `cleanup_processes()`: Cleanup terminated processes (line 466)
- `terminate_all_processes()`: Terminate all processes (line 483)
- `_active_processes`: Dict tracking active processes (line 66)

**Cache management** (workspace discovery):
- `_cache_get()`: Get cached workspace info (line 440)
- `_cache_set()`: Cache workspace info (line 455)
- `clear_cache()`: Clear cache (line 459)
- `invalidate_cache()`: Invalidate cache (line 550)
- `_ws_cache`: Workspace cache dict (line 60)
- `_ws_cache_ttl`: Cache TTL in seconds (line 63)

**Handlers**:
- `nuke_handler`: SimpleNukeLauncher instance (line 72)

**Internal state**:
- `current_shot`: Currently selected shot (line 69)

---

## 3. DEPRECATED LEGACY LAUNCHER STACK

### 3.1 CommandLauncher
**File**: `/home/gabrielh/projects/shotbot/command_launcher.py`

**Class**: `CommandLauncher` (lines 90-845)

**Status**: DEPRECATED - Set `USE_SIMPLIFIED_LAUNCHER=false` to use

**Description**: Complex legacy launcher with 756 lines

### 3.1.1 Legacy Launcher Flow Diagram

```
User Action
    ↓
LauncherController.launch_app("nuke")
    ↓
MainWindow.command_launcher.set_current_shot(shot)
    ↓
CommandLauncher.launch_app()
    ├─→ EnvironmentManager.build_environment()
    │
    ├─→ ProcessExecutor._execute_launch()
    │   ├─→ IF Config.PERSISTENT_TERMINAL_ENABLED:
    │   │   └─→ PersistentTerminalManager (send via FIFO)
    │   │
    │   └─→ ELSE:
    │       └─→ subprocess.Popen() + terminal
    │
    └─→ Emit Signals

    (Optional) LauncherManager.execute_launcher()
        ├─→ LauncherValidator.validate()
        ├─→ LauncherWorker (async execution)
        └─→ LauncherProcessManager (track processes)
```

**Signals** (lines 99-100):
- `command_executed`
- `command_error`

**Core methods**:
- `__init__()`: Initialize with terminal manager (line 102)
- `set_current_shot()`: Set current shot context (line 174)
- `launch_app()`: Main launch method (line 383)
- `launch_app_with_scene()`: Launch with scene (line 585)
- `launch_app_with_scene_context()`: Launch with full context (line 676)

**Internal execution**:
- `_try_persistent_terminal()`: Try persistent terminal (line 223)
- `_launch_in_new_terminal()`: Launch in new terminal (line 265)
- `_execute_launch()`: Execute launch command (line 360)
- `_validate_workspace_before_launch()`: Validate workspace (line 799)

**Dependencies** (lines 114-140):
- `env_manager`: EnvironmentManager instance
- `process_executor`: ProcessExecutor instance
- `nuke_handler`: SimpleNukeLauncher instance
- `persistent_terminal`: Optional terminal manager
- `_raw_plate_finder`, `_nuke_script_generator`, `_threede_latest_finder`, `_maya_latest_finder`

**Deprecation warning** (lines 5-17):
```
To use this legacy launcher, set environment variable: USE_SIMPLIFIED_LAUNCHER=false
```

### 3.2 LauncherManager
**File**: `/home/gabrielh/projects/shotbot/launcher_manager.py`

**Class**: `LauncherManager` (lines 63-679)

**Status**: DEPRECATED - Set `USE_SIMPLIFIED_LAUNCHER=false` to use

**Description**: Custom launcher management (617 lines)

#### 3.2.1 Custom Launcher Execution Flow (Legacy)

```
User Clicks Custom Launcher Button
    ↓
LauncherController.execute_custom_launcher(launcher_id)
    ↓
LauncherManager.execute_launcher(launcher_id)
    ├─→ LauncherValidator.validate_launcher_config()
    │   └─→ Validation errors → signal validation_error
    │
    ├─→ LauncherProcessManager.create_process()
    │   └─→ Create ProcessInfo record
    │
    ├─→ LauncherWorker (async execution)
    │   ├─→ Substitute environment variables
    │   ├─→ ProcessExecutor.run_command()
    │   ├─→ Monitor execution
    │   └─→ Track process
    │
    └─→ Emit Signals:
        ├─→ execution_started
        ├─→ command_started
        ├─→ command_output (if streaming)
        ├─→ command_finished
        └─→ execution_finished

    ↓
Clean Up Finished Workers
    └─→ _cleanup_finished_workers()
```

**Signals** (lines 75-87):
- `launchers_changed`, `launcher_added`, `launcher_updated`, `launcher_deleted`
- `validation_error`, `execution_started`, `execution_finished`
- `command_started`, `command_finished`, `command_error`, `command_output`

**Core methods**:
- `create_launcher()`: Create custom launcher (line 206)
- `update_launcher()`: Update launcher (line 300)
- `delete_launcher()`: Delete launcher (line 376)
- `get_launcher()`: Get by ID (line 394)
- `get_launcher_by_name()`: Get by name (line 405)
- `list_launchers()`: List all launchers (line 418)
- `execute_launcher()`: Execute custom launcher (line 473)
- `execute_in_shot_context()`: Execute in shot context (line 556)
- `validate_command_syntax()`: Validate command (line 439)
- `validate_launcher_config()`: Validate config (line 450)

**Process management**:
- `get_active_process_count()`: Count active processes (line 605)
- `get_active_process_info()`: Get process info (line 613)
- `terminate_process()`: Terminate specific process (line 621)
- `stop_all_workers()`: Stop all workers (line 633)
- `MAX_CONCURRENT_PROCESSES = 8` (line 90)

**Internal components** (lines 108-111):
- `_config_manager`: LauncherConfigManager instance
- `_repository`: LauncherRepository instance
- `_validator`: LauncherValidator instance
- `_process_manager`: LauncherProcessManager instance

**Deprecation warning** (lines 8-20)

### 3.3 PersistentTerminalManager
**File**: `/home/gabrielh/projects/shotbot/persistent_terminal_manager.py`

**Class**: `PersistentTerminalManager` (deprecated)

**Status**: DEPRECATED - Terminal feature, legacy only

**Components**:
- `TerminalOperationWorker`: Worker for terminal operations

**Configuration**:
- Requires FIFO path (Config.PERSISTENT_TERMINAL_FIFO)
- Config flags: Config.PERSISTENT_TERMINAL_ENABLED, Config.USE_PERSISTENT_TERMINAL

### 3.4 ProcessPoolManager
**File**: `/home/gabrielh/projects/shotbot/process_pool_manager.py`

**Class**: `ProcessPoolManager` (deprecated)

**Status**: DEPRECATED - Process pool singleton, legacy system

**Components**:
- `CommandCache`: Caches command results
- `ProcessMetrics`: Tracks process metrics

**Instance methods**:
- `get_instance()`: Get singleton
- `reset()`: Reset singleton (for testing)

**Deprecation warning** (lines 8-20)

---

## 4. LAUNCHER CONTROLLER

### 4.1 LauncherController
**File**: `/home/gabrielh/projects/shotbot/controllers/launcher_controller.py`

**Class**: `LauncherController` (lines 69-754)

**Description**: Coordinates launcher operations with UI

**Key methods**:
- `__init__()`: Initialize (line 89)
- `set_current_shot()`: Set shot context (line 146)
- `set_current_scene()`: Set 3DE scene context (line 168)
- `get_launch_options()`: Get available launch options (line 194)
- `launch_app()`: Launch application (line 355)
- `execute_custom_launcher()`: Execute custom launcher (line 469)
- `update_custom_launcher_buttons()`: Update UI buttons (line 520)
- `show_launcher_manager()`: Show launcher manager dialog (line 540)
- `update_launcher_menu()`: Update menu (line 565)
- `update_launcher_menu_availability()`: Update menu availability (line 628)

**Context management** (lines 96-103):
- `window`: Reference to MainWindow
- `_current_scene`: Current 3DE scene
- `_current_shot`: Current shot
- `_launcher_dialog`: Launcher manager dialog

**Signal handlers**:
- `_on_command_error()`: Handle command errors (line 647)
- `_on_launcher_started()`: Handle launch start (line 680)
- `_on_launcher_finished()`: Handle launch finish (line 692)

---

## 5. LAUNCHER MODELS & COMPONENTS

### 5.1 Launcher Subsystem Architecture Diagram

```
┌──────────────────────────────────────────────────────────────┐
│              LAUNCHER SUBMODULE (launcher/)                   │
├──────────────────────────────────────────────────────────────┤
│                                                                │
│  LauncherConfigManager ←→ ConfigData (Pydantic)               │
│      └─→ Load/save launcher configs                           │
│                                                                │
│  LauncherRepository                                            │
│      └─→ Persist custom launchers                             │
│                                                                │
│  LauncherValidator                                             │
│      ├─→ validate_command_syntax()                            │
│      └─→ validate_launcher_config()                           │
│                                                                │
│  LauncherProcessManager                                        │
│      ├─→ create_process()                                      │
│      ├─→ get_active_processes()                               │
│      └─→ track_completion()                                   │
│                                                                │
│  LauncherWorker (QThread)                                      │
│      ├─→ Async command execution                              │
│      └─→ Process monitoring                                   │
│                                                                │
│  Models (launcher/models.py)                                   │
│      ├─→ CustomLauncher                                        │
│      ├─→ LauncherParameter                                    │
│      ├─→ ProcessInfo                                           │
│      └─→ ...other types                                        │
│                                                                │
│  result_types.py                                               │
│      ├─→ LauncherCreationResult                               │
│      ├─→ LauncherUpdateResult                                 │
│      └─→ LauncherExecutionResult                              │
└──────────────────────────────────────────────────────────────┘
```

### 5.2 Launcher Submodule (launcher/)
**Directory**: `/home/gabrielh/projects/shotbot/launcher/`

**Files and classes**:

#### launcher/models.py
**Classes**:
- `ProcessInfoDict`: Type definition for process info
- `ParameterType`: Enum for parameter types
- `LauncherParameter`: Parameter definition
- `LauncherValidation`: Validation result
- `LauncherTerminal`: Terminal configuration
- `LauncherEnvironment`: Environment configuration
- `CustomLauncher`: Custom launcher definition
- `ProcessInfo`: Process information

#### launcher/process_manager.py
**Class**: `LauncherProcessManager`
- Manages process lifecycle
- Tracks active processes

#### launcher/config_manager.py
**Class**: `LauncherConfigManager`
- **Constant**: `CONFIG_DIR_ENV_VAR`
- **Type**: `ConfigData` (Pydantic model)
- Loads/saves launcher configurations

#### launcher/validator.py
**Class**: `LauncherValidator`
- Validates launcher commands
- Validates configurations

#### launcher/repository.py
**Class**: `LauncherRepository`
- Stores/retrieves custom launchers
- Persistence layer

#### launcher/worker.py
**Class**: `LauncherWorker`
- Qt worker for async launcher execution
- Thread-safe execution

#### launcher/result_types.py
**Type aliases**:
- `Result`: Generic result type
- `LauncherCreationResult`
- `LauncherUpdateResult`
- `LauncherExecutionResult`

---

## 6. LAUNCH UTILITIES (launch/ submodule)

**Directory**: `/home/gabrielh/projects/shotbot/launch/`

### 6.0 Launch Utilities Architecture Diagram

```
┌──────────────────────────────────────────────────────────────┐
│              LAUNCH UTILITIES (launch/)                        │
├──────────────────────────────────────────────────────────────┤
│                                                                │
│  EnvironmentManager                                            │
│      ├─→ build_environment() → env dict                       │
│      ├─→ get_workspace_env() → workspace vars                 │
│      ├─→ get_vfx_tool_env() → tool-specific vars              │
│      └─→ Integration: workspace (ws) system                   │
│                                                                │
│  CommandBuilder                                                │
│      ├─→ build_command() → shell command string              │
│      ├─→ escape_path() → safe paths                           │
│      ├─→ build_ws_command() → workspace command              │
│      └─→ build_app_launch_cmd() → app command                │
│                                                                │
│  ProcessExecutor                                               │
│      ├─→ run_command() → execute command                      │
│      ├─→ IF Config.PERSISTENT_TERMINAL_ENABLED:              │
│      │   └─→ Use PersistentTerminalManager (FIFO)             │
│      ├─→ ELSE:                                                │
│      │   └─→ subprocess.Popen() + terminal                    │
│      └─→ Monitor process, emit signals                        │
│                                                                │
└──────────────────────────────────────────────────────────────┘
```

### 6.1 CommandBuilder
**File**: `/home/gabrielh/projects/shotbot/launch/command_builder.py`

**Class**: `CommandBuilder`
- Constructs shell commands for app launching
- Handles command escaping
- Integrates workspace (ws) commands

### 6.2 EnvironmentManager
**File**: `/home/gabrielh/projects/shotbot/launch/environment_manager.py`

**Class**: `EnvironmentManager`
- Manages environment variables for launches
- Sets up VFX tool environments
- Configures workspace integration

### 6.3 ProcessExecutor
**File**: `/home/gabrielh/projects/shotbot/launch/process_executor.py`

**Class**: `ProcessExecutor`
- Executes commands in terminal or background
- Handles persistent terminal (legacy)
- Monitors process execution
- Configuration-driven (uses Config.PERSISTENT_TERMINAL_ENABLED, Config.USE_PERSISTENT_TERMINAL)

---

## 7. NUKE-SPECIFIC LAUNCHING

### 7.0 Nuke Launch Flow Diagram

```
SimplifiedLauncher._build_app_command("nuke")
    ↓
nuke_handler = SimpleNukeLauncher()
    ↓
SimpleNukeLauncher.open_latest_script()
    ├─→ Find latest Nuke workspace script
    ├─→ _create_script_via_nuke_api()
    │   ├─→ Create base script
    │   ├─→ Add undistortion nodes (if raw plate)
    │   ├─→ Configure read nodes
    │   └─→ Save as new version
    │
    └─→ Return script path

    ↓
Build command:
    "nuke -x <script_path>"

    ↓
[Optional] NukeScriptGenerator features:
    ├─→ nuke_script_templates.py (template files)
    ├─→ nuke_undistortion_parser.py (undistortion data)
    ├─→ nuke_media_detector.py (media detection)
    ├─→ nuke_workspace_manager.py (workspace structure)
    ├─→ nuke_launch_router.py (launch routing)
    └─→ nuke_launch_handler.py (launch handling)
```

### 7.1 SimpleNukeLauncher
**File**: `/home/gabrielh/projects/shotbot/simple_nuke_launcher.py`

**Class**: `SimpleNukeLauncher` (lines 24-242)

**Description**: Minimal Nuke launcher (218 lines)

**Methods**:
- `open_latest_script()`: Open latest script (line 33)
- `_create_script_via_nuke_api()`: Create via API (line 100)
- `create_new_version()`: Create new script version (line 186)

### 7.2 Nuke Launch Handler
**File**: `/home/gabrielh/projects/shotbot/nuke_launch_handler.py`

**Description**: Handles Nuke-specific launching logic

### 7.3 Nuke Script Generator
**File**: `/home/gabrielh/projects/shotbot/nuke_script_generator.py`

**Class**: `NukeScriptGenerator`
- Generates Nuke scripts
- Adds undistortion nodes
- Configures raw plate reading

### 7.4 Nuke Workspace Manager
**File**: `/home/gabrielh/projects/shotbot/nuke_workspace_manager.py`

**Description**: Manages Nuke workspace/project structure

### 7.5 Nuke Launch Router
**File**: `/home/gabrielh/projects/shotbot/nuke_launch_router.py`

**Description**: Routes launches to correct Nuke instances

### 7.6 Nuke Script Templates
**File**: `/home/gabrielh/projects/shotbot/nuke_script_templates.py`

**Description**: Templates for Nuke script generation

### 7.7 Nuke Media Detector
**File**: `/home/gabrielh/projects/shotbot/nuke_media_detector.py`

**Description**: Detects media for Nuke launching

---

## 8. LAUNCHER UI COMPONENTS

### 8.1 LauncherPanel
**File**: `/home/gabrielh/projects/shotbot/launcher_panel.py`

**Classes**:
- `AppConfig`: Configuration for app launcher buttons
- `CheckboxConfig`: Configuration for option checkboxes
- `AppLauncherSection`: Section of launcher panel
- `LauncherPanel`: Main launcher UI panel

**Purpose**: UI for launching applications with options (raw plate, open 3DE, etc.)

### 8.2 LauncherDialog (manager UI)
**File**: `/home/gabrielh/projects/shotbot/launcher_dialog.py`

**Classes**:
- `LauncherListWidget`: List of custom launchers
- `LauncherPreviewPanel`: Preview panel
- `LauncherEditDialog`: Edit launcher dialog
- `LauncherManagerDialog`: Main manager dialog

**Purpose**: UI for creating/editing custom launchers

---

## 9. CONFIGURATION & SETTINGS

### 9.1 Config Module
**File**: `/home/gabrielh/projects/shotbot/config.py`

**Settings for launching** (lines 117-125):
```python
PERSISTENT_TERMINAL_ENABLED: bool = (os.getenv("PERSISTENT_TERMINAL_ENABLED", "false").lower() == "true")
USE_PERSISTENT_TERMINAL: bool = (os.getenv("USE_PERSISTENT_TERMINAL", "false").lower() == "true")
PERSISTENT_TERMINAL_FIFO: str = "/tmp/shotbot_commands.fifo"
PERSISTENT_TERMINAL_TITLE: str = "ShotBot Terminal"
```

### 9.2 Environment Variables

**Feature flag**:
- `USE_SIMPLIFIED_LAUNCHER` (default: "true")
  - true = Use SimplifiedLauncher (new default)
  - false = Use legacy stack (CommandLauncher, LauncherManager, etc.)

**Persistent terminal** (legacy):
- `PERSISTENT_TERMINAL_ENABLED` (default: "false")
- `USE_PERSISTENT_TERMINAL` (default: "false")

**Other**:
- `SHOTBOT_MOCK`: Mock mode for testing
- `SHOTBOT_NO_INITIAL_LOAD`: Skip initial shot load

---

## 10. TESTING STRUCTURE

### 10.0 Testing Architecture Overview

```
TESTS/UNIT/ (Isolated component testing)
├─→ test_simplified_launcher_nuke.py
├─→ test_simplified_launcher_maya.py
├─→ test_command_launcher.py
├─→ test_command_launcher_properties.py
├─→ test_command_launcher_threading.py
├─→ test_launcher_manager.py
├─→ test_launcher_panel.py
├─→ test_launcher_dialog.py
├─→ test_launcher_worker.py
├─→ test_launcher_models.py
├─→ test_launcher_process_manager.py
├─→ test_launcher_validator.py
├─→ test_launcher_controller.py
└─→ test_simple_nuke_launcher.py

TESTS/INTEGRATION/ (Full workflow testing)
├─→ test_launcher_workflow_integration.py
│   └─→ Full launch pipeline (shot → app)
│
├─→ test_launcher_panel_integration.py
│   └─→ UI panel + launcher coordination
│
├─→ test_feature_flag_simplified.py
│   └─→ Feature flag behavior
│
├─→ test_main_window_coordination.py
│   └─→ MainWindow launcher setup + coordination
│
└─→ test_terminal_integration.py
    └─→ Terminal execution (legacy)
```

### 10.1 Unit Tests
**Directory**: `/home/gabrielh/projects/shotbot/tests/unit/`

**Launcher-related test files**:
- `test_simplified_launcher_nuke.py`: SimplifiedLauncher Nuke tests
- `test_simplified_launcher_maya.py`: SimplifiedLauncher Maya tests
- `test_command_launcher.py`: CommandLauncher tests
- `test_command_launcher_properties.py`: CommandLauncher properties
- `test_command_launcher_threading.py`: CommandLauncher threading
- `test_launcher_manager.py`: LauncherManager tests
- `test_launcher_panel.py`: LauncherPanel UI tests
- `test_launcher_dialog.py`: LauncherManagerDialog UI tests
- `test_launcher_worker.py`: LauncherWorker tests
- `test_launcher_models.py`: Launcher model tests
- `test_launcher_process_manager.py`: Process manager tests
- `test_launcher_validator.py`: Validator tests
- `test_launcher_controller.py`: Controller tests
- `test_simple_nuke_launcher.py`: SimpleNukeLauncher tests

### 10.2 Integration Tests
**Directory**: `/home/gabrielh/projects/shotbot/tests/integration/`

**Launcher-related test files**:
- `test_launcher_workflow_integration.py`: Full launcher workflow
- `test_launcher_panel_integration.py`: Launcher panel integration
- `test_feature_flag_simplified.py`: SimplifiedLauncher feature flag
- `test_main_window_coordination.py`: MainWindow launcher coordination
- `test_terminal_integration.py`: Terminal integration

---

## 11. ARCHITECTURE DIAGRAMS

### 11.1 Component Hierarchy (Detailed)

```
┌─────────────────────────────────────────────────────────────────┐
│                        MAINWINDOW                               │
│                                                                   │
│  cache_manager           shot_model         threede_controller   │
│  settings_manager        previous_shots     launcher_controller  │
│  refresh_orchestrator    models                                 │
├─────────────────────────────────────────────────────────────────┤
│  LAUNCHER SYSTEM (Feature Flag: USE_SIMPLIFIED_LAUNCHER)         │
│                                                                   │
│  IF true (DEFAULT):                    IF false (LEGACY):       │
│  ┌──────────────────────┐             ┌──────────────────────┐  │
│  │ SimplifiedLauncher   │             │   CommandLauncher    │  │
│  │ (610 lines)          │             │   (756 lines)        │  │
│  │ • launch_app()       │             │ • launch_app()       │  │
│  │ • launch_vfx_app()   │             │ • launch_app_with_   │  │
│  │ • execute_ws_cmd()   │             │   scene()            │  │
│  │ • process tracking   │             │ • _try_persistent_   │  │
│  │ • nuke_handler       │             │   terminal()         │  │
│  │ • Signals            │             │ • Signals            │  │
│  └──────────────────────┘             │ • env_manager        │  │
│   ↓                                   │ • process_executor   │  │
│  SimpleNukeLauncher                   │ • nuke_handler       │  │
│                                        └──────────────────────┘  │
│  launcher_manager = None               ↓                         │
│  persistent_terminal = None           LauncherManager           │
│                                        │ (617 lines)             │
│                                        │ • Custom launcher CRUD  │
│                                        │ • execute_launcher()    │
│                                        │ • Process management    │
│                                        │                         │
│                                        └─→ PersistentTerminal   │
│                                            Manager               │
│                                            (Terminal via FIFO)   │
│                                                                   │
├─────────────────────────────────────────────────────────────────┤
│ LauncherController (ALWAYS PRESENT)                              │
│ • Coordinates launcher operations with UI                       │
│ • set_current_shot()                                            │
│ • launch_app()                                                  │
│ • execute_custom_launcher()                                     │
│ • update_launcher_menu()                                        │
├─────────────────────────────────────────────────────────────────┤
│ UI Components                                                    │
│ • LauncherPanel: App launch buttons + options                   │
│ • LauncherManagerDialog: Custom launcher CRUD                   │
│ • launcher_panel: Shot filtering, info display                  │
└─────────────────────────────────────────────────────────────────┘
```

### 11.2 Simplified Component Tree

```
MAINWINDOW
├─ command_launcher: SimplifiedLauncher (default) OR CommandLauncher (legacy)
│  ├─ set_current_shot()
│  ├─ launch_app()
│  ├─ launch_app_with_scene()
│  └─ Signals: command_executed, command_error
│
├─ launcher_manager: LauncherManager (legacy only, None with SimplifiedLauncher)
│  ├─ Custom launcher CRUD
│  ├─ Execution management
│  ├─ Process tracking
│  └─ Signals: launchers_changed, execution_started, etc.
│
├─ launcher_controller: LauncherController (ALWAYS present)
│  ├─ set_current_shot()
│  ├─ set_current_scene()
│  ├─ launch_app()
│  ├─ execute_custom_launcher()
│  ├─ update_launcher_menu()
│  └─ Coordinates between UI and launcher
│
├─ launcher_panel: LauncherPanel (UI)
│  └─ App launcher buttons with options
│
├─ persistent_terminal: PersistentTerminalManager (legacy only)
│  └─ Terminal communication via FIFO
│
└─ threede_controller: ThreeDEController
   └─ Manages 3DE scene discovery/selection
```

---

## 12. SIGNAL FLOW DIAGRAMS

### 12.1 SimplifiedLauncher Signals

```
SimplifiedLauncher SIGNALS:
├─→ command_executed(command: str, result: int)
├─→ command_error(error: str)
├─→ process_started(pid: int, command: str)
└─→ process_finished(pid: int, return_code: int)
```

### 12.2 Legacy Launcher Signals

```
CommandLauncher SIGNALS:
├─→ command_executed(command: str, result: int)
└─→ command_error(error: str)

LauncherManager SIGNALS:
├─→ launchers_changed()
├─→ launcher_added(id: str)
├─→ launcher_updated(id: str)
├─→ launcher_deleted(id: str)
├─→ validation_error(error: str)
├─→ execution_started(launcher_id: str)
├─→ execution_finished(launcher_id: str)
├─→ command_started(launcher_id: str)
├─→ command_finished(launcher_id: str)
├─→ command_error(error: str)
└─→ command_output(output: str)

LauncherController RESPONDS TO:
├─→ launcher.command_executed
├─→ launcher.command_error
├─→ launcher_manager.execution_started
└─→ launcher_manager.execution_finished
```

### 12.3 Process Lifecycle Diagram

```
launch_app() call
    ↓
Create command string
    ├─→ Environment setup
    ├─→ Path resolution
    └─→ Command building
    ↓
Execute command
    ├─→ Terminal/background selection
    ├─→ Process.Popen() or FIFO write
    └─→ PID tracking
    ↓
Track process
    ├─→ Monitor execution
    ├─→ Capture output/errors
    └─→ Store in active_processes dict
    ↓
Signal emission
    ├─→ command_executed / command_error
    ├─→ process_started / process_finished
    └─→ UI updates
    ↓
Process cleanup
    ├─→ Remove from active_processes
    ├─→ Close file handles
    └─→ Log execution metrics
```

### 12.4 Shot Context Flow

```
MainWindow._on_shot_selected(shot)
    ↓
LauncherController.set_current_shot(shot)
    │
    ├─→ Update LauncherController._current_shot
    ├─→ Update SimplifiedLauncher.current_shot OR
    │   CommandLauncher.set_current_shot()
    │
    └─→ Update LauncherPanel display
            └─→ Show shot info
            └─→ Enable/disable buttons
                ↓
User clicks "Launch"
    ↓
LauncherController.launch_app()
    ├─→ Validate current shot
    ├─→ Build launch context
    │   ├─→ Shot: ShotModel (name, path, etc)
    │   ├─→ Scene: Optional 3DE scene
    │   └─→ Options: Raw plate, open 3DE, etc
    │
    └─→ SimplifiedLauncher.launch_vfx_app()
        └─→ Use current_shot for environment setup
```

## 12. KEY RELATIONSHIPS

### SimplifiedLauncher flow:
1. MainWindow creates SimplifiedLauncher (feature flag true)
2. LauncherController coordinates launches
3. SimplifiedLauncher receives launch request
4. Executes command via EnvironmentManager + ProcessExecutor
5. Emits signals for UI feedback

### Legacy launcher flow:
1. MainWindow creates CommandLauncher (feature flag false)
2. MainWindow creates LauncherManager
3. MainWindow creates PersistentTerminalManager (if enabled)
4. LauncherController coordinates launches
5. CommandLauncher receives launch request
6. Uses ProcessExecutor (which uses PersistentTerminalManager if enabled)
7. Emits signals for UI feedback

### Custom launcher flow:
1. LauncherController receives custom launcher request
2. Validates via LauncherValidator
3. Executes via LauncherManager.execute_launcher()
4. Uses LauncherWorker for async execution
5. Emits execution signals

---

## 13. WORKSPACE (WS) INTEGRATION

**Purpose**: VFX production workspace management system

**SimplifiedLauncher integration**:
- `execute_ws_command()`: Execute workspace commands (line 229)
- `_cache_get()`: Cache workspace discovery (line 440)
- `_find_latest_nuke_workspace_script()`: Find scripts (line 421)

**EnvironmentManager integration**:
- Sets up workspace environment variables
- Configures workspace for launches

**CommandBuilder integration**:
- Builds ws commands for app launching

---

## 14. DEPRECATION TIMELINE

**2025-11-12 Phase 1** (CURRENT):
- SimplifiedLauncher set as default
- Legacy modules emit deprecation warnings
- Both systems functional

**2025-11-12 Phase 2**:
- Integration tests updated for both launchers
- Legacy system maintained for backward compatibility

**Future**:
- Legacy modules will be archived/removed

---

## 15. FILE PATHS SUMMARY

### Active (Current Default)
```
/home/gabrielh/projects/shotbot/simplified_launcher.py
/home/gabrielh/projects/shotbot/simple_nuke_launcher.py
/home/gabrielh/projects/shotbot/launcher_panel.py
/home/gabrielh/projects/shotbot/launcher_dialog.py
/home/gabrielh/projects/shotbot/controllers/launcher_controller.py

/home/gabrielh/projects/shotbot/launch/
  ├── command_builder.py
  ├── environment_manager.py
  ├── process_executor.py
  └── __init__.py

/home/gabrielh/projects/shotbot/launcher/
  ├── models.py
  ├── process_manager.py
  ├── config_manager.py
  ├── validator.py
  ├── repository.py
  ├── worker.py
  ├── result_types.py
  └── __init__.py
```

### Deprecated (Legacy)
```
/home/gabrielh/projects/shotbot/command_launcher.py
/home/gabrielh/projects/shotbot/launcher_manager.py
/home/gabrielh/projects/shotbot/persistent_terminal_manager.py
/home/gabrielh/projects/shotbot/process_pool_manager.py
```

### Nuke Integration
```
/home/gabrielh/projects/shotbot/nuke_launch_handler.py
/home/gabrielh/projects/shotbot/nuke_script_generator.py
/home/gabrielh/projects/shotbot/nuke_workspace_manager.py
/home/gabrielh/projects/shotbot/nuke_launch_router.py
/home/gabrielh/projects/shotbot/nuke_script_templates.py
/home/gabrielh/projects/shotbot/nuke_media_detector.py
```

---

## 16. QUICK REFERENCE: KEY ENTRY POINTS

| Action | Code Path |
|--------|-----------|
| Launch Nuke | MainWindow.launcher_controller.launch_app("nuke") |
| Launch Maya | MainWindow.launcher_controller.launch_app("maya") |
| Launch 3DEqualizer | MainWindow.launcher_controller.launch_app("3de") |
| Launch with scene | LauncherController._launch_app_with_scene() |
| Custom launcher | LauncherController.execute_custom_launcher() |
| Launcher manager UI | LauncherController.show_launcher_manager() |
| Set shot context | LauncherController.set_current_shot() |
| Set scene context | LauncherController.set_current_scene() |

---

## 17. FEATURE FLAG USAGE

### 17.1 Decision Tree: Which Launcher?

```
                    User clicks "Launch Nuke"
                              ↓
                    Check USE_SIMPLIFIED_LAUNCHER
                              ↓
                     ┌────────┴────────┐
                     ↓                 ↓
                  true            false
                  ↓                 ↓
           SimplifiedLauncher  CommandLauncher
           • ⚠️ BROKEN          • Working
           • Will be removed   • Use this
           • DO NOT USE        • Production ready
           • Default (BAD)     • Recommended
                 ↓
           NukeHandler selection
                 ↓
          SimpleNukeLauncher
           (218 lines)
```

**RECOMMENDATION: Set `USE_SIMPLIFIED_LAUNCHER=false` until SimplifiedLauncher is fixed or removed.**

### 17.2 Implementation

**In code** (main_window.py lines 298-328):
```python
use_simplified_launcher = os.environ.get("USE_SIMPLIFIED_LAUNCHER", "true").lower() == "true"

if use_simplified_launcher:
    from simplified_launcher import SimplifiedLauncher
    self.command_launcher = SimplifiedLauncher()
    self.launcher_manager = None
    self.persistent_terminal = None
else:
    # Legacy stack (deprecated)
    self.persistent_terminal = PersistentTerminalManager(...)
    self.command_launcher = CommandLauncher(...)
    self.launcher_manager = LauncherManager(...)
```

**To use working launcher (RECOMMENDED)**:
```bash
export USE_SIMPLIFIED_LAUNCHER=false
python shotbot.py
```

---

End of Launcher Architecture Map
