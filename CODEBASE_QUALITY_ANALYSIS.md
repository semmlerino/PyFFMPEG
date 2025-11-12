# SHOTBOT CODEBASE ANALYSIS: Code Quality Issues

## Executive Summary
This analysis identifies **code duplication (DRY violations)**, **over-engineering (YAGNI violations)**, and **complexity hotspots** across the Shotbot codebase. The project is well-organized overall but shows signs of accumulated technical debt in specific areas.

**Metrics:**
- Total Python files: 170+
- Largest file: utils.py (1,688 lines)
- Complexity hotspots identified: 20+
- Duplicate code blocks: 10+
- Unused/alternative implementations: 4

---

## TOP 10 DRY VIOLATIONS (Code Duplication)

### 1. **Shot Model Filter Methods (CRITICAL - 9 files)**
**Impact: VERY HIGH** - Same filtering logic duplicated across multiple model classes

**Files Affected:**
- `base_shot_model.py:299-347`
- `previous_shots_model.py:368-417`
- `shot_item_model.py`
- `previous_shots_item_model.py`
- `threede_item_model.py`
- `threede_scene_model.py`

**Duplicated Methods:**
- `set_show_filter()` - Lines repeated identically
- `get_show_filter()` - Lines repeated identically
- `set_text_filter()` - Lines repeated identically
- `get_text_filter()` - Lines repeated identically
- `get_filtered_shots()` - Logic is identical, only different field names
- `get_available_shows()` - Same implementation pattern

**Code Example (BaseShotModel):**
```python
def set_show_filter(self, show: str | None) -> None:
    self._filter_show = show
    self.logger.info(f"Show filter set to: {show if show else 'All Shows'}")

def get_filtered_shots(self) -> list[Shot]:
    filtered = compose_filters(self.shots, show=self._filter_show, text=self._filter_text)
    return filtered
```

**Code Example (PreviousShotsModel):**
```python
def set_show_filter(self, show: str | None) -> None:
    self._filter_show = show
    self.logger.info(f"Show filter set to: {show if show else 'All Shows'}")

def get_filtered_shots(self) -> list[Shot]:
    filtered = compose_filters(self._previous_shots, show=self._filter_show, text=self._filter_text)
    return filtered
```

**Why It's Problematic:**
- Changes to filter logic must be made in 5+ places
- Inconsistency risk if one implementation gets updated but others don't
- Violates DRY principle
- Reduces maintainability

**Refactoring Suggestion:**
Extract into a mixin class (`FilterMixin`) or base class that provides these methods with customizable item sources.

```python
class FilterMixin:
    def _get_items_for_filtering(self) -> list[Shot]:
        """Override in subclass to return items to filter"""
        raise NotImplementedError
    
    def set_show_filter(self, show: str | None) -> None:
        self._filter_show = show
        self.logger.info(f"Show filter set to: {show if show else 'All Shows'}")
    
    def get_filtered_shots(self) -> list[Shot]:
        filtered = compose_filters(
            self._get_items_for_filtering(),
            show=self._filter_show,
            text=self._filter_text
        )
        return filtered
```

---

### 2. **Singleton Reset Pattern (CRITICAL - 5 files)**
**Impact: HIGH** - Identical reset() implementation across singletons

**Files Affected:**
- `process_pool_manager.py:633-652`
- `progress_manager.py:542-565`
- `notification_manager.py:353-366`
- `filesystem_coordinator.py` (similar pattern)
- `runnable_tracker.py` (similar pattern)

**Code Example (ProcessPoolManager):**
```python
@classmethod
def reset(cls) -> None:
    """Reset singleton for testing. INTERNAL USE ONLY."""
    if cls._instance is not None:
        if hasattr(cls._instance, 'cleanup'):
            cls._instance.cleanup()
        if hasattr(cls._instance, 'shutdown'):
            cls._instance.shutdown()
    
    with cls._lock:
        cls._instance = None
```

