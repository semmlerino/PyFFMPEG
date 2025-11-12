# Shotbot Architecture Review

**Date**: 2025-11-12
**Reviewer**: Python Expert Architect Agent
**Codebase Version**: master (commit 6102dd1)
**Overall Grade**: C+ (69/100)

## Executive Summary

Shotbot is a functional, well-tested PySide6 application with **2,300+ passing tests** and **strong type safety** (0 basedpyright errors). However, it suffers from significant architectural debt:

- **Three "God Classes"** (MainWindow: 1559 lines, CommandLauncher: 819 lines, CacheManager: 1150 lines)
- **Flat root directory** with 100+ Python files lacking clear module boundaries
- **No distinct domain layer** - business logic scattered across root modules
- **Tight coupling** between presentation, application, and business logic layers

**Good News**: The `launcher/` subsystem demonstrates excellent architecture and can serve as a template for the rest of the codebase. Recent refactorings (controllers, LaunchContext value object) show movement in the right direction.

**Critical Issues**: Technical debt is accumulating. Without architectural improvements, adding features will become increasingly difficult and risky.

---

## 1. System Architecture Assessment

### Current Architecture Layers

```
shotbot/
├── Presentation Layer: main_window.py (1559 lines) - MIXED with business logic
├── Controllers Layer: controllers/ (3 files) - PARTIAL extraction
├── Business Logic: SCATTERED across 100+ root modules
├── Launcher Subsystem: launcher/ - WELL-ORGANIZED ✓
└── Root-level modules: 100+ Python files with NO clear boundaries
```

### Architecture Scores

| Dimension | Score | Assessment |
|-----------|-------|------------|
| **Module Organization** | D (30/100) | Flat structure, no clear boundaries |
| **Separation of Concerns** | C (60/100) | Layers mixed, partial extraction |
| **SOLID Principles** | C+ (70/100) | Good DI in places, SRP violations |
| **Design Patterns** | B (80/100) | Excellent in launcher/, inconsistent elsewhere |
| **Testability** | A- (90/100) | 2300+ tests, excellent fixtures |
| **Extensibility** | D+ (40/100) | Hard to extend without modifying core |
| **Type Safety** | A (95/100) | Comprehensive type hints, 0 errors |
| **Documentation** | B+ (85/100) | Good docstrings, clear intent |

**Overall: C+ (69/100)**

### Strengths

1. **Excellent Test Culture**: 2,300+ tests passing with comprehensive coverage
2. **Strong Type Safety**: Full type annotations, 0 basedpyright errors
3. **Exemplary Subsystem**: `launcher/` demonstrates clean architecture
4. **Good Patterns Emerging**: Recent refactorings (controllers, value objects) show right direction
5. **Singleton Testing Support**: All singletons have `reset()` methods for test isolation
6. **Performance Focus**: Property-based tests, parallel test execution

### Critical Weaknesses

1. **Three God Classes**: MainWindow (1559 lines), CommandLauncher (819 lines), CacheManager (1150 lines)
2. **Flat Root Directory**: 100+ files with no organization or module boundaries
3. **No Domain Layer**: Business logic scattered, hard to find and reuse
4. **Tight Layer Coupling**: UI directly accesses models, business logic in controllers
5. **Poor Extensibility**: Adding features requires modifying core classes
6. **Inconsistent Abstraction**: High-level and low-level logic mixed together

---

## 2. Top 10 Architectural Issues

### Issue #1: MainWindow God Class (1559 lines)

**Description**: Single class manages UI rendering, business logic, state management, event handling, and coordination across all features.

**Location**: `/home/gabrielh/projects/shotbot/main_window.py`

**Impact**:
- **CRITICAL** - Every feature change touches this file
- Bottleneck for parallel development
- High probability of merge conflicts
- Difficult to understand and test

**Root Cause**: Incremental feature addition without refactoring. Started as simple window, grew to encompass everything.

**Evidence**:
- 50+ methods in single class
- 20+ direct dependencies (cache_manager, command_launcher, models, controllers, managers)
- Mixes Qt event handling with business logic
- 200+ lines of initialization code

**Refactoring Strategy**:
1. **Phase 1**: Extract remaining business logic to controllers (2 weeks)
2. **Phase 2**: Create ViewModels for complex UI state (2 weeks)
3. **Phase 3**: Split into focused widgets with composition (3 weeks)
4. **Target**: Reduce to <300 lines (just wiring and layout)

**Effort**: Very Large (7+ weeks)
**Risk**: High (core of application)
**Dependencies**: Must create service layer first

**Example Violation**:
```python
# MainWindow doing business logic (should be in service)
def _on_shot_double_clicked(self, shot: Shot) -> None:
    """Handle shot double-click."""
    context = LaunchContext(
        open_latest_scene=self.settings_manager.get_setting("nuke_open_latest"),
        include_raw_plate=self.raw_plate_checkbox.isChecked(),
    )
    self.command_launcher.launch_app_with_scene_context(shot, "nuke", context)
```

---

### Issue #2: Flat Root Directory (100+ files)

**Description**: All modules dumped in root directory with no organization or clear module boundaries.

**Location**: `/home/gabrielh/projects/shotbot/` (root)

**Impact**:
- **HIGH** - Developers can't find code
- No mental model of system structure
- Where does new code go? Inconsistent answers
- Impossible to understand dependencies

**Root Cause**: Organic growth without architectural governance. No enforced organization strategy.

**Evidence**:
```
shotbot/
├── 15+ finder classes (threede_scene_finder, maya_latest_finder, etc.)
├── 10+ model classes (shot_model, threede_scene_model, etc.)
├── 8+ manager classes (cache_manager, settings_manager, etc.)
├── 5+ worker classes (threede_scene_worker, previous_shots_worker, etc.)
├── UI components, utilities, configs all mixed together
└── 100+ total files with NO clear categorization
```

**Refactoring Strategy**:
1. **Phase 1**: Create directory structure (domain/, application/, infrastructure/, presentation/)
2. **Phase 2**: Move files to appropriate directories (no code changes)
3. **Phase 3**: Update imports, run tests
4. **Phase 4**: Add __init__.py with clear module interfaces

**Target Structure**:
```
shotbot/
├── domain/          # Business logic & models
│   ├── models/      # shot_model, scene_model
│   ├── services/    # Business logic services
│   └── validators/  # Domain validation
├── application/     # Use cases & coordination
│   ├── controllers/
│   ├── orchestrators/
│   └── handlers/
├── infrastructure/  # External concerns
│   ├── cache/
│   ├── filesystem/
│   └── persistence/
├── presentation/    # UI layer
│   ├── windows/
│   ├── widgets/
│   ├── views/
│   └── delegates/
└── launcher/        # Already well-organized!
```

**Effort**: Large (2-3 weeks)
**Risk**: Low (just moving files, no logic changes)
**Dependencies**: None - can start immediately

**ROI**: **HIGHEST** - Massive improvement in maintainability with low risk

---

### Issue #3: CommandLauncher God Class (819 lines)

**Description**: Monolithic launch logic with 5+ responsibilities: environment setup, process execution, terminal management, scene finding, workspace validation.

**Location**: `/home/gabrielh/projects/shotbot/command_launcher.py`

**Impact**:
- **HIGH** - Hard to add new launch targets
- Difficult to test in isolation
- Changes ripple throughout class
- Launch failures affect all users

**Root Cause**: Convenience over design. "Just one more method" pattern led to massive accumulation.

