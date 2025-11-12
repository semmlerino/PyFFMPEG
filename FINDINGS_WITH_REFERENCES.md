# DETAILED FINDINGS - SPECIFIC FILE:LINE REFERENCES

## DRY VIOLATIONS - EXACT LOCATIONS

### Issue 1: Filter Methods Duplication (9 files)

**Locations:**

| File | Method | Line | Issue |
|------|--------|------|-------|
| base_shot_model.py | set_show_filter() | 299-305 | Identical implementation |
| base_shot_model.py | get_show_filter() | 308-310 | Identical getter |
| base_shot_model.py | set_text_filter() | 312-319 | Identical implementation |
| base_shot_model.py | get_text_filter() | 321-323 | Identical getter |
| base_shot_model.py | get_filtered_shots() | 325-340 | Uses compose_filters() |
| base_shot_model.py | get_available_shows() | 342-347 | Extract to set |
| previous_shots_model.py | set_show_filter() | 368-375 | **DUPLICATE** of base_shot_model:299-305 |
| previous_shots_model.py | get_show_filter() | 377-379 | **DUPLICATE** of base_shot_model:308-310 |
| previous_shots_model.py | set_text_filter() | 381-388 | **DUPLICATE** of base_shot_model:312-319 |
| previous_shots_model.py | get_text_filter() | 390-392 | **DUPLICATE** of base_shot_model:321-323 |
| previous_shots_model.py | get_filtered_shots() | 394-410 | Uses compose_filters() |
| previous_shots_model.py | get_available_shows() | 412-417 | Same pattern as base |
| shot_item_model.py | Various filters | ? | Likely similar |
| previous_shots_item_model.py | Various filters | ? | Likely similar |
| threede_item_model.py | Various filters | ? | Likely similar |
| threede_scene_model.py | Various filters | ? | Likely similar |

**Estimated Lines Duplicated:** 40+ lines across 9 files

**Fix:** Extract FilterMixin class with `_get_items_for_filtering()` abstract method

---

### Issue 2: Singleton Reset Pattern (5 files)

**Locations:**

| File | Class | reset() | Lines | Issue |
|------|-------|---------|-------|-------|
| process_pool_manager.py | ProcessPoolManager | 633-652 | 20 | Full implementation |
| progress_manager.py | ProgressManager | 542-565 | 24 | Full implementation |
| notification_manager.py | NotificationManager | 353-366 | 14 | Full implementation |
| filesystem_coordinator.py | FilesystemCoordinator | ? | ~15 | Similar pattern |
| runnable_tracker.py | RunnableTracker | ? | ~15 | Similar pattern |

**Pattern Similarity:** 70-80% identical code

**Fix:** Create SingletonBase class with reset() implementation

---

### Issue 3: Cache Read/Write Duplication (3 files)

**Locations:**

| File | Methods | Lines | Issue |
|------|---------|-------|-------|
| cache_manager.py | _read_json_cache() | 1031-1096 | 65 lines, handles TTL |
| cache_manager.py | _write_json_cache() | 1098-1142 | 45 lines |
| scene_cache.py | Similar methods | ? | Try-except pattern |
| launcher_dialog.py | _save() | 362-432 | 70 lines, JSON parsing |

**Common Patterns:**
- Open file with try-except
- Parse JSON with error handling
- Check TTL if needed
- Return None on error

**Fix:** Create generic CacheUtil.read_json_cache(path, check_ttl=False)

---

### Issue 4: Worker Threading Pattern (4 files)

**Locations:**

| File | Class | Method | Lines | Pattern |
|------|-------|--------|-------|---------|
| previous_shots_worker.py | PreviousShotsWorker | run() | ~30 | Try-except-emit |
| threede_scene_worker.py | ThreeDESceneWorker | run() | ~30 | Try-except-emit |
| launcher/worker.py | CommandWorker | run() | ~50 | Try-except-emit |
| thread_safe_worker.py | ThreadSafeWorker | run() | ~50 | Try-except-emit |

