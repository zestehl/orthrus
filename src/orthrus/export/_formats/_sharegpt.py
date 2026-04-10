"""ShareGPT format — conversation-style training data for instruction tuning.

ShareGPT format (widely used in open-source training datasets):
https://github.com/HuggingFaceH4/ShareGPT

Each record is a conversation with alternating "from" roles:
  human / gpt / system
"""

from __future__ import annotations

from orthrus.capture.turn import Turn


class ShareGPTFormatter:
    """ShareGPT conversation format exporter.

    Converts each Turn into a conversation with:
    1. Optional system message (from available_tools or active_skills)
    2. Human turn (query_text)
    3. GPT turn (response_text + optional reasoning_content)

    Returns None if query_text or response_text are missing.
    """

    @property
    def format_name(self) -> str:
        return "sharegpt"

    def format(self, turn: Turn) -> dict[str, object] | None:
        if not turn.query_text or not turn.response_text:
            return None

        # Build the conversation
        conversations: list[dict[str, str]] = []

        # Optional system message derived from context
        system_parts: list[str] = []
        if turn.available_tools:
            system_parts.append(f"Tools available: {', '.join(turn.available_tools)}")
        if turn.active_skills:
            system_parts.append(f"Active skills: {', '.join(turn.active_skills)}")
        if system_parts:
            conversations.append({
                "from": "system",
                "value": "\n".join(system_parts),
            })

        # Human turn
        conversations.append({
            "from": "human",
            "value": turn.query_text,
        })

        # GPT turn: include reasoning_content as a prefix if present
        gpt_value = turn.response_text
        if turn.reasoning_content:
            gpt_value = f"<reasoning>\n{turn.reasoning_content}\n</reasoning>\n\n{gpt_value}"

        conversations.append({
            "from": "gpt",
            "value": gpt_value,
        })

        # Build output record
        record: dict[str, object] = {
            "conversations": conversations,
            "turn_id": turn.trace_id,
            "session_id": turn.session_id,
            "timestamp": turn.timestamp.isoformat(),
        }

        # Include quality metadata if available
        if turn.user_rating is not None:
            record["quality"] = turn.user_rating

        # Include outcome as a tag
        if turn.outcome.value != "success":
            record["outcome"] = turn.outcome.value

        # Include tool calls summary if present
        if turn.tool_calls:
            record["tool_calls"] = [
                {
                    "tool": tc.tool_name,
                    "duration_ms": tc.duration_ms,
                    "success": tc.success,
                }
                for tc in turn.tool_calls
            ]

        return record
