# PathUtils Split Plan

**Date**: 2025-11-12
**Task**: Split 870-line PathUtils into 3-4 focused modules

## Current Structure

**PathUtils** (lines 193-1062, 870 lines total)

### Method Analysis

Based on code inspection, here are all PathUtils methods grouped by responsibility:

#### Group 1: Path Builders (~100 lines, lines 197-295)
Methods that construct file/directory paths:
- `build_path()` - Generic path construction (lines 197-216)
- `build_thumbnail_path()` - Thumbnail directory paths (lines 219-245)
- `build_raw_plate_path()` - Raw plate paths (lines 271-281)
- `build_threede_scene_path()` - 3DE scene paths (lines 283-295)

#### Group 2: Thumbnail Finders (~600 lines, lines 248-739)
Methods that find thumbnail images:
- `find_turnover_plate_thumbnail()` - Turnover plate thumbnails (lines 248-269)
- `find_any_publish_thumbnail()` - Published thumbnails (lines 205-270)
- `find_undistorted_jpeg_thumbnail()` - Undistorted JPEG thumbnails (lines 458-541)
- `find_user_workspace_jpeg_thumbnail()` - User workspace thumbnails (lines 542-653)
- `find_shot_thumbnail()` - General shot thumbnails (lines 654-739)

#### Group 3: Path Validators (~120 lines, lines 297-434)
Methods for path validation and caching:
- `validate_path_exists()` - Single path validation with caching (lines 297-384)
- `_cleanup_path_cache()` - Cache cleanup (lines 357-384)
- `batch_validate_paths()` - Batch validation (lines 386-434)

#### Group 4: File Operations (~50 lines, lines 435-501, 740-870)
Remaining utilities:
- `safe_mkdir()` - Directory creation (lines 435-456)
- `find_mov_file_for_path()` - MOV file finding (lines 740-800)
- `discover_plate_directories()` - Plate directory discovery (lines 801-870)

## Splitting Strategy

### Module 1: `path_builders.py` (~150 lines)

**Contents**:
- All path construction methods
- Dependencies: Config, Path

```python
from pathlib import Path
from config import Config

class PathBuilders:
    \"\"\"Utilities for constructing VFX pipeline paths.\"\"\"

    @staticmethod
    def build_path(base_path: str | Path, *segments: str) -> Path:
        ...

    @staticmethod
    def build_thumbnail_path(...) -> Path:
        ...

    @staticmethod
    def build_raw_plate_path(workspace_path: str) -> Path:
        ...

    @staticmethod
    def build_threede_scene_path(workspace_path: str, username: str) -> Path:
        ...
```

### Module 2: `path_validators.py` (~180 lines)

**Contents**:
- Path validation and caching logic
- Module-level cache management
- Dependencies: Path, threading, time, logging

```python
from pathlib import Path
import threading
import time
from logging_mixin import get_module_logger

# Module-level cache
_path_cache: dict[str, tuple[bool, float]] = {}
_path_cache_lock = threading.Lock()
_PATH_CACHE_TTL = 0.0
_cache_disabled = False

class PathValidators:
    \"\"\"Utilities for path validation with caching.\"\"\"

    @staticmethod
    def validate_path_exists(path: str | Path, description: str = "Path") -> bool:
        ...

    @staticmethod
    def _cleanup_path_cache() -> None:
        ...

    @staticmethod
    def batch_validate_paths(paths: list[str | Path]) -> dict[str, bool]:
        ...

def clear_path_cache() -> None:
    \"\"\"Clear path validation cache.\"\"\"
    ...

def disable_path_caching() -> None:
    ...

def enable_path_caching() -> None:
    ...
```

### Module 3: `thumbnail_finders.py` (~650 lines)

**Contents**:
- All thumbnail finding methods
- Dependencies: Path, PathBuilders, PathValidators, FileUtils, VersionUtils, Config

```python
from pathlib import Path
from config import Config
from path_builders import PathBuilders
from path_validators import PathValidators
# Note: Will keep VersionUtils and FileUtils dependencies for now

class ThumbnailFinders:
    \"\"\"Utilities for finding thumbnail images in VFX pipeline.\"\"\"

    @staticmethod
    def find_turnover_plate_thumbnail(...) -> Path | None:
        ...

    @staticmethod
    def find_any_publish_thumbnail(...) -> Path | None:
        ...

    @staticmethod
    def find_undistorted_jpeg_thumbnail(...) -> Path | None:
        ...

    @staticmethod
    def find_user_workspace_jpeg_thumbnail(...) -> Path | None:
        ...

    @staticmethod
    def find_shot_thumbnail(...) -> Path | None:
        ...
```

### Module 4: `file_discovery.py` (~100 lines)

**Contents**:
- File and directory discovery utilities
- Dependencies: Path, PathValidators, Config

```python
from pathlib import Path
from config import Config
from path_validators import PathValidators

class FileDiscovery:
    \"\"\"Utilities for file and directory discovery.\"\"\"

    @staticmethod
    def safe_mkdir(path: str | Path, description: str = "Directory") -> bool:
        ...

    @staticmethod
    def find_mov_file_for_path(thumbnail_path: Path) -> Path | None:
        ...

    @staticmethod
    def discover_plate_directories(...) -> list[Path]:
        ...
```

