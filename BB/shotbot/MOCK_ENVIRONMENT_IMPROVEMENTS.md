# Mock Environment and Testing Improvements

This document summarizes the comprehensive improvements made to ShotBot's mock environment and testing infrastructure.

## Overview

Successfully created a complete mock VFX environment system that enables development and testing without requiring VFX infrastructure, including proper dependency injection, headless mode support, and cache isolation.

## Key Improvements

### 1. VFX Filesystem Capture and Recreation
**Problem:** Developers couldn't test without VFX infrastructure
**Solution:** Created tools to capture real VFX structure and recreate locally

**Files Created:**
- `capture_vfx_structure.py` - Captures directory structure from production VFX workstation
- `recreate_vfx_structure.py` - Recreates structure with placeholder files locally  
- `join_and_recreate.py` - Handles split JSON files for large captures
- `MOCK_ENVIRONMENT_SETUP.md` - Documentation for the process

**Features:**
- Auto-generates timestamped capture filenames
- Merges multiple JSON files (for transfers requiring splits)
- Creates placeholder thumbnails with gradients
- Mock 3DE scene files
- Symlinks for convenience
- Successfully recreated 11,386 directories and 31,377 files

### 2. Dependency Injection System for ProcessPoolManager
**Problem:** Direct singleton modification was fragile and order-dependent
**Solution:** Clean factory pattern with dependency injection

**Files Created:**
- `process_pool_factory.py` - Factory for creating/injecting ProcessPoolManager instances
- `test_dependency_injection.py` - Comprehensive tests for DI system

**Features:**
- Clean separation between production and mock implementations
- Support for custom implementations
- Maintains singleton behavior
- Full backward compatibility
- Three modes: production, mock, custom

**Updated Files:**
- `process_pool_manager.py` - Added factory support
- `base_shot_model.py` - Uses factory for DI
- `launcher_manager.py` - Uses factory for DI
- `main_window.py` - Uses factory for DI
- `shotbot.py` - Uses factory for mock mode
- `shotbot_mock.py` - Uses factory instead of direct injection

### 3. Headless Mode for CI/CD Testing
**Problem:** Tests couldn't run in CI/CD without display
**Solution:** Comprehensive headless mode with Qt offscreen platform

**Files Created:**
- `headless_mode.py` - Headless mode utilities and configuration
- `test_headless.py` - Tests for headless functionality

**Features:**
- Auto-detects CI environments (GitHub Actions, GitLab, Jenkins, etc.)
- Configures Qt for offscreen rendering
- Patches UI operations to be no-ops
- HeadlessMainWindow for testing without UI
- Decorators for conditional execution
- Command-line flag `--headless`

**Updated Files:**
- `shotbot.py` - Added --headless argument and headless mode support

### 4. Cache Directory Separation
**Problem:** Mock/test data could contaminate production cache
**Solution:** Mode-based cache directories

**Files Created:**
- `cache_config.py` - Cache configuration and directory management
- `test_cache_separation.py` - Tests for cache isolation

**Features:**
- Separate directories for production, mock, and test modes
- Automatic mode detection
- Cache migration utilities
- Cache info reporting
- Complete data isolation between modes

**Cache Directories:**
- Production: `~/.shotbot/cache`
- Mock: `~/.shotbot/cache_mock`
- Test: `~/.shotbot/cache_test`

**Updated Files:**
- `cache_manager.py` - Uses CacheConfig for directory selection

### 5. Enhanced Mock Mode Launcher
**Files Updated:**
- `shotbot_mock.py` - Now uses dependency injection and auto-detects recreated filesystem
- `demo_shots.json` - Real VFX show structure (gator, jack_ryan, broken_eggs)

**Features:**
- Auto-detects recreated VFX filesystem at `/tmp/mock_vfx`
- Sets SHOWS_ROOT environment variable
- Visual "MOCK MODE" indicator in UI
- Uses ProcessPoolFactory for clean injection

## Usage Examples

### Running in Mock Mode
```bash
# With recreated filesystem
python recreate_vfx_structure.py vfx_structure.json
./venv/bin/python shotbot_mock.py

# Or with flag
./venv/bin/python shotbot.py --mock
```

### Running in Headless Mode
```bash
# For CI/CD environments
./venv/bin/python shotbot.py --headless

# Or via environment
SHOTBOT_HEADLESS=1 ./venv/bin/python shotbot.py
```

### Capturing VFX Structure
```bash
# On VFX workstation
python capture_vfx_structure.py
# Creates: vfx_structure_hostname_20240315_143022.json

# Transfer and recreate locally
python recreate_vfx_structure.py vfx_structure_*.json
```

### Handling Split Files
```bash
# If file was split for transfer
python join_and_recreate.py vfxstructure1.json vfxstructure2.json
```

## Testing

All new features include comprehensive tests:

```bash
# Test dependency injection
./venv/bin/python test_dependency_injection.py

# Test headless mode
./venv/bin/python test_headless.py

# Test cache separation
./venv/bin/python test_cache_separation.py

# Test mock injection
./venv/bin/python test_mock_injection.py
```

## Benefits

✅ **Development without VFX infrastructure** - Work from anywhere  
✅ **CI/CD compatibility** - Tests run in GitHub Actions, GitLab CI, etc.  
✅ **Clean dependency injection** - No more brittle singleton manipulation  
✅ **Data isolation** - Mock/test data never contaminates production  
✅ **Realistic testing** - Uses actual production directory structure  
✅ **Backward compatible** - All existing code continues to work  

## Architecture Improvements

1. **Separation of Concerns**: Each system (DI, headless, cache) is independent
2. **Factory Pattern**: ProcessPoolFactory provides clean abstraction
3. **Mode Detection**: Automatic detection of mock/test/headless/CI modes
4. **Facade Pattern**: CacheManager maintains compatibility while using new architecture
5. **Protocol-Based Design**: ProcessPoolInterface ensures type safety

## Performance Impact

- No performance degradation in production mode
- Mock mode starts instantly (no ws command delays)
- Headless mode reduces resource usage
- Cache separation prevents cross-contamination slowdowns

## Future Enhancements

Potential future improvements:
- Mock data generator for various test scenarios
- Performance profiling in mock mode
- Integration with pytest fixtures
- Docker container with pre-built mock environment
- Mock network services for complete isolation