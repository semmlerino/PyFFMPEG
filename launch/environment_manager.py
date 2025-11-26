"""Environment management for application launching.

This module handles environment detection and configuration:
- Rez package manager availability
- Rez package mapping for applications
- Terminal emulator detection
"""

import logging
import os
import shutil
import subprocess
import threading
import time
from typing import TYPE_CHECKING, Final


if TYPE_CHECKING:
    from config import Config


logger = logging.getLogger(__name__)


class EnvironmentManager:
    """Manages launch environment configuration.

    This class provides stateless functions for detecting and configuring
    the launch environment. It handles:
    - Rez availability checking
    - Rez package mapping
    - Terminal emulator detection with caching

    All methods are instance methods to support caching, but operate
    independently without requiring shared state.
    """

    # Terminal preference order (common VFX facility terminals)
    TERMINAL_PREFERENCE: Final[list[str]] = [
        "gnome-terminal",
        "konsole",
        "xfce4-terminal",
        "mate-terminal",
        "alacritty",
        "kitty",
        "terminology",
        "xterm",
        "x-terminal-emulator",
    ]

    # Cache TTL for terminal detection (5 minutes)
    TERMINAL_CACHE_TTL_SEC: Final[float] = 300.0

    def __init__(self) -> None:
        """Initialize EnvironmentManager with empty cache."""
        self._rez_available_cache: bool | None = None
        self._ws_available_cache: bool | None = None
        self._available_terminal_cache: str | None = None
        self._terminal_cache_time: float = 0.0

    def is_rez_available(self, config: "type[Config]") -> bool:
        """Check if rez environment is available and should be used for wrapping.

        Args:
            config: Application configuration

        Returns:
            True if rez is available and should be used for wrapping commands

        Notes:
            - Checks config.USE_REZ_ENVIRONMENT first
            - If REZ_AUTO_DETECT enabled and REZ_USED is set, returns False
              (already in a rez context, don't double-wrap)
            - Otherwise checks if 'rez' command is available
            - Caches result for performance
        """
        if not config.USE_REZ_ENVIRONMENT:
            return False

        # Check for REZ_USED environment variable (indicates we're already in a rez env)
        # Don't wrap again to avoid double-wrapping and package conflicts
        # Unless REZ_FORCE_WRAP is set (for base rez envs that need app packages added)
        if config.REZ_AUTO_DETECT and os.environ.get("REZ_USED") and not config.REZ_FORCE_WRAP:
            logger.debug("Already in rez environment (REZ_USED set), skipping rez wrapping")
            return False

        # Return cached result if available
        if self._rez_available_cache is not None:
            return self._rez_available_cache

        # Check if rez command is available
        self._rez_available_cache = shutil.which("rez") is not None
        logger.debug(f"Rez availability cached: {self._rez_available_cache}")
        return self._rez_available_cache

    def is_ws_available(self) -> bool:
        """Check if ws (workspace) command is available.

        Returns:
            True if ws command is available (binary, function, or alias)

        Notes:
            - Uses bash login shell to detect shell functions/aliases
              (shutil.which only finds binaries, not shell functions)
            - Checks once and caches result
            - Used for pre-flight validation before launching
        """
        if self._ws_available_cache is not None:
            return self._ws_available_cache

        # Use bash login shell to check for ws - handles binaries, functions, and aliases
        # shutil.which() only finds binaries, but ws is often a shell function in VFX studios
        try:
            result = subprocess.run(
                ["bash", "-lc", "command -v ws"],
                check=False, capture_output=True,
                text=True,
                timeout=2,  # Reduced from 5s to avoid long UI freezes
            )
            self._ws_available_cache = result.returncode == 0
        except (subprocess.TimeoutExpired, OSError) as e:
            logger.warning(f"Failed to check ws availability: {e}")
            # Fall back to shutil.which (better than nothing)
            self._ws_available_cache = shutil.which("ws") is not None

        logger.debug(f"ws availability cached: {self._ws_available_cache}")
        return self._ws_available_cache

    def get_rez_packages(self, app_name: str, config: "type[Config]") -> list[str]:
        """Get rez packages for the specified application.

        Args:
            app_name: Name of the application (nuke, maya, 3de)
            config: Application configuration

        Returns:
            List of rez packages to load for the application

        Notes:
            - Returns empty list for unknown applications
            - Packages are defined in Config.REZ_*_PACKAGES
        """
        package_map: dict[str, list[str]] = {
            "nuke": config.REZ_NUKE_PACKAGES,
            "maya": config.REZ_MAYA_PACKAGES,
            "3de": config.REZ_3DE_PACKAGES,
        }
        packages = package_map.get(app_name, [])
        logger.debug(f"Rez packages for {app_name}: {packages}")
        return packages

    def detect_terminal(self) -> str | None:
        """Detect available terminal emulator.

        Returns:
            Name of available terminal emulator, or None if none found

        Notes:
            - Checks terminals in preference order
            - Caches result for performance with 5-minute TTL
            - Preference: gnome-terminal > konsole > xterm > x-terminal-emulator
        """
        # Return cached result if not expired (cache_time > 0 means detection was performed)
        current_time = time.monotonic()
        if (
            self._terminal_cache_time > 0
            and current_time - self._terminal_cache_time < self.TERMINAL_CACHE_TTL_SEC
        ):
            return self._available_terminal_cache

        # Check terminals in order of preference
        for term in self.TERMINAL_PREFERENCE:
            if shutil.which(term) is not None:
                self._available_terminal_cache = term
                self._terminal_cache_time = current_time
                logger.info(f"Detected terminal: {term}")
                return term

        # No terminal found - cache the None result too
        self._available_terminal_cache = None
        self._terminal_cache_time = current_time
        logger.warning("No terminal emulator found")
        return None

    def reset_cache(self) -> None:
        """Reset cached environment detection results.

        Useful for testing or when environment changes are expected.
        """
        self._rez_available_cache = None
        self._ws_available_cache = None
        self._available_terminal_cache = None
        self._terminal_cache_time = 0.0
        logger.debug("EnvironmentManager cache reset")

    def warm_cache_async(self) -> None:
        """Pre-warm environment caches in background thread.

        Call this at startup to avoid blocking the main thread on first
        environment checks. The caches will be populated in the background
        and subsequent calls to is_rez_available(), is_ws_available(), and
        detect_terminal() will return immediately from cache.
        """
        def _warm() -> None:
            try:
                # These calls will populate the caches
                _ = self.is_ws_available()
                _ = self.detect_terminal()
                logger.debug("Environment caches pre-warmed successfully")
            except Exception as e:
                logger.warning(f"Error during cache pre-warming: {e}")

        thread = threading.Thread(target=_warm, daemon=True, name="EnvironmentCacheWarm")
        thread.start()
