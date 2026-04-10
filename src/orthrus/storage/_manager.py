"""StorageManager — orchestrator for all storage writers.

Responsibilities:
  - Route write_turn() to the correct Parquet + JSONL writers
  - Maintain one writer pair per (session_id, date) pair
  - Flush on interval or when session-date changes
  - Build and write session manifests after each flush
  - Provide hot file discovery and integrity verification
  - Delegate rotation to the rotation module
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import structlog

from orthrus.capture.turn import Turn
from orthrus.config._models import StorageConfig
from orthrus.storage._jsonl import JSONLWriter, jsonl_file_stats
from orthrus.storage._manifest import (
    FileEntry,
    build_file_entry,
    build_manifest,
    read_manifest,
    write_manifest,
)
from orthrus.storage._parquet import ParquetWriter, parquet_file_stats
from orthrus.storage._paths import StoragePaths
from orthrus.storage._rotation import RotationResult, rotate

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class StorageError(Exception):
    """Base exception for storage errors."""


class DiskFullError(StorageError):
    """Raised when disk space is exhausted."""


# ---------------------------------------------------------------------------
# TurnRecord — public alias
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TurnRecord:
    """A Turn with its storage location metadata.

    Returned by StorageManager.write_turn() so callers know where
    the turn was written.
    """

    turn: Turn
    parquet_path: Path
    jsonl_path: Path


# ---------------------------------------------------------------------------
# Active writers tracking
# ---------------------------------------------------------------------------


@dataclass
class _SessionWriters:
    """Managed writers for one (session_id, date) pair."""

    parquet: ParquetWriter
    jsonl: JSONLWriter
    first_write: datetime
    num_turns: int = 0


# ---------------------------------------------------------------------------
# StorageManager
# ---------------------------------------------------------------------------


class StorageManager:
    """Manages durable persistence of Turn records.

    Coordinates Parquet, JSONL, and manifest writes. Rotation is
    triggered on demand (not automatically).

    Thread-safe for writes from a single producer.
    """

    def __init__(
        self,
        config: StorageConfig,
        paths: StoragePaths | None = None,
        flush_interval_seconds: int = 60,
    ) -> None:
        """Initialize the StorageManager.

        Args:
            config: Validated StorageConfig from orthrus.config.
            paths: StoragePaths. If None, resolved from config.
            flush_interval_seconds: Flush writers after this many seconds
                                   of inactivity (per session-date).
        """
        self._config = config
        self._paths = paths or StoragePaths.resolve()
        self._flush_interval = flush_interval_seconds

        # Active writers: key = (session_id, date_str "YYYY-MM-DD")
        self._writers: dict[tuple[str, str], _SessionWriters] = {}
        self._lock = threading.Lock()

        # Track last flush time per session for interval flushing
        self._last_flush: dict[tuple[str, str], float] = {}

        # Stats
        self._total_turns_written = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def write_turn(self, turn: Turn) -> TurnRecord:
        """Write a single Turn to Parquet and JSONL.

        Creates or appends to the appropriate session-date files.
        Flushes and manifests after each call; interval flush is handled
        by the caller or a background thread.

        Args:
            turn: A validated Turn instance.

        Returns:
            TurnRecord with paths to the written files.

        Raises:
            DiskFullError: If a write fails due to disk space.
            StorageError: If the file cannot be written.
        """
        key = (turn.session_id, turn.timestamp.strftime("%Y-%m-%d"))

        with self._lock:
            writers = self._get_or_create_writers(key, turn)

            try:
                writers.parquet.write(turn)
                writers.jsonl.write(turn)
                writers.num_turns += 1
                self._total_turns_written += 1
            except OSError as exc:
                if _is_disk_full(exc):
                    raise DiskFullError(f"Disk full writing {turn.trace_id}") from exc
                raise StorageError(f"Failed to write {turn.trace_id}: {exc}") from exc

            # Update flush timestamp
            self._last_flush[key] = time.monotonic()

        return TurnRecord(
            turn=turn,
            parquet_path=writers.parquet._path,
            jsonl_path=writers.jsonl._path,
        )

    def flush(self) -> None:
        """Flush all open writers and write manifests.

        Call this on a timer or before shutdown.
        """
        with self._lock:
            for key, writers in list(self._writers.items()):
                self._flush_writers(writers)
                # Write manifest for this session-date
                session_id, date_str = key
                ts = writers.first_write
                manifest_path = self._paths.capture_for_date(ts) / self._paths.manifest_filename(
                    session_id, ts
                )
                self._write_manifest(writers, session_id, ts, manifest_path)
                del self._writers[key]
                self._last_flush.pop(key, None)

    def rotate(self) -> RotationResult:
        """Execute rotation policy: hot → warm → archive.

        Returns:
            RotationResult with actions taken and any errors.
        """
        result = rotate(
            capture_dir=self._paths.capture,
            warm_dir=self._paths.warm,
            archive_dir=self._paths.archive,
            hot_max_days=self._config.hot_max_days,
            warm_max_days=self._config.warm_max_days,
            warm_compression=self._config.warm_compression,
            warm_compression_level=self._config.warm_compression_level,
            archive_compression=self._config.archive_compression,
            archive_compression_level=self._config.archive_compression_level,
        )
        logger.info("rotation_complete", result=result)
        return result

    def get_hot_files(
        self,
        since: datetime | None = None,
    ) -> list[Path]:
        """List hot storage files, optionally filtered by time.

        Args:
            since: If set, only return files from dates >= this timestamp (UTC).

        Returns:
            Sorted list of Parquet and JSONL file paths.
        """
        files: list[Path] = []
        capture = self._paths.capture

        if not capture.is_dir():
            return files

        for yyyy_dir in capture.iterdir():
            if not yyyy_dir.is_dir() or not yyyy_dir.name.isdigit():
                continue
            for mm_dir in yyyy_dir.iterdir():
                if not mm_dir.is_dir() or not mm_dir.name.isdigit():
                    continue
                for dd_dir in mm_dir.iterdir():
                    if not dd_dir.is_dir() or not dd_dir.name.isdigit():
                        continue
                    if since is not None:
                        try:
                            file_date = datetime(
                                int(yyyy_dir.name),
                                int(mm_dir.name),
                                int(dd_dir.name),
                                tzinfo=UTC,
                            )
                            if file_date < since.astimezone(UTC):
                                continue
                        except ValueError:
                            continue
                    for f in dd_dir.iterdir():
                        if f.suffix in (".parquet", ".jsonl"):
                            files.append(f)

        files.sort()
        return files

    def verify_integrity(self, file: Path) -> bool:
        """Verify a file's checksum against its session manifest.

        Returns:
            True if the file matches its manifest entry, False if the
            manifest is missing, the file is missing, or checksums differ.
        """
        # The manifest sits alongside its data files and is the only -manifest.json
        candidates = list(file.parent.glob("*-manifest.json"))
        if not candidates:
            return False
        manifest_path = candidates[0]

        manifest = read_manifest(manifest_path)
        entry_name = file.name
        for entry in manifest.files:
            if entry.name == entry_name:
                return verify_file(file, entry.checksum)
        return False

    @property
    def total_turns_written(self) -> int:
        """Total number of turns written since initialization."""
        return self._total_turns_written

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get_or_create_writers(
        self,
        key: tuple[str, str],
        turn: Turn,
    ) -> _SessionWriters:
        """Get or create writer pair for a session-date."""
        if key in self._writers:
            return self._writers[key]

        session_id, date_str = key
        # Parse date for directory
        ts = turn.timestamp.astimezone(UTC)
        capture_dir = self._paths.capture_for_date(ts)

        pq_name = self._paths.turns_filename(turn.session_id, turn.timestamp)
        jsonl_name = self._paths.trajectories_filename(turn.session_id, turn.timestamp)

        parquet_path = capture_dir / pq_name
        jsonl_path = capture_dir / jsonl_name

        writers = _SessionWriters(
            parquet=ParquetWriter(
                path=parquet_path,
                row_group_size=self._config.parquet_row_group_size,
            ),
            jsonl=JSONLWriter(path=jsonl_path),
            first_write=ts,
        )

        self._writers[key] = writers
        logger.debug("opened_writers", session=session_id, date=date_str)
        return writers

    def _flush_writers(self, writers: _SessionWriters) -> None:
        """Flush and close a writer pair, write manifest."""
        try:
            writers.parquet.close()
            writers.jsonl.close()
            logger.debug(
                "flushed_writers",
                parquet=str(writers.parquet._path),
                turns=writers.num_turns,
            )
        except Exception as exc:
            logger.error("flush_error", error=str(exc))

    def _write_manifest(
        self,
        writers: _SessionWriters,
        session_id: str,
        ts: datetime,
        manifest_path: Path,
    ) -> None:
        """Write manifest.json for the current session-date.

        Args:
            writers: Active writer pair.
            session_id: Session identifier.
            ts: Timestamp used for date partitioning.
            manifest_path: Where to write the manifest JSON.
        """
        date_str = ts.strftime("%Y-%m-%d")
        pq_path = writers.parquet._path
        jsonl_path = writers.jsonl._path

        file_entries: list[FileEntry] = []

        if pq_path.is_file():
            try:
                stats = parquet_file_stats(pq_path)
                file_entries.append(build_file_entry(pq_path, cast(int, stats["num_rows"])))
            except Exception as exc:
                logger.warning("manifest_parquet_stat_failed", path=str(pq_path), error=str(exc))

        if jsonl_path.is_file():
            try:
                stats = jsonl_file_stats(jsonl_path)
                file_entries.append(FileEntry(
                    name=jsonl_path.name,
                    checksum=f"sha256:{_sha256_hex(jsonl_path)}",
                    size_bytes=cast(int, stats["size_bytes"]),
                    num_rows=cast(int, stats["num_lines"]),
                    type="jsonl",
                ))
            except Exception as exc:
                logger.warning("manifest_jsonl_stat_failed", path=str(jsonl_path), error=str(exc))

        if file_entries:
            manifest = build_manifest(session_id, date_str, file_entries)
            write_manifest(manifest, manifest_path)

    def __enter__(self) -> StorageManager:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        """Flush all writers and release resources."""
        self.flush()


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _is_disk_full(exc: OSError) -> bool:
    """Return True if an OSError indicates disk full."""
    import errno
    return exc.errno in (
        errno.ENOSPC,
        errno.EDQUOT,
    )


def _sha256_hex(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(1_048_576):
            h.update(chunk)
    return h.hexdigest()


def verify_file(path: Path, expected_checksum: str) -> bool:
    """Verify a file against a "sha256:{hex}" checksum."""
    if not path.is_file():
        return False
    actual = _sha256_hex(path)
    expected = expected_checksum.removeprefix("sha256:")
    return actual == expected


__all__ = [
    "StorageManager",
    "TurnRecord",
    "StoragePaths",
    "StorageError",
    "DiskFullError",
]
