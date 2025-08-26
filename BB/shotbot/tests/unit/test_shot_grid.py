"""Unit tests for ShotGrid widget following UNIFIED_TESTING_GUIDE.

Tests thumbnail grid display, selection, and user interactions.
"""

from __future__ import annotations

# Test doubles for behavior testing (UNIFIED_TESTING_GUIDE)
from tests.test_doubles_library import (
    TestSubprocess, TestShot, TestShotModel,
    TestCacheManager, TestLauncher, TestWorker,
    ThreadSafeTestImage, SignalDouble, TestProcessPool
)