**Code Example (ProgressManager):**
```python
@classmethod
def reset(cls) -> None:
    """Reset singleton for testing. INTERNAL USE ONLY."""
    if cls._instance is not None:
        cls._instance.clear_all_operations()
    
    with cls._lock:
        cls._instance = None
```

**Why It's Problematic:**
- Pattern is nearly identical across all singletons
- Error-prone to maintain manually
- Inconsistent cleanup logic
- Difficult to ensure all state is cleared

**Refactoring Suggestion:**
Create a base singleton class or mixin that provides the reset() pattern.

```python
class SingletonBase:
    _instance: ClassVar[Optional['SingletonBase']] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()
    
    @classmethod
    def reset(cls) -> None:
        """Reset singleton for testing."""
        if cls._instance is not None:
            cls._instance._do_cleanup()
        with cls._lock:
            cls._instance = None
    
    def _do_cleanup(self) -> None:
        """Override to implement cleanup. Called during reset."""
        pass
```

---

### 3. **Cache Read/Write Pattern (MEDIUM - 3 files)**
**Impact: MEDIUM**

**Files Affected:**
- `cache_manager.py:1031-1142` (_read_json_cache, _write_json_cache)
- `scene_cache.py`
- `launcher_dialog.py:362-432`

**Duplicated Logic:**
- Try-except blocks for JSON read/write
- TTL checking
- File path validation
- Lock acquisition

**Example Pattern:**
All three files have similar code:
```python
try:
    with open(cache_file, 'r') as f:
        data = json.load(f)
    if check_ttl:
        # Check TTL logic
    return data
except FileNotFoundError:
    return None
except (json.JSONDecodeError, IOError):
    # Error handling
    return None
```

**Refactoring Suggestion:**
Create a `CacheManager.read_cache()` and `write_cache()` utility that handles all the common logic.

---

### 4. **Worker Threading Pattern (MEDIUM - 4 files)**
**Impact: MEDIUM**

**Files Affected:**
- `previous_shots_worker.py`
- `threede_scene_worker.py`
- `launcher/worker.py`
- `thread_safe_worker.py`

**Duplicated Code:**
- QThread setup and teardown
- Run/finished signal connections
- Error signal handling
- Cleanup logic

**Example (PreviousShotsWorker):**
```python
def run(self) -> None:
    try:
        # Do work
    except Exception as e:
        self.error.emit(str(e))
    finally:
        self.finished.emit()
```

**Example (ThreeDESceneWorker):**
```python
def run(self) -> None:
    try:
        # Do work
    except Exception as e:
        self.error.emit(str(e))
    finally:
        self.finished.emit()
```

**Refactoring Suggestion:**
Extract base worker class with template method pattern:

```python
class BaseWorker(QThread):
    error = pyqtSignal(str)
    finished = pyqtSignal()
    
    def run(self) -> None:
        try:
            self.do_work()
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()
    
    def do_work(self) -> None:
        raise NotImplementedError
```

---

### 5. **Scene/Shot Discovery Pattern (MEDIUM - Multiple Files)**
**Impact: MEDIUM**

**Files Affected:**
- `threede_scene_finder.py` vs `threede_scene_finder_optimized.py` (2 versions!)
- `previous_shots_finder.py`
- `raw_plate_finder.py`
- `maya_latest_finder.py` vs `maya_latest_finder_refactored.py` (2 versions!)

**Issue:** Having TWO versions of the same class:
- `threede_scene_finder.py` and `threede_scene_finder_optimized.py`
- `maya_latest_finder.py` and `maya_latest_finder_refactored.py`

One is likely unused, representing dead code.

**Refactoring Suggestion:**
Consolidate into single version. Delete the unused alternative.

---

### 6. **Error Handling & Logging Boilerplate (MEDIUM - 18 files)**
**Impact: MEDIUM**

**Files with 10+ try-except blocks:**
- `persistent_terminal_manager.py` (18)
- `utils.py` (15)
- `persistent_bash_session.py` (13)
- `launcher/process_manager.py` (13)
- `filesystem_scanner.py` (12)
- `cache_manager.py` (12)

