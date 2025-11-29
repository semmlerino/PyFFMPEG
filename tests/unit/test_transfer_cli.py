"""Tests for transfer_cli module - folder encoding with size limits."""

from __future__ import annotations

from pathlib import Path

import pytest

from transfer_cli import FolderEncoder


class TestFolderEncoderSizeLimit:
    """Tests for folder size limit enforcement."""

    def test_encode_folder_under_limit_succeeds(self, tmp_path: Path) -> None:
        """Encoding a small folder succeeds."""
        # Create a small test folder
        test_folder = tmp_path / "small_folder"
        test_folder.mkdir()
        (test_folder / "file.txt").write_text("small content")

        encoder = FolderEncoder()
        encoded, _chunks = encoder.encode_folder(str(test_folder))

        assert encoded is not None
        assert len(encoded) > 0

    def test_encode_folder_over_limit_raises_value_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Encoding a folder over size limit raises ValueError."""
        # Create a test folder
        test_folder = tmp_path / "large_folder"
        test_folder.mkdir()
        (test_folder / "file.txt").write_text("content")

        # Set a very low limit for testing (1 byte)
        monkeypatch.setattr(FolderEncoder, "MAX_FOLDER_SIZE_MB", 0.000001)

        encoder = FolderEncoder()

        with pytest.raises(ValueError, match="Folder too large to encode"):
            encoder.encode_folder(str(test_folder))

    def test_get_folder_size_calculates_correctly(self, tmp_path: Path) -> None:
        """_get_folder_size returns correct total size."""
        test_folder = tmp_path / "sized_folder"
        test_folder.mkdir()

        # Create files with known sizes
        (test_folder / "file1.txt").write_bytes(b"a" * 100)  # 100 bytes
        (test_folder / "file2.txt").write_bytes(b"b" * 200)  # 200 bytes

        subfolder = test_folder / "sub"
        subfolder.mkdir()
        (subfolder / "file3.txt").write_bytes(b"c" * 50)  # 50 bytes

        encoder = FolderEncoder()
        size = encoder._get_folder_size(test_folder)

        # Total: 100 + 200 + 50 = 350 bytes
        assert size == 350

    def test_get_folder_size_handles_permission_errors(
        self, tmp_path: Path
    ) -> None:
        """_get_folder_size skips files it can't access."""
        test_folder = tmp_path / "mixed_folder"
        test_folder.mkdir()
        (test_folder / "accessible.txt").write_bytes(b"a" * 100)

        encoder = FolderEncoder()
        # Should not raise, even if some files can't be accessed
        size = encoder._get_folder_size(test_folder)

        assert size >= 100

    def test_encode_nonexistent_folder_raises_file_not_found(self) -> None:
        """Encoding nonexistent folder raises FileNotFoundError."""
        encoder = FolderEncoder()

        with pytest.raises(FileNotFoundError, match="Folder not found"):
            encoder.encode_folder("/nonexistent/path/that/does/not/exist")

    def test_encode_file_instead_of_folder_raises_value_error(
        self, tmp_path: Path
    ) -> None:
        """Encoding a file (not folder) raises ValueError."""
        test_file = tmp_path / "file.txt"
        test_file.write_text("content")

        encoder = FolderEncoder()

        with pytest.raises(ValueError, match="not a directory"):
            encoder.encode_folder(str(test_file))

    def test_verbose_mode_reports_size(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Verbose mode reports folder size in output."""
        test_folder = tmp_path / "verbose_folder"
        test_folder.mkdir()
        (test_folder / "file.txt").write_text("content")

        encoder = FolderEncoder(verbose=True)
        encoder.encode_folder(str(test_folder))

        captured = capsys.readouterr()
        # Verbose output includes size in MB
        assert "MB" in captured.err or "Encoding folder" in captured.err
