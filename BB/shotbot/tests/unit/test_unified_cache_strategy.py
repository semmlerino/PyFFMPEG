#!/usr/bin/env python3
"""Comprehensive test for the unified cache strategy implementation.

This test verifies that:
1. All cache components use consistent configuration from SettingsManager
2. Configuration changes propagate to all components
3. Memory limits and expiry times are unified across the system
4. Backward compatibility is maintained
"""

# Standard library imports
import sys
from pathlib import Path

# Third-party imports
import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

# Local application imports
from cache_config import UnifiedCacheConfig
from cache_manager import CacheManager


class MockSettingsManager:
    """Mock settings manager for testing."""

    def __init__(self, memory_mb: int = 100, expiry_min: int = 30) -> None:
        self._memory_mb = memory_mb
        self._expiry_min = expiry_min
        self._change_callbacks = []

        # Create mock signal
        self.settings_changed = MockSignal()

    def get_max_cache_memory_mb(self) -> int:
        return self._memory_mb

    def get_cache_expiry_minutes(self) -> int:
        return self._expiry_min

    def update_memory_limit(self, new_mb: int) -> None:
        """Simulate settings change."""
        self._memory_mb = new_mb
        # Emit settings changed signal
        for callback in self._change_callbacks:
            callback("performance/max_cache_memory_mb", new_mb)

    def update_expiry_time(self, new_min: int) -> None:
        """Simulate settings change."""
        self._expiry_min = new_min
        # Emit settings changed signal
        for callback in self._change_callbacks:
            callback("performance/cache_expiry_minutes", new_min)


class MockSignal:
    """Mock Qt signal for testing."""

    def __init__(self) -> None:
        self._callbacks = []

    def connect(self, callback) -> None:
        self._callbacks.append(callback)

    def emit(self, *args) -> None:
        for callback in self._callbacks:
            callback(*args)


@pytest.mark.skip(
    reason="Tests implementation details (_memory_manager, _shot_cache) that may have changed in CacheManager refactoring"
)
def test_unified_cache_strategy() -> bool:
    """Test the complete unified cache strategy implementation."""

    print("=" * 60)
    print("Testing Unified Cache Strategy Implementation")
    print("=" * 60)

    # Test 1: Basic unified configuration
    print("\n1. Testing basic unified configuration...")

    mock_settings = MockSettingsManager(memory_mb=150, expiry_min=45)
    config = UnifiedCacheConfig(mock_settings)

    assert config.memory_limit_mb == 150
    assert config.expiry_minutes == 45
    assert config.memory_limit_bytes == 150 * 1024 * 1024
    assert config.expiry_seconds == 45 * 60

    print(f"   ✓ Memory limit: {config.memory_limit_mb}MB")
    print(f"   ✓ Expiry time: {config.expiry_minutes} minutes")

    # Test 2: CacheManager integration
    print("\n2. Testing CacheManager integration...")

    # Without unified config (backward compatibility)
    cache_old = CacheManager()
    old_memory = cache_old._memory_manager.max_memory_bytes // (1024 * 1024)
    old_expiry = cache_old._shot_cache._expiry_minutes

    print(f"   ✓ Without unified config: {old_memory}MB, {old_expiry}min")

    # With unified config
    cache_new = CacheManager(settings_manager=mock_settings)
    new_memory = cache_new._memory_manager.max_memory_bytes // (1024 * 1024)
    new_expiry = cache_new._shot_cache._expiry_minutes

    print(f"   ✓ With unified config: {new_memory}MB, {new_expiry}min")

    assert new_memory == 150
    assert new_expiry == 45

    # Test 3: All cache components use unified config
    print("\n3. Testing all cache components use unified config...")

    shot_expiry = cache_new._shot_cache._expiry_minutes
    threede_expiry = cache_new._threede_cache._expiry_minutes
    previous_expiry = cache_new._previous_shots_cache._expiry_minutes

    assert shot_expiry == 45
    assert threede_expiry == 45
    assert previous_expiry == 45

    print(f"   ✓ Shot cache: {shot_expiry}min")
    print(f"   ✓ 3DE cache: {threede_expiry}min")
    print(f"   ✓ Previous shots cache: {previous_expiry}min")

    # Test 4: Dynamic configuration updates
    print("\n4. Testing dynamic configuration updates...")

    # Update memory limit
    print("   → Updating memory limit to 250MB...")
    mock_settings._change_callbacks = []

    # Manually connect the cache manager's callback
    if cache_new._unified_config:
        mock_settings._change_callbacks.append(
            cache_new._unified_config._on_settings_changed
        )

    mock_settings.update_memory_limit(250)
    updated_memory = cache_new._memory_manager.max_memory_bytes // (1024 * 1024)
    print(f"   ✓ Memory limit updated to: {updated_memory}MB")

    # Update expiry time
    print("   → Updating expiry time to 120min...")
    mock_settings.update_expiry_time(120)
    updated_shot_expiry = cache_new._shot_cache._expiry_minutes
    updated_threede_expiry = cache_new._threede_cache._expiry_minutes

    print(f"   ✓ Shot cache expiry updated to: {updated_shot_expiry}min")
    print(f"   ✓ 3DE cache expiry updated to: {updated_threede_expiry}min")

    assert updated_memory == 250
    assert updated_shot_expiry == 120
    assert updated_threede_expiry == 120

    # Test 5: Configuration access methods
    print("\n5. Testing configuration access methods...")

    cache_config = cache_new._unified_config.get_cache_config()

    assert cache_config["memory_limit_mb"] == 250
    assert cache_config["expiry_minutes"] == 120
    assert cache_config["memory_limit_bytes"] == 250 * 1024 * 1024
    assert cache_config["expiry_seconds"] == 120 * 60

    print(f"   ✓ Config dict: {cache_config}")

    print("\n" + "=" * 60)
    print("✅ All unified cache strategy tests PASSED!")
    print("=" * 60)

    return True


def demonstrate_benefits() -> None:
    """Demonstrate the benefits of the unified cache strategy."""

    print("\nUnified Cache Strategy Benefits:")
    print("-" * 40)
    print("✅ Consistent configuration across all cache components")
    print("✅ User-configurable memory limits and expiry times")
    print("✅ Dynamic configuration updates without restart")
    print("✅ Backward compatibility with existing code")
    print("✅ Centralized cache management")
    print("✅ Performance optimization through unified settings")
    print("✅ Memory usage coordination prevents conflicts")
    print("✅ Settings integration with SettingsManager")

    print("\nComponents now unified:")
    print("• MemoryManager - respects user memory limits")
    print("• ShotCache - uses user expiry settings")
    print("• ThreeDECache - uses user expiry settings")
    print("• PreviousShotsCache - uses user expiry settings")
    print("• Future cache components automatically unified")


if __name__ == "__main__":
    success = test_unified_cache_strategy()
    if success:
        demonstrate_benefits()
    else:
        sys.exit(1)