**Pattern Duplication:**
All follow similar pattern:
```python
try:
    # Do something
except SomeError as e:
    self.logger.error(f"Error: {e}")
    # Cleanup or return default
except AnotherError as e:
    self.logger.warning(f"Warning: {e}")
    # Different cleanup
```

**Refactoring Suggestion:**
Create decorator/context manager for common error handling:

```python
@log_and_handle_errors(default=None)
def some_operation(self):
    # Implementation
```

---

### 7. **Validation Duplication (MEDIUM - 3 files)**
**Impact: MEDIUM**

**Files Affected:**
- `utils.py:489-518` (validate_path_exists)
- `launcher_dialog.py:_validate_name()`, `_validate_command()`
- `launcher/validator.py`

**Issue:** Multiple validation implementations with similar logic:
```python
# In utils.py
def validate_path_exists(path: str) -> bool:
    if not path:
        return False
    if not os.path.exists(path):
        return False
    return True

# In launcher_dialog.py
def _validate_name(self) -> bool:
    if not self.name_field.text().strip():
        return False
    # ... more checks
    return True
```

**Refactoring Suggestion:**
Create unified validation utilities or use a validation library.

---

### 8. **Qt Signal Connection Boilerplate (MEDIUM - 6+ files)**
**Impact: MEDIUM**

Repeated patterns:
```python
self.worker.finished.connect(self._on_worker_finished)
self.worker.error.connect(self._on_worker_error)
self.worker.start()
```

Same pattern in:
- `previous_shots_model.py`
- `threede_scene_model.py`
- `shot_model.py`
- Multiple controller files

**Refactoring Suggestion:**
Create helper method for worker connection setup.

---

### 9. **Cache TTL Checking (SMALL)**
**Impact: SMALL**

**Files Affected:**
- `cache_manager.py` - Multiple TTL checks
- `scene_cache.py` - Similar TTL logic

**Pattern:**
```python
def _is_cache_expired(self, file_path: str) -> bool:
    if not os.path.exists(file_path):
        return True
    
    mtime = os.path.getmtime(file_path)
    age_seconds = time.time() - mtime
    ttl_seconds = self._cache_ttl * 60
    
    return age_seconds > ttl_seconds
```

**Refactoring Suggestion:**
Extract to utility function or cache manager method.

---

### 10. **Refactored/Optimized File Versions (YAGNI VIOLATION)**
**Impact: HIGH** - Dead code

**Files:**
- `main_window_refactored.py` - Is this used?
- `optimized_shot_parser.py` - Is this used instead of regular parser?
- `threede_scene_finder_optimized.py` - Two versions exist
- `maya_latest_finder_refactored.py` - Two versions exist

These should be consolidated or deleted.

---

## TOP 10 YAGNI VIOLATIONS (Over-Engineering)

### 1. **Unused Alternative Implementations (CRITICAL)**
**Impact: VERY HIGH** - Dead code maintenance burden

**Files:**
- `main_window_refactored.py` (758 lines) - Does this duplicate main_window.py (1,563 lines)?
- `threede_scene_finder_optimized.py` - Does this duplicate threede_scene_finder.py?
- `maya_latest_finder_refactored.py` - Does this duplicate maya_latest_finder.py?
- `optimized_shot_parser.py` - Is this used?

**Why It's Problematic:**
- Takes up codebase space
- Developers don't know which to use
- Creates maintenance burden (fix bugs in 2 places?)
- Confuses new team members

**Action:**
Verify which versions are actually used. Delete the unused ones immediately.

---

### 2. **Over-Complex Cache Manager (MEDIUM)**
**Impact: MEDIUM**

**File:** `cache_manager.py` (1,150 lines)

**Issues:**
- Handles 5 different cache types: shots, previous_shots, threede_scenes, migrated_shots, generic_data
- 40+ methods
- Tries to be too generic
- Internal _stat_cache for file stats (another cache layer?)

