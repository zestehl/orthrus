"""Rotation: hot → warm → archive tier management.

Rotation is triggered by StorageManager.rotate() and moves files based on age.
This module handles:
  - Discovering hot files older than hot_max_days
  - Compressing them with zstd/lz4
  - Moving to the warm tier
  - Discovering warm files older than warm_max_days
  - Compressing further and moving to archive tier
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

try:
    import zstandard as zstd
    _HAS_ZSTD = True
except ImportError:
    _HAS_ZSTD = False
    zstd = None  # type: ignore[assignment]
from datetime import UTC, datetime, timedelta
from pathlib import Path

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FileRotation:
    """Single file rotation action."""

    source: Path
    destination: Path
    compression: str
    original_size: int
    compressed_size: int


@dataclass(frozen=True)
class RotationResult:
    """Result of a full rotation pass."""

    hot_to_warm: tuple[FileRotation, ...]
    warm_to_archive: tuple[FileRotation, ...]
    errors: tuple[str, ...]

    @property
    def total_moved(self) -> int:
        return len(self.hot_to_warm) + len(self.warm_to_archive)

    @property
    def bytes_saved(self) -> int:
        saved = 0
        for r in self.hot_to_warm:
            saved += r.original_size - r.compressed_size
        for r in self.warm_to_archive:
            saved += r.original_size - r.compressed_size
        return saved


# ---------------------------------------------------------------------------
# Compression helpers
# ---------------------------------------------------------------------------


def _zstd_compress(src: Path, dst: Path, level: int = 3) -> int:
    """Compress src into dst using zstd, return compressed size."""
    if not _HAS_ZSTD:
        raise ImportError(
            "zstandard required for compression. Install with: uv pip install zstandard"
        )
    cctx = zstd.ZstdCompressor(level=level)
    with open(src, "rb") as fi, open(dst, "wb") as fo:
        cctx.copy_stream(fi, fo)
    return dst.stat().st_size


def _zstd_decompress(src: Path, dst: Path) -> int:
    """Decompress a zstd-compressed src into dst, return decompressed size."""
    if not _HAS_ZSTD:
        raise ImportError(
            "zstandard required for decompression. Install with: uv pip install zstandard"
        )
    dctx = zstd.ZstdDecompressor()
    with open(src, "rb") as fi, open(dst, "wb") as fo:
        dctx.copy_stream(fi, fo)
    return dst.stat().st_size


# ---------------------------------------------------------------------------
# Discovery helpers
# ---------------------------------------------------------------------------


def _hot_files(capture_dir: Path, hot_max_days: int) -> list[Path]:
    """Find hot parquet/jsonl files older than hot_max_days."""
    cutoff = datetime.now(UTC) - timedelta(days=hot_max_days)
    cutoff_date = cutoff.date()
    files: list[Path] = []

    if not capture_dir.is_dir():
        return files

    for yyyy_dir in capture_dir.iterdir():
        if not yyyy_dir.is_dir() or not yyyy_dir.name.isdigit():
            continue
        for mm_dir in yyyy_dir.iterdir():
            if not mm_dir.is_dir() or not mm_dir.name.isdigit():
                continue
            for dd_dir in mm_dir.iterdir():
                if not dd_dir.is_dir() or not dd_dir.name.isdigit():
                    continue
                try:
                    file_date = datetime(
                        int(yyyy_dir.name),
                        int(mm_dir.name),
                        int(dd_dir.name),
                        tzinfo=UTC,
                    ).date()
                except ValueError:
                    continue
                if file_date < cutoff_date:
                    for f in dd_dir.iterdir():
                        if f.suffix in (".parquet", ".jsonl"):
                            files.append(f)
    return files


def _warm_files(warm_dir: Path, warm_max_days: int) -> list[Path]:
    """Find warm .parquet.zst / .jsonl.zst files older than warm_max_days."""
    cutoff = datetime.now(UTC) - timedelta(days=warm_max_days)
    cutoff_ts = cutoff.timestamp()
    files: list[Path] = []

    if not warm_dir.is_dir():
        return files

    for f in warm_dir.rglob("*.zst"):
        if f.stat().st_mtime < cutoff_ts:
            files.append(f)
    return files


# ---------------------------------------------------------------------------
# Rotation logic
# ---------------------------------------------------------------------------


def rotate(
    capture_dir: Path,
    warm_dir: Path,
    archive_dir: Path,
    hot_max_days: int,
    warm_max_days: int,
    warm_compression: str,
    warm_compression_level: int,
    archive_compression: str,
    archive_compression_level: int,
) -> RotationResult:
    """Execute one rotation pass across all tiers.

    Returns:
        RotationResult with all actions taken and any errors.
    """
    hot_to_warm: list[FileRotation] = []
    warm_to_archive: list[FileRotation] = []
    errors: list[str] = []

    # ---- hot → warm ----
    hot_files = _hot_files(capture_dir, hot_max_days)
    for src in hot_files:
        try:
            # Compute destination: same session-date structure under warm/YYYY/MM/
            date_parts = src.parent.name, src.parent.parent.name, src.parent.parent.parent.name
            year, month = date_parts[2], date_parts[1]
            warm_subdir = warm_dir / year / month
            warm_subdir.mkdir(parents=True, exist_ok=True)

            dst_name = src.stem  # strip .parquet
            if warm_compression == "zstd":
                dst = warm_subdir / f"{dst_name}.zst"
                size = _zstd_compress(src, dst, level=warm_compression_level)
            else:
                # lz4 not yet implemented; fall back to copy
                dst = warm_subdir / f"{dst_name}{src.suffix}"
                dst.write_bytes(src.read_bytes())
                size = dst.stat().st_size

            hot_to_warm.append(FileRotation(
                source=src,
                destination=dst,
                compression=warm_compression,
                original_size=src.stat().st_size,
                compressed_size=size,
            ))
            # Remove original after successful compression
            src.unlink()
        except Exception as exc:  # pragma: no cover
            errors.append(f"hot→warm {src}: {exc}")
            logger.warning("rotation_error", source=str(src), error=str(exc))

    # ---- warm → archive ----
    warm_files = _warm_files(warm_dir, warm_max_days)
    for src in warm_files:
        try:
            # Archive uses quarter grouping
            mtime = datetime.fromtimestamp(src.stat().st_mtime, tz=UTC)
            quarter = (mtime.month - 1) // 3 + 1
            archive_subdir = archive_dir / f"{mtime.year:04d}" / f"Q{quarter}"
            archive_subdir.mkdir(parents=True, exist_ok=True)

            dst_name = src.stem  # strip .zst
            if archive_compression == "zstd":
                dst = archive_subdir / f"{dst_name}.zst"
                size = _zstd_compress(src, dst, level=archive_compression_level)
            else:
                dst = archive_subdir / src.name
                dst.write_bytes(src.read_bytes())
                size = dst.stat().st_size

            warm_to_archive.append(FileRotation(
                source=src,
                destination=dst,
                compression=archive_compression,
                original_size=src.stat().st_size,
                compressed_size=size,
            ))
            src.unlink()
        except Exception as exc:  # pragma: no cover
            errors.append(f"warm→archive {src}: {exc}")
            logger.warning("rotation_error", source=str(src), error=str(exc))

    return RotationResult(
        hot_to_warm=tuple(hot_to_warm),
        warm_to_archive=tuple(warm_to_archive),
        errors=tuple(errors),
    )
