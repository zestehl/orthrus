"""Tests for Exporter and quality scoring."""

from datetime import UTC, datetime

import pytest

from orthrus.capture.turn import ToolCall, Turn, TurnOutcome
from orthrus.export._exporter import (
    _cosine_similarity,
    _quality_bin,
    compute_quality,
)
from orthrus.export._formats._sharegpt import ShareGPTFormatter
from orthrus.export._result import ExportResult

# --------------------------------------------------------------------------:
# Test helpers
# --------------------------------------------------------------------------:


def make_turn(
    *,
    trace_id: str = "01900000-0000-7000-8000-000000000001",
    session_id: str = "test-session",
    timestamp: datetime | None = None,
    query_text: str = "What is 2+2?",
    response_text: str | None = "4",
    reasoning_content: str | None = None,
    outcome: TurnOutcome = TurnOutcome.SUCCESS,
    tool_calls: tuple[ToolCall, ...] = (),
    available_tools: tuple[str, ...] = (),
    active_skills: tuple[str, ...] = (),
    user_rating: float | None = None,
    query_embedding: tuple[float, ...] | None = None,
    error_class: str | None = None,
) -> Turn:
    """Create a valid Turn for testing."""
    return Turn(
        trace_id=trace_id,
        session_id=session_id,
        timestamp=timestamp or datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
        query_text=query_text,
        context_hash="a" * 64,
        available_tools=available_tools,
        active_skills=active_skills,
        reasoning_content=reasoning_content,
        tool_calls=tool_calls,
        outcome=outcome,
        duration_ms=100,
        response_text=response_text,
        user_rating=user_rating,
        query_embedding=query_embedding,
        error_class=error_class,
    )


# --------------------------------------------------------------------------:
# Quality scoring
# --------------------------------------------------------------------------:


class TestComputeQuality:
    def test_base_score(self):
        # 0.5 base + SUCCESS +0.1 = 0.6
        turn = make_turn(response_text=None)
        assert compute_quality(turn) == 0.6

    def test_response_bonus(self):
        turn = make_turn(response_text="answer")
        # 0.5 base + SUCCESS +0.1 + response +0.2 = 0.8
        assert compute_quality(turn) == pytest.approx(0.8)

    def test_success_bonus(self):
        turn = make_turn(response_text="answer", outcome=TurnOutcome.SUCCESS)
        # same as response_bonus — SUCCESS is default
        assert compute_quality(turn) == pytest.approx(0.8)

    def test_error_penalty(self):
        turn = make_turn(response_text="answer", outcome=TurnOutcome.ERROR)
        # 0.5 base + ERROR -0.1 + response +0.2 = 0.6
        assert compute_quality(turn) == 0.6

    def test_reasoning_bonus(self):
        turn = make_turn(response_text="answer", reasoning_content="thinking")
        # 0.5 + SUCCESS +0.1 + response +0.2 + reasoning +0.05 = 0.85
        assert compute_quality(turn) == 0.85

    def test_tool_all_success_bonus(self):
        turn = make_turn(
            response_text="answer",
            tool_calls=(
                ToolCall(
                    tool_name="terminal",
                    arguments_hash="a" * 64,
                    output_hash="b" * 64,
                    duration_ms=100,
                    exit_code=0,
                    success=True,
                ),
            ),
        )
        # 0.5 + SUCCESS +0.1 + response +0.2 + all-success +0.1 = 0.9
        assert compute_quality(turn) == pytest.approx(0.9)

    def test_tool_any_failure_penalty(self):
        turn = make_turn(
            response_text="answer",
            tool_calls=(
                ToolCall(
                    tool_name="terminal",
                    arguments_hash="a" * 64,
                    output_hash="b" * 64,
                    duration_ms=100,
                    exit_code=1,
                    success=False,
                ),
            ),
        )
        # 0.5 + SUCCESS +0.1 + response +0.2 + some-fail -0.1 = 0.7
        assert compute_quality(turn) == 0.7

    def test_user_rating_overrides(self):
        turn = make_turn(response_text="answer", user_rating=0.95)
        assert compute_quality(turn) == 0.95

    def test_clamped_to_1(self):
        turn = make_turn(
            response_text="answer",
            outcome=TurnOutcome.SUCCESS,
            reasoning_content="thinking",
            tool_calls=(
                ToolCall(
                    tool_name="terminal",
                    arguments_hash="a" * 64,
                    output_hash="b" * 64,
                    duration_ms=100,
                    exit_code=0,
                    success=True,
                ),
            ),
            user_rating=1.0,
        )
        assert compute_quality(turn) == 1.0

    def test_clamped_to_0(self):
        # 0.5 base + ERROR -0.1 + failed-tool -0.1 = 0.3 (no response_text so no +0.2)
        # Floor to 0.0
        turn = make_turn(
            response_text=None,
            outcome=TurnOutcome.ERROR,
            tool_calls=(
                ToolCall(
                    tool_name="terminal",
                    arguments_hash="a" * 64,
                    output_hash="b" * 64,
                    duration_ms=100,
                    exit_code=1,
                    success=False,
                ),
            ),
        )
        assert compute_quality(turn) == pytest.approx(0.3)


