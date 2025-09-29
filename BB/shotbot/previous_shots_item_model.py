"""Qt Model/View item model for previous shots display using UnifiedItemModel.

This module provides backward compatibility with the original PreviousShotsItemModel
by using the unified implementation with PREVIOUS type configuration.
"""

from __future__ import annotations

# Standard library imports
from typing import TYPE_CHECKING

# Local application imports
from unified_item_model import (
    UnifiedItemModel,
    UnifiedItemType,
    create_previous_shots_item_model,
)

if TYPE_CHECKING:
    # Local application imports
    from PySide6.QtCore import QObject

    from cache_manager import CacheManager
    from previous_shots_model import PreviousShotsModel


# For backward compatibility, alias the unified model configured for previous shots
class PreviousShotsItemModel(UnifiedItemModel):
    """Previous shots-specific Qt Model implementation using unified architecture.

    This is a backward-compatible alias that creates a UnifiedItemModel
    configured for PREVIOUS type. All original methods and properties are preserved.
    """

    def __init__(
        self,
        previous_shots_model: PreviousShotsModel,
        cache_manager: CacheManager | None = None,
        parent: QObject | None = None,
    ) -> None:
        """Initialize the item model.

        Args:
            previous_shots_model: The underlying previous shots model
            cache_manager: Optional cache manager for thumbnails
            parent: Optional parent object
        """
        # Initialize as UnifiedItemModel with PREVIOUS type
        super().__init__(
            UnifiedItemType.PREVIOUS, cache_manager, parent, previous_shots_model
        )

    # ============= Backward compatibility properties and methods =============

    @property
    def _model(self) -> PreviousShotsModel:
        """Backward compatibility property for accessing underlying model."""
        return self._underlying_model

    def _update_shots(self) -> None:
        """Backward compatibility method for updating shots from underlying model."""
        self._update_from_underlying_model()


# Factory function (the preferred way to create previous shots models)
def create_previous_shots_model(
    previous_shots_model: PreviousShotsModel,
    cache_manager: CacheManager | None = None,
    parent: QObject | None = None,
) -> UnifiedItemModel:
    """Create a previous shots item model using the unified implementation.

    Args:
        previous_shots_model: The underlying previous shots model
        cache_manager: Optional cache manager for thumbnails
        parent: Optional parent QObject

    Returns:
        UnifiedItemModel configured for previous shots
    """
    return create_previous_shots_item_model(previous_shots_model, cache_manager, parent)
