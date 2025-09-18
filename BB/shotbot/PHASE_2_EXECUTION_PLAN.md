# PHASE 2: ELIMINATE CODE DUPLICATION - EXECUTION PLAN

## Objective
Eliminate 2,500+ lines of duplicate code by extracting common patterns into reusable components.

## Current Status
- **Phase 1 Complete**: 5,537 lines of dead code removed
- **Phase 2 Starting**: Focus on consolidating duplicate patterns
- **Partially Implemented**: LoggingMixin (used in 6 modules), ThreadSafeWorker (used in 3 workers)

## Detailed Duplication Analysis

### 1. Logging Pattern Duplication (72 files, ~500 lines)
- **Current**: 72 files still use `logger = logging.getLogger(__name__)`
- **Solution**: Apply existing LoggingMixin to all applicable classes
- **Files Affected**: 72 Python modules
- **Reduction**: ~500 lines (7 lines per file average)

### 2. Exception Handling Patterns (210 occurrences, ~1,000 lines)
- **Current**: Repetitive try/except blocks with similar logging
- **Solution**: Create ErrorHandlingMixin with common patterns
- **Patterns to Extract**:
  ```python
  # Common pattern repeated everywhere:
  try:
      # operation
  except Exception as e:
      logger.error(f"Operation failed: {e}")
      return False, False  # or None, or raise
  ```
- **Reduction**: ~1,000 lines

### 3. Qt Signal-Slot Setup (233 occurrences, ~700 lines)
- **Current**: Repetitive signal connection patterns
- **Solution**: Create SignalManager utility class
- **Common Patterns**:
  - Worker signal connections
  - Progress signal chains
  - Cleanup on destruction
- **Reduction**: ~700 lines

### 4. Process Execution (65 occurrences, ~400 lines)
- **Current**: Duplicate subprocess/QProcess handling
- **Solution**: Enhance ProcessPoolManager usage
- **Pattern**: Error handling, timeout, logging all duplicated
- **Reduction**: ~400 lines

### 5. Scene Finder Duplication (2,000+ lines)
- **Files**:
  - threede_scene_finder.py (56 lines - facade)
  - threede_scene_finder_optimized.py (319 lines)
  - threede_scene_finder_optimized_monolithic_backup.py (1,697 lines)
- **Issue**: Massive duplication in monolithic backup
- **Solution**: Consolidate into single optimized implementation
- **Reduction**: ~1,600 lines

### 6. Worker Thread Patterns (~300 lines)
- **Current**: Only 3 workers use ThreadSafeWorker
- **Unconverted Workers**:
  - SessionWarmer (main_window.py)
  - AsyncShotLoader (shot_model_optimized.py)
  - FolderOpenerThread (in patch file)
  - TestThread (test files)
- **Solution**: Convert all to ThreadSafeWorker
- **Reduction**: ~300 lines

## Execution Steps

### Step 1: Apply LoggingMixin Broadly (2 hours)
```bash
# Files to modify (72 total)
- base_shot_model.py
- base_thumbnail_delegate.py
- cache_manager.py
- app_launcher_manager.py
- command_launcher.py
- main_window.py
- shot_model.py
- threede_scene_model.py
# ... and 64 more
```

**Implementation**:
1. Replace `logger = logging.getLogger(__name__)` with inheritance from LoggingMixin
2. Update logger references from module-level to `self.logger`
3. For module-level functions, use `get_module_logger(__name__)`

### Step 2: Create ErrorHandlingMixin (1 hour)
```python
# error_handling_mixin.py
class ErrorHandlingMixin:
    def safe_execute(self, operation, default=None, log_error=True):
        """Execute operation with standard error handling."""

    def safe_file_operation(self, path_operation, path, default=None):
        """Execute file operation with path validation and error handling."""

    @contextmanager
    def error_context(self, operation_name, reraise=False):
        """Context manager for error handling blocks."""
```

### Step 3: Create SignalManager Utility (1 hour)
```python
# signal_manager.py
class SignalManager:
    def __init__(self, owner):
        self.owner = owner
        self._connections = []

    def connect_safely(self, signal, slot, connection_type=None):
        """Connect with tracking for cleanup."""

    def disconnect_all(self):
        """Disconnect all tracked connections."""

    def chain_signals(self, source_signal, target_signal):
        """Chain one signal to another with tracking."""
```

### Step 4: Consolidate Scene Finders (2 hours)
1. Verify threede_scene_finder_optimized_monolithic_backup.py functionality
2. Extract unique features not in optimized version
3. Merge into threede_scene_finder_optimized.py
4. Update imports in scene_discovery_coordinator.py
5. Delete monolithic backup file

### Step 5: Convert Remaining Workers (1 hour)
1. Convert SessionWarmer to use ThreadSafeWorker
2. Convert AsyncShotLoader to use ThreadSafeWorker
3. Update any test workers
4. Remove duplicate worker lifecycle code

### Step 6: Extract Common Qt Widget Patterns (1 hour)
```python
# qt_widget_mixins.py
class QtWidgetMixin:
    """Common Qt widget setup patterns."""

    def setup_standard_layout(self, layout_type="vertical"):
        """Setup standard layout with margins."""

    def add_standard_buttons(self, buttons=None):
        """Add OK/Cancel or custom buttons."""

    def connect_standard_shortcuts(self):
        """Setup common keyboard shortcuts."""
```

### Step 7: Testing and Verification (1 hour)
1. Run full test suite after each major change
2. Verify mock environment still works
3. Check for any regression in functionality
4. Performance testing for consolidated components

## Order of Execution

1. **Batch 1 - Low Risk** (Steps 1, 2, 3)
   - Apply LoggingMixin
   - Create ErrorHandlingMixin
   - Create SignalManager
   - Test & Commit

2. **Batch 2 - Medium Risk** (Steps 5, 6)
   - Convert workers to ThreadSafeWorker
   - Extract Qt widget patterns
   - Test & Commit

3. **Batch 3 - High Risk** (Step 4)
   - Consolidate scene finders
   - Extensive testing required
   - Test & Commit

## Success Metrics

- **Line Reduction**: Target 2,500+ lines removed
- **File Count**: Reduce by ~10-15 files
- **Test Coverage**: Maintain or improve current coverage
- **Performance**: No regression in startup or operation speed
- **Code Quality**: All tests pass, type checking clean

## Risk Mitigation

1. **Incremental Changes**: Apply one pattern at a time
2. **Test After Each Step**: Run quick tests frequently
3. **Git Commits**: Commit after each successful pattern application
4. **Rollback Plan**: Each step can be reverted independently
5. **Performance Monitoring**: Check startup time doesn't increase

## Estimated Timeline

- **Total Time**: 9-10 hours
- **Approach**: Incremental, with testing between batches
- **Commits**: 3-4 major commits (one per batch)

## Post-Phase 2 Status

After Phase 2 completion:
- **Codebase**: ~2,500 fewer lines
- **Maintenance**: Significantly easier with centralized patterns
- **Next Phase**: Ready for Phase 3 (Architecture improvements)
- **Code Quality**: Improved consistency across all modules

## Command Reference

```bash
# Run tests after each change
python3 tests/utilities/quick_test.py

# Check specific pattern usage
grep -r "logger = logging.getLogger" --include="*.py" | wc -l

# Verify type checking
basedpyright

# Test mock environment
python shotbot.py --mock
```

## Notes

- LoggingMixin and ThreadSafeWorker already exist and are tested
- Focus on applying existing patterns before creating new ones
- Prioritize high-frequency duplication patterns
- Keep backward compatibility for all public APIs