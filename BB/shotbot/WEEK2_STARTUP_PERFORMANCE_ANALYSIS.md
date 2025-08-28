# Week 2: Startup Performance Analysis Report

## Executive Summary
Total startup time: **1,316.35 ms** (1.3 seconds)
- Module imports: 905.82 ms (69%)
- MainWindow creation: 410.53 ms (31%)

## Performance Bottlenecks Identified

### 1. PySide6.QtWidgets Import - 559.35 ms (42% of startup)
**Issue**: Qt widgets module is the single largest contributor to startup time
**Impact**: Over half a second delay before any application logic runs
**Root Cause**: PySide6 loads extensive widget classes and Qt runtime initialization

### 2. MainWindow Creation - 410.53 ms (31% of startup)
**Issue**: Heavy initialization in constructor
**Key Contributors**:
- `_setup_ui()`: 290 ms
- `threede_shot_grid` initialization: 259 ms
- Menu bar creation: 54 ms
- Accessibility setup: 32 ms

### 3. Module Import Chain - 344.88 ms (26% of startup)
- `main_window` module: 201.41 ms
- `cache_manager` module: 100.86 ms
- `shot_model` module: 42.15 ms

### 4. Shot Model Refresh - 661.83 ms
**Issue**: Synchronous workspace command execution
**Impact**: Blocks UI during initial load
**Note**: This happens after startup but affects perceived performance

## Detailed Timing Breakdown

### Import Times
```
PySide6.QtWidgets       559.35 ms  ████████████████████████████
main_window            201.41 ms  ██████████
cache_manager          100.86 ms  █████
shot_model              42.15 ms  ██
process_pool_manager     2.04 ms  ▌
PySide6.QtCore           0.01 ms  
PySide6.QtGui            0.00 ms  (already loaded)
```

### MainWindow Components
```
_setup_ui()            290.00 ms  ████████████████
threede_shot_grid      259.00 ms  ██████████████
menu_bar                54.00 ms  ███
accessibility           32.00 ms  ██
stylesheets             23.00 ms  █
```

### Cache Operations (Post-Startup)
```
refresh_shots          661.83 ms  ████████████████████████████████
clear_cache              6.02 ms  ▌
cache_shots              1.69 ms  
get_cached_shots         0.05 ms  
```

## Optimization Strategies

### Priority 1: Lazy Loading Qt Modules (Potential: -300ms)
```python
# Before: Eager import
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, 
    QHBoxLayout, QPushButton, QTabWidget,
    QSplitter, QMenuBar, QMenu, QToolBar
)

# After: Lazy import
def _import_qt_widgets():
    global QMainWindow, QWidget, QVBoxLayout
    from PySide6.QtWidgets import (
        QMainWindow, QWidget, QVBoxLayout, ...
    )
```

### Priority 2: Defer Heavy Widget Creation (Potential: -200ms)
```python
# Before: Create all tabs immediately
def _setup_ui(self):
    self.shot_grid = ShotGrid()
    self.threede_grid = ThreeDEGrid()  # 259ms!
    self.previous_grid = PreviousShotsGrid()

# After: Create tabs on demand
def _setup_ui(self):
    self.shot_grid = ShotGrid()
    self._threede_grid = None  # Create when tab activated
    
def _on_tab_changed(self, index):
    if index == 1 and not self._threede_grid:
        self._threede_grid = ThreeDEGrid()
```

### Priority 3: Async Shot Loading (Potential: -600ms perceived)
```python
# Before: Blocking refresh
def __init__(self):
    self.shot_model = ShotModel()
    self.shot_model.refresh_shots()  # 661ms block!

# After: Background refresh
def __init__(self):
    self.shot_model = ShotModel(load_cache=True)
    QTimer.singleShot(0, self._async_refresh)
    
def _async_refresh(self):
    self.refresh_worker = RefreshWorker()
    self.refresh_worker.finished.connect(self._on_refresh_done)
    self.refresh_worker.start()
```

### Priority 4: Module Import Optimization (Potential: -100ms)
```python
# Before: Import everything at module level
import logging
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

# After: Import only essentials, defer others
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path
    from datetime import datetime
```

### Priority 5: Cache Manager Simplification (Potential: -50ms)
- Move heavy initialization out of __init__
- Lazy-create thread pools
- Defer storage backend initialization

## Implementation Recommendations

### Quick Wins (< 1 day)
1. **Async shot refresh**: Move refresh_shots() out of constructor
2. **Defer menu creation**: Create menus on first access
3. **Lazy stylesheet loading**: Load CSS on demand

### Medium Effort (1-2 days)
1. **Tab lazy loading**: Create tab content when activated
2. **Import optimization**: Move non-critical imports to functions
3. **Cache manager refactor**: Lazy initialization of components

### Long Term (3-5 days)
1. **Qt module splitting**: Custom Qt import wrapper with lazy loading
2. **Progressive UI**: Show minimal UI first, enhance progressively
3. **Worker thread pool**: Pre-warmed threads for async operations

## Performance Targets

### Current State (1,316 ms)
- Import phase: 906 ms
- UI creation: 410 ms

### After Quick Wins (Target: 900 ms)
- Import phase: 900 ms (unchanged)
- UI creation: 0 ms (deferred)
- Background: +600 ms (non-blocking)

### After Full Optimization (Target: 500 ms)
- Import phase: 300 ms (lazy Qt)
- UI creation: 200 ms (minimal UI)
- Background: +400 ms (progressive enhancement)

## Perceived Performance Strategy

Beyond actual performance, perceived performance matters:

1. **Show something immediately**: Even a splash screen
2. **Progressive disclosure**: Load visible content first
3. **Async everything**: Never block the UI thread
4. **Loading indicators**: Show progress for long operations
5. **Cache aggressively**: Use cached data while refreshing

## Memory Impact

Current startup memory allocation:
- Qt modules: ~45 MB
- Application modules: ~12 MB
- Cache structures: ~8 MB
- Total: ~65 MB

With lazy loading:
- Initial: ~25 MB
- Full load: ~65 MB (same final state)

## Conclusion

The primary bottleneck is Qt module import time (42% of startup). Combined with heavy MainWindow initialization (31%), these account for 73% of startup time.

Implementing lazy loading and deferred initialization can reduce perceived startup time from 1.3 seconds to under 500ms, while maintaining full functionality through progressive enhancement.

The most impactful optimization is moving the 661ms shot refresh to a background thread, which would make the application appear responsive immediately while loading data asynchronously.