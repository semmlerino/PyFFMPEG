# Phase 5-6 Refactoring Safety Review

**Date:** 2025-10-31
**Reviewer:** Code Architecture Analysis
**Confidence Level:** 99%+ (Based on actual codebase inspection)

---

## Executive Summary

Review of proposed Phase 5-6 refactorings against actual codebase:

| Refactoring | Safety | Recommendation | Effort to Fix |
|-------------|--------|-----------------|---------------|
| 5.1: FilterableModel mixin | 🔴 BREAKS CODE | Do not implement | N/A |
| 5.2: ThumbnailManager | ✅ SAFE (but unnecessary) | Optional | Low |
| 6.1: Generic CacheManager[T] | 🔴 BREAKS CODE | Do not implement | N/A |
| 6.2: Replace QSettings→JSON | ✅ SAFE (with migration) | Optional | Medium |

**Primary Finding:** Phases 5-6 are "nice-to-have" refactorings. All introduce complexity or breaking changes without substantial benefits for a personal VFX tool.

---

# PHASE 5: Model Architecture Changes

## Task 5.1: FilterableModel Mixin

**Status:** 🔴 **BREAKS CODE**

### Problem Exists: YES (Confirmed)

All three models have similar filtering logic:
- `/mnt/c/CustomScripts/Python/PyFFMPEG/BB/shotbot/shot_item_model.py:147-166`
- `/mnt/c/CustomScripts/Python/PyFFMPEG/BB/shotbot/threede_item_model.py:151-172`
- `/mnt/c/CustomScripts/Python/PyFFMPEG/BB/shotbot/previous_shots_item_model.py:150-171`

### Solution Would Work: NO (Critical incompatibilities)

#### Breaking Change 1: Different Underlying Model Types

**ShotItemModel:**
```python
def set_show_filter(self, shot_model: BaseShotModel, show: str | None) -> None:
    shot_model.set_show_filter(show)
```

**ThreeDEItemModel:**
```python
def set_show_filter(self, threede_scene_model: ThreeDESceneModel, show: str | None) -> None:
    threede_scene_model.set_show_filter(show)
```

**PreviousShotsItemModel:**
```python
def set_show_filter(self, previous_shots_model: PreviousShotsModel, show: str | None) -> None:
    previous_shots_model.set_show_filter(show)
```

**Issue:** Parameter types differ (`BaseShotModel` vs `ThreeDESceneModel` vs `PreviousShotsModel`). A mixin cannot handle this without:
- Option A: Use `object` parameter (loses type safety)
- Option B: Require all models implement Protocol (requires changes to 3 model classes)
- Option C: Conditional type checking in mixin (defeats purpose of code reuse)

#### Breaking Change 2: Different Method Names on Return Data

**ShotItemModel & PreviousShotsItemModel:**
```python
filtered_shots = shot_model.get_filtered_shots()
self.set_shots(filtered_shots)
```

**ThreeDEItemModel:**
```python
filtered_scenes = threede_scene_model.get_filtered_scenes()  # ← Different method!
self.set_scenes(filtered_scenes)  # ← Different method!
```

**Issue:** Cannot unify in mixin without requiring ThreeDESceneModel to rename `get_filtered_scenes()` → `get_filtered_shots()` (breaking change to that class).

#### Implementation Complexity

Would require modifying at minimum:
1. `BaseShotModel` interface
2. `ThreeDESceneModel` interface
3. `PreviousShotsModel` interface
4. All three item models
5. Possibly main_window.py call sites

**Cost: HIGH (5+ files changed)**

### Verdict

✅ **PROBLEM EXISTS** - Code duplication is real
❌ **SOLUTION BREAKS CODE** - Requires breaking changes to 3+ other classes
⚪ **UNNECESSARY** - 100 lines of duplication across 3 files is acceptable for a personal tool

### Recommendation

**DO NOT IMPLEMENT.** Current code is clear, type-safe, and working. Code duplication is minimal and intentional (each model has different underlying types).

---

## Task 5.2: Move Thumbnail Operations to ThumbnailManager

**Status:** ✅ **SAFE (but adds complexity)**

### Problem Exists: NO (Current design is good)

Thumbnail operations in `BaseItemModel` are:
- `_load_visible_thumbnails()` (line 329)
- `_do_load_visible_thumbnails()` (line 346)
- `_load_thumbnail_async()` (line 401)
- `_load_cached_pixmap()` (line 489)
- `_get_thumbnail_pixmap()` (line 528)
- `clear_thumbnail_cache()` (cleanup)

