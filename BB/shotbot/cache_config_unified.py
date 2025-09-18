"""Unified cache configuration system integrating SettingsManager with cache components.

This module provides a centralized configuration system that ensures all cache
components use consistent, user-configurable settings from SettingsManager.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal
from logging_mixin import LoggingMixin

if TYPE_CHECKING:
    from cache.memory_manager import MemoryManager
    from settings_manager import SettingsManager



class UnifiedCacheConfig(LoggingMixin, QObject):
    """Unified cache configuration that integrates with SettingsManager.

    This class provides a single point of configuration for all cache components,
    ensuring they use consistent user-configurable settings instead of hardcoded values.

    Signals:
        memory_limit_changed: Emitted when memory limit changes (int: new_limit_mb)
        expiry_time_changed: Emitted when expiry time changes (int: new_expiry_minutes)
        config_updated: Emitted when any cache configuration changes
    """

    # Signals for configuration changes
    memory_limit_changed = Signal(int)  # new_limit_mb
    expiry_time_changed = Signal(int)  # new_expiry_minutes
    config_updated = Signal()

    def __init__(self, settings_manager: SettingsManager) -> None:
        """Initialize unified cache config with settings manager.

        Args:
            settings_manager: The application's settings manager
        """
        super().__init__()
        self._settings_manager = settings_manager

        # Connect to settings changes
        self._settings_manager.settings_changed.connect(self._on_settings_changed)

        self.logger.debug("UnifiedCacheConfig initialized")

    @property
    def memory_limit_mb(self) -> int:
        """Get current memory limit in MB from user settings."""
        return self._settings_manager.get_max_cache_memory_mb()

    @property
    def memory_limit_bytes(self) -> int:
        """Get current memory limit in bytes from user settings."""
        return self.memory_limit_mb * 1024 * 1024

    @property
    def expiry_minutes(self) -> int:
        """Get current cache expiry time in minutes from user settings."""
        return self._settings_manager.get_cache_expiry_minutes()

    @property
    def expiry_seconds(self) -> int:
        """Get current cache expiry time in seconds from user settings."""
        return self.expiry_minutes * 60

    def get_memory_limit_mb(self) -> int:
        """Get memory limit in MB (method for backward compatibility)."""
        return self.memory_limit_mb

    def get_expiry_minutes(self) -> int:
        """Get expiry time in minutes (method for backward compatibility)."""
        return self.expiry_minutes

    def get_cache_config(self) -> dict[str, int]:
        """Get complete cache configuration dictionary.

        Returns:
            Dictionary with all cache configuration values
        """
        return {
            "memory_limit_mb": self.memory_limit_mb,
            "memory_limit_bytes": self.memory_limit_bytes,
            "expiry_minutes": self.expiry_minutes,
            "expiry_seconds": self.expiry_seconds,
        }

    def _on_settings_changed(self, setting_key: str, new_value: object) -> None:
        """Handle settings changes and emit appropriate signals.

        Args:
            setting_key: The settings key that changed
            new_value: The new value for the setting
        """
        if setting_key == "performance/max_cache_memory_mb":
            # Type narrowing for numeric values from QSettings
            if isinstance(new_value, (int, float, str)):
                self.logger.info(f"Cache memory limit changed to {new_value}MB")
                self.memory_limit_changed.emit(int(new_value))
                self.config_updated.emit()
        elif setting_key == "performance/cache_expiry_minutes":
            # Type narrowing for numeric values from QSettings
            if isinstance(new_value, (int, float, str)):
                self.logger.info(f"Cache expiry time changed to {new_value} minutes")
                self.expiry_time_changed.emit(int(new_value))
                self.config_updated.emit()

    def apply_to_memory_manager(self, memory_manager: MemoryManager) -> None:
        """Apply current settings to a MemoryManager instance.

        Args:
            memory_manager: MemoryManager instance to configure
        """
        memory_manager.set_memory_limit(self.memory_limit_mb)
        self.logger.debug(f"Applied memory limit {self.memory_limit_mb}MB to MemoryManager")

    def create_memory_manager(self) -> MemoryManager:
        """Create a MemoryManager with current unified settings.

        Returns:
            MemoryManager instance configured with current settings
        """
        from cache.memory_manager import MemoryManager

        return MemoryManager(max_memory_mb=self.memory_limit_mb)


# Global instance for easy access (initialized by CacheManager)
_unified_config: UnifiedCacheConfig | None = None


def get_unified_cache_config() -> UnifiedCacheConfig | None:
    """Get the global unified cache config instance.

    Returns:
        Global UnifiedCacheConfig instance or None if not initialized
    """
    return _unified_config


def set_unified_cache_config(config: UnifiedCacheConfig) -> None:
    """Set the global unified cache config instance.

    Args:
        config: UnifiedCacheConfig instance to set as global
    """
    global _unified_config
    _unified_config = config
    logger.debug("Global unified cache config set")


def create_unified_cache_config(
    settings_manager: SettingsManager,
) -> UnifiedCacheConfig:
    """Create and set the global unified cache config.

    Args:
        settings_manager: Settings manager to use for configuration

    Returns:
        Created UnifiedCacheConfig instance
    """
    config = UnifiedCacheConfig(settings_manager)
    set_unified_cache_config(config)
    return config
