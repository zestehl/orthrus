"""Local / directory sync target."""

from __future__ import annotations

import shutil
import tarfile
from pathlib import Path

import structlog

from orthrus.sync.targets._base import BaseSyncTarget

logger = structlog.get_logger(__name__)


class LocalTarget(BaseSyncTarget):
    """Sync to a local directory (external drive, NAS mount, etc.).

    Parameters
    ----------
    path:
        Absolute path to the local sync destination.
    compression:
        Compression to apply before sync: "none" or "zstd".
    compression_level:
        Zstandard compression level (1-22).
    """

    def __init__(
        self,
        *,
        path: str,
        compression: str = "zstd",
        compression_level: int = 3,
    ) -> None:
        super().__init__(compression=compression, compression_level=compression_level)
        self._path = Path(path).expanduser().resolve()

    @property
    def name(self) -> str:
        return f"local:{self._path}"

    def push(self, local_path: Path, remote_path: str) -> bool:
        """Copy local files to the destination directory."""
        src = local_path.resolve()
        dst = (self._path / remote_path).resolve()

        if not src.exists():
            logger.warning("local_push_src_missing", src=src)
            return False

        try:
            dst.parent.mkdir(parents=True, exist_ok=True)

            if src.is_dir():
                if self._compression != "none":
                    # Compress directory as tar.zst
                    archive_name = dst.with_name(dst.name + ".tar.zst")
                    self._compress_dir_to_archive(src, archive_name)
                    logger.info("local_push_dir_compressed", src=src, dst=archive_name)
                else:
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                    logger.info("local_push_dir", src=src, dst=dst)
            else:
                if self._compression != "none":
                    compressed = dst.with_suffix(dst.suffix + ".zst")
                    self._compress_file(src, compressed)
                    logger.info("local_push_file_compressed", src=src, dst=compressed)
                else:
                    shutil.copy2(src, dst)
                    logger.info("local_push_file", src=src, dst=dst)

            return True
        except Exception as exc:
            logger.error("local_push_failed", src=src, dst=dst, error=str(exc))
            return False

    def pull(self, remote_path: str, local_path: Path) -> bool:
        """Copy files from the destination directory to local."""
        src = (self._path / remote_path).resolve()
        dst = local_path.resolve()

        if not src.exists():
            logger.warning("local_pull_src_missing", src=src)
            return False

        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            logger.info("local_pull", src=src, dst=dst)
            return True
        except Exception as exc:
            logger.error("local_pull_failed", src=src, dst=dst, error=str(exc))
            return False

    def verify(self, remote_path: str) -> bool:
        """Check if destination directory is accessible and writable."""
        try:
            p = self._path / remote_path
            p.parent.mkdir(parents=True, exist_ok=True)
            # Touch a temporary file to verify write access
            test_file = p.parent / f".orthrus_write_test_{id(self)}"
            test_file.touch()
            test_file.unlink()
            return True
        except Exception as exc:
            logger.warning("local_verify_failed", path=self._path, error=str(exc))
            return False

    def _compress_dir_to_archive(self, src_dir: Path, dst: Path) -> Path:
        """Create a compressed tar archive of a directory."""
        try:
            import zstandard as zstd
        except ImportError:
            logger.warning("zstd_not_available", target=self.name)
            shutil.copytree(src_dir, dst, dirs_exist_ok=True)
            return dst

        compressor = zstd.ZstdCompressor(level=self._compression_level)
        with (
            open(dst, "wb") as fo,
            compressor.stream_writer(fo) as writer,
            tarfile.open(fileobj=writer, mode="w") as tar,  # noqa: SIM117
        ):
            tar.add(src_dir, arcname=src_dir.name)
        return dst
