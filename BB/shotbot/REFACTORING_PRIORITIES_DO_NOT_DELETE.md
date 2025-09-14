# ShotBot Refactoring Priorities - DO NOT DELETE

## Top Refactoring Priorities (Analyzed 2025-01-14)

Based on comprehensive analysis of the shotbot codebase, here are the **biggest refactoring priorities** in order of impact:

### 1. **Break Down the MainWindow God Object** (HIGHEST PRIORITY)
- **Problem**: main_window.py has 1,965 lines with 50+ methods handling everything from UI setup to business logic
- **Impact**: Violates Single Responsibility Principle, makes testing difficult, maintenance nightmare
- **Solution**: Extract focused controllers using Mediator pattern
  - Extract **UI Setup Controller** (methods: `_setup_ui`, `_setup_menu`, `_setup_accessibility`)
  - Extract **Shot Management Controller** (methods: `_refresh_shots`, `_on_shots_loaded`, `_on_shot_selected`)
  - Extract **3DE Scene Controller** (8+ methods starting with `_on_threede_`)
  - Extract **Launcher Coordinator** (methods: `_launch_app*`, `_execute_custom_launcher`)
  - Extract **Settings Persistence Handler** (methods: `_load_settings`, `_save_settings`)
  - Apply **Mediator Pattern** to coordinate between extracted components

### 2. **Fix Critical Type Safety Issues**
- **Problem**: 53 errors, 1,286 warnings causing uncertainty in refactoring
- **Impact**: Without proper types, refactoring becomes risky - can't rely on type checker
- **Solution**:
  - Add proper type hints for all return types (especially `list[Shot]`, not just `list`)
  - Replace `Any` with specific types or Union types
  - Fix `typing_extensions.override` imports (Python 3.11 compatibility)
  - Create type aliases for complex types (e.g., `ShotList = list[Shot]`)
  - Add `TypedDict` for configuration dictionaries

### 3. **Refactor Complex Scene Finder Module**
- **Problem**: threede_scene_finder_optimized.py has 1,697 lines doing too much
- **Impact**: Monolithic file handling file system scanning, parsing, caching - error-prone and hard to test
- **Solution**:
  - Extract **FileSystemScanner** class for directory traversal
  - Extract **SceneParser** for 3DE file parsing logic
  - Extract **SceneCache** for caching discovered scenes
  - Create **SceneDiscoveryStrategy** interface with implementations (local, network)
  - Apply **Template Method Pattern** for different scan strategies

### 4. **Reduce Coupling Through Dependency Injection**
- **Problem**: main_window.py directly imports 20+ modules creating tight coupling
- **Impact**: Rigid architecture, hard to test in isolation, changes ripple through system
- **Solution**:
  - Create **ServiceRegistry** for managing dependencies
  - Implement **Factory Pattern** for creating views and models
  - Use **Dependency Injection Container** for wiring components
  - Define clear interfaces (protocols) between layers
  - Move from direct imports to lazy loading where appropriate

### 5. **Consolidate Threading Utilities**
- **Problem**: Multiple threading-related files with overlapping functionality, scattered threading logic
- **Impact**: Potential race conditions, inconsistent patterns, hard to debug concurrent behavior
- **Solution**:
  - Merge threading utilities into single **ThreadingManager** module
  - Create **WorkerPool** abstraction for background tasks
  - Implement **AsyncTaskQueue** with priority support
  - Add **ThreadSafeCache** decorator for automatic locking
  - Standardize signal/slot patterns for cross-thread communication

### 6. **Improve Cache Architecture**
- **Problem**: Multiple cache implementations with inconsistent strategies, memory management concerns
- **Impact**: Memory issues, poor performance, unpredictable behavior
- **Solution**:
  - Implement **Strategy Pattern** for different cache backends
  - Create **CachePolicy** enum (LRU, TTL, Size-based)
  - Add **CacheMetrics** for monitoring hit/miss rates
  - Implement **ChainOfResponsibility** for cache layers (memory → disk → network)
  - Add cache warming and preloading capabilities

### 7. **Eliminate Code Duplication with Logging Mixin**
- **Problem**: 30+ files with identical `logger = logging.getLogger(__name__)` pattern
- **Impact**: Repeated boilerplate code, inconsistent logging patterns
- **Solution**:
  - Create `LoggingMixin` class with standardized logging setup
  - Add log level configuration per module
  - Implement structured logging with context (user, shot, operation)
  - Create `@log_execution` decorator for method timing/tracing

## Implementation Strategy

### Phase 1 (Week 1-2): Foundation
- **Priority 1**: Start with MainWindow refactoring - highest impact on maintainability
- **Priority 2**: Fix critical type errors in parallel - provides safety net for refactoring

### Phase 2 (Week 3): Core Components
- **Priority 3**: Refactor scene finder module
- **Priority 7**: Implement logging mixin (quick win)

### Phase 3 (Week 4): Architecture
- **Priority 4**: Reduce coupling through dependency injection
- **Priority 5**: Consolidate threading utilities

### Phase 4 (Week 5): Optimization
- **Priority 6**: Improve cache architecture
- Comprehensive testing of refactored components

## Key Principles

1. **Incremental Refactoring**: Each change should keep tests passing
2. **Extract Don't Rewrite**: Pull out functionality, don't rebuild from scratch
3. **Test Coverage**: Use existing 106 test files to ensure no regressions
4. **Signal Preservation**: Maintain existing Qt signal-slot architecture
5. **Backward Compatibility**: Don't break existing functionality

## Risk Mitigation

- Start with least risky extractions (UI setup, settings persistence)
- Keep original files as backup during transition
- Use feature flags to toggle between old/new implementations
- Extensive testing at each step
- Document all interface changes

---
*Analysis completed: 2025-01-14*
*Next review: After Phase 1 completion*