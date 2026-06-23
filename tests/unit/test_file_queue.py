#!/usr/bin/env python3
"""Unit tests for the pure file-queue model and display formatters.

These types carry no Qt dependency, so they are tested directly without a
QApplication. They are the single source of truth that FileListWidget renders
from (Finding #5 — state was previously smeared across QListWidgetItem
UserRoles and side cache dicts).
"""

from pympeg.domain.status import FileStatus
from pympeg.file_queue import (
    FileEntry,
    FileQueueModel,
    compute_display,
    format_file_with_metadata,
)


class TestFileEntry:
    def test_defaults(self):
        entry = FileEntry(path="/test/video.ts")
        assert entry.path == "/test/video.ts"
        assert entry.status == FileStatus.PENDING
        assert entry.progress == 0
        assert entry.metadata is None
        assert entry.metadata_requested is False


class TestFileQueueModel:
    def test_add_returns_entry_and_dedupes(self):
        model = FileQueueModel()
        entry = model.add("/a.ts")
        assert entry is not None
        assert entry.path == "/a.ts"
        assert len(model) == 1
        assert "/a.ts" in model

        # Duplicate path is rejected and returns None
        assert model.add("/a.ts") is None
        assert len(model) == 1

    def test_get_missing_returns_none(self):
        model = FileQueueModel()
        assert model.get("/missing.ts") is None

    def test_get_returns_same_mutable_entry(self):
        model = FileQueueModel()
        _ = model.add("/a.ts")
        entry = model.get("/a.ts")
        assert entry is not None
        entry.status = FileStatus.PROCESSING
        # Mutation is visible through a second lookup (single store)
        assert model.get("/a.ts").status == FileStatus.PROCESSING

    def test_remove(self):
        model = FileQueueModel()
        _ = model.add("/a.ts")
        _ = model.add("/b.ts")
        assert model.remove("/a.ts") is True
        assert "/a.ts" not in model
        assert len(model) == 1
        # Index stays consistent after removal
        assert model.get("/b.ts") is not None
        assert model.paths_in_order() == ["/b.ts"]

    def test_remove_missing_returns_false(self):
        model = FileQueueModel()
        assert model.remove("/missing.ts") is False

    def test_clear(self):
        model = FileQueueModel()
        _ = model.add("/a.ts")
        _ = model.add("/b.ts")
        model.clear()
        assert len(model) == 0
        assert model.paths_in_order() == []

    def test_paths_in_order_preserves_insertion_order(self):
        model = FileQueueModel()
        for p in ("/a.ts", "/b.ts", "/c.ts"):
            _ = model.add(p)
        assert model.paths_in_order() == ["/a.ts", "/b.ts", "/c.ts"]

    def test_reorder_matches_given_order(self):
        model = FileQueueModel()
        for p in ("/a.ts", "/b.ts", "/c.ts"):
            _ = model.add(p)
        model.reorder(["/c.ts", "/a.ts", "/b.ts"])
        assert model.paths_in_order() == ["/c.ts", "/a.ts", "/b.ts"]
        # Index map stays in sync so lookups/removals still resolve
        assert model.remove("/a.ts") is True
        assert model.paths_in_order() == ["/c.ts", "/b.ts"]

    def test_reorder_appends_unnamed_entries(self):
        model = FileQueueModel()
        for p in ("/a.ts", "/b.ts", "/c.ts"):
            _ = model.add(p)
        # Only name two; the third keeps its place at the end
        model.reorder(["/b.ts", "/a.ts"])
        assert model.paths_in_order() == ["/b.ts", "/a.ts", "/c.ts"]

    def test_paths_with_status(self):
        model = FileQueueModel()
        for p in ("/a.ts", "/b.ts", "/c.ts"):
            _ = model.add(p)
        model.get("/a.ts").status = FileStatus.COMPLETED
        model.get("/c.ts").status = FileStatus.COMPLETED
        assert model.paths_with_status(FileStatus.COMPLETED) == ["/a.ts", "/c.ts"]
        assert model.paths_with_status(FileStatus.PENDING) == ["/b.ts"]

    def test_status_counts(self):
        model = FileQueueModel()
        for p in ("/a.ts", "/b.ts", "/c.ts", "/d.ts"):
            _ = model.add(p)
        model.get("/a.ts").status = FileStatus.COMPLETED
        model.get("/b.ts").status = FileStatus.PROCESSING
        model.get("/c.ts").status = FileStatus.FAILED
        # /d.ts stays pending
        counts = model.status_counts()
        assert counts[FileStatus.PENDING] == 1
        assert counts[FileStatus.PROCESSING] == 1
        assert counts[FileStatus.COMPLETED] == 1
        assert counts[FileStatus.FAILED] == 1
        assert counts[FileStatus.SKIPPED] == 0


