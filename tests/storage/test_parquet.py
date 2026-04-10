"""Tests for orthrus.storage._parquet."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest

from orthrus.capture.turn import ToolCall, Turn, TurnOutcome
from orthrus.storage._parquet import (
    ParquetWriter,
    read_turns,
    turn_to_record,
)


@pytest.fixture
def sample_turn() -> Turn:
    """A valid Turn with all fields populated."""
    return Turn(
        trace_id="018f1234-5678-7abc-8def-1234567890ab",
        session_id="test-session",
        timestamp=datetime(2026, 4, 9, 12, 0, 0, tzinfo=UTC),
        query_text="What is the capital of France?",
        context_hash=hashlib.sha256(b"test-context").hexdigest(),
        available_tools=("web_search", "file_read"),
        tool_calls=(
            ToolCall(
                tool_name="web_search",
                arguments_hash=hashlib.sha256(b'{"q":"France capital"}').hexdigest(),
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


class TestTurnToRecord:
    """turn_to_record() conversion."""

    def test_required_fields(self, sample_turn):
        """All required columns are present and correct type."""
        record = turn_to_record(sample_turn)

        assert record["trace_id"] == sample_turn.trace_id
        assert record["session_id"] == sample_turn.session_id
        assert record["query_text"] == sample_turn.query_text
        assert record["context_ref"] == sample_turn.context_hash
        assert record["available_tools"] == ["web_search", "file_read"]
        assert record["duration_ms"] == 200
        assert record["outcome"] == "success"

    def test_optional_fields_null(self, sample_turn):
        """Optional fields that are None are None in record."""
        record = turn_to_record(sample_turn)

        assert record["query_embedding"] is None
        assert record["response_text"] == "Paris"
        assert record["reasoning_content"] is None
        assert record["tool_selection"] is None

    def test_embedding_stored_as_list(self):
        """Embedding is stored as a Python list (Arrow compatible)."""
        emb = tuple([0.1] * 384)
        turn = Turn(
            trace_id="018f1234-5678-7abc-8def-1234567890ab",
            session_id="test",
            timestamp=datetime.now(UTC),
            query_text="Test query",
            context_hash=hashlib.sha256(b"ctx").hexdigest(),
            available_tools=(),
            query_embedding=emb,
        )
        record = turn_to_record(turn)

        assert record["query_embedding"] is not None
        assert len(record["query_embedding"]) == 384
        assert isinstance(record["query_embedding"], list)

    def test_tool_calls_serialized(self, sample_turn):
        """tool_calls are serialized as JSON string."""
        import json
        record = turn_to_record(sample_turn)

        parsed = json.loads(record["tool_calls"])
        assert len(parsed) == 1
        assert parsed[0]["tool_name"] == "web_search"
        assert parsed[0]["success"] is True


class TestParquetWriter:
    """ParquetWriter round-trip tests."""

    def test_write_single_turn_creates_file(self, tmp_path, sample_turn):
        """write() creates the parquet file."""
        path = tmp_path / "test.parquet"
        writer = ParquetWriter(path)

        writer.write(sample_turn)
        writer.close()

        assert path.is_file()
        assert path.stat().st_size > 0

    def test_roundtrip_single_turn(self, tmp_path, sample_turn):
        """Written turn can be read back."""
        path = tmp_path / "test.parquet"
        writer = ParquetWriter(path)

        writer.write(sample_turn)
        writer.close()

        rows = read_turns(path)
        assert len(rows) == 1
        assert rows[0]["trace_id"] == sample_turn.trace_id
        assert rows[0]["query_text"] == sample_turn.query_text

    def test_roundtrip_multiple_turns(self, tmp_path):
        """Multiple turns round-trip correctly."""
        path = tmp_path / "multi.parquet"
        writer = ParquetWriter(path)

        turns = [
            Turn(
                trace_id=f"018f1234-5678-7abc-8def-{i:012d}",
                session_id="batch-test",
                timestamp=datetime(2026, 4, 9, 12, i, 0, tzinfo=UTC),
                query_text=f"Query {i}",
                context_hash=hashlib.sha256(b"ctx").hexdigest(),
                available_tools=(),
            )
            for i in range(5)
        ]

        writer.write_batch(turns)
        writer.close()

        rows = read_turns(path)
        assert len(rows) == 5
        assert rows[2]["query_text"] == "Query 2"

    def test_context_manager(self, tmp_path, sample_turn):
        """Writer works as a context manager."""
        path = tmp_path / "ctx.parquet"
        with ParquetWriter(path) as writer:
            writer.write(sample_turn)

        rows = read_turns(path)
        assert len(rows) == 1

    def test_rows_written_count(self, tmp_path, sample_turn):
        """rows_written property is accurate."""
        path = tmp_path / "count.parquet"
        writer = ParquetWriter(path)

        assert writer.rows_written == 0
        writer.write(sample_turn)
        assert writer.rows_written == 1
        writer.write(sample_turn)
        assert writer.rows_written == 2
        writer.close()

    def test_manifest_appears_after_close(self, tmp_path, sample_turn):
        """After close the file is readable."""
        path = tmp_path / "verify.parquet"
        writer = ParquetWriter(path)
        writer.write(sample_turn)
        writer.close()

        from orthrus.storage._parquet import parquet_file_stats
        stats = parquet_file_stats(path)

        assert stats["num_rows"] == 1
        assert stats["num_columns"] > 0
        assert stats["size_bytes"] > 0
