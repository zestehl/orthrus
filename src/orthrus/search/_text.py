"""Text search — substring and regex search over stored turns."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import structlog

from orthrus.storage._parquet import read_turns

logger = structlog.get_logger(__name__)


@dataclass
class _TextMatch:
    """A single text search match."""

    trace_id: str
    score: float  # Higher = better match


def text_search(
    parquet_paths: list[Path],
    query: str,
    *,
    use_regex: bool = False,
    filters: dict[str, object] | None = None,
    max_results: int = 100,
) -> list[_TextMatch]:
    """Search turns by substring or regex match on query_text.

    Scoring: results are scored by position and length ratio.
    Earlier matches score higher; longer query coverage scores higher.

    Args:
        parquet_paths: Parquet files to search.
        query: Search string (substring or regex pattern).
        use_regex: If True, ``query`` is a regex pattern.
        filters: Optional field filters (applied before scoring).
        max_results: Maximum results to return.

    Returns:
        List of _TextMatch, ordered by descending score.
    """
    if not query or not query.strip():
        return []

    filters = filters or {}

    try:
        if use_regex:
            pattern = re.compile(query, re.IGNORECASE)
        else:
            # Escape special regex chars for literal substring search
            escaped = re.escape(query)
            pattern = re.compile(escaped, re.IGNORECASE)
    except re.error as exc:
        logger.warning("text_search_invalid_regex", query=query, error=str(exc))
        return []

    matches: list[_TextMatch] = []

    for path in parquet_paths:
        try:
            rows = read_turns(path)
        except Exception as exc:
            logger.warning("text_search_read_error", path=str(path), error=str(exc))
            continue

        for row in rows:
            # Apply filters first
            if not _passes_filters(row, filters):
                continue

            query_text = row.get("query_text", "")
            if not isinstance(query_text, str):
                continue

            m = pattern.search(query_text)
            if not m:
                continue

            # Score: combination of position (earlier is better) and coverage ratio
            match_pos = m.start()
            match_len = m.end() - m.start()
            text_len = len(query_text)

            # Position score: 1.0 at start, decays linearly to 0.0 at end
            pos_score = 1.0 - (match_pos / max(text_len, 1))

            # Coverage score: how much of the query matched
            coverage_score = match_len / max(len(query), 1)

            # Combined score: geometric mean of position and coverage
            score = (pos_score * coverage_score) ** 0.5

            matches.append(_TextMatch(trace_id=str(row["trace_id"]), score=score))

    # Sort by descending score, then ascending trace_id as tiebreaker
    matches.sort(key=lambda m: (-m.score, m.trace_id))
    return matches[:max_results]


def _passes_filters(row: dict[str, object], filters: dict[str, object]) -> bool:
    """Check if a row passes all filters."""
    for field, expected in filters.items():
        if field not in row:
            # Unknown filter field — ignore (pass through)
            continue

        value = row[field]

        if isinstance(expected, str) and isinstance(value, str):
            # String containment match for string filters
            if expected.lower() not in value.lower():
                return False
        elif isinstance(expected, (list, tuple)) and hasattr(expected, "__iter__"):
            # Membership check — any element of expected must be in value
            # value is a tuple/list (stored in parquet), cast for mypy
            value_seq: Sequence[object] = value  # type: ignore[assignment]
            if not any(item in value_seq for item in expected if item is not None):
                return False
        else:
            # Direct equality
            if value != expected:
                return False

    return True
