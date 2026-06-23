"""File conversion status enum."""

from enum import Enum


class FileStatus(Enum):
    """Status of a file in the conversion queue.

    The values equal the legacy literal strings used throughout the widget,
    controller, and tests so the migration is drop-in.
    """

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