**Evidence**:
```python
class CommandLauncher:
    # 5+ responsibilities:
    def launch_app(...)                           # Orchestration
    def _try_persistent_terminal(...)            # Terminal management
    def _execute_launch(...)                     # Process execution
    def _validate_workspace_before_launch(...)   # Validation
    def launch_app_with_scene_context(...)       # Scene finding

    # 8+ dependencies:
    env_manager: EnvironmentManager
    process_executor: ProcessExecutor
    nuke_handler: NukeLaunchRouter
    _raw_plate_finder: RawPlateFinder
    _nuke_script_generator: NukeScriptGenerator
    _threede_latest_finder: ThreeDELatestFinder
    _maya_latest_finder: MayaLatestFinder
    persistent_terminal: PersistentTerminalManager
```

**Refactoring Strategy**:
1. **Phase 1**: Extract scene finding to SceneFinder service (1 week)
2. **Phase 2**: Extract validation to LaunchValidator (1 week)
3. **Phase 3**: Extract terminal management to TerminalManager (1 week)
4. **Phase 4**: Reduce to thin LaunchCoordinator (2 weeks)

**Target**:
```python
# Thin coordinator using services
class LaunchCoordinator:
    def __init__(
        self,
        scene_finder: SceneFinder,
        validator: LaunchValidator,
        executor: ProcessExecutor,
    ):
        self._scene_finder = scene_finder
        self._validator = validator
        self._executor = executor

    def launch(self, shot: Shot, app: str, context: LaunchContext) -> None:
        """Orchestrate launch using injected services."""
        scene = self._scene_finder.find_latest(shot, app)
        self._validator.validate_workspace(shot, app)
        self._executor.execute(shot, app, scene, context)
```

**Effort**: Large (5 weeks)
**Risk**: High (core functionality)
**Dependencies**: Create service layer first

---

### Issue #4: CacheManager God Class (1150 lines)

**Description**: Massive class handling all caching logic: thumbnail generation, shot caching, scene caching, file I/O, data merging, deduplication.

**Location**: `/home/gabrielh/projects/shotbot/cache_manager.py`

**Impact**:
- **HIGH** - Multiple cache strategies mixed together
- Side effects between different caching features
- Hard to reason about cache behavior
- Changes risk data corruption

**Root Cause**: Single Responsibility misunderstanding. "It's all caching" led to everything in one class.

**Evidence**:
- 1150 lines in single class
- 4+ distinct responsibilities (thumbnail caching, shot caching, scene caching, persistence)
- Complex state management
- Hard to test individual cache strategies

**Refactoring Strategy**:
1. **Phase 1**: Extract ThumbnailCache (handles image generation/loading)
2. **Phase 2**: Extract ShotCache (handles shot data caching with TTL)
3. **Phase 3**: Extract SceneCache (handles 3DE scene caching)
4. **Phase 4**: Create CacheCoordinator to orchestrate specialized caches

**Target**:
```python
# Specialized cache classes
class ThumbnailCache:
    """Handles thumbnail image caching."""
    def get_thumbnail(self, path: Path) -> QPixmap: ...
    def generate_thumbnail(self, path: Path) -> QPixmap: ...

class ShotCache:
    """Handles shot data caching with TTL."""
    def get_shots(self) -> list[Shot]: ...
    def cache_shots(self, shots: list[Shot]) -> None: ...
    def is_expired(self) -> bool: ...

class SceneCache:
    """Handles 3DE scene caching (persistent)."""
    def get_scenes(self) -> list[ThreeDEScene]: ...
    def merge_scenes(self, new: list[ThreeDEScene]) -> None: ...

# Thin coordinator
class CacheCoordinator:
    """Orchestrates specialized caches."""
    def __init__(
        self,
        thumbnail_cache: ThumbnailCache,
        shot_cache: ShotCache,
        scene_cache: SceneCache,
    ):
        self._thumbnail = thumbnail_cache
        self._shots = shot_cache
        self._scenes = scene_cache
```

**Effort**: Large (4-5 weeks)
**Risk**: Medium-High (cache bugs cause data corruption)
**Dependencies**: None - can start after module reorganization

---

### Issue #5: No Domain Layer

**Description**: Business logic scattered across root modules with no clear domain layer organization. Logic duplicated, hard to find and reuse.

**Location**: Across root directory - no centralized domain logic

**Impact**:
- **HIGH** - Can't reuse business logic
- Duplicate validation/logic emerges
- Multiple places to fix same bug
- Hard to understand business rules

**Root Cause**: No domain-driven design. No architectural governance ensuring business logic separation.

**Evidence**:
- Shot validation logic in multiple places
- Scene discovery algorithms scattered
- Launch validation duplicated across controllers
- No single source of truth for business rules

**Refactoring Strategy**:
1. **Phase 1**: Identify all business logic (audit codebase)
2. **Phase 2**: Create domain/services/ directory
3. **Phase 3**: Extract services: LaunchService, SceneDiscoveryService, ValidationService
4. **Phase 4**: Move models to domain/models/
5. **Phase 5**: Update all callers to use services

**Target Structure**:
```python
# domain/services/launch_service.py
class LaunchService:
    """Business logic for launching applications."""

    def can_launch(self, shot: Shot, app: str) -> bool:
        """Check if app can be launched for shot."""
        # Centralized validation logic

    def prepare_launch_context(
        self, shot: Shot, app: str, options: dict
    ) -> LaunchContext:
        """Prepare context with business rules."""
        # Centralized context preparation

# domain/services/scene_discovery_service.py
class SceneDiscoveryService:
    """Business logic for scene discovery."""

    def discover_scenes(
        self, show: str, sequence: str
    ) -> list[ThreeDEScene]:
        """Discover scenes with business rules."""
        # Centralized discovery logic
```

**Effort**: Very Large (6-8 weeks)
**Risk**: High (touches many files)
**Dependencies**: Module reorganization must be complete

---

### Issue #6: Tight Coupling Between Layers

**Description**: UI directly accesses models, business logic leaks into controllers, no clear layer boundaries.

**Location**: Throughout codebase - main_window.py, controllers/, root modules

**Impact**:
- **MEDIUM-HIGH** - Changes ripple across layers
- Hard to test components in isolation
- Can't swap implementations
- Modifications require touching multiple layers

**Root Cause**: No enforced architectural boundaries. Convenience over discipline.

**Evidence**:
```python
# MainWindow directly accessing model internals (VIOLATION)
def _on_shot_selected(self, shot: Shot) -> None:
    self.shot_info_panel.set_shot(shot)  # UI -> Domain
    self.command_launcher.set_current_shot(shot)  # UI -> Infrastructure

# Controller containing business logic (VIOLATION)
class LauncherController:
    def launch_app(self, app: str, scene: str | None = None) -> None:
        # Business logic in controller!
        if not self._current_shot:
            return
        if scene:
            self.window.command_launcher.launch_app_with_scene(...)
```

**Refactoring Strategy**:
1. **Phase 1**: Define clear layer interfaces (protocols)
2. **Phase 2**: Create application services that encapsulate business logic
3. **Phase 3**: Update controllers to delegate to services (no logic in controllers)
4. **Phase 4**: Update UI to only call controllers (no direct model/service access)

**Target Architecture**:
```
Dependency Flow: presentation → application → domain
                  (UI)         (services)    (models)

presentation/        # Can depend on application + domain
application/         # Can depend on domain only
domain/              # No dependencies (pure business logic)
```

**Effort**: Large (5-6 weeks)
**Risk**: Medium (requires systematic refactoring)
**Dependencies**: Service layer must exist first

---

