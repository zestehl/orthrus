"""SyncManager — orchestrates sync operations across targets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import structlog

from orthrus.config._models import SyncConfig
from orthrus.config._models import SyncTarget as SyncTargetConfig
from orthrus.storage._paths import StoragePaths
from orthrus.sync._models import SyncResult, SyncTarget
from orthrus.sync.targets._local import LocalTarget
from orthrus.sync.targets._rsync import RsyncTarget
from orthrus.sync.targets._s3 import S3Target

logger = structlog.get_logger(__name__)


@dataclass
class _TargetHandle:
    """A resolved target with its config."""
    config: SyncTargetConfig
    target: SyncTarget


class SyncManager:
    """Orchestrates sync operations across one or more configured targets.

    Reads the list of hot/warm files from StorageManager and pushes them
    to each configured target.

    Memory contract: O(1) — files are listed and transferred one at a time,
    never fully buffered in memory.
    """

    def __init__(
        self,
        config: SyncConfig,
        storage_paths: StoragePaths | None = None,
    ) -> None:
        self._config = config
        self._paths = storage_paths or StoragePaths.resolve()
        self._targets: list[_TargetHandle] = []
        self._resolve_targets()

    def _resolve_targets(self) -> None:
        """Instantiate target objects from config."""
        for tc in self._config.targets:
            target = self._build_target(tc)
            if target is not None:
                self._targets.append(_TargetHandle(config=tc, target=target))
                logger.info("sync_target_resolved", name=target.name, type=tc.type)
            else:
                logger.warning("sync_target_skipped", type=tc.type, reason="no_builder")

    def _build_target(self, cfg: SyncTargetConfig) -> SyncTarget | None:
        """Build a SyncTarget from config."""
        compression = cfg.compression
        compression_level = cfg.compression_level

        if cfg.type == "local":
            return LocalTarget(
                path=cfg.path,
                compression=compression,
                compression_level=compression_level,
            )
        elif cfg.type == "rsync":
            return RsyncTarget(
                host=cfg.host or "",
                path=cfg.path,
                user=cfg.user,
                compression=compression,
                compression_level=compression_level,
                ssh_key=None,
                bandwidth_limit=None,
            )
        elif cfg.type == "s3":
            return S3Target(
                bucket=cfg.bucket or "",
                prefix=cfg.prefix or "",
                region=cfg.region,
                credentials=cfg.credentials,
                compression=compression,
                compression_level=compression_level,
                storage_class="STANDARD",
                endpoint_url=None,
            )
        return None

    def sync(
        self,
        *,
        dry_run: bool = False,
        verbose: bool = False,
        target_name: str | None = None,
    ) -> SyncResult:
        """Execute sync to all configured targets (or a specific one)."""
        files = self._list_syncable_files()
        total_bytes = sum(f.stat().st_size for f in files if f.is_file())

        if dry_run:
            logger.info("sync_dry_run", files=len(files), bytes=total_bytes)
            for f in files:
                logger.info("sync_dry_run_file", path=str(f))
            return SyncResult(
                success=True,
                files_transferred=len(files),
                bytes_transferred=total_bytes,
            )

        results: list[dict[str, object]] = []
        errors: list[str] = []
        total_transferred = 0
        total_files = 0

        for handle in self._targets:
            if target_name and target_name not in handle.target.name:
                continue

            ok, transferred, f_count, errs = self._sync_to_target(handle, files, verbose)
            results.append({
                "target": handle.target.name,
                "success": ok,
                "files": f_count,
                "bytes": transferred,
                "errors": errs,
            })
            total_transferred += transferred
            total_files += f_count
            if errs:
                errors.extend(errs)

        success = len(errors) == 0
        logger.info(
            "sync_complete",
            success=success,
            files=total_files,
            bytes=total_transferred,
            targets=len(results),
        )

        return SyncResult(
            success=success,
            bytes_transferred=total_transferred,
            files_transferred=total_files,
            errors=tuple(errors),
            target_results=tuple(results),
        )

    def _sync_to_target(
        self,
        handle: _TargetHandle,
        files: list[Path],
        verbose: bool,
    ) -> tuple[bool, int, int, list[str]]:
        """Sync files to a single target. Returns (ok, bytes, file_count, errors)."""
        target = handle.target
        errors: list[str] = []
        transferred = 0
        file_count = 0

        # Verify target is reachable first
        if not target.verify(""):
            errors.append(f"Target unreachable: {target.name}")
            return False, 0, 0, errors

        for file_path in files:
            rel_path = str(file_path.relative_to(self._paths.capture))
            ok = target.push(file_path, rel_path)
            if ok:
                transferred += file_path.stat().st_size
                file_count += 1
                if verbose:
                    logger.info("sync_file_ok", target=target.name, path=str(file_path))
            else:
                msg = f"Failed to sync {file_path} to {target.name}"
                errors.append(msg)
                logger.warning("sync_file_failed", target=target.name, path=str(file_path))

        return len(errors) == 0, transferred, file_count, errors

    def _list_syncable_files(self) -> list[Path]:
        """List all hot/warm parquet and jsonl files ready to sync."""
        capture = self._paths.capture
        warm = self._paths.warm
        files: list[Path] = []

        for base in (capture, warm):
            if base.is_dir():
                files.extend(base.rglob("*.parquet"))
                files.extend(base.rglob("*.jsonl"))

        files.sort(key=lambda p: p.stat().st_mtime)
        total_sz = sum(f.stat().st_size for f in files)
        logger.debug("sync_files_found", count=len(files), bytes=total_sz)
        return files

    def verify_targets(self) -> dict[str, bool]:
        """Check reachability of all configured targets."""
        return {h.target.name: h.target.verify("") for h in self._targets}
