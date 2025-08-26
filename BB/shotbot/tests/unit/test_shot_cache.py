"""Unit tests for ShotCache following UNIFIED_TESTING_GUIDE.

Tests shot data caching with TTL validation and thread safety.
"""

from __future__ import annotations

# Test doubles for behavior testing (UNIFIED_TESTING_GUIDE)
from tests.test_doubles_library import (
    TestSubprocess, TestShot, TestShotModel,
    TestCacheManager, TestLauncher, TestWorker,
    ThreadSafeTestImage, SignalDouble, TestProcessPool
)