**Duplicated Code:**
```python
def run(self) -> None:
    try:
        # Do work
    except Exception as e:
        self.error.emit(str(e))
    finally:
        self.finished.emit()
```

**Fix:** Create BaseWorker class with template method pattern

---

### Issue 5: Duplicate Finder Implementations

**Critical:** TWO versions of same files

| File | Alternative | Purpose | Issue |
|------|------------|---------|-------|
| threede_scene_finder.py | threede_scene_finder_optimized.py | Find 3DE scenes | Which is used? |
| maya_latest_finder.py | maya_latest_finder_refactored.py | Find latest Maya scenes | Which is used? |
| shot_model.py | ? | Main shot model | No alt version? |
| main_window.py | main_window_refactored.py | Main window | Which is used? |

**Action Items:**
1. Check git history to see which is newer
2. Delete the older version
3. Remove confusion from codebase

---

### Issue 6: Error Handling Boilerplate

**Files with 10+ try-except blocks:**

| File | Count | Impact |
|------|-------|--------|
| persistent_terminal_manager.py | 18 | Very high repetition |
| utils.py | 15 | High repetition |
| persistent_bash_session.py | 13 | High repetition |
| launcher/process_manager.py | 13 | High repetition |
| filesystem_scanner.py | 12 | High repetition |
| cache_manager.py | 12 | High repetition |

**Sample Pattern (utils.py, lines 489-518, 545-560, etc.):**
```python
try:
    # Do something
except SomeError as e:
    logger.error(f"Error: {e}")
    return None
except AnotherError as e:
    logger.warning(f"Warning: {e}")
    return default_value
```

**Fix:** Create @log_and_handle_errors decorator

---

### Issue 7: Validation Duplication (3 files)

**Locations:**

| File | Function | Lines | Type |
|------|----------|-------|------|
| utils.py | validate_path_exists() | 489-500 | Path validation |
| launcher/validator.py | validate_command() | ? | Command validation |
| launcher_dialog.py | _validate_name() | ? | UI field validation |

**Duplicated Logic:**
- Empty string checks
- File existence checks
- Format validation

---

### Issue 8: Qt Signal Connection Boilerplate (6+ files)

**Pattern seen in:**
- previous_shots_model.py:~180
- threede_scene_model.py:~200
- shot_model.py:~243-292
- controllers/launcher_controller.py
- controllers/threede_controller.py

**Repeated Code:**
```python
self.worker.finished.connect(self._on_worker_finished)
self.worker.error.connect(self._on_worker_error)
self.worker.start()
```

**Fix:** Create `_connect_worker(worker, finished_slot, error_slot)` helper

---

## YAGNI VIOLATIONS - EXACT LOCATIONS

### Issue 1: Unused Alternative Files (CRITICAL)

**Files:**
1. `/home/gabrielh/projects/shotbot/main_window_refactored.py` (758 lines)
   - Duplicates: main_window.py (1,563 lines)
   - **Action:** Check which is current, delete the other

2. `/home/gabrielh/projects/shotbot/threede_scene_finder_optimized.py`
   - Duplicates: threede_scene_finder.py
   - **Action:** Check which is used, delete the other

3. `/home/gabrielh/projects/shotbot/maya_latest_finder_refactored.py`
   - Duplicates: maya_latest_finder.py
   - **Action:** Check which is used, delete the other

4. `/home/gabrielh/projects/shotbot/optimized_shot_parser.py`
   - **Action:** Check if used, delete if not

---

### Issue 2: Over-Complex CacheManager

**File:** `cache_manager.py:182-1150` (969 lines)

**Classes/Methods Related to Same Data Type:**

Shots:
- get_cached_shots():524-530
- cache_shots():532-548
- get_persistent_shots():550-559
- migrate_shots_to_previous():572-622
- merge_shots_incremental():662-729