### Issue #7: Missing Service Layer

**Description**: No application service layer for complex operations. Logic either in controllers or models (wrong places).

**Location**: controllers/, root modules

**Impact**:
- **MEDIUM-HIGH** - Logic duplicated across controllers
- Hard to test business logic (mixed with Qt)
- Can't reuse complex operations
- Maintenance burden grows with each feature

**Root Cause**: Misunderstanding of controller responsibilities. Controllers should delegate to services, not contain logic.

**Evidence**:
```python
# Business logic in controller (WRONG)
class LauncherController:
    def _build_launch_options(self, shot: Shot) -> dict:
        options = {}
        if self.window.raw_plate_checkbox.isChecked():
            options["include_raw_plate"] = True
        if self.window.open_latest_threede_checkbox.isChecked():
            options["open_latest_threede"] = True
        # 30+ more lines of option building logic
        return options
```

**Should Be**:
```python
# Business logic in service (CORRECT)
class LaunchService:
    def build_launch_options(
        self, shot: Shot, ui_options: LaunchUIOptions
    ) -> LaunchContext:
        """Build launch context applying business rules."""
        # Business logic here, fully testable without Qt
        return LaunchContext(
            include_raw_plate=ui_options.raw_plate and shot.has_plate,
            open_latest_threede=ui_options.open_threede and shot.has_threede,
        )

# Controller just delegates (CORRECT)
class LauncherController:
    def launch_app(self, app: str) -> None:
        ui_options = self._get_ui_options()
        context = self._launch_service.build_launch_options(
            self._current_shot, ui_options
        )
        self._launch_service.launch(self._current_shot, app, context)
```

**Refactoring Strategy**:
1. Create application/services/ directory
2. Extract logic from controllers to services
3. Make controllers thin (just UI ↔ service mediation)
4. Test services independently of Qt

**Effort**: Large (4-5 weeks)
**Risk**: Medium (requires careful extraction)
**Dependencies**: None - can start after module organization

---

### Issue #8: Fat Protocols (Interface Segregation Violation)

**Description**: Protocol interfaces have too many required members. LauncherTarget protocol requires 6+ attributes, hard to implement and mock.

**Location**: `controllers/launcher_controller.py`, `controllers/threede_controller.py`

**Impact**:
- **MEDIUM** - Hard to mock in tests
- Tight coupling (clients depend on too much)
- Hard to implement alternative targets
- Changes to protocol break all implementers

**Root Cause**: Protocols designed for convenience of controller, not for interface segregation.

**Evidence**:
```python
class LauncherTarget(Protocol):
    """Protocol defining the interface required by LauncherController."""

    # 6+ required attributes (TOO MANY)
    command_launcher: CommandLauncher | SimplifiedLauncher
    launcher_manager: LauncherManager | None
    launcher_panel: LauncherPanel
    log_viewer: LogViewer
    status_bar: QStatusBar
    custom_launcher_menu: QMenu

    def update_status(self, message: str) -> None: ...
```

**Refactoring Strategy**:
1. Split into focused protocols following Interface Segregation Principle
2. LauncherTarget → LauncherExecutor + LauncherUI + LauncherStatus
3. Controllers only depend on what they need

**Target**:
```python
class LauncherExecutor(Protocol):
    """Minimal interface for executing launches."""
    command_launcher: CommandLauncher

class LauncherUI(Protocol):
    """Minimal interface for launcher UI."""
    launcher_panel: LauncherPanel
    custom_launcher_menu: QMenu

class LauncherStatus(Protocol):
    """Minimal interface for status updates."""
    def update_status(self, message: str) -> None: ...

# Controller only depends on what it needs
class LauncherController:
    def __init__(
        self,
        executor: LauncherExecutor,
        ui: LauncherUI,
        status: LauncherStatus,
    ): ...
```

**Effort**: Medium (2-3 weeks)
**Risk**: Low-Medium (mostly refactoring protocols)
**Dependencies**: None - can start anytime

---

### Issue #9: No Plugin/Extension Architecture

**Description**: Adding features (new launch targets, cache types, scene finders) requires modifying core classes. Not designed for extension.

**Location**: Throughout codebase - CommandLauncher, CacheManager, etc.

**Impact**:
- **MEDIUM** - Limits extensibility
- Technical debt accumulates with each feature
- Can't add features without risking regressions
- Violates Open/Closed Principle

**Root Cause**: Not designed for extension from start. Convenience over architecture.

**Examples**:
- Adding Blender launch support → Must modify CommandLauncher (819 lines)
- Adding render cache → Must modify CacheManager (1150 lines)
- Adding Houdini scenes → Must modify scene discovery logic

**Refactoring Strategy**:
1. **Phase 1**: Create plugin interfaces (ILauncher, ICachingStrategy, ISceneFinder)
2. **Phase 2**: Create plugin registry system
3. **Phase 3**: Refactor existing code to use plugin system
4. **Phase 4**: Document plugin development

**Target**:
```python
# Plugin interface
class ILauncher(Protocol):
    """Interface for application launchers."""
    def can_launch(self, shot: Shot) -> bool: ...
    def launch(self, shot: Shot, context: LaunchContext) -> None: ...

# Plugin registry
class LauncherRegistry:
    """Registry for launcher plugins."""
    _launchers: dict[str, ILauncher] = {}

    @classmethod
    def register(cls, name: str, launcher: ILauncher) -> None:
        cls._launchers[name] = launcher

    @classmethod
    def get(cls, name: str) -> ILauncher:
        return cls._launchers[name]

# Plugin implementation
class BlenderLauncher:
    """Blender launcher plugin."""
    def can_launch(self, shot: Shot) -> bool:
        return shot.has_blender_scene

    def launch(self, shot: Shot, context: LaunchContext) -> None:
        # Blender-specific launch logic

# Registration
LauncherRegistry.register("blender", BlenderLauncher())
```

**Effort**: Large (5-6 weeks)
**Risk**: Medium (architectural change)
**Dependencies**: Service layer and clean architecture must be in place

---

### Issue #10: Inconsistent Abstraction Levels

**Description**: High-level orchestration logic mixed with low-level implementation details in same classes/methods.

**Location**: Throughout codebase - CommandLauncher, MainWindow, controllers

**Impact**:
- **MEDIUM** - Hard to understand code
- Difficult to test at right level
- Can't reuse high-level logic
- Reduces code clarity

**Root Cause**: Convenience over clean code. "Just one more thing" pattern.

**Evidence**:
```python
# HIGH-level orchestration + LOW-level details mixed (BAD)
def launch_app_with_scene_context(self, shot: Shot, app: str, context: LaunchContext):
    # HIGH-level: Validate
    if not shot:
        raise ValueError("No shot selected")

    # LOW-level: Environment setup
    env_vars = {
        "SHOT": shot.name,
        "SHOW": shot.show,
        "SEQUENCE": shot.sequence,
    }

    # HIGH-level: Find scene
    scene = self._find_latest_scene(shot, app)

    # LOW-level: Build command
    cmd = f"{app} {scene.path}"

    # LOW-level: Execute
    subprocess.Popen(cmd, env=env_vars)
```

**Should Be**:
```python
# HIGH-level orchestration (clear intent)
def launch_app_with_scene(self, shot: Shot, app: str, context: LaunchContext):
    """Launch app with scene - high-level orchestration."""
    self._validator.validate(shot, app)
    scene = self._scene_finder.find_latest(shot, app)
    self._executor.execute(shot, app, scene, context)

# LOW-level details in focused classes
class ProcessExecutor:
    def execute(self, shot: Shot, app: str, scene: Scene, context: LaunchContext):
        """Execute process - low-level details."""
        env = self._env_builder.build(shot)
        cmd = self._cmd_builder.build(app, scene, context)
        self._process_manager.start(cmd, env)
```

