"""Launcher system package for ShotBot.

This package provides modular components for managing custom VFX application launchers.
"""

# Local application imports
# Import data models (no Qt dependencies)
# Import non-Qt components
from launcher.config_manager import LauncherConfigManager
from launcher.models import (
    CustomLauncher,
    LauncherEnvironment,
    LauncherTerminal,
    LauncherValidation,
    ProcessInfo,
)
from launcher.repository import LauncherRepository
from launcher.validator import LauncherValidator

# Qt-dependent components imported conditionally
try:
    # Local application imports
    from launcher.process_manager import LauncherProcessManager
    from launcher.worker import LauncherWorker

    _qt_available = True
except ImportError:
    _qt_available = False
    LauncherProcessManager = None
    LauncherWorker = None

__all__ = [
    # Data models
    "CustomLauncher",
    # Core components
    "LauncherConfigManager",
    "LauncherEnvironment",
    "LauncherRepository",
    "LauncherTerminal",
    "LauncherValidation",
    "LauncherValidator",
    "ProcessInfo",
]

# Add Qt components if available
if _qt_available:
    __all__.extend(["LauncherProcessManager", "LauncherWorker"])

__version__ = "1.0.0"
