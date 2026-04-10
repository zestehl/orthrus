"""Tests for orthrus.search._vector — cosine similarity and Annoy search."""

from __future__ import annotations

import numpy as np
import pytest

from orthrus.search._vector import (
    _AnnoyIndex,
    cosine_similarity,
    vector_search,
)

# Annoy is optional — skip tests if not available
annoy = pytest.importorskip("annoy", reason="annoy not installed")


class TestCosineSimilarity:
    """cosine_similarity() function tests."""

    def test_identical_vectors(self):
        """Identical vectors return 1.0."""
        a = np.array([1.0, 0.0, 0.0])
        b = np.array([1.0, 0.0, 0.0])
        assert cosine_similarity(a, b) == pytest.approx(1.0)

    def test_opposite_vectors(self):
        """Opposite vectors return -1.0."""
        a = np.array([1.0, 0.0, 0.0])
        b = np.array([-1.0, 0.0, 0.0])
        assert cosine_similarity(a, b) == pytest.approx(-1.0)

    def test_orthogonal_vectors(self):
        """Orthogonal vectors return 0.0."""
        a = np.array([1.0, 0.0, 0.0])
        b = np.array([0.0, 1.0, 0.0])
        assert cosine_similarity(a, b) == pytest.approx(0.0)

    def test_partial_similarity(self):
        """Partially similar vectors return intermediate value."""
        a = np.array([1.0, 1.0, 0.0])
        b = np.array([1.0, 0.0, 0.0])
        # cos(theta) = dot / (||a|| * ||b||) = 1 / (sqrt(2) * 1) ≈ 0.707
        assert cosine_similarity(a, b) == pytest.approx(0.707, abs=0.01)

    def test_zero_vector_a(self):
        """Zero vector a returns 0.0."""
        a = np.array([0.0, 0.0, 0.0])
        b = np.array([1.0, 0.0, 0.0])
        assert cosine_similarity(a, b) == 0.0

    def test_zero_vector_b(self):
        """Zero vector b returns 0.0."""
        a = np.array([1.0, 0.0, 0.0])
        b = np.array([0.0, 0.0, 0.0])
        assert cosine_similarity(a, b) == 0.0

    def test_high_dimensions(self):
        """Works with high-dimensional vectors."""
        a = np.random.randn(384).astype(np.float32)
        b = np.random.randn(384).astype(np.float32)
        result = cosine_similarity(a, b)
        assert -1.0 <= result <= 1.0

    def test_returns_float(self):
        """Returns a Python float, not numpy scalar."""
        a = np.array([1.0, 0.0])
        b = np.array([1.0, 0.0])
        result = cosine_similarity(a, b)
        assert isinstance(result, float)


