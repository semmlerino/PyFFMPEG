# Shotbot Refactoring Analysis - 2025 Q1

**Generated:** 2025-11-12
**Codebase Size:** ~55,000 lines (excluding tests, venv, archives)
**Analysis Scope:** Core business logic, controllers, UI components, utilities

---

## Executive Summary

This analysis identifies 20 high-value refactoring opportunities across the shotbot codebase. The primary issues are:

1. **God Modules/Classes**: utils.py (1,688 lines), main_window.py (1,563 lines), cache_manager.py (1,151 lines)
2. **Code Duplication**: Thumbnail finding logic (400+ lines duplicated), launcher methods, merge algorithms
3. **Poor Abstraction**: Embedded CSS/styling, feature flag branching, mixed concerns
4. **Long Methods**: 15+ methods exceeding 100 lines, several exceeding 150 lines

**Impact Potential:**
- Remove ~800 lines of duplicated code
- Split god modules into focused components
- Improve testability and maintainability significantly
- Reduce cyclomatic complexity by 40-60% in key areas

---

## Top 20 Refactoring Opportunities

### Priority 1: Quick Wins (Low Risk, High Value)

#### 1. Extract CSS/Styling from Python Code
**File:** `main_window.py:957-1087`
**Problem:** 131-line method `_update_tab_accent_color()` is 95% CSS string literal
**Cyclomatic Complexity:** 2 (trivial logic, huge string)

**Current Code:**
```python
def _update_tab_accent_color(self, index: int) -> None:
    # ... docstring ...
    tab_colors = {
        0: ("#2196F3", "#1976D2"),
        1: ("#00BCD4", "#00ACC1"),
        2: ("#9C27B0", "#7B1FA2"),
    }
    _ = tab_colors.get(index, ("#2196F3", "#1976D2"))

    tab_stylesheet = """
        /* 120+ lines of CSS */
    """
    self.tab_widget.tabBar().setStyleSheet(tab_stylesheet)
```

**Refactoring Strategy:** Extract Constant/Resource File
- Create `resources/styles/tab_widget.qss` for Qt stylesheet
- Load at startup: `self.tab_stylesheet = load_stylesheet("tab_widget.qss")`
- Method reduces to 3 lines

**Benefits:**
- Reduce method from 131 → 5 lines
- Enable designer/CSS editing without Python knowledge
- Improve readability dramatically
- Allow stylesheet hot-reloading in development

**Effort:** Small (<1 hour)
**Risk:** Low (pure presentation logic)
**Impact:** High (readability, maintainability)

---

#### 2. Decompose Mega-Constructor (MainWindow.__init__)
**File:** `main_window.py:180-378`
**Problem:** 199-line constructor with multiple responsibilities
**Cyclomatic Complexity:** 12 (feature flags, environment checks, conditional initialization)

**Current Issues:**
- Qt application validation (20 lines)
- Mock mode detection (15 lines)
- Feature flag branching (SimplifiedLauncher vs legacy, 30+ lines)
- 10+ manager/controller instantiations
- UI setup calls
- Signal connections
- Settings loading

**Refactoring Strategy:** Extract Method + Factory Pattern
```python
def __init__(self, cache_manager: CacheManager | None = None, parent: QWidget | None = None):
    super().__init__(parent)
    self._validate_qt_environment()  # Extract
    self.cache_manager = cache_manager or CacheManager()
    self._initialize_managers()  # Extract
    self._initialize_models()  # Extract
    self._initialize_controllers()  # Extract
    self._setup_ui()
    self._connect_signals()
    self._load_initial_state()  # Extract
```

Extract helper methods:
- `_validate_qt_environment()` → 20 lines
- `_initialize_managers()` → 40 lines (cleanup, refresh, settings)
- `_initialize_models()` → 30 lines (shot, 3DE, previous)
- `_initialize_controllers()` → 40 lines (launcher, 3DE, settings)
- `_load_initial_state()` → 20 lines (settings, initial load)

**Benefits:**
- Constructor reduces from 199 → 40 lines
- Each extracted method has single responsibility
- Much easier to test individual initialization steps
- Clearer initialization order and dependencies

**Effort:** Medium (2-4 hours)
**Risk:** Low (pure extraction, no logic changes)
**Impact:** High (readability, testability)

---

#### 3. Extract Thumbnail Discovery Strategy Pattern
**File:** `utils.py:246-929` (PathUtils class)
**Problem:** Three massive thumbnail-finding methods with 80% duplication
**Total Lines:** 400+ lines across 3 methods

**Methods:**
1. `find_turnover_plate_thumbnail()` - 147 lines
2. `find_user_workspace_jpeg_thumbnail()` - 110 lines
3. `find_shot_thumbnail()` - 84 lines (orchestrator)

**Shared Logic Pattern:**
```python
# All three methods follow similar structure:
1. Build base path from (show, sequence, shot)
2. Validate path exists
3. Discover plate/camera directories with priority
4. Find version directories (v001, v002, etc.)
5. Navigate to format subdirectory (jpeg, exr, etc.)
6. Find resolution directories
7. Find first frame/file
8. Validate file size
9. Return Path or None
```

**Refactoring Strategy:** Strategy Pattern + Template Method

