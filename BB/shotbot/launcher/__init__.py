"""Launcher system package for ShotBot.

This package provides modular components for managing custom VFX application launchers.
"""

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
    from launcher.process_manager import LauncherProcessManager
    from launcher.worker import LauncherWorker
    _QT_AVAILABLE = True
except ImportError:
    _QT_AVAILABLE = False
    LauncherProcessManager = None
    LauncherWorker = None

__all__ = [
    # Data models
    "CustomLauncher",
    "LauncherEnvironment",
    "LauncherTerminal",
    "LauncherValidation",
    "ProcessInfo",
    # Core components
    "LauncherConfigManager",
    "LauncherRepository",
    "LauncherValidator",
]

# Add Qt components if available
if _QT_AVAILABLE:
    __all__.extend(["LauncherProcessManager", "LauncherWorker"])

__version__ = "1.0.0"