"""Vector search — cosine similarity and Annoy approximate nearest neighbor search."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
import structlog

from orthrus.storage._parquet import read_turns

logger = structlog.get_logger(__name__)

# Annoy index metadata filename
_INDEX_METADATA = "index_meta.json"


@dataclass
class _VectorMatch:
    """A single vector search match."""

    trace_id: str
    score: float  # Cosine similarity [0, 1]


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors.

    Returns a float in [-1.0, 1.0] where 1.0 is identical direction,
    0.0 is orthogonal, and -1.0 is opposite.
    """
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


# ---------------------------------------------------------------------------
# Annoy index
# ---------------------------------------------------------------------------


class _AnnoyIndex:
    """Persistent Annoy index with lazy build and mtime-based staleness."""

    def __init__(
        self,
        index_dir: Path,
        dimensions: int,
        metric: str = "cosine",
    ) -> None:
        self._index_dir = index_dir
        self._dimensions = dimensions
        self._metric = metric
        self._index_path = index_dir / "search.ann"
        self._meta_path = index_dir / _INDEX_METADATA
        self._index: object | None = None

    @property
    def index_path(self) -> Path:
        return self._index_path

    @property
    def meta_path(self) -> Path:
        return self._meta_path

    def is_stale(self, parquet_paths: list[Path]) -> bool:
        """Check if the index is older than any of the parquet source file."""
        if not self._index_path.exists() or not self._meta_path.exists():
            return True

        index_mtime = self._index_path.stat().st_mtime
        return any(pq_path.stat().st_mtime > index_mtime for pq_path in parquet_paths)

    def load(self) -> bool:
        """Load the index from disk. Returns True on success, False on failure."""
        try:
            import annoy

            self._index = annoy.AnnoyIndex(self._dimensions, self._metric)
            self._index.load(str(self._index_path))  # type: ignore[union-attr]
            logger.info("annoy_index_loaded", path=str(self._index_path))
            return True
        except Exception as exc:
            logger.warning("annoy_index_load_failed", error=str(exc))
            self._index = None
            return False

    def build(
        self,
        parquet_paths: list[Path],
        trace_ids: list[str],
        embeddings: np.ndarray,
        num_trees: int = 100,
    ) -> bool:
        """Build and persist a new Annoy index from embeddings.

        Returns True on success, False on failure (falls back to brute-force).
        """
        try:
            import annoy

            self._index_dir.mkdir(parents=True, exist_ok=True)

            index = annoy.AnnoyIndex(self._dimensions, self._metric)
            for i, embedding in enumerate(embeddings):
                index.add_item(i, embedding.tolist())

            index.build(num_trees)

            # Write index
            index.save(str(self._index_path))

            # Write metadata
            meta = {
                "trace_ids": trace_ids,
                "num_vectors": len(trace_ids),
                "dimensions": self._dimensions,
                "metric": self._metric,
                "num_trees": num_trees,
            }
            self._meta_path.write_text(json.dumps(meta), encoding="utf-8")

            self._index = index
            logger.info(
                "annoy_index_built",
                path=str(self._index_path),
                num_vectors=len(trace_ids),
            )
            return True

        except Exception as exc:
            logger.error("annoy_index_build_failed", error=str(exc))
            return False

    def search(self, query_embedding: np.ndarray, k: int) -> list[tuple[int, float]]:
        """Search the index for k nearest neighbors.

        Returns list of (item_index, distance) pairs.
        """
        if self._index is None:
            return []
        index: Any = self._index
        result: list[list[int] | list[float]] = index.get_nns_by_vector(
            query_embedding.tolist(), k, include_distances=True
        )
        # result[0] is list[int], result[1] is list[float]
        indices: list[int] = cast("list[int]", result[0])
        distances: list[float] = cast("list[float]", result[1])
        return list(zip(indices, distances, strict=True))

    def get_trace_id_at(self, index: int) -> str | None:
        """Look up trace_id by Annoy index (from metadata)."""
        try:
            meta = json.loads(self._meta_path.read_text(encoding="utf-8"))
            trace_ids: list[str] = meta["trace_ids"]
            return trace_ids[index]
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Vector search
# ---------------------------------------------------------------------------


def vector_search(
    parquet_paths: list[Path],
    query_embedding: np.ndarray,
    *,
    max_results: int = 100,
    use_annoy: bool = True,
    index_dir: Path | None = None,
    dimensions: int = 384,
) -> list[_VectorMatch]:
    """Search turns by cosine similarity to query embedding.

    Uses Annoy for approximate nearest neighbor search when available and
    up-to-date; falls back to brute-force on disk embeddings.

    Args:
        parquet_paths: Parquet files to search.
        query_embedding: Query vector (1D numpy array, float32).
        max_results: Maximum number of results to return.
        use_annoy: If True, attempt Annoy search; if False or Annoy fails, brute-force.
        index_dir: Directory for persisted Annoy index. None = no persistence.
        dimensions: Embedding dimension (used when building new index).

    Returns:
        List of _VectorMatch, ordered by descending cosine similarity.
    """
    # Collect all trace_ids and embeddings from parquet
    trace_ids: list[str] = []
    embeddings: list[np.ndarray] = []

    for path in parquet_paths:
        try:
            rows = read_turns(path)
        except Exception as exc:
            logger.warning("vector_search_read_error", path=str(path), error=str(exc))
            continue

        for row in rows:
            emb = row.get("query_embedding")
            if emb is None:
                continue
            # query_embedding stored as a list of floats
            vec = np.array(emb, dtype=np.float32)
            trace_ids.append(str(row["trace_id"]))
            embeddings.append(vec)

    if not embeddings:
        return []

    embeddings_array = np.stack(embeddings, axis=0)  # shape: (N, D)

    # --- Annoy path ---
    if use_annoy and index_dir is not None:
        index = _AnnoyIndex(index_dir, dimensions=dimensions)

        if index.is_stale(parquet_paths):
            built = index.build(parquet_paths, trace_ids, embeddings_array)
            if not built:
                use_annoy = False
        else:
            loaded = index.load()
            if not loaded:
                use_annoy = False

        if use_annoy and index._index is not None:
            # Annoy search
            try:
                results = index.search(query_embedding, k=max_results)
                matches: list[_VectorMatch] = []
                for ann_idx, dist in results:
                    tid = index.get_trace_id_at(int(ann_idx))
                    if tid is None:
                        continue
                    # Annoy cosine distance is (1 - cosine_similarity)
                    score = 1.0 - dist
                    matches.append(_VectorMatch(trace_id=tid, score=score))

                matches.sort(key=lambda m: (-m.score, m.trace_id))
                return matches[:max_results]
            except Exception as exc:
                logger.warning("annoy_search_failed_fallback", error=str(exc))
                use_annoy = False

    # --- Brute-force fallback ---
    scores: list[tuple[int, float]] = []
    for i, emb in enumerate(embeddings):
        score = cosine_similarity(query_embedding, emb)
        scores.append((i, score))

    # Sort descending by cosine similarity
    scores.sort(key=lambda x: -x[1])
    top_k = scores[:max_results]

    return [
        _VectorMatch(trace_id=trace_ids[i], score=sim)
        for i, sim in top_k
    ]
