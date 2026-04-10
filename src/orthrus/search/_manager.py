"""SearchManager — combines text and vector search with RRF fusion."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import numpy as np
import structlog

from orthrus.search._text import text_search
from orthrus.search._vector import _INDEX_METADATA, vector_search

if TYPE_CHECKING:
    from orthrus.embedding import EmbeddingBackend
    from orthrus.storage import StorageManager

logger = structlog.get_logger(__name__)

# RRF constant — standard value from Glei et al. SIGIR 2019
_RRF_K = 60

# ---------------------------------------------------------------------------
# Filterable field registry
# ---------------------------------------------------------------------------

# Registry of Turn fields that can be used in SearchQuery.filters.
# Maps field name -> type coercion function (value from filters dict -> Python value).
# Adding a new field = add one entry here.
SEARCHABLE_FIELDS: dict[str, Callable[[Any], Any]] = {
    "outcome": str,
    "session_id": str,
    "duration_ms": int,
    "schema_version": int,
    "capture_profile": str,
    "platform": str,
    "active_skills": lambda v: tuple(v) if isinstance(v, list) else v,
    "available_tools": lambda v: tuple(v) if isinstance(v, list) else v,
    "parent_trace_id": lambda v: str(v) if v is not None else None,
    "error_class": lambda v: str(v) if v is not None else None,
    # Timestamp is handled specially (range queries), not via this registry
}


def _coerce_filters(filters: dict[str, Any]) -> dict[str, Any]:
    """Coerce filter values to their expected Python types."""
    coerced: dict[str, Any] = {}
    for field_name, value in filters.items():
        if field_name == "timestamp":
            # timestamp filtering handled separately
            coerced[field_name] = value
        elif field_name in SEARCHABLE_FIELDS:
            try:
                coerced[field_name] = SEARCHABLE_FIELDS[field_name](value)
            except (ValueError, TypeError) as exc:
                logger.debug(
                    "filter_coerce_failed",
                    field=field_name,
                    value=value,
                    error=str(exc),
                )
                coerced[field_name] = value
        else:
            coerced[field_name] = value
    return coerced


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SearchQuery:
    """Query specification for search.

    Attributes:
        text: Text to search for in query_text (substring or regex if use_regex=True).
        vector: Query embedding vector (list[float]). If set, vector search is run.
        use_regex: If True, ``text`` is treated as a regex pattern.
        mode: Search mode — "auto" (text+vector if both set), "text" (text only),
            "vector" (vector only), "hybrid" (both, fused via RRF).
        filters: Field filters applied before ranking. Supported fields:
            outcome, session_id, duration_ms, schema_version, capture_profile,
            platform, active_skills, available_tools, parent_trace_id, error_class,
            timestamp (as ISO string or (min, max) tuple for range).
        max_results: Maximum results to return (default 10).
        text_max_results: Max text search results to consider for fusion (default 100).
        vector_max_results: Max vector search results to consider for fusion (default 100).
        hybrid_rerank_top_k: For hybrid mode, how many top results to load full data for.
    """

    text: str | None = None
    vector: list[float] | None = None
    use_regex: bool = False
    mode: Literal["auto", "text", "vector", "hybrid"] = "auto"
    filters: dict[str, Any] = field(default_factory=dict)
    max_results: int = 10
    text_max_results: int = 100
    vector_max_results: int = 100
    hybrid_rerank_top_k: int = 20

    def __post_init__(self) -> None:
        if self.mode not in ("auto", "text", "vector", "hybrid"):
            raise ValueError(f"Invalid mode: {self.mode!r}")


@dataclass
class SearchResult:
    """A single search result.

    Attributes:
        trace_id: Unique turn identifier (UUID7).
        score: Relevance score (higher = better). In hybrid mode this is the
            RRF score. In text/vector mode it's the native score.
        turn_data: Full turn data dict loaded from storage.
    """

    trace_id: str
    score: float
    turn_data: dict[str, Any]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class SearchError(Exception):
    """Raised when search fails."""


# ---------------------------------------------------------------------------
# SearchManager
# ---------------------------------------------------------------------------


class SearchManager:
    """Manages search over stored turns.

    Combines full-text search and vector similarity search using
    Reciprocal Rank Fusion (RRF) for hybrid ranking.

    Args:
        storage: StorageManager instance for reading parquet files.
        embedding: Optional EmbeddingBackend for vectorizing query text.
            Required for vector search when SearchQuery.vector is not provided.
        index_dir: Optional directory for persisted Annoy index files.
            If None, index is held in memory only (rebuilt each session).
    """

    def __init__(
        self,
        storage: StorageManager,
        embedding: EmbeddingBackend | None = None,
        index_dir: Path | None = None,
    ) -> None:
        self._storage = storage
        self._embedding = embedding
        self._index_dir = index_dir

    # ------------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------------

    def search(self, query: SearchQuery) -> list[SearchResult]:
        """Execute a search query.

        Args:
            query: SearchQuery specifying text, vector, mode, and filters.

        Returns:
            List of SearchResult ordered by descending relevance score.

        Raises:
            SearchError: If query.vector is needed but no embedding backend
                is configured, or if storage reads fail.
        """
        # Resolve effective mode
        mode = _resolve_mode(query)

        if mode == "text":
            return self._search_text(query)
        elif mode == "vector":
            return self._search_vector(query)
        elif mode == "hybrid":
            return self._search_hybrid(query)
        else:
            return self._search_auto(query)

    def build_index(self, *, force: bool = False) -> bool:
        """Build or rebuild the Annoy index from stored turns.

        Args:
            force: If True, always rebuild. If False, only rebuild if stale.

        Returns:
            True if index was built or is already current. False on failure.
        """
        from orthrus.search._vector import _AnnoyIndex

        if self._index_dir is None:
            logger.warning("build_index_no_index_dir")
            return False

        parquet_paths = self._storage.get_hot_files()
        if not parquet_paths:
            return True

        dimensions = self._get_embedding_dimensions()
        index = _AnnoyIndex(self._index_dir, dimensions=dimensions)

        if not force and not index.is_stale(parquet_paths):
            return True

        # Collect embeddings
        trace_ids: list[str] = []
        embeddings: list[np.ndarray] = []

        for path in parquet_paths:
            try:
                from orthrus.storage._parquet import read_turns

                rows = read_turns(path)
            except Exception as exc:
                logger.warning("build_index_read_error", path=str(path), error=str(exc))
                continue

            for row in rows:
                emb = row.get("query_embedding")
                if emb is None:
                    continue
                vec = np.array(emb, dtype=np.float32)
                trace_ids.append(str(row["trace_id"]))
                embeddings.append(vec)

        if not embeddings:
            return True

        embeddings_array = np.stack(embeddings, axis=0)
        return index.build(parquet_paths, trace_ids, embeddings_array)

    def index_status(self) -> dict[str, Any]:
        """Return the status of the search index.

        Returns a dict with keys:
            index_dir: Path to index directory (or None).
            exists: Whether index files exist on disk.
            stale: Whether index is older than parquet source files.
            num_vectors: Number of vectors indexed (from metadata, if available).
        """
        from orthrus.search._vector import _AnnoyIndex

        status: dict[str, Any] = {
            "index_dir": str(self._index_dir) if self._index_dir else None,
            "exists": False,
            "stale": True,
            "num_vectors": 0,
        }

        if self._index_dir is None:
            return status

        index_path = self._index_dir / "search.ann"
        meta_path = self._index_dir / _INDEX_METADATA

        if not index_path.exists():
            return status

        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            status["num_vectors"] = meta.get("num_vectors", 0)
        except Exception:
            pass

        dimensions = self._get_embedding_dimensions()
        index = _AnnoyIndex(self._index_dir, dimensions=dimensions)
        parquet_paths = self._storage.get_hot_files()

        status["exists"] = True
        status["stale"] = index.is_stale(parquet_paths)

        return status

    # ------------------------------------------------------------------------
    # Internal — mode dispatch
    # ------------------------------------------------------------------------

    def _search_auto(self, query: SearchQuery) -> list[SearchResult]:
        """Auto mode: use text if text is set, vector if vector is set, both if both."""
        if query.text and query.vector:
            return self._search_hybrid(query)
        elif query.vector:
            return self._search_vector(query)
        elif query.text:
            return self._search_text(query)
        else:
            return []

    def _search_text(self, query: SearchQuery) -> list[SearchResult]:
        parquet_paths = self._storage.get_hot_files()
        if not parquet_paths:
            return []

        coerced_filters = _coerce_filters(query.filters)
        text_matches = text_search(
            parquet_paths,
            query.text or "",
            use_regex=query.use_regex,
            filters=coerced_filters,
            max_results=query.text_max_results,
        )

        trace_ids = [m.trace_id for m in text_matches]
        scores = {m.trace_id: m.score for m in text_matches}
        turn_data = self._load_turns_by_id(trace_ids, limit=len(trace_ids))

        return [
            SearchResult(trace_id=tid, score=scores[tid], turn_data=data)
            for tid, data in turn_data.items()
            if tid in scores
        ]

    def _search_vector(self, query: SearchQuery) -> list[SearchResult]:
        if query.vector is None:
            raise SearchError("vector search requires a query vector")

        parquet_paths = self._storage.get_hot_files()
        if not parquet_paths:
            return []

        dimensions = self._get_embedding_dimensions()
        query_vec = np.array(query.vector, dtype=np.float32)

        if query_vec.shape[-1] != dimensions:
            raise SearchError(
                f"query vector has {query_vec.shape[-1]} dimensions, "
                f"expected {dimensions}"
            )

        vector_matches = vector_search(
            parquet_paths,
            query_vec,
            max_results=query.vector_max_results,
            use_annoy=True,
            index_dir=self._index_dir,
            dimensions=dimensions,
        )

        trace_ids = [m.trace_id for m in vector_matches]
        scores = {m.trace_id: m.score for m in vector_matches}
        turn_data = self._load_turns_by_id(trace_ids, limit=len(trace_ids))

        return [
            SearchResult(trace_id=tid, score=scores[tid], turn_data=data)
            for tid, data in turn_data.items()
            if tid in scores
        ]

    def _search_hybrid(self, query: SearchQuery) -> list[SearchResult]:
        """Run text and vector search, fuse with RRF."""
        # Get text results (if text query provided)
        text_scores: dict[str, float] = {}
        if query.text:
            parquet_paths = self._storage.get_hot_files()
            if parquet_paths:
                coerced_filters = _coerce_filters(query.filters)
                text_matches = text_search(
                    parquet_paths,
                    query.text,
                    use_regex=query.use_regex,
                    filters=coerced_filters,
                    max_results=query.text_max_results,
                )
                for rank, m in enumerate(text_matches, start=1):
                    text_scores[m.trace_id] = _rrf_score(rank)

        # Get vector results (if vector provided or we can embed the text)
        vector_scores: dict[str, float] = {}
        query_vec: np.ndarray | None = None

        if query.vector is not None:
            query_vec = np.array(query.vector, dtype=np.float32)
        elif query.text and self._embedding is not None:
            # Embed the query text using the backend
            try:
                query_vec = self._embed_text(query.text)
            except Exception as exc:
                logger.warning("hybrid_embedding_failed", error=str(exc))

        if query_vec is not None:
            dimensions = self._get_embedding_dimensions()
            if query_vec.shape[-1] != dimensions:
                logger.warning(
                    "hybrid_vector_dimension_mismatch",
                    expected=dimensions,
                    got=query_vec.shape[-1],
                )
            else:
                parquet_paths = self._storage.get_hot_files()
                if parquet_paths:
                    vector_matches = vector_search(
                        parquet_paths,
                        query_vec,
                        max_results=query.vector_max_results,
                        use_annoy=True,
                        index_dir=self._index_dir,
                        dimensions=dimensions,
                    )
                    for rank, vm in enumerate(vector_matches, start=1):
                        vector_scores[vm.trace_id] = _rrf_score(rank)

        # Fused scores — union of trace_ids from both rankers
        all_trace_ids = set(text_scores) | set(vector_scores)
        fused: dict[str, float] = {}
        for tid in all_trace_ids:
            s = text_scores.get(tid, 0.0) + vector_scores.get(tid, 0.0)
            fused[tid] = s

        # Sort by fused score descending
        ranked = sorted(fused.items(), key=lambda x: (-x[1], x[0]))

        # Load full turn data for top-k results
        top_trace_ids = [tid for tid, _ in ranked[: query.hybrid_rerank_top_k]]
        turn_data = self._load_turns_by_id(top_trace_ids, limit=len(top_trace_ids))

        return [
            SearchResult(trace_id=tid, score=score, turn_data=turn_data.get(tid, {}))
            for tid, score in ranked
            if tid in turn_data
        ]

    # ------------------------------------------------------------------------
    # Internal — helpers
    # ------------------------------------------------------------------------

    def _embed_text(self, text: str) -> np.ndarray:
        """Embed text using the configured embedding backend (synchronous)."""
        if self._embedding is None:
            raise SearchError("no embedding backend configured")

        # The backend encode method is synchronous
        embeddings = self._embedding.encode([text])
        return np.array(embeddings[0], dtype=np.float32)

    def _get_embedding_dimensions(self) -> int:
        """Get embedding dimensions from backend or config."""
        if self._embedding is not None:
            return self._embedding.dimensions
        # Default fallback
        from orthrus.capture.turn import Turn

        return Turn.EXPECTED_EMBEDDING_DIMENSIONS

    def _load_turns_by_id(
        self, trace_ids: list[str], limit: int
    ) -> dict[str, dict[str, Any]]:
        """Load full turn data from parquet files by trace_id.

        Args:
            trace_ids: Ordered list of trace_ids to load.
            limit: Maximum number of results to load.

        Returns:
            Dict mapping trace_id -> turn data dict.
        """
        if not trace_ids:
            return {}

        trace_id_set = set(trace_ids[:limit])
        result: dict[str, dict[str, Any]] = {}
        parquet_paths = self._storage.get_hot_files()

        for path in parquet_paths:
            if len(result) >= limit:
                break
            try:
                from orthrus.storage._parquet import read_turns

                rows = read_turns(path)
            except Exception as exc:
                logger.warning("load_turns_read_error", path=str(path), error=str(exc))
                continue

            for row in rows:
                tid = row.get("trace_id")
                if tid in trace_id_set and tid not in result:
                    result[tid] = dict(row)
                    if len(result) >= limit:
                        break

        return result


# ---------------------------------------------------------------------------
# Internal — RRF
# ---------------------------------------------------------------------------


def _rrf_score(rank: int) -> float:
    """Reciprocal Rank Fusion score for a given rank (1-indexed)."""
    return 1.0 / (_RRF_K + rank)


def _resolve_mode(query: SearchQuery) -> Literal["text", "vector", "hybrid", "auto"]:
    """Resolve the effective search mode from a query."""
    if query.mode != "auto":
        return query.mode
    if query.text and query.vector:
        return "hybrid"
    elif query.vector:
        return "vector"
    elif query.text:
        return "text"
    else:
        return "auto"