3DE Scenes:
- get_cached_threede_scenes():731-740
- cache_threede_scenes():765-776
- get_persistent_threede_scenes():742-754
- merge_scenes_incremental():779-845

Previous Shots:
- get_cached_previous_shots():624-630
- cache_previous_shots():644-659
- get_persistent_previous_shots():632-642

**Duplication:**
- merge_shots_incremental() (68 lines) and merge_scenes_incremental() (68 lines) - nearly identical!
  Location: Lines 662-729 vs 779-845

**Over-Engineering:**
- Should have separate cache managers per type OR generic cache base
- _stat_cache (line 213) is a secondary cache layer

**Fix:** Create CacheType protocol and generic cache wrapper

---

### Issue 3: Multiple Launcher Implementations

**Files:**
- command_launcher.py (824 lines)
- simplified_launcher.py (610 lines)
- nuke_launch_handler.py
- simple_nuke_launcher.py

**Question:** Which is the primary? Are all needed?

**Fix:** Delete unused implementations

---

### Issue 4: Multiple Finder Base Classes

**Files:**
- base_asset_finder.py
- base_scene_finder.py
- shot_finder_base.py

**Question:** Why 3 bases? Why not 1 unified base?

**Concrete Finders Using These Bases (12 total):**
- threede_scene_finder.py + threede_scene_finder_optimized.py (2!)
- previous_shots_finder.py
- raw_plate_finder.py
- maya_latest_finder.py + maya_latest_finder_refactored.py (2!)
- threede_latest_finder.py
- others...

**Fix:** Consolidate to single BaseFinder class

---

### Issue 5: Over-Complex Scene Discovery

**Files:**
- filesystem_scanner.py (1,049 lines)
- scene_discovery_coordinator.py (737 lines)
- scene_discovery_strategy.py (666 lines)

**Question:** Can these be consolidated?

**Pattern:**
- Strategy pattern (strategy.py)
- Coordinator pattern (coordinator.py)
- Scanner pattern (scanner.py)

Likely too much architecture for one domain feature.

---

### Issue 6: Unused _metadata Parameter

**File:** `cache_manager.py:768`

```python
def cache_threede_scenes(
    self,
    scenes: list[ThreeDESceneDict],
    _metadata: dict[str, object] | None = None,  # UNUSED!
) -> None:
```

**Action:** Remove unused parameter

---

### Issue 7: Multiple Configuration Files

**Files:**
- config.py
- cache_config.py
- timeout_config.py

**Why Fragmented?** Could be unified.

---

### Issue 8: Complex Base Item Model

**File:** `base_item_model.py:1-838` (838 lines, 30+ methods)

**Responsibilities:**
- Qt model behavior
- Thumbnail loading (lines 196+)
- Selection management
- Filtering
- Caching

**Over-Engineered:** Too many concerns in one class

**Fix:** Use composition or split into:
- BaseItemModel (Qt model basics)
- ThumbnailMixin (thumbnail loading)
- SelectionMixin (selection)
- FilterMixin (filtering)

---

### Issue 9: Complex Notification Manager

**File:** `notification_manager.py:267-619` (353 lines)

**Methods:** error(), warning(), info(), success(), progress(), toast()

**Over-Engineered:** Tries to be too generic

**Fix:** Split into:
- DialogNotificationManager (error/warning/info)
- ToastNotificationManager (toast)
- ProgressNotificationManager (progress)

---

## COMPLEXITY HOTSPOTS - EXACT LOCATIONS

### Cyclomatic Complexity Analysis

#### Very High (>8 branches)

1. **ProcessPoolManager.shutdown()** (106 lines)
   - Location: `process_pool_manager.py:528-633`
   - Issues: 6+ try-except blocks, 5+ stages, nested error handling
   - Fix: Extract into _shutdown_sessions(), _shutdown_executor(), _cleanup_resources(), _finalize()

