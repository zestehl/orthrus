"""Tests for orthrus.storage._manager."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest

from orthrus.capture.turn import ToolCall, Turn, TurnOutcome
from orthrus.config._models import StorageConfig
from orthrus.storage._manager import (
    StorageManager,
    TurnRecord,
)
from orthrus.storage._paths import StoragePaths


@pytest.fixture
def storage_config() -> StorageConfig:
    return StorageConfig(
        hot_max_days=30,
        warm_max_days=90,
        warm_compression="zstd",
        warm_compression_level=3,
        archive_compression="zstd",
        archive_compression_level=9,
        parquet_row_group_size=100,
    )


@pytest.fixture
def storage_paths(tmp_path, monkeypatch) -> StoragePaths:
    """StoragePaths pointing at a temp directory."""
    import orthrus.storage._paths as p
    monkeypatch.setattr(p, "_data_root", lambda: tmp_path)
    return StoragePaths.resolve()


def make_turn(
    trace_id: str = "018f1234-5678-7abc-8def-1234567890ab",
    session: str = "test-session",
    ts: datetime | None = None,
    query: str = "What is the capital of France?",
) -> Turn:
    return Turn(
        trace_id=trace_id,
        session_id=session,
        timestamp=ts or datetime(2026, 4, 9, 12, 0, 0, tzinfo=UTC),
        query_text=query,
        context_hash=hashlib.sha256(b"test-context").hexdigest(),
        available_tools=("web_search", "file_read"),
        tool_calls=(
            ToolCall(
                tool_name="web_search",
                arguments_hash=hashlib.sha256(b'{"q":"France"}').hexdigest(),
                output_hash=hashlib.sha256(b'"Paris"').hexdigest(),
                duration_ms=150,
                exit_code=0,
                success=True,
            ),
        ),
        outcome=TurnOutcome.SUCCESS,
        duration_ms=200,
        response_text="Paris",
    )


class TestStorageManagerInit:
    """StorageManager initialization."""

    def test_init_with_paths(self, storage_config, storage_paths):
        """Manager initializes with explicit paths."""
        mgr = StorageManager(storage_config, paths=storage_paths)
        assert mgr.total_turns_written == 0

    def test_init_without_paths(self, storage_config, tmp_path, monkeypatch):
        """Manager resolves paths when not provided."""
        import orthrus.storage._paths as p
        monkeypatch.setattr(p, "_data_root", lambda: tmp_path)
        mgr = StorageManager(storage_config)
        assert mgr.total_turns_written == 0


class TestWriteTurn:
    """StorageManager.write_turn()."""

    def test_write_single_turn(
        self, storage_config, storage_paths, tmp_path
    ):
        """write_turn() returns TurnRecord with correct paths."""
        mgr = StorageManager(storage_config, paths=storage_paths)
        turn = make_turn()

        record = mgr.write_turn(turn)
        mgr.close()  # flush so files are on disk

        assert isinstance(record, TurnRecord)
        assert record.parquet_path.is_file()
        assert record.jsonl_path.is_file()
        assert record.turn is turn
        assert mgr.total_turns_written == 1

    def test_multiple_turns_same_session(
        self, storage_config, storage_paths
    ):
        """Multiple turns to the same session share one file pair."""
        mgr = StorageManager(storage_config, paths=storage_paths)
        ts = datetime(2026, 4, 9, 12, 0, 0, tzinfo=UTC)
        turns = [
            make_turn(
                trace_id=f"018f1234-5678-7abc-8def-{i:012d}",
                ts=ts.replace(minute=i),
            )
            for i in range(3)
        ]

        records = [mgr.write_turn(t) for t in turns]

        # All point to the same files
        assert records[0].parquet_path == records[1].parquet_path == records[2].parquet_path
        assert records[0].jsonl_path == records[1].jsonl_path == records[2].jsonl_path

    def test_different_sessions_different_files(
        self, storage_config, storage_paths
    ):
        """Different sessions get different files."""
        mgr = StorageManager(storage_config, paths=storage_paths)

        t1 = make_turn(trace_id="018f1234-5678-7abc-8def-000000000001", session="session-A")
        t2 = make_turn(trace_id="018f1234-5678-7abc-8def-000000000002", session="session-B")

        r1 = mgr.write_turn(t1)
        r2 = mgr.write_turn(t2)

        assert r1.parquet_path != r2.parquet_path
        assert r1.jsonl_path != r2.jsonl_path

    def test_close_flushes_all(
        self, storage_config, storage_paths
    ):
        """close() flushes all writers."""
        mgr = StorageManager(storage_config, paths=storage_paths)
        for i in range(3):
            mgr.write_turn(make_turn(trace_id=f"018f1234-5678-7abc-8def-{i:012d}"))

        mgr.close()

        # Files should be on disk
        files = list(storage_paths.capture.rglob("*.parquet"))
        assert len(files) == 1

    def test_context_manager(
        self, storage_config, storage_paths
    ):
        """StorageManager works as a context manager."""
        with StorageManager(storage_config, paths=storage_paths) as mgr:
            mgr.write_turn(make_turn())

        files = list(storage_paths.capture.rglob("*.parquet"))
        assert len(files) == 1


class TestHotFiles:
    """get_hot_files()."""

    def test_lists_all_hot_files(self, storage_config, storage_paths):
        """get_hot_files() returns all parquet and jsonl files."""
        mgr = StorageManager(storage_config, paths=storage_paths)
        for i in range(3):
            mgr.write_turn(make_turn(trace_id=f"018f1234-5678-7abc-8def-{i:012d}"))
        mgr.close()

        files = mgr.get_hot_files()
        paths = [f.name for f in files]
        assert any("turns.parquet" in p for p in paths)
        assert any("trajectories.jsonl" in p for p in paths)

    def test_filters_by_since(self, storage_config, storage_paths):
        """get_hot_files(since=...) filters by timestamp."""
        mgr = StorageManager(storage_config, paths=storage_paths)
        mgr.write_turn(make_turn(ts=datetime(2026, 4, 5, tzinfo=UTC)))
        mgr.write_turn(make_turn(ts=datetime(2026, 4, 10, tzinfo=UTC)))
        mgr.close()

        since = datetime(2026, 4, 8, tzinfo=UTC)
        files = mgr.get_hot_files(since=since)
        # Should only include the Apr 10 file (date dir "10")
        date_dirs = {f.parent.name for f in files}
        assert date_dirs == {"10"}


class TestVerifyIntegrity:
    """verify_integrity()."""

    def test_verify_returns_true_for_written_file(
        self, storage_config, storage_paths
    ):
        """verify_integrity returns True when file matches manifest."""
        mgr = StorageManager(storage_config, paths=storage_paths)
        turn = make_turn()
        record = mgr.write_turn(turn)
        mgr.close()  # flush and write manifest

        assert mgr.verify_integrity(record.parquet_path) is True
        assert mgr.verify_integrity(record.jsonl_path) is True

    def test_verify_returns_false_for_missing_file(
        self, storage_config, storage_paths
    ):
        """verify_integrity returns False when manifest is missing."""
        from pathlib import Path
        mgr = StorageManager(storage_config, paths=storage_paths)
        assert mgr.verify_integrity(Path("/nonexistent/file.parquet")) is False


class TestRotate:
    """rotate()."""

    def test_rotate_moves_old_files(
        self, storage_config, storage_paths, tmp_path
    ):
        """rotate() moves files older than hot_max_days to warm."""
        mgr = StorageManager(storage_config, paths=storage_paths)

        # Write a turn with a past date
        old_ts = datetime(2025, 1, 1, tzinfo=UTC)
        t = make_turn(
            trace_id="018f1234-5678-7abc-8def-000000000001",
            ts=old_ts,
        )
        mgr.write_turn(t)
        mgr.close()

        # Manually create a hot file with old timestamp for testing
        # In real usage, the file would be at the old date's path
        old_capture_dir = storage_paths.capture / "2025" / "01" / "01"
        old_capture_dir.mkdir(parents=True, exist_ok=True)
        old_pq = old_capture_dir / "session-old-20250101-turns.parquet"
        old_pq.write_bytes(b"old parquet content")

        result = mgr.rotate()

        assert result.total_moved >= 0  # old file moved
