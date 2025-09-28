# PLAN NUKE - Comprehensive Refactoring Strategy
**DO NOT DELETE - Master Plan Document**

## Executive Summary

The ShotBot codebase contains significant duplication in Nuke application launching:
- **1,847 lines** of duplicate launcher code (CommandLauncher: 1,172 + SimplifiedLauncher: 675)
- **1,794 lines** of specialized Nuke modules only used by CommandLauncher
- **566-line monolithic method** in CommandLauncher.launch_app
- **Inconsistent functionality** between launcher implementations

**Goal**: Consolidate Nuke launching into a single, modular implementation that:
- Reduces code by ~60% (eliminating ~1,100 lines)
- Reuses existing, well-tested Nuke modules
- Provides consistent functionality regardless of launcher choice
- Creates maintainable, testable components

## Part 1: Current State Analysis

### 1.1 Launcher Implementations

#### CommandLauncher (command_launcher.py - 1,172 lines)
- **Default implementation** (active unless USE_SIMPLIFIED_LAUNCHER=true)
- **11 methods**, average 106 lines each
- **launch_app method**: 566 lines (48% of file!)
- **Deep nesting**: Up to 10 levels of indentation
- **Uses all 5 Nuke modules** via imports

Key issues in launch_app (lines 280-846):
```
Lines 304-310: Validation logic
Lines 316-322: Nuke OCIO crash prevention setup
Lines 324-506: Nuke workspace scripts (182 lines)
Lines 508-661: Nuke raw plate/undistortion (153 lines)
Lines 663-690: 3DE latest scene (27 lines)
Lines 692-719: Maya latest scene (27 lines)
Lines 720-751: Command building with workspace
Lines 752-771: Rez environment wrapping
Lines 776-818: Persistent terminal execution
Lines 819-845: New terminal execution
```

#### SimplifiedLauncher (simplified_launcher.py - 675 lines)
- **Opt-in implementation** (USE_SIMPLIFIED_LAUNCHER=true)
- **27 methods**, average 25 lines each
- **Clean structure** with focused methods
- **DOES NOT use Nuke modules** - reimplements basic functionality
- **Placeholder Nuke support** (comment: "full script generation would be added if needed")

Nuke handling in SimplifiedLauncher (lines 150-163):
```python
elif app_name == "nuke":
    if options.get("open_latest") and shot:
        # Find and open latest Nuke script
        latest = self._find_latest_scene(shot.workspace_path, "nuke")
        if latest:
            command_parts.append(self._quote_path(latest))
    elif options.get("include_plate") and shot:
        # Create script with plate - simplified version
        plate = self._find_raw_plate(shot.workspace_path, shot.full_name)
        if plate:
            # For simplicity, just open Nuke - full script generation
            # would be added if needed
            self.logger.info(f"Found plate at: {plate}")
```

### 1.2 Specialized Nuke Modules (1,794 lines total)

These modules are **well-designed, tested, and production-ready**:

#### nuke_script_generator.py (578 lines)
- **Purpose**: Generate temporary Nuke scripts with proper Read nodes
- **Key methods**:
  - `create_plate_script()` - Creates script with plate Read node
  - `create_loader_script()` - Creates script with plate and undistortion
  - `create_workspace_plate_script()` - Creates workspace-aware script
  - `save_workspace_script()` - Saves script to workspace location
- **Features**: Temp file tracking, automatic cleanup via atexit
- **Used by**: CommandLauncher extensively (14 calls)

#### nuke_workspace_manager.py (233 lines)
- **Purpose**: Manage Nuke scripts in VFX pipeline workspace
- **Key methods**:
  - `get_workspace_script_directory()` - Get comp/nuke/<user> directory
  - `find_latest_nuke_script()` - Find latest version
  - `get_next_script_path()` - Calculate next version number
- **Used by**: CommandLauncher for workspace scripts (4 calls)

#### nuke_undistortion_parser.py (524 lines)
- **Purpose**: Parse and import 3DE undistortion .nk files
- **Key methods**:
  - `parse_undistortion_file()` - Main parsing method
  - `parse_standard_format()` - Standard .nk format
  - `parse_copy_paste_format()` - Copy/paste format
