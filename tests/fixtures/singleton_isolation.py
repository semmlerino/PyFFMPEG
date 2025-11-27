"""Singleton and cache isolation fixtures for test isolation.

This module provides the cleanup_state autouse fixture that ensures singleton
state and caches are properly reset between tests, preventing test contamination
and flaky behavior.

Fixtures:
    reset_caches (autouse): Lightweight cleanup for ALL tests - caches and config
    reset_singletons: Heavy cleanup for Qt tests - singletons, threads
    cleanup_state_lite: Alias for reset_caches (backward compatibility)
    cleanup_state_heavy: Alias for reset_singletons (backward compatibility)

Environment Variables:
    SHOTBOT_TEST_STRICT_CLEANUP: Set to "1" to fail on cleanup exceptions
    SHOTBOT_TEST_AGGRESSIVE_GC: Set to "1" to run gc.collect() after each test
    CI / GITHUB_ACTIONS: Auto-enables STRICT_CLEANUP in CI environments
"""

from __future__ import annotations

import gc
import logging
import os
from typing import TYPE_CHECKING

import pytest


if TYPE_CHECKING:
    from collections.abc import Iterator

_logger = logging.getLogger(__name__)

# Strict mode fails on cleanup exceptions (auto-enabled in CI)
STRICT_CLEANUP = (
    os.environ.get("SHOTBOT_TEST_STRICT_CLEANUP", "0") == "1"
    or os.environ.get("CI") == "true"
    or os.environ.get("GITHUB_ACTIONS") == "true"
)

# Aggressive GC mode - only run gc.collect() when explicitly requested
AGGRESSIVE_GC = os.environ.get("SHOTBOT_TEST_AGGRESSIVE_GC", "0") == "1"


@pytest.fixture(autouse=True)
def reset_caches() -> Iterator[None]:
    """Lightweight cleanup for ALL tests - caches and config reset before each test.

    This autouse fixture provides minimal cleanup that runs for every test,
    including pure logic tests that don't touch Qt or singletons.

    Before test:
    - Clear all utility caches
    - Re-enable caching (in case previous test disabled it)
    - Reset Config.SHOWS_ROOT
    - Clear OptimizedShotParser pattern cache

    After test:
    - gc.collect() only if SHOTBOT_TEST_AGGRESSIVE_GC=1

    Note: After-test cache clearing is handled by the next test's before-test
    cleanup, eliminating redundant work in the hot path.

    For heavy cleanup (Qt, singletons, threads), see reset_singletons fixture.
    """
    from utils import clear_all_caches, enable_caching

    # ===== BEFORE TEST: Lightweight setup =====
    clear_all_caches()
    enable_caching()  # Re-enable in case previous test disabled it

    # Reset Config.SHOWS_ROOT
    try:
        from config import Config

        Config.SHOWS_ROOT = os.environ.get("SHOWS_ROOT", "/shows")
    except (RuntimeError, AttributeError, ImportError) as e:
        _logger.debug("Config.SHOWS_ROOT reset before-test exception: %s", e)
        if STRICT_CLEANUP:
            raise

    # Clear OptimizedShotParser pattern cache
    try:
        import optimized_shot_parser

        optimized_shot_parser._PATTERN_CACHE.clear()
    except (RuntimeError, AttributeError, ImportError) as e:
        _logger.debug("optimized_shot_parser cache clear exception: %s", e)
        if STRICT_CLEANUP:
            raise

    yield

    # ===== AFTER TEST: Minimal cleanup =====
    # Only run gc.collect() if explicitly requested (reduces overhead)
    if AGGRESSIVE_GC:
        gc.collect()


# Backward compatibility alias
cleanup_state_lite = reset_caches


@pytest.fixture
def reset_singletons() -> Iterator[None]:
    """Heavy cleanup for Qt tests - singletons, threads, Qt state.

    NOTE: This fixture is NOT autouse. It is applied conditionally via
    conftest.py's pytest_collection_modifyitems hook to tests that use qtbot
    or are marked with @pytest.mark.qt.

    Before test:
    - Reset all registered singletons via SingletonRegistry

    After test:
    - Process pending Qt events (handled by qt_cleanup, not here)
    - Reset all registered singletons via SingletonRegistry

    Cleanup order is managed centrally by SingletonRegistry:
    - Qt UI singletons first (NotificationManager, ProgressManager)
    - Worker tracking (QRunnableTracker, ThreadSafeWorker)
    - Process pools (ProcessPoolManager)
    - Infrastructure (FilesystemCoordinator)
    """
    from tests.fixtures.singleton_registry import SingletonRegistry

    # ===== BEFORE TEST: Reset all singletons =====
    errors = SingletonRegistry.reset_all(strict=STRICT_CLEANUP)
    for path, exc in errors:
        _logger.debug("Singleton reset before-test failed: %s: %s", path, exc)

    yield

    # ===== AFTER TEST: Reset singletons =====
    # Note: Qt event processing is handled by qt_cleanup fixture
    errors = SingletonRegistry.reset_all(strict=STRICT_CLEANUP)
    for path, exc in errors:
        _logger.debug("Singleton reset after-test failed: %s: %s", path, exc)


# Backward compatibility alias
cleanup_state_heavy = reset_singletons


@pytest.fixture
def cleanup_state(reset_caches: None, reset_singletons: None) -> Iterator[None]:
    """Combined cleanup fixture for backward compatibility.

    This fixture combines both lite and heavy cleanup. Use this if you explicitly
    need both, but prefer using reset_singletons directly for Qt tests.
    """
    yield
