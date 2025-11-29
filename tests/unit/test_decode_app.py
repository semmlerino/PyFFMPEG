"""Tests for decode_app module - bundle decoding with cleanup on failure."""

from __future__ import annotations

import base64
import io
import tarfile
from pathlib import Path

from decode_app import _cleanup_partial_extraction, decode_bundle


class TestCleanupPartialExtraction:
    """Tests for _cleanup_partial_extraction helper."""

    def test_cleanup_removes_partial_directory(self, tmp_path: Path) -> None:
        """Cleanup removes partial extraction directory."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Create a "partial extraction"
        partial = output_dir / "bundle_root"
        partial.mkdir()
        (partial / "file.txt").write_text("partial")

        _cleanup_partial_extraction(str(output_dir), "bundle_root")

        assert not partial.exists()

    def test_cleanup_does_nothing_if_no_root_name(self, tmp_path: Path) -> None:
        """Cleanup is a no-op when root_name is None."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Should not raise
        _cleanup_partial_extraction(str(output_dir), None)

    def test_cleanup_handles_missing_directory(self, tmp_path: Path) -> None:
        """Cleanup handles case where partial dir doesn't exist."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Should not raise even if directory doesn't exist
        _cleanup_partial_extraction(str(output_dir), "nonexistent")


class TestDecodeBundleCleanup:
    """Tests for decode_bundle cleanup on failure."""

    def _create_valid_bundle(self, tmp_path: Path) -> Path:
        """Create a valid base64-encoded tar.gz bundle."""
        # Create a folder to encode
        source = tmp_path / "source"
        source.mkdir()
        (source / "file.txt").write_text("content")

        # Create tar.gz in memory
        tar_buffer = io.BytesIO()
        with tarfile.open(fileobj=tar_buffer, mode="w:gz") as tar:
            tar.add(str(source), arcname="source")

        # Encode to base64
        tar_buffer.seek(0)
        encoded = base64.b64encode(tar_buffer.read()).decode("utf-8")

        # Write to file
        bundle_file = tmp_path / "bundle.txt"
        bundle_file.write_text(encoded)

        return bundle_file

    def test_decode_bundle_success(self, tmp_path: Path) -> None:
        """Successful decode extracts files."""
        bundle = self._create_valid_bundle(tmp_path)
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        result = decode_bundle(str(bundle), str(output_dir))

        assert result is True
        assert (output_dir / "source" / "file.txt").exists()

    def test_decode_bundle_invalid_base64_returns_false(
        self, tmp_path: Path
    ) -> None:
        """Invalid base64 returns False."""
        bundle_file = tmp_path / "invalid.txt"
        bundle_file.write_text("not valid base64!!!")

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        result = decode_bundle(str(bundle_file), str(output_dir))

        assert result is False

    def test_decode_bundle_missing_file_returns_false(self) -> None:
        """Missing bundle file returns False."""
        result = decode_bundle("/nonexistent/bundle.txt", "/tmp")
        assert result is False

    def test_decode_bundle_list_only_does_not_extract(
        self, tmp_path: Path
    ) -> None:
        """list_only=True lists contents without extracting."""
        bundle = self._create_valid_bundle(tmp_path)
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        result = decode_bundle(str(bundle), str(output_dir), list_only=True)

        assert result is True
        # Should NOT have extracted
        assert not (output_dir / "source").exists()
