# Timeout Configuration Improvements

## Problem Identified

The timeouts in the ShotBot application were too aggressive for production VFX environments:
- Command execution: 30 seconds (too short for complex workspace operations)
- Process termination: 2-3 seconds (not enough time for graceful shutdown)
- File searches: 5-30 seconds (insufficient for large network filesystems)
- Application startup: 5 seconds (VFX applications often take longer)

These short timeouts were causing:
- Premature termination of valid operations
- False failures on slow network filesystems
- Applications being killed before fully starting
- Session recovery loops due to timeout errors

## Improvements Made

### 1. Command Execution Timeouts

**Before:**
- Default: 30 seconds
- No differentiation between command types

**After:**
- Workspace commands: **120 seconds** (2 minutes)
- Application launches: **300 seconds** (5 minutes)
- Simple commands: 30 seconds (unchanged)
- Heavy operations: **300 seconds** (5 minutes)

### 2. Process Termination Timeouts

**Before:**
- Graceful termination: 2-3 seconds
- Force kill: 1 second after

**After:**
- Graceful termination: **10 seconds**
- Force kill: **5 seconds** after terminate
- Process startup validation: **30 seconds** (was 5 seconds)

### 3. File Discovery Timeouts

**Before:**
- Quick check: 5 seconds
- Standard search: 30 seconds

**After:**
- Quick check: **15 seconds**
- Standard search: **120 seconds** (2 minutes)
- Deep recursive search: **300 seconds** (5 minutes)

### 4. Session Management

**Before:**
- Fixed 30-second timeout for all operations
- Quick recovery attempts causing loops

**After:**
- Default session commands: **120 seconds**
- Session recovery max wait: **30 seconds**
- Health check commands: 5 seconds

## New Centralized Configuration

Created `timeout_config.py` to centralize all timeout settings:

```python
from timeout_config import TimeoutConfig

# Get timeout for specific operation
timeout = TimeoutConfig.get_timeout_for_operation('workspace')

# Scale all timeouts for slower environment
TimeoutConfig.scale_timeouts(2.0)  # Double all timeouts

# Optimize for network latency
TimeoutConfig.optimize_for_network_latency(200)  # 200ms latency
```

## Environment Variables

Two new environment variables for runtime adjustment:

```bash
# Scale all timeouts by a factor
export SHOTBOT_TIMEOUT_SCALE=2.0  # Double all timeouts

# Optimize for network latency
export SHOTBOT_NETWORK_LATENCY_MS=200  # Adjust for 200ms latency
```

## Modified Files

1. **process_pool_manager.py**
   - `execute()`: 30s → 120s default timeout
   - `execute_workspace_command()`: Added timeout parameter (default 120s)
   - Process termination: 2s → 10s graceful, 5s force kill

2. **launcher_manager.py**
   - `PROCESS_STARTUP_TIMEOUT_MS`: 5000ms → 30000ms
   - Process wait timeouts: 0.5-3s → 1-10s
   - ProcessPool execution: Added 300s timeout for app launches

3. **threede_scene_finder.py**
   - Quick check: 5s → 15s
   - Standard search: 30s → 120s
   - Deep search: Added 300s option

4. **timeout_config.py** (NEW)
   - Centralized timeout configuration
   - Environment-based adjustment
   - Network latency optimization

## Benefits

### Reliability
- Fewer false failures on slow networks
- Applications have time to start properly
- Graceful shutdown prevents data corruption

### Flexibility
- Easily adjustable via environment variables
- Centralized configuration for maintenance
- Automatic network latency compensation

### Production Ready
- Timeouts appropriate for VFX scale
- Handles large file operations
- Supports heavy applications

## Usage Examples

### For Slow Network Environment
```bash
# Double all timeouts for slow network
export SHOTBOT_TIMEOUT_SCALE=2.0
python shotbot.py
```

### For High-Latency Network
```bash
# Optimize for 300ms network latency
export SHOTBOT_NETWORK_LATENCY_MS=300
python shotbot.py
```

### In Code
```python
from timeout_config import TimeoutConfig

# Use appropriate timeout for operation
timeout = TimeoutConfig.WORKSPACE_COMMAND_HEAVY  # 300 seconds

# Execute with custom timeout
result = process_pool.execute_workspace_command(
    command="complex_operation",
    timeout=timeout
)
```

## Monitoring

Monitor timeout-related issues with:
```python
# Check if operations are timing out
metrics = process_pool.get_metrics()
if 'timeout_errors' in metrics:
    print(f"Timeout errors: {metrics['timeout_errors']}")
    
# Get timeout configuration
print(TimeoutConfig.get_config_summary())
```

## Recommendations

1. **Start Conservative**: Use current settings and monitor
2. **Adjust Based on Environment**: Scale timeouts for your specific network/hardware
3. **Monitor and Tune**: Track timeout errors and adjust accordingly
4. **Document Changes**: Keep track of timeout adjustments for your environment

## Summary

The timeout improvements make ShotBot more robust and production-ready:
- **4x longer** command execution timeouts (30s → 120s)
- **3-5x longer** process termination grace period (2-3s → 10s)
- **4x longer** file search timeouts (30s → 120s)
- **6x longer** application startup validation (5s → 30s)

These changes ensure reliable operation in production VFX environments with:
- Large network filesystems
- Heavy applications
- Variable network latency
- Complex workspace operations