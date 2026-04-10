"""Raw format — complete Turn record as JSON.

Raw passthrough of all Turn fields that can be represented in JSON.
No filtering or transformation is applied.
"""

from __future__ import annotations

from orthrus.capture.turn import ToolCall, Turn


class RawFormatter:
    """Raw JSON format exporter.

    Serializes all non-None Turn fields into a flat JSON dict.
    Embeddings are stored as lists of floats. ToolCall tuples are
    serialized as lists of dicts.

    This format is useful for debugging, re-processing with custom
    tooling, or as a fallback when a structured format is not suitable.
    """

    @property
    def format_name(self) -> str:
        return "raw"

    def format(self, turn: Turn) -> dict[str, object]:
        def _emb(values: tuple[float, ...] | None) -> list[float] | None:
            return list(values) if values is not None else None

        def _tools(
            tool_calls: tuple[ToolCall, ...],
        ) -> list[dict[str, object]]:
            return [
                {
                    "tool_name": tc.tool_name,
                    "arguments_hash": tc.arguments_hash,
                    "output_hash": tc.output_hash,
                    "duration_ms": tc.duration_ms,
                    "exit_code": tc.exit_code,
                    "success": tc.success,
                }
                for tc in tool_calls
            ]

        return {
            "trace_id": turn.trace_id,
            "session_id": turn.session_id,
            "timestamp": turn.timestamp.isoformat(),
            "schema_version": turn.schema_version,
            "query_text": turn.query_text,
            "query_embedding": _emb(turn.query_embedding),
            "parent_trace_id": turn.parent_trace_id,
            "context_hash": turn.context_hash,
            "available_tools": list(turn.available_tools),
            "active_skills": list(turn.active_skills),
            "reasoning_content": turn.reasoning_content,
            "tool_selection": turn.tool_selection,
            "tool_calls": _tools(turn.tool_calls),
            "duration_ms": turn.duration_ms,
            "outcome": turn.outcome.value,
            "response_text": turn.response_text,
            "response_embedding": _emb(turn.response_embedding),
            "error_class": turn.error_class,
            "user_rating": turn.user_rating,
            "orthrus_version": turn.orthrus_version,
            "capture_profile": turn.capture_profile,
            "platform": turn.platform,
        }
