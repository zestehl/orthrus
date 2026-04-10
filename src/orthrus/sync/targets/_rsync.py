"""rsync/SSH sync target."""

from __future__ import annotations

from pathlib import Path

import structlog

from orthrus.sync._models import SyncError
from orthrus.sync.targets._base import BaseSyncTarget

logger = structlog.get_logger(__name__)


class RsyncTarget(BaseSyncTarget):
    """Sync to a remote host via rsync over SSH.

    Parameters
    ----------
    host:
        Remote host (e.g. "user@backup.example.com").
    path:
        Remote path (e.g. "/backups/orthrus/").
    user:
        SSH username (optional if embedded in host).
    compression:
        "none" or "zstd". rsync itself handles delta compression.
    compression_level:
        Zstandard level for pre-sync compression of large files.
    ssh_key:
        Path to SSH private key (passed as -i to ssh).
    bandwidth_limit:
        Maximum bandwidth in MB/s (passed to rsync --bwlimit).
    """

    def __init__(
        self,
        *,
        host: str,
        path: str,
        user: str | None = None,
        compression: str = "zstd",
        compression_level: int = 3,
        ssh_key: str | None = None,
        bandwidth_limit: float | None = None,
    ) -> None:
        super().__init__(compression=compression, compression_level=compression_level)
        self._host = host
        self._path = path.rstrip("/")
        self._user = user
        self._ssh_key = ssh_key
        self._bandwidth_limit = bandwidth_limit

    @property
    def name(self) -> str:
        return f"rsync:{self._host}:{self._path}"

    @property
    def _ssh_cmd(self) -> list[str]:
        """Build the SSH command with key and user."""
        cmd = ["ssh"]
        if self._ssh_key:
            cmd += ["-i", str(self._ssh_key)]
        if self._user:
            cmd += ["-l", self._user]
        return cmd

    def push(self, local_path: Path, remote_path: str) -> bool:
        """rsync a local file or directory to the remote host."""
        src = local_path.resolve()
        remote_dest = f"{self._host}:{self._path}/{remote_path}"

        if not src.exists():
            logger.warning("rsync_push_src_missing", src=src)
            return False

        try:
            cmd = self._build_rsync_cmd(src, remote_dest)
            logger.debug("rsync_push", cmd=" ".join(cmd), src=src)
            result = self._run(cmd)
            if result.returncode not in (0, 23, 24):
                # 23 = partial transfer, 24 = vanished source
                msg = result.stderr.decode("utf-8", errors="replace").strip()
                logger.error("rsync_push_failed", src=src, dest=remote_dest, stderr=msg)
                return False
            logger.info("rsync_push_ok", src=src, dest=remote_dest)
            return True
        except SyncError:
            return False
        except Exception as exc:
            logger.error("rsync_push_exception", src=src, error=str(exc))
            return False

    def pull(self, remote_path: str, local_path: Path) -> bool:
        """rsync a remote file or directory from the remote host."""
        src = f"{self._host}:{self._path}/{remote_path}"
        dst = local_path.resolve()

        try:
            cmd = ["rsync", "-av"]
            if self._ssh_key:
                cmd += ["-e", "ssh -i " + str(self._ssh_key)]
            if self._bandwidth_limit:
                cmd += ["--bwlimit", str(int(self._bandwidth_limit))]
            cmd += [f"{self._user}@{src}/" if self._user else f"{src}/", str(dst)]
            logger.debug("rsync_pull", cmd=" ".join(cmd), src=src, dst=dst)
            result = self._run(cmd)
            if result.returncode not in (0, 23, 24):
                msg = result.stderr.decode("utf-8", errors="replace").strip()
                logger.error("rsync_pull_failed", src=src, dst=dst, stderr=msg)
                return False
            logger.info("rsync_pull_ok", src=src, dst=dst)
            return True
        except Exception as exc:
            logger.error("rsync_pull_exception", src=src, dst=dst, error=str(exc))
            return False

    def verify(self, remote_path: str) -> bool:
        """Check remote path via SSH."""
        cmd = self._ssh_cmd + [self._host, "test", "-e", f"{self._path}/{remote_path}"]
        try:
            result = self._run(cmd)
            return result.returncode == 0
        except Exception as exc:
            logger.warning("rsync_verify_failed", host=self._host, error=str(exc))
            return False

    def _build_rsync_cmd(
        self,
        src: Path,
        dst: str,
    ) -> list[str]:
        """Build the rsync command."""
        cmd = [
            "rsync",
            "-av",
            "--delete",
        ]
        if self._compression == "none":
            cmd += ["--no-compress"]
        else:
            # rsync handles its own compression; zstd pre-compression
            # is for cases where we want archival compression
            pass
        if self._bandwidth_limit:
            cmd += ["--bwlimit", str(int(self._bandwidth_limit))]
        if self._ssh_key:
            cmd += ["-e", "ssh -i " + str(self._ssh_key)]
        cmd += [str(src), dst]
        return cmd