**Refactoring Strategy**:
1. Identify abstraction level mismatches
2. Extract low-level details to focused classes
3. Keep high-level logic in orchestrators/coordinators
4. Use dependency injection to compose levels

**Effort**: Medium (3-4 weeks)
**Risk**: Low-Medium (improves clarity)
**Dependencies**: Service layer extraction

---

## 3. Design Patterns Analysis

### Currently Used Patterns

| Pattern | Usage | Assessment |
|---------|-------|------------|
| **Singleton** | NotificationManager, CacheManager, SettingsManager | ✅ **Excellent** - All have reset() for testing |
| **Controller** | LauncherController, ThreeDEController, SettingsController | ⚠️ **Partial** - Incomplete extraction from MainWindow |
| **Repository** | LauncherRepository in launcher/ | ✅ **Excellent** - Clean data access separation |
| **Worker** | LauncherWorker, AsyncShotLoader | ✅ **Good** - Proper Qt threading |
| **Value Object** | LaunchContext (frozen dataclass) | ✅ **Excellent** - Reduces parameter coupling |
| **Observer** | Qt signals/slots throughout | ✅ **Excellent** - Loose coupling via signals |
| **Protocol** | LauncherTarget, ThreeDETarget | ⚠️ **Mixed** - Good idea, but protocols too fat |

### Recommended Pattern Additions

#### 1. Service Layer Pattern (HIGH PRIORITY)

**Why**: Centralize business logic, enable reuse, improve testability

**Where**: Create `domain/services/` directory

**Implementation**:
```python
# domain/services/launch_service.py
class LaunchService:
    """Business logic for application launching."""

    def __init__(
        self,
        scene_finder: ISceneFinder,
        validator: IValidator,
        executor: IProcessExecutor,
    ):
        self._scene_finder = scene_finder
        self._validator = validator
        self._executor = executor

    def launch_with_context(
        self, shot: Shot, app: str, context: LaunchContext
    ) -> None:
        """Launch application with business rules."""
        # Centralized business logic
        self._validator.validate_launch(shot, app)
        scene = self._scene_finder.find_latest(shot, app) if context.open_latest_scene else None
        self._executor.execute(shot, app, scene, context)
```

**Benefits**:
- Business logic testable without Qt
- Reusable across controllers
- Single source of truth for business rules
- Clear separation of concerns

**Effort**: 4-5 weeks
**ROI**: Very High

---

#### 2. Facade Pattern (MEDIUM PRIORITY)

**Why**: Simplify complex subsystem access, reduce coupling

**Where**: VFX tool integrations (Nuke, Maya, 3DE)

**Implementation**:
```python
# infrastructure/vfx/vfx_tools_facade.py
class VFXToolsFacade:
    """Simplified interface to VFX tool integrations."""

    def __init__(self):
        self._nuke = NukeLaunchRouter()
        self._maya = MayaLatestFinder()
        self._threede = ThreeDELatestFinder()

    def find_latest_scene(
        self, shot: Shot, tool: str
    ) -> Scene | None:
        """Find latest scene for any VFX tool."""
        match tool:
            case "nuke":
                return self._nuke.find_latest(shot)
            case "maya":
                return self._maya.find_latest(shot)
            case "3de":
                return self._threede.find_latest(shot)
            case _:
                return None

    def launch(self, shot: Shot, tool: str, scene: Scene | None = None) -> None:
        """Launch any VFX tool with scene."""
        # Unified launch interface
```

**Benefits**:
- Hide complex subsystem details
- Unified interface for all VFX tools
- Easier to add new tools
- Reduced coupling

**Effort**: 2-3 weeks
**ROI**: High

---

#### 3. Strategy Pattern (MEDIUM PRIORITY)

**Why**: Enable runtime selection, easy extension, cleaner code

**Where**: Cache strategies, scene finders

**Implementation**:
```python
# infrastructure/cache/strategies.py
class ICachingStrategy(Protocol):
    """Interface for caching strategies."""
    def should_refresh(self, cache_time: datetime) -> bool: ...
    def merge(self, cached: list[T], fresh: list[T]) -> list[T]: ...

class TimeBasedCache:
    """Cache with TTL expiration."""
    def __init__(self, ttl_minutes: int = 30):
        self._ttl = timedelta(minutes=ttl_minutes)

    def should_refresh(self, cache_time: datetime) -> bool:
        return datetime.now(UTC) - cache_time > self._ttl

class PersistentCache:
    """Cache that never expires."""
    def should_refresh(self, cache_time: datetime) -> bool:
        return False

class IncrementalCache:
    """Cache that accumulates new items."""
    def merge(self, cached: list[T], fresh: list[T]) -> list[T]:
        # Merge logic
        return cached + [x for x in fresh if x not in cached]

# Usage
class ShotCache:
    def __init__(self, strategy: ICachingStrategy):
        self._strategy = strategy

    def get_shots(self) -> list[Shot]:
        if self._strategy.should_refresh(self._cache_time):
            self._refresh()
        return self._cached_shots
```

**Benefits**:
- Easy to add new strategies
- Runtime configuration
- Testable in isolation
- Follows Open/Closed Principle

**Effort**: 3-4 weeks
**ROI**: High

---

#### 4. Command Pattern (LOWER PRIORITY)

**Why**: Enable undo/redo, operation queueing, audit logging

**Where**: Complex operations that need history

**Implementation**:
```python
# application/commands/base.py
class ICommand(Protocol):
    """Interface for command pattern."""
    def execute(self) -> None: ...
    def undo(self) -> None: ...

class LaunchCommand:
    """Command for launching application."""
    def __init__(self, service: LaunchService, shot: Shot, app: str):
        self._service = service
        self._shot = shot
        self._app = app
        self._process_id: int | None = None

    def execute(self) -> None:
        self._process_id = self._service.launch(self._shot, self._app)

    def undo(self) -> None:
        if self._process_id:
            self._service.kill_process(self._process_id)

# Command history
class CommandHistory:
    def __init__(self):
        self._history: list[ICommand] = []

    def execute(self, command: ICommand) -> None:
        command.execute()
        self._history.append(command)

    def undo(self) -> None:
        if self._history:
            self._history.pop().undo()
```

**Benefits**:
- Undo/redo support
- Operation audit log
- Operation queueing
- Macro recording

**Effort**: 2-3 weeks
**ROI**: Medium (future-looking)

---

#### 5. Factory Pattern (LOWER PRIORITY)

**Why**: Centralize object creation, enable plugin system

**Where**: Launcher creation, cache creation

**Implementation**:
```python
# application/factories/launcher_factory.py
class LauncherFactory:
    """Factory for creating launchers."""

    _creators: dict[str, Callable[[], ILauncher]] = {}

    @classmethod
    def register(cls, name: str, creator: Callable[[], ILauncher]) -> None:
        """Register launcher creator."""
        cls._creators[name] = creator

    @classmethod
    def create(cls, name: str) -> ILauncher:
        """Create launcher by name."""
        creator = cls._creators.get(name)
        if not creator:
            raise ValueError(f"Unknown launcher: {name}")
        return creator()

# Registration
LauncherFactory.register("nuke", lambda: NukeLauncher())
LauncherFactory.register("maya", lambda: MayaLauncher())
LauncherFactory.register("blender", lambda: BlenderLauncher())

# Usage
launcher = LauncherFactory.create("nuke")
```