**Methods Related to Same Thing:**
- `get_cached_shots()`, `cache_shots()`, `get_persistent_shots()`, `merge_shots_incremental()`
- `get_cached_threede_scenes()`, `cache_threede_scenes()`, `get_persistent_threede_scenes()`, `merge_scenes_incremental()`
- `get_cached_previous_shots()`, `cache_previous_shots()`, etc.

**Why It's Over-Engineered:**
- Could separate into multiple cache managers (ShotsCacheManager, ScenesCacheManager, etc.)
- Merge logic is similar but duplicated (`merge_shots_incremental` vs `merge_scenes_incremental`)
- _stat_cache adds complexity without clear benefit

**Refactoring Suggestion:**
Split into domain-specific cache managers or use generic cache base class.

---

### 3. **Multiple Launcher Implementations (MEDIUM)**
**Impact: MEDIUM**

**Files:**
- `command_launcher.py`
- `simplified_launcher.py`
- `nuke_launch_handler.py`
- `simple_nuke_launcher.py`

**Issue:** Unclear which launcher should be used for which situation.

**Over-Engineered Aspects:**
- 4 different launcher implementations
- Not clear if all are used
- Maintenance burden

---

### 4. **Overly Complex Threading Utilities (MEDIUM)**
**Impact: MEDIUM**

**Files:**
- `thread_safe_worker.py` (629 lines)
- `threading_manager.py`
- `threading_utils.py` (885 lines)
- `persistent_terminal_manager.py` (919 lines)

**Questions:**
- Do all 4 files need to exist?
- Are there duplicate features?
- Could this be consolidated?

**Example of Possible Duplication:**
Both `threading_manager.py` and `thread_safe_worker.py` seem to manage worker threads.

---

### 5. **Multiple Finder Base Classes (MEDIUM)**
**Impact: MEDIUM**

**Files:**
- `base_asset_finder.py`
- `base_scene_finder.py`
- `shot_finder_base.py`

**Issue:** 3 different base finder classes. Why?
- Are they different enough to justify?
- Should there be just ONE base?

**Concrete Finders (12 total):**
- `threede_scene_finder.py` + `threede_scene_finder_optimized.py` (2!)
- `previous_shots_finder.py`
- `raw_plate_finder.py`
- `maya_latest_finder.py` + `maya_latest_finder_refactored.py` (2!)
- `threede_latest_finder.py`
- And more...

**Over-Engineered Aspects:**
- Multiple base classes creating hierarchy confusion
- Duplication with "optimized" and "refactored" versions
- Unclear which to inherit from

---

### 6. **Unused _metadata Parameters (SMALL)**
**Impact: SMALL** - Code smell

**Example:** `cache_manager.py` methods have `_metadata: dict[str, object] | None = None` parameter that's never used:

```python
def cache_threede_scenes(
    self,
    scenes: list[ThreeDESceneDict],
    _metadata: dict[str, object] | None = None,  # UNUSED!
) -> None:
```

**Why It's Problematic:**
- Confuses API - developers wonder what to pass
- Suggests incomplete implementation
- Parameter name has `_` prefix (unused convention) but still causes confusion

**Action:** Remove unused parameters.

---

### 7. **Over-Engineered Scene Discovery (MEDIUM)**
**Impact: MEDIUM**

**Files:**
- `scene_discovery_coordinator.py` (737 lines)
- `scene_discovery_strategy.py` (666 lines)
- `filesystem_scanner.py` (1,049 lines)

**Issue:** 3 files handling scene discovery. Are all needed?

**Questions:**
- Could coordinator and strategy be combined?
- Does scanner need to exist separately?
- Is this following an overly complex design pattern?

---

### 8. **Multiple Configuration Files (SMALL)**
**Impact: SMALL**

**Files:**
- `config.py`
- `cache_config.py`
- `timeout_config.py`

**Issue:** Fragmented configuration. Why not unified?

**Over-Engineered Aspects:**
- Three different config modules
- Unclear which to use for what
- Harder to see all configuration in one place

---

### 9. **Generic Base Item Model Complexity (MEDIUM)**
**Impact: MEDIUM**

