"""Tests for SyncManager."""

from pathlib import Path

import pytest

from orthrus.config._models import SyncConfig, SyncTarget
from orthrus.sync._manager import SyncManager
from orthrus.sync._models import SyncResult


class TestSyncManager:
    def test_empty_sync_result(self):
        """SyncManager with no targets and no files returns success."""
        cfg = SyncConfig(enabled=True, targets=[])
        mgr = SyncManager(cfg)
        result = mgr.sync(dry_run=True)
        assert result.success is True
        assert result.files_transferred == 0
        assert result.errors == ()

    def test_verify_targets_empty(self):
        cfg = SyncConfig(enabled=True, targets=[])
        mgr = SyncManager(cfg)
        status = mgr.verify_targets()
        assert status == {}

    def test_local_target_sync_dry_run(self, tmp_path):
        """Dry run lists files without transferring."""
        capture = tmp_path / "capture"
        capture.mkdir()
        (capture / "turns.parquet").write_bytes(b"fake parquet data")

        target = SyncTarget(
            type="local",
            path=str(tmp_path / "backup"),
            schedule="manual",
        )
        cfg = SyncConfig(enabled=True, targets=[target])
        mgr = SyncManager(cfg, storage_paths=_make_paths(tmp_path))
        result = mgr.sync(dry_run=True)
        assert result.success is True
        assert result.files_transferred == 1

    def test_bytes_calculation(self):
        """Empty config with no files returns 0 bytes."""
        cfg = SyncConfig(enabled=True, targets=[])
        mgr = SyncManager(cfg)
        result = mgr.sync(dry_run=True)
        assert result.bytes_transferred == 0


def _make_paths(tmp_path: Path):
    """Create a minimal StoragePaths for testing."""
    from orthrus.storage._paths import StoragePaths
    capture = tmp_path / "capture"
    warm = tmp_path / "warm"
    archive = tmp_path / "archive"
    derived = tmp_path / "derived"
    capture.mkdir(parents=True, exist_ok=True)
    warm.mkdir(parents=True, exist_ok=True)
    archive.mkdir(parents=True, exist_ok=True)
    derived.mkdir(parents=True, exist_ok=True)
    return StoragePaths(
        root=tmp_path,
        capture=capture,
        warm=warm,
        archive=archive,
        derived=derived,
    )
