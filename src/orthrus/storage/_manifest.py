"""SHA-256 manifest per session file.

Each capture day produces one manifest.json listing:
  - parquet and jsonl files written
  - their SHA-256 checksums
  - row counts and timestamps

Format:
{
  "version": 1,
  "session_id": "...",
  "date": "YYYY-MM-DD",
  "generated_at": "...",
  "files": [
    {
      "name": "session-YYYYMMDD-turns.parquet",
      "checksum": "sha256:...",
      "size_bytes": 12345,
      "num_rows": 100,
      "type": "parquet"
    },
    ...
  ]
}
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

_MANIFEST_VERSION = 1


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FileEntry:
    """Checksummed file in a session manifest."""

    name: str
    checksum: str  # "sha256:{hex}"
    size_bytes: int
    num_rows: int
    type: str  # "parquet" | "jsonl"


@dataclass(frozen=True)
class Manifest:
    """Session-level manifest covering all files for one session-date."""

    version: int
    session_id: str
    date: str  # "YYYY-MM-DD"
    generated_at: str
    files: tuple[FileEntry, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "session_id": self.session_id,
            "date": self.date,
            "generated_at": self.generated_at,
            "files": [asdict(f) for f in self.files],
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256_hex(path: Path) -> str:
    """Compute SHA-256 hex digest of a file.

    Reads in 1MB chunks to handle large files without memory pressure.
    """
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(1_048_576):
            h.update(chunk)
    return h.hexdigest()


def _file_type(name: str) -> str:
    """Infer file type from extension."""
    if name.endswith(".parquet"):
        return "parquet"
    if name.endswith(".jsonl"):
        return "jsonl"
    return "unknown"


def build_file_entry(path: Path, num_rows: int) -> FileEntry:
    """Build a FileEntry for an existing file on disk."""
    checksum = _sha256_hex(path)
    return FileEntry(
        name=path.name,
        checksum=f"sha256:{checksum}",
        size_bytes=path.stat().st_size,
        num_rows=num_rows,
        type=_file_type(path.name),
    )


def build_manifest(
    session_id: str,
    date: str,
    files: list[FileEntry],
) -> Manifest:
    """Build a Manifest for a session-date."""
    return Manifest(
        version=_MANIFEST_VERSION,
        session_id=session_id,
        date=date,
        generated_at=datetime.now(UTC).isoformat(),
        files=tuple(files),
    )


# ---------------------------------------------------------------------------
# Write / read
# ---------------------------------------------------------------------------


def write_manifest(manifest: Manifest, path: Path) -> None:
    """Write manifest JSON to disk (overwrites existing)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")
    tmp.rename(path)
    logger.debug("manifest_written", path=str(path))


def read_manifest(path: Path) -> Manifest:
    """Read and parse a manifest JSON file."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)

    files = tuple(
        FileEntry(
            name=f["name"],
            checksum=f["checksum"],
            size_bytes=f["size_bytes"],
            num_rows=f["num_rows"],
            type=f["type"],
        )
        for f in data["files"]
    )

    return Manifest(
        version=data["version"],
        session_id=data["session_id"],
        date=data["date"],
        generated_at=data["generated_at"],
        files=files,
    )


# ---------------------------------------------------------------------------
# Integrity verification
# ---------------------------------------------------------------------------


def verify_file(path: Path, expected_checksum: str) -> bool:
    """Verify a file against a "sha256:{hex}" checksum.

    Returns:
        True if the file matches, False otherwise.
    """
    if not path.is_file():
        return False

    actual = _sha256_hex(path)
    expected = expected_checksum.removeprefix("sha256:")
    return actual == expected


def verify_manifest_integrity(manifest: Manifest, base_dir: Path) -> dict[str, bool]:
    """Verify all files listed in a manifest against their checksums.

    Returns:
        Dict mapping filename -> True if valid, False otherwise.
    """
    results: dict[str, bool] = {}
    for entry in manifest.files:
        file_path = base_dir / entry.name
        results[entry.name] = verify_file(file_path, entry.checksum)
    return results
