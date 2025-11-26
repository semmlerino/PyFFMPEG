"""Determinism fixtures for reproducible test execution.

This module provides fixtures that ensure consistent, reproducible test behavior
by controlling random number generation. Use these fixtures when tests depend on
random values or when debugging flaky tests.

Usage:
    @pytest.mark.usefixtures("stable_random_seed")
    def test_something_with_random():
        # Random values are now deterministic
        ...

    # Or request explicitly:
    def test_something(stable_random_seed):
        ...

NOTE: These fixtures are NOT autouse. Tests must explicitly request them
or use the marker to opt-in. This reduces overhead for tests that don't
need deterministic randomness.
"""

from __future__ import annotations

import random

import pytest


@pytest.fixture
def stable_random_seed() -> None:
    """Fix random seeds for reproducible tests.

    This fixture makes each test's random values deterministic while pytest-randomly
    still shuffles test ORDER to surface hidden test coupling.

    Use this when:
    - Tests use random.choice(), random.randint(), etc.
    - Tests use numpy random functions
    - You're debugging a flaky test that might have randomness issues

    Note: pytest-randomly handles test order randomization separately - this
    fixture only controls random values WITHIN tests, not test ordering.
    """
    random.seed(12345)

    try:
        import numpy as np

        np.random.seed(12345)
    except ImportError:
        pass  # numpy not installed