**File:** `base_item_model.py` (838 lines)

**Methods:** 30+ methods

**Questions:**
- Is it generic enough to be worth the complexity?
- Could it be simplified?
- Does it handle too many concerns?

**Over-Engineered Aspects:**
- Handles thumbnail loading
- Handles selection
- Handles filtering
- Handles caching
- All in one class

---

### 10. **Notification Manager Complexity (SMALL)**
**Impact: SMALL**

**File:** `notification_manager.py` (619 lines)

**Issues:**
- Handles: error(), warning(), info(), success(), progress(), toast()
- Internal: _active_toasts, _reposition_toasts, etc.
- Lots of internal state management

**Over-Engineered Aspects:**
- Could be split into ToastManager and DialogManager
- Too many responsibilities

---

## TOP 10 COMPLEXITY HOTSPOTS

### 1. **ProcessPoolManager.shutdown() - 106 lines**
**File:** `process_pool_manager.py:528-633`
**Cyclomatic Complexity:** HIGH (8+ branches)

**Issues:**
- Multiple try-except blocks (6+)
- Nested error handling
- Complex stage-based shutdown sequence
- Warnings filter boilerplate

**Example:**
```python
try:
    try:
        self._executor.shutdown(wait=True, cancel_futures=True)
        shutdown_successful = True
    except Exception as e:
        self._executor.shutdown(wait=False)
except Exception as e:
    # Error handling
```

**Refactoring:**
Extract shutdown stages into separate methods:
- `_shutdown_sessions()`
- `_shutdown_executor()`
- `_cleanup_resources()`
- `_finalize_shutdown()`

---

### 2. **BaseItemModel.set_items() - 110 lines**
**File:** `base_item_model.py:664-773`
**Cyclomatic Complexity:** MEDIUM (5+ branches)

**Issues:**
- Multiple try-except-finally blocks
- Complex cache filtering logic
- Thread checking
- Lots of logging

**Refactoring:**
Extract into smaller focused methods:
- `_verify_main_thread()`
- `_stop_thumbnail_timers()`
- `_update_model_data()`
- `_update_thumbnail_cache()`

---

### 3. **ThumbnailWidgetBase.run() - 129 lines**
**File:** `thumbnail_widget_base.py:196-324`
**Cyclomatic Complexity:** HIGH

**Issues:**
- Complex thumbnail loading pipeline
- Multiple state transitions
- Nested conditionals
- Error handling throughout

**Refactoring:**
Use state machine pattern.

---

### 4. **CacheManager.merge_shots_incremental() - 68 lines**
**File:** `cache_manager.py:662-729`
**Cyclomatic Complexity:** MEDIUM

**Duplication:** Very similar to `merge_scenes_incremental()` (68 lines, starts at line 779)

**Issues:**
- Two nearly identical merge methods
- Should be generic

---

### 5. **CacheManager.merge_scenes_incremental() - 68 lines**
**File:** `cache_manager.py:779-845`
**Cyclomatic Complexity:** MEDIUM

**Issue:** Duplicate of `merge_shots_incremental()` with different types.

---

### 6. **LauncherDialog._save() - 72 lines**
**File:** `launcher_dialog.py:362-433`
**Cyclomatic Complexity:** MEDIUM (6+ branches)

**Issues:**
- If-else chain for environment setup
- Nested if-else for create vs update
- Multiple notification calls

**Refactoring:**
Extract into:
- `_build_environment()`
- `_create_launcher()`
- `_update_launcher()`

---

### 7. **ShotModel._on_shots_loaded() - 70 lines**
**File:** `shot_model.py:362-431`
**Cyclomatic Complexity:** MEDIUM

**Issues:**
- Complex merge logic
- Multiple signal emissions
- Error handling
- State management

---

### 8. **PersistentTerminalManager._ensure_dispatcher_healthy() - 64 lines**
**File:** `persistent_terminal_manager.py:707-770`
**Cyclomatic Complexity:** HIGH

