# Shot Model Migration Plan to ProcessPoolManager

## Executive Summary

This document outlines the migration strategy for `shot_model.py` to use the new `ProcessPoolManager` for all subprocess operations. The migration will improve performance through command caching, session reuse, and reduce subprocess overhead.

## Current State Analysis

### Subprocess Calls in shot_model.py

#### 1. Primary `ws -sg` Command (Line 207-213)
```python
# Current implementation
result = subprocess.run(
    ["/bin/bash", "-i", "-c", "ws -sg"],
    capture_output=True,
    text=True,
    timeout=Config.WS_COMMAND_TIMEOUT_SECONDS,
    env=os.environ.copy(),
)
```

**Characteristics:**
- Interactive bash required (`-i` flag) for shell function
- Timeout: 10 seconds (from Config)
- Returns workspace shot list
- Called on every refresh
- Output parsed to extract shot data

## Migration Strategy

### 1. Import ProcessPoolManager

```python
# Add to imports
from process_pool_manager import ProcessPoolManager

# In __init__ method
def __init__(self, cache_manager: Optional["CacheManager"] = None, load_cache: bool = True):
    # ... existing code ...
    self._process_pool = ProcessPoolManager.get_instance()
```

### 2. Migrate `ws -sg` Command

#### Before (Current Implementation - Lines 206-273)
```python
def refresh_shots(self) -> RefreshResult:
    """Fetch and parse shot list from ws -sg command."""
    try:
        # Save current shots for comparison
        old_shot_data = {
            (shot.full_name, shot.workspace_path) for shot in self.shots
        }

        # Run ws -sg command in interactive bash shell
        result = subprocess.run(
            ["/bin/bash", "-i", "-c", "ws -sg"],
            capture_output=True,
            text=True,
            timeout=Config.WS_COMMAND_TIMEOUT_SECONDS,
            env=os.environ.copy(),
        )

        if result.returncode != 0:
            error_msg = f"ws -sg command failed with return code {result.returncode}"
            if result.stderr:
                error_msg += f": {result.stderr.strip()}"
            logger.error(error_msg)
            return RefreshResult(success=False, has_changes=False)

        # Parse output
        try:
            new_shots = self._parse_ws_output(result.stdout)
        except ValueError as e:
            logger.error(f"Failed to parse ws -sg output: {e}")
            return RefreshResult(success=False, has_changes=False)

        # ... rest of the method ...
```

#### After (ProcessPoolManager Implementation)
```python
def refresh_shots(self) -> RefreshResult:
    """Fetch and parse shot list from ws -sg command.
    
    Uses ProcessPoolManager for optimized command execution with:
    - Command caching (30-second TTL for workspace commands)
    - Persistent bash session reuse
    - Automatic retry on session failure
    """
    try:
        # Save current shots for comparison
        old_shot_data = {
            (shot.full_name, shot.workspace_path) for shot in self.shots
        }

        # Execute workspace command through ProcessPoolManager
        # 30-second cache TTL is appropriate for workspace commands
        # as shot assignments change infrequently
        try:
            output = self._process_pool.execute_workspace_command(
                "ws -sg",
                cache_ttl=30  # Cache for 30 seconds
            )
        except TimeoutError as e:
            logger.error(f"Timeout while running ws -sg command: {e}")
            return RefreshResult(success=False, has_changes=False)
        except RuntimeError as e:
            # Handle session failures and other runtime errors
            logger.error(f"Failed to execute ws -sg command: {e}")
            return RefreshResult(success=False, has_changes=False)

        # Parse output (reuse existing parser)
        try:
            new_shots = self._parse_ws_output(output)
        except ValueError as e:
            logger.error(f"Failed to parse ws -sg output: {e}")
            return RefreshResult(success=False, has_changes=False)

        new_shot_data = {
            (shot.full_name, shot.workspace_path) for shot in new_shots
        }

        # Check if there are changes
        has_changes = old_shot_data != new_shot_data

        if has_changes:
            self.shots = new_shots
            logger.info(f"Shot list updated: {len(new_shots)} shots found")

            # Cache the results
            if self.shots:
                try:
                    self.cache_manager.cache_shots(self.shots)
                except (OSError, IOError) as e:
                    logger.warning(f"Failed to cache shots: {e}")

        return RefreshResult(success=True, has_changes=has_changes)

    except Exception as e:
        logger.exception(f"Unexpected error while fetching shots: {e}")
        return RefreshResult(success=False, has_changes=False)
```

### 3. Add Cache Invalidation Support

