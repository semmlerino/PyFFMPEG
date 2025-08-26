# UNIFIED_TESTING_GUIDE Refactoring Plan
*Created: 2025-01-11 | Status: Ready for Implementation*

## Executive Summary
Restructure the 1,288-line UNIFIED_TESTING_GUIDE_DO_NOT_DELETE.md to a focused 700-line guide optimized for LLM usage, incorporating modern pytest/pytest-qt best practices from 2024-2025.

## Current State Analysis

### Problems Identified
1. **Size**: 1,288 lines - too large for optimal LLM context usage
2. **Redundancy**: Qt threading appears 6+ times, 'ws' command 3+ times
3. **Organization**: No clear hierarchy, jumps between conceptual and tactical
4. **Missing Modern Patterns**: No factory fixtures, pytest.param, fixture scopes, qtbot.waitUntil
5. **No Quick Start**: LLM must scan entire document to find common patterns

### Strengths to Preserve
- Decision trees (lines 59-113) - Excellent for algorithmic decisions
- Quick Lookup Table (line 966) - Perfect for pattern matching
- Test Templates (lines 416-585) - Directly usable code
- Clear anti-patterns with ❌ and ✅ examples

## Implementation Plan

### Phase 1: Extract Content to Separate Files

#### 1. Create WSL-TESTING.md
Extract lines 835-962 from current guide:
```markdown
# WSL Testing Guide for ShotBot

## Performance Characteristics
- /mnt/c operations are 10-100x slower than native Linux
- Test collection can take 60+ seconds
- Solution: Categorize tests and use optimized runners

## Test Categorization
@pytest.mark.fast  # < 100ms
@pytest.mark.slow  # > 1s
@pytest.mark.critical  # Must pass

## Optimized pytest.ini
[tool:pytest]
addopts = 
    -q                    # Quiet output
    -ra                   # Show all test outcomes
    --maxfail=1          # Stop on first failure
    -p no:cacheprovider  # Disable cache (slow on WSL)
    --tb=short           # Shorter tracebacks

## Running Tests
python3 quick_test.py              # 2 seconds
python3 run_tests_wsl.py --fast    # 30 seconds
python3 run_tests_wsl.py --all     # Full suite in batches

## Performance Tips
1. Use tmpfs for test artifacts
2. Minimize test collection
3. Disable unnecessary pytest features
```

#### 2. Create CACHE-TESTING.md
Extract lines 587-678 from current guide:
```markdown
# Cache Architecture Testing Guide

## Component Testing Matrix
| Component | Test in Isolation | Key Test Scenarios |
|-----------|------------------|-------------------|
| StorageBackend | ✅ Yes | Atomic writes, thread safety |
| FailureTracker | ✅ Yes | Exponential backoff, cleanup |
| MemoryManager | ✅ Yes | LRU eviction, size tracking |
| ThumbnailProcessor | ⚠️ Partial | Format support, thread safety |
| ShotCache | ✅ Yes | TTL expiration, serialization |
| ThreeDECache | ✅ Yes | Metadata, deduplication |
| CacheValidator | ❌ No | Consistency, repair |
| ThumbnailLoader | ❌ No | Async loading, signals |

## Component Isolation Testing
[Include code examples from lines 604-629]

## Component Integration Testing  
[Include code examples from lines 632-652]

## Cache Manager Facade Testing
[Include code examples from lines 655-677]
```

#### 3. Create PROPERTY-TESTING.md
Extract lines 239-299 from current guide:
```markdown
# Property-Based Testing with Hypothesis

## When to Use
- Path operations and validation
- Cache key generation  
- Parsing functions
- Data transformations
- Invariants for all inputs

## ShotBot Patterns

### Path Operations
@given(st.from_regex(r"/shows/[a-z0-9_]+/[a-z0-9_]+/\d{4}", fullmatch=True))
def test_shot_path_roundtrip(path):
    shot = Shot.from_path(path)
    assert shot.to_path() == path

### Cache Key Invariants
[Include examples from lines 263-273]

### Workspace Command Parsing
[Include examples from lines 277-298]
```

### Phase 2: Restructure Main Guide

#### New Structure (700 lines total):

