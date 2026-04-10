"""Turn and ToolCall dataclasses — the atomic unit of agent telemetry.

Immutable, validated at construction. The foundation of Orthrus.
"""

from __future__ import annotations

import math
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import ClassVar

from orthrus.capture._uuid7 import _UUID7_PATTERN

# Max length for text fields (10KB)
_MAX_TEXT_LENGTH = 10_000

# SHA-256 hex pattern (64 chars)
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

# Control chars to preserve (tab, newline, carriage return)
_KEEP_CONTROL = frozenset({"\t", "\n", "\r"})


class TurnOutcome(Enum):
    """Outcome of an agent turn."""

    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    PARTIAL = "partial"


def _sanitize_text(value: str, *, max_length: int = _MAX_TEXT_LENGTH) -> str:
    """Sanitize text: strip control chars (except \\t\\n\\r), enforce max length.

    Args:
        value: Raw text string.
        max_length: Maximum allowed length.

    Returns:
        Sanitized text.

    Raises:
        ValueError: If text exceeds max length or is empty/whitespace after sanitization.
    """
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


def _validate_embedding(
    value: list[float] | tuple[float, ...] | None,
    *,
    expected_dimensions: int | None = None,
) -> tuple[float, ...] | None:
    """Validate embedding vector: no NaN/Inf, correct dimensions, convert to tuple.

    Args:
        value: Raw embedding (list or tuple of floats).
        expected_dimensions: If set, require exactly this many dimensions.

    Returns:
        Validated tuple of floats, or None.

    Raises:
        ValueError: If NaN/Inf found or dimensions mismatch.
    """
    if value is None:
        return None
    tup = tuple(float(x) for x in value)
    if any(not math.isfinite(x) for x in tup):
        raise ValueError("Embedding contains NaN or Inf values")
    if expected_dimensions is not None and len(tup) != expected_dimensions:
        raise ValueError(f"Embedding has {len(tup)} dimensions, expected {expected_dimensions}")
    return tup


def _get_orthrus_version() -> str:
    """Get the current Orthrus version."""
    try:
        from importlib.metadata import version

        return version("orthrus")
    except Exception:
        return "0.1.0"


def _get_platform() -> str:
    """Get platform identifier string."""
    return f"{sys.platform}-{__import__('platform').machine()}"


# --- Pre-compute interned strings (same for all turns in a session) ---
_ORTHRUS_VERSION = sys.intern(_get_orthrus_version())
_PLATFORM = sys.intern(_get_platform())


@dataclass(frozen=True, slots=True)
class ToolCall:
    """A single tool invocation within a turn.

    Immutable. Arguments and outputs are stored as SHA-256 hashes
    to avoid storing potentially sensitive data directly.
    """

    tool_name: str
    arguments_hash: str
    output_hash: str
    duration_ms: int
    exit_code: int
    success: bool

    def __post_init__(self) -> None:
        # tool_name: non-empty string
        if not isinstance(self.tool_name, str) or not self.tool_name.strip():
            raise ValueError("tool_name cannot be empty")
        object.__setattr__(self, "tool_name", self.tool_name.strip())

        # arguments_hash: SHA-256
        validated_args = _validate_sha256(self.arguments_hash, "arguments_hash")
        object.__setattr__(self, "arguments_hash", validated_args)

        # output_hash: SHA-256
        validated_out = _validate_sha256(self.output_hash, "output_hash")
        object.__setattr__(self, "output_hash", validated_out)

        # duration_ms: non-negative
        if not isinstance(self.duration_ms, int) or self.duration_ms < 0:
            raise ValueError(f"duration_ms must be non-negative int, got {self.duration_ms}")


