# ShotBot Refactoring Plan Alpha - DO NOT DELETE
*Generated: 2025-01-18*

## 🔍 Comprehensive Analysis Results

### Code Duplication Analysis (~2,500 lines of duplicate code)

#### 1. Duplicate Delegate Painting Logic
- **Files**: `shot_grid_delegate.py` and `threede_grid_delegate.py`
- **Duplication**: 80-90% identical code (~500 lines)
- **Duplicated Methods**:
  - `paint()` method structure (lines 106-172 in both files)
  - `_paint_background()` (lines 173-203 similar)
  - `_paint_thumbnail()`, `_paint_loading_indicator()`, `_paint_placeholder()`
  - `_paint_focus_indicator()`, `sizeHint()` implementation

#### 2. Repeated Model Initialization Patterns
- **Files**: `shot_model.py`, `base_shot_model.py`, `previous_shots_model.py`, `threede_scene_model.py`
- **Common Pattern**:
  ```python
  def __init__(self, cache_manager: CacheManager | None = None, ...):
      super().__init__()
      self._cache_manager = cache_manager or CacheManager()
      self._shots: list[Shot] = []
      self._lock = QMutex()
      if load_cache:
          self._load_from_cache()
  ```

#### 3. Duplicate Cache Operations
- Methods `_load_from_cache()` and `_save_to_cache()` repeated in 4+ model files
- Identical error handling patterns
- Cache key generation logic duplicated

#### 4. Worker Thread Cleanup Pattern
- Duplicated in: `previous_shots_model.py`, `main_window.py`, `threede_scene_finder.py`
- ~40 lines of identical cleanup code per instance

#### 5. Repeated Error Handling (50+ instances)
```python
except Exception as e:
    logger.error(f"Failed to [action]: {e}")
    self._emit_error(f"Failed to [action]: {str(e)}")
```

#### 6. Duplicate UI Setup Methods
- Files: `launcher_panel.py`, `launcher_dialog.py`, `main_window.py`, `shot_info_panel.py`
- Similar `_setup_ui()` patterns

### Dead Code Analysis (~5,000 lines)

#### Obsolete Files Not Referenced
- `config_refactored.py` - Unused refactored config
- `accessibility_manager_complete.py` - Duplicate version not imported
- `process_pool_factory_refactored.py` - Unused refactored factory
- `cache_config_unified.py` - Alternative cache config not used

#### Backup Files (8 files)
- `accessibility_manager.py.backup`
- `accessibility_manager_complete.py.backup`
- `config.py.backup`
- `main_window.py.backup`
- `pyrightconfig.json.backup`
- `shot_item_model.py.backup`
- `shot_model_optimized.py.backup`
- `threede_scene_finder_optimized_monolithic_backup.py`

#### Test Files in Root Directory (26 files)
- `test_actual_parsing.py`
- `test_cache_separation.py`
- `test_critical_fixes_complete.py`
- `test_critical_fixes_simple.py`
- `test_dependency_injection.py`
- `test_headless.py`
- `test_json_error_handling.py`
- `test_logging_mixin.py`
- `test_mock_injection.py`
- `test_mock_mode.py`
- `test_parser_optimization.py`
- `test_persistent_terminal.py`
- `test_python311_real_compat.py`
- `test_python311_syntax.py`
- `test_qthread_cleanup.py`
- `test_refactoring.py`
- `test_run_linters.py`
- `test_runner.py`
- `test_shot_fetcher.py`
- `test_shot_model.py`
- `test_shot_parser_edge_cases.py`
- `test_threede_latest_scene_finder.py`
- `test_threede_scene_finder_edge_cases.py`
- `test_threede_scene_validation.py`
- `test_workspace_parser.py`
- `test_workspace_parser_comprehensive.py`

#### Deprecated Code
- `process_pool_manager.py`:
  - Method `_get_bash_session_deprecated()` - Not called anywhere
  - Dictionary `self._sessions` - Marked deprecated but kept

#### Unused Exception Classes
- From `exceptions.py`:
  - `NetworkError` - No usage found
  - `ValidationError` - No usage found
  - `ConfigurationError` - No usage found
  - Helper functions: `raise_if_invalid_path()`, `raise_if_command_not_allowed()`

### Architectural Issues

#### 1. Mixed Responsibilities
- **ProcessPoolManager**: Service inherits from QObject, uses Qt signals (business logic mixed with presentation)
- **CacheManager**: Business logic coupled to Qt framework (QThreadPool, signals)
- **Shot Model**: Contains file system operations mixed with data representation

#### 2. Layer Violations
- **LauncherManager**: Business logic emitting Qt signals directly
- **NotificationManager**: Service layer importing Qt widgets
- **CommandLauncher**: Business logic inheriting from QObject
- **SettingsController**: Direct UI manipulation from controller