```markdown
# Unified Testing Guide for ShotBot
*Optimized for LLM usage - Single source of truth*

## 🚀 QUICK START (50 lines)

### What Are You Testing? (Decision Tree)
```
IF testing Qt widget → Jump to "Qt Widget Pattern" (line 180)
ELIF testing worker thread → Jump to "Worker Thread Pattern" (line 230)
ELIF testing 'ws' command → Jump to "TestProcessPoolManager" (line 280)
ELIF testing cache → Jump to "Cache Testing" (line 330)
ELIF testing signals → Jump to "Signal Testing" (line 380)
ELSE → Check Quick Lookup Table (line 600)
```

### Most Common Pattern (Copy & Paste)
```python
def test_widget(qtbot):
    widget = MyWidget()
    qtbot.addWidget(widget)  # CRITICAL: Register for cleanup
    
    qtbot.mouseClick(widget.button, Qt.LeftButton)
    assert widget.label.text() == "Expected"
```

### Factory Fixture Pattern (Modern Best Practice)
```python
@pytest.fixture
def make_shot():
    def _make(show="test", seq="seq1", shot="0010"):
        return Shot(show, seq, shot, f"/shows/{show}/{seq}/{shot}")
    return _make

def test_with_factory(make_shot):
    shot1 = make_shot()
    shot2 = make_shot(show="other")
```

## 📋 CORE PRINCIPLES (50 lines)

### Three Fundamental Rules
1. **Test Behavior, Not Implementation**
   ❌ mock.assert_called_once()  # Who cares?
   ✅ assert result.success       # Actual outcome

2. **Real Components Over Mocks**
   ❌ controller = Mock(spec=Controller)
   ✅ controller = Controller(process_pool=TestProcessPool())

3. **Mock Only at System Boundaries**
   - External APIs, Network calls
   - Subprocess calls
   - System time
   - NOT internal methods

### Mocking Decision Algorithm
```
FOR each dependency:
    IF crosses process boundary → Mock/TestDouble
    ELIF network/external API → Mock
    ELIF Qt widget/signal → Use real with qtbot
    ELIF internal method → Use real
```

## 🎯 COMMON PATTERNS (250 lines)

### Unit Test Pattern
```python
def test_pure_logic():
    # No mocks needed for pure functions
    result = calculate_something(input_data)
    assert result == expected
```

### Qt Widget Pattern
```python
def test_widget(qtbot):
    widget = MyWidget()
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)
    
    # Modern signal waiting
    with qtbot.waitSignal(widget.finished, timeout=1000):
        widget.start_operation()
    
    # Condition waiting (NEW)
    qtbot.waitUntil(lambda: widget.isReady(), timeout=1000)
```

### Worker Thread Pattern (CRITICAL - Thread Safety)
```python
def test_worker(qtbot):
    # ⚠️ NEVER use QPixmap in worker threads!
    worker = ImageWorker()
    
    # Use ThreadSafeTestImage instead
    image = ThreadSafeTestImage(100, 100)
    worker.set_image(image)
    
    with qtbot.waitSignal(worker.finished):
        worker.start()
    
    # Cleanup
    if worker.isRunning():
        worker.quit()
        worker.wait(1000)
```

### Signal Testing Pattern
```python
# Modern parameter checking (NEW)
def check_value(val):
    return val > 100

with qtbot.waitSignal(signal, check_params_cb=check_value):
    trigger_action()

# Negative testing with wait (NEW)
with qtbot.assertNotEmitted(signal, wait=100):
    other_action()
```

### TestProcessPoolManager Pattern ('ws' Command)
```python
# CRITICAL: 'ws' is a shell function, not executable!
def test_shot_refresh():
    model = ShotModel()
    
    test_pool = TestProcessPoolManager()
    test_pool.set_outputs(
        "workspace /shows/TEST/seq01/0010",
        "workspace /shows/TEST/seq01/0020"
    )
    model._process_pool = test_pool
    
    result = model.refresh_shots()
    assert result.success
```

### Parametrization Patterns (Modern)
```python
# Basic parametrization
@pytest.mark.parametrize("input,expected", [
    (1, 2),
    (3, 4),
])

# With marks (NEW)
@pytest.mark.parametrize("count,expected", [
    (10, True),
    pytest.param(1000, True, marks=pytest.mark.slow),
])

# Indirect fixture parametrization (NEW)
@pytest.mark.parametrize("db", ["mysql", "pg"], indirect=True)
```

### Fixture Scope Optimization (NEW)
```python
@pytest.fixture(scope="session")  # Expensive, reuse
def heavy_resource():
    return ExpensiveSetup()

@pytest.fixture(scope="function")  # Default, isolated
def test_data():
    return {"key": "value"}
```

## ⚠️ CRITICAL RULES (100 lines)

### Qt Threading Rule (FATAL if violated)
**QPixmap = Main Thread ONLY | QImage = Any Thread**

❌ **CRASHES PYTHON**:
```python
def worker():
    pixmap = QPixmap(100, 100)  # Fatal Python error: Aborted