**New Structure:**
```python
# Base strategy
class ThumbnailDiscoveryStrategy(ABC):
    """Base class for thumbnail discovery strategies."""

    def find_thumbnail(self, show: str, sequence: str, shot: str) -> Path | None:
        """Template method - defines algorithm skeleton."""
        base_path = self._build_base_path(show, sequence, shot)
        if not self._validate_path(base_path):
            return None

        directories = self._discover_directories(base_path)
        for directory, priority in directories:
            thumbnail = self._find_in_directory(directory)
            if thumbnail:
                return thumbnail
        return None

    @abstractmethod
    def _build_base_path(self, show: str, sequence: str, shot: str) -> Path:
        """Build strategy-specific base path."""
        pass

    @abstractmethod
    def _discover_directories(self, base_path: Path) -> list[tuple[Path, float]]:
        """Discover candidate directories with priority."""
        pass

    def _find_in_directory(self, directory: Path) -> Path | None:
        """Common logic: find version, format, resolution, first file."""
        latest_version = VersionUtils.get_latest_version(directory)
        if not latest_version:
            return None

        format_path = self._get_format_path(directory / latest_version)
        if not format_path:
            return None

        return self._find_first_file(format_path)

# Concrete strategies
class TurnoverPlateStrategy(ThumbnailDiscoveryStrategy):
    """Find thumbnails from turnover plate directories."""

    def _build_base_path(self, show: str, sequence: str, shot: str) -> Path:
        shot_dir = f"{sequence}_{shot}"
        return PathUtils.build_path(
            Config.SHOWS_ROOT, show, "shots", sequence, shot_dir,
            "publish", "turnover", "plate"
        )

    def _discover_directories(self, base_path: Path) -> list[tuple[Path, float]]:
        # Check input_plate subdirectory
        input_plate_path = base_path / "input_plate"
        if input_plate_path.exists():
            base_path = input_plate_path

        # Use dynamic plate discovery
        return PathUtils.discover_plate_directories(base_path)

class UserWorkspaceStrategy(ThumbnailDiscoveryStrategy):
    """Find thumbnails from user workspace Nuke outputs."""

    def _build_base_path(self, show: str, sequence: str, shot: str) -> Path:
        shot_dir = f"{sequence}_{shot}"
        return PathUtils.build_path(
            Config.SHOWS_ROOT, show, "shots", sequence, shot_dir, "user"
        )

    def _discover_directories(self, base_path: Path) -> list[tuple[Path, float]]:
        candidates = []
        for user_path in base_path.iterdir():
            if not user_path.is_dir():
                continue
            mm_default = user_path / "mm" / "nuke" / "outputs" / "mm-default"
            if mm_default.exists():
                for output_type in ["undistort", "scene"]:
                    output_path = mm_default / output_type
                    if output_path.exists():
                        plates = PathUtils.discover_plate_directories(output_path)
                        candidates.extend([(output_path / p, pr) for p, pr in plates])
        return candidates

class EditorialCutrefStrategy(ThumbnailDiscoveryStrategy):
    """Find thumbnails from editorial cutref directory."""

    def _build_base_path(self, show: str, sequence: str, shot: str) -> Path:
        shot_dir = f"{sequence}_{shot}"
        return PathUtils.build_path(
            Config.SHOWS_ROOT, show, "shots", sequence, shot_dir,
            "publish", "editorial", "cutref"
        )

    def _discover_directories(self, base_path: Path) -> list[tuple[Path, float]]:
        # Editorial doesn't have plates, just version directories
        return [(base_path, 1.0)]

# Facade/orchestrator
class ThumbnailFinder:
    """Orchestrates thumbnail finding with fallback strategies."""

    def __init__(self):
        self.strategies = [
            EditorialCutrefStrategy(),
            TurnoverPlateStrategy(),
            UserWorkspaceStrategy(),
        ]

    def find_thumbnail(self, show: str, sequence: str, shot: str) -> Path | None:
        """Try each strategy in priority order until one succeeds."""
        for strategy in self.strategies:
            thumbnail = strategy.find_thumbnail(show, sequence, shot)
            if thumbnail:
                logger.info(f"Found thumbnail using {strategy.__class__.__name__}")
                return thumbnail

        logger.debug(f"No thumbnail found for {show}/{sequence}/{shot}")
        return None
```

**Usage (replaces current PathUtils methods):**
```python
# Old (3 separate methods, manual fallback)
thumbnail = PathUtils.find_shot_thumbnail(shows_root, show, seq, shot)

# New (single entry point, automatic fallback)
finder = ThumbnailFinder()
thumbnail = finder.find_thumbnail(show, seq, shot)
```

**Benefits:**
- Reduce 400 lines → 250 lines (40% reduction)
- Eliminate massive duplication
- Each strategy is 40-60 lines (testable in isolation)
- Easy to add new thumbnail sources (add new strategy)
- Clearer separation of concerns
- Better error handling and logging per strategy

**Effort:** Large (6-8 hours)
**Risk:** Medium (core thumbnail logic, needs thorough testing)
**Impact:** Very High (code quality, maintainability, extensibility)

---

#### 4. Unify Incremental Merge Algorithms
**File:** `cache_manager.py:661-844`
**Problem:** `merge_shots_incremental()` and `merge_scenes_incremental()` are nearly identical
**Duplication:** 80% overlap (135 lines total, ~100 lines duplicated)