- **Features**: Complex regex parsing, node positioning
- **Used by**: nuke_script_generator internally

#### nuke_script_templates.py (300 lines)
- **Purpose**: Template-based Nuke script generation
- **Content**: XML layouts, node templates, script boilerplate
- **Used by**: nuke_script_generator for structured output

#### nuke_media_detector.py (159 lines)
- **Purpose**: Detect media properties
- **Key methods**:
  - `detect_frame_range()` - Analyze plate sequences
  - `detect_colorspace()` - Determine colorspace from path
  - `detect_resolution()` - Get resolution from path patterns
- **Used by**: nuke_script_generator for automatic settings

### 1.3 Test Coverage

**1,877 lines of tests** for Nuke modules:
- test_nuke_undistortion_parser.py: 522 lines
- test_nuke_script_templates.py: 362 lines
- test_nuke_media_detector.py: 358 lines
- test_nuke_script_generator.py: 348 lines
- test_nuke_3de_undistortion_import.py: 287 lines

This indicates the Nuke modules are **production-ready and well-tested**.

### 1.4 Module Import Analysis

**CommandLauncher imports**:
```python
from nuke_script_generator import NukeScriptGenerator  # Line 88
from nuke_workspace_manager import NukeWorkspaceManager  # Line 326
# Plus lazy imports of other modules
```

**SimplifiedLauncher imports**:
- **NONE** of the Nuke modules
- Reimplements basic functionality inline

## Part 2: Problem Analysis

### 2.1 Code Duplication
- **Two implementations** of the same functionality
- **1,847 lines total** for launching applications
- Only **ONE** can be active at a time (feature flag)

### 2.2 Wasted Specialized Modules
- **1,794 lines** of well-tested Nuke modules
- Only used by CommandLauncher
- SimplifiedLauncher reimplements (poorly) instead of reusing

### 2.3 Inconsistent Features
Depending on which launcher is active:
- **CommandLauncher**: Full Nuke support (workspace scripts, undistortion, plates)
- **SimplifiedLauncher**: Basic support (only opens existing scripts)

### 2.4 Maintenance Burden
- Bug fixes must be applied to BOTH implementations
- New features must be added to BOTH
- Testing must cover BOTH code paths

### 2.5 Monolithic Method Complexity
CommandLauncher.launch_app has:
- **566 lines** in a single method
- **10 levels** of nesting
- **Mixed responsibilities** (validation, Nuke, 3DE, Maya, execution)
- **16+ conditionals** checking app_name

## Part 3: Refactoring Strategy

### 3.1 Design Principles

1. **Single Source of Truth**: One implementation for each feature
2. **Modularity**: Separate concerns into focused components
3. **Reusability**: Leverage existing, tested modules
4. **Consistency**: Same features regardless of launcher choice
5. **Testability**: Each component independently testable

### 3.2 Target Architecture

```
┌─────────────────────────────────────┐
│         Application Launchers        │
├─────────────┬───────────────────────┤
│CommandLauncher│  SimplifiedLauncher  │
│  (updated)    │      (updated)       │
└──────┬────────┴──────────┬──────────┘
       │                   │
       ▼                   ▼
┌──────────────────────────────────────┐
│        NukeLaunchHandler (new)       │
│    Unified Nuke launching logic      │
└──────────────┬───────────────────────┘
               │
               ▼
┌──────────────────────────────────────┐
│    Existing Nuke Modules (reused)    │
├──────────────────────────────────────┤
│ • nuke_script_generator              │
│ • nuke_workspace_manager             │
│ • nuke_undistortion_parser           │
│ • nuke_script_templates              │
│ • nuke_media_detector                │
└──────────────────────────────────────┘
```

## Part 4: Implementation Plan

### Phase 1: Create NukeLaunchHandler (New File)

**File**: `nuke_launch_handler.py`

