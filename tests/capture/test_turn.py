"""Tests for Turn and ToolCall dataclasses.

The Turn is the atomic unit of agent telemetry. Immutable, validated at construction.
"""

from datetime import UTC, datetime, timezone

import pytest

from orthrus.capture.turn import ToolCall, Turn, TurnOutcome


class TestToolCall:
    """Test ToolCall dataclass."""

    def test_basic_construction(self):
        """ToolCall with minimal required fields."""
        tc = ToolCall(
            tool_name="terminal",
            arguments_hash="a" * 64,
            output_hash="b" * 64,
            duration_ms=150,
            exit_code=0,
            success=True,
        )
        assert tc.tool_name == "terminal"
        assert tc.duration_ms == 150
        assert tc.success is True

    def test_immutable(self):
        """ToolCall must be frozen — mutation raises."""
        tc = ToolCall(
            tool_name="terminal",
            arguments_hash="a" * 64,
            output_hash="b" * 64,
            duration_ms=100,
            exit_code=0,
            success=True,
        )
        with pytest.raises(AttributeError):
            tc.tool_name = "file"

    def test_invalid_arguments_hash(self):
        """arguments_hash must be 64 hex chars."""
        with pytest.raises(ValueError, match="arguments_hash"):
            ToolCall(
                tool_name="terminal",
                arguments_hash="short",
                output_hash="b" * 64,
                duration_ms=100,
                exit_code=0,
                success=True,
            )

    def test_invalid_output_hash(self):
        """output_hash must be 64 hex chars."""
        with pytest.raises(ValueError, match="output_hash"):
            ToolCall(
                tool_name="terminal",
                arguments_hash="a" * 64,
                output_hash="not-hex-at-all-just-a-long-string-that-is-not-hex-value!!",
                duration_ms=100,
                exit_code=0,
                success=True,
            )

    def test_negative_duration_rejected(self):
        """duration_ms cannot be negative."""
        with pytest.raises(ValueError, match="duration_ms"):
            ToolCall(
                tool_name="terminal",
                arguments_hash="a" * 64,
                output_hash="b" * 64,
                duration_ms=-1,
                exit_code=0,
                success=True,
            )

    def test_empty_tool_name_rejected(self):
        """tool_name cannot be empty."""
        with pytest.raises(ValueError, match="tool_name"):
            ToolCall(
                tool_name="",
                arguments_hash="a" * 64,
                output_hash="b" * 64,
                duration_ms=100,
                exit_code=0,
                success=True,
            )


