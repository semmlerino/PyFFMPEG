"""Result types for launcher operations.

This module defines standard result types for launcher operations, providing
a consistent error handling pattern across the launcher system.

Design Pattern:
    - Use Result objects for operations with expected failure modes
    - Use Exceptions for truly exceptional errors (I/O, system failures)
    - Use Qt Signals for async UI notifications (not error propagation)

Examples:
    >>> result = create_launcher(launcher_config)
    >>> if result.success:
    ...     launcher_id = result.value
    >>> else:
    ...     for error in result.errors:
    ...         print(f"Error: {error}")
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeVar


T = TypeVar("T")


@dataclass
class Result[T]:
    """Generic result type for operations that can fail.

    This provides a consistent way to handle success/failure without
    mixing exceptions, None returns, and signals.

    Attributes:
        success: Whether the operation succeeded
        value: The result value (only valid if success=True)
        errors: List of error messages (only populated if success=False)
    """

    success: bool
    value: T | None = None
    errors: list[str] | None = None

    @classmethod
    def ok(cls, value: T) -> Result[T]:
        """Create a successful result.

        Args:
            value: The success value

        Returns:
            Result with success=True and the value
        """
        return cls(success=True, value=value, errors=None)

    @classmethod
    def fail(cls, *errors: str) -> Result[T]:
        """Create a failed result.

        Args:
            *errors: One or more error messages

        Returns:
            Result with success=False and error messages
        """
        return cls(success=False, value=None, errors=list(errors))

    def __bool__(self) -> bool:
        """Allow using result in boolean context.

        Returns:
            success value
        """
        return self.success


# Commonly used result types
LauncherCreationResult = Result[str]  # Returns launcher_id on success
LauncherUpdateResult = Result[bool]  # Returns True on success
LauncherExecutionResult = Result[bool]  # Returns True on success
