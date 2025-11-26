"""Singleton and cache isolation fixtures for test isolation.

This module provides the cleanup_state autouse fixture that ensures singleton
state and caches are properly reset between tests, preventing test contamination
and flaky behavior.

Fixtures:
    cleanup_state: Reset singletons and caches between tests (autouse)
"""

from __future__ import annotations

import gc
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest


if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def cleanup_state() -> Iterator[None]:
    """Clean up all module-level caches and singleton state before and after each test.

    This autouse fixture consolidates cache clearing, singleton resets, and threading cleanup
    to prevent test contamination. Runs both before and after each test for complete isolation.

    Before test:
    - Clear all utility caches and disable caching
    - Clear shared cache directory
    - Reset NotificationManager and ProgressManager singletons

    After test (defense in depth):
    - Process pending Qt events
    - Clean up Qt widgets (NotificationManager, ProgressManager)
    - Reset all singletons (ProcessPoolManager, QRunnableTracker, ThreadSafeWorker)
    - Clear caches again
    - Force garbage collection

    See UNIFIED_TESTING_V2.MD section "Common Root Causes of Isolation Failures" for details.
    """
    from notification_manager import NotificationManager
    from progress_manager import ProgressManager
    from utils import clear_all_caches, disable_caching

    # ===== BEFORE TEST: Setup clean state =====

    # Clear ALL caches FIRST, before any test operations
    clear_all_caches()

    # CRITICAL: Clear shared cache directory to prevent contamination
    # Tests using CacheManager() without cache_dir parameter use ~/.shotbot/cache_test
    # This shared directory accumulates data across test runs, causing contamination
    shared_cache_dir = Path.home() / ".shotbot" / "cache_test"
    if shared_cache_dir.exists():
        try:
            shutil.rmtree(shared_cache_dir)
        except FileNotFoundError:
            # Race condition in pytest-xdist: another worker may have deleted it
            pass
        except OSError:
            # Race condition in pytest-xdist: another worker may have created
            # files while we were deleting. This is acceptable during parallel
            # testing - each test should handle its own cache isolation.
            pass

    # CRITICAL: Reset _cache_disabled flag to ensure consistent test behavior
    # Some tests call enable_caching() to test caching behavior.
    # Always disable caching at the start of each test for predictable behavior.
    disable_caching()

    # Reset all singleton managers using their reset() methods
    # Order matters: NotificationManager FIRST (closes Qt widgets that ProgressManager may reference)
    try:
        NotificationManager.reset()
    except (RuntimeError, AttributeError):
        # Qt objects may already be deleted
        pass

    # THEN reset ProgressManager (now safe to clear widget references)
    try:
        ProgressManager.reset()
    except (RuntimeError, AttributeError):
        # Qt objects may already be deleted
        pass

    # ProcessPoolManager reset removed - now handled by mock_process_pool_manager autouse fixture
    # The autouse fixture patches ProcessPoolManager._instance for all tests
    # Resetting here would interfere with the mock

    # Reset FilesystemCoordinator
    try:
        from filesystem_coordinator import FilesystemCoordinator

        FilesystemCoordinator.reset()
    except (RuntimeError, AttributeError, ImportError):
        pass

    # Clear OptimizedShotParser pattern cache to prevent test contamination
    # The cache is keyed by Config.SHOWS_ROOT; if tests change this config,
    # the cached patterns become invalid for subsequent tests
    try:
        import optimized_shot_parser

        optimized_shot_parser._PATTERN_CACHE.clear()
    except (RuntimeError, AttributeError, ImportError):
        pass

    # Reset Config.SHOWS_ROOT in SETUP phase to prevent contamination
    # This runs BEFORE the test body to ensure clean state
    try:
        import os

        from config import Config

        Config.SHOWS_ROOT = os.environ.get("SHOWS_ROOT", "/shows")
    except (RuntimeError, AttributeError, ImportError):
        pass

    yield

    # ===== AFTER TEST: Comprehensive cleanup (defense in depth) =====

    # Reset Config.SHOWS_ROOT in teardown to clean up after tests that don't use monkeypatch
    # Tests that DO use monkeypatch will have their values restored automatically by pytest
    try:
        import os

        from config import Config

        Config.SHOWS_ROOT = os.environ.get("SHOWS_ROOT", "/shows")
    except (RuntimeError, AttributeError, ImportError):
        pass

    # Qt Event Processing - Process pending events before cleanup
    # This ensures Qt is in a stable state before we start tearing things down
    try:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app:
            app.processEvents()
    except (RuntimeError, ImportError):
        # Qt not available or objects already deleted, ignore
        pass

    # Reset all singleton managers using their reset() methods
    # NotificationManager first (must happen early to avoid Qt object access after deletion)
    try:
        NotificationManager.reset()
    except (RuntimeError, AttributeError):
        pass

    # ProgressManager cleanup
    try:
        ProgressManager.reset()
    except (RuntimeError, AttributeError):
        pass

    # Clear utils caches
    clear_all_caches()

    # CRITICAL: Clear shared cache directory after test
    if shared_cache_dir.exists():
        try:
            shutil.rmtree(shared_cache_dir)
        except (FileNotFoundError, OSError):
            # FileNotFoundError: Already deleted by another worker
            # OSError: Directory not empty (race condition during parallel execution)
            pass

    # CRITICAL: Reset _cache_disabled flag after test
    disable_caching()

    # QRunnableTracker Cleanup
    from runnable_tracker import QRunnableTracker

    try:
        QRunnableTracker.reset()
    except Exception as e:
        import warnings

        warnings.warn(f"QRunnableTracker reset failed: {e}", RuntimeWarning, stacklevel=2)

    # ProcessPoolManager Cleanup
    from process_pool_manager import ProcessPoolManager

    try:
        ProcessPoolManager.reset()
    except Exception as e:
        import warnings

        warnings.warn(f"ProcessPoolManager reset failed: {e}", RuntimeWarning, stacklevel=2)

    # FilesystemCoordinator Cleanup
    from filesystem_coordinator import FilesystemCoordinator

    try:
        FilesystemCoordinator.reset()
    except Exception as e:
        import warnings

        warnings.warn(f"FilesystemCoordinator reset failed: {e}", RuntimeWarning, stacklevel=2)

    # ThreadSafeWorker Zombie Cleanup
    # Uses reset() which safely stops timer and clears tracking lists under mutex
    from thread_safe_worker import ThreadSafeWorker

    try:
        ThreadSafeWorker.reset()
    except Exception as e:
        import warnings

        warnings.warn(f"ThreadSafeWorker reset failed: {e}", RuntimeWarning, stacklevel=2)

    # Force garbage collection to clean up any instances that cached state
    # (e.g., TargetedShotsFinder instances with cached Config.SHOWS_ROOT regex patterns)
    gc.collect()
