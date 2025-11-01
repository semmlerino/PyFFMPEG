# ShotBot Consolidation Analysis: Quick Reference

## Key Findings Summary

### Duplicate Code Volume
- **Total Estimated Duplication:** 1,500-2,000 lines
- **Percentage of Codebase:** ~20-25%
- **Effort to Consolidate:** 90 hours (2-3 person-weeks)
- **Expected Improvement:** 15-25% maintainability gain

---

## Top 10 Overlapping Responsibilities (Severity-Ranked)

### HIGH SEVERITY

**1. Shot Discovery & Filesystem Scanning (210 LOC)**
- Files: raw_plate_finder.py, undistortion_finder.py, plate_discovery.py
- Root Cause: No base abstraction for "iterate + filter + select best"
- Solution: Create FileSystemDiscoveryBase
- Impact: 60% reduction in these files

**2. Model Class Refresh/Load Patterns (200+ LOC)**
- Files: base_shot_model.py, shot_model.py, threede_scene_model.py, previous_shots_model.py
- Root Cause: ThreeDESceneModel and PreviousShotsModel don't inherit from BaseShotModel
- Solution: Create UnifiedModelBase[T]
- Impact: 80 LOC reduction per model

### MEDIUM SEVERITY

**3. Item Model Role Handling (70 LOC)**
- Files: threede_item_model.py mostly
- Root Cause: Repetitive if/elif chains for role mapping
- Solution: Add ROLE_CONFIG: ClassVar in base
- Impact: 50+ LOC reduction in threede_item_model

**4. Worker Progress Tracking (100+ LOC)**
- Files: threede_scene_worker.py, previous_shots_worker.py
- Root Cause: Duplicate QtProgressReporter + ProgressCalculator
- Solution: Consolidate in centralized ProgressManager
- Impact: 80+ LOC reduction

**5. Launcher Command Validation (150+ LOC)**
- Files: nuke_launch_handler.py, launcher_controller.py
- Root Cause: Each handler reimplements validation & conditional logic
- Solution: Create CommandBuilder pattern
- Impact: 40+ LOC reduction per handler

**6. Path Validation & Construction (120+ LOC)**
- Files: utils.py, finder_utils.py, raw_plate_finder.py, undistortion_finder.py
- Root Cause: PathUtils and FinderUtils overlap; finders reimplement
- Solution: Consolidate PathUtils + create PlatePathBuilder, ThumbnailPathBuilder
- Impact: 40+ LOC reduction

**7. Version Extraction (100+ LOC)**
- Files: utils.py, version_mixin.py, raw_plate_finder.py
- Root Cause: VersionMixin duplicates VersionUtils
- Solution: Remove VersionMixin, single VersionUtils authority
- Impact: 30+ LOC reduction

### LOW-MEDIUM SEVERITY

**8. Qt Signal Connections (20 LOC)**
- Pattern duplication across shot_item_model.py, threede_item_model.py, previous_shots_item_model.py
- Solution: Signal adapter pattern in base
- Impact: 10 LOC reduction per model

**9. Cache Merging Logic (50+ LOC)**
- Reimplemented across cache_manager.py, shot_model.py, threede_scene_model.py, previous_shots_model.py
- Solution: Generic CollectionDiffCalculator[T]
- Impact: 50+ LOC reduction

**10. Thumbnail Loading (30 LOC)**
- Split between base_item_model.py (loading) and delegates (display)
- Solution: Unified ThumbnailManager
- Impact: 30 LOC reduction

---

## Missing Abstractions (Priority Order)

| # | Abstraction | Status | Effort | Impact | Priority |
|---|-------------|--------|--------|--------|----------|
| 1 | FileSystemDiscoveryBase | Not implemented | 4h | 210 LOC | HIGH |
| 2 | UnifiedModelBase[T] | Partial (BaseShotModel) | 8h | 250+ LOC | HIGH |
| 3 | CommandBuilder | Not implemented | 6h | 150+ LOC | MEDIUM |
| 4 | ProgressTrackingManager | Partial (ProgressManager) | 4h | 100+ LOC | MEDIUM |
| 5 | ConfigurableRoleMapper | Not implemented | 2h | 70 LOC | MEDIUM |
| 6 | PlatePathBuilder | Not implemented | 3h | 40+ LOC | LOW-MEDIUM |
| 7 | ThumbnailPathBuilder | Not implemented | 3h | 40+ LOC | LOW-MEDIUM |
| 8 | CollectionDiffCalculator[T] | Not implemented | 2h | 50+ LOC | LOW |

---

## Duplicate Code Patterns (by Frequency)

### Pattern 1: "Build Path + Validate + Iterate" (42 occurrences)
**Total Duplication:** 210 lines (5 lines × 42)
**Consolidated Location:** FileSystemDiscoveryBase.discover_directories()

### Pattern 2: "Get Latest + Get Path" (31 occurrences)
**Total Duplication:** 248 lines (8 lines × 31)
**Consolidated Location:** VersionUtils.get_latest()

### Pattern 3: "Signal Emission + State Update" (25 occurrences)
**Total Duplication:** 100 lines (4 lines × 25)
**Consolidated Location:** BaseModel signal handling (automatic)

### Pattern 4: "Options Validation + Conditional Logic" (18 occurrences)
**Total Duplication:** 126 lines (7 lines × 18)
**Consolidated Location:** CommandBuilder