class TestAnnoyIndex:
    """_AnnoyIndex class tests."""

    def test_is_stale_missing_index(self, tmp_path):
        """Missing index is stale."""
        index = _AnnoyIndex(tmp_path, dimensions=384)
        assert index.is_stale([]) is True

    def test_is_stale_missing_meta(self, tmp_path):
        """Index without meta is stale."""
        index_dir = tmp_path / "index"
        index_dir.mkdir()
        (index_dir / "search.ann").write_bytes(b"fake index")
        index = _AnnoyIndex(index_dir, dimensions=384)
        assert index.is_stale([]) is True

    def test_build_and_load(self, tmp_path):
        """Can build and load an Annoy index."""
        index_dir = tmp_path / "index"
        index_dir.mkdir()

        trace_ids = ["t1", "t2", "t3"]
        embeddings = np.array([
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ], dtype=np.float32)

        index = _AnnoyIndex(index_dir, dimensions=3)
        success = index.build([tmp_path / "fake.parquet"], trace_ids, embeddings)
        assert success is True
        assert index.is_stale([tmp_path / "fake.parquet"]) is False

        # Load into new instance
        index2 = _AnnoyIndex(index_dir, dimensions=3)
        assert index2.load() is True

    def test_search(self, tmp_path):
        """Search returns nearest neighbors."""
        index_dir = tmp_path / "index"
        index_dir.mkdir()

        trace_ids = ["t1", "t2", "t3"]
        embeddings = np.array([
            [1.0, 0.0, 0.0],  # t1
            [0.0, 1.0, 0.0],  # t2
            [0.0, 0.0, 1.0],  # t3
        ], dtype=np.float32)

        index = _AnnoyIndex(index_dir, dimensions=3)
        index.build([tmp_path / "fake.parquet"], trace_ids, embeddings)

        # Query with t1 vector — should find t1 first
        query = np.array([0.9, 0.1, 0.0], dtype=np.float32)
        results = index.search(query, k=3)

        assert len(results) == 3
        # First result should be t1 (index 0)
        assert results[0][0] == 0

    def test_get_trace_id_at(self, tmp_path):
        """Can look up trace_id by Annoy index."""
        index_dir = tmp_path / "index"
        index_dir.mkdir()

        trace_ids = ["t1", "t2", "t3"]
        embeddings = np.eye(3, dtype=np.float32)

        index = _AnnoyIndex(index_dir, dimensions=3)
        index.build([tmp_path / "fake.parquet"], trace_ids, embeddings)

        assert index.get_trace_id_at(0) == "t1"
        assert index.get_trace_id_at(1) == "t2"
        assert index.get_trace_id_at(2) == "t3"

    def test_get_trace_id_at_invalid(self, tmp_path):
        """Invalid index returns None."""
        index_dir = tmp_path / "index"
        index_dir.mkdir()

        embeddings = np.eye(3, dtype=np.float32)
        index = _AnnoyIndex(index_dir, dimensions=3)
        index.build([tmp_path / "fake.parquet"], ["t1", "t2", "t3"], embeddings)

        assert index.get_trace_id_at(99) is None


class TestVectorSearch:
    """vector_search() function tests."""

    def test_empty_parquet_list(self):
        """Empty parquet list returns empty."""
        results = vector_search([], np.array([0.1] * 384, dtype=np.float32))
        assert results == []

    def test_max_results(self, parquet_paths):
        """Respects max_results limit."""
        query = np.array([0.15] * 384, dtype=np.float32)
        results = vector_search(parquet_paths, query, max_results=2, use_annoy=False)
        assert len(results) <= 2

    def test_scores_descending(self, parquet_paths):
        """Results are sorted by descending cosine similarity."""
        query = np.array([0.2] * 384, dtype=np.float32)
        results = vector_search(parquet_paths, query, use_annoy=False)
        scores = [m.score for m in results]
        assert scores == sorted(scores, reverse=True)

    def test_brute_force_vs_annoy(self, parquet_paths):
        """Annoy and brute-force return similar results."""
        query = np.array([0.2] * 384, dtype=np.float32)

        brute_results = vector_search(parquet_paths, query, use_annoy=False)
        annoy_results = vector_search(parquet_paths, query, use_annoy=True, index_dir=None)

        # Should return same number of results
        assert len(brute_results) == len(annoy_results)

    def test_annoy_with_index_dir(self, parquet_paths, tmp_path):
        """Annoy index is built and persisted when index_dir provided."""
        index_dir = tmp_path / "annoy_index"
        query = np.array([0.2] * 384, dtype=np.float32)

        results1 = vector_search(parquet_paths, query, use_annoy=True, index_dir=index_dir)
        assert len(results1) > 0

        # Second call should use cached index
        results2 = vector_search(parquet_paths, query, use_annoy=True, index_dir=index_dir)
        assert len(results2) > 0

    def test_score_range(self, parquet_paths):
        """Scores are in [-1, 1] range (cosine similarity)."""
        query = np.array([0.1] * 384, dtype=np.float32)
        results = vector_search(parquet_paths, query, use_annoy=False)
        for r in results:
            assert -1.0 <= r.score <= 1.0

    def test_trace_id_in_results(self, parquet_paths):
        """Results contain valid trace_ids."""
        query = np.array([0.1] * 384, dtype=np.float32)
        results = vector_search(parquet_paths, query, use_annoy=False)
        for r in results:
            assert r.trace_id.startswith("018f")
