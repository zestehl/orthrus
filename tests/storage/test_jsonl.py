"""Tests for orthrus.storage._jsonl."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

import pytest

from orthrus.capture.turn import ToolCall, Turn, TurnOutcome
from orthrus.storage._jsonl import (
    JSONLWriter,
    read_jsonl,
    turn_to_jsonl_record,
)


@pytest.fixture
def sample_turn() -> Turn:
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


class TestTurnToJsonlRecord:
    """turn_to_jsonl_record() serialization."""

    def test_required_fields(self, sample_turn):
        """Required fields are present."""
        record = turn_to_jsonl_record(sample_turn)

        assert record["trace_id"] == sample_turn.trace_id
        assert record["session_id"] == sample_turn.session_id
        assert record["query_text"] == sample_turn.query_text
        assert record["context_ref"] == sample_turn.context_hash
        assert record["duration_ms"] == 200
        assert record["outcome"] == "success"

    def test_timestamp_iso_format(self, sample_turn):
        """timestamp is stored as ISO string."""
        record = turn_to_jsonl_record(sample_turn)

        assert record["timestamp"] == "2026-04-09T12:00:00+00:00"

    def test_embedding_stored_as_list(self):
        """Embedding is stored as a JSON list."""
        turn = Turn(
            trace_id="018f1234-5678-7abc-8def-1234567890ab",
            session_id="test",
            timestamp=datetime.now(UTC),
            query_text="Test",
            context_hash=hashlib.sha256(b"ctx").hexdigest(),
            available_tools=(),
            query_embedding=tuple([0.1] * 384),
        )
        record = turn_to_jsonl_record(turn)

        assert record["query_embedding"] is not None
        assert len(record["query_embedding"]) == 384

    def test_optional_fields_null(self, sample_turn):
        """None fields remain None."""
        record = turn_to_jsonl_record(sample_turn)

        assert record["query_embedding"] is None
        assert record["reasoning_content"] is None

    def test_json_serializable(self, sample_turn):
        """Record is valid JSON (no datetime objects)."""
        record = turn_to_jsonl_record(sample_turn)

        # Should not raise
        json.dumps(record)


class TestJSONLWriter:
    """JSONLWriter append-only tests."""

    def test_write_single_turn_creates_file(self, tmp_path, sample_turn):
        """write() creates the JSONL file."""
        path = tmp_path / "test.jsonl"
        writer = JSONLWriter(path)

        writer.write(sample_turn)
        writer.close()

        assert path.is_file()
        assert path.stat().st_size > 0

    def test_roundtrip_single_turn(self, tmp_path, sample_turn):
        """Written turn can be read back."""
        path = tmp_path / "test.jsonl"
        writer = JSONLWriter(path)

        writer.write(sample_turn)
        writer.close()

        records = read_jsonl(path)
        assert len(records) == 1
        assert records[0]["trace_id"] == sample_turn.trace_id
        assert records[0]["query_text"] == sample_turn.query_text

    def test_roundtrip_multiple_turns(self, tmp_path):
        """Multiple turns round-trip correctly."""
        path = tmp_path / "multi.jsonl"
        writer = JSONLWriter(path)

        turns = [
            Turn(
                trace_id=f"018f1234-5678-7abc-8def-{i:012d}",
                session_id="batch-test",
                timestamp=datetime(2026, 4, 9, 12, i, 0, tzinfo=UTC),
                query_text=f"Query {i}",
                context_hash=hashlib.sha256(b"ctx").hexdigest(),
                available_tools=(),
            )
            for i in range(3)
        ]

        writer.write_batch(turns)
        writer.close()

        records = read_jsonl(path)
        assert len(records) == 3
        assert records[2]["query_text"] == "Query 2"

    def test_append_mode(self, tmp_path, sample_turn):
        """Multiple writes append to the same file."""
        path = tmp_path / "append.jsonl"

        with JSONLWriter(path) as w:
            w.write(sample_turn)
        with JSONLWriter(path) as w:
            w.write(sample_turn)

        records = read_jsonl(path)
        assert len(records) == 2

    def test_context_manager(self, tmp_path, sample_turn):
        """Writer works as a context manager."""
        path = tmp_path / "ctx.jsonl"
        with JSONLWriter(path) as writer:
            writer.write(sample_turn)

        records = read_jsonl(path)
        assert len(records) == 1

    def test_lines_written_count(self, tmp_path, sample_turn):
        """lines_written property is accurate."""
        path = tmp_path / "count.jsonl"
        writer = JSONLWriter(path)

        assert writer.lines_written == 0
        writer.write(sample_turn)
        assert writer.lines_written == 1
        writer.write(sample_turn)
        assert writer.lines_written == 2
        writer.close()

    def test_file_stats(self, tmp_path, sample_turn):
        """jsonl_file_stats returns correct stats."""
        path = tmp_path / "stats.jsonl"
        writer = JSONLWriter(path)

        writer.write(sample_turn)
        writer.close()

        from orthrus.storage._jsonl import jsonl_file_stats
        stats = jsonl_file_stats(path)

        assert stats["num_lines"] == 1
        assert stats["size_bytes"] > 0
