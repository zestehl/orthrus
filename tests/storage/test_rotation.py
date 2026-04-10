"""Tests for orthrus.storage._rotation."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import zstandard as zstd

from orthrus.storage._rotation import (
    FileRotation,
    RotationResult,
    _hot_files,
    rotate,
)


@pytest.fixture
def tier_dirs(tmp_path):
    """Create capture, warm, archive directories."""
    capture = tmp_path / "capture"
    warm = tmp_path / "warm"
    archive = tmp_path / "archive"
    capture.mkdir()
    warm.mkdir()
    archive.mkdir()
    return capture, warm, archive


def _write_hot_file(capture_dir: str, year: int, month: int, day: int, content: bytes) -> None:
    """Write a hot parquet file in the time-partitioned structure."""
    d = capture_dir / str(year) / f"{month:02d}" / f"{day:02d}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "session-20260409-turns.parquet").write_bytes(content)


class TestHotFiles:
    """_hot_files discovery."""

    def test_finds_old_files(self, tier_dirs, tmp_path):
        """_hot_files returns files older than hot_max_days."""
        capture, _, _ = tier_dirs

        # Recent file — should NOT be included
        _write_hot_file(capture, 2026, 4, 10, b"recent")

        # Old file (Apr 1, 2026) — should be included
        old_date = datetime.now(UTC).day - 15
        if old_date < 1:
            old_date = 1
        _write_hot_file(capture, 2026, 4, old_date, b"old")

        files = _hot_files(capture, hot_max_days=7)
        assert len(files) == 1
        assert b"old" in files[0].read_bytes()

    def test_empty_capture_dir(self, tier_dirs):
        """_hot_files returns empty list when capture is empty."""
        capture, _, _ = tier_dirs
        files = _hot_files(capture, hot_max_days=7)
        assert files == []


class TestRotationResult:
    """RotationResult dataclass."""

    def test_total_moved(self):
        """total_moved counts both tiers."""
        result = RotationResult(
            hot_to_warm=(
                FileRotation(
                    source="/a.parquet",
                    destination="/a.parquet.zst",
                    compression="zstd",
                    original_size=1000,
                    compressed_size=300,
                ),
            ),
            warm_to_archive=(),
            errors=(),
        )
        assert result.total_moved == 1

    def test_bytes_saved(self):
        """bytes_saved sums compression differences."""
        result = RotationResult(
            hot_to_warm=(
                FileRotation(
                    source="/a.parquet",
                    destination="/a.parquet.zst",
                    compression="zstd",
                    original_size=1000,
                    compressed_size=300,
                ),
            ),
            warm_to_archive=(
                FileRotation(
                    source="/b.parquet.zst",
                    destination="/b.parquet.zst",
                    compression="zstd",
                    original_size=300,
                    compressed_size=100,
                ),
            ),
            errors=(),
        )
        assert result.bytes_saved == (1000 - 300) + (300 - 100)


class TestRotate:
    """Full rotation pipeline."""

    def test_hot_to_warm_compression(self, tier_dirs, tmp_path):
        """Old hot files are compressed and moved to warm."""
        capture, warm, archive = tier_dirs

        # Write an old hot file
        old_date = datetime.now(UTC).day - 15
        if old_date < 1:
            old_date = 1
        _write_hot_file(capture, 2026, 4, old_date, b"x" * 500)

        result = rotate(
            capture_dir=capture,
            warm_dir=warm,
            archive_dir=archive,
            hot_max_days=7,
            warm_max_days=30,
            warm_compression="zstd",
            warm_compression_level=3,
            archive_compression="zstd",
            archive_compression_level=9,
        )

        assert result.total_moved == 1
        rotation = result.hot_to_warm[0]
        assert rotation.compression == "zstd"
        assert rotation.compressed_size < rotation.original_size

        # Source file should be gone
        assert not list(capture.rglob("*.parquet"))

    def test_warm_to_archive(self, tier_dirs, tmp_path):
        """Old warm files are compressed and moved to archive."""
        capture, warm, archive = tier_dirs

        # Create a warm file directly
        warm_subdir = warm / "2026" / "04"
        warm_subdir.mkdir(parents=True)
        warm_file = warm_subdir / "session-20260401-turns.parquet.zst"
        warm_file.write_bytes(b"warm data")

        # Set mtime to 60 days ago
        old_mtime = (datetime.now(UTC).timestamp()) - (60 * 86400)
        warm_file.chmod(0o644)
        import os
        os.utime(warm_file, (old_mtime, old_mtime))

        result = rotate(
            capture_dir=capture,
            warm_dir=warm,
            archive_dir=archive,
            hot_max_days=7,
            warm_max_days=30,
            warm_compression="zstd",
            warm_compression_level=3,
            archive_compression="zstd",
            archive_compression_level=9,
        )

        assert len(result.warm_to_archive) == 1
        assert result.warm_to_archive[0].compression == "zstd"

    def test_zstd_roundtrip(self, tier_dirs, tmp_path):
        """Compressed data can be decompressed correctly."""
        capture, warm, archive = tier_dirs

        original_data = b"This is test data for zstd compression"
        old_date = datetime.now(UTC).day - 15
        if old_date < 1:
            old_date = 1
        _write_hot_file(capture, 2026, 4, old_date, original_data)

        result = rotate(
            capture_dir=capture,
            warm_dir=warm,
            archive_dir=archive,
            hot_max_days=7,
            warm_max_days=30,
            warm_compression="zstd",
            warm_compression_level=3,
            archive_compression="zstd",
            archive_compression_level=9,
        )

        compressed_file = result.hot_to_warm[0].destination
        dctx = zstd.ZstdDecompressor()
        with open(compressed_file, "rb") as fi, open(tmp_path / "decompressed.txt", "wb") as fo:
            dctx.copy_stream(fi, fo)
        decompressed = (tmp_path / "decompressed.txt").read_bytes()

        assert decompressed == original_data
