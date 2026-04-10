"""TurnData, CaptureResult, and CaptureStatus dataclasses.

TurnData is the validated input to CaptureManager.capture().
CaptureResult is the output returned to the caller.
CaptureStatus is a snapshot of the capture pipeline health.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orthrus.capture.turn import ToolCall, TurnOutcome

    # ResourceProfile for type annotation only

# Max length for text fields (10KB) — mirrors Turn field limits
_MAX_TEXT_LENGTH = 10_000

# SHA-256 hex pattern (64 chars)
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

# Control chars to preserve (tab, newline, carriage return)
_KEEP_CONTROL = frozenset({"\t", "\n", "\r"})


def _sanitize_text(value: str, *, max_length: int = _MAX_TEXT_LENGTH) -> str:
    """Sanitize text: strip control chars (except \\t\\n\\r), enforce max length."""
    if len(value) > max_length:
        raise ValueError(f"Text exceeds max length ({max_length}): {len(value)}")
    sanitized = "".join(c for c in value if ord(c) >= 32 or c in _KEEP_CONTROL)
    if not sanitized.strip():
        raise ValueError("Text cannot be empty or whitespace-only")
    return sanitized


def _validate_sha256(value: str, field_name: str) -> str:
    """Validate and normalize a SHA-256 hex string."""
    if not isinstance(value, str):
        raise ValueError(f"{field_name}: expected str, got {type(value).__name__}")
    normalized = value.lower()
    if not _SHA256_PATTERN.match(normalized):
        raise ValueError(f"{field_name}: expected 64 hex chars (SHA-256), got {value!r}")
    return normalized


def _validate_tool_calls(
    value: list[ToolCall] | tuple[ToolCall, ...],
) -> tuple[ToolCall, ...]:
    """Normalize tool_calls to tuple."""
    if isinstance(value, list):
        return tuple(value)
    return value


# Lazily resolved enums — imported from turn.py to avoid circular imports
_turn_outcome_typ: type | None = None


def _get_turn_outcome() -> type[TurnOutcome]:
    global _turn_outcome_typ
    if _turn_outcome_typ is None:
        from orthrus.capture.turn import TurnOutcome

        _turn_outcome_typ = TurnOutcome
    return _turn_outcome_typ


@dataclass(frozen=True, slots=True)
class TurnData:
    """Validated input for a single agent turn.

    This is the boundary input to CaptureManager.capture(). All fields
    are validated at construction so that invalid data never enters
    the ingest queue.

    The agent or integration layer constructs TurnData from its own
    representation and passes it to capture(). TurnData does not hold
    generated fields (trace_id, timestamp) — those are added by
    CaptureManager when the Turn is constructed.
    """

    # --- Required fields ---
    query_text: str
    context_hash: str
    available_tools: tuple[str, ...]
    tool_calls: tuple[ToolCall, ...]

    # --- Optional fields ---
    outcome: TurnOutcome | None = field(default=None)
    duration_ms: int = 0
    error_class: str | None = None
    reasoning_content: str | None = None
    tool_selection: str | None = None
    active_skills: tuple[str, ...] = ()
    response_text: str | None = None
    user_rating: float | None = None

    def __post_init__(
        self,
    ) -> None:
        # --- outcome: resolve from string or enum ---
        turn_outcome_cls = _get_turn_outcome()
        if self.outcome is None:
            # Default to SUCCESS if not provided
            object.__setattr__(self, "outcome", turn_outcome_cls.SUCCESS)
        elif isinstance(self.outcome, str):
            try:
                object.__setattr__(self, "outcome", turn_outcome_cls(self.outcome))
            except ValueError:
                raise ValueError(
                    f"outcome: invalid value {self.outcome!r}, "
                    f"expected one of {[e.value for e in turn_outcome_cls]}"
                ) from None

        # --- query_text: sanitize ---
        try:
            sanitized = _sanitize_text(self.query_text)
        except ValueError as e:
            raise ValueError(f"query_text: {e}") from e
        object.__setattr__(self, "query_text", sanitized)

        # --- context_hash: validate ---
        validated_ctx = _validate_sha256(self.context_hash, "context_hash")
        object.__setattr__(self, "context_hash", validated_ctx)

        # --- available_tools: normalize to tuple ---
        if isinstance(self.available_tools, list):
            object.__setattr__(self, "available_tools", tuple(self.available_tools))

        # --- tool_calls: normalize to tuple ---
        validated_tc = _validate_tool_calls(self.tool_calls)
        object.__setattr__(self, "tool_calls", validated_tc)

        # --- active_skills: normalize to tuple ---
        if isinstance(self.active_skills, list):
            object.__setattr__(self, "active_skills", tuple(self.active_skills))

        # --- duration_ms: non-negative ---
        if not isinstance(self.duration_ms, int) or self.duration_ms < 0:
            raise ValueError(f"duration_ms: must be non-negative int, got {self.duration_ms}")

        # --- response_text: sanitize if present ---
        if self.response_text is not None:
            try:
                sanitized_resp = _sanitize_text(self.response_text)
            except ValueError as e:
                raise ValueError(f"response_text: {e}") from e
            object.__setattr__(self, "response_text", sanitized_resp)

        # --- reasoning_content: sanitize if present ---
        if self.reasoning_content is not None:
            try:
                sanitized_rc = _sanitize_text(self.reasoning_content)
            except ValueError as e:
                raise ValueError(f"reasoning_content: {e}") from e
            object.__setattr__(self, "reasoning_content", sanitized_rc)

        # --- user_rating: 0.0-1.0 range ---
        if self.user_rating is not None:
            if not isinstance(self.user_rating, (int, float)):
                raise ValueError(
                    f"user_rating: expected float, got {type(self.user_rating).__name__}"
                )
            if not (0.0 <= self.user_rating <= 1.0):
                raise ValueError(
                    f"user_rating: must be between 0.0 and 1.0, got {self.user_rating}"
                )

    def as_dict(self) -> dict[str, object]:
        """Return a dict suitable for Turn construction.

        Excludes fields that are auto-generated: trace_id, session_id,
        timestamp, schema_version, orthrus_version, capture_profile, platform.
        """
        from orthrus.capture.turn import TurnOutcome

        result = {}
        for name in self.__slots__:
            value = getattr(self, name)
            # Serialize TurnOutcome enum to its value
            if name == "outcome" and isinstance(value, TurnOutcome):
                value = value.value
            result[name] = value
        return result


@dataclass(frozen=True, slots=True)
class CaptureResult:
    """Outcome of a CaptureManager.capture() call."""

    trace_id: str
    error: str | None = None


@dataclass(frozen=True, slots=True)
class CaptureStatus:
    """Snapshot of the capture pipeline health."""

    queue_depth: int
    queue_max: int
    is_started: bool
    is_draining: bool
    total_captured: int
    total_queued: int
    total_written: int
    embedding_pending: int
    embedding_enabled: bool
    healthy: bool