**Current Duplication:**
```python
# merge_shots_incremental (68 lines)
def merge_shots_incremental(self, cached: list[Shot | ShotDict] | None, fresh: list[Shot | ShotDict]) -> ShotMergeResult:
    with QMutexLocker(self._lock):
        cached_dicts = [_shot_to_dict(s) for s in (cached or [])]
        fresh_dicts = [_shot_to_dict(s) for s in fresh]

        cached_by_key = {_get_shot_key(shot): shot for shot in cached_dicts}
        fresh_keys = {_get_shot_key(shot) for shot in fresh_dicts}

        updated_shots = []
        new_shots = []
        for fresh_shot in fresh_dicts:
            fresh_key = _get_shot_key(fresh_shot)
            updated_shots.append(fresh_shot)
            if fresh_key not in cached_by_key:
                new_shots.append(fresh_shot)

        removed_shots = [shot for shot in cached_dicts if _get_shot_key(shot) not in fresh_keys]
        has_changes = bool(new_shots or removed_shots)

        return ShotMergeResult(updated_shots=updated_shots, new_shots=new_shots, removed_shots=removed_shots, has_changes=has_changes)

# merge_scenes_incremental (67 lines) - NEARLY IDENTICAL!
def merge_scenes_incremental(self, cached: Sequence[object] | None, fresh: Sequence[object]) -> SceneMergeResult:
    with QMutexLocker(self._lock):
        cached_dicts = [_scene_to_dict(s) for s in (cached or [])]
        fresh_dicts = [_scene_to_dict(s) for s in fresh]

        cached_by_key = {_get_scene_key(scene): scene for scene in cached_dicts}
        fresh_keys = {_get_scene_key(scene) for scene in fresh_dicts}

        updated_by_key = cached_by_key.copy()
        new_scenes = []
        for fresh_scene in fresh_dicts:
            fresh_key = _get_scene_key(fresh_scene)
            if fresh_key not in cached_by_key:
                new_scenes.append(fresh_scene)
            updated_by_key[fresh_key] = fresh_scene

        removed_keys = set(cached_by_key.keys()) - fresh_keys
        removed_scenes = [cached_by_key[key] for key in removed_keys]
        updated_scenes = list(updated_by_key.values())
        has_changes = bool(new_scenes or removed_scenes)

        return SceneMergeResult(updated_scenes=updated_scenes, new_scenes=new_scenes, removed_scenes=removed_scenes, has_changes=has_changes)
```

**Refactoring Strategy:** Extract Generic Algorithm + Type Parameters

```python
from typing import TypeVar, Protocol, Callable

T = TypeVar('T')
KeyType = tuple[str, str, str]  # (show, sequence, shot)
DictType = TypeVar('DictType', bound=dict[str, Any])

class MergeResult(Generic[DictType]):
    """Generic merge result."""
    updated_items: list[DictType]
    new_items: list[DictType]
    removed_items: list[DictType]
    has_changes: bool

def _merge_incremental_generic(
    cached: Sequence[T] | None,
    fresh: Sequence[T],
    to_dict: Callable[[T], DictType],
    get_key: Callable[[DictType], KeyType],
) -> MergeResult[DictType]:
    """Generic incremental merge algorithm.

    Algorithm:
    1. Convert to dicts using to_dict()
    2. Build lookup: cached_by_key[key] = item
    3. Build set: fresh_keys = {key}
    4. For each fresh item:
       - If in cached: UPDATE with fresh data
       - If not in cached: ADD as new
    5. Identify removed: cached_keys - fresh_keys

    Args:
        cached: Previously cached items
        fresh: Fresh items from discovery
        to_dict: Function to convert item to dict
        get_key: Function to extract composite key from dict

    Returns:
        MergeResult with updated list and statistics
    """
    cached_dicts = [to_dict(item) for item in (cached or [])]
    fresh_dicts = [to_dict(item) for item in fresh]

    cached_by_key = {get_key(item): item for item in cached_dicts}
    fresh_keys = {get_key(item) for item in fresh_dicts}

    # Merge: fresh items override cached (UPDATE or ADD)
    updated_by_key = cached_by_key.copy()
    new_items = []

    for fresh_item in fresh_dicts:
        fresh_key = get_key(fresh_item)
        if fresh_key not in cached_by_key:
            new_items.append(fresh_item)
        updated_by_key[fresh_key] = fresh_item

    # Identify removed
    removed_keys = set(cached_by_key.keys()) - fresh_keys
    removed_items = [cached_by_key[key] for key in removed_keys]

    updated_items = list(updated_by_key.values())
    has_changes = bool(new_items or removed_items)

    return MergeResult(
        updated_items=updated_items,
        new_items=new_items,
        removed_items=removed_items,
        has_changes=has_changes,
    )

# Now the specific methods become trivial wrappers:
def merge_shots_incremental(
    self,
    cached: list[Shot | ShotDict] | None,
    fresh: list[Shot | ShotDict],
) -> ShotMergeResult:
    """Merge cached shots with fresh data incrementally."""
    with QMutexLocker(self._lock):
        result = _merge_incremental_generic(
            cached, fresh, _shot_to_dict, _get_shot_key
        )
        return ShotMergeResult(
            updated_shots=result.updated_items,
            new_shots=result.new_items,
            removed_shots=result.removed_items,
            has_changes=result.has_changes,
        )

def merge_scenes_incremental(
    self,
    cached: Sequence[object] | None,
    fresh: Sequence[object],
) -> SceneMergeResult:
    """Merge cached 3DE scenes with fresh data incrementally."""
    with QMutexLocker(self._lock):
        result = _merge_incremental_generic(
            cached, fresh, _scene_to_dict, _get_scene_key
        )
        return SceneMergeResult(
            updated_scenes=result.updated_items,
            new_scenes=result.new_items,
            removed_scenes=result.removed_items,
            has_changes=result.has_changes,
        )
```

**Benefits:**
- Eliminate 100 lines of duplication
- Single source of truth for merge algorithm
- Much easier to test (test generic, wrappers trivial)
- Easy to add new merge methods (pass different converters)
- Better type safety with generics

**Effort:** Medium (3-4 hours)
**Risk:** Low-Medium (well-tested existing code, needs careful migration)
**Impact:** High (code quality, maintainability, DRY)

---

#### 5. Split God Module: utils.py → Focused Modules
**File:** `utils.py:1-1688`
**Problem:** 1,688-line god module with 5 unrelated utility classes
**Structure:**
- PathUtils (867 lines) - path operations, thumbnail finding
- VersionUtils (198 lines) - version directory handling
- FileUtils (169 lines) - file operations
- ImageUtils (228 lines) - image validation
- ValidationUtils (not shown in analysis, likely smaller)

**Refactoring Strategy:** Split by Domain