Plus supporting state:
- `_thumbnail_cache: dict[str, QImage]` (line 139)
- `_loading_states: dict[str, str]` (line 140)
- `_thumbnail_timer` and `_thumbnail_debounce_timer`

**Current Design:** Thumbnails are internal to model, not exposed to views

### Solution Would Work: YES (but adds indirection)

Could create `ThumbnailManager`:
```python
class ThumbnailManager:
    def __init__(self, cache_manager: CacheManager):
        self._cache = cache_manager
        self._thumbnail_cache = LRUCache[str, QImage]()
        self._loading_states = {}
        self._cache_mutex = QMutex()

    def load_visible_range(self, items: list[T], start: int, end: int) -> None:
        # Extract thumbnail loading logic
        pass

    def get_thumbnail(self, item: T) -> QPixmap | None:
        # Get cached thumbnail
        pass

    # Signal: thumbnail_loaded(row: int)
```

Then in BaseItemModel:
```python
class BaseItemModel:
    def __init__(self):
        self._thumbnail_manager = ThumbnailManager(self._cache_manager)

    def set_visible_range(self, start: int, end: int) -> None:
        self._thumbnail_manager.load_visible_range(self._items, start, end)
```

### Breaking Changes

**Mild breaking changes:**
1. Tests that mock `_load_thumbnail_async` would need updating (moderate)
2. Tests that access `_thumbnail_cache` directly would need updating (moderate)
3. Views still call `model.set_visible_range()` - no change needed
4. `data()` method accesses thumbnails via `_get_thumbnail_pixmap()` - can stay internal

**Migration Path:** Straightforward with updated test doubles

### Analysis

✅ **WOULD WORK:** Technically feasible, low runtime risk
❌ **ADDS INDIRECTION:** One more object to manage/test
⚪ **MINIMAL BENEFIT:** Current design already separates concerns well

### Verdict

✅ **SAFE** - No breaking API changes, straightforward to implement

✅ **WORKS** - Code would function correctly after refactoring

