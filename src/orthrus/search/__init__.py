"""Orthrus search module — full-text and vector similarity search over turns.

Public API
----------
SearchQuery : dataclass
    Query specification with filters and ranking options.
SearchResult : dataclass
    A single search result with trace_id, score, and turn_data.
SearchManager : class
    Manages search over stored turns, combining text and vector search.

Example
-------
::

    from orthrus.search import SearchManager, SearchQuery
    from orthrus.embedding import TransformersBackend

    backend = TransformersBackend()
    manager = SearchManager(storage=storage_manager, embedding=backend)

    results = manager.search(SearchQuery(text="what is susy"))
    for r in results:
        print(r.score, r.turn_data["query_text"])

    # With filters
    results = manager.search(SearchQuery(
        text="error",
        mode="hybrid",
        filters={"outcome": "error"},
        max_results=20,
    ))
"""

from __future__ import annotations

from orthrus.search._manager import (
    SEARCHABLE_FIELDS,
    SearchError,
    SearchManager,
    SearchQuery,
    SearchResult,
)

__all__ = [
    "SearchQuery",
    "SearchResult",
    "SearchManager",
    "SearchError",
    "SEARCHABLE_FIELDS",
]