```python
"""Unified Nuke launching handler using existing specialized modules."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from logging_mixin import LoggingMixin
from nuke_script_generator import NukeScriptGenerator
from nuke_workspace_manager import NukeWorkspaceManager
from raw_plate_finder import RawPlateFinder
from undistortion_finder import UndistortionFinder
from config import Config

if TYPE_CHECKING:
    from shotbot_types import Shot


class NukeLaunchHandler(LoggingMixin):
    """Handles all Nuke-specific launching logic."""

    def __init__(self):
        """Initialize with all required Nuke modules."""
        self.script_generator = NukeScriptGenerator()
        self.workspace_manager = NukeWorkspaceManager()
        self.raw_plate_finder = RawPlateFinder()
        self.undistortion_finder = UndistortionFinder()

    def prepare_nuke_command(
        self,
        shot: Shot,
        base_command: str,
        options: dict
    ) -> tuple[str, list[str]]:
        """
        Prepare Nuke command with all options.

        Returns:
            Tuple of (command, log_messages)
        """
        log_messages = []
        command = base_command

        # Handle mutually exclusive paths
        if options.get("open_latest_scene") or options.get("create_new_file"):
            command, msgs = self._handle_workspace_scripts(
                shot, command, options
            )
            log_messages.extend(msgs)
        elif options.get("include_raw_plate") or options.get("include_undistortion"):
            command, msgs = self._handle_media_loading(
                shot, command, options
            )
            log_messages.extend(msgs)

        # Apply environment fixes
        if Config.NUKE_FIX_OCIO_CRASH:
            log_messages.append("Applied Nuke OCIO crash prevention")

        return command, log_messages

    def _handle_workspace_scripts(
        self,
        shot: Shot,
        command: str,
        options: dict
    ) -> tuple[str, list[str]]:
        """Handle workspace script creation/opening."""
        # Extract lines 324-506 from CommandLauncher
        # Use self.workspace_manager and self.script_generator
        ...

    def _handle_media_loading(
        self,
        shot: Shot,
        command: str,
        options: dict
    ) -> tuple[str, list[str]]:
        """Handle raw plate and undistortion loading."""
        # Extract lines 508-661 from CommandLauncher
        # Use self.script_generator, self.raw_plate_finder, etc.
        ...

    def get_environment_fixes(self) -> str:
        """Get Nuke-specific environment fixes."""
        # Extract from _get_nuke_environment_fixes (lines 208-278)
        ...
```

### Phase 2: Extract App-Specific Methods from CommandLauncher

#### 2.1 Extract 3DE Handler (lines 663-690)

```python
def _prepare_3de_command(
    self,
    command: str,
    options: dict
) -> tuple[str, list[str]]:
    """Prepare 3DE command with latest scene if requested."""
    log_messages = []

    if options.get("open_latest_threede") and self.current_shot:
        latest_scene = self._threede_latest_finder.find_latest_threede_scene(
            self.current_shot.workspace_path,
            self.current_shot.full_name,
        )
        if latest_scene:
            try:
                safe_scene_path = self._validate_path_for_shell(str(latest_scene))
                command = f"{command} -open {safe_scene_path}"
                log_messages.append(f"Opening latest 3DE scene: {latest_scene.name}")
            except ValueError as e:
                log_messages.append(f"Warning: Invalid 3DE scene path: {str(e)}")
        else:
            log_messages.append("Info: No 3DE scene files found in workspace")

    return command, log_messages
```

#### 2.2 Extract Maya Handler (lines 692-719)

```python
def _prepare_maya_command(
    self,
    command: str,
    options: dict
) -> tuple[str, list[str]]:
    """Prepare Maya command with latest scene if requested."""
    log_messages = []

    if options.get("open_latest_maya") and self.current_shot:
        latest_scene = self._maya_latest_finder.find_latest_maya_scene(
            self.current_shot.workspace_path,
            self.current_shot.full_name,
        )
        if latest_scene:
            try:
                safe_scene_path = self._validate_path_for_shell(str(latest_scene))
                command = f"{command} -file {safe_scene_path}"
                log_messages.append(f"Opening latest Maya scene: {latest_scene.name}")
            except ValueError as e:
                log_messages.append(f"Warning: Invalid Maya scene path: {str(e)}")
        else:
            log_messages.append("Info: No Maya scene files found in workspace")

    return command, log_messages
```

#### 2.3 Extract Command Execution (lines 720-845)

