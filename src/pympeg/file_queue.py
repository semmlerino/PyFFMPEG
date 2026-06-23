#!/usr/bin/env python3
"""Pure file-queue model and display formatters for the file list.

This module is the single source of truth for the queue's domain state. It has
no Qt dependency, so it can be unit-tested directly and reasoned about without a
running QApplication. ``FileListWidget`` renders its ``QListWidgetItem`` views
from this model instead of smearing status/progress/metadata across per-item
``UserRole`` slots and a parallel ``metadata_cache`` dict (Finding #5).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pympeg.domain.status import FileStatus

if TYPE_CHECKING:
    from pympeg.metadata.probe import VideoMetadata


@dataclass
class FileEntry:
    """All domain state for a single queued file."""

    path: str
    status: FileStatus = FileStatus.PENDING
    progress: int = 0
    metadata: VideoMetadata | None = None
    # Tracks whether async metadata extraction has been dispatched, so the
    # worker is started at most once per file (replaces the old "present in
    # metadata_cache" sentinel).
    metadata_requested: bool = False


class FileQueueModel:
    """Ordered store of :class:`FileEntry` keyed by path.

    Backed by a single insertion-ordered ``dict`` (Python 3.7+ preserves
    insertion order). Display order is simply the dict's iteration order, so
    lookups stay O(1) without a parallel ``path -> index`` map to keep in sync.
    """

    def __init__(self) -> None:
        self._entries: dict[str, FileEntry] = {}

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, path: str) -> bool:
        return path in self._entries

    def add(self, path: str) -> FileEntry | None:
        """Append a new pending entry; return it, or ``None`` if already present."""
        if path in self._entries:
            return None
        entry = FileEntry(path=path)
        self._entries[path] = entry
        return entry

    def get(self, path: str) -> FileEntry | None:
        """Return the (mutable) entry for ``path``, or ``None`` if absent."""
        return self._entries.get(path)

    def remove(self, path: str) -> bool:
        """Remove ``path`` if present; return whether anything was removed."""
        return self._entries.pop(path, None) is not None

    def clear(self) -> None:
        """Drop all entries."""
        self._entries.clear()

    def paths_in_order(self) -> list[str]:
        """Return file paths in current display order."""
        return list(self._entries)

    def entries_in_order(self) -> list[FileEntry]:
        """Return a shallow copy of the entries in current display order."""
        return list(self._entries.values())

    def reorder(self, ordered_paths: list[str]) -> None:
        """Reorder entries to match ``ordered_paths`` (e.g. after a view move).

        Paths not present in the model are ignored; entries whose path is not
        named in ``ordered_paths`` keep their relative order and are appended at
        the end, so the model can never silently lose an entry.
        """
        new_entries: dict[str, FileEntry] = {}
        for path in ordered_paths:
            entry = self._entries.get(path)
            if entry is not None and path not in new_entries:
                new_entries[path] = entry
        for path, entry in self._entries.items():
            if path not in new_entries:
                new_entries[path] = entry
        self._entries = new_entries

    def paths_with_status(self, status: FileStatus) -> list[str]:
        """Return paths whose entry has the given status, in display order."""
        return [path for path, entry in self._entries.items() if entry.status == status]

    def status_counts(self) -> dict[FileStatus, int]:
        """Return a count of entries per :class:`FileStatus` (all keys present)."""
        counts = Counter(entry.status for entry in self._entries.values())
        return {status: counts.get(status, 0) for status in FileStatus}


def format_file_with_metadata(filename: str, metadata: VideoMetadata) -> str:
    """Join a filename with its available metadata parts using ``•`` separators."""
    parts = [filename]

    if metadata.get("duration") != "Unknown":
        parts.append(metadata["duration"])

    width = metadata.get("width", 0)
    height = metadata.get("height", 0)
    if width > 0 and height > 0:
        parts.append(f"{width}x{height}")

    codec = metadata.get("codec", "").upper()
    if codec and codec != "UNKNOWN":
        parts.append(codec)

    bitrate = metadata.get("bitrate", "")
    if bitrate and bitrate != "Unknown":
        parts.append(bitrate)

    return " • ".join(parts)


def compute_display(filename: str, entry: FileEntry) -> str:
    """Build the list-item display text for ``entry`` (status + progress + metadata)."""
    metadata = entry.metadata

    if entry.status == FileStatus.PENDING:
        if metadata:
            return f"⏳ {format_file_with_metadata(filename, metadata)}"
        return f"🔄 {filename} • Loading..."
    if entry.status == FileStatus.PROCESSING:
        if metadata:
            return f"🚀 {format_file_with_metadata(filename, metadata)} — {entry.progress}%"
        return f"🚀 {filename} — {entry.progress}%"
    if entry.status == FileStatus.COMPLETED:
        return f"✅ {filename} — Completed"
    if entry.status == FileStatus.FAILED:
        return f"❌ {filename} — Failed"
    if entry.status == FileStatus.SKIPPED:
        return f"⏭️ {filename} — Skipped"
    return filename