---

## Module Restructuring (Recommended)

### utils/ → utils/ + discovery/
**Current:** 650+ lines scattered
**Proposed:**
```
utils/
  ├── paths.py (consolidated PathUtils)
  ├── versions.py (VersionUtils - remove VersionMixin)
  ├── files.py, images.py, validation.py (unchanged)
  └── discovery.py (FileSystemDiscoveryBase)

discovery/
  ├── base.py (FileSystemDiscoveryBase)
  ├── plate_finder.py (RawPlateFinder refactored)
  ├── undistortion_finder.py (UndistortionFinder refactored)
  └── scene_finder.py (consolidated)
```
**Benefit:** 40% reduction, clearer boundaries

### models/ (NEW ORGANIZATION)
**Current:** Scattered, inconsistent hierarchy
**Proposed:**
```
models/
  ├── base.py (UnifiedModelBase[T])
  ├── shot_model.py (extends UnifiedModelBase[Shot])
  ├── threede_scene_model.py (extends UnifiedModelBase[ThreeDEScene])
  └── previous_shots_model.py (extends UnifiedModelBase[Shot])
```
**Benefit:** 250+ LOC eliminated, consistent patterns

### launchers/ (ENHANCED ORGANIZATION)
**Current:** Scattered validation logic
**Proposed:**
```
launchers/
  ├── builder.py (CommandBuilder - NEW)
  ├── handlers/
  │   ├── base.py (LaunchHandlerBase - NEW)
  │   ├── nuke.py (NukeLaunchHandler refactored)
  │   ├── maya.py, threede.py (app-specific)
  └── controller.py (use builder)
```
**Benefit:** 150+ LOC consolidated, reusable validation

---

## Implementation Phases (Quick View)

| Phase | Duration | Effort | Key Deliverables | Risk | Impact |
|-------|----------|--------|------------------|------|--------|
| 1: Foundation | 2 weeks | 20h | FileSystemDiscoveryBase, CommandBuilder, ProgressManager | LOW | HIGH |
| 2: Finders | 2 weeks | 15h | 3 refactored finders, -210 LOC | LOW | HIGH |
| 3: Models | 2 weeks | 16h | Unified model hierarchy, -350 LOC | MEDIUM | HIGH |
| 4: Item Models | 1 week | 6h | Role configuration, -70 LOC | LOW | MEDIUM |
| 5: Workers | 1 week | 8h | Unified progress tracking, -80 LOC | LOW | MEDIUM |
| 6: Launchers | 1 week | 14h | Handler base class, -150 LOC | MEDIUM | MEDIUM |
| 7: Testing | 1 week | 10h | Full regression testing | LOW | CRITICAL |

**Total: ~90 hours (2-3 weeks for one developer)**

---

## Critical Files to Update

### Create (NEW)
- `discovery/base.py` - FileSystemDiscoveryBase
- `models/base.py` - UnifiedModelBase[T]
- `launchers/builder.py` - CommandBuilder
- `launchers/handlers/base.py` - LaunchHandlerBase

### Refactor (EXISTING)
- `raw_plate_finder.py` - Use FileSystemDiscoveryBase
- `undistortion_finder.py` - Use FileSystemDiscoveryBase
- `threede_scene_model.py` - Inherit UnifiedModelBase
- `previous_shots_model.py` - Inherit UnifiedModelBase
- `threede_item_model.py` - Use role configuration
- `nuke_launch_handler.py` - Use CommandBuilder
- `progress_manager.py` - Enhance with worker support
- `utils.py` - Split into utils/ submodules
- `version_mixin.py` - DELETE (merge into VersionUtils)

### Verify (TESTING)
- All 1,919 unit tests pass
- Zero type checking errors (basedpyright)
- Zero new lint issues (ruff)
- Integration tests for new abstractions
- Performance regression testing

---

## Quick Start: What to Read First

1. **Overview:** Read "Executive Summary" section
2. **Decisions:** Review "Top 10 Overlapping Responsibilities"
3. **Impact:** Check "Part 2: Duplicate Code Analysis" for specific line counts
4. **Strategy:** See "Part 5: Consolidation Roadmap" for prioritization
5. **Architecture:** Study "Part 4: Module Restructuring Suggestions"

---

## One-Page Summary

**Problem:** 1,500-2,000 LOC of duplicated code across discovery, models, and launcher components  
**Root Cause:** Missing abstractions (FileSystemDiscoveryBase, UnifiedModelBase, CommandBuilder)  
**Solution:** 7-phase refactoring creating 4 reusable abstractions  
**Effort:** 90 hours (2-3 person-weeks)  
**Benefit:** 20-25% code reduction, 15-25% maintainability improvement  
**Risk:** LOW (1,919 passing tests provide safety net)  
**Start:** Create FileSystemDiscoveryBase first (4 hours, high ROI)

---

## File Locations

- **Full Analysis:** `/mnt/c/CustomScripts/Python/PyFFMPEG/BB/shotbot/CODEBASE_CONSOLIDATION_ANALYSIS.md`
- **This Quick Ref:** `/mnt/c/CustomScripts/Python/PyFFMPEG/BB/shotbot/CONSOLIDATION_QUICK_REFERENCE.md`

---

Generated: 2025-11-01 | Analysis Scope: 1,000+ Python files | Test Coverage: 1,919 passing tests