class TestTurn:
    """Test Turn dataclass."""

    @pytest.fixture
    def minimal_turn_kwargs(self):
        """Minimal valid kwargs for Turn construction."""
        return {
            "trace_id": "018f1234-5678-7abc-8def-0123456789ab",
            "session_id": "session-001",
            "timestamp": datetime(2026, 4, 9, 20, 0, 0, tzinfo=UTC),
            "query_text": "move to the directory",
            "context_hash": "a" * 64,
            "available_tools": ["terminal", "file"],
        }

    def test_minimal_construction(self, minimal_turn_kwargs):
        """Turn with minimum required fields."""
        turn = Turn(**minimal_turn_kwargs)
        assert turn.query_text == "move to the directory"
        assert turn.schema_version == 1
        assert turn.outcome == TurnOutcome.SUCCESS

    def test_immutable(self, minimal_turn_kwargs):
        """Turn must be frozen — mutation raises."""
        turn = Turn(**minimal_turn_kwargs)
        with pytest.raises(AttributeError):
            turn.query_text = "changed"

    def test_invalid_trace_id(self, minimal_turn_kwargs):
        """trace_id must be valid UUID7."""
        minimal_turn_kwargs["trace_id"] = "not-a-uuid"
        with pytest.raises(ValueError, match="trace_id"):
            Turn(**minimal_turn_kwargs)

    def test_empty_query_text_rejected(self, minimal_turn_kwargs):
        """query_text cannot be empty."""
        minimal_turn_kwargs["query_text"] = ""
        with pytest.raises(ValueError, match="query_text"):
            Turn(**minimal_turn_kwargs)

    def test_whitespace_query_text_rejected(self, minimal_turn_kwargs):
        """query_text cannot be whitespace only."""
        minimal_turn_kwargs["query_text"] = "   "
        with pytest.raises(ValueError, match="query_text"):
            Turn(**minimal_turn_kwargs)

    def test_query_text_max_length(self, minimal_turn_kwargs):
        """query_text cannot exceed 10KB."""
        minimal_turn_kwargs["query_text"] = "x" * 10_001
        with pytest.raises(ValueError, match="max length"):
            Turn(**minimal_turn_kwargs)

    def test_control_chars_sanitized(self, minimal_turn_kwargs):
        """Control characters (except \\t\\n\\r) must be stripped."""
        minimal_turn_kwargs["query_text"] = "hello\x00world\x01test"
        turn = Turn(**minimal_turn_kwargs)
        assert "\x00" not in turn.query_text
        assert "\x01" not in turn.query_text
        assert turn.query_text == "helloworldtest"

    def test_tabs_newlines_preserved(self, minimal_turn_kwargs):
        """\\t, \\n, \\r must be preserved in query_text."""
        minimal_turn_kwargs["query_text"] = "line1\nline2\ttab\rcarriage"
        turn = Turn(**minimal_turn_kwargs)
        assert "\n" in turn.query_text
        assert "\t" in turn.query_text
        assert "\r" in turn.query_text

    def test_invalid_context_hash(self, minimal_turn_kwargs):
        """context_hash must be 64 hex chars."""
        minimal_turn_kwargs["context_hash"] = "bad-hash"
        with pytest.raises(ValueError, match="context_hash"):
            Turn(**minimal_turn_kwargs)

    def test_naive_timestamp_rejected(self, minimal_turn_kwargs):
        """Timestamp must be timezone-aware."""
        minimal_turn_kwargs["timestamp"] = datetime(2026, 4, 9, 20, 0, 0)  # no tz
        with pytest.raises(ValueError, match="timezone"):
            Turn(**minimal_turn_kwargs)

    def test_non_utc_normalized(self, minimal_turn_kwargs):
        """Non-UTC timestamp must be normalized to UTC."""
        from datetime import timedelta
        est = timezone(timedelta(hours=-5))
        minimal_turn_kwargs["timestamp"] = datetime(2026, 4, 9, 15, 0, 0, tzinfo=est)
        turn = Turn(**minimal_turn_kwargs)
        # 15:00 EST = 20:00 UTC
        assert turn.timestamp.hour == 20
        assert turn.timestamp.tzinfo == UTC

    def test_negative_duration_rejected(self, minimal_turn_kwargs):
        """duration_ms cannot be negative."""
        minimal_turn_kwargs["duration_ms"] = -1
        with pytest.raises(ValueError, match="duration_ms"):
            Turn(**minimal_turn_kwargs)

    def test_invalid_embedding_nan(self, minimal_turn_kwargs):
        """Embedding with NaN must be rejected."""
        minimal_turn_kwargs["query_embedding"] = [float('nan')] + [0.5] * 383
        with pytest.raises(ValueError, match="NaN|Inf"):
            Turn(**minimal_turn_kwargs)

    def test_invalid_embedding_inf(self, minimal_turn_kwargs):
        """Embedding with Inf must be rejected."""
        minimal_turn_kwargs["query_embedding"] = [float('inf')] + [0.5] * 383
        with pytest.raises(ValueError, match="NaN|Inf"):
            Turn(**minimal_turn_kwargs)

    def test_valid_embedding(self, minimal_turn_kwargs):
        """Valid embedding accepted and stored as tuple."""
        emb = [0.1] * 384
        minimal_turn_kwargs["query_embedding"] = emb
        turn = Turn(**minimal_turn_kwargs)
        assert turn.query_embedding is not None
        assert len(turn.query_embedding) == 384
        assert isinstance(turn.query_embedding, tuple)

    def test_none_embedding_allowed(self, minimal_turn_kwargs):
        """None embedding is valid (lazy generation)."""
        minimal_turn_kwargs["query_embedding"] = None
        turn = Turn(**minimal_turn_kwargs)
        assert turn.query_embedding is None

    def test_tool_calls_stored_as_tuple(self, minimal_turn_kwargs):
        """tool_calls must be stored as tuple (immutable)."""
        tc = ToolCall(
            tool_name="terminal",
            arguments_hash="a" * 64,
            output_hash="b" * 64,
            duration_ms=100,
            exit_code=0,
            success=True,
        )
        minimal_turn_kwargs["tool_calls"] = [tc]
        turn = Turn(**minimal_turn_kwargs)
        assert isinstance(turn.tool_calls, tuple)
        assert len(turn.tool_calls) == 1

    def test_available_tools_stored_as_tuple(self, minimal_turn_kwargs):
        """available_tools must be stored as tuple (immutable)."""
        minimal_turn_kwargs["available_tools"] = ["terminal", "file", "web"]
        turn = Turn(**minimal_turn_kwargs)
        assert isinstance(turn.available_tools, tuple)
        assert len(turn.available_tools) == 3

    def test_active_skills_stored_as_tuple(self, minimal_turn_kwargs):
        """active_skills must be stored as tuple (immutable)."""
        minimal_turn_kwargs["active_skills"] = ["python-pro", "tdd"]
        turn = Turn(**minimal_turn_kwargs)
        assert isinstance(turn.active_skills, tuple)

    def test_with_embedding_immutability(self, minimal_turn_kwargs):
        """with_embedding returns new Turn, does not mutate."""
        turn1 = Turn(**minimal_turn_kwargs)
        emb = [0.1] * 384
        turn2 = turn1.with_embedding(emb)
        assert turn1.query_embedding is None
        assert turn2.query_embedding is not None
        assert id(turn1) != id(turn2)

    def test_with_embedding_rejects_wrong_dims(self, minimal_turn_kwargs):
        """with_embedding must validate dimensions."""
        turn = Turn(**minimal_turn_kwargs)
        with pytest.raises(ValueError, match="dimensions|NaN|Inf"):
            turn.with_embedding([0.1] * 100)  # wrong dimensions

    def test_with_embedding_rejects_nan(self, minimal_turn_kwargs):
        """with_embedding must reject NaN values."""
        turn = Turn(**minimal_turn_kwargs)
        bad_emb = [float('nan')] + [0.1] * 383
        with pytest.raises(ValueError, match="NaN|Inf"):
            turn.with_embedding(bad_emb)

    def test_turn_is_hashable(self, minimal_turn_kwargs):
        """Frozen+slots Turn must be hashable (usable in sets)."""
        turn = Turn(**minimal_turn_kwargs)
        hash(turn)  # should not raise

    def test_enum_outcome(self, minimal_turn_kwargs):
        """TurnOutcome enum values work."""
        minimal_turn_kwargs["outcome"] = TurnOutcome.ERROR
        turn = Turn(**minimal_turn_kwargs)
        assert turn.outcome == TurnOutcome.ERROR

    def test_default_providence_fields(self, minimal_turn_kwargs):
        """orthrus_version, capture_profile, platform should have defaults."""
        turn = Turn(**minimal_turn_kwargs)
        assert turn.orthrus_version  # not empty
        assert turn.capture_profile == "standard"
        assert turn.platform  # not empty
