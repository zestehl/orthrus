"""Storage directory layout and path resolution.

Time-partitioned layout:
  capture/  YYYY/MM/DD/{session_id}-{date}-turns.parquet
             YYYY/MM/DD/{session_id}-{date}-trajectories.jsonl
             YYYY/MM/DD/{session_id}-{date}-manifest.json
  warm/     YYYY/MM/{session_id}-{date}.parquet.zst
  archive/  YYYY/QN/{session_id}-{date}.parquet.zst
"""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from orthrus.config._paths import orthrus_dirs

# ---------------------------------------------------------------------------
# Directory root helpers
# ---------------------------------------------------------------------------


def _ensure_dir(path: Path) -> None:
    """Create directory and all parents, ignoring permission errors."""
    with suppress(OSError):
        path.mkdir(parents=True, exist_ok=True)


def _data_root() -> Path:
    """Root of orthrus data directory (~/.orthrus or XDG equivalent)."""
    dirs = orthrus_dirs()
    # Use legacy ~/.orthrus for data (capture/warm/archive live here)
    legacy = Path.home() / ".orthrus"
    if legacy.exists() or not dirs.data.exists():
        return legacy
    return dirs.data


# --------------------------------------------------------------------------
# Paths dataclass
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class StoragePaths:
    """Resolved storage paths derived from config and data root."""

    root: Path
    capture: Path
    warm: Path
    archive: Path
    derived: Path

    @classmethod
    def resolve(
        cls,
        config_paths: dict[str, str] | None = None,
    ) -> StoragePaths:
        """Resolve storage paths from config overrides or defaults.

        Args:
            config_paths: Optional dict of tier -> path overrides from config.
                          Keys: "capture", "warm", "archive", "derived".
        """
        root = _data_root()
        overrides = config_paths or {}

        capture = cls._resolve_tier(root / "capture", overrides.get("capture"))
        warm = cls._resolve_tier(root / "warm", overrides.get("warm"))
        archive = cls._resolve_tier(root / "archive", overrides.get("archive"))
        derived = cls._resolve_tier(root / "derived", overrides.get("derived"))

        # Ensure directories exist
        for tier_dir in (capture, warm, archive, derived):
            _ensure_dir(tier_dir)

        return cls(
            root=root,
            capture=capture,
            warm=warm,
            archive=archive,
            derived=derived,
        )

    @staticmethod
    def _resolve_tier(default: Path, override: str | None) -> Path:
        if override:
            return Path(override).expanduser().resolve()
        return default

    def capture_for_date(self, timestamp: datetime) -> Path:
        """Return the capture subdirectory for a given UTC timestamp."""
        ts = timestamp.astimezone(UTC)
        return self.capture / f"{ts.year:04d}" / f"{ts.month:02d}" / f"{ts.day:02d}"

    def warm_for_month(self, year: int, month: int) -> Path:
        """Return the warm subdirectory for a given year/month."""
        return self.warm / f"{year:04d}" / f"{month:02d}"

    def archive_for_quarter(self, year: int, quarter: int) -> Path:
        """Return the archive subdirectory for a given year/quarter."""
        return self.archive / f"{year:04d}" / f"Q{quarter}"

    # ------------------------------------------------------------------
    # File name builders
    # ------------------------------------------------------------------

    @staticmethod
    def session_prefix(session_id: str, timestamp: datetime) -> str:
        """Base prefix for session files: {session_id}-{YYYYMMDD}."""
        ts = timestamp.astimezone(UTC)
        # Sanitize session_id for use in filenames
        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in session_id)
        return f"{safe_id}-{ts.strftime('%Y%m%d')}"

    @staticmethod
    def turns_filename(session_id: str, timestamp: datetime) -> str:
        """Parquet filename for a session on a given date."""
        prefix = StoragePaths.session_prefix(session_id, timestamp)
        return f"{prefix}-turns.parquet"

    @staticmethod
    def trajectories_filename(session_id: str, timestamp: datetime) -> str:
        """JSONL filename for a session on a given date."""
        prefix = StoragePaths.session_prefix(session_id, timestamp)
        return f"{prefix}-trajectories.jsonl"

    @staticmethod
    def manifest_filename(session_id: str, timestamp: datetime) -> str:
        """Manifest filename for a session on a given date."""
        prefix = StoragePaths.session_prefix(session_id, timestamp)
        return f"{prefix}-manifest.json"