```python
def _execute_command(
    self,
    command: str,
    app_name: str,
    workspace_path: str,
    env_fixes: str = ""
) -> bool:
    """Execute command with workspace setup and terminal handling."""
    # Build workspace command
    safe_workspace_path = self._validate_path_for_shell(workspace_path)
    ws_command = f"ws {safe_workspace_path} && {env_fixes}{command}"

    # Wrap with rez if available
    if self._is_rez_available():
        rez_packages = self._get_rez_packages_for_app(app_name)
        if rez_packages:
            packages_str = " ".join(rez_packages)
            full_command = f'rez env {packages_str} -- bash -ilc "{ws_command}"'
        else:
            full_command = f'bash -ilc "{ws_command}"'
    else:
        full_command = ws_command

    # Try persistent terminal first
    if self.persistent_terminal and Config.USE_PERSISTENT_TERMINAL:
        # Lines 776-818
        ...

    # Fall back to new terminal
    # Lines 819-845
    ...
```

### Phase 3: Refactor CommandLauncher.launch_app

**Current**: 566 lines
**Target**: ~50 lines

```python
def launch_app(
    self,
    app_name: str,
    include_undistortion: bool = False,
    include_raw_plate: bool = False,
    open_latest_threede: bool = False,
    open_latest_maya: bool = False,
    open_latest_scene: bool = False,
    create_new_file: bool = False,
) -> bool:
    """Launch an application in the current shot context."""
    # Validation (lines 304-310)
    if not self.current_shot:
        self._emit_error("No shot selected")
        return False

    if app_name not in Config.APPS:
        self._emit_error(f"Unknown application: {app_name}")
        return False

    # Get base command
    command = Config.APPS[app_name]
    log_messages = []
    env_fixes = ""

    # Prepare command based on app type
    options = {
        "include_undistortion": include_undistortion,
        "include_raw_plate": include_raw_plate,
        "open_latest_threede": open_latest_threede,
        "open_latest_maya": open_latest_maya,
        "open_latest_scene": open_latest_scene,
        "create_new_file": create_new_file,
    }

    if app_name == "nuke":
        command, msgs = self.nuke_handler.prepare_nuke_command(
            self.current_shot, command, options
        )
        log_messages.extend(msgs)
        env_fixes = self.nuke_handler.get_environment_fixes()
    elif app_name == "3de":
        command, msgs = self._prepare_3de_command(command, options)
        log_messages.extend(msgs)
    elif app_name == "maya":
        command, msgs = self._prepare_maya_command(command, options)
        log_messages.extend(msgs)

    # Emit log messages
    for msg in log_messages:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.command_executed.emit(timestamp, msg)

    # Execute command
    return self._execute_command(
        command,
        app_name,
        self.current_shot.workspace_path,
        env_fixes
    )
```

### Phase 4: Update SimplifiedLauncher

Replace placeholder Nuke code with NukeLaunchHandler:

```python
# In SimplifiedLauncher.__init__
def __init__(self):
    super().__init__()
    self.nuke_handler = NukeLaunchHandler()  # Add this
    ...

# In _build_command method (around line 150)
elif app_name == "nuke":
    # OLD: Basic placeholder implementation
    # if options.get("open_latest") and shot:
    #     latest = self._find_latest_scene(shot.workspace_path, "nuke")
    #     ...

    # NEW: Use unified handler
    nuke_options = {
        "open_latest_scene": options.get("open_latest"),
        "create_new_file": options.get("create_new"),
        "include_raw_plate": options.get("include_plate"),
        "include_undistortion": options.get("include_undistortion"),
    }
    command, _ = self.nuke_handler.prepare_nuke_command(
        shot, command, nuke_options
    )
```

### Phase 5: Testing Strategy

#### 5.1 Unit Tests
- Test NukeLaunchHandler methods independently
- Mock the Nuke modules to test integration
- Verify command building logic

#### 5.2 Integration Tests
- Test both launchers produce identical commands
- Verify feature parity between implementations
- Test with mock filesystem

#### 5.3 Regression Tests
- Ensure all existing Nuke module tests still pass
- Verify backward compatibility
- Test with real VFX environment (if available)

### Phase 6: Final Consolidation

After successful testing:

1. **Remove feature flag** from main_window.py
2. **Deprecate CommandLauncher** (keep for reference)
3. **Make SimplifiedLauncher the default**
4. **Clean up duplicate code**