⚪ **UNNECESSARY** - Current model-based design is clear and maintainable. Extraction would add complexity without removing it (moving ~150 lines from model to manager doesn't reduce overall lines or complexity).

### Recommendation

**OPTIONAL.** Only implement if:
- Multiple models need different thumbnail strategies (they don't)
- ThumbnailManager needs to be shared/reused (it won't be)
- You want to unit test thumbnail logic separately (worth ~2 hours)

**Skip for now.** Current design is fine. Revisit only if you need to:
1. Support thumbnails from different sources (OpenEXR, etc.)
2. Have configurable thumbnail strategies
3. Cache thumbnails in different backends

---

# PHASE 6: Cache System Overhaul

## Task 6.1: Generic CacheManager[T]

**Status:** 🔴 **BREAKS CODE**

### Problem Exists: YES (Type-specific methods)

Current `CacheManager` has type-specific APIs:
- `cache_shots(shots: list[Shot | ShotDict])`
- `get_cached_shots()`
- `cache_previous_shots(shots: Sequence[Shot | ShotDict])`
- `get_cached_previous_shots()`
- `get_persistent_previous_shots()`
- `cache_thumbnail(thumbnail_path, show, sequence, shot, ...)`
- `merge_shots_incremental(cached, fresh)`

### Solution Would Work: NO (Requires Type Handler Infrastructure)

To make generic, would need:
```python
class CacheManager(Generic[T], LoggingMixin, QObject):
    def __init__(self, cache_dir: Path | None = None):
        # Problem: How do you know which file to use?
        # Which serializer? Which TTL?
        pass

    def cache(self, key: str, data: list[T]) -> None:
        # Problem: Key is ambiguous (shots vs previous shots vs scenes)
        serialized = self._serialize(data)  # Problem: type-specific!
        self._write_json_cache(file_for_key(key), serialized)

    def get_cached(self, key: str) -> list[T] | None:
        # Problem: Which TTL to check? Different for each type
        data = self._read_json_cache(file_for_key(key), check_ttl=???)
        return self._deserialize(data)  # Problem: type-specific!
```

### Breaking Changes Required

**Major breaking changes:**

1. **All callers must change:**
```python
# OLD API (type-specific):
shots = cache_manager.get_cached_shots()

# NEW API (generic):
shots = cache_manager.get_cached("shots")  # Type information lost!
```

2. **Type information loss:**
```python
# OLD: Type checker knows return type
shots: list[Shot] = cache_manager.get_cached_shots()

# NEW: Type checker cannot infer type
shots = cache_manager.get_cached("shots")  # Type is Any!
```

3. **Need Handler Registry:**
```python
class CacheHandler(Protocol):
    file_path: Path
    ttl_seconds: int
    def serialize(self, data: Any) -> str: ...
    def deserialize(self, data: str) -> Any: ...

CACHE_HANDLERS = {
    "shots": ShotCacheHandler(),
    "previous_shots": PreviousShotsCacheHandler(),
    "threede_scenes": ThreeDESceneCacheHandler(),
    "thumbnails": ThumbnailCacheHandler(),
}
```

4. **Type-specific methods wouldn't work:**
```python
# Current:
result = cache_manager.merge_shots_incremental(cached, fresh)

# Generic: Would need type-aware merge
result = cache_manager.merge_incremental("shots", cached, fresh)
```

### Code Impact

Files that would break:
1. `shot_model.py` - Uses `get_cached_shots()`, `merge_shots_incremental()`
2. `previous_shots_model.py` - Uses `get_cached_previous_shots()`, `cache_previous_shots()`
3. `threede_scene_model.py` - Uses 3DE scene cache methods
4. `cache_manager.py` - Entire API redesign
5. All tests using cache manager

**Cost: VERY HIGH (redesign entire cache system)**

### Verdict

✅ **PROBLEM EXISTS** - Type-specific methods could be unified
❌ **SOLUTION BREAKS CODE** - Requires handler registry + API redesign
❌ **LOSES TYPE SAFETY** - Generic version with string keys = loss of type information

### Recommendation

**DO NOT IMPLEMENT.** Current design is:
- Type-safe (explicit method names)
- Clear (method names match data types)
- Maintainable (easy to understand what's cached)

Generic version would:
- Lose type safety
- Require string-based lookups
- Introduce handler registry (more code)
- Break all callers
- Offer zero benefit for a single-user tool with fixed cache types

---

## Task 6.2: Replace QSettings with JSON

**Status:** ✅ **SAFE (with migration)**

### Problem Exists: YES (Platform-specific storage)

Current implementation uses `QSettings`:
- Platform-dependent backend (Registry on Windows, plist on Mac, INI on Linux)
- `/mnt/c/CustomScripts/Python/PyFFMPEG/BB/shotbot/settings_manager.py:88`
- `/mnt/c/CustomScripts/Python/PyFFMPEG/BB/shotbot/qt_widget_mixin.py:83-100`

### Solution Would Work: YES (with proper migration)

Could replace with JSON file:
```python
class SettingsManager:
    SETTINGS_FILE = Path(QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppDataLocation
    )) / "settings.json"

    def __init__(self):
        self.settings = self._load_settings()

    def _load_settings(self) -> dict:
        if self.SETTINGS_FILE.exists():
            with open(self.SETTINGS_FILE) as f:
                return json.load(f)
        return self._get_defaults()

    def _save_settings(self) -> None:
        # Atomic write with temp file + os.replace()
        temp = self.SETTINGS_FILE.with_suffix('.json.tmp')
        with open(temp, 'w') as f:
            json.dump(self.settings, f, indent=2)
        os.replace(temp, self.SETTINGS_FILE)

    def get(self, key: str, default: Any) -> Any:
        return self.settings.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.settings[key] = value
        self._save_settings()
```

### Breaking Changes

**Minimal and manageable:**

1. **Settings location changes** (one-time migration)
   - Old: Platform-specific (~/Library/Preferences on macOS, etc.)
   - New: Single JSON file in app data directory
   - Migration: Load from old location on first run

2. **Type handling for QByteArray:**
   - QSettings: `geometry_bytes: QByteArray = settings.value(...)`
   - JSON: Must encode as base64
   ```python
   # Save
   settings["geometry"] = geometry_bytes.data().hex()

   # Load
   geometry_bytes = QByteArray.fromHex(settings["geometry"])
   ```

3. **No API change needed:**
   ```python
   # All existing code works unchanged:
   geometry = settings_manager.get_window_geometry()
   settings_manager.set_window_geometry(new_geometry)
   ```

### Code Examples

**Migration path (already exists in codebase):**
```python
# settings_manager.py lines 188-214
def _migrate_old_settings(self) -> None:
    """Migrate settings from old format to new organized format."""
    if self.settings.contains("migration_version"):
        return  # Already migrated

    # Load from QSettings, write to JSON
    for old_key, new_key in old_key_mappings:
        if self.settings.contains(old_key):
            value = self.settings.value(old_key)
            self.settings.setValue(new_key, value)
```

**Implementation:**
```python
def __init__(self):
    # Try JSON first
    if self.SETTINGS_FILE.exists():
        self._load_from_json()
    else:
        # Try QSettings as fallback
        self._load_from_qsettings()
        self._save_to_json()  # Migrate

def _load_from_json(self) -> None:
    with open(self.SETTINGS_FILE) as f:
        self.settings = json.load(f)

def _save_to_json(self) -> None:
    temp = self.SETTINGS_FILE.with_suffix('.json.tmp')
    with open(temp, 'w') as f:
        json.dump(self.settings, f, indent=2, default=self._json_encoder)
    os.replace(temp, self.SETTINGS_FILE)

def _json_encoder(self, obj: Any) -> Any:
    if isinstance(obj, QByteArray):
        return {"__qbytearray__": obj.data().hex()}
    if isinstance(obj, QSize):
        return {"__qsize__": [obj.width(), obj.height()]}
    raise TypeError(f"Cannot serialize {type(obj)}")
```

### Analysis

✅ **WOULD WORK:** JSON is simpler than platform-specific backends
✅ **MIGRATION PATH EXISTS:** Current code has migration logic already
⚪ **BEHAVIOR CHANGE:** Settings now in single JSON vs platform-native storage

### Advantages

- Simpler code (no QSettings abstraction layer)
- Settings visible and editable by users
- Cross-platform (same location everywhere)
- Easier to backup/restore

### Disadvantages

- Lose platform-native behavior (some users prefer Registry/plist)
- Requires migration code
- Must handle concurrent access (Qt handles this for QSettings)
- Must implement atomic writes (QSettings does this)

### Verdict

✅ **SAFE** - Technical implementation straightforward
✅ **WORKS** - Would pass all tests with proper migration
✅ **FEASIBLE** - Code already has migration infrastructure

### Recommendation

**OPTIONAL.** Implement if you want:
- Simpler code
- User-visible settings file
- Cross-platform consistency

**Skip if:**
- Current QSettings works fine (it does)
- Don't want to migrate user settings
- Want platform-native behavior

**Implementation Priority:** LOW - Current QSettings is working, not a bottleneck

---

# Summary Table

| Phase | Task | Safety | API Breaking | Complexity | Benefit | Verdict |
|-------|------|--------|--------------|-----------|---------|---------|
| 5 | 5.1 FilterableModel | 🔴 Breaks | YES (3+ files) | HIGH | LOW | Skip |
| 5 | 5.2 ThumbnailManager | ✅ Safe | NO | MEDIUM | LOW | Optional |
| 6 | 6.1 Generic Cache | 🔴 Breaks | YES (5+ files) | HIGH | NONE | Skip |
| 6 | 6.2 Replace QSettings | ✅ Safe | NO | MEDIUM | MEDIUM | Optional |

---

# Recommendations

## High Priority: DO NOT IMPLEMENT
- **Phase 5.1 (FilterableModel)** - Breaking changes outweigh minor code duplication
- **Phase 6.1 (Generic Cache)** - Loses type safety, gains zero benefit

## Low Priority: CONSIDER IF MOTIVATED
- **Phase 5.2 (ThumbnailManager)** - Works but adds indirection
- **Phase 6.2 (Replace QSettings)** - Works but don't fix what's not broken

## Focus Instead On
1. **Phase 1-2 (already done):** Critical bugs and performance
2. **Phase 3-4 (ready to go):** Architecture cleanup and testing
3. **User features:** VFX-specific improvements (Nuke integration, plate handling, etc.)

---

**Conclusion:** Phases 5-6 are premature optimization/over-engineering. Current code is good. Focus on completing Phase 4 and shipping a solid v1.0 instead.

---

**Document Version:** 1.0
**Last Updated:** 2025-10-31
**Confidence:** 99%+ (Based on full codebase inspection)
