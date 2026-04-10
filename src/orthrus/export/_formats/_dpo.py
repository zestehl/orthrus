"""DPO format — preference pair training data for RLHF alignment.

DPO (Direct Preference Optimization) format from the DPO paper:
https://arxiv.org/abs/2305.18290

Each record contains:
  prompt    : the user query
  chosen    : the preferred assistant response
  rejected   : the dispreferred assistant response (synthesized from error/partial outcomes)

For successful turns, rejected is synthesized from the tool-call error information.
For error/partial turns, the response_text is the chosen and the rejected is
synthesized from the error context.
"""

from __future__ import annotations

from orthrus.capture.turn import Turn


class DPOFormatter:
    """DPO preference-pair format exporter.

    Generates a (prompt, chosen, rejected) triplet per turn.

    - chosen: always the assistant's response_text (if available)
    - rejected: synthesized from error context or tool failure information

    Returns None if query_text is missing (prompt is required for DPO).
    """

    @property
    def format_name(self) -> str:
        return "dpo"

    def format(self, turn: Turn) -> dict[str, object] | None:
        if not turn.query_text:
            return None

        # Build prompt from query + available context
        prompt_parts = [turn.query_text]
        if turn.available_tools:
            prompt_parts.append(f"[Tools: {', '.join(turn.available_tools)}]")
        if turn.active_skills:
            prompt_parts.append(f"[Skills: {', '.join(turn.active_skills)}]")
        prompt = "\n".join(prompt_parts)

        # Determine chosen response
        if turn.response_text:
            chosen = turn.response_text
            if turn.reasoning_content:
                chosen = f"<reasoning>\n{turn.reasoning_content}\n</reasoning>\n\n{chosen}"
        elif turn.outcome == turn.outcome.ERROR and turn.error_class:
            chosen = f"[Error: {turn.error_class}]"
        else:
            chosen = "[No response recorded]"

        # Determine rejected response
        if turn.outcome.value in ("error", "timeout", "partial"):
            if turn.tool_calls:
                failed = [
                    tc for tc in turn.tool_calls if not tc.success
                ]
                if failed:
                    rejected = (
                        f"[Tool failure: {failed[0].tool_name} "
                        f"exited with code {failed[0].exit_code}]"
                    )
                else:
                    rejected = "[Operation did not complete successfully]"
            elif turn.error_class:
                rejected = f"[Error: {turn.error_class}]"
            else:
                rejected = "[Request timed out or was interrupted]"
        else:
            # For successful turns, use a minimal/brief baseline as the rejected
            # (the user can replace this with their own baseline response)
            rejected = "[Skipped — no dispreferred response available]"

        return {
            "prompt": prompt,
            "chosen": chosen,
            "rejected": rejected,
            "turn_id": turn.trace_id,
            "session_id": turn.session_id,
            "timestamp": turn.timestamp.isoformat(),
            "outcome": turn.outcome.value,
        }
