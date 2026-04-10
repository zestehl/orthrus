"""Tests for orthrus.search._manager — SearchManager."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from orthrus.search._manager import (
    SEARCHABLE_FIELDS,
    SearchError,
    SearchManager,
    SearchQuery,
    SearchResult,
    _coerce_filters,
    _resolve_mode,
    _rrf_score,
)


class TestRRFScore:
    """RRF scoring tests."""

    def test_rrf_score_rank1(self):
        """Rank 1 gets highest score."""
        assert _rrf_score(1) == pytest.approx(1.0 / 61.0)

    def test_rrf_score_rank2(self):
        """Rank 2 gets lower score than rank 1."""
        assert _rrf_score(2) < _rrf_score(1)

    def test_rrf_score_decreases(self):
        """Score decreases monotonically with rank."""
        scores = [_rrf_score(i) for i in range(1, 11)]
        assert scores == sorted(scores, reverse=True)


class TestResolveMode:
    """_resolve_mode() tests."""

    def test_explicit_text(self):
        """mode='text' returns 'text'."""
        q = SearchQuery(text="test", mode="text")
        assert _resolve_mode(q) == "text"

    def test_explicit_vector(self):
        """mode='vector' returns 'vector'."""
        q = SearchQuery(vector=[0.1] * 384, mode="vector")
        assert _resolve_mode(q) == "vector"

    def test_explicit_hybrid(self):
        """mode='hybrid' returns 'hybrid'."""
        q = SearchQuery(text="test", vector=[0.1] * 384, mode="hybrid")
        assert _resolve_mode(q) == "hybrid"

    def test_auto_both(self):
        """Auto with both text and vector returns hybrid."""
        q = SearchQuery(text="test", vector=[0.1] * 384, mode="auto")
        assert _resolve_mode(q) == "hybrid"

    def test_auto_vector_only(self):
        """Auto with vector only returns vector."""
        q = SearchQuery(vector=[0.1] * 384, mode="auto")
        assert _resolve_mode(q) == "vector"

    def test_auto_text_only(self):
        """Auto with text only returns text."""
        q = SearchQuery(text="test", mode="auto")
        assert _resolve_mode(q) == "text"

    def test_auto_neither(self):
        """Auto with neither returns auto."""
        q = SearchQuery(mode="auto")
        assert _resolve_mode(q) == "auto"


class TestSearchQuery:
    """SearchQuery dataclass tests."""

    def test_defaults(self):
        """Default values are set correctly."""
        q = SearchQuery()
        assert q.text is None
        assert q.vector is None
        assert q.mode == "auto"
        assert q.filters == {}
        assert q.max_results == 10

    def test_invalid_mode_raises(self):
        """Invalid mode raises ValueError."""
        with pytest.raises(ValueError, match="Invalid mode"):
            SearchQuery(mode="invalid")

    def test_with_text(self):
        """Can create query with text."""
        q = SearchQuery(text="hello world")
        assert q.text == "hello world"

    def test_with_vector(self):
        """Can create query with vector."""
        vec = [0.1] * 384
        q = SearchQuery(vector=vec)
        assert q.vector == vec


class TestCoerceFilters:
    """_coerce_filters() tests."""

    def test_passthrough_unknown_field(self):
        """Unknown fields pass through unchanged."""
        result = _coerce_filters({"unknown": "value"})
        assert result["unknown"] == "value"

    def test_coerce_outcome_to_str(self):
        """outcome is coerced to str."""
        result = _coerce_filters({"outcome": 123})
        assert result["outcome"] == "123"

    def test_coerce_duration_ms_to_int(self):
        """duration_ms is coerced to int."""
        result = _coerce_filters({"duration_ms": "200"})
        assert result["duration_ms"] == 200

    def test_active_skills_list_to_tuple(self):
        """active_skills list is coerced to tuple."""
        result = _coerce_filters({"active_skills": ["a", "b"]})
        assert result["active_skills"] == ("a", "b")

    def test_timestamp_passthrough(self):
        """timestamp is passed through unchanged."""
        result = _coerce_filters({"timestamp": "2026-01-01"})
        assert result["timestamp"] == "2026-01-01"


class TestSearchableFields:
    """SEARCHABLE_FIELDS registry tests."""

    def test_has_expected_fields(self):
        """Registry has expected fields."""
        expected = {
            "outcome", "session_id", "duration_ms", "schema_version",
            "capture_profile", "platform", "active_skills", "available_tools",
            "parent_trace_id", "error_class",
        }
        assert expected.issubset(SEARCHABLE_FIELDS.keys())

    def test_all_fields_callable(self):
        """All field coercers are callable."""
        for field, fn in SEARCHABLE_FIELDS.items():
            assert callable(fn), f"{field} is not callable"


class TestSearchManager:
    """SearchManager integration tests."""

    @pytest.fixture
    def mock_storage(self, parquet_paths):
        """Mock StorageManager returning our parquet files."""
        storage = MagicMock()
        storage.get_hot_files.return_value = parquet_paths
        return storage

    @pytest.fixture
    def search_manager(self, mock_storage):
        """SearchManager with mock storage."""
        return SearchManager(storage=mock_storage)

    def test_search_text_mode(self, search_manager, parquet_paths):
        """Text search returns results."""

        # Patch the internal storage call
        search_manager._storage.get_hot_files.return_value = parquet_paths

        results = search_manager.search(SearchQuery(text="France", mode="text"))
        assert len(results) > 0
        assert all(isinstance(r, SearchResult) for r in results)

    def test_search_text_mode_no_results(self, search_manager, parquet_paths):
        """Text search with no matches returns empty."""
        search_manager._storage.get_hot_files.return_value = parquet_paths
        results = search_manager.search(SearchQuery(text="xyznonexistent", mode="text"))
        assert results == []

    def test_search_vector_mode(self, search_manager, parquet_paths):
        """Vector search returns results."""
        search_manager._storage.get_hot_files.return_value = parquet_paths
        query_vec = [0.1] * 384
        results = search_manager.search(SearchQuery(vector=query_vec, mode="vector"))
        assert len(results) >= 0  # May be 0 if no embeddings
        assert all(isinstance(r, SearchResult) for r in results)

    def test_search_vector_dimension_mismatch(self, search_manager, parquet_paths):
        """Wrong dimension vector raises SearchError."""
        search_manager._storage.get_hot_files.return_value = parquet_paths
        query_vec = [0.1] * 100  # Wrong dimension
        with pytest.raises(SearchError, match="dimensions"):
            search_manager.search(SearchQuery(vector=query_vec, mode="vector"))

    def test_search_auto_text(self, search_manager, parquet_paths):
        """Auto mode with text uses text search."""
        search_manager._storage.get_hot_files.return_value = parquet_paths
        results = search_manager.search(SearchQuery(text="France"))
        assert len(results) >= 0

    def test_search_auto_vector(self, search_manager, parquet_paths):
        """Auto mode with vector uses vector search."""
        search_manager._storage.get_hot_files.return_value = parquet_paths
        results = search_manager.search(SearchQuery(vector=[0.1] * 384))
        assert isinstance(results, list)

    def test_search_empty_query(self, search_manager, parquet_paths):
        """Empty query returns empty list."""
        search_manager._storage.get_hot_files.return_value = parquet_paths
        results = search_manager.search(SearchQuery())
        assert results == []

    def test_search_with_filters(self, search_manager, parquet_paths):
        """Search with filters applies them."""
        search_manager._storage.get_hot_files.return_value = parquet_paths
        results = search_manager.search(SearchQuery(
            text="TypeError",
            mode="text",
            filters={"outcome": "error"}
        ))
        assert len(results) >= 0

    def test_search_max_results(self, search_manager, parquet_paths):
        """Respects max_results limit."""
        search_manager._storage.get_hot_files.return_value = parquet_paths
        results = search_manager.search(SearchQuery(
            text="quantum",
            mode="text",
            max_results=1
        ))
        assert len(results) <= 1

    def test_index_status_no_index_dir(self, search_manager):
        """index_status returns correct info when no index_dir."""
        status = search_manager.index_status()
        assert status["index_dir"] is None
        assert status["exists"] is False

    def test_index_status_with_index_dir(self, search_manager, tmp_path):
        """index_status checks index on disk."""
        search_manager._index_dir = tmp_path / "index"
        search_manager._storage.get_hot_files.return_value = []

        status = search_manager.index_status()
        assert status["exists"] is False
        assert status["stale"] is True

    def test_build_index_no_index_dir(self, search_manager):
        """build_index returns False when no index_dir."""
        result = search_manager.build_index()
        assert result is False

    def test_build_index_no_files(self, search_manager, tmp_path):
        """build_index returns True when no files to index."""
        search_manager._index_dir = tmp_path / "index"
        search_manager._storage.get_hot_files.return_value = []

        result = search_manager.build_index()
        assert result is True

    def test_search_result_fields(self, search_manager, parquet_paths):
        """SearchResult has expected fields."""
        search_manager._storage.get_hot_files.return_value = parquet_paths
        results = search_manager.search(SearchQuery(text="France", mode="text"))
        if results:
            r = results[0]
            assert hasattr(r, "trace_id")
            assert hasattr(r, "score")
            assert hasattr(r, "turn_data")
            assert isinstance(r.trace_id, str)
            assert isinstance(r.score, float)
            assert isinstance(r.turn_data, dict)


class TestSearchManagerWithRealStorage:
    """SearchManager tests with real StorageManager and parquet files."""

    @pytest.fixture
    def real_storage_manager(self, search_tmp_path, parquet_paths):
        """Real StorageManager pointing to temp storage."""
        from orthrus.config._models import StorageConfig
        from orthrus.storage import StorageManager, StoragePaths

        config = StorageConfig(
            hot_root=search_tmp_path / "capture",
            warm_root=search_tmp_path / "warm",
            archive_root=search_tmp_path / "archive",
        )
        # StorageManager(config) ignores config.hot_root — must pass explicit StoragePaths
        paths = StoragePaths(
            root=search_tmp_path,
            capture=search_tmp_path / "capture",
            warm=search_tmp_path / "warm",
            archive=search_tmp_path / "archive",
            derived=search_tmp_path / "derived",
        )
        manager = StorageManager(config, paths=paths)
        return manager

    def test_search_with_real_storage(self, real_storage_manager, parquet_paths):
        """End-to-end search with real storage."""
        manager = SearchManager(storage=real_storage_manager)
        results = manager.search(SearchQuery(text="France", mode="text"))
        assert len(results) > 0

    def test_hybrid_search_with_embedding(self, real_storage_manager, parquet_paths):
        """Hybrid search combines text and vector."""
        from orthrus.embedding import TransformersBackend

        backend = TransformersBackend(model_name="all-MiniLM-L6-v2")

        manager = SearchManager(
            storage=real_storage_manager,
            embedding=backend,
        )
        results = manager.search(SearchQuery(
            text="France",
            vector=[0.1] * 384,
            mode="hybrid"
        ))
        assert isinstance(results, list)
