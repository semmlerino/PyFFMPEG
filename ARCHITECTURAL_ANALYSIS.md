# ARCHITECTURAL ANALYSIS

## Executive Summary

**Overall Assessment**: The shotbot codebase exhibits significant over-engineering with excessive abstraction, singleton proliferation, and architectural pattern mixing. However, evidence of successful consolidation efforts (80% code reduction in launcher system) demonstrates that major simplification is achievable.

**Key Findings**:
- **11 singleton managers** consuming 6,824 lines (average 620 lines each)
- **2,902 lines of base classes** (6 base class hierarchies) with minimal concrete implementations
- **30+ files** using TYPE_CHECKING to hide circular dependencies instead of fixing architecture
- **3 overlapping architectural patterns**: Controllers + Managers + Orchestrators/Coordinators
- **Successful precedent**: simplified_launcher.py achieved 80% reduction (3,153 → 610 lines)
- **Pattern stacking**: Strategy + Coordinator + Base Class + Protocol patterns all combined

**Impact**:
- High maintenance burden (9,726+ lines of architectural overhead)
- Difficult onboarding (mixed patterns, unclear responsibilities)
- Hidden circular dependencies create fragile module structure
- Test complexity from singleton state management

**Opportunity**: Conservative estimate suggests 40-60% reduction in architectural code is achievable based on existing consolidation success.

---

## Top Architecture Issues

### 1. [Complexity] HIGH - Singleton Manager Explosion

**Issue**: 11 singleton managers handling cross-cutting concerns, totaling 6,824 lines

**Files Involved**:
```
cache_manager.py              1,151 lines
process_pool_manager.py         777 lines
launcher_manager.py             679 lines
notification_manager.py         657 lines
settings_manager.py             636 lines
progress_manager.py             606 lines
signal_manager.py               506 lines
persistent_terminal_manager.py  934 lines
threading_manager.py            389 lines
filesystem_coordinator.py       250 lines
cleanup_manager.py              239 lines
```

**Description**: Every cross-cutting concern has become a singleton manager. Many provide functionality already available in Python stdlib or Qt framework.

**Consequences**:
- Test isolation complexity (all require reset() methods for parallel tests)
- Global state management burden
- Unclear responsibilities between managers
- High line count for relatively simple functionality

**Specific Problems**:
- **SignalManager** (506 lines): Wraps Qt's signal-slot mechanism which already handles connection management
- **ThreadingManager** (389 lines): Wraps Python's threading and Qt's QThread
- **CleanupManager** (239 lines): Could be simple module-level cleanup functions
- **FilesystemCoordinator** (250 lines): Just a directory cache - could be integrated where used

**Evidence of Over-Engineering**:
```python
# SignalManager usage - adds complexity over Qt's built-in features
signal_manager.connect_safely(button.clicked, self.on_click)
# vs. Qt's native approach:
button.clicked.connect(self.on_click)
```

---

### 2. [Abstraction] HIGH - Excessive Base Class Hierarchy

**Issue**: 2,902 lines of base classes with minimal concrete implementations

**Files Involved**:
```
base_item_model.py           838 lines → 3 implementations (Shot, ThreeDEScene, PreviousShots)
base_grid_view.py            448 lines → 3 implementations
base_thumbnail_delegate.py   570 lines → 2 implementations
base_shot_model.py           381 lines → 1 implementation (ShotModel)
base_asset_finder.py         363 lines → ~2 implementations
base_scene_finder.py         302 lines → ~2 implementations
```

**Description**: Abstract base classes created for code reuse even when there are only 1-3 concrete implementations. Classic premature abstraction.

**Consequences**:
- Navigation difficulty (must jump between base and concrete classes)
- Premature generalization for future use cases that never materialized
- Higher cognitive load to understand any single implementation
- Changes require modifications in both base and concrete classes

**Specific Example - BaseItemModel**:
- 838 lines of generic code
- Only 3 concrete implementations: ShotItemModel, ThreeDEItemModel, PreviousShotsItemModel
- Most implementations are nearly identical with minor differences
- Could be a single ItemModel[T] with minimal specialization

**YAGNI Violation**:
```python
# base_shot_model.py - 381 lines for ONE implementation
class BaseShotModel(ABC, LoggingMixin, QObject, metaclass=QABCMeta):
    # Complex filtering, sorting, caching infrastructure
    # Only concrete implementation: ShotModel
```

---

### 3. [Coupling] HIGH - Circular Dependencies Hidden by TYPE_CHECKING

**Issue**: 30+ files use TYPE_CHECKING pattern to avoid runtime circular imports instead of fixing module architecture

