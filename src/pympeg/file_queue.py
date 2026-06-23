#!/usr/bin/env python3
"""Pure file-queue model and display formatters for the file list.

This module is the single source of truth for the queue's domain state. It has
no Qt dependency, so it can be unit-tested directly and reasoned about without a
running QApplication. ``FileListWidget`` renders its ``QListWidgetItem`` views
from this model instead of smearing status/progress/metadata across per-item
``UserRole`` slots and a parallel ``metadata_cache`` dict (Finding #5).
"""

from __future__ import annotations

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

    Maintains a ``path -> index`` map kept in sync with the entry order so
    lookups stay O(1) while display order is preserved across reordering.
    """

    def __init__(self) -> None:
        self._entries: list[FileEntry] = []
        self._index: dict[str, int] = {}

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, path: str) -> bool:
        return path in self._index

    def add(self, path: str) -> FileEntry | None:
        """Append a new pending entry; return it, or ``None`` if already present."""
        if path in self._index:
            return None
        entry = FileEntry(path=path)
        self._index[path] = len(self._entries)
        self._entries.append(entry)
        return entry

    def get(self, path: str) -> FileEntry | None:
        """Return the (mutable) entry for ``path``, or ``None`` if absent."""
        idx = self._index.get(path)
        return self._entries[idx] if idx is not None else None

    def remove(self, path: str) -> bool:
        """Remove ``path`` if present; return whether anything was removed."""
        idx = self._index.get(path)
        if idx is None:
            return False
        del self._entries[idx]
        self._reindex()
        return True

    def clear(self) -> None:
        """Drop all entries."""
        self._entries.clear()
        self._index.clear()

    def paths_in_order(self) -> list[str]:
        """Return file paths in current display order."""
        return [e.path for e in self._entries]

    def entries_in_order(self) -> list[FileEntry]:
        """Return a shallow copy of the entries in current display order."""
        return list(self._entries)

    def reorder(self, ordered_paths: list[str]) -> None:
        """Reorder entries to match ``ordered_paths`` (e.g. after a view move).

        Paths not present in the model are ignored; entries whose path is not
        named in ``ordered_paths`` keep their relative order and are appended at
        the end, so the model can never silently lose an entry.
        """
        by_path = {e.path: e for e in self._entries}
        new_entries: list[FileEntry] = []
        seen: set[str] = set()
        for path in ordered_paths:
            entry = by_path.get(path)
            if entry is not None and path not in seen:
                new_entries.append(entry)
                seen.add(path)
        for entry in self._entries:
            if entry.path not in seen:
                new_entries.append(entry)
                seen.add(entry.path)
        self._entries = new_entries
        self._reindex()

    def paths_with_status(self, status: FileStatus) -> list[str]:
        """Return paths whose entry has the given status, in display order."""
        return [e.path for e in self._entries if e.status == status]

    def status_counts(self) -> dict[FileStatus, int]:
        """Return a count of entries per :class:`FileStatus` (all keys present)."""
        counts = dict.fromkeys(FileStatus, 0)
        for entry in self._entries:
            counts[entry.status] += 1
        return counts

    def _reindex(self) -> None:
        self._index = {e.path: i for i, e in enumerate(self._entries)}


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