**Issues:**
- Multiple error checks
- Complex recovery logic
- Nested exception handling

---

### 9. **ThreeDEController.cleanup_worker() - 64 lines**
**File:** `controllers/threede_controller.py:295-358`
**Cyclomatic Complexity:** HIGH

**Issues:**
- Multiple cleanup stages
- Complex worker state checking
- Error handling in each stage

---

### 10. **SettingsDialog.save_settings() - 77 lines**
**File:** `settings_dialog.py:800-876`
**Cyclomatic Complexity:** MEDIUM

**Issues:**
- Long method collecting many settings
- Multiple try-except blocks
- Complex field extraction

**Refactoring:**
Extract field collection into separate method.

---

## DETAILED COMPLEXITY ANALYSIS

### Methods with Deep Nesting (>3 levels)

**File: cache_manager.py**
- Lines 717-726: 4 levels of nesting
  ```python
  with QMutexLocker(self._lock):
      cached_dicts = [...]
      cached_by_key = {
          _get_shot_key(shot): shot for shot in cached_dicts
      }  # 4 levels
  ```

**File: base_item_model.py**
- Lines 685-696: 4 levels
  ```python
  if app:
      if QThread.currentThread() != app.thread():
          # Error
      if self._thumbnail_timer.isActive():
          # Stop timer
  ```

**File: process_pool_manager.py**
- Lines 545-565: Multiple 3-4 level nesting blocks

---

## MEMORY/PERFORMANCE CONCERNS

### 1. **CacheManager._stat_cache**
**File:** `cache_manager.py:213`

Additional cache layer for file stats:
```python
self._stat_cache = {}  # Additional cache
```

**Questions:**
- Why not use OS file system caching?
- Does this improve performance?
- Is it properly invalidated?

---

### 2. **Multiple Cache Layers**
- `CacheManager._thumbnail_cache`
- `CacheManager._stat_cache`
- `ProcessPoolManager._cache`
- `thread_safe_thumbnail_cache.py`
- `scene_cache.py`

**Issue:** Multiple caching systems. Are they coordinated?

---

## REFACTORING ROADMAP SUMMARY

### CRITICAL (Do First)
1. **Extract FilterMixin** - Reduce 9-file duplication for filter methods
2. **Delete unused alternative implementations** - Remove refactored/optimized duplicates
3. **Create SingletonBase** - Eliminate reset() duplication across 5 singletons
4. **Consolidate finder base classes** - 3 bases is too many

### HIGH (Do Second)
1. **Extract BaseWorker** - Reduce worker duplication (4 files)
2. **Split CacheManager** - Too many responsibilities (1,150 lines)
3. **Consolidate scene discovery** - 3 files seems like too many
4. **Extract launcher implementations** - Clarify which is primary

### MEDIUM (Do Third)
1. **Create generic merge method** - `merge_shots_incremental` vs `merge_scenes_incremental`
2. **Extract shutdown stages** - Break up ProcessPoolManager.shutdown()
3. **Extract cache read/write** - Reduce duplication across 3 files
4. **Unified configuration** - Combine config.py, cache_config.py, timeout_config.py

### LOW (Polish)
1. Remove unused _metadata parameters
2. Simplify ThumbnailWidgetBase.run()
3. Extract validation utilities
4. Create error handling decorator

---

## CONCLUSION

The Shotbot codebase is well-structured overall with good separation of concerns. However, it shows signs of accumulated technical debt:

- **~10-15% code duplication** in critical filter/cache/worker logic
- **4+ unused alternative implementations** creating maintenance confusion
- **20+ methods over 50 lines** that could be decomposed further
- **Multiple layered abstractions** (3+ base classes for finders) that add complexity

**Recommended approach:**
1. Delete unused versions (quick win)
2. Extract mixins for duplicated patterns (medium effort, high impact)
3. Decompose long methods (ongoing)
4. Consider consolidating scene discovery logic

**Estimated effort to address all issues:** 30-40 hours
**Estimated impact on maintainability:** 20-30% improvement