**Files Involved**:
```
main_window.py, command_launcher.py, launcher_manager.py, process_pool_manager.py,
filesystem_scanner.py, threede_scene_model.py, shot_model.py, cache_manager.py,
refresh_orchestrator.py, cleanup_manager.py, [20+ more]
```

**Description**: Instead of restructuring modules to eliminate circular dependencies, the codebase uses TYPE_CHECKING imports and Protocol workarounds to mask the problem.

**Consequences**:
- Fragile module structure (circular dependencies still exist, just hidden)
- Runtime import failures possible if patterns not followed correctly
- Protocols with `Any` types lose type safety benefits
- Difficult refactoring (must maintain circular dependency patterns)

**Specific Example**:
```python
# refresh_orchestrator.py
class RefreshOrchestratorMainWindowProtocol(Protocol):
    """Protocol defining MainWindow interface.

    This avoids circular imports while providing proper type safety.
    Attributes are typed as Any because we cannot import MainWindow
    without creating a circular dependency.
    """
    tab_widget: Any  # Lost type safety!
    shot_model: Any
    threede_controller: Any
```

**Explicit Acknowledgment in Code**:
```python
# filesystem_scanner.py line 9-10
# pyright: reportImportCycles=false
# Import cycles are broken at runtime through lazy imports
```

---

### 4. [Pattern] HIGH - Duplicate Launcher Systems

**Issue**: Two complete launcher systems coexist, old system still active despite deprecation

**Files Involved**:
```
OLD SYSTEM (deprecated but active):
- command_launcher.py (deprecated, issues deprecation warning)
- launcher_manager.py (679 lines)
- /launcher/ package:
  - models.py, repository.py, config_manager.py
  - validator.py, process_manager.py, worker.py
  Total: ~3,153 lines

NEW SYSTEM:
- simplified_launcher.py (610 lines)
  Consolidates 4 modules into 1
```

**Description**: simplified_launcher.py achieved 80% reduction (3,153 → 610 lines) by eliminating unnecessary abstractions. However, old system remains active with deprecation warnings.

**Consequences**:
- Duplicate maintenance burden
- Unclear which system to use for new features
- Technical debt accumulation
- Deprecation warnings in production code

**Evidence of Success**:
```python
# command_launcher.py header
"""DEPRECATED: This module is deprecated in favor of simplified_launcher.py.
The SimplifiedLauncher consolidates functionality from 4 modules (3,153 lines)
into one (610 lines).
"""
```

**Recommendation**: Complete migration demonstrates path forward for other systems.

---

### 5. [Pattern] MEDIUM - Pattern Stacking Without Benefit

**Issue**: Multiple design patterns stacked together (Strategy + Coordinator + Base Class + Protocol) when simpler solutions would suffice

**Files Involved**:
```
Finder hierarchy:
- shot_finder_base.py (base class + ABC)
- base_asset_finder.py (base class + ABC)
- base_scene_finder.py (base class + ABC)
- scene_discovery_strategy.py (strategy pattern)
- scene_discovery_coordinator.py (coordinator pattern)
- filesystem_coordinator.py (coordinator pattern)
- Various concrete finders: threede_scene_finder.py, maya_latest_finder.py,
  previous_shots_finder.py, targeted_shot_finder.py, raw_plate_finder.py
```

**Description**: Scene discovery has 4 layers of abstraction:
1. ABC base classes (ShotFinderBase, BaseAssetFinder, BaseSceneFinder)
2. Strategy pattern (SceneDiscoveryStrategy)
3. Coordinator pattern (SceneDiscoveryCoordinator, FilesystemCoordinator)
4. Protocol pattern (used to connect layers without circular imports)

**Consequences**:
- 13 files (~3,000+ lines) for file discovery
- Must navigate multiple abstraction layers to understand behavior
- Difficult to trace execution flow
- Over-engineered for a single-user desktop application

**Alternative**: Simple directory scanning with direct file filtering would be 200-300 lines.

---

### 6. [Complexity] MEDIUM - Mixed Architectural Patterns

**Issue**: Controllers, Managers, Orchestrators, and Coordinators all coexist with unclear responsibility boundaries

**Files Involved**:
```
CONTROLLERS:
- controllers/launcher_controller.py
- controllers/settings_controller.py
- controllers/threede_controller.py

MANAGERS:
- launcher_manager.py (679 lines)
- cache_manager.py (1,151 lines)
- [9 more managers]

ORCHESTRATORS/COORDINATORS:
- refresh_orchestrator.py
- scene_discovery_coordinator.py
- filesystem_coordinator.py
```

**Description**: Three different architectural patterns for organizing business logic, with fuzzy boundaries:
- **Controllers**: Handle UI logic and coordinate between views and models
- **Managers**: Singleton services for cross-cutting concerns
- **Orchestrators/Coordinators**: Coordinate complex multi-step operations

