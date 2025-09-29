"""Qt Model/View implementation for shot data using UnifiedItemModel.

This module provides backward compatibility with the original ShotItemModel
by using the unified implementation with SHOT type configuration.
"""

from __future__ import annotations

# Standard library imports
from enum import IntEnum
from typing import TYPE_CHECKING

# Third-party imports
from PySide6.QtCore import Qt

# Local application imports
from base_item_model import BaseItemRole
from unified_item_model import (
    UnifiedItemModel,
    UnifiedItemType,
    create_shot_item_model,
)

if TYPE_CHECKING:
    from PySide6.QtCore import QObject

    from cache_manager import CacheManager


class ShotRole(IntEnum):
    """Custom roles for shot data access - extends BaseItemRole."""

    # Inherit all base roles
    DisplayRole = BaseItemRole.DisplayRole
    DecorationRole = BaseItemRole.DecorationRole
    ToolTipRole = BaseItemRole.ToolTipRole
    SizeHintRole = BaseItemRole.SizeHintRole

    # Common roles from base
    ShotObjectRole = BaseItemRole.ObjectRole
    ShowRole = BaseItemRole.ShowRole
    SequenceRole = BaseItemRole.SequenceRole
    FullNameRole = BaseItemRole.FullNameRole
    WorkspacePathRole = BaseItemRole.WorkspacePathRole
    ThumbnailPathRole = BaseItemRole.ThumbnailPathRole
    ThumbnailPixmapRole = BaseItemRole.ThumbnailPixmapRole
    LoadingStateRole = BaseItemRole.LoadingStateRole
    IsSelectedRole = BaseItemRole.IsSelectedRole

    # Shot-specific roles (maps to UnifiedRole.ItemSpecificRole1)
    ShotNameRole = Qt.ItemDataRole.UserRole + 4


# For backward compatibility, alias the unified model configured for shots
class ShotItemModel(UnifiedItemModel):
    """Shot-specific Qt Model implementation using unified architecture.

    This is a backward-compatible alias that creates a UnifiedItemModel
    configured for SHOT type. All original methods and properties are preserved.
    """

    def __init__(
        self,
        cache_manager: CacheManager | None = None,
        parent: QObject | None = None,
    ) -> None:
        """Initialize the shot item model.

        Args:
            cache_manager: Optional cache manager for thumbnails
            parent: Optional parent QObject
        """
        # Initialize as UnifiedItemModel with SHOT type
        super().__init__(UnifiedItemType.SHOT, cache_manager, parent)


# Factory function (the preferred way to create shot models)
def create_shot_model(
    cache_manager: CacheManager | None = None,
    parent: QObject | None = None,
) -> UnifiedItemModel:
    """Create a shot item model using the unified implementation.

    Args:
        cache_manager: Optional cache manager for thumbnails
        parent: Optional parent QObject

    Returns:
        UnifiedItemModel configured for shots
    """
    return create_shot_item_model(cache_manager, parent)
