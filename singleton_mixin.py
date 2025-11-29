"""Thread-safe singleton mixin to eliminate boilerplate singleton code.

This module provides a reusable SingletonMixin that implements the double-checked
locking singleton pattern with proper test isolation support via reset().

Usage:
    from typing_compat import override

    class MyService(SingletonMixin):
        def __init__(self) -> None:
            if self._is_initialized():
                return
            super().__init__()
            # ... actual initialization ...
            self._mark_initialized()

        @classmethod
        @override  # Mark as override for type checker
        def _cleanup_instance(cls) -> None:
            if cls._instance is not None:
                cls._instance.shutdown()  # Your cleanup logic
"""

from __future__ import annotations

import threading
from typing import ClassVar, Self


class SingletonMixin:
    """Thread-safe singleton mixin with double-checked locking.

    Provides:
    - Thread-safe singleton creation via __new__
    - Initialization guard helpers (_is_initialized, _mark_initialized)
    - Test isolation via reset() classmethod
    - Customizable cleanup via _cleanup_instance() override

    Note: Subclasses must call _is_initialized() at the start of __init__
    and _mark_initialized() at the end to prevent re-initialization.
    """

    _instance: ClassVar[Self | None] = None  # type: ignore[misc]
    _lock: ClassVar[threading.RLock] = threading.RLock()  # RLock for reentrant cleanup
    _initialized: ClassVar[bool] = False

    def __new__(cls) -> Self:
        """Create singleton instance with thread-safe double-checked locking."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    cls._instance = instance
        return cls._instance

    @classmethod
    def _is_initialized(cls) -> bool:
        """Check if singleton has been initialized.

        Use at the start of __init__ to guard against re-initialization:
            if self._is_initialized():
                return
        """
        return cls._initialized

    @classmethod
    def _mark_initialized(cls) -> None:
        """Mark singleton as initialized.

        Use at the end of __init__:
            self._mark_initialized()
        """
        cls._initialized = True

    @classmethod
    def _cleanup_instance(cls) -> None:
        """Override in subclass to provide cleanup logic.

        Called by reset() before clearing the singleton instance.
        Subclasses should override this to call their cleanup methods:
            @classmethod
            def _cleanup_instance(cls) -> None:
                if cls._instance is not None:
                    cls._instance.shutdown()
        """

    @classmethod
    def reset(cls) -> None:
        """Reset singleton for testing. INTERNAL USE ONLY.

        This method clears all state and resets the singleton instance.
        It should only be used in test cleanup to ensure test isolation.
        """
        with cls._lock:
            if cls._instance is not None:
                cls._cleanup_instance()
            cls._instance = None
            cls._initialized = False