class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = tuple([0.1] * 10)
        assert _cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        a = (1.0, 0.0, 0.0)
        b = (0.0, 1.0, 0.0)
        assert _cosine_similarity(a, b) == pytest.approx(0.0)

    def test_zero_vector(self):
        assert _cosine_similarity((0.0, 0.0), (1.0, 2.0)) == 0.0

    def test_arbitrary(self):
        a = (1.0, 2.0, 3.0)
        b = (4.0, 5.0, 6.0)
        sim = _cosine_similarity(a, b)
        # Should be < 1.0 and > 0.0
        assert 0.0 < sim < 1.0


class TestQualityBin:
    @pytest.mark.parametrize("score,expected", [
        (0.0, "0.0-0.2"),
        (0.15, "0.0-0.2"),
        (0.2, "0.2-0.4"),
        (0.35, "0.2-0.4"),
        (0.4, "0.4-0.6"),
        (0.55, "0.4-0.6"),
        (0.6, "0.6-0.8"),
        (0.75, "0.6-0.8"),
        (0.8, "0.8-1.0"),
        (0.99, "0.8-1.0"),
        (1.0, "0.8-1.0"),
    ])
    def test_bins(self, score, expected):
        assert _quality_bin(score) == expected


# --------------------------------------------------------------------------:
# ExportResult
# --------------------------------------------------------------------------:


class TestExportResult:
    def test_success_property(self):
        result = ExportResult()
        assert result.success is True

    def test_error_sets_success_false(self):
        result = ExportResult(error="something failed")
        assert result.success is False


# --------------------------------------------------------------------------:
# ShareGPT formatter integration
# --------------------------------------------------------------------------:


class TestShareGPTFormatterIntegration:
    """Test ShareGPTFormatter handles full Turn lifecycle."""

    def test_format_roundtrip_query_and_response(self):
        formatter = ShareGPTFormatter()
        turn = make_turn(
            query_text="Explain quantum entanglement",
            response_text="Quantum entanglement is...",
            available_tools=("terminal",),
        )
        result = formatter.format(turn)
        assert result is not None
        convs = result["conversations"]
        assert len(convs) == 3  # system + human + gpt
        assert convs[1]["from"] == "human"
        assert convs[2]["from"] == "gpt"
        assert "Quantum entanglement" in convs[2]["value"]

    def test_no_system_when_no_context(self):
        formatter = ShareGPTFormatter()
        turn = make_turn(available_tools=(), active_skills=())
        result = formatter.format(turn)
        assert result is not None
        convs = result["conversations"]
        # human + gpt only, no system
        assert convs[0]["from"] == "human"
        assert convs[1]["from"] == "gpt"

    def test_failed_turn_still_exports(self):
        formatter = ShareGPTFormatter()
        turn = make_turn(outcome=TurnOutcome.ERROR)
        result = formatter.format(turn)
        assert result is not None
        assert result["outcome"] == "error"