**Consequences**:
- Unclear where to place new functionality
- Responsibility confusion (LauncherController + LauncherManager both handle launching)
- Inconsistent patterns across codebase
- Difficult onboarding

**Specific Example**:
```python
# Both handle launcher functionality:
LauncherController    # coordinates UI interactions
LauncherManager       # manages launcher instances
# Unclear: Who owns launcher lifecycle? Who owns launcher state?
```

---

### 7. [Abstraction] MEDIUM - Mixin Proliferation

**Issue**: 5+ mixin classes used throughout codebase, creating complex multiple inheritance chains

**Files Involved**:
```
logging_mixin.py         443 lines (wraps logging.getLogger)
qt_widget_mixin.py       436 lines (Qt widget patterns)
error_handling_mixin.py  ~200 lines
progress_mixin.py        ~150 lines
version_mixin.py         ~100 lines
```

**Description**: Mixins used for cross-cutting concerns, creating complex MRO chains and implicit dependencies.

**Consequences**:
- Multiple inheritance complexity (must understand MRO)
- Implicit dependencies (mixins expect certain attributes to exist)
- Testing difficulty (must mock mixin methods)
- LoggingMixin just wraps logging.getLogger() - minimal value

**Specific Example**:
```python
# Complex inheritance chain
class MainWindow(QtWidgetMixin, LoggingMixin, QMainWindow):
    # QtWidgetMixin inherits from LoggingMixin
    # So actually: MainWindow → QtWidgetMixin → LoggingMixin → QMainWindow
    # Must understand MRO to know which __init__ is called
```

**LoggingMixin Value Proposition**:
```python
# Mixin adds 443 lines to avoid:
class MyClass:
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

# Instead requires:
class MyClass(LoggingMixin):
    def __init__(self):
        super().__init__()  # Must remember to call super
        # self.logger now available via property
```

---

### 8. [Coupling] MEDIUM - MainWindow God Class

**Issue**: MainWindow has 35+ imports and depends on nearly every manager, controller, and model in the system

**Files Involved**: main_window.py (coordinates entire application)

**Imports**:
```python
# Managers (11+)
from cache_manager import CacheManager
from cleanup_manager import CleanupManager
from launcher_manager import LauncherManager
from notification_manager import NotificationManager
from process_pool_manager import ProcessPoolManager
from progress_manager import ProgressManager
from settings_manager import SettingsManager
from persistent_terminal_manager import PersistentTerminalManager
# ... more

# Controllers (3)
from controllers.launcher_controller import LauncherController
from controllers.settings_controller import SettingsController
from controllers.threede_controller import ThreeDEController

# Models (4+)
from shot_model import Shot, ShotModel
from threede_scene_model import ThreeDEScene, ThreeDESceneModel
from previous_shots_model import PreviousShotsModel
# ... more views, delegates, mixins
```

**Description**: MainWindow acts as composition root but is tightly coupled to implementation details of all components.

**Consequences**:
- Difficult to test in isolation
- Changes to any subsystem may require MainWindow changes
- 35+ imports = high coupling
- Refactoring is risky

**Partial Remediation**: RefreshOrchestrator extracted some logic but still depends on global singletons.

---

## Design Pattern Analysis

### Appropriate Pattern Usage

#### 1. Model-View-Delegate (Qt Standard)
**✅ APPROPRIATE**: Well-implemented Qt Model/View architecture
- `ShotItemModel`, `ThreeDEItemModel`, `PreviousShotsItemModel` → Qt models
- `ShotGridView`, `ThreeDEGridView` → Qt views
- `ShotGridDelegate`, `ThreeDEGridDelegate` → Qt delegates
- **Why appropriate**: Leverages Qt framework, clear separation of concerns

#### 2. Dataclasses for Value Objects
**✅ APPROPRIATE**: Simple immutable data structures
- `LaunchContext` - encapsulates launch parameters
- `LauncherParameter` - parameter configuration
- **Why appropriate**: Reduces parameter coupling, immutable by design

#### 3. Protocol Pattern (When Used Correctly)
**✅ APPROPRIATE**: `ProcessPoolInterface` defines clear contract
- Enables testing with mock implementations
- Clean interface definition
- **Why appropriate**: Used for dependency inversion, not to hide circular imports

### Inappropriate Pattern Usage

#### 1. Singleton Pattern (Overused)
**❌ INAPPROPRIATE**: 11 singleton managers for every cross-cutting concern

**Problems**:
- Global state management
- Testing complexity (requires reset() methods)
- Hidden dependencies (imported anywhere)
- Violates Dependency Inversion Principle

**Better Alternatives**:
- Simple module-level functions for utilities (SignalManager, CleanupManager)
- Dependency injection for services (CacheManager, ProgressManager)
- Qt parent-child relationships for lifecycle management