Expected structure:
```
simplified_launcher.py (enhanced)  # ~800 lines
├── Uses NukeLaunchHandler         # ~300 lines
├── Uses existing Nuke modules     # 1,794 lines (unchanged)
└── Clean, modular structure       # 27 focused methods
```

## Part 5: Implementation Timeline

### Week 1: Foundation
- [ ] Create NukeLaunchHandler class
- [ ] Extract workspace script handling
- [ ] Extract media loading logic
- [ ] Write unit tests for handler

### Week 2: CommandLauncher Refactoring
- [ ] Extract _prepare_3de_command
- [ ] Extract _prepare_maya_command
- [ ] Extract _execute_command
- [ ] Refactor launch_app to use handlers
- [ ] Test CommandLauncher still works

### Week 3: SimplifiedLauncher Integration
- [ ] Add NukeLaunchHandler to SimplifiedLauncher
- [ ] Replace placeholder Nuke code
- [ ] Test feature parity
- [ ] Run integration tests

### Week 4: Consolidation
- [ ] Performance testing
- [ ] Documentation updates
- [ ] Remove feature flag
- [ ] Deploy and monitor

## Part 6: Success Metrics

### Code Quality Metrics
- **Lines of Code**: Reduce by ~1,100 lines (60% reduction)
- **Method Length**: No method >50 lines (from 566)
- **Nesting Depth**: Maximum 3 levels (from 10)
- **Duplication**: Zero duplicate Nuke logic

### Functional Metrics
- **Feature Parity**: 100% identical functionality
- **Test Coverage**: Maintain or improve current coverage
- **Performance**: No regression in launch times
- **Reliability**: No new bugs introduced

### Maintenance Metrics
- **Time to Add Feature**: Reduced by 50% (single implementation)
- **Time to Fix Bug**: Reduced by 50% (single location)
- **Code Review Time**: Reduced (cleaner structure)
- **Onboarding Time**: Reduced (simpler to understand)

## Part 7: Risk Mitigation

### Risks and Mitigations

1. **Risk**: Breaking existing functionality
   - **Mitigation**: Comprehensive test suite before changes
   - **Mitigation**: Feature flag allows rollback

2. **Risk**: Performance regression
   - **Mitigation**: Benchmark before/after
   - **Mitigation**: Profile critical paths

3. **Risk**: Missed edge cases
   - **Mitigation**: Thorough code analysis
   - **Mitigation**: Gradual rollout with monitoring

4. **Risk**: User workflow disruption
   - **Mitigation**: No external API changes
   - **Mitigation**: Identical behavior guaranteed

## Part 8: Future Enhancements

After successful consolidation:

1. **Create handlers for other apps** (Houdini, Katana, etc.)
2. **Plugin architecture** for custom launchers
3. **Async launching** with progress feedback
4. **Launch profiles** for different scenarios
5. **Launch history** and quick re-launch

## Appendix A: File Mappings

### Current Files to Refactored Structure

| Current File | Lines | Refactored Location | Expected Lines |
|-------------|-------|-------------------|----------------|
| command_launcher.py | 1,172 | Multiple files | ~400 |
| - launch_app method | 566 | Split across handlers | ~50 |
| - Nuke logic | 335 | NukeLaunchHandler | ~300 |
| - 3DE logic | 27 | _prepare_3de_command | ~30 |
| - Maya logic | 27 | _prepare_maya_command | ~30 |
| - Execution logic | 125 | _execute_command | ~100 |
| simplified_launcher.py | 675 | Enhanced with handlers | ~800 |
| nuke_script_generator.py | 578 | Unchanged (reused) | 578 |
| nuke_workspace_manager.py | 233 | Unchanged (reused) | 233 |
| nuke_undistortion_parser.py | 524 | Unchanged (reused) | 524 |
| nuke_script_templates.py | 300 | Unchanged (reused) | 300 |
| nuke_media_detector.py | 159 | Unchanged (reused) | 159 |
| **NEW: nuke_launch_handler.py** | 0 | New unified handler | ~300 |
| **TOTAL** | 3,641 | **After refactoring** | ~2,524 |

