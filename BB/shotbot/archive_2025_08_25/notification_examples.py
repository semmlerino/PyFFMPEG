"""Examples of how to integrate the notification system throughout ShotBot.

This module demonstrates best practices for using the NotificationManager
in various parts of the application.
"""

import logging
from typing import Optional

from notification_manager import NotificationManager, NotificationType


class CacheErrorHandler:
    """Example of how to handle cache-related errors with notifications."""

    @staticmethod
    def handle_thumbnail_error(shot_name: str, error: Exception) -> None:
        """Handle thumbnail loading errors with appropriate notifications."""
        error_msg = str(error)

        if "permission" in error_msg.lower():
            NotificationManager.warning(
                "Permission Error",
                f"Cannot access thumbnail for {shot_name}",
                "Check file permissions on the thumbnail directory",
            )
        elif "not found" in error_msg.lower():
            # Use toast for less critical missing file errors
            NotificationManager.toast(
                f"Thumbnail not found for {shot_name}",
                NotificationType.WARNING,
                duration=3000,
            )
        elif "out of memory" in error_msg.lower():
            NotificationManager.error(
                "Memory Error",
                "Not enough memory to load thumbnail",
                "Try closing other applications or reducing thumbnail cache size",
            )
        else:
            # Generic cache error
            logging.error(f"Thumbnail error for {shot_name}: {error}")
            NotificationManager.toast(
                f"Failed to load thumbnail for {shot_name}", NotificationType.ERROR
            )

    @staticmethod
    def handle_cache_corruption(cache_file: str) -> None:
        """Handle cache file corruption with recovery options."""
        NotificationManager.error(
            "Cache Corruption Detected",
            f"The cache file {cache_file} appears to be corrupted.",
            "The cache will be rebuilt automatically. This may take a few moments.",
        )


class WorkflowNotifications:
    """Examples of workflow-related notifications."""

    @staticmethod
    def shot_selection_feedback(shot_name: str, has_thumbnail: bool) -> None:
        """Provide feedback when a shot is selected."""
        if has_thumbnail:
            NotificationManager.info(f"Selected {shot_name}", 2000)
        else:
            NotificationManager.toast(
                f"Selected {shot_name} (no thumbnail)",
                NotificationType.INFO,
                duration=2000,
            )

    @staticmethod
    def background_task_progress(task_name: str, total_items: int) -> Optional[object]:
        """Start a progress dialog for background tasks."""
        if total_items > 10:  # Only show for substantial tasks
            return NotificationManager.progress(
                f"Processing {task_name}",
                f"Processing {total_items} items...",
                cancelable=True,
            )
        else:
            NotificationManager.info(f"Processing {task_name}...")
            return None

    @staticmethod
    def task_completion(task_name: str, success_count: int, error_count: int) -> None:
        """Show task completion summary."""
        if error_count == 0:
            NotificationManager.success(
                f"{task_name} completed - {success_count} items processed"
            )
        elif success_count > 0:
            NotificationManager.warning(
                f"{task_name} completed with errors",
                f"Processed {success_count} items successfully, {error_count} failed",
            )
        else:
            NotificationManager.error(
                f"{task_name} failed", f"All {error_count} items failed to process"
            )


class LauncherNotifications:
    """Examples of launcher-related notifications."""

    @staticmethod
    def app_launch_success(app_name: str, shot_name: str, extras: list = None) -> None:
        """Show success notification for app launch."""
        extras_str = ""
        if extras:
            extras_str = f" with {', '.join(extras)}"

        NotificationManager.toast(
            f"{app_name.title()} launched for {shot_name}{extras_str}",
            NotificationType.SUCCESS,
        )

    @staticmethod
    def custom_launcher_created(launcher_name: str) -> None:
        """Show notification when custom launcher is created."""
        NotificationManager.toast(
            f"Custom launcher '{launcher_name}' created", NotificationType.SUCCESS
        )
        NotificationManager.info(f"Custom launcher '{launcher_name}' is now available")

    @staticmethod
    def nuke_script_generated(shot_name: str, includes: list) -> None:
        """Show notification when Nuke script is generated."""
        includes_str = ", ".join(includes) if includes else "basic setup"
        NotificationManager.toast(
            f"Nuke script generated for {shot_name} ({includes_str})",
            NotificationType.SUCCESS,
            duration=3000,
        )


class ValidationNotifications:
    """Examples of validation and user input notifications."""

    @staticmethod
    def invalid_shot_selection() -> None:
        """Handle invalid shot selection."""
        NotificationManager.warning(
            "Invalid Selection",
            "Please select a valid shot from the grid before launching applications.",
        )

    @staticmethod
    def file_not_found(file_type: str, shot_name: str) -> None:
        """Handle missing files with helpful messages."""
        NotificationManager.toast(
            f"{file_type} not found for {shot_name}",
            NotificationType.WARNING,
            duration=4000,
        )

    @staticmethod
    def workspace_validation_failed(workspace_path: str) -> None:
        """Handle workspace validation errors."""
        NotificationManager.error(
            "Workspace Error",
            f"Cannot access workspace: {workspace_path}",
            "Make sure you have proper permissions and the path exists.",
        )


# Example usage patterns:


def example_cache_integration():
    """Example of integrating notifications with cache operations."""
    try:
        # Simulate cache operation
        pass
    except PermissionError as e:
        CacheErrorHandler.handle_thumbnail_error("shot001", e)
    except FileNotFoundError as e:
        CacheErrorHandler.handle_thumbnail_error("shot001", e)
    except Exception as e:
        CacheErrorHandler.handle_thumbnail_error("shot001", e)


def example_workflow_integration():
    """Example of integrating notifications with workflow operations."""
    task_name = "3DE Scene Discovery"
    total_scenes = 25

    # Start progress
    progress = WorkflowNotifications.background_task_progress(task_name, total_scenes)

    # Simulate processing...
    success_count = 23
    error_count = 2

    # Close progress and show completion
    if progress:
        NotificationManager.close_progress()

    WorkflowNotifications.task_completion(task_name, success_count, error_count)


def example_launcher_integration():
    """Example of integrating notifications with launcher operations."""
    # Success case
    LauncherNotifications.app_launch_success(
        "nuke", "shot001", ["raw plate", "undistortion"]
    )

    # Custom launcher case
    LauncherNotifications.custom_launcher_created("My Custom Tool")

    # Script generation
    LauncherNotifications.nuke_script_generated(
        "shot001", ["raw plate", "undistortion"]
    )
