"""Sync result and target protocol definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


class SyncError(Exception):
    """Raised when a sync operation fails unrecoverably."""


class SyncTarget(Protocol):
    """Pluggable sync target protocol.

    Implement this to add a new sync backend (S3, rsync, etc.).
    """

    def push(self, local_path: Path, remote_path: str) -> bool:
        """Push a local file or directory to the remote.

        Returns True on success, False on failure.
        """
        ...

    def pull(self, remote_path: str, local_path: Path) -> bool:
        """Pull a remote file or directory to local.

        Returns True on success, False on failure.
        """
        ...

    def verify(self, remote_path: str) -> bool:
        """Check if a remote path exists and is accessible.

        Returns True if reachable, False otherwise.
        """
        ...

    @property
    def name(self) -> str:
        """Human-readable name for this target (e.g. 's3:my-bucket')."""
        ...


@dataclass(frozen=True)
class SyncResult:
    """Result of a sync operation across all targets."""

    success: bool
    bytes_transferred: int = 0
    files_transferred: int = 0
    errors: tuple[str, ...] = field(default_factory=tuple)
    target_results: tuple[dict[str, object], ...] = field(default_factory=tuple)

    @property
    def failed(self) -> bool:
        """True if any target had errors."""
        return bool(self.errors)