**Example**:
```python
# Current: Singleton with global state
ProgressManager.operation("Loading...")  # accessed anywhere

# Better: Context manager or simple function
with progress_dialog("Loading...") as progress:
    progress.update(50)
```

#### 2. Protocol Pattern (Misused for Circular Imports)
**❌ INAPPROPRIATE**: Used to mask circular dependencies with `Any` types

**Problems**:
- Loses type safety (uses `Any`)
- Hides architectural problems
- Creates maintenance burden

**Example**:
```python
# refresh_orchestrator.py - Protocol to avoid fixing circular import
class RefreshOrchestratorMainWindowProtocol(Protocol):
    tab_widget: Any  # Lost type safety!
    shot_model: Any
```

**Better Alternative**: Fix module structure to eliminate circular dependencies

#### 3. ABC Base Classes (Premature Abstraction)
**❌ INAPPROPRIATE**: Abstract base classes with 1-3 implementations

**Problems**:
- Premature generalization
- Navigation complexity
- YAGNI violation (built for future that never came)

**Example**:
```python
# base_shot_model.py - 381 lines for ONE implementation
class BaseShotModel(ABC):
    # Complex filtering, sorting, caching
    # Only ShotModel inherits from this
```

**Better Alternative**: Wait until 3+ implementations exist, then extract commonality

#### 4. Strategy Pattern (Over-Applied)
**❌ INAPPROPRIATE**: SceneDiscoveryStrategy with single implementation

**Problems**:
- Adds indirection without benefit
- No alternative strategies exist
- Could be simple methods

**Better Alternative**: Direct implementation until multiple strategies needed

#### 5. Coordinator/Orchestrator Pattern (Redundant)
**❌ INAPPROPRIATE**: Multiple coordinators for simple orchestration

**Problems**:
- RefreshOrchestrator: 200+ lines to coordinate 3 refresh operations
- SceneDiscoveryCoordinator: Coordinates strategy pattern
- FilesystemCoordinator: Just a cache wrapper

**Better Alternative**: Simple methods on appropriate classes

---

## Dependency & Coupling Analysis

### Circular Dependencies

**Count**: 30+ files use TYPE_CHECKING to avoid runtime circular imports

**Major Circular Dependency Groups**:

#### 1. MainWindow ↔ Controllers ↔ Managers
```
main_window.py → launcher_controller.py → launcher_manager.py
                                        ↓
                                  main_window.py (via Protocol)
```

#### 2. Scene Discovery Circular Chain
```
filesystem_scanner.py → filesystem_coordinator.py → scene_parser.py
        ↑                                               ↓
        └───────────────────────────────────────────────┘
# Broken with TYPE_CHECKING and lazy imports
```

#### 3. Model ↔ Cache ↔ Notification
```
shot_model.py → cache_manager.py → notification_manager.py
     ↑                                      ↓
     └──────────────────────────────────────┘
```

**Root Causes**:
1. God classes (MainWindow) that import everything
2. Managers that depend on each other
3. Bidirectional dependencies (Model → Cache, Cache → Model notifications)

**Suggested Fixes**:
1. **Dependency Inversion**: Controllers should depend on interfaces, not concrete managers
2. **Event Bus**: Replace direct notifications with event publication
3. **Composition Root**: Create explicit initialization layer that wires dependencies
4. **Module Restructuring**: Group by feature, not by technical layer

---

### Tight Coupling Hotspots

#### 1. MainWindow (35+ imports)
**Coupling Score**: VERY HIGH
- Imports 11 managers, 3 controllers, 4+ models, multiple views/delegates
- Changes to any subsystem ripple to MainWindow
- Nearly impossible to test in isolation

#### 2. CacheManager (1,151 lines, many dependents)
**Coupling Score**: HIGH
- Used by: MainWindow, Controllers, Models, Workers
- Knows about: Shot, ThreeDEScene, thumbnails, filesystem
- Should be split by responsibility

#### 3. ProgressManager (used everywhere)
**Coupling Score**: HIGH
- Global singleton accessed from any module
- 50+ call sites across codebase
- Creates hidden dependency (code fails without ProgressManager initialized)

#### 4. Controllers ↔ Managers Bidirectional
**Coupling Score**: HIGH
```
LauncherController → LauncherManager → LauncherController (for UI updates)
ThreeDEController → CacheManager → ThreeDEController (for refresh signals)
```

---

### Module Cohesion Issues

#### 1. utils.py (catch-all module)
**Problem**: Likely contains unrelated utility functions
**Impact**: Low cohesion, difficult to understand purpose

#### 2. Managers without clear single responsibility
- **CacheManager**: Handles shots, scenes, thumbnails, JSON, file I/O (too much)
- **NotificationManager**: Handles toasts, progress dialogs, messages (overlaps with ProgressManager)
- **LauncherManager**: Handles launcher storage + execution (should be separate)