@dataclass(frozen=True, slots=True)
class Turn:
    """Atomic agent interaction record.

    Immutable, validated at construction. Every field is checked on creation
    so that invalid data never enters the system.
    """

    # --- Required fields ---
    trace_id: str
    session_id: str
    timestamp: datetime
    query_text: str
    context_hash: str
    available_tools: tuple[str, ...]

    # --- Optional fields ---
    parent_trace_id: str | None = None
    query_embedding: tuple[float, ...] | None = None
    active_skills: tuple[str, ...] = ()
    reasoning_content: str | None = None
    tool_selection: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    outcome: TurnOutcome = TurnOutcome.SUCCESS
    duration_ms: int = 0
    error_class: str | None = None
    user_rating: float | None = None
    response_text: str | None = None
    response_embedding: tuple[float, ...] | None = None

    # --- Providence ---
    schema_version: int = 1
    orthrus_version: str = field(default_factory=lambda: _ORTHRUS_VERSION)
    capture_profile: str = "standard"
    platform: str = field(default_factory=lambda: _PLATFORM)

    # Non-field: configuration constant
    EXPECTED_EMBEDDING_DIMENSIONS: ClassVar[int] = 384

    def __post_init__(self) -> None:
        # --- trace_id: must be valid UUID7 ---
        if not isinstance(self.trace_id, str):
            raise ValueError(f"trace_id: expected str, got {type(self.trace_id).__name__}")
        if not _UUID7_PATTERN.match(self.trace_id):
            raise ValueError(f"trace_id: invalid UUID7: {self.trace_id!r}")

        # --- session_id: non-empty string ---
        if not isinstance(self.session_id, str) or not self.session_id.strip():
            raise ValueError("session_id cannot be empty")
        object.__setattr__(self, "session_id", self.session_id.strip())

        # --- timestamp: must be timezone-aware, normalize to UTC ---
        if not isinstance(self.timestamp, datetime):
            raise ValueError(f"timestamp: expected datetime, got {type(self.timestamp).__name__}")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC)")
        # Normalize to UTC if not already UTC
        if self.timestamp.tzinfo != UTC:
            utc_ts = self.timestamp.astimezone(UTC)
            object.__setattr__(self, "timestamp", utc_ts)

        # --- query_text: sanitize ---
        try:
            sanitized_query = _sanitize_text(self.query_text)
        except ValueError as e:
            raise ValueError(f"query_text: {e}") from e
        object.__setattr__(self, "query_text", sanitized_query)

        # --- context_hash: SHA-256 ---
        validated_ctx = _validate_sha256(self.context_hash, "context_hash")
        object.__setattr__(self, "context_hash", validated_ctx)

        # --- available_tools: normalize to tuple ---
        if isinstance(self.available_tools, list):
            object.__setattr__(self, "available_tools", tuple(self.available_tools))

        # --- active_skills: normalize to tuple ---
        if isinstance(self.active_skills, list):
            object.__setattr__(self, "active_skills", tuple(self.active_skills))

        # --- tool_calls: normalize to tuple ---
        if isinstance(self.tool_calls, list):
            object.__setattr__(self, "tool_calls", tuple(self.tool_calls))

        # --- query_embedding: validate ---
        if self.query_embedding is not None:
            validated_emb = _validate_embedding(
                self.query_embedding,
                expected_dimensions=self.EXPECTED_EMBEDDING_DIMENSIONS,
            )
            object.__setattr__(self, "query_embedding", validated_emb)

        # --- response_embedding: validate ---
        if self.response_embedding is not None:
            validated_resp_emb = _validate_embedding(self.response_embedding)
            object.__setattr__(self, "response_embedding", validated_resp_emb)

        # --- duration_ms: non-negative ---
        if not isinstance(self.duration_ms, int) or self.duration_ms < 0:
            raise ValueError(f"duration_ms must be non-negative int, got {self.duration_ms}")

        # --- parent_trace_id: if present, must be valid UUID7 ---
        if self.parent_trace_id is not None and not _UUID7_PATTERN.match(self.parent_trace_id):
            raise ValueError(f"parent_trace_id: invalid UUID7: {self.parent_trace_id!r}")

        # --- response_text: sanitize if present ---
        if self.response_text is not None:
            sanitized_resp = _sanitize_text(self.response_text)
            object.__setattr__(self, "response_text", sanitized_resp)

        # --- reasoning_content: sanitize if present ---
        if self.reasoning_content is not None:
            sanitized_reasoning = _sanitize_text(self.reasoning_content)
            object.__setattr__(self, "reasoning_content", sanitized_reasoning)

    def with_embedding(self, embedding: list[float]) -> Turn:
        """Return a new Turn with query_embedding set (immutable update).

        Args:
            embedding: Float vector to attach.

        Returns:
            New Turn instance with embedding set.

        Raises:
            ValueError: If embedding contains NaN/Inf or wrong dimensions.
        """
        validated = _validate_embedding(
            embedding,
            expected_dimensions=self.EXPECTED_EMBEDDING_DIMENSIONS,
        )
        # Build new instance from current slots
        kwargs = {
            k: getattr(self, k)
            for k in self.__slots__  # slots only, no ClassVar
        }
        kwargs["query_embedding"] = validated
        return Turn(**kwargs)