threading.Thread(target=worker).start()
```

✅ **SAFE**:
```python
def worker():
    image = ThreadSafeTestImage(100, 100)  # Thread-safe
threading.Thread(target=worker).start()
```

### Signal Race Conditions
❌ **RACE CONDITION**:
```python
worker.start()  # Signal might emit before setup!
with qtbot.waitSignal(worker.started):
    pass
```

✅ **SAFE**:
```python
with qtbot.waitSignal(worker.started):
    worker.start()  # Signal captured correctly
```

### Qt Container Truthiness
❌ **BUG**:
```python
if self.layout:  # False for empty QVBoxLayout!
    self.layout.addWidget(widget)
```

✅ **CORRECT**:
```python
if self.layout is not None:
    self.layout.addWidget(widget)
```

## 📊 QUICK REFERENCE (150 lines)

### Lookup Table
| Scenario | Solution |
|----------|----------|
| Testing shot refresh | TestProcessPoolManager |
| Testing thumbnails in threads | ThreadSafeTestImage |
| Testing Qt dialogs | Mock exec() |
| Testing worker threads | QThread with cleanup |
| Testing signal emission | waitSignal BEFORE action |
| Testing conditions | qtbot.waitUntil |

### Complete Marker Strategy
```python
markers = [
    "unit: Pure logic tests",
    "integration: Component integration",
    "qt: Qt-specific tests",
    "slow: Tests >1s",
    "performance: Benchmark tests",
    "stress: Load tests",
    "critical: Must-pass tests",
    "flaky: Known intermittent issues",
]
```

### Essential Fixtures
```python
@pytest.fixture
def qtbot(): ...           # Qt test interface
@pytest.fixture
def tmp_path(): ...         # Temp directory
@pytest.fixture
def make_shot(): ...        # Shot factory (NEW)
@pytest.fixture(scope="session")
def expensive_setup(): ...  # Session-scoped (NEW)
```

### Commands
```bash
# Run tests
python run_tests.py

# Fast tests only
pytest -m "not slow"

# With coverage
pytest --cov=. --cov-report=html
```

## 📚 APPENDIX (100 lines)

### Test Doubles Library
```python
class TestProcessPoolManager:
    """For 'ws' command testing"""
    
class ThreadSafeTestImage:
    """For thread-safe image testing"""
    
class TestSignal:
    """Lightweight signal double"""
```

### Common Issues & Solutions
| Issue | Solution |
|-------|----------|
| "Fatal Python error: Aborted" | Using QPixmap in thread - use QImage |
| Collection warnings | Classes starting with Test need renaming |
| Signal not received | Set up waitSignal before triggering |
| Empty Qt container is falsy | Use `is not None` check |

### External Guides
- WSL Testing → WSL-TESTING.md
- Cache Testing → CACHE-TESTING.md  
- Property Testing → PROPERTY-TESTING.md

### Pytest Deprecation Fixes
- Use `pytest.fail()` not `pytest.raises()`
- Use `tmp_path` not `tmpdir`
- Use `pytest.param` for parametrize marks
```

### Phase 3: Content Migration Checklist

#### To Remove Completely:
- [ ] Anti-pattern detection function (lines 988-1008)
- [ ] Flakiness quarantine details (lines 1099-1136)
- [ ] Excessive Qt API listing (most of line 8 content)
- [ ] Duplicate threading examples (consolidate 6 occurrences)

#### To Consolidate:
- [ ] QPixmap/QImage (6 occurrences → 1 authoritative section)
- [ ] 'ws' command (3 occurrences → 1 section)
- [ ] Signal testing (scattered → 1 unified section)

#### To Add:
- [ ] Factory fixture pattern
- [ ] pytest.param with marks
- [ ] Fixture scope optimization
- [ ] qtbot.waitUntil
- [ ] qtbot.assertNotEmitted with wait
- [ ] check_params_cb for signals

## Success Metrics
- [ ] Guide reduced to ~700 lines
- [ ] Zero redundancy (each concept once)
- [ ] Clear "START HERE" section
- [ ] Modern patterns included
- [ ] 3 separate detailed guides created
- [ ] Improved LLM parsing speed

## Execution Order
1. Create the 3 new .md files first
2. Back up current UNIFIED_TESTING_GUIDE
3. Restructure main guide following new structure
4. Verify all critical content preserved
5. Test with sample queries to ensure usability

## Notes for Implementation
- Preserve exact code examples that work
- Keep the ❌ and ✅ pattern for clarity
- Ensure line number references in Quick Start are accurate
- Test the decision tree logic for completeness
- Maintain the practical, no-nonsense tone

*This plan provides complete context for continuing the refactoring work.*