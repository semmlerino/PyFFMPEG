# Critical Fixes Applied - August 15, 2025

## 1. Fixed Temporary Folder Accumulation

### Problem
- `bundle_app.py` was creating random temporary directories (`/tmp/shotbot_bundle_XXXXX`)
- These accumulated over time if cleanup failed
- Could cause race conditions with simultaneous processes

### Solution
- Changed to use a fixed temporary directory name: `/tmp/shotbot_bundle_temp`
- Directory is cleaned and recreated on each run
- Prevents accumulation and race conditions

### Files Modified
- `bundle_app.py` (lines 289-295)

## 2. Fixed workspace_1 Session Hang

### Problem
- Second bash session (`workspace_1`) was hanging during initialization on Linux
- Insufficient delay between session creations causing resource contention

### Solution
- Increased delay between session creations from 0.1s to 0.3s
- Added variable delays based on session number (0.1s for first, 0.2s for subsequent)
- Added fallback initialization if marker not found
- Better error logging to show accumulated output on failure

### Files Modified
- `process_pool_manager.py`
  - Lines 279-284: Variable initialization delays
  - Lines 904-907: Increased inter-session delay to 0.3s
  - Lines 369-388: Added fallback initialization

## 3. Fixed Post-Commit Hook Output Directory

### Problem
- Post-commit hook was using wrong project root for nested repositories
- Output directory wasn't in the correct location

### Solution
- Changed from `git rev-parse --show-toplevel` to relative path resolution
- Directory now correctly placed in project root as `.post-commit-output/`

### Files Modified
- `.git/hooks/post-commit` (line 8)

## Testing Commands

Test the fixes with:

```bash
# Test session creation
python test_session_creation.py

# Test with verbose logging
SHOTBOT_DEBUG_VERBOSE=1 python shotbot.py

# Test bundle creation
python bundle_app.py -v

# Check temp directory
ls -la /tmp/shotbot_bundle_temp
```

## Key Improvements

1. **Predictable temp directories** - No more random folder accumulation
2. **More robust session initialization** - Better delays and fallback handling
3. **Enhanced debugging** - Shows accumulated output on initialization failure
4. **Fixed folder consistency** - Post-commit hook uses correct paths

## Next Steps

If issues persist:
1. Run with `SHOTBOT_DEBUG_VERBOSE=1` to get detailed logs
2. Check `/tmp/shotbot_bundle_temp` isn't locked by another process
3. Verify bash initialization completes within timeout (2 seconds)