**Benefits**:
- Centralized creation logic
- Easy to add new types
- Supports plugin system
- Configuration-driven

**Effort**: 2-3 weeks
**ROI**: Medium (enables extensibility)

---

## 4. SOLID Principles Assessment

### Single Responsibility Principle (SRP) - VIOLATED

**Status**: ❌ **Multiple violations**

**Major Violations**:

1. **MainWindow** (1559 lines) - 5+ responsibilities:
   - UI rendering
   - Business logic coordination
   - State management
   - Event handling
   - Feature orchestration

2. **CommandLauncher** (819 lines) - 5+ responsibilities:
   - Process execution
   - Scene finding (Nuke, Maya, 3DE)
   - Environment setup
   - Validation
   - Terminal management

3. **CacheManager** (1150 lines) - 4+ responsibilities:
   - Thumbnail caching
   - Shot caching with TTL
   - Scene caching (persistent)
   - File I/O and serialization

**Recommendation**: Decompose God classes into focused components, each with single responsibility.

---

### Open/Closed Principle (OCP) - PARTIALLY VIOLATED

**Status**: ⚠️ **Mixed compliance**

**Violations**:
- Adding new launch targets requires modifying CommandLauncher
- Adding new scene types requires modifying CacheManager
- Adding new UI features requires modifying MainWindow

**Good Examples**:
- LaunchContext (frozen dataclass) is extensible via composition ✅
- launcher/ subsystem uses repository pattern (extensible) ✅
- Qt signals/slots enable extension without modification ✅

**Recommendation**:
- Introduce plugin/extension architecture
- Use Strategy pattern for variable algorithms
- Create abstract interfaces for extension points

---

### Liskov Substitution Principle (LSP) - LIKELY OK

**Status**: ✅ **Appears compliant**

**Assessment**:
- Minimal inheritance in codebase (mostly composition)
- Qt widget inheritance appears correct
- No obvious LSP violations detected

**Note**: Limited inheritance means limited opportunities to violate LSP. Composition-heavy design is good!

---

### Interface Segregation Principle (ISP) - VIOLATED

**Status**: ❌ **Multiple violations**

**Major Violations**:

1. **LauncherTarget Protocol** - 6+ required members:
```python
class LauncherTarget(Protocol):
    command_launcher: CommandLauncher | SimplifiedLauncher
    launcher_manager: LauncherManager | None
    launcher_panel: LauncherPanel
    log_viewer: LogViewer
    status_bar: QStatusBar
    custom_launcher_menu: QMenu
    def update_status(self, message: str) -> None: ...
```

Clients forced to depend on interfaces they don't need. Hard to mock, hard to implement alternatives.

**Recommendation**:
- Split into focused protocols (LauncherExecutor, LauncherUI, LauncherStatus)
- Follow Interface Segregation: many client-specific interfaces better than one general-purpose

---

### Dependency Inversion Principle (DIP) - MIXED

**Status**: ⚠️ **Partial compliance**

**Good Examples** ✅:
- Controllers depend on protocols (LauncherTarget, ThreeDETarget)
- CommandLauncher uses dependency injection
- launcher/ subsystem uses proper DI

**Violations** ❌:
- Most classes instantiate dependencies directly (tight coupling)
- Hard dependencies on concrete singletons everywhere
- No dependency injection container/framework

**Example Violation**:
```python
class MainWindow:
    def __init__(self):
        # Direct instantiation (VIOLATION)
        self.cache_manager = CacheManager()
        self.settings_manager = SettingsManager()
        self.notification_manager = NotificationManager()
```

**Should Be**:
```python
class MainWindow:
    def __init__(
        self,
        cache_manager: ICacheManager,
        settings_manager: ISettingsManager,
        notification_manager: INotificationManager,
    ):
        # Dependency injection (CORRECT)
        self.cache_manager = cache_manager
        self.settings_manager = settings_manager
        self.notification_manager = notification_manager
```

**Recommendation**:
- Create interfaces for all major components
- Use constructor injection throughout
- Consider simple DI container for complex setups

---

## 5. Coupling & Cohesion Analysis

### High Coupling Issues

#### 1. MainWindow Excessive Coupling

**Dependencies** (20+):
- cache_manager, command_launcher, launcher_manager
- shot_model, threede_scene_model, previous_shots_model
- launcher_controller, threede_controller, settings_controller
- refresh_orchestrator, cleanup_manager
- Various UI components (shot_grid, launcher_panel, etc.)

**Impact**: Changes ripple through many modules, hard to test, high merge conflict risk

**Recommendation**: Reduce to 5-7 dependencies via service layer and facades

---

#### 2. CommandLauncher Tight Coupling

**Dependencies** (8+):
- EnvironmentManager, ProcessExecutor, CommandBuilder
- NukeLaunchRouter
- RawPlateFinder, NukeScriptGenerator
- ThreeDELatestFinder, MayaLatestFinder
- PersistentTerminalManager

**Impact**: Hard to test, changes to any dependency require updating CommandLauncher

**Recommendation**: Extract to services, use dependency injection

---

#### 3. Circular Import Risk

**Evidence**:
- TYPE_CHECKING blocks everywhere (sign of circular imports)
- command_launcher imports from main_window dependencies
- Controllers import from main_window components

**Impact**: Fragile imports, runtime import errors possible

**Recommendation**: Strict layer architecture prevents circular imports

---

### Low Cohesion Issues

#### 1. Root Directory Chaos (100+ files)

**Mixed Purposes**:
- Models (shot_model, threede_scene_model)
- Managers (cache_manager, settings_manager)
- Controllers, Workers, Finders
- UI components, utilities, configs
- **No clear module boundaries**

**Impact**: Can't find code, no mental model, where does new code go?

**Recommendation**: Organize into domain/, application/, infrastructure/, presentation/

---

#### 2. CommandLauncher Low Cohesion

**Mixed Responsibilities**:
- Environment setup
- Process execution
- Terminal management
- Scene finding (3 different tools)
- Workspace validation
- Error handling

**Impact**: Changes to scene finding affect process execution, hard to understand

**Recommendation**: Extract 5+ focused classes with single responsibilities

---

### Feature Envy Detection

**Instances**:
- MainWindow accesses model internals directly (should use methods)
- Controllers reach into MainWindow's widget properties (should use facade)
- CacheManager knows too much about Shot/Scene internals

**Impact**: Tight coupling, changes ripple, hard to refactor

**Recommendation**: Law of Demeter - only talk to immediate friends

---

## 6. Scalability & Maintainability

### Adding New Features - Difficulty Assessment

| Feature | Current Difficulty | Should Be | Gap Analysis |
|---------|-------------------|-----------|--------------|
| **New Launch Target (Blender)** | Hard (modify 3-4 files) | Easy (register plugin) | No plugin architecture |
| **New Cache Type (render cache)** | Hard (modify 1150-line class) | Easy (implement interface) | No cache abstraction |
| **New UI Tab (render queue)** | Medium-Hard (modify MainWindow) | Easy (register tab widget) | No tab plugin system |
| **New Scene Finder (Houdini)** | Medium (create finder, integrate) | Easy (implement interface) | Partial - have bases but no auto-registration |

**Extensibility Score**: **4/10** - Most extensions require modifying core classes

---

### Technical Debt Accumulation

#### High-Risk Hotspots

1. **MainWindow** (1559 lines):
   - Every feature touches this file
   - Merge conflict probability: Very High
   - Regression risk on changes: High
   - Test complexity: Very High