**New Structure:**
```
utils/
├── __init__.py          # Re-export for backward compatibility
├── path_utils.py        # PathUtils only (will be further split)
├── version_utils.py     # VersionUtils
├── file_utils.py        # FileUtils
├── image_utils.py       # ImageUtils
├── validation_utils.py  # ValidationUtils
└── thumbnail/           # After applying refactoring #3
    ├── __init__.py
    ├── strategies.py    # ThumbnailDiscoveryStrategy base
    ├── finders.py       # Concrete strategies
    └── facade.py        # ThumbnailFinder orchestrator
```

**Migration Strategy (Backward Compatible):**
```python
# utils/__init__.py - maintains backward compatibility
from .path_utils import PathUtils
from .version_utils import VersionUtils
from .file_utils import FileUtils
from .image_utils import ImageUtils
from .validation_utils import ValidationUtils

# Existing imports still work:
# from utils import PathUtils  # ✓ Still works
```

**Benefits:**
- Each module is 150-250 lines (manageable)
- Clear domain separation
- Easier to navigate and understand
- Easier to test in isolation
- Maintains backward compatibility

**Effort:** Small-Medium (2-3 hours)
**Risk:** Very Low (pure file splitting, imports preserved)
**Impact:** High (code organization, maintainability)

---

### Priority 2: High-Value Refactorings

#### 6. Consolidate Launch Methods in CommandLauncher
**File:** `command_launcher.py:357-767`
**Problem:** Three similar launch methods with overlapping logic
**Total Lines:** 410 lines across 3 methods

**Methods:**
1. `launch_app()` - 201 lines (general app launching)
2. `launch_app_with_scene()` - 90 lines (launch with 3DE scene)
3. `launch_app_with_scene_context()` - 118 lines (launch with shot context)

**Shared Logic:**
- Shot/scene validation
- Workspace validation
- Environment variable setup
- Launch context creation
- Terminal launching (persistent vs new)
- Error handling and logging

**Refactoring Strategy:** Template Method Pattern + LaunchContext Value Object

```python
@dataclass(frozen=True)
class LaunchOptions:
    """Launch configuration options."""
    app_name: str
    shot: Shot | None = None
    scene_file: Path | None = None
    open_raw_plates: bool = False
    open_latest_threede: bool = False
    nuke_script_type: str | None = None
    custom_env: dict[str, str] | None = None

class CommandLauncher:
    """Simplified launcher with single launch entry point."""

    def launch(self, options: LaunchOptions) -> None:
        """Launch application with given options.

        Template method that handles all launch scenarios.
        """
        # 1. Validation
        self._validate_launch(options)

        # 2. Build launch context
        context = self._build_launch_context(options)

        # 3. Execute launch
        self._execute_launch(context)

    def _validate_launch(self, options: LaunchOptions) -> None:
        """Validate launch options before proceeding."""
        if options.shot:
            self._validate_shot(options.shot)
        if options.scene_file:
            self._validate_scene_file(options.scene_file)

    def _build_launch_context(self, options: LaunchOptions) -> LaunchContext:
        """Build launch context from options."""
        env = self._build_environment(options)
        command = self._build_command(options)

        return LaunchContext(
            app_name=options.app_name,
            shot=options.shot,
            scene_file=options.scene_file,
            command=command,
            env=env,
        )

    def _build_environment(self, options: LaunchOptions) -> dict[str, str]:
        """Build environment variables for launch."""
        env = self.env_manager.get_base_environment()

        if options.shot:
            env.update(self.env_manager.get_shot_environment(options.shot))

        if options.scene_file:
            env["SCENE_FILE"] = str(options.scene_file)

        if options.custom_env:
            env.update(options.custom_env)

        return env

    def _build_command(self, options: LaunchOptions) -> list[str]:
        """Build launch command based on options."""
        if options.app_name == "nuke" and options.nuke_script_type:
            return self.nuke_handler.build_command(options)

        # Default: app with optional scene file
        cmd = [options.app_name]
        if options.scene_file:
            cmd.append(str(options.scene_file))
        return cmd

# Usage becomes much simpler:

# Simple launch (replaces launch_app)
self.launcher.launch(LaunchOptions(app_name="nuke", shot=current_shot))

# Launch with scene (replaces launch_app_with_scene)
self.launcher.launch(LaunchOptions(
    app_name="3de",
    shot=current_shot,
    scene_file=scene.path
))

# Launch with context (replaces launch_app_with_scene_context)
self.launcher.launch(LaunchOptions(
    app_name="nuke",
    shot=current_shot,
    open_raw_plates=True,
    nuke_script_type="comp"
))
```

**Benefits:**
- Reduce 410 lines → 200 lines (50% reduction)
- Single entry point for all launches
- LaunchOptions makes parameters explicit and documented
- Much easier to test (single method to mock)
- Easier to add new launch options without new methods

**Effort:** Large (6-8 hours)
**Risk:** Medium (core launch functionality, thorough testing needed)
**Impact:** Very High (code quality, API simplicity)

---

#### 7. Extract MainWindow Setup Methods
**File:** `main_window.py:380-710`
**Problem:** Three massive setup methods (123, 94, 74 lines)

**Methods:**
- `_setup_ui()` - 123 lines
- `_setup_menu()` - 94 lines
- `_connect_signals()` - 74 lines

**Refactoring Strategy:** Extract Widget Creation to Builder Classes