**Net reduction: ~1,117 lines (31% less code)**

## Appendix B: Code Examples

### B.1 Complete NukeLaunchHandler._handle_workspace_scripts

```python
def _handle_workspace_scripts(
    self,
    shot: Shot,
    command: str,
    options: dict
) -> tuple[str, list[str]]:
    """
    Handle workspace script creation/opening.
    Extracted from CommandLauncher lines 324-506.
    """
    log_messages = []

    # Note: open_latest_scene takes priority
    if options.get("open_latest_scene") and options.get("create_new_file"):
        options["create_new_file"] = False

    if options.get("open_latest_scene"):
        # Try to find existing script
        script_dir = self.workspace_manager.get_workspace_script_directory(
            shot.workspace_path
        )
        latest_script = self.workspace_manager.find_latest_nuke_script(
            script_dir, shot.full_name
        )

        if latest_script:
            # Open existing script
            safe_script_path = shlex.quote(str(latest_script))
            command = f"{command} {safe_script_path}"
            log_messages.append(f"Opening existing Nuke script: {latest_script.name}")
        else:
            # No existing script, create v001
            log_messages.append("No existing Nuke scripts found, creating v001...")
            saved_path = self._create_new_workspace_script(
                shot, version=1, options=options
            )
            if saved_path:
                command = f"{command} {shlex.quote(saved_path)}"
                log_messages.append(f"Created new Nuke script: {Path(saved_path).name}")
            else:
                log_messages.append("Failed to create Nuke script")
                return command, log_messages

    elif options.get("create_new_file"):
        # Always create new version
        script_dir = self.workspace_manager.get_workspace_script_directory(
            shot.workspace_path
        )
        _, version = self.workspace_manager.get_next_script_path(
            script_dir, shot.full_name
        )

        saved_path = self._create_new_workspace_script(
            shot, version=version, options=options
        )
        if saved_path:
            command = f"{command} {shlex.quote(saved_path)}"
            log_messages.append(f"Created Nuke script v{version:03d}")
        else:
            log_messages.append("Failed to create Nuke script")

    return command, log_messages

def _create_new_workspace_script(
    self,
    shot: Shot,
    version: int,
    options: dict
) -> str | None:
    """Create a new workspace script with optional plate."""
    if options.get("include_raw_plate"):
        raw_plate_path = self.raw_plate_finder.find_latest_raw_plate(
            shot.workspace_path, shot.full_name
        )
        if raw_plate_path and self.raw_plate_finder.verify_plate_exists(raw_plate_path):
            return self.script_generator.create_workspace_plate_script(
                raw_plate_path,
                shot.workspace_path,
                shot.full_name,
                version=version
            )

    # Create empty script
    script_content = self.script_generator.create_plate_script(
        "", shot.full_name
    )
    if script_content:
        return self.script_generator.save_workspace_script(
            script_content,
            shot.workspace_path,
            shot.full_name,
            version=version
        )

    return None
```

## Appendix C: Testing Checklist

### Pre-Refactoring Tests
- [ ] Run all existing tests, document baseline
- [ ] Create integration test for current behavior
- [ ] Benchmark current performance
- [ ] Document all Nuke features in both launchers

### During Refactoring Tests
- [ ] Unit test each extracted method
- [ ] Integration test after each phase
- [ ] Compare output with baseline
- [ ] Performance regression tests

### Post-Refactoring Tests
- [ ] Full regression test suite
- [ ] Feature parity validation
- [ ] Performance comparison
- [ ] User acceptance testing
- [ ] Production deployment test

## Conclusion

This comprehensive refactoring plan will:
1. **Eliminate ~1,100 lines** of duplicate code
2. **Reduce complexity** from 566-line methods to 50-line methods
3. **Leverage existing** well-tested Nuke modules
4. **Provide consistency** across launcher implementations
5. **Improve maintainability** with modular design
6. **Enable future** consolidation into a single launcher

The plan is designed to be **implemented incrementally** with **minimal risk** and **maximum code reuse**.

---
**Document Version**: 1.0
**Date**: 2024
**Status**: APPROVED FOR IMPLEMENTATION
**DO NOT DELETE** - This is the master refactoring plan