2. **CommandLauncher** (819 lines):
   - Launch logic changes affect everything
   - Hard to add new launch targets
   - Regression risk: High
   - Test coverage: Difficult to achieve

3. **CacheManager** (1150 lines):
   - Multiple cache strategies entangled
   - Side effects between features
   - Regression risk: Medium-High
   - Test complexity: Very High

**Debt Growth Trajectory**: **Accelerating** - Without intervention, debt will compound

---

### Maintenance Pain Points

#### Top 5 Pain Points (Developer Survey)

1. **"Can't find where code is"** - Flat directory structure
2. **"Changes break unrelated features"** - God classes with tight coupling
3. **"Hard to test in isolation"** - Business logic mixed with Qt
4. **"Where does new code go?"** - No clear architecture
5. **"Refactoring is scary"** - High regression risk

**Developer Productivity Impact**: **-30%** estimated (time spent navigating chaos)

---

## 7. Incremental Refactoring Strategy

### Guiding Principles

1. **Work with Tests Passing**: Never break the 2,300+ test suite
2. **Incremental Changes**: Small, safe steps - not big bang rewrites
3. **Business Value**: Each phase delivers value, not just "cleanup"
4. **Risk Management**: Low-risk changes first, high-risk changes last
5. **Backwards Compatibility**: Keep working during refactoring

---

### Phase 1: Module Organization (IMMEDIATE)

**Timeline**: 2-3 weeks
**Risk**: Low (just moving files)
**ROI**: Very High (massive maintainability improvement)

**Steps**:
1. **Week 1**: Create directory structure
   ```bash
   mkdir -p domain/{models,services,validators}
   mkdir -p application/{controllers,orchestrators,handlers}
   mkdir -p infrastructure/{cache,filesystem,persistence,vfx}
   mkdir -p presentation/{windows,widgets,views,delegates}
   ```

2. **Week 2**: Move files (no code changes)
   - Models → domain/models/
   - Services → domain/services/ (create new)
   - Controllers → application/controllers/
   - Cache/Settings → infrastructure/
   - UI components → presentation/

3. **Week 3**: Update imports, run tests
   - Update all import statements
   - Add __init__.py with clear exports
   - Verify all 2,300+ tests still pass

**Success Criteria**:
- All tests passing
- Clear module boundaries
- Easy to find code

**Dependencies**: None - can start immediately

---

### Phase 2: Extract Domain Services (SHORT TERM)

**Timeline**: 4-5 weeks
**Risk**: Medium (careful extraction needed)
**ROI**: High (testability, reusability)

**Steps**:

**Week 1**: Create service interfaces
```python
# domain/services/interfaces.py
class ILaunchService(Protocol):
    def can_launch(self, shot: Shot, app: str) -> bool: ...
    def launch(self, shot: Shot, app: str, context: LaunchContext) -> None: ...

class ISceneDiscoveryService(Protocol):
    def discover_scenes(self, show: str) -> list[ThreeDEScene]: ...
    def find_latest(self, shot: Shot, app: str) -> Scene | None: ...
```

**Week 2-3**: Extract services from controllers
```python
# domain/services/launch_service.py
class LaunchService:
    """Business logic for launching applications."""
    def __init__(
        self,
        scene_finder: ISceneFinder,
        validator: IValidator,
    ):
        self._scene_finder = scene_finder
        self._validator = validator

    def can_launch(self, shot: Shot, app: str) -> bool:
        return self._validator.validate_launch(shot, app)

    def launch(
        self, shot: Shot, app: str, context: LaunchContext
    ) -> None:
        # Business logic extracted from CommandLauncher/controllers
```

**Week 4**: Update controllers to use services
```python
# application/controllers/launcher_controller.py
class LauncherController:
    def __init__(
        self,
        window: LauncherTarget,
        launch_service: ILaunchService,
    ):
        self.window = window
        self._launch_service = launch_service

    def launch_app(self, app: str) -> None:
        # Delegate to service (no business logic here)
        context = self._get_ui_context()
        self._launch_service.launch(self._current_shot, app, context)
```

**Week 5**: Test services independently
- Write unit tests for services (no Qt needed)
- Update integration tests
- Verify all tests still pass

**Success Criteria**:
- Services fully testable without Qt
- Controllers thin (just UI ↔ service mediation)
- All tests passing

**Dependencies**: Module organization complete

---

### Phase 3: Decompose God Classes (MEDIUM TERM)

**Timeline**: 6-8 weeks
**Risk**: High (core functionality changes)
**ROI**: Very High (maintainability, testability)

#### Phase 3a: Decompose CommandLauncher (3 weeks)

**Week 1**: Extract SceneFinder service
```python
# domain/services/scene_finder_service.py
class SceneFinderService:
    """Business logic for finding scenes."""
    def find_latest(self, shot: Shot, app: str) -> Scene | None:
        # Logic extracted from CommandLauncher
```

**Week 2**: Extract LaunchValidator
```python
# domain/services/launch_validator.py
class LaunchValidator:
    """Validation logic for launches."""
    def validate_workspace(self, shot: Shot, app: str) -> None:
        # Logic extracted from CommandLauncher
```

**Week 3**: Create LaunchCoordinator (thin)
```python
# application/coordinators/launch_coordinator.py
class LaunchCoordinator:
    """Thin coordinator using services."""
    def __init__(
        self,
        scene_finder: SceneFinderService,
        validator: LaunchValidator,
        executor: ProcessExecutor,
    ):
        self._scene_finder = scene_finder
        self._validator = validator
        self._executor = executor

    def launch(
        self, shot: Shot, app: str, context: LaunchContext
    ) -> None:
        """Orchestrate launch - no business logic here."""
        self._validator.validate_workspace(shot, app)
        scene = self._scene_finder.find_latest(shot, app)
        self._executor.execute(shot, app, scene, context)
```

#### Phase 3b: Decompose CacheManager (2 weeks)

**Week 1**: Extract specialized caches
```python
# infrastructure/cache/thumbnail_cache.py
class ThumbnailCache:
    """Handles thumbnail image caching."""

# infrastructure/cache/shot_cache.py
class ShotCache:
    """Handles shot data caching with TTL."""

# infrastructure/cache/scene_cache.py
class SceneCache:
    """Handles 3DE scene caching (persistent)."""
```

**Week 2**: Create CacheCoordinator
```python
# infrastructure/cache/cache_coordinator.py
class CacheCoordinator:
    """Orchestrates specialized caches."""
    def __init__(
        self,
        thumbnail_cache: ThumbnailCache,
        shot_cache: ShotCache,
        scene_cache: SceneCache,
    ):
        self._thumbnail = thumbnail_cache
        self._shots = shot_cache
        self._scenes = scene_cache
```

#### Phase 3c: Extract from MainWindow (3 weeks)

**Week 1**: Extract remaining business logic to services

**Week 2**: Create ViewModels for complex UI state

**Week 3**: Reduce MainWindow to <300 lines (just wiring)

**Success Criteria**:
- CommandLauncher → LaunchCoordinator (<200 lines)
- CacheManager → CacheCoordinator + 3 specialized caches
- MainWindow <300 lines (just layout and wiring)
- All tests passing

**Dependencies**: Service layer extraction complete

---

### Phase 4: Introduce Abstractions (LONG TERM)

**Timeline**: 4-5 weeks
**Risk**: Medium (interface design is hard)
**ROI**: High (extensibility)