#### 3. Split responsibilities
- **Two item model hierarchies**: BaseItemModel + BaseShotModel (why two?)
- **Two finder base classes**: ShotFinderBase + BaseAssetFinder (overlapping)

---

### Suggested Decoupling Strategies

#### 1. Introduce Event Bus / Mediator
**Current**: Direct manager-to-manager dependencies
```python
cache_manager.notify_users()  # direct call to NotificationManager
```

**Better**: Event publication
```python
events.publish("cache.cleared", cache_type="shots")
# Any component can subscribe without coupling
```

#### 2. Dependency Injection for Managers
**Current**: Global singleton imports
```python
from progress_manager import ProgressManager
ProgressManager.operation("Loading")  # accessed anywhere
```

**Better**: Constructor injection
```python
class MyView:
    def __init__(self, progress: ProgressService):
        self.progress = progress

    def load(self):
        with self.progress.operation("Loading"):
            ...
```

#### 3. Feature-Based Module Structure
**Current**: Technical layers (managers/, controllers/, models/)
```
managers/
  cache_manager.py
  progress_manager.py
controllers/
  launcher_controller.py
models/
  shot_model.py
```

**Better**: Feature modules
```
shots/
  model.py
  view.py
  cache.py
  controller.py
launcher/
  launcher.py
  config.py
common/
  progress.py
  notifications.py
```

#### 4. Extract Interfaces/Protocols (Correctly)
**Current**: Protocols with `Any` to hide circular imports

**Better**: Proper interface extraction
```python
# domain/interfaces.py (no dependencies)
class CacheProtocol(Protocol):
    def get_shots(self) -> list[Shot]: ...
    def cache_shot(self, shot: Shot) -> None: ...

# infrastructure/cache.py (implements interface)
class FileSystemCache:
    def get_shots(self) -> list[Shot]: ...

# No circular dependency - interface has no imports
```

---

## Abstraction Analysis

### Unnecessary Abstraction Layers

#### 1. Base Class for Single Implementation
**File**: `base_shot_model.py` (381 lines)
**Concrete Classes**: 1 (ShotModel)
**Abstraction Cost**: 381 lines of code, navigation complexity
**Justification**: "Future reuse" that never materialized
**Recommendation**: Merge into ShotModel, eliminate base class

#### 2. Strategy Pattern Without Multiple Strategies
**Files**:
- `scene_discovery_strategy.py`
- `scene_discovery_coordinator.py`

**Problem**: Strategy pattern requires multiple strategies. Only one exists.
**Abstraction Cost**: 2 extra files, indirection layer
**Recommendation**: Inline strategy into coordinator, wait for second strategy before abstracting

#### 3. SignalManager Wrapping Qt
**File**: `signal_manager.py` (506 lines)
**Purpose**: "Manage signal-slot connections with automatic cleanup"
**Problem**: Qt already provides this functionality
```python
# SignalManager adds 506 lines to do:
signal_manager.connect_safely(button.clicked, self.on_click)

# Qt's native approach:
button.clicked.connect(self.on_click)
# Qt handles cleanup when object is destroyed (parent-child relationship)
```
**Recommendation**: Remove SignalManager, use Qt's native signal management

#### 4. Three-Layer Abstraction for Directory Caching
**Files**:
- `filesystem_coordinator.py` (250 lines) - Coordinator
- `DirectoryCache` class in `filesystem_scanner.py` - Cache implementation
- `FilesystemScanner` class - Scanner with cache integration

**Problem**: 3 classes for directory listing cache
**Simplification**: Single FilesystemScanner with dict cache would be 50-100 lines

---

### Premature Generalizations

#### 1. Generic BaseItemModel[T]
**File**: `base_item_model.py` (838 lines)
**Implementations**: 3 (Shot, ThreeDEScene, PreviousShots)

**Over-Generalization**:
- Complex filtering system used by only 2 of 3 implementations
- Generic sorting infrastructure for 3 sort options
- Abstract methods that all implementations override identically

**Indicator**: Concrete implementations are nearly identical, suggesting base class captured wrong abstraction

**Recommendation**:
- Merge into single ItemModel[T] with minimal specialization
- Reduce from 838 → ~300 lines

#### 2. Mixin for Logging
**File**: `logging_mixin.py` (443 lines)
**Value Proposition**: Standardize logger setup

**Problem**: 443 lines to avoid writing:
```python
self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
```

**Over-Generalization**:
- ContextualLogger class (150+ lines) for context management
- log_execution decorator (100+ lines) for method timing
- Thread-local storage for logging context

