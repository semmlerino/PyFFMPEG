# Option B: Type Safety Campaign Plan

## Current Status (Week 1 Complete)
- ✅ Fixed 11 F811 redefinition errors
- ✅ Fixed 8 F401 unused imports  
- ✅ Reviewed 30 E402 module import ordering issues (non-critical)
- ✅ Verified test suite integrity (81 passing tests)

## Type Checking Baseline
- **2032 errors** - Critical typing issues
- **647 warnings** - Type incompatibilities
- **18376 notes** - Information about partial/unknown types

## 3-Week Type Safety Implementation Plan

### Week 2: Core Module Type Safety (Priority 1)
Focus on critical path modules with highest impact on stability:

#### Target Modules (0 type errors goal):
1. **shot_model.py** (286 lines)
   - Core data loading and caching
   - Shot list management
   - Refresh operations
   
2. **cache_manager.py** (369 lines) 
   - Performance-critical caching facade
   - Thumbnail processing
   - Memory management
   
3. **launcher_manager.py** (1116 lines)
   - Command execution safety
   - Process lifecycle management  
   - Thread-safe operations
   
4. **previous_shots_worker.py** (262 lines)
   - Background thread safety
   - Signal emission patterns
   - State management

#### Tasks:
- [ ] Add comprehensive type annotations to method signatures
- [ ] Fix Optional handling for Qt widgets
- [ ] Add TypedDict for configuration dictionaries
- [ ] Create Protocol definitions for interfaces
- [ ] Validate with `basedpyright --typeCheckingMode strict` on each module

### Week 3: UI Components & Workers (Priority 2)
Focus on Qt components and background workers:

#### Target Modules:
1. **main_window.py** (1187 lines)
   - Central UI coordination
   - Signal-slot connections
   - Widget lifecycle
   
2. **shot_grid.py** (350 lines)
   - Thumbnail grid management
   - Selection handling
   
3. **threede_scene_worker.py** (400 lines)
   - Background scanning
   - Progressive operations
   
4. **cache/** module package (8 files)
   - StorageBackend type safety
   - FailureTracker generics
   - ThumbnailProcessor protocols

#### Tasks:
- [ ] Add Qt signal type declarations
- [ ] Fix widget Optional patterns
- [ ] Add overload signatures for multi-purpose methods
- [ ] Create type stubs for external dependencies
- [ ] Run integration tests after each module

### Week 4: Utilities & Test Infrastructure (Priority 3)
Complete type coverage and establish CI/CD checks:

#### Target Modules:
1. **utils.py** (many unknown types)
   - Path operations
   - Validation utilities
   - Caching decorators
   
2. **config.py**
   - Configuration constants
   - Type-safe settings
   
3. **Test files**
   - Test double type safety
   - Fixture type annotations
   - Protocol compliance

#### Tasks:
- [ ] Fix all remaining type errors in utils.py
- [ ] Add type guards for runtime checks
- [ ] Create pytest plugin for type validation
- [ ] Set up pre-commit hooks for type checking
- [ ] Document type safety patterns in CONTRIBUTING.md

## Success Metrics
- **Week 2 End**: 0 errors in 4 core modules, <1500 total errors
- **Week 3 End**: 0 errors in 8 critical modules, <500 total errors  
- **Week 4 End**: <100 total errors, CI/CD type checking enabled

## Type Safety Patterns to Implement

### 1. Optional Widget Handling
```python
# Before
widget = self.findChild(QWidget, "name")
widget.setEnabled(True)  # Type error if None

# After
widget = self.findChild(QWidget, "name")
assert widget is not None, "Widget 'name' must exist"
widget.setEnabled(True)
```

### 2. Signal Type Declarations
```python
# Before
signal = Signal()

# After  
signal: Signal = Signal()
data_signal: Signal[dict] = Signal(dict)
```

### 3. TypedDict for Configurations
```python
from typing import TypedDict

class ShotData(TypedDict):
    show: str
    sequence: str
    shot: str
    workspace_path: str
```

### 4. Protocol Definitions
```python
from typing import Protocol

class CacheProtocol(Protocol):
    def cache_shots(self, shots: list[Shot]) -> None: ...
    def get_cached_shots(self) -> Optional[list[dict]]: ...
```

### 5. Overload Signatures
```python
from typing import overload

@overload
def get_path(as_string: Literal[True]) -> str: ...

@overload  
def get_path(as_string: Literal[False]) -> Path: ...

def get_path(as_string: bool = False) -> Union[str, Path]:
    path = Path("/some/path")
    return str(path) if as_string else path
```

## Risk Mitigation
- Test each module after type safety changes
- Keep backward compatibility with existing APIs
- Use gradual typing (start with public APIs)
- Document breaking changes if any
- Maintain separate branch for type safety work

## Tools & Configuration
- **basedpyright**: Primary type checker
- **mypy**: Secondary validation
- **pytest-mypy**: Test type checking
- **pre-commit**: Automated checks

## Next Steps After Type Safety Campaign
1. Performance profiling and optimization (Option C subset)
2. Architecture improvements for maintainability
3. Enhanced error handling and logging
4. API documentation generation from types