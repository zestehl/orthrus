"""Base class for sync targets — shared compression logic."""

from __future__ import annotations

import shutil
import subprocess
from abc import abstractmethod
from pathlib import Path

import structlog

from orthrus.sync._models import SyncError, SyncTarget

__all__ = ["BaseSyncTarget", "SyncError"]

logger = structlog.get_logger(__name__)


class BaseSyncTarget(SyncTarget):
    """Base class for sync targets.

    Provides shared compression utilities using zstandard.
    Subclasses must implement push/pull/verify/name properties.
    """

    def __init__(
        self,
        *,
        compression: str = "zstd",
        compression_level: int = 3,
    ) -> None:
        self._compression = compression
        self._compression_level = compression_level

    @abstractmethod
    def push(self, local_path: Path, remote_path: str) -> bool:
        """Push a local file or directory to the remote."""
        ...

    @abstractmethod
    def pull(self, remote_path: str, local_path: Path) -> bool:
        """Pull a remote file or directory to local."""
        ...

    @abstractmethod
    def verify(self, remote_path: str) -> bool:
        """Check if a remote path exists and is accessible."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for this target."""
        ...

    def _compress_file(self, src: Path, dst: Path) -> Path:
        """Compress a file using the configured compression.

        Returns path to the compressed file.
        """
        if self._compression == "none" or not src.is_file():
            if dst != src:
                shutil.copy2(src, dst)
            return dst

        if self._compression == "zstd":
            return self._zstd_compress(src, dst)

        # Unknown compression — copy as-is
        if dst != src:
            shutil.copy2(src, dst)
        return dst

    def _zstd_compress(self, src: Path, dst: Path) -> Path:
        """Compress src into dst using zstd, return compressed path."""
        try:
            import zstandard as zstd
        except ImportError:
            logger.warning("zstd_not_available", target=self.name)
            shutil.copy2(src, dst)
            return dst

        cctx = zstd.ZstdCompressor(level=self._compression_level)
        with open(src, "rb") as fi, open(dst, "wb") as fo:
            cctx.copy_stream(fi, fo)
        return dst

    def _run(
        self,
        cmd: list[str],
        *,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[bytes]:
        """Run a command, raising on non-zero exit.

        Returns CompletedProcess with captured stdout/stderr.
        """
        return subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            check=False,
        )

    def _run_checked(
        self,
        cmd: list[str],
        *,
        cwd: Path | None = None,
    ) -> None:
        """Run a command, raising SyncError on failure."""
        result = self._run(cmd, cwd=cwd)
        if result.returncode != 0:
            msg = result.stderr.decode("utf-8", errors="replace").strip()
            raise SyncError(f"{self.name}: command failed: {' '.join(cmd)}: {msg}")

    def _bytes_for_paths(self, paths: list[Path]) -> int:
        """Sum total size in bytes of the given paths."""
        total = 0
        for p in paths:
            if p.is_file():
                total += p.stat().st_size
            elif p.is_dir():
                for f in p.rglob("*"):
                    if f.is_file():
                        total += f.stat().st_size
        return total
