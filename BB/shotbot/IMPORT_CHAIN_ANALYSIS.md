# Import Chain Analysis
*Date: 2025-08-25*

## Main Window Import Breakdown

### Total Import Time: 1,052ms

### Major Components:
| Component | Time (ms) | % of Total | Status |
|-----------|-----------|------------|--------|
| PySide6.QtCore | 370 | 35% | BLOCKER |
| PySide6.QtGui | 141 | 13% | BLOCKER |
| PySide6.QtWidgets | 113 | 11% | BLOCKER |
| main_window (self) | 160 | 15% | High |
| cache_manager + modules | 70 | 7% | Moderate |
| previous_shots_grid | 39 | 4% | OK |
| command_launcher | 32 | 3% | OK |
| launcher_dialog | 20 | 2% | OK |
| shot_grid_view | 18 | 2% | OK |
| Other | ~89 | 8% | OK |

### PySide6 Impact
- **Total PySide6 time**: ~625ms (59% of total)
- **Cannot be optimized directly** (external library)
- **Solution**: Lazy loading or splash screen

## Optimization Strategies

### 1. Immediate: Lazy Import Heavy Modules
```python
# Instead of top-level imports:
# from launcher_dialog import LauncherDialog

# Use lazy imports in methods:
def show_launcher_dialog(self):
    from launcher_dialog import LauncherDialog
    dialog = LauncherDialog(self)
```

**Potential savings**: 100-150ms

### 2. Short-term: Split main_window.py
Current: 1,755 lines importing everything upfront

Proposed structure:
```
main_window.py (300 lines) - Core only
├── ui/main_window_ui.py - UI setup
├── ui/main_window_menus.py - Menu/toolbar
├── controllers/shot_controller.py - Shot logic
├── controllers/launcher_controller.py - Launcher logic
└── controllers/cache_controller.py - Cache logic
```

**Potential savings**: 200-300ms

### 3. Medium-term: Implement Splash Screen
```python
# Show splash immediately (before heavy imports)
app = QApplication(sys.argv)
splash = QSplashScreen(QPixmap("splash.png"))
splash.show()
app.processEvents()

# Then import heavy modules
from main_window import MainWindow
window = MainWindow()
splash.finish(window)
```

**User experience**: Immediate feedback

### 4. Long-term: Plugin Architecture
- Load features on-demand
- Separate core from optional features
- Use QPluginLoader for dynamic loading

## Import Chain Dependencies

### Critical Path (must load):
1. PySide6.QtCore (370ms) - Required for Qt
2. PySide6.QtWidgets (113ms) - Required for UI
3. config.py (fast) - Configuration
4. shot_model.py (14ms) - Core data model

### Can Be Deferred:
1. launcher_dialog (20ms) - Only when opening dialog
2. previous_shots_grid (39ms) - Only for that tab
3. threede_scene_worker (10ms) - Only when scanning
4. cache submodules (50ms) - Can lazy load

### Heavy Submodule Chains:
- cache_manager → 8 submodules (70ms total)
- command_launcher → raw_plate_finder → utils (32ms total)
- launcher_dialog → launcher_config → launcher_manager (20ms total)

## Recommended Actions

### Phase 1: Quick Wins (Today)
1. ✅ Move launcher_dialog import to method level
2. ✅ Defer previous_shots_grid until tab switch
3. ✅ Lazy load threede_scene_worker

Expected improvement: **100-150ms (10-15%)**

### Phase 2: Refactor (This Week)
1. Extract UI setup to separate module
2. Create controller classes for business logic
3. Implement lazy property pattern for heavy objects

Expected improvement: **200-300ms (20-30%)**

### Phase 3: Architecture (Next Week)
1. Implement splash screen
2. Create plugin system for optional features
3. Use QThread for background initialization

Expected improvement: **User perceives instant startup**

## Code Examples

### Lazy Import Pattern
```python
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._launcher_dialog = None
        
    @property
    def launcher_dialog(self):
        if self._launcher_dialog is None:
            from launcher_dialog import LauncherDialog
            self._launcher_dialog = LauncherDialog
        return self._launcher_dialog
        
    def show_launcher_manager(self):
        dialog = self.launcher_dialog(self)
        dialog.exec()
```

### Deferred Tab Loading
```python
def on_tab_changed(self, index):
    if index == 2 and not self.previous_shots_loaded:
        from previous_shots_grid import PreviousShotsGrid
        self.previous_shots_grid = PreviousShotsGrid()
        self.previous_shots_loaded = True
```

## Measurement Script
```bash
# Baseline
time python3 -c "import main_window"

# After optimization
time python3 -c "import main_window_optimized"

# Detailed analysis
python3 -X importtime -c "import main_window" 2>&1 | \
  awk '/import time:/ {sum+=$5} END {print "Total:", sum/1000, "ms"}'
```

## Success Metrics
- [ ] Import time <700ms (from 1,052ms)
- [ ] First window appears <500ms
- [ ] All features available <2s
- [ ] No functionality regression

---
*This analysis guides the optimization of application startup time.*