#### 3. God Objects
- **MainWindow**: Orchestrates everything - cache, launchers, processes, settings, UI
- **CacheManager**: Manages thumbnails, shots, 3DE scenes, memory, validation, async loading (470+ lines)

#### 4. Tight Coupling
- Worker classes directly creating Qt objects
- Views importing concrete model classes instead of interfaces
- No dependency inversion - concrete dependencies everywhere

## 📋 Complete Refactoring Plan

### Phase 1: Quick Wins - Remove Dead Code (1-2 hours)
**Goal**: Clean up obvious dead code with zero functional risk

1. Delete all backup files (8 files)
2. Move test files from root to tests/ directory (26 files)
3. Remove obsolete alternative implementations (4 files)
4. Remove deprecated methods and unused code
5. Run full test suite to verify no breakage

**Impact**: ~5,000 lines removed, cleaner repository

### Phase 2: Eliminate Duplication (4-6 hours)
**Goal**: Consolidate duplicate patterns without changing architecture

1. **Consolidate Delegate Classes**
   - Refactor to use BaseThumbnailDelegate properly
   - Extract common painting logic
   - Save ~500 lines

2. **Extract Common Patterns**
   - Create `common/error_handling.py` with decorators
   - Create `common/worker_utils.py` for thread management
   - Create `common/cache_operations.py` for cache patterns

3. **Implement Mixins**
   - Apply existing LoggingMixin broadly
   - Create CacheMixin for models
   - Create ThreadSafeMixin for locking

4. **Create Base Classes**
   - BaseModelWithCache for model initialization
   - BaseWorkerThread for worker lifecycle

**Impact**: ~2,500 lines removed, single source of truth

### Phase 3: Fix Architecture (2-3 days)
**Goal**: Decouple business logic from Qt framework

1. **Extract Pure Python Services**
   ```python
   # Before (coupled to Qt)
   class ProcessPoolManager(QObject):
       def execute(self):
           self.signal.emit()

   # After (decoupled)
   class ProcessPoolService:
       def execute(self, callback):
           callback(result)

   class QtProcessPoolAdapter(QObject):
       def __init__(self, service):
           self.service = service
       def execute(self):
           self.service.execute(lambda r: self.signal.emit(r))
   ```

2. **Implement Proper Layering**
   ```
   presentation/
   ├── views/          # Qt widgets only
   ├── view_models/    # Qt models only
   └── qt_adapters/    # Qt signal adapters

   application/
   ├── controllers/    # Orchestration logic
   └── use_cases/      # Business operations

   domain/
   ├── models/         # Pure data structures
   ├── services/       # Business logic
   └── interfaces/     # Abstract protocols

   infrastructure/
   ├── cache/          # Storage implementation
   ├── process/        # Process management
   └── filesystem/     # File operations
   ```

3. **Break Up God Objects**
   - Split MainWindow into ApplicationCoordinator + UI components
   - Split CacheManager into specialized caches
   - Each class gets single responsibility

**Impact**: Testable without Qt, clear boundaries, maintainable

## 🎯 Success Metrics

1. **Phase 1 Success**:
   - All tests pass
   - Repository cleaner
   - No functional changes

2. **Phase 2 Success**:
   - Code reduction of 2,000+ lines
   - All tests pass
   - Easier to understand patterns

3. **Phase 3 Success**:
   - Business logic testable without Qt
   - Clear architectural boundaries
   - Reduced coupling metrics

## ⚠️ Risk Assessment

### Phase 1 Risks
- **Risk Level**: LOW
- **Potential Issues**: Some "dead" code might be referenced indirectly
- **Mitigation**: Run comprehensive tests after each deletion

### Phase 2 Risks
- **Risk Level**: MEDIUM
- **Potential Issues**: Subtle behavior differences in consolidated code
- **Mitigation**: Careful testing, preserve exact behavior

### Phase 3 Risks
- **Risk Level**: HIGH
- **Potential Issues**: Breaking architectural changes
- **Mitigation**: Incremental refactoring, adapter pattern for compatibility

## 📅 Recommended Timeline

- **Week 1**: Phase 1 (immediate)
- **Week 1-2**: Phase 2 (after Phase 1 verification)
- **Week 3-4**: Phase 3 planning and gradual implementation
- **Ongoing**: Incremental improvements as features are added

## 🔄 Alternative Approach

If Phase 3 is too risky, consider:
1. Keep Qt coupling but improve organization
2. Use interfaces/protocols within current structure
3. Focus on Phase 1-2 benefits only
4. Document architectural debt for future refactoring

## 📝 Notes

- This plan preserves all functionality
- Each phase is independently valuable
- Can stop after any phase with benefits realized
- Tests are critical - run after every change
- Consider feature freeze during Phase 3

---
*This document should be preserved as reference throughout the refactoring process*