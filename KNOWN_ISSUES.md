# Known Issues and Solutions

This document describes known issues in ShotBot and their solutions or workarounds.

## Nuke OCIO Plugin Crashes

### Issue
When launching Nuke, it crashes during startup with errors like:
```
/software/bluebolt/rez/packages/bluebolt/nuke_tools/4.0.0rc9/python-3.11/init/nuke_init_ocio.py : error interpreting this plugin
```

### Cause
This error occurs when Nuke tries to load OCIO (OpenColorIO) plugins from the rez environment that have compatibility issues with the current Python version or Nuke build, causing Nuke to crash completely.

### Impact
- **Severity**: Critical - Prevents Nuke from starting
- **Functional Impact**: Complete - Nuke cannot be launched
- **Performance Impact**: Total application failure

### Solutions

1. **Automatic Environment Fixes (Implemented)**
   - ShotBot automatically applies environment fixes when launching Nuke
   - Problematic plugin paths are filtered out of `NUKE_PATH`
   - OCIO configuration is set to a safe fallback or unset to use Nuke's built-in default
   - Crash reporting is disabled to prevent hanging on failure

2. **Update Rez Package (Long-term)**
   - Contact the VFX pipeline team to update the bluebolt nuke_tools package
   - Request a version compatible with Python 3.11 and current Nuke builds

3. **Manual Environment Fix**
   - Export environment variables before launching Nuke:
   ```bash
   export NUKE_PATH="/path/to/safe/plugins"  # Exclude problematic paths
   unset OCIO  # Use Nuke's built-in OCIO configuration
   export NUKE_DISABLE_CRASH_REPORTING=1
   nuke
   ```

### Configuration Options

```python
# In config.py
NUKE_FIX_OCIO_CRASH = True                    # Enable automatic crash prevention
NUKE_SKIP_PROBLEMATIC_PLUGINS = True          # Filter out problematic plugin paths
NUKE_PROBLEMATIC_PLUGIN_PATHS = [             # Paths to exclude from NUKE_PATH
    "/software/bluebolt/rez/packages/bluebolt/nuke_tools/4.0.0rc9/python-3.11/init",
]
NUKE_OCIO_FALLBACK_CONFIG = "/usr/share/color/nuke-default/config.ocio"  # Fallback OCIO
```

### How the Fix Works

When launching Nuke, ShotBot automatically:
1. **Filters NUKE_PATH**: Removes directories containing problematic plugins
2. **Sets OCIO Configuration**: Uses a fallback OCIO config or unsets it entirely
3. **Disables Crash Reporting**: Prevents Nuke from hanging on crash
4. **Sets Safe Temp Directories**: Ensures accessible cache and temp locations

This allows Nuke to start successfully while avoiding the problematic OCIO plugin.

## Persistent Terminal FIFO Errors

### Issue
```
Failed to send command to FIFO: [Errno 2] No such file or directory: '/tmp/shotbot_commands.fifo'
```

### Cause
The FIFO (named pipe) used for persistent terminal communication gets deleted by system cleanup or the terminal dispatcher stops running.

### Solution
- **Automatic Recovery**: ShotBot now automatically recreates missing FIFOs
- **Fallback**: Commands automatically fall back to new terminal windows if persistent terminal fails
- **Manual Fix**: Restart ShotBot to reinitialize the persistent terminal system

## Threading Executor Timeouts

### Issue
```
threading_utils - WARNING - Executor shutdown timeout after 5.0s, some threads may still be running
```

### Cause
Background threads (usually filesystem scanning or thumbnail processing) don't complete within the shutdown timeout.

### Solution
- **Reduced Severity**: Warning level lowered to debug to reduce noise
- **Improved Cleanup**: ProcessPoolManager now uses proper timeouts
- **No Action Needed**: These warnings are usually harmless and indicate background cleanup

## Performance Recommendations

### Large Shot Counts
- For shows with >500 shots, consider increasing cache TTL values
- Monitor memory usage during initial thumbnail loading
- Use mock mode for development when possible

### Network File Systems
- Increase subprocess timeouts if working over slow network filesystems
- Consider local caching for frequently accessed shots
- Monitor process pool performance metrics

## Getting Help

1. **Check Logs**: `~/.shotbot/logs/shotbot.log` contains detailed debugging information
2. **Debug Mode**: Run with `SHOTBOT_DEBUG=1 python shotbot.py` for verbose output
3. **Mock Mode**: Test functionality with `python shotbot.py --mock` to isolate environment issues
4. **Issue Reporting**: Include relevant log excerpts when reporting issues

## Environment-Specific Notes

### WSL (Windows Subsystem for Linux)
- Ensure X11 forwarding is configured for GUI applications
- Some terminal emulators may not be available - ShotBot will try multiple options

### Rez Environments
- Verify rez packages are compatible with Python 3.11+
- Check that workspace (`ws`) command is available in the rez environment
- Monitor rez package loading times for performance optimization