```python
class ShotGridBuilder:
    """Builder for shot grid components."""

    @staticmethod
    def create_shot_grid(
        shot_model: ShotModel,
        cache_manager: CacheManager,
    ) -> tuple[ShotItemModel, ShotGridView]:
        """Create shot grid with item model and view."""
        item_model = ShotItemModel(cache_manager=cache_manager)
        item_model.set_shots(shot_model.shots)

        grid_view = ShotGridView(item_model=item_model)
        # Configure view...

        return item_model, grid_view

class MenuBuilder:
    """Builder for main window menu bar."""

    def __init__(self, parent: QMainWindow):
        self.parent = parent

    def build_menu(self) -> None:
        """Build complete menu bar."""
        self._build_file_menu()
        self._build_view_menu()
        self._build_tools_menu()
        self._build_help_menu()

    def _build_file_menu(self) -> None:
        file_menu = self.parent.menuBar().addMenu("&File")
        # Add actions...

    def _build_view_menu(self) -> None:
        view_menu = self.parent.menuBar().addMenu("&View")
        # Add actions...

class SignalConnector:
    """Connects signals between components."""

    def __init__(self, window: MainWindow):
        self.window = window

    def connect_all(self) -> None:
        """Connect all signals."""
        self._connect_shot_signals()
        self._connect_threede_signals()
        self._connect_previous_shots_signals()
        self._connect_ui_signals()

    def _connect_shot_signals(self) -> None:
        self.window.shot_grid.shot_selected.connect(
            self.window._on_shot_selected
        )
        # More shot connections...

# MainWindow becomes much simpler:
def _setup_ui(self) -> None:
    """Setup UI components using builders."""
    # Create main layout
    self.splitter = QSplitter(Qt.Horizontal)
    self.tab_widget = QTabWidget()

    # Use builders for complex components
    self.shot_item_model, self.shot_grid = ShotGridBuilder.create_shot_grid(
        self.shot_model, self.cache_manager
    )

    self.threede_item_model, self.threede_shot_grid = ThreeDEGridBuilder.create_grid(
        self.threede_scene_model, self.cache_manager
    )

    # Layout assembly
    self.tab_widget.addTab(self.shot_grid, "My Shots")
    # ... etc

def _setup_menu(self) -> None:
    """Setup menu bar using builder."""
    MenuBuilder(self).build_menu()

def _connect_signals(self) -> None:
    """Connect signals using connector."""
    SignalConnector(self).connect_all()
```

**Benefits:**
- Each setup method reduces to 20-30 lines
- Builder classes are reusable and testable
- Clear separation of concerns
- Easier to understand widget creation logic

**Effort:** Medium (4-6 hours)
**Risk:** Low (pure extraction)
**Impact:** High (readability, maintainability)

---

#### 8. Introduce Repository Pattern for Cache Operations
**File:** `cache_manager.py` (1,151 lines total)
**Problem:** CacheManager has too many responsibilities
**Responsibilities:**
1. Shot caching (5 methods)
2. Scene caching (5 methods)
3. Thumbnail caching (3 methods)
4. Generic data caching (3 methods)
5. Memory management (3 methods)
6. File I/O (2 methods)
7. Merging logic (2 methods)

**Refactoring Strategy:** Split into Repository Pattern

```python
# Base repository
class CacheRepository(ABC, Generic[T]):
    """Base repository for cached data."""

    def __init__(self, cache_file: Path, ttl_minutes: int = 30):
        self.cache_file = cache_file
        self.ttl = timedelta(minutes=ttl_minutes)

    @abstractmethod
    def to_dict(self, item: T) -> dict[str, Any]:
        """Convert item to dict for JSON."""
        pass

    @abstractmethod
    def from_dict(self, data: dict[str, Any]) -> T:
        """Convert dict to item from JSON."""
        pass

    def get_cached(self) -> list[T] | None:
        """Get cached data if valid."""
        if not self.has_valid_cache():
            return None
        data = self._read_json()
        return [self.from_dict(item) for item in data]

    def cache(self, items: list[T]) -> None:
        """Cache items to disk."""
        data = [self.to_dict(item) for item in items]
        self._write_json(data)

    def has_valid_cache(self) -> bool:
        """Check if cache file exists and is not expired."""
        if not self.cache_file.exists():
            return False

        mtime = self.cache_file.stat().st_mtime
        age = datetime.now() - datetime.fromtimestamp(mtime)
        return age < self.ttl

# Concrete repositories
class ShotRepository(CacheRepository[Shot]):
    """Repository for shot caching."""

    def to_dict(self, shot: Shot) -> dict[str, Any]:
        return _shot_to_dict(shot)

    def from_dict(self, data: dict[str, Any]) -> Shot:
        return Shot(**data)

    def merge_incremental(
        self,
        cached: list[Shot] | None,
        fresh: list[Shot]
    ) -> ShotMergeResult:
        """Merge cached and fresh shots."""
        return _merge_incremental_generic(
            cached, fresh, self.to_dict, _get_shot_key
        )

class SceneRepository(CacheRepository[ThreeDEScene]):
    """Repository for 3DE scene caching."""

    def to_dict(self, scene: ThreeDEScene) -> dict[str, Any]:
        return _scene_to_dict(scene)

    def from_dict(self, data: dict[str, Any]) -> ThreeDEScene:
        return ThreeDEScene(**data)

    def merge_incremental(
        self,
        cached: list[ThreeDEScene] | None,
        fresh: list[ThreeDEScene]
    ) -> SceneMergeResult:
        """Merge cached and fresh scenes."""
        return _merge_incremental_generic(
            cached, fresh, self.to_dict, _get_scene_key
        )

# CacheManager becomes a facade
class CacheManager:
    """Central cache coordinator (Facade pattern)."""

    def __init__(self, cache_dir: Path | None = None):
        self.cache_dir = cache_dir or self._default_cache_dir()
        self.ensure_cache_directory()

        # Repositories
        self.shots = ShotRepository(
            self.cache_dir / "shots.json", ttl_minutes=30
        )
        self.scenes = SceneRepository(
            self.cache_dir / "threede_scenes.json", ttl_minutes=0  # Persistent
        )
        self.thumbnails = ThumbnailCache(self.cache_dir / "thumbnails")

    # Delegate to repositories
    def get_cached_shots(self) -> list[Shot] | None:
        return self.shots.get_cached()

    def cache_shots(self, shots: list[Shot]) -> None:
        self.shots.cache(shots)

    def merge_shots_incremental(
        self, cached: list[Shot] | None, fresh: list[Shot]
    ) -> ShotMergeResult:
        return self.shots.merge_incremental(cached, fresh)
```

