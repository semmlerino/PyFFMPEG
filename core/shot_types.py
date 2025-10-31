"""Core shot-related types.

This module provides domain-specific types for shot operations,
separated from generic type definitions.
"""

from typing import NamedTuple


class RefreshResult(NamedTuple):
    """Result of a shot refresh operation.

    This NamedTuple provides type-safe results from ShotModel.refresh_shots() operations,
    allowing callers to determine both operation success and whether the shot list
    actually changed. This enables efficient UI updates that only occur when needed.

    Attributes:
        success: Whether the refresh operation completed successfully.
            True indicates the workspace command executed without errors and
            the shot list was parsed. False indicates command failure, timeout,
            or parsing errors that prevented shot list updates.

        has_changes: Whether the shot list changed compared to the previous
            refresh. True indicates new shots were added, existing shots were
            removed, or shot metadata changed. False indicates the shot list
            is identical to the previous state. Only meaningful when success=True.

    Examples:
        Basic usage with tuple unpacking:
            >>> result = shot_model.refresh_shots()
            >>> success, has_changes = result
            >>> if success and has_changes:
            ...     update_ui_with_new_shots()

        Explicit attribute access:
            >>> result = shot_model.refresh_shots()
            >>> if result.success:
            ...     logger.info(f"Refresh successful, changes: {result.has_changes}")
            ... else:
            ...     logger.error("Shot refresh failed")

        Conditional UI updates:
            >>> result = shot_model.refresh_shots()
            >>> if result.success and result.has_changes:
            ...     shot_grid.update_shots(shot_model.get_shots())
            ... elif result.success:
            ...     logger.debug("Shot list unchanged, skipping UI update")
            ... else:
            ...     show_error_dialog("Failed to refresh shots")

    Type Safety:
        This NamedTuple enforces type safety at runtime and provides IDE
        autocompletion. It replaces the previous tuple return type:

        Before: tuple[bool, bool]  # Unclear which bool means what
        After:  RefreshResult      # Self-documenting with named fields
    """

    success: bool
    has_changes: bool