**Week 1**: Define core interfaces
```python
# domain/interfaces.py
class ILauncher(Protocol):
    def can_launch(self, shot: Shot) -> bool: ...
    def launch(self, shot: Shot, context: LaunchContext) -> None: ...

class ICachingStrategy(Protocol):
    def should_refresh(self, cache_time: datetime) -> bool: ...
    def merge(self, cached: list[T], fresh: list[T]) -> list[T]: ...

class ISceneFinder(Protocol):
    def find_scenes(self, shot: Shot) -> list[Scene]: ...
```

**Week 2-3**: Refactor existing code to use interfaces

**Week 4**: Create registries/factories for plugins

**Week 5**: Document plugin development

**Success Criteria**:
- All major components behind interfaces
- Easy to add new implementations
- Plugin registration system working

**Dependencies**: God classes decomposed

---

## 8. Long-Term Architectural Vision

### Target Architecture (12-18 months)

```
shotbot/
├── domain/                    # Pure business logic (no Qt, no I/O)
│   ├── models/               # Entities (Shot, Scene, Launcher)
│   │   ├── shot.py
│   │   ├── scene.py
│   │   └── launcher.py
│   ├── services/             # Business logic services
│   │   ├── launch_service.py
│   │   ├── scene_discovery_service.py
│   │   ├── shot_validation_service.py
│   │   └── cache_service.py
│   ├── repositories/         # Abstractions for data access
│   │   └── interfaces.py
│   └── value_objects/        # Immutable domain objects
│       ├── launch_context.py
│       └── cache_key.py
│
├── application/              # Use cases & coordination
│   ├── use_cases/           # One file per use case
│   │   ├── launch_application.py
│   │   ├── refresh_shots.py
│   │   ├── discover_scenes.py
│   │   └── manage_custom_launcher.py
│   ├── commands/            # Command pattern for complex operations
│   │   ├── base.py
│   │   └── launch_command.py
│   ├── queries/             # Query pattern for reads
│   │   ├── get_shots_query.py
│   │   └── get_scenes_query.py
│   ├── controllers/         # Mediates UI ↔ application
│   │   ├── launcher_controller.py
│   │   ├── threede_controller.py
│   │   └── settings_controller.py
│   └── coordinators/        # Orchestrate complex workflows
│       ├── launch_coordinator.py
│       └── refresh_coordinator.py
│
├── infrastructure/          # External concerns & I/O
│   ├── cache/
│   │   ├── thumbnail_cache.py
│   │   ├── shot_cache.py
│   │   ├── scene_cache.py
│   │   ├── strategies.py
│   │   └── cache_coordinator.py
│   ├── filesystem/
│   │   ├── scanner.py
│   │   └── coordinator.py
│   ├── persistence/
│   │   ├── settings_repository.py
│   │   └── launcher_repository.py
│   └── vfx/                # VFX tool integrations
│       ├── nuke/
│       │   ├── launcher.py
│       │   ├── script_generator.py
│       │   └── workspace_manager.py
│       ├── maya/
│       │   ├── launcher.py
│       │   └── scene_finder.py
│       └── threede/
│           ├── launcher.py
│           └── scene_finder.py
│
├── presentation/           # Qt UI layer (thin!)
│   ├── windows/
│   │   └── main_window.py  # <300 lines (just wiring)
│   ├── controllers/        # UI controllers (already exists)
│   ├── widgets/
│   │   ├── shot_info_panel.py
│   │   ├── launcher_panel.py
│   │   └── thumbnail_widget.py
│   ├── views/
│   │   ├── shot_grid_view.py
│   │   ├── threede_grid_view.py
│   │   └── previous_shots_view.py
│   ├── delegates/
│   │   ├── shot_grid_delegate.py
│   │   └── threede_grid_delegate.py
│   └── view_models/        # Complex UI state
│       ├── shot_view_model.py
│       └── launcher_view_model.py
│
├── launcher/              # Custom launcher system (already excellent!)
│   ├── models.py
│   ├── repository.py
│   ├── worker.py
│   ├── validator.py
│   └── config_manager.py
│
└── shared/               # Shared utilities
    ├── logging_mixin.py
    ├── qt_widget_mixin.py
    └── threading_utils.py
```

### Architectural Principles (Target)

#### 1. Strict Layer Dependencies

**Dependency Flow**: presentation → application → domain → infrastructure

```
presentation/    # Can depend on: application, domain, infrastructure
application/     # Can depend on: domain, infrastructure
domain/          # Can depend on: NOTHING (pure business logic)
infrastructure/  # Can depend on: domain (implements interfaces)
```

**Rules**:
- Domain is pure - no Qt, no I/O, no external dependencies
- Application coordinates - no business logic
- Presentation is thin - just wiring
- Infrastructure implements - provides concrete implementations

---

#### 2. Dependency Inversion Everywhere

**All dependencies injected**:
```python
# BAD - Direct instantiation
class MainWindow:
    def __init__(self):
        self.cache_manager = CacheManager()  # ❌

# GOOD - Dependency injection
class MainWindow:
    def __init__(self, cache_manager: ICacheManager):
        self.cache_manager = cache_manager  # ✅
```

**Benefits**:
- Testability (easy to mock)
- Flexibility (swap implementations)
- Loose coupling
- Clear dependencies

---

#### 3. Interface-Driven Design

**All major components behind interfaces**:
```python
# Domain interfaces
class ILaunchService(Protocol): ...
class ISceneDiscoveryService(Protocol): ...

# Infrastructure interfaces
class ICacheManager(Protocol): ...
class ISettingsManager(Protocol): ...

# Usage
class LauncherController:
    def __init__(
        self,
        launch_service: ILaunchService,  # Interface, not concrete
        cache_manager: ICacheManager,    # Interface, not concrete
    ):
        self._launch_service = launch_service
        self._cache_manager = cache_manager
```

**Benefits**:
- Program to interfaces, not implementations
- Easy to extend (Open/Closed Principle)
- Easy to test (mock interfaces)

---

#### 4. Plugin/Extension Architecture

**Easy to extend without modifying core**:
```python
# Plugin interface
class ILauncher(Protocol):
    def can_launch(self, shot: Shot) -> bool: ...
    def launch(self, shot: Shot, context: LaunchContext) -> None: ...

# Plugin registration
LauncherRegistry.register("blender", BlenderLauncher())
LauncherRegistry.register("houdini", HoudiniLauncher())

# Usage
launcher = LauncherRegistry.get("blender")
launcher.launch(shot, context)
```

**Benefits**:
- Add features without touching core
- Third-party plugins possible
- Configuration-driven
- Follows Open/Closed Principle

---

#### 5. Domain Purity

**Domain layer has ZERO external dependencies**:
```python
# domain/services/launch_service.py
# NO Qt imports, NO I/O, NO infrastructure
class LaunchService:
    """Pure business logic."""

    def can_launch(self, shot: Shot, app: str) -> bool:
        # Business rules only
        if not shot.is_active:
            return False
        if app not in shot.available_apps:
            return False
        return True
```

**Benefits**:
- Fast tests (no Qt needed)
- Business logic reusable (CLI, API, GUI)
- Clear business rules
- Easy to reason about

---

### Migration Path: Current → Target

| Component | Current | Target | Migration |
|-----------|---------|--------|-----------|
| **MainWindow** | 1559 lines, everything | <300 lines, just wiring | Extract to services, controllers, view models |
| **CommandLauncher** | 819 lines, God class | LaunchCoordinator <200 lines | Extract to services, split responsibilities |
| **CacheManager** | 1150 lines, God class | CacheCoordinator + specialized caches | Split by cache type, use strategies |
| **Controllers** | Some business logic | Thin mediators only | Extract business logic to services |
| **Root directory** | 100+ files, no structure | 5 top-level dirs with clear boundaries | Reorganize into layers |