```python
def invalidate_workspace_cache(self):
    """Invalidate workspace command cache.
    
    Useful when shot assignments have changed and immediate
    refresh is needed without waiting for cache TTL.
    """
    self._process_pool.invalidate_cache("ws -sg")
    logger.info("Invalidated workspace cache")
```

### 4. Add Performance Metrics Method

```python
def get_performance_metrics(self) -> Dict[str, Any]:
    """Get performance metrics for subprocess operations.
    
    Returns:
        Dictionary containing:
        - subprocess_calls: Total subprocess calls made
        - cache_hits: Number of cache hits
        - cache_misses: Number of cache misses
        - average_response_ms: Average command execution time
        - cache_hit_rate: Percentage of requests served from cache
    """
    return self._process_pool.get_metrics()
```

### 5. Cleanup on Deletion

```python
def __del__(self):
    """Cleanup when model is destroyed."""
    # Note: ProcessPoolManager is a singleton and manages its own lifecycle
    # We don't shut it down here as other components may be using it
    pass
```

## Cache TTL Recommendations

| Command | Current Frequency | Recommended TTL | Rationale |
|---------|------------------|-----------------|-----------|
| `ws -sg` | Every 5 minutes | 30 seconds | Balance between freshness and performance. Short enough to catch changes, long enough to benefit from caching during rapid UI interactions |

## Integration Points

### 1. Signal Connections
The ProcessPoolManager emits signals that can be connected for monitoring:

```python
# In MainWindow or monitoring component
pool = ProcessPoolManager.get_instance()
pool.command_completed.connect(self.on_command_completed)
pool.command_failed.connect(self.on_command_failed)

def on_command_completed(self, command: str, result: object):
    """Handle successful command completion."""
    if "ws -sg" in command:
        self.status_bar.showMessage("Workspace data refreshed from cache" 
                                   if "cached" in str(result) else 
                                   "Workspace data fetched")

def on_command_failed(self, command: str, error: str):
    """Handle command failure."""
    logger.error(f"Command failed: {command} - {error}")
    self.status_bar.showMessage(f"Failed to execute: {command}")
```

### 2. Manual Cache Control
For UI actions that need immediate fresh data:

```python
# In refresh button handler
def on_force_refresh(self):
    """Force refresh without cache."""
    self.shot_model.invalidate_workspace_cache()
    result = self.shot_model.refresh_shots()
    # ... handle result ...
```

## Backward Compatibility

### 1. RefreshResult Return Type
The return type remains unchanged - still returns `RefreshResult(success, has_changes)`.

### 2. Error Handling
All existing error paths are preserved with similar logging:
- Timeout errors
- Command failures  
- Parse errors
- Unexpected exceptions

### 3. Signal Emissions
The model continues to work with existing signals and doesn't require changes to consumers.

## Testing Strategy

### 1. Unit Tests
Update existing tests to mock ProcessPoolManager:

```python
@patch('shot_model.ProcessPoolManager.get_instance')
def test_refresh_shots_with_pool_manager(mock_get_instance):
    """Test shot refresh using ProcessPoolManager."""
    mock_pool = MagicMock()
    mock_pool.execute_workspace_command.return_value = """
    workspace /shows/project/shots/seq01/shot01
    workspace /shows/project/shots/seq01/shot02
    """
    mock_get_instance.return_value = mock_pool
    
    model = ShotModel()
    result = model.refresh_shots()
    
    assert result.success
    assert len(model.shots) == 2
    mock_pool.execute_workspace_command.assert_called_once_with("ws -sg", cache_ttl=30)
```

### 2. Integration Tests
Test actual ProcessPoolManager integration:

```python
def test_shot_model_with_real_pool_manager():
    """Test shot model with real ProcessPoolManager."""
    model = ShotModel()
    
    # First call - cache miss
    result1 = model.refresh_shots()
    metrics1 = model.get_performance_metrics()
    
    # Second call - should hit cache
    result2 = model.refresh_shots()
    metrics2 = model.get_performance_metrics()
    
    assert metrics2["cache_stats"]["hits"] > metrics1["cache_stats"]["hits"]
```

### 3. Performance Tests
Measure improvement:

```python
def test_performance_improvement():
    """Verify performance improvement with ProcessPoolManager."""
    model = ShotModel()
    
    # Measure 10 consecutive refreshes
    start = time.time()
    for _ in range(10):
        model.refresh_shots()
    elapsed_with_pool = time.time() - start
    
    # Compare with expected improvement
    # With caching, should be at least 5x faster
    assert elapsed_with_pool < 2.0  # Should complete in under 2 seconds
```

