"""Tests for ShareGPT, DPO, and Raw formatters."""

import json
from datetime import UTC, datetime

import pytest

from orthrus.capture.turn import ToolCall, Turn, TurnOutcome
from orthrus.export._formats._sharegpt import ShareGPTFormatter
from orthrus.export._formats._dpo import DPOFormatter
from orthrus.export._formats._raw import RawFormatter


def make_turn(
    *,
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
    """Helper to create a valid Turn for testing."""
    return Turn(
        trace_id="01900000-0000-7000-8000-000000000001",
        session_id="test-session",
        timestamp=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
        query_text=query_text,
        context_hash="a" * 64,
        available_tools=available_tools,
        active_skills=active_skills,
        reasoning_content=reasoning_content,
        tool_calls=tool_calls,
        outcome=outcome,
        response_text=response_text,
        user_rating=user_rating,
        query_embedding=query_embedding,
        error_class=error_class,
    )


class TestShareGPTFormatter:
    @pytest.fixture
    def formatter(self):
        return ShareGPTFormatter()

    def test_basic_turn(self, formatter):
        turn = make_turn(response_text="4", available_tools=())
        result = formatter.format(turn)
        assert result is not None
        assert "conversations" in result
        convs = result["conversations"]
        # No system message when no tools or skills
        assert len(convs) == 2  # human + gpt
        assert convs[0]["from"] == "human"
        assert convs[0]["value"] == "What is 2+2?"
        assert convs[1]["from"] == "gpt"
        assert convs[1]["value"] == "4"

    def test_system_message_with_tools(self, formatter):
        turn = make_turn(
            available_tools=("web_search", "file_read"),
            active_skills=("python-pro",),
        )
        result = formatter.format(turn)
        assert result is not None
        convs = result["conversations"]
        # First message should be system
        assert convs[0]["from"] == "system"
        assert "web_search" in convs[0]["value"]
        assert "python-pro" in convs[0]["value"]

    def test_reasoning_prefixed_in_gpt_response(self, formatter):
        turn = make_turn(
            response_text="The answer is 4",
            reasoning_content="2+2 equals 4",
        )
        result = formatter.format(turn)
        assert result is not None
        convs = result["conversations"]
        gpt_turn = convs[-1]
        assert "<reasoning>" in gpt_turn["value"]
        assert "2+2 equals 4" in gpt_turn["value"]
        assert "The answer is 4" in gpt_turn["value"]

    def test_missing_response_returns_none(self, formatter):
        turn = make_turn(response_text=None)
        assert formatter.format(turn) is None

    def test_missing_query_returns_none(self, formatter):
        # Empty query_text is rejected by Turn at construction.
        # ShareGPT returns None for turns without query_text.
        with pytest.raises(ValueError, match="query_text"):
            make_turn(query_text="")

    def test_tool_calls_included(self, formatter):
        turn = make_turn(
            tool_calls=(
                ToolCall(
                    tool_name="terminal",
                    arguments_hash="a" * 64,
                    output_hash="b" * 64,
                    duration_ms=100,
                    exit_code=0,
                    success=True,
                ),
            )
        )
        result = formatter.format(turn)
        assert result is not None
        assert "tool_calls" in result
        assert result["tool_calls"][0]["tool"] == "terminal"

    def test_user_rating_included(self, formatter):
        turn = make_turn(user_rating=0.9)
        result = formatter.format(turn)
        assert result["quality"] == 0.9

    def test_outcome_tag_on_error(self, formatter):
        turn = make_turn(outcome=TurnOutcome.ERROR)
        result = formatter.format(turn)
        assert result["outcome"] == "error"


class TestDPOFormatter:
    @pytest.fixture
    def formatter(self):
        return DPOFormatter()

    def test_basic_turn(self, formatter):
        turn = make_turn(response_text="4")
        result = formatter.format(turn)
        assert result is not None
        assert "prompt" in result
        assert "chosen" in result
        assert "rejected" in result
        assert "What is 2+2?" in result["prompt"]
        assert result["chosen"] == "4"

    def test_reasoning_in_chosen(self, formatter):
        turn = make_turn(
            response_text="The answer is 4",
            reasoning_content="2+2 = 4",
        )
        result = formatter.format(turn)
        assert "<reasoning>" in result["chosen"]
        assert "2+2 = 4" in result["chosen"]
        assert "The answer is 4" in result["chosen"]

    def test_rejected_on_error_turn(self, formatter):
        turn = make_turn(
            outcome=TurnOutcome.ERROR,
            error_class="TimeoutError",
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
            available_tools=(),
        )
        result = formatter.format(turn)
        assert result is not None
        assert "rejected" in result
        assert "TimeoutError" in result["rejected"] or "Tool failure" in result["rejected"]

    def test_no_response_chosen(self, formatter):
        turn = make_turn(response_text=None, outcome=TurnOutcome.ERROR)
        result = formatter.format(turn)
        assert result is not None
        assert "chosen" in result

    def test_tools_included_in_prompt(self, formatter):
        turn = make_turn(available_tools=("web_search",))
        result = formatter.format(turn)
        assert "web_search" in result["prompt"]

    def test_missing_query_returns_none(self, formatter):
        # Empty query_text is rejected at Turn construction.
        with pytest.raises(ValueError, match="query_text"):
            make_turn(query_text="")


class TestRawFormatter:
    @pytest.fixture
    def formatter(self):
        return RawFormatter()

    def test_all_fields_present(self, formatter):
        turn = make_turn(
            response_text="result",
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
            user_rating=0.85,
            query_embedding=tuple([0.1] * 384),
        )
        result = formatter.format(turn)
        assert result["trace_id"] == turn.trace_id
        assert result["session_id"] == turn.session_id
        assert result["query_text"] == "What is 2+2?"
        assert result["response_text"] == "result"
        assert result["reasoning_content"] == "thinking"
        assert result["outcome"] == "success"
        assert result["user_rating"] == 0.85
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["tool_name"] == "terminal"
        # embedding should be a list
        assert isinstance(result["query_embedding"], list)
        assert len(result["query_embedding"]) == 384

    def test_optional_fields_none(self, formatter):
        turn = make_turn(
            response_text=None,
            reasoning_content=None,
            tool_calls=(),
            user_rating=None,
            query_embedding=None,
        )
        result = formatter.format(turn)
        assert result["response_text"] is None
        assert result["reasoning_content"] is None
        assert result["tool_calls"] == []
        assert result["user_rating"] is None
        assert result["query_embedding"] is None
