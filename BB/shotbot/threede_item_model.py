"""Qt Model/View implementation for 3DE scene data using UnifiedItemModel.

This module provides backward compatibility with the original ThreeDEItemModel
by using the unified implementation with THREEDE type configuration.
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
    create_threede_item_model,
)

if TYPE_CHECKING:
    from PySide6.QtCore import QObject


class ThreeDERole(IntEnum):
    """Custom roles for 3DE scene data access - extends BaseItemRole."""

    # Inherit all base roles
    DisplayRole = BaseItemRole.DisplayRole
    DecorationRole = BaseItemRole.DecorationRole
    ToolTipRole = BaseItemRole.ToolTipRole
    SizeHintRole = BaseItemRole.SizeHintRole

    # Common roles from base
    SceneObjectRole = BaseItemRole.ObjectRole
    ShowRole = BaseItemRole.ShowRole
    SequenceRole = BaseItemRole.SequenceRole
    FullNameRole = BaseItemRole.FullNameRole
    WorkspacePathRole = BaseItemRole.WorkspacePathRole
    ThumbnailPathRole = BaseItemRole.ThumbnailPathRole
    ThumbnailPixmapRole = BaseItemRole.ThumbnailPixmapRole
    LoadingStateRole = BaseItemRole.LoadingStateRole
    IsSelectedRole = BaseItemRole.IsSelectedRole

    # 3DE-specific roles (mapped to unified roles)
    ShotRole = Qt.ItemDataRole.UserRole + 4  # Maps to ItemSpecificRole1
    UserRole = Qt.ItemDataRole.UserRole + 5  # Maps to ItemSpecificRole2
    ScenePathRole = Qt.ItemDataRole.UserRole + 6  # Maps to ItemSpecificRole3
    ModifiedTimeRole = Qt.ItemDataRole.UserRole + 11  # Maps to ModifiedTimeRole


# For backward compatibility, alias the unified model configured for 3DE scenes
class ThreeDEItemModel(UnifiedItemModel):
    """3DE scene-specific Qt Model implementation using unified architecture.

    This is a backward-compatible alias that creates a UnifiedItemModel
    configured for THREEDE type. All original methods and properties are preserved.
    """

    def __init__(
        self,
        cache_manager: QObject | None = None,
        parent: QObject | None = None,
    ) -> None:
        """Initialize the 3DE item model.

        Args:
            cache_manager: Optional cache manager for thumbnails
            parent: Optional parent QObject
        """
        # Initialize as UnifiedItemModel with THREEDE type
        super().__init__(UnifiedItemType.THREEDE, cache_manager, parent)


# Factory function (the preferred way to create 3DE models)
def create_threede_model(
    cache_manager: QObject | None = None,
    parent: QObject | None = None,
) -> UnifiedItemModel:
    """Create a 3DE item model using the unified implementation.

    Args:
        cache_manager: Optional cache manager for thumbnails
        parent: Optional parent QObject

    Returns:
        UnifiedItemModel configured for 3DE scenes
    """
    return create_threede_item_model(cache_manager, parent)
