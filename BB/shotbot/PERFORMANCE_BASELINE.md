# Performance Baseline Report
*Date: 2025-08-25*

## Executive Summary
This report establishes performance baselines for the ShotBot application, identifying bottlenecks and providing metrics for tracking improvements.

## 1. Import Performance

### Module Import Times
| Module | Time (ms) | Status |
|--------|-----------|--------|
| shotbot | 38.7 | Good |
| main_window | **1,039.6** | SLOW - Primary bottleneck |
| cache_manager | <0.1 | Excellent (already imported) |
| shot_model | <0.1 | Excellent (already imported) |
| **Total** | **~1,100** | Target: <500ms |

### Import Chain Analysis
- **main_window.py** is the primary bottleneck (1+ second)
- Likely loading heavy Qt/PySide6 components
- Cascading imports from multiple large modules

## 2. Code Complexity Metrics

### Highest Complexity Functions
| Function | File | Complexity | Risk |
|----------|------|------------|------|
| `PersistentBashSession._start_session` | process_pool_manager.py | **F (55)** | CRITICAL |
| `PersistentBashSession._read_with_backoff` | process_pool_manager.py | **E (39)** | CRITICAL |
| `PersistentBashSession.execute` | process_pool_manager.py | **C (20)** | High |
| `LauncherManager.update_launcher` | launcher_manager.py | **C (18)** | High |
| `LauncherManager.execute_launcher` | launcher_manager.py | **C (17)** | High |

### Complexity by File
| File | Average | Max | Functions >10 |
|------|---------|-----|---------------|
| process_pool_manager.py | 5.8 (B) | 55 (F) | 3 |
| launcher_manager.py | 4.2 (A) | 18 (C) | 5 |
| main_window.py | 2.3 (A) | 12 (C) | 2 |
| cache_manager.py | 2.1 (A) | 17 (C) | 1 |

## 3. File Size Analysis

### Large Files Requiring Refactoring
| File | Lines | Target | Reduction Needed |
|------|-------|--------|------------------|
| launcher_manager.py | **2,003** | 500 | -75% |
| main_window.py | **1,755** | 500 | -71% |
| process_pool_manager.py | **1,449** | 500 | -66% |
| **Total** | **5,207** | 1,500 | -71% |

### Acceptable Files
- cache_manager.py: 572 lines (recently refactored)
- shot_model.py: 543 lines (acceptable)

## 4. Technical Debt Quantified

### Files in Root Directory
- **Current**: 131 Python files
- **Target**: <50 files
- **Action**: Move 80+ files to appropriate directories

### Archived Today
- **Location**: `archive_2025_08_25/`
- **Files moved**: 25+ files including:
  - 4 legacy cache implementations
  - All `.backup` and `.bak` files
  - Performance monitoring modules (obsolete)

### Still Needs Cleanup
- Test utilities in root: ~10 files
- Fix/refactor scripts: ~15 files
- Demo/example files: ~5 files

## 5. Memory & Resource Usage

### Estimated Memory Footprint
- **Import overhead**: ~50MB (PySide6 + dependencies)
- **Cache system**: 100MB limit (configured)
- **Typical session**: 200-300MB expected
- **Peak usage**: Unknown (needs profiling)

## 6. Test Suite Performance

### Test Execution Times
- **Total tests**: 1,172
- **Fast tests (<100ms)**: 607 (52%)
- **Slow tests (>1s)**: 565 (48%)
- **Average time**: ~40ms per test
- **Total suite time**: ~47 seconds

### Performance Issues
- 48% slow tests indicate potential application performance problems
- WSL filesystem overhead affects both tests and application
- Parallel execution often slower than serial due to overhead

## 7. Critical Performance Bottlenecks

### Priority 1 - Import Time
- **Issue**: 1+ second startup time
- **Cause**: Heavy main_window.py imports
- **Solution**: Lazy loading, module splitting

### Priority 2 - Complex Functions
- **Issue**: F/E level complexity in process_pool_manager
- **Cause**: Monolithic session management
- **Solution**: Extract and simplify logic

### Priority 3 - File Sizes
- **Issue**: 3 files >1,400 lines each
- **Cause**: Lack of separation of concerns
- **Solution**: Decompose into focused modules

## 8. Performance Targets

### Short-term (1 week)
- [ ] Import time <0.7 seconds
- [ ] No function >30 complexity (D level max)
- [ ] Archive 50+ obsolete files

### Medium-term (2 weeks)
- [ ] Import time <0.5 seconds
- [ ] No function >20 complexity (C level max)
- [ ] No file >1,000 lines

### Long-term (4 weeks)
- [ ] Import time <0.3 seconds
- [ ] Average complexity <3 (A level)
- [ ] No file >500 lines
- [ ] Memory usage <150MB typical

## 9. Monitoring Plan

### Weekly Metrics
```bash
# Import time
time python3 -c "import shotbot"

# Complexity
radon cc *.py -s -a | grep "Average"

# File sizes
wc -l *.py | sort -rn | head -5

# Memory usage
python3 -c "
import psutil
import shotbot
print(f'Memory: {psutil.Process().memory_info().rss/1024/1024:.1f}MB')
"
```

### Regression Detection
- Set up CI to track import times
- Alert if complexity increases
- Monitor file size growth

## 10. Immediate Actions

### Today
1. ✅ Archived 25+ obsolete files
2. ✅ Fixed broken imports from archived modules
3. Continue moving test utilities to tests/

### Tomorrow
1. Profile main_window.py import chain
2. Start extracting PersistentBashSession
3. Create module dependency graph

### This Week
1. Reduce main_window.py to <1,000 lines
2. Simplify top 3 complex functions
3. Achieve <0.7s import time

## Appendix A: Profiling Commands

```bash
# Detailed import profiling
python3 -X importtime shotbot.py 2>&1 | head -50

# Memory profiling
python3 -m memory_profiler shotbot.py

# Line profiling for hot functions
kernprof -l -v shotbot.py

# Continuous monitoring
py-spy top -- python3 shotbot.py
```

## Appendix B: Optimization Opportunities

### Quick Wins (Days)
1. Lazy import heavy modules
2. Cache compiled regex patterns
3. Use __slots__ for frequently created objects

### Medium Effort (Weeks)
1. Implement startup splash screen
2. Background module loading
3. Optimize Qt widget creation

### Major Refactoring (Month)
1. Microservice architecture
2. Plugin system for features
3. Async/await for I/O operations

---
*This baseline will be used to measure the success of optimization efforts over the coming weeks.*