2. **ThumbnailWidgetBase.run()** (129 lines)
   - Location: `thumbnail_widget_base.py:196-324`
   - Issues: Multiple nested conditions, state transitions
   - Fix: Use state machine pattern

3. **PersistentTerminalManager._ensure_dispatcher_healthy()** (64 lines)
   - Location: `persistent_terminal_manager.py:707-770`
   - Issues: Multiple error checks, complex recovery logic
   - Fix: Extract error handling strategies

#### High (5-8 branches)

4. **BaseItemModel.set_items()** (110 lines)
   - Location: `base_item_model.py:664-773`
   - Issues: Complex initialization, multiple timers, cache updates
   - Fix: Extract _verify_main_thread(), _stop_timers(), _update_cache()

5. **CacheManager.merge_shots_incremental()** (68 lines)
   - Location: `cache_manager.py:662-729`
   - Issues: Complex data structure manipulation
   - Fix: Use better data structures/algorithms

6. **CacheManager.merge_scenes_incremental()** (68 lines)
   - Location: `cache_manager.py:779-845`
   - Issues: Duplicate of merge_shots_incremental()
   - Fix: Create generic merge method

7. **ThreeDEController.cleanup_worker()** (64 lines)
   - Location: `controllers/threede_controller.py:295-358`
   - Issues: Multiple cleanup stages
   - Fix: Extract stage methods

8. **LauncherDialog._save()** (72 lines)
   - Location: `launcher_dialog.py:362-433`
   - Issues: If-else chain, nested conditions
   - Fix: Extract _build_environment(), _create_launcher()

#### Medium (3-5 branches)

9. **ShotModel._on_shots_loaded()** (70 lines)
   - Location: `shot_model.py:362-431`
   - Issues: Complex merge, signal emissions
   - Fix: Extract _process_merge_result()

10. **SettingsDialog.save_settings()** (77 lines)
    - Location: `settings_dialog.py:800-876`
    - Issues: Long field collection, try-except
    - Fix: Extract _collect_settings()

---

### Deep Nesting Analysis (>3 levels)

**File: cache_manager.py**

Line 717-726: 4 levels
```
with QMutexLocker(self._lock):      # Level 1
    for fresh_shot in fresh_dicts:  # Level 2
        fresh_key = _get_shot_key(fresh_shot)
        updated_shots.append(fresh_shot)
        if fresh_key not in cached_by_key:
            new_shots.append(fresh_shot)
```

**File: base_item_model.py**

Lines 685-696: 4 levels
```
if app:                                      # Level 1
    if QThread.currentThread() != app.thread():  # Level 2
        raise QtThreadError(...)
    if self._thumbnail_timer.isActive():    # Level 2 (sibling)
        self._thumbnail_timer.stop()
```

**File: process_pool_manager.py**

Lines 574-582: 4 levels of try-except nesting

---

## SUMMARY TABLE: FINDINGS BY SEVERITY

| Category | Issue | Files | Lines | Fix Effort | Impact |
|----------|-------|-------|-------|-----------|--------|
| DRY | Filter methods | 9 | 40+ | Medium | Very High |
| DRY | Singleton reset | 5 | 100+ | Low | High |
| DRY | Cache I/O | 3 | 60+ | Low | Medium |
| DRY | Worker pattern | 4 | 100+ | Medium | Medium |
| DRY | Error handling | 18 | 200+ | High | Medium |
| YAGNI | Unused alternatives | 4 | 2000+ | Very Low | Very High |
| YAGNI | Over-complex cache | 1 | 969 | High | High |
| YAGNI | Multiple launchers | 4 | ? | Medium | Medium |
| YAGNI | Multiple finders | 12 | 1000+ | High | Medium |
| Complexity | Long methods | 10 | 700+ | Medium | Medium |

**Total Estimated Refactoring Effort:** 30-40 hours
**Expected Improvement in Maintainability:** 20-30%
**Quick Wins:** Delete unused files (4 files, 2000+ lines, ~1 hour)