**Most Usage**: Just accessing `self.logger.info()`
**Recommendation**: Simple property or class attribute, extract decorator to separate module

---

### YAGNI Violations (Built for Future)

#### 1. LauncherParameter Validation System
**File**: `launcher/models.py`
**Feature**: Comprehensive parameter validation (min/max, choices, types, file filters)
**Actual Usage**: Most launchers use 1-2 simple parameters
**YAGNI**: Built complex validation for "future custom launchers"
**Cost**: 200+ lines of parameter infrastructure

#### 2. Multiple Base Finder Classes
**Files**:
- `shot_finder_base.py`
- `base_asset_finder.py`
- `base_scene_finder.py`

**Intent**: "Reusable finder infrastructure for any asset type"
**Reality**: Only shots and scenes are actually found
**YAGNI**: "asset" abstraction never used beyond shots/scenes
**Recommendation**: Merge into single finder pattern

#### 3. Cache Merge Strategies
**File**: `cache_manager.py`
**Feature**: Incremental merging with ShotMergeResult, SceneMergeResult
```python
class ShotMergeResult(NamedTuple):
    updated_shots: list[ShotDict]
    new_shots: list[ShotDict]
    removed_shots: list[ShotDict]
    has_changes: bool
```
**Actual Usage**: Only "updated_shots" used, rest ignored
**YAGNI**: Built for complex merge UI that doesn't exist
**Recommendation**: Simplify to return merged list, remove detailed tracking

#### 4. FilesystemCoordinator
**File**: `filesystem_coordinator.py` (250 lines)
**Feature**: Coordinate filesystem access across multiple threads
**Reality**: Accessed from single thread (3DE worker)
**YAGNI**: Built for parallel filesystem scanning that isn't implemented
**Recommendation**: Simple directory cache, 50 lines

---

### Leaky Abstractions

#### 1. BaseItemModel Exposes Qt Implementation Details
**Problem**: Base class supposed to abstract item model, but concrete classes must understand:
- Qt model roles (DisplayRole, UserRole, DecorationRole)
- Row/column indexing
- Model reset signals
- Drag/drop MIME types

**Leak**: Abstraction doesn't hide Qt complexity, just adds layer on top

#### 2. BaseThumbnailDelegate Assumes Specific Data Structure
**Problem**: Delegate assumes models return specific dict keys:
- `"thumbnail_path"`
- `"full_name"`
- `"workspace_path"`

**Leak**: "Abstract" delegate is tightly coupled to concrete data format

#### 3. Protocol with Any Types
**Problem**: RefreshOrchestratorMainWindowProtocol uses `Any` for type hints
**Leak**: Protocol claims to provide type safety while using `Any` everywhere

---

## Simplification Roadmap

### Phase 1: Low-Hanging Fruit (2-3 weeks, Low Risk)

#### 1.1 Complete Launcher Migration
**Effort**: 3-4 days
**Risk**: Low (new system already proven)
**Action**:
- Remove deprecation warning, make simplified_launcher.py default
- Delete old launcher system (command_launcher.py, launcher_manager.py, /launcher/ package)
- Update MainWindow to use new launcher exclusively
**Impact**: Remove 2,543 lines, simplify architecture

#### 1.2 Eliminate Redundant Managers
**Effort**: 5-6 days
**Risk**: Low (simple functionality)
**Targets**:
- **SignalManager** (506 lines) → Use Qt's native signal management
- **CleanupManager** (239 lines) → Simple module-level cleanup functions
- **ThreadingManager** (389 lines) → Use Python threading/Qt QThread directly
- **FilesystemCoordinator** (250 lines) → Inline cache into scanner

**Action**:
```python
# Replace SignalManager usage
button.clicked.connect(self.on_click)  # Qt handles cleanup via parent-child

# Replace CleanupManager
def cleanup_application():
    """Module-level cleanup function."""
    close_connections()
    save_state()
```

**Impact**: Remove 1,384 lines, reduce singleton count by 4

#### 1.3 Merge Base Classes with Single Implementation
**Effort**: 2-3 days
**Risk**: Low (mechanical refactoring)
**Targets**:
- `base_shot_model.py` (381 lines, 1 implementation) → Merge into shot_model.py

**Impact**: Remove 381 lines, improve code navigation

---

### Phase 2: Medium Complexity (3-4 weeks, Medium Risk)

#### 2.1 Consolidate Finder Hierarchies
**Effort**: 1 week
**Risk**: Medium (multiple inheritance chains)
**Action**:
- Merge ShotFinderBase + BaseAssetFinder + BaseSceneFinder → Single BaseFinder
- Eliminate SceneDiscoveryStrategy + SceneDiscoveryCoordinator abstraction layers
- Simplify to: BaseFinder → ConcreteFinders (threede, maya, previous)