class TestFormatFileWithMetadata:
    def test_full_metadata(self):
        meta = {
            "duration": "00:10:30",
            "width": 1920,
            "height": 1080,
            "codec": "h264",
            "bitrate": "5000k",
        }
        assert (
            format_file_with_metadata("video.ts", meta)
            == "video.ts • 00:10:30 • 1920x1080 • H264 • 5000k"
        )

    def test_unknown_duration_and_bitrate_skipped(self):
        meta = {
            "duration": "Unknown",
            "width": 1920,
            "height": 1080,
            "codec": "h264",
            "bitrate": "Unknown",
        }
        assert (
            format_file_with_metadata("video.ts", meta) == "video.ts • 1920x1080 • H264"
        )

    def test_zero_resolution_and_empty_fields_skipped(self):
        meta = {
            "duration": "00:01:00",
            "width": 0,
            "height": 0,
            "codec": "",
            "bitrate": "",
        }
        assert format_file_with_metadata("video.ts", meta) == "video.ts • 00:01:00"

    def test_unknown_codec_skipped(self):
        meta = {
            "duration": "00:01:00",
            "width": 1280,
            "height": 720,
            "codec": "unknown",
            "bitrate": "1000k",
        }
        assert (
            format_file_with_metadata("video.ts", meta)
            == "video.ts • 00:01:00 • 1280x720 • 1000k"
        )


class TestComputeDisplay:
    def _entry(self, status: FileStatus, progress: int = 0, metadata=None) -> FileEntry:
        return FileEntry(
            path="/test/video.ts",
            status=status,
            progress=progress,
            metadata=metadata,
        )

    def test_pending_without_metadata(self):
        entry = self._entry(FileStatus.PENDING)
        assert compute_display("video.ts", entry) == "🔄 video.ts • Loading..."

    def test_pending_with_metadata(self):
        meta = {
            "duration": "00:01:00",
            "width": 0,
            "height": 0,
            "codec": "",
            "bitrate": "",
        }
        entry = self._entry(FileStatus.PENDING, metadata=meta)
        assert compute_display("video.ts", entry) == "⏳ video.ts • 00:01:00"

    def test_processing_without_metadata(self):
        entry = self._entry(FileStatus.PROCESSING, progress=50)
        assert compute_display("video.ts", entry) == "🚀 video.ts — 50%"

    def test_processing_with_metadata(self):
        meta = {
            "duration": "00:01:00",
            "width": 0,
            "height": 0,
            "codec": "",
            "bitrate": "",
        }
        entry = self._entry(FileStatus.PROCESSING, progress=75, metadata=meta)
        assert compute_display("video.ts", entry) == "🚀 video.ts • 00:01:00 — 75%"

    def test_completed(self):
        entry = self._entry(FileStatus.COMPLETED)
        assert compute_display("video.ts", entry) == "✅ video.ts — Completed"

    def test_failed(self):
        entry = self._entry(FileStatus.FAILED)
        assert compute_display("video.ts", entry) == "❌ video.ts — Failed"

    def test_skipped(self):
        entry = self._entry(FileStatus.SKIPPED)
        assert compute_display("video.ts", entry) == "⏭️ video.ts — Skipped"
