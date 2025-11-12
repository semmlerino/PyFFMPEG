# Python Modernization - Quick Reference Guide

## One-Page Summary

**Shotbot Modernization Score: 85/100** - Already very well-modernized!

### Top 3 Quick Wins

#### 1. Dict Union Operator (30 min)
```python
# OLD - exceptions.py, model files
error_details = details or {}
if workspace_path:
    error_details["workspace_path"] = workspace_path

# NEW - Python 3.9+
error_details = (details or {}) | {"workspace_path": workspace_path}
```

#### 2. Exception Classes to Dataclasses (45 min)
```python
# OLD - exceptions.py:31-47
class ShotBotError(Exception):
    def __init__(self, message, details=None, error_code=None):
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.error_code = error_code or "SHOTBOT_ERROR"

# NEW
@dataclass
class ShotBotError(Exception):
    message: str
    details: dict = field(default_factory=dict)
    error_code: str = "SHOTBOT_ERROR"
    
    def __post_init__(self):
        super().__init__(self.message)
```

#### 3. NamedTuple to Dataclass (20 min)
```python
# OLD - cache_manager.py:85-92
class ShotMergeResult(NamedTuple):
    updated_shots: list[ShotDict]
    new_shots: list[ShotDict]
    removed_shots: list[ShotDict]
    has_changes: bool

# NEW
@dataclass(frozen=True)  # Immutable like NamedTuple
class ShotMergeResult:
    updated_shots: list[ShotDict]
    new_shots: list[ShotDict]
    removed_shots: list[ShotDict]
    has_changes: bool
```

---

## Feature Status Checklist

### Type System
- [x] 90% Type hint coverage
- [x] TypedDict usage (ShotDict, ThreeDESceneDict)
- [x] Protocol usage (Filterable, _HasToDict)
- [x] Union syntax (`str | None`)
- [x] Type aliases (JSONValue)

### String Formatting
- [x] 95% f-string usage
- [x] No old-style % formatting
- [x] No excessive .format() calls

### Modern Patterns
- [x] Dataclasses in core models
- [x] Walrus operator where beneficial
- [x] Pathlib for all path operations
- [ ] Dict union operator (opportunity: 307 dict() calls)
- [ ] Exception dataclasses (opportunity: 8 classes)
- [ ] Singleton pattern modernization (opportunity: 3-4 singletons)

### Standard Library
- [x] functools.lru_cache in utils.py
- [x] contextlib for context managers
- [x] functools.partial for callbacks
- [x] collections.defaultdict
- [x] collections.deque
- [ ] functools.reduce for aggregations (optional)
- [ ] itertools for better iteration (optional)

---

## Priority Matrix

### Do First (1-2 hours, very low risk)
1. **exceptions.py** - Dict union operator
   - Files: exceptions.py
   - Time: 30 min
   - Risk: None (just syntax change)
   - Lines saved: ~50

2. **exceptions.py** - Convert to dataclasses
   - Files: exceptions.py
   - Time: 45 min
   - Risk: Low (add tests)
   - Lines saved: ~150

3. **cache_manager.py** - NamedTuple → dataclass
   - Files: cache_manager.py
   - Time: 20 min
   - Risk: Very low
   - Lines saved: ~5

### Do Next (3-5 hours, low risk)
4. **path_validators.py** - Add more walrus operators
   - Files: path_validators.py
   - Time: 20 min
   - Risk: Very low

5. **launcher/models.py** - NamedTuple conversions
   - Files: launcher/models.py
   - Time: 20 min
   - Risk: Very low

### Do Later (5-8 hours, medium risk)
6. **Singleton pattern** - Introduce metaclass
   - Files: filesystem_coordinator.py, progress_manager.py
   - Time: 6-8 hours
   - Risk: Medium (affects multiple classes)

7. **functools.cached_property** - Selective use
   - Files: various model classes
   - Time: 3-4 hours
   - Risk: Low (very selective)

---

## Don't Change (Already Perfect)

- ✅ Type hint system
- ✅ Pathlib usage (90%+)
- ✅ f-string usage (95%+)
- ✅ Config class organization
- ✅ Dataclass usage in core models (Shot, ThreeDEScene)
- ✅ Protocol usage
- ✅ TypedDict usage

---

## Files by Priority

| Priority | File | Action | Effort | Impact |
|----------|------|--------|--------|--------|
| 1 | exceptions.py | Dict union + dataclass | 1 hr | High |
| 2 | cache_manager.py | NamedTuple → dataclass | 20 min | Medium |
| 3 | launcher/models.py | NamedTuple → dataclass | 20 min | Low |
| 3 | path_validators.py | Walrus operators | 20 min | Low |
| 4 | filesystem_coordinator.py | Singleton pattern | 2 hrs | Medium |

---

## Implementation Notes

### Dict Union Operator
- Python 3.9+ required (project uses 3.11+)
- Works with any dict-like objects
- Right side overwrites left side on conflicts
- Cleaner than dict() constructor with updates

### Dataclass for Exceptions
- Need to call `super().__init__(message)` in `__post_init__`
- Maintains backward compatibility
- Automatic `__repr__`, `__eq__`, `__hash__`
- Much less boilerplate

### NamedTuple → Dataclass
- Use `frozen=True` to maintain immutability
- Keep field order for positional construction
- Better IDE support, more flexible

### Singleton Pattern
- Current pattern: manual __new__ + locking
- Options:
  1. Metaclass (best for stateful singletons)
  2. functools.cache (best for stateless)
  3. Factory function (simple alternative)
- Benefit: less code duplication

---

## Testing Impact

All changes are **backward compatible**:
- Exception behavior unchanged
- Dict merging semantics identical
- NamedTuple and dataclass have same interface

**Test updates needed:**
- Any tests checking `__repr__` of exceptions (likely none)
- Any tests checking object type for singleton (minimal)

---

## Related Files

- **PYTHON_MODERNIZATION_ANALYSIS.md** - Full detailed analysis
- **pyproject.toml** - Python version (3.11+)
- **pyrightconfig.json** - Type checking config

---

## Questions?

For detailed explanation of each opportunity, see:
**PYTHON_MODERNIZATION_ANALYSIS.md**

For each recommendation, the full report provides:
- Current code examples
- Modern alternatives
- Benefits explanation
- Implementation details
- File references with line numbers