### Module 5: `path_utils.py` (UPDATED, ~100 lines)

**Purpose**: Compatibility layer that re-exports everything

```python
\"\"\"Path utilities - compatibility layer.

DEPRECATED: Import from specific modules instead:
- path_builders.PathBuilders
- path_validators.PathValidators
- thumbnail_finders.ThumbnailFinders
- file_discovery.FileDiscovery
\"\"\"

import warnings
from path_builders import PathBuilders
from path_validators import PathValidators
from thumbnail_finders import ThumbnailFinders
from file_discovery import FileDiscovery

class PathUtils:
    \"\"\"DEPRECATED: Use specific modules instead.\"\"\"

    # Re-export all methods for backward compatibility
    build_path = PathBuilders.build_path
    build_thumbnail_path = PathBuilders.build_thumbnail_path
    build_raw_plate_path = PathBuilders.build_raw_plate_path
    build_threede_scene_path = PathBuilders.build_threede_scene_path

    validate_path_exists = PathValidators.validate_path_exists
    _cleanup_path_cache = PathValidators._cleanup_path_cache
    batch_validate_paths = PathValidators.batch_validate_paths

    find_turnover_plate_thumbnail = ThumbnailFinders.find_turnover_plate_thumbnail
    find_any_publish_thumbnail = ThumbnailFinders.find_any_publish_thumbnail
    find_undistorted_jpeg_thumbnail = ThumbnailFinders.find_undistorted_jpeg_thumbnail
    find_user_workspace_jpeg_thumbnail = ThumbnailFinders.find_user_workspace_jpeg_thumbnail
    find_shot_thumbnail = ThumbnailFinders.find_shot_thumbnail

    safe_mkdir = FileDiscovery.safe_mkdir
    find_mov_file_for_path = FileDiscovery.find_mov_file_for_path
    discover_plate_directories = FileDiscovery.discover_plate_directories
```

## Implementation Steps

### Phase 1: Create New Modules (2 hours)

1. **Create `path_builders.py`** (30 min)
   - Extract 4 path building methods
   - Add imports and documentation
   - Run: `basedpyright path_builders.py`

2. **Create `path_validators.py`** (30 min)
   - Extract 3 validation methods
   - Move module-level cache variables
   - Add cache management functions
   - Run: `basedpyright path_validators.py`

3. **Create `file_discovery.py`** (30 min)
   - Extract 3 file discovery methods
   - Update imports to use PathValidators
   - Run: `basedpyright file_discovery.py`

4. **Create `thumbnail_finders.py`** (30 min)
   - Extract 5 thumbnail finding methods
   - Update imports to use PathBuilders, PathValidators
   - Keep FileUtils and VersionUtils dependencies
   - Run: `basedpyright thumbnail_finders.py`

### Phase 2: Update utils.py (1 hour)

1. **Replace PathUtils in utils.py** (30 min)
   - Remove old PathUtils class
   - Create new PathUtils compatibility class
   - Re-export all methods from new modules
   - Run: `basedpyright utils.py`

2. **Update cache management in utils.py** (30 min)
   - Import cache functions from path_validators
   - Update `clear_all_caches()` to call new functions
   - Update `disable_caching()`/`enable_caching()`

### Phase 3: Testing (1 hour)

1. **Run targeted tests** (30 min)
   ```bash
   pytest tests/unit/test_utils.py -v
   pytest tests/unit/test_utils_extended.py -v
   ```

2. **Run full test suite** (30 min)
   ```bash
   pytest tests/ -n auto --dist=loadgroup
   ```

### Phase 4: Update External Imports (Optional, 1-2 hours)

If time permits, update the 14 files that import PathUtils:
- Change `from utils import PathUtils` to more specific imports
- E.g., `from thumbnail_finders import ThumbnailFinders`
- Add deprecation warnings when using old imports

## Dependencies to Maintain

**Existing cross-module dependencies that WILL REMAIN**:

1. **ThumbnailFinders** needs:
   - `FileUtils.find_files_by_extension()`
   - `FileUtils.get_first_image_file()`
   - `VersionUtils.get_latest_version()`

2. **FileDiscovery** needs:
   - `PathValidators.validate_path_exists()`

3. **ThumbnailFinders** needs:
   - `PathBuilders.build_path()`
   - `PathValidators.validate_path_exists()`

These dependencies are FINE - we're not trying to eliminate all dependencies, just split PathUtils into logical modules.

## Success Criteria

1. ✅ All 4 new modules created
2. ✅ PathUtils compatibility layer works
3. ✅ 0 type errors (basedpyright)
4. ✅ All tests pass (2,641+ tests)
5. ✅ Backward compatibility maintained
6. ✅ Clear module responsibilities

## Rollback Plan

If anything goes wrong:
1. Revert all changes: `git checkout utils.py`
2. Delete new modules: `rm path_*.py thumbnail_finders.py file_discovery.py`
3. Run tests to confirm: `pytest tests/unit/test_utils.py`

## Estimated Time

- **Phase 1**: 2 hours (create modules)
- **Phase 2**: 1 hour (update utils.py)
- **Phase 3**: 1 hour (testing)
- **Phase 4**: 1-2 hours (optional updates)

**Total**: 4-6 hours (as estimated)
