"""Repository pattern for launcher CRUD operations.

This module provides a repository layer for managing launcher data,
extracted from the original launcher_manager.py for better separation of concerns.
"""

from __future__ import annotations

# Standard library imports
import uuid
from typing import TYPE_CHECKING

# Local application imports
from logging_mixin import LoggingMixin

if TYPE_CHECKING:
    # Local application imports
    from launcher.config_manager import LauncherConfigManager
    from launcher.models import CustomLauncher


class LauncherRepository(LoggingMixin):
    """Repository for launcher CRUD operations."""

    def __init__(self, config_manager: LauncherConfigManager) -> None:
        """Initialize the repository.

        Args:
            config_manager: Configuration manager for persistence
        """
        super().__init__()
        self._config_manager = config_manager
        self._launchers: dict[str, CustomLauncher] = {}
        self.reload()

    def reload(self) -> None:
        """Reload launchers from storage."""
        self._launchers = self._config_manager.load_launchers()
        self.logger.info(f"Loaded {len(self._launchers)} launchers from storage")

    def save(self) -> bool:
        """Save current launchers to storage.

        Returns:
            True if successful, False otherwise
        """
        success = self._config_manager.save_launchers(self._launchers)
        if success:
            self.logger.info(f"Saved {len(self._launchers)} launchers to storage")
        else:
            self.logger.error("Failed to save launchers to storage")
        return success

    def create(self, launcher: CustomLauncher) -> bool:
        """Create a new launcher.

        Args:
            launcher: The launcher to create

        Returns:
            True if successful, False otherwise
        """
        # Generate ID if not provided
        if not launcher.id:
            launcher.id = self._generate_id()

        # Check if ID already exists
        if launcher.id in self._launchers:
            self.logger.warning(f"Launcher with ID {launcher.id} already exists")
            return False

        # Add to collection
        self._launchers[launcher.id] = launcher

        # Save to storage
        if self.save():
            self.logger.info(
                f"Created launcher '{launcher.name}' with ID {launcher.id}"
            )
            return True
        # Rollback on save failure
        del self._launchers[launcher.id]
        return False

    def update(self, launcher: CustomLauncher) -> bool:
        """Update an existing launcher.

        Args:
            launcher: The launcher with updated data

        Returns:
            True if successful, False otherwise
        """
        if launcher.id not in self._launchers:
            self.logger.warning(f"Launcher with ID {launcher.id} not found for update")
            return False

        # Keep backup for rollback
        backup = self._launchers[launcher.id]

        # Update launcher
        self._launchers[launcher.id] = launcher

        # Save to storage
        if self.save():
            self.logger.info(f"Updated launcher '{launcher.name}'")
            return True
        # Rollback on save failure
        self._launchers[launcher.id] = backup
        return False

    def delete(self, launcher_id: str) -> bool:
        """Delete a launcher.

        Args:
            launcher_id: ID of the launcher to delete

        Returns:
            True if successful, False otherwise
        """
        if launcher_id not in self._launchers:
            self.logger.warning(
                f"Launcher with ID {launcher_id} not found for deletion"
            )
            return False

        # Keep backup for rollback
        backup = self._launchers[launcher_id]
        launcher_name = backup.name

        # Delete from collection
        del self._launchers[launcher_id]

        # Save to storage
        if self.save():
            self.logger.info(f"Deleted launcher '{launcher_name}'")
            return True
        # Rollback on save failure
        self._launchers[launcher_id] = backup
        return False

    def get(self, launcher_id: str) -> CustomLauncher | None:
        """Get a launcher by ID.

        Args:
            launcher_id: ID of the launcher to retrieve

        Returns:
            The launcher if found, None otherwise
        """
        return self._launchers.get(launcher_id)

    def get_by_name(self, name: str) -> CustomLauncher | None:
        """Get a launcher by name.

        Args:
            name: Name of the launcher to retrieve

        Returns:
            The first launcher with matching name, None if not found
        """
        for launcher in self._launchers.values():
            if launcher.name == name:
                return launcher
        return None

    def list_all(self, category: str | None = None) -> list[CustomLauncher]:
        """List all launchers, optionally filtered by category.

        Args:
            category: Optional category filter

        Returns:
            List of launchers
        """
        launchers = list(self._launchers.values())

        if category:
            launchers = [
                launcher for launcher in launchers if launcher.category == category
            ]

        # Sort by name for consistent ordering
        launchers.sort(key=lambda launcher: launcher.name.lower())

        return launchers

    def get_categories(self) -> list[str]:
        """Get list of unique launcher categories.

        Returns:
            Sorted list of category names
        """
        categories: set[str] = set()
        for launcher in self._launchers.values():
            if launcher.category:
                categories.add(launcher.category)

        return sorted(categories)

    def exists(self, launcher_id: str) -> bool:
        """Check if a launcher exists.

        Args:
            launcher_id: ID to check

        Returns:
            True if launcher exists, False otherwise
        """
        return launcher_id in self._launchers

    def count(self) -> int:
        """Get total number of launchers.

        Returns:
            Number of launchers
        """
        return len(self._launchers)

    def _generate_id(self) -> str:
        """Generate a unique launcher ID.

        Returns:
            New unique ID
        """
        return str(uuid.uuid4())