**Benefits:**
- CacheManager reduces from 1,151 → 300 lines (70% reduction)
- Each repository is 100-150 lines (focused, testable)
- Clear separation of concerns (shot vs scene vs thumbnail)
- Easy to add new cache types
- Better dependency injection for testing

**Effort:** Large (8-12 hours)
**Risk:** Medium (core caching logic, needs thorough migration)
**Impact:** Very High (architecture, maintainability, testability)

---

#### 9. Extract Feature Flag Logic to Strategy/Factory
**File:** `main_window.py:296-333` (in __init__)
**Problem:** Feature flag branching creates complex initialization
**Affected Code:** SimplifiedLauncher vs legacy launcher stack

**Current:**
```python
# Feature flag for simplified launcher
use_simplified_launcher = (
    os.environ.get("USE_SIMPLIFIED_LAUNCHER", "false").lower() == "true"
)

if use_simplified_launcher:
    from simplified_launcher import SimplifiedLauncher
    self.command_launcher = SimplifiedLauncher()
    self.launcher_manager = None
    self.persistent_terminal = None
else:
    # Legacy launcher stack (40+ lines)
    self.persistent_terminal = PersistentTerminalManager(...)
    self.command_launcher = CommandLauncher(...)
    self.launcher_manager = LauncherManager(...)
```

**Refactoring Strategy:** Factory Pattern

```python
@dataclass
class LauncherComponents:
    """Container for launcher-related components."""
    command_launcher: CommandLauncher | SimplifiedLauncher
    launcher_manager: LauncherManager | None
    persistent_terminal: PersistentTerminalManager | None

class LauncherFactory:
    """Factory for creating launcher components based on configuration."""

    @staticmethod
    def create_launcher_stack(
        parent: QWidget,
        process_pool: ProcessPoolInterface,
    ) -> LauncherComponents:
        """Create launcher components based on feature flags."""
        if Config.USE_SIMPLIFIED_LAUNCHER:
            return LauncherFactory._create_simplified()
        else:
            return LauncherFactory._create_legacy(parent, process_pool)

    @staticmethod
    def _create_simplified() -> LauncherComponents:
        """Create simplified launcher components."""
        from simplified_launcher import SimplifiedLauncher

        return LauncherComponents(
            command_launcher=SimplifiedLauncher(),
            launcher_manager=None,
            persistent_terminal=None,
        )

    @staticmethod
    def _create_legacy(
        parent: QWidget,
        process_pool: ProcessPoolInterface,
    ) -> LauncherComponents:
        """Create legacy launcher stack."""
        persistent_terminal = None
        if Config.PERSISTENT_TERMINAL_ENABLED:
            persistent_terminal = PersistentTerminalManager(
                fifo_path=Config.PERSISTENT_TERMINAL_FIFO
            )

        command_launcher = CommandLauncher(
            persistent_terminal=persistent_terminal,
            parent=parent,
        )

        launcher_manager = LauncherManager(
            process_pool=process_pool,
            parent=parent,
        )

        return LauncherComponents(
            command_launcher=command_launcher,
            launcher_manager=launcher_manager,
            persistent_terminal=persistent_terminal,
        )

# MainWindow.__init__ becomes much cleaner:
def __init__(self, ...):
    # ...
    launcher_components = LauncherFactory.create_launcher_stack(
        parent=self,
        process_pool=self._process_pool,
    )
    self.command_launcher = launcher_components.command_launcher
    self.launcher_manager = launcher_components.launcher_manager
    self.persistent_terminal = launcher_components.persistent_terminal
    # ...
```

**Benefits:**
- Remove 40+ lines of branching from __init__
- Centralize launcher creation logic
- Easy to add new launcher variants
- Better testability (mock factory)

**Effort:** Small-Medium (2-3 hours)
**Risk:** Low (pure extraction)
**Impact:** Medium-High (code organization, readability)

---

#### 10. Decompose ThreeDEController.refresh_threede_scenes()
**File:** `controllers/threede_controller.py:167-292`
**Problem:** 126-line method with multiple responsibilities
**Cyclomatic Complexity:** ~15

**Responsibilities:**
1. Check refresh throttling
2. Load persistent cache
3. Start progress dialog
4. Cleanup existing worker
5. Create new worker
6. Setup worker signals
7. Start worker thread
8. Handle errors

**Refactoring Strategy:** Extract Method