## Migration Steps

1. **Phase 1: Add ProcessPoolManager** (Low Risk)
   - Import ProcessPoolManager
   - Initialize in `__init__`
   - Add metrics method

2. **Phase 2: Migrate ws -sg Command** (Medium Risk)
   - Replace subprocess.run with ProcessPoolManager
   - Maintain all error handling
   - Add cache invalidation method

3. **Phase 3: Testing & Validation** (Required)
   - Run all existing tests
   - Add new integration tests
   - Performance benchmarking

4. **Phase 4: Monitor in Production**
   - Watch metrics for cache hit rate
   - Monitor error rates
   - Tune cache TTL if needed

## Expected Benefits

### Performance Improvements
- **Subprocess Calls Reduction**: ~90% reduction from caching
- **Response Time**: <10ms for cached responses (vs 500-1000ms for subprocess)
- **Session Reuse**: Eliminates bash startup overhead (~100ms per call)

### Resource Usage
- **Process Creation**: Reduced by ~90%
- **Memory**: Slight increase for cache storage (~1MB)
- **CPU**: Lower overall usage from fewer process spawns

### User Experience
- **Faster UI Updates**: Instant response for cached data
- **Smoother Interactions**: No UI freezing during refresh
- **Better Responsiveness**: Parallel execution capability

## Risk Mitigation

### 1. Cache Staleness
- **Risk**: Cached data may be outdated
- **Mitigation**: 30-second TTL ensures reasonable freshness
- **Control**: Manual invalidation available for force refresh

### 2. Session Failures
- **Risk**: Persistent bash session might die
- **Mitigation**: Automatic session restart in ProcessPoolManager
- **Fallback**: Direct subprocess execution if pool fails

### 3. Memory Growth
- **Risk**: Cache could grow unbounded
- **Mitigation**: Automatic cleanup of expired entries
- **Monitoring**: Metrics track cache size

## Code Example: Complete Migration

```python
"""Shot data model with ProcessPoolManager integration."""

import logging
from typing import Dict, Any, List, Optional
from process_pool_manager import ProcessPoolManager
from config import Config

logger = logging.getLogger(__name__)

class ShotModel:
    """Shot model with optimized subprocess handling."""
    
    def __init__(self, cache_manager: Optional["CacheManager"] = None, load_cache: bool = True):
        from cache_manager import CacheManager
        
        self.shots: List[Shot] = []
        self.cache_manager = cache_manager or CacheManager()
        self._parse_pattern = re.compile(r"workspace\s+(/shows/(\w+)/shots/(\w+)/(\w+))")
        
        # Initialize ProcessPoolManager singleton
        self._process_pool = ProcessPoolManager.get_instance()
        
        if load_cache:
            self._load_from_cache()
    
    def refresh_shots(self) -> RefreshResult:
        """Fetch shots using ProcessPoolManager with caching."""
        try:
            # Track current state
            old_shot_data = {(shot.full_name, shot.workspace_path) for shot in self.shots}
            
            # Execute through pool manager with caching
            try:
                output = self._process_pool.execute_workspace_command(
                    "ws -sg",
                    cache_ttl=30
                )
            except (TimeoutError, RuntimeError) as e:
                logger.error(f"Command execution failed: {e}")
                return RefreshResult(success=False, has_changes=False)
            
            # Parse and compare
            try:
                new_shots = self._parse_ws_output(output)
            except ValueError as e:
                logger.error(f"Parse error: {e}")
                return RefreshResult(success=False, has_changes=False)
            
            new_shot_data = {(shot.full_name, shot.workspace_path) for shot in new_shots}
            has_changes = old_shot_data != new_shot_data
            
            if has_changes:
                self.shots = new_shots
                logger.info(f"Updated {len(new_shots)} shots")
                self._cache_to_disk()
            
            return RefreshResult(success=True, has_changes=has_changes)
            
        except Exception as e:
            logger.exception(f"Unexpected error: {e}")
            return RefreshResult(success=False, has_changes=False)
    
    def invalidate_workspace_cache(self):
        """Force cache invalidation for immediate refresh."""
        self._process_pool.invalidate_cache("ws -sg")
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get subprocess performance metrics."""
        return self._process_pool.get_metrics()
    
    # ... rest of existing methods remain unchanged ...
```

## Conclusion

The migration to ProcessPoolManager provides significant performance improvements while maintaining full backward compatibility. The changes are isolated to the subprocess execution layer, preserving all existing interfaces and behavior. The 30-second cache TTL for workspace commands provides an optimal balance between data freshness and performance gains.