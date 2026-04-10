"""JSONL streaming writer for Turn records.

One file per (session_id, date). Append-only, line-delimited JSON.
Writes are buffered and flushed on flush_interval or close.
"""

from __future__ import annotations

import json
from pathlib import Path

import structlog

from orthrus.capture.turn import ToolCall, Turn

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Record conversion
# ---------------------------------------------------------------------------


def turn_to_jsonl_record(turn: Turn) -> dict[str, object]:
    """Serialize a Turn as a JSON-serializable dict for JSONL storage.

    Embeddings are stored as lists (not base64) for human readability.
    """
    def _emb(values: tuple[float, ...] | None) -> list[float] | None:
        return list(values) if values is not None else None

    def _tools(tool_calls: tuple[ToolCall, ...]) -> list[dict[str, object]]:
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

        "context_ref": turn.context_hash,
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

        "orthrus_version": turn.orthrus_version,
        "capture_profile": turn.capture_profile,
        "platform": turn.platform,
    }


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


class JSONLWriter:
    """Append-only JSONL writer with buffered I/O.

    One file per (session_id, date). Subsequent writes append lines.
    """

    _BUFFER_SIZE = 64  # lines to buffer before flushing

    def __init__(self, path: Path) -> None:
        """Initialize writer for the given path.

        Args:
            path: JSONL file path. Created (or opened for append) on first write.
        """
        self._path = path
        self._buffer: list[str] = []
        self._bytes_written = 0
        self._lines_written = 0
        self._closed = False

    def write(self, turn: Turn) -> None:
        """Buffer a single Turn. Flushes automatically when buffer is full."""
        record = turn_to_jsonl_record(turn)
        line = json.dumps(record, ensure_ascii=False)
        self._buffer.append(line)
        self._bytes_written += len(line.encode("utf-8")) + 1  # +1 for newline
        self._lines_written += 1
        if len(self._buffer) >= self._BUFFER_SIZE:
            self._flush()

    def write_batch(self, turns: list[Turn]) -> None:
        """Buffer multiple Turns."""
        for turn in turns:
            record = turn_to_jsonl_record(turn)
            line = json.dumps(record, ensure_ascii=False)
            self._buffer.append(line)
            self._bytes_written += len(line.encode("utf-8")) + 1
            self._lines_written += 1
        if self._buffer:
            self._flush()

    def _flush(self) -> None:
        """Write buffered lines to disk (append mode)."""
        if not self._buffer:
            return

        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "a", encoding="utf-8") as fh:
            fh.write("\n".join(self._buffer))
            fh.write("\n")

        logger.debug(
            "jsonl_flushed",
            path=str(self._path),
            lines=len(self._buffer),
        )
        self._buffer.clear()

    def close(self) -> None:
        """Flush remaining records and close."""
        if self._closed:
            return
        self._flush()
        self._closed = True

    def __enter__(self) -> JSONLWriter:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @property
    def lines_written(self) -> int:
        """Total lines written (including unflushed buffer)."""
        return self._lines_written


# ---------------------------------------------------------------------------
# Reading helpers
# ---------------------------------------------------------------------------


def read_jsonl(path: Path) -> list[dict[str, object]]:
    """Read all lines from a JSONL file.

    Args:
        path: JSONL file to read.

    Returns:
        List of parsed JSON objects.
    """
    records: list[dict[str, object]] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def jsonl_file_stats(path: Path) -> dict[str, object]:
    """Return stats for a JSONL file."""
    line_count = 0
    size_bytes = 0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            size_bytes += len(line.encode("utf-8"))
            line_count += 1
    return {
        "path": str(path),
        "num_lines": line_count,
        "size_bytes": size_bytes,
    }