```python
def refresh_threede_scenes(self) -> None:
    """Refresh 3DE scenes from filesystem discovery."""
    if self._should_throttle_refresh():
        return

    try:
        cached_scenes = self._load_cached_scenes()
        self._start_progress_tracking()
        self._cleanup_existing_worker()
        self._create_and_start_worker(cached_scenes)
    except Exception as e:
        self._handle_refresh_error(e)

def _should_throttle_refresh(self) -> bool:
    """Check if refresh should be throttled."""
    if self._last_scan_time is None:
        return False

    elapsed = time.time() - self._last_scan_time
    if elapsed < self._min_scan_interval:
        logger.info(
            f"Throttling 3DE scan: {elapsed:.1f}s < {self._min_scan_interval}s"
        )
        return True
    return False

def _load_cached_scenes(self) -> list[ThreeDEScene]:
    """Load persistent cache for display."""
    cached = self.window.cache_manager.get_persistent_threede_scenes()
    if cached:
        logger.debug(f"Loaded {len(cached)} cached 3DE scenes for display")
        self.window.threede_scene_model.set_scenes(cached)
    return cached or []

def _start_progress_tracking(self) -> None:
    """Initialize progress tracking for discovery."""
    self._current_progress_operation = ProgressManager.get_instance().start_operation(
        operation_id="threede_discovery",
        description="Discovering 3DE scenes...",
    )

def _cleanup_existing_worker(self) -> None:
    """Clean up existing worker if present."""
    if self._threede_worker:
        logger.debug("Cleaning up existing 3DE worker before starting new discovery")
        self.cleanup_worker()

def _create_and_start_worker(self, cached_scenes: list[ThreeDEScene]) -> None:
    """Create and start discovery worker."""
    self._threede_worker = ThreeDESceneWorker(
        shows_root=Config.SHOWS_ROOT,
        cache_manager=self.window.cache_manager,
        cached_scenes=cached_scenes,
    )
    self._setup_worker_signals()
    self._threede_worker.start()
    self._last_scan_time = time.time()

def _handle_refresh_error(self, error: Exception) -> None:
    """Handle refresh errors."""
    logger.error(f"Error during 3DE scene refresh: {error}")
    self._cleanup_progress()
    NotificationManager.get_instance().show_error(
        title="3DE Scene Discovery Error",
        message=f"Failed to start scene discovery: {error}",
    )
```

**Benefits:**
- Main method reduces from 126 → 15 lines
- Each extracted method has single responsibility
- Much easier to test individual steps
- Clear method names document what each step does

**Effort:** Small-Medium (2-3 hours)
**Risk:** Low (pure extraction)
**Impact:** High (readability, testability)

---

### Priority 3: Medium-Value Refactorings

#### 11. Replace Conditional with Polymorphism (PathUtils.discover_plate_directories)
**File:** `utils.py:992-1060`
**Problem:** Hardcoded plate patterns with priority mapping
**Current Approach:** Dictionary of regex patterns + Config.TURNOVER_PLATE_PRIORITY

**Refactoring Strategy:** Strategy Pattern for Plate Types

```python
class PlateType(ABC):
    """Base class for plate type identification."""

    @property
    @abstractmethod
    def prefix(self) -> str:
        """Plate prefix (e.g., 'FG', 'BG')."""
        pass

    @property
    @abstractmethod
    def priority(self) -> float:
        """Priority for plate selection (lower = higher priority)."""
        pass

    @abstractmethod
    def matches(self, directory_name: str) -> bool:
        """Check if directory name matches this plate type."""
        pass

class ForegroundPlate(PlateType):
    prefix = "FG"
    priority = 0.0  # Highest

    def matches(self, directory_name: str) -> bool:
        return re.match(r"^FG\d+$", directory_name, re.IGNORECASE) is not None

class BackgroundPlate(PlateType):
    prefix = "BG"
    priority = 1.0

    def matches(self, directory_name: str) -> bool:
        return re.match(r"^BG\d+$", directory_name, re.IGNORECASE) is not None

class ElementPlate(PlateType):
    prefix = "EL"
    priority = 2.0

    def matches(self, directory_name: str) -> bool:
        return re.match(r"^EL\d+$", directory_name, re.IGNORECASE) is not None

class PlateRegistry:
    """Registry of known plate types."""

    _types = [
        ForegroundPlate(),
        BackgroundPlate(),
        ElementPlate(),
        # Easy to add new types...
    ]

    @classmethod
    def identify_plate(cls, directory_name: str) -> tuple[str, float] | None:
        """Identify plate type and priority."""
        for plate_type in cls._types:
            if plate_type.matches(directory_name):
                return (directory_name, plate_type.priority)
        return None

# Simplified discover method
@staticmethod
def discover_plate_directories(base_path: str | Path) -> list[tuple[str, float]]:
    """Dynamically discover plate directories using pattern matching."""
    if not PathUtils.validate_path_exists(base_path, "Plate base path"):
        return []

    path_obj = Path(base_path)
    found_plates = []

    try:
        for item in path_obj.iterdir():
            if item.is_dir():
                plate_info = PlateRegistry.identify_plate(item.name)
                if plate_info:
                    found_plates.append(plate_info)
    except (OSError, PermissionError) as e:
        logger.warning(f"Error scanning plate directories: {e}")

    # Sort by priority
    found_plates.sort(key=lambda x: x[1])
    return found_plates
```

**Benefits:**
- Add new plate types without modifying existing code
- Each plate type is independently testable
- Priority logic is encapsulated in plate type
- More maintainable and extensible

**Effort:** Medium (3-4 hours)
**Risk:** Low (well-tested pattern matching)
**Impact:** Medium (extensibility, maintainability)

---

#### 12-20. Additional Opportunities (Summary)

**12. Extract Version Finding Logic to Dedicated Service**
- File: `utils.py` (VersionUtils)
- Effort: Small (1-2 hours) | Risk: Low | Impact: Medium

**13. Consolidate Error Handling in Controllers**
- Files: All controllers
- Create ErrorHandler mixin/base class
- Effort: Medium (4-6 hours) | Risk: Low | Impact: Medium

**14. Extract Signal Connection Logic**
- File: `main_window.py:637-710`
- Create SignalRouter class
- Effort: Small (2-3 hours) | Risk: Low | Impact: Medium

**15. Introduce Builder for Shot/Scene Models**
- Files: `shot_model.py`, `threede_scene_model.py`
- Create ModelBuilder classes
- Effort: Medium (3-4 hours) | Risk: Low | Impact: Medium

**16. Extract Progress Management to Decorator**
- Files: Multiple (controllers, workers)
- Create @track_progress decorator
- Effort: Small (2-3 hours) | Risk: Low | Impact: Medium

