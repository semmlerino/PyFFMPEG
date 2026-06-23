"""Unit tests for domain.status.FileStatus.

The enum values must stay equal to the literal status strings used throughout
the widget/controller/tests today, so the migration is drop-in.
"""

from domain.status import FileStatus


class TestFileStatus:
    def test_enum_values_equal_legacy_strings(self):
        assert FileStatus.PENDING.value == "pending"
        assert FileStatus.PROCESSING.value == "processing"
        assert FileStatus.COMPLETED.value == "completed"
        assert FileStatus.FAILED.value == "failed"
        assert FileStatus.SKIPPED.value == "skipped"

    def test_all_five_statuses_present(self):
        assert {s.value for s in FileStatus} == {
            "pending",
            "processing",
            "completed",
            "failed",
            "skipped",
        }

    def test_constructible_from_legacy_string(self):
        assert FileStatus("pending") is FileStatus.PENDING
        assert FileStatus("skipped") is FileStatus.SKIPPED
