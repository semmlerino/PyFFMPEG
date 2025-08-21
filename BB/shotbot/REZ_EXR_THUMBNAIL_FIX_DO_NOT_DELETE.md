# Rez EXR Thumbnail Processing Fix - DO NOT DELETE

## Date: 2025-08-20

## Problem Analysis

### Original Issue
EXR thumbnails failing to generate with errors:
```
2025-08-20 11:28:57 - cache.thumbnail_processor - DEBUG - OpenEXR not available
2025-08-20 11:28:57 - cache.thumbnail_processor - DEBUG - imageio loading failed: Could not find a backend
2025-08-20 11:28:57 - cache.thumbnail_processor - DEBUG - PIL loading failed: cannot identify image file
```

### Root Cause Discovery

**Initial Assumption**: Missing Python packages (`OpenEXR`, `imageio`)

**Actual Root Cause**: **Rez Package Management Environment**

The user runs ShotBot using Rez package management:
```bash
rez env PySide6_Essentials pillow psutil imageio openexr Jinja2 -- SHOTBOT_DEBUG_LEVEL=all python3 shotbot.py
```

**Key Insight**: In Rez environments, package imports are determined by how the Rez packages are configured, not the original PyPI package names.

### The Problem

1. **Rez `openexr` package** exists but may provide different import name than expected
   - Code expects: `import OpenEXR` (uppercase, official package style)
   - Rez may provide: `import openexr` (lowercase, alternative style)
   - Or package configuration may be broken

2. **Rez `imageio` package** lacks EXR backends
   - Basic imageio available but missing `imageio[opencv]` or `imageio[pyav]` plugins
   - EXR backend detection fails

## Solution Strategy

### Phase 1: Rez Environment Diagnosis
- Add comprehensive Rez environment inspection
- Check `REZ_*` environment variables
- Test multiple import patterns
- Diagnose package availability

### Phase 2: Dual Import Strategy  
- Try both `import OpenEXR` and `import openexr`
- Detect which package is available and adapt API usage
- Handle different package APIs gracefully

### Phase 3: Enhanced Error Reporting
- VFX-pipeline specific error messages
- Clear guidance for Rez package issues
- Debugging information for pipeline teams

## Implementation Details

### Completed Changes

#### 1. Rez Environment Diagnostics (`_get_rez_environment_info()`)
- **Environment Variable Detection**: Checks all `REZ_*` variables
- **Package Root Inspection**: `REZ_OPENEXR_ROOT`, `REZ_IMAGEIO_ROOT` 
- **Resolved Package List**: `REZ_USED_RESOLVE` analysis
- **Python Path Verification**: Ensures packages are in `sys.path`

#### 2. Dual Import Strategy (`_load_exr_with_openexr()`)
```python
# Strategy 1: Official OpenEXR (uppercase)
try:
    import OpenEXR
    import Imath
    api_style = "official"
except ImportError:
    # Strategy 2: Alternative openexr (lowercase)
    try:
        import openexr
        import Imath  # or import imath as Imath
        api_style = "alternative" 
    except ImportError:
        # Enhanced Rez-specific error reporting
```

#### 3. Enhanced imageio Support (`_load_exr_with_imageio()`)
- **Version Fallback**: `imageio.v3` → `imageio` (v2)
- **Backend Detection**: Clear error messages for missing EXR plugins
- **Rez-Specific Guidance**: Suggests checking `imageio[opencv]` components

#### 4. Comprehensive Error Reporting
- **Environment Context**: Different messages for Rez vs non-Rez environments
- **Package Configuration Issues**: Specific guidance for misconfigured Rez packages
- **Backend Availability**: Clear indication of missing EXR support components

### API Adaptation Features
- **Dynamic Module References**: Uses `openexr_module` and `imath_module` variables
- **Method Name Fallbacks**: `InputFile()` vs `File()` for different packages
- **Error Context Preservation**: Original errors with Rez-specific enhancement

## VFX Pipeline Impact

This fix ensures:
- ✅ **Rez Compatibility**: Works with both official and alternative OpenEXR packages
- ✅ **Studio Integration**: No changes needed to existing Rez package configurations  
- ✅ **Clear Diagnostics**: VFX teams get actionable error messages
- ✅ **Universal Support**: Works in both Rez and non-Rez environments
- ✅ **Graceful Degradation**: Proper fallback when EXR support unavailable

## Testing Requirements

1. **Rez Environment Testing**: Test with actual studio Rez setup ✅
2. **Package Variation Testing**: Test with different OpenEXR package configurations ✅  
3. **Error Reporting Testing**: Verify clear error messages for troubleshooting ✅
4. **Fallback Testing**: Ensure graceful degradation when EXR support unavailable ✅

## Expected Log Output

### Success Case (Rez Environment)
```
DEBUG - Rez OpenEXR package detected at: /path/to/rez/openexr/1.0.0
DEBUG - Using alternative openexr package (lowercase)
DEBUG - Successfully loaded EXR using alternative OpenEXR API
```

### Diagnostic Case (Configuration Issue)
```
WARNING - OpenEXR import failed in Rez environment (package at /path/to/rez/openexr/1.0.0): No module named 'OpenEXR'
WARNING - imageio missing EXR backends (Rez imageio package needs EXR plugins - check if imageio[opencv] components are included)
ERROR - All EXR backends failed in Rez environment. Check package configurations for: ['openexr-1.0.0', 'imageio-2.22.0']
```

---
**Status**: ✅ **Implementation Complete**
**Deployed**: Rez-aware EXR processing with comprehensive diagnostics