**Impact**: Reduce 13 finder files → 6 files, remove ~1,500 lines

#### 2.2 Simplify BaseItemModel Generic Hierarchy
**Effort**: 1 week
**Risk**: Medium (Qt model code requires careful testing)
**Action**:
- Reduce BaseItemModel from 838 lines to ~300 lines
- Remove unused filtering/sorting infrastructure
- Eliminate abstract methods all implementations override identically

**Current**:
```python
BaseItemModel[T] (838 lines)
  ├─ ShotItemModel (nearly identical)
  ├─ ThreeDEItemModel (nearly identical)
  └─ PreviousShotsItemModel (nearly identical)
```

**Target**:
```python
ItemModel[T] (300 lines)
  # Concrete classes only override data() method for specific display needs
```

**Impact**: Remove ~700 lines, simplify model architecture

#### 2.3 Replace LoggingMixin with Simple Pattern
**Effort**: 4-5 days
**Risk**: Low (mechanical refactoring, 77 classes use it)
**Action**:
```python
# Current: 443 lines of LoggingMixin
class MyClass(LoggingMixin, QObject):
    pass

# Target: Simple property or module-level helper
class MyClass(QObject):
    @property
    def logger(self):
        return logging.getLogger(f"{__name__}.{self.__class__.__name__}")

# Or even simpler - module-level logger:
logger = logging.getLogger(__name__)
```

**Impact**: Remove 443 lines, simplify inheritance chains

---

### Phase 3: Architectural Restructuring (4-6 weeks, Higher Risk)

#### 3.1 Fix Circular Dependencies
**Effort**: 2 weeks
**Risk**: High (requires careful refactoring of 30+ files)
**Action**:
- Create dependency-free interfaces in `domain/interfaces.py`
- Move concrete implementations to separate modules
- Establish clear dependency direction: UI → Controllers → Services → Domain
- Remove all TYPE_CHECKING workarounds

**Before**:
```
main_window.py ←→ controllers ←→ managers ←→ models
         (30+ files with TYPE_CHECKING hacks)
```

**After**:
```
UI Layer (main_window.py)
    ↓
Controller Layer (launcher_controller.py)
    ↓
Service Layer (cache_service.py, progress_service.py)
    ↓
Domain Layer (shot.py, scene.py) - no dependencies
```

**Impact**: Eliminate 30+ TYPE_CHECKING imports, enable proper dependency injection

#### 3.2 Consolidate Manager Singletons
**Effort**: 2-3 weeks
**Risk**: Medium-High (global state replacement)
**Targets**:
- CacheManager, ProgressManager, NotificationManager → Service classes with injection
- SettingsManager → Stay singleton (application-wide config is appropriate)

**Action**:
```python
# Current: Global singletons
from progress_manager import ProgressManager
ProgressManager.operation("Loading")

# Target: Dependency injection
class ShotView:
    def __init__(self, progress_service: ProgressService, cache_service: CacheService):
        self.progress = progress_service
        self.cache = cache_service

    def load_shots(self):
        with self.progress.operation("Loading"):
            shots = self.cache.get_shots()
```

**Benefits**:
- Testable (inject mocks)
- Explicit dependencies (no hidden globals)
- Proper lifecycle management

**Impact**: Reduce singleton count from 11 → 2-3, improve testability

#### 3.3 Feature-Based Module Restructuring (Optional)
**Effort**: 3-4 weeks
**Risk**: High (large-scale refactoring)
**Action**: Reorganize from technical layers to feature modules

**Before**:
```
shotbot/
  models/
  views/
  controllers/
  managers/
```

**After**:
```
shotbot/
  shots/
    model.py, view.py, controller.py, cache.py
  launcher/
    launcher.py, config.py, dialog.py
  threede/
    scene_model.py, discovery.py, view.py
  common/
    services/
      progress.py, notifications.py, settings.py
```

**Benefits**:
- Features are self-contained
- Easier to understand feature scope
- Reduced coupling between features

**Impact**: Improved maintainability, clearer architecture

---

### Phase 4: Protocol and Abstraction Cleanup (1-2 weeks, Low Risk)

#### 4.1 Remove Protocol Workarounds
**Effort**: 3-4 days
**Risk**: Low (assuming Phase 3.1 completed)
**Action**:
- Remove Protocols used to mask circular dependencies
- Replace with proper interface definitions
- Keep only legitimate Protocol usage (ProcessPoolInterface)

**Impact**: Remove 10+ unnecessary Protocol definitions

#### 4.2 Eliminate Unnecessary Base Classes
**Effort**: 1 week
**Risk**: Low
**Targets**:
- BaseGridView (448 lines) → Keep only if 3+ implementations truly share code
- BaseThumbnailDelegate (570 lines) → Merge common code, eliminate base class

**Rule of Three**: Don't create base class until 3+ implementations exist

**Impact**: Remove 1,000+ lines of premature abstraction

---

## Effort & Risk Assessment

### Summary Table

| Phase | Duration | Risk | Lines Removed | Complexity Reduction |
|-------|----------|------|---------------|---------------------|
| Phase 1 | 2-3 weeks | Low | ~4,308 | High (eliminate 4 singletons, deprecated code) |
| Phase 2 | 3-4 weeks | Medium | ~2,643 | Medium (simplify hierarchies) |
| Phase 3 | 4-6 weeks | High | ~3,000+ | Very High (fix architecture) |
| Phase 4 | 1-2 weeks | Low | ~1,000+ | Medium (cleanup) |
| **Total** | **10-15 weeks** | **Staged** | **~11,000 lines** | **40-50% reduction in architectural overhead** |

### Conservative Estimate
- **Total architectural overhead identified**: ~9,726 lines (managers + base classes)
- **Realistic reduction target**: 40-60% (4,000-6,000 lines)
- **Development time**: 2-3 months with testing
- **Risk mitigation**: Comprehensive test suite with 2,300+ tests provides safety net

### Precedent for Success
The **simplified_launcher.py** consolidation achieved:
- **80% reduction**: 3,153 lines → 610 lines
- **Eliminated**: Repository pattern, config abstraction, worker abstraction, validator abstraction
- **Maintained**: All functionality, cleaner API, better testability
- **Outcome**: Proves aggressive simplification is feasible

### Quick Wins (1-2 weeks)
Priority targets for immediate impact:
1. **SignalManager removal** (506 lines) - Use Qt native
2. **CleanupManager removal** (239 lines) - Module functions
3. **Complete launcher migration** (2,543 lines) - Already proven
4. **FilesystemCoordinator removal** (250 lines) - Inline cache

**Total Quick Wins**: 3,538 lines removed in 2 weeks (low risk)

---

## Recommendations

### Immediate Actions (This Quarter)
1. **Complete launcher migration** - Remove deprecated system
2. **Eliminate redundant managers** - SignalManager, CleanupManager, ThreadingManager
3. **Document architectural decisions** - Update ARCHITECTURE.md with rationale

### Short-Term (Next Quarter)
1. **Simplify base class hierarchies** - Merge single-implementation bases
2. **Consolidate finder pattern** - Single BaseFinder instead of 3
3. **Replace LoggingMixin** - Simple property pattern

### Long-Term (6+ months)
1. **Fix circular dependencies** - Proper module structure
2. **Dependency injection** - Replace global singletons
3. **Feature-based modules** - Reorganize by domain

### Architectural Principles Moving Forward

#### 1. Rule of Three
**Don't create abstraction until 3+ implementations exist**
- Wait for duplication before extracting base class
- Premature abstraction is worse than duplication

#### 2. YAGNI Enforcement
**Build for today's requirements, not tomorrow's possibilities**
- No "future-proofing" without concrete use case
- Delete unused abstractions

#### 3. Prefer Composition Over Inheritance
**Use mixins sparingly, prefer explicit composition**
```python
# Prefer:
class MyView:
    def __init__(self, logger, progress):
        self.logger = logger
        self.progress = progress

# Over:
class MyView(LoggingMixin, ProgressMixin):
    pass
```

#### 4. No Protocols for Circular Dependencies
**Fix the architecture, don't mask the problem**
- Protocols with `Any` types are code smell
- TYPE_CHECKING imports indicate circular dependency to fix

#### 5. Singleton Discipline
**Singletons only for true application-wide state**
- Settings: ✅ Appropriate (app-wide configuration)
- Cache: ❌ Should be injected service
- Progress: ❌ Should be injected service
- Notifications: ❌ Should be event bus or injected service

---

## Conclusion

The shotbot codebase demonstrates classic over-engineering patterns:
- Singleton proliferation (11 managers)
- Premature abstraction (base classes for 1-2 implementations)
- Pattern stacking (Strategy + Coordinator + Base + Protocol)
- Circular dependencies hidden with TYPE_CHECKING

However, **the simplified_launcher.py consolidation proves that aggressive simplification is achievable** (80% reduction). Conservative estimates suggest **40-60% reduction in architectural overhead** is realistic.

**Key Insight**: The codebase accumulated architectural complexity through "future-proofing" that never materialized. Most abstractions serve 1-3 implementations when they were built to serve many.

**Recommended Approach**: Staged simplification over 3-6 months:
1. Quick wins (redundant managers, deprecated code)
2. Hierarchy simplification (merge base classes)
3. Architectural fixes (circular dependencies, dependency injection)

The comprehensive test suite (2,300+ tests) provides a safety net for aggressive refactoring.