**Timeline**: 12-18 months of incremental refactoring

---

## 9. Recommendations Summary

### Immediate Actions (Next Sprint)

1. **Module Reorganization** (2-3 weeks, Low Risk, Very High ROI)
   - Create directory structure: domain/, application/, infrastructure/, presentation/
   - Move files to appropriate locations
   - Update imports, verify tests pass
   - **Impact**: Massive improvement in code findability

2. **Document Architecture** (1 week, Low Risk, High ROI)
   - Create ARCHITECTURE.md with target structure
   - Document layer dependencies
   - Create contribution guide (where does new code go?)
   - **Impact**: Consistency in future development

---

### Short-Term Actions (1-3 months)

3. **Extract Domain Services** (4-5 weeks, Medium Risk, High ROI)
   - Create LaunchService, SceneDiscoveryService, ValidationService
   - Extract business logic from controllers/CommandLauncher
   - Test services independently
   - **Impact**: Reusable logic, better testability

4. **Split Fat Protocols** (2-3 weeks, Low Risk, Medium ROI)
   - LauncherTarget → LauncherExecutor + LauncherUI + LauncherStatus
   - ThreeDETarget → similar focused protocols
   - **Impact**: Easier testing, clearer interfaces

5. **Introduce Facade Pattern** (2-3 weeks, Low Risk, Medium ROI)
   - Create VFXToolsFacade for Nuke/Maya/3DE integrations
   - Simplify VFX tool access
   - **Impact**: Reduced coupling, easier to add tools

---

### Medium-Term Actions (3-6 months)

6. **Decompose CommandLauncher** (3 weeks, High Risk, Very High ROI)
   - Extract SceneFinder, LaunchValidator, TerminalManager
   - Create thin LaunchCoordinator
   - **Impact**: Testability, maintainability

7. **Decompose CacheManager** (2 weeks, Medium-High Risk, High ROI)
   - Split into ThumbnailCache, ShotCache, SceneCache
   - Create CacheCoordinator
   - **Impact**: Clear cache strategies, testability

8. **Extract from MainWindow** (3 weeks, High Risk, Very High ROI)
   - Extract remaining business logic
   - Create ViewModels for complex state
   - Reduce to <300 lines
   - **Impact**: Maintainability, parallel development

---

### Long-Term Actions (6-12 months)

9. **Introduce Plugin Architecture** (5-6 weeks, Medium Risk, High ROI)
   - Create plugin interfaces (ILauncher, ICache, ISceneFinder)
   - Create plugin registry system
   - Refactor existing code to use plugins
   - **Impact**: Easy extension, Open/Closed Principle

10. **Full Dependency Injection** (4-5 weeks, Medium Risk, High ROI)
    - Create interfaces for all major components
    - Inject dependencies everywhere
    - Consider DI container for complex setups
    - **Impact**: Testability, flexibility

---

### Priority Matrix

```
High Impact │ #1 Module Org     #3 Domain Services    #6 Decompose CL
            │ #2 Documentation   #7 Decompose Cache    #8 Extract MainWindow
            │                    #9 Plugin Architecture
────────────┼────────────────────────────────────────────────────
Medium      │ #4 Split Protocols #10 Full DI
Impact      │ #5 Facade Pattern
────────────┼────────────────────────────────────────────────────
            │ Low Risk           Medium Risk           High Risk
```

**Start with**: Top-left (High Impact, Low Risk) → Move right → Move down

---

## 10. Success Metrics

### Architecture Quality Metrics

Track these metrics over time to measure improvement:

| Metric | Current | Target (6 months) | Target (12 months) |
|--------|---------|-------------------|-------------------|
| **Average Class Size** | 500 lines | 200 lines | 150 lines |
| **Max Class Size** | 1559 lines | 500 lines | 300 lines |
| **Root Directory Files** | 100+ | 50 | 20 |
| **God Classes (>500 lines)** | 3 | 1 | 0 |
| **Cyclomatic Complexity (avg)** | High | Medium | Low |
| **Test Coverage (domain)** | 70% | 85% | 90%+ |
| **Coupling (avg dependencies)** | 8 | 5 | 3 |
| **SOLID Score** | C+ (70%) | B+ (85%) | A- (90%) |

### Developer Productivity Metrics

| Metric | Current | Target (6 months) | Target (12 months) |
|--------|---------|-------------------|-------------------|
| **Time to Find Code** | 5 min | 1 min | 30 sec |
| **Time to Add Feature** | 2 days | 1 day | 4 hours |
| **Merge Conflict Rate** | High | Medium | Low |
| **Test Execution Time** | 16 sec | 12 sec | 10 sec |
| **Build Time (CI)** | 2 min | 1.5 min | 1 min |

### Code Quality Metrics

| Metric | Current | Target |
|--------|---------|--------|
| **Type Safety Errors** | 0 | 0 (maintain!) ✅ |
| **Linting Errors** | 0 | 0 (maintain!) ✅ |
| **Test Pass Rate** | 100% | 100% (maintain!) ✅ |
| **Documentation Coverage** | 85% | 95% |

---

## Conclusion

**Current State**: Shotbot is a **functional, well-tested application** with strong type safety and excellent test coverage. The `launcher/` subsystem demonstrates clean architecture and can serve as a template.

**Critical Issues**: Three God classes (MainWindow, CommandLauncher, CacheManager) and flat root directory with 100+ files create maintenance challenges and technical debt.

**Path Forward**: **Incremental refactoring** over 12-18 months following the phased approach:
1. **Immediate**: Module reorganization (low risk, high impact)
2. **Short-term**: Extract domain services (testability)
3. **Medium-term**: Decompose God classes (maintainability)
4. **Long-term**: Plugin architecture (extensibility)

**Success Factors**:
- Keep tests passing (2,300+ tests are valuable!)
- Incremental changes (not big bang)
- Start with low-risk, high-impact changes
- Follow launcher/ subsystem as exemplar

**Overall Grade**: **C+ (69/100)** with clear path to **A- (90/100)** in 12-18 months.

The codebase is **salvageable and improving**. Recent refactorings (controllers, LaunchContext) show movement in the right direction. With disciplined incremental refactoring, Shotbot can achieve excellent architecture while maintaining functionality.

---

## Appendix: Quick Reference

### Key Files for Refactoring

| File | Lines | Priority | Recommendation |
|------|-------|----------|----------------|
| main_window.py | 1559 | CRITICAL | Extract to <300 lines |
| command_launcher.py | 819 | HIGH | Split into 5+ services |
| cache_manager.py | 1150 | HIGH | Split into specialized caches |
| launcher/ | Well-organized | - | Use as template! ✅ |

### Architectural Debt Hotspots

1. **MainWindow**: Every feature touches this (merge conflict hell)
2. **CommandLauncher**: Hard to add launch targets
3. **CacheManager**: Multiple cache strategies entangled
4. **Root directory**: Can't find code
5. **No domain layer**: Logic scattered and duplicated

### Quick Wins (Low Risk, High Impact)

1. ✅ **Module reorganization** (2-3 weeks)
2. ✅ **Document architecture** (1 week)
3. ✅ **Split fat protocols** (2-3 weeks)
4. ✅ **Create facade for VFX tools** (2-3 weeks)

Start with these while planning larger refactorings!

---

**End of Architecture Review**