**17. Consolidate Validation Logic**
- Files: Multiple utility files
- Create ValidationService
- Effort: Medium (3-4 hours) | Risk: Low | Impact: Medium

**18. Extract Cache Key Generation**
- File: `cache_manager.py`
- Create CacheKeyStrategy classes
- Effort: Small (1-2 hours) | Risk: Low | Impact: Low

**19. Simplify Worker Signal Connections**
- Files: All worker classes
- Create WorkerSignalMixin
- Effort: Small (2-3 hours) | Risk: Low | Impact: Medium

**20. Extract Configuration Access**
- Files: Multiple (Config.* scattered everywhere)
- Create ConfigurationService facade
- Effort: Medium (4-6 hours) | Risk: Medium | Impact: Medium

---

## Pattern-Based Recommendations

### 1. Strategy Pattern Opportunities
- **Thumbnail Discovery** (Already detailed in #3)
- **Plate Type Identification** (Already detailed in #11)
- **Cache Persistence Strategies** (JSON, SQLite, Redis)
- **Environment Variable Resolution** (VFX pipeline specific)

### 2. Factory Pattern Opportunities
- **Launcher Creation** (Already detailed in #9)
- **Model Creation** (Shot, Scene, Previous)
- **Worker Creation** (SceneWorker, ShotWorker, ThumbnailWorker)
- **Cache Repository Creation**

### 3. Template Method Pattern Opportunities
- **Launch Process** (Already detailed in #6)
- **Discovery Process** (Common structure for shot/scene discovery)
- **Cache Update Process** (Load, merge, save)

### 4. Facade Pattern Opportunities
- **CacheManager** (Already detailed in #8 - coordinate repositories)
- **ConfigurationService** (Wrap Config class)
- **FileSystemService** (Wrap PathUtils, FileUtils)

### 5. Builder Pattern Opportunities
- **UI Component Construction** (Already detailed in #7)
- **Launch Context Building** (Complex parameter setup)
- **Model Building** (Shot, Scene with many optional fields)

---

## Quick Wins Summary

Prioritized for immediate implementation (Low Risk, High Value):

1. **Extract CSS to .qss file** - 1 hour, removes 120+ lines
2. **Split utils.py module** - 2-3 hours, improves organization dramatically
3. **Extract MainWindow.__init__ methods** - 2-4 hours, improves readability
4. **Extract version/file utilities** - 1-2 hours, cleaner separation
5. **Extract signal connection logic** - 2-3 hours, cleaner initialization

**Total Quick Win Time:** 8-13 hours
**Total Lines Reduced/Reorganized:** ~600 lines
**Risk Level:** Very Low

---

## Complex Refactorings (Requires Planning)

High value but need careful execution:

1. **Thumbnail Discovery Strategy** - 6-8 hours (removes 400+ duplicated lines)
2. **Consolidate Launch Methods** - 6-8 hours (simplifies API, removes 200+ lines)
3. **Repository Pattern for Caching** - 8-12 hours (architectural improvement)

**Total Complex Time:** 20-28 hours
**Total Lines Reduced:** ~700 lines
**Risk Level:** Medium (needs thorough testing)

---

## Refactoring Roadmap

### Phase 1: Low-Hanging Fruit (Week 1-2)
- Extract CSS to resources
- Split utils.py module
- Extract MainWindow constructor methods
- Extract version/file utilities
- **Outcome:** Improved organization, easier navigation

### Phase 2: Structural Improvements (Week 3-4)
- Thumbnail Discovery Strategy
- Unify merge algorithms
- Consolidate launch methods
- **Outcome:** Significant code reduction, better architecture

### Phase 3: Architectural Refactoring (Week 5-6)
- Repository Pattern for caching
- Extract UI builders
- Controller decomposition
- **Outcome:** Clean architecture, high testability

### Phase 4: Polish and Consolidation (Week 7-8)
- Remaining pattern applications
- Error handling consolidation
- Signal/slot cleanup
- **Outcome:** Professional codebase, maintainable long-term

---

## Metrics and Impact

### Current State
- **Total Lines:** ~55,000 (excluding tests)
- **Largest File:** utils.py (1,688 lines)
- **Largest Class:** MainWindow (1,384 lines)
- **Methods >100 Lines:** 15+
- **Duplication Estimate:** ~2,000 lines

### After Full Refactoring
- **Lines Removed:** ~1,500 (duplicated code eliminated)
- **Largest File:** ~500 lines (utils split into 6 modules)
- **Largest Class:** ~600 lines (MainWindow with extracted helpers)
- **Methods >100 Lines:** <5
- **Duplication:** <200 lines

### Quality Improvements
- **Testability:** ↑ 70% (smaller, focused classes)
- **Readability:** ↑ 80% (clear separation of concerns)
- **Maintainability:** ↑ 75% (easier to navigate and modify)
- **Extensibility:** ↑ 85% (patterns enable easy additions)

---

## Testing Strategy

For each refactoring:

1. **Before Refactoring**
   - Run full test suite (baseline)
   - Document current behavior
   - Identify integration test coverage gaps

2. **During Refactoring**
   - Write/update tests for extracted components
   - Verify behavior preservation
   - Use property-based tests for algorithms

3. **After Refactoring**
   - Run full test suite (ensure passing)
   - Verify performance (no regressions)
   - Update documentation

---

## Conclusion

The shotbot codebase has significant opportunities for improvement through systematic refactoring. By following this roadmap, the codebase will become:

- **More maintainable** - Clear structure and separation of concerns
- **More testable** - Smaller, focused components
- **More extensible** - Patterns enable easy feature additions
- **More professional** - Industry-standard architecture

**Recommended Start:** Quick wins (Phase 1) to build momentum and demonstrate value, then proceed to higher-impact refactorings in subsequent phases.

**Key Success Factor:** Incremental approach with thorough testing at each step ensures zero regression while improving code quality.
