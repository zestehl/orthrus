"""Parquet writer for Turn records.

Append-only, row-grouped writes. Each session-date gets one file;
subsequent writes append row groups.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import structlog

from orthrus.capture.turn import ToolCall, Turn

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

# pyarrow ships with the package; importing here keeps the dependency explicit
try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "pyarrow is required for Parquet storage. Install with: uv pip install pyarrow"
    ) from exc


# Current schema version — bump for breaking changes
_SCHEMA_VERSION = 1

# Expected embedding dimensions (must match Turn.EXPECTED_EMBEDDING_DIMENSIONS)
_EMBEDDING_DIM = 384


def _build_schema() -> pa.Schema:
    """Return the canonical Parquet schema for a Turn record."""
        # Use tuple pairs: more compatible with pyarrow's schema() overloads
    pairs: list[tuple[str, pa.DataType]] = [
        # Identification
        ("trace_id", pa.string()),
        ("session_id", pa.string()),
        ("timestamp", pa.timestamp("us", tz="UTC")),
        ("schema_version", pa.int8()),
        # Input
        ("query_text", pa.string()),
        # query_embedding: nullable variable-length list (may be None or any length)
        ("query_embedding", pa.list_(pa.float32())),
        ("query_intent", pa.string()),
        # Context
        ("context_ref", pa.string()),
        ("available_tools", pa.list_(pa.string())),
        ("active_skills", pa.list_(pa.string())),
        # Reasoning
        ("reasoning_content", pa.string()),
        ("tool_selection", pa.string()),
        # Execution
        ("tool_calls", pa.string()),
        ("duration_ms", pa.int64()),
        ("outcome", pa.string()),
        # Response
        ("response_text", pa.string()),
        # response_embedding: nullable variable-length list
        ("response_embedding", pa.list_(pa.float32())),
        # Error
        ("error_class", pa.string()),
        # Providence
        ("orthrus_version", pa.string()),
        ("capture_profile", pa.string()),
        ("platform", pa.string()),
    ]
    return pa.schema(pairs)


TURN_SCHEMA = _build_schema()


# ---------------------------------------------------------------------------
# Record conversion
# ---------------------------------------------------------------------------


def _serialize_tool_calls(tool_calls: tuple[ToolCall, ...]) -> str:
    """Serialize a tuple of ToolCall into a JSON string."""
    return json.dumps([
        {
            "tool_name": tc.tool_name,
            "arguments_hash": tc.arguments_hash,
            "output_hash": tc.output_hash,
            "duration_ms": tc.duration_ms,
            "exit_code": tc.exit_code,
            "success": tc.success,
        }
        for tc in tool_calls
    ])


def turn_to_record(turn: Turn) -> dict[str, object]:
    """Convert a Turn dataclass into a dict of Arrow-compatible types.

    Args:
        turn: Validated Turn instance.

    Returns:
        Dict mapping column names to Arrow-compatible values.
    """
    # Helper: safely build embedding list with correct dimensions
    def _emb(
        values: tuple[float, ...] | None, *, fixed_dim: int | None = None
    ) -> list[float] | None:
        if values is None:
            return None
        result = list(values)
        if fixed_dim is not None and len(result) != fixed_dim:
            # Skip silently — schema allows wrong-dim embeddings through;
            # downstream quality gate will catch it
            return None
        return result

    return {
        "trace_id": turn.trace_id,
        "session_id": turn.session_id,
        "timestamp": turn.timestamp,
        "schema_version": _SCHEMA_VERSION,

        "query_text": turn.query_text,
        "query_embedding": _emb(turn.query_embedding, fixed_dim=_EMBEDDING_DIM),
        "query_intent": None,  # reserved for future use

        "context_ref": turn.context_hash,
        "available_tools": list(turn.available_tools),
        "active_skills": list(turn.active_skills),

        "reasoning_content": turn.reasoning_content,
        "tool_selection": turn.tool_selection,

        "tool_calls": _serialize_tool_calls(turn.tool_calls),
        "duration_ms": turn.duration_ms,
        "outcome": turn.outcome.value,

        "response_text": turn.response_text,
        "response_embedding": _emb(turn.response_embedding),

        "error_class": turn.error_class,

        "orthrus_version": turn.orthrus_version,
        "capture_profile": turn.capture_profile,
        "platform": turn.platform,
    }


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


class ParquetWriter:
    """Append-only Parquet writer with row-group flushing.

    One file per (session_id, date). Subsequent batches append row groups.
    """

    def __init__(
        self,
        path: Path,
        row_group_size: int = 1000,
    ) -> None:
        """Initialize writer for the given path.

        Args:
            path: Parquet file path. Created with schema on first write.
            row_group_size: Max rows per row group before forced flush.
        """
        self._path = path
        self._row_group_size = row_group_size
        self._buffer: list[dict[str, object]] = []
        self._writer: pq.ParquetWriter | None = None
        self._rows_written = 0

    def _init_writer(self) -> None:
        """Open (or create) the Parquet writer for self._path."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._writer = pq.ParquetWriter(
            self._path,
            TURN_SCHEMA,
            compression="snappy",  # fast, well-supported
        )

    def write(self, turn: Turn) -> None:
        """Buffer a single Turn. Flushes automatically when row group is full."""
        self._buffer.append(turn_to_record(turn))
        if len(self._buffer) >= self._row_group_size:
            self._flush()

    def write_batch(self, turns: list[Turn]) -> None:
        """Buffer multiple Turns. Flushes automatically when row group is full."""
        self._buffer.extend(turn_to_record(t) for t in turns)
        if len(self._buffer) >= self._row_group_size:
            self._flush()

    def _flush(self) -> None:
        """Write buffered records as a single row group to disk."""
        if not self._buffer:
            return

        if self._writer is None:
            self._init_writer()

        assert self._writer is not None

        table = pa.Table.from_pylist(self._buffer, schema=TURN_SCHEMA)
        table.to_pydict()  # validate

        self._writer.write_table(table, row_group_size=len(self._buffer))
        self._rows_written += len(self._buffer)
        self._buffer.clear()

        logger.debug(
            "parquet_flushed",
            path=str(self._path),
            rows=self._rows_written,
        )

    def close(self) -> None:
        """Flush remaining records and close the writer."""
        self._flush()
        if self._writer is not None:
            self._writer.close()
            self._writer = None

    def __enter__(self) -> ParquetWriter:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @property
    def rows_written(self) -> int:
        """Total rows written (including unflushed buffer)."""
        return self._rows_written + len(self._buffer)


# ---------------------------------------------------------------------------
# Reading helpers
# ---------------------------------------------------------------------------


def read_turns(path: Path) -> list[dict[str, object]]:
    """Read all rows from a Parquet file as plain dicts.

    Args:
        path: Parquet file to read.

    Returns:
        List of row dicts matching the Turn record schema.
    """
    table = pq.read_table(path)
    return cast("list[dict[str, object]]", table.to_pylist())


def parquet_file_stats(path: Path) -> dict[str, object]:
    """Return stats for a Parquet file (row count, size, schema version)."""
    pf = pq.ParquetFile(path)
    metadata = pf.metadata
    return {
        "path": str(path),
        "num_rows": metadata.num_rows,
        "num_row_groups": metadata.num_row_groups,
        "num_columns": metadata.num_columns,
        "size_bytes": path.stat().st_size,
        "schema_version": _SCHEMA_VERSION,
    }
