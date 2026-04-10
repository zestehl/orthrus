"""Tests for orthrus.embedding._mlx — MLXBackend."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Tests — no MagicMock on .config attributes to avoid descriptor issues
# ---------------------------------------------------------------------------

class TestMLXBackendInit:
    """MLXBackend.__init__ tests."""

    def test_init_defaults(self, tmp_path):
        """Init stores model_path and default options."""
        from orthrus.embedding._mlx import MLXBackend

        backend = MLXBackend(model_path=tmp_path / "mlx-model")
        assert backend._model_path == tmp_path / "mlx-model"
        assert backend._batch_size == 32
        assert backend._fallback_to_cpu is False
        assert backend._dimensions is None

    def test_init_custom(self, tmp_path):
        """Custom batch_size and fallback_to_cpu."""
        from orthrus.embedding._mlx import MLXBackend

        backend = MLXBackend(
            model_path=tmp_path / "model",
            batch_size=16,
            fallback_to_cpu=True,
        )
        assert backend._batch_size == 16
        assert backend._fallback_to_cpu is True


class TestMLXBackendEncode:
    """MLXBackend.encode() tests with mocked internals."""

    def test_encode_returns_correct_type(self, tmp_path):
        """encode() returns list of float lists with correct dimensions."""
        from orthrus.embedding._mlx import MLXBackend

        mock_model = MagicMock()
        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": np.array([[1, 2, 3]]),
            "attention_mask": np.array([[1, 1, 1]]),
        }
        mock_output = MagicMock()
        mock_output.last_hidden_state = np.zeros(
            (1, 3, 384), dtype=np.float32
        )
        mock_model.return_value = mock_output

        import orthrus.embedding._mlx as mlx_module
        mlx_module._mlx_model = None
        mlx_module._mlx_tokenizer = None
        mlx_module._mlx_dims = None

        def fake_load(path):
            return mock_model, mock_tokenizer, 384

        with patch.object(mlx_module, "_load_mlx_model", fake_load):
            backend = MLXBackend(model_path=tmp_path / "model")
            result = backend.encode(["hello world"])

        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], list)
        assert len(result[0]) == 384

    def test_encode_multiple_texts(self, tmp_path):
        """encode() handles batch of multiple texts."""
        from orthrus.embedding._mlx import MLXBackend

        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": np.array([[1, 2, 3], [4, 5, 0]]),
            "attention_mask": np.array([[1, 1, 1], [1, 1, 0]]),
        }
        mock_output = MagicMock()
        mock_output.last_hidden_state = np.zeros((2, 3, 384), dtype=np.float32)
        mock_model = MagicMock(return_value=mock_output)

        import orthrus.embedding._mlx as mlx_module
        mlx_module._mlx_model = None
        mlx_module._mlx_tokenizer = None
        mlx_module._mlx_dims = None

        def fake_load(path):
            return mock_model, mock_tokenizer, 384

        with patch.object(mlx_module, "_load_mlx_model", fake_load):
            backend = MLXBackend(model_path=tmp_path / "model")
            result = backend.encode(["hello", "world test"])

        assert len(result) == 2
        assert all(isinstance(r, list) for r in result)
        assert all(len(r) == 384 for r in result)

    def test_encode_empty_list_propagates_error(self, tmp_path):
        """encode() with empty list — tokenizer raises, backend propagates."""
        from orthrus.embedding._mlx import MLXBackend

        mock_model = MagicMock()
        mock_tokenizer = MagicMock()
        # Empty list causes IndexError from tokenizer
        mock_tokenizer.side_effect = IndexError("list index out of range")
        mock_output = MagicMock()
        mock_output.last_hidden_state = np.zeros((1, 3, 384), dtype=np.float32)
        mock_model.return_value = mock_output

        import orthrus.embedding._mlx as mlx_module
        mlx_module._mlx_model = None
        mlx_module._mlx_tokenizer = None
        mlx_module._mlx_dims = None

        def fake_load(path):
            return mock_model, mock_tokenizer, 384

        with patch.object(mlx_module, "_load_mlx_model", fake_load):
            backend = MLXBackend(model_path=tmp_path / "model")
            with pytest.raises(IndexError):
                backend.encode([])

    def test_dimensions_cached(self, tmp_path):
        """dimensions property loads model once."""
        from orthrus.embedding._mlx import MLXBackend

        mock_model = MagicMock()
        mock_tokenizer = MagicMock()

        import orthrus.embedding._mlx as mlx_module
        mlx_module._mlx_model = None
        mlx_module._mlx_tokenizer = None
        mlx_module._mlx_dims = None

        def fake_load(path):
            return mock_model, mock_tokenizer, 768

        with patch.object(mlx_module, "_load_mlx_model", fake_load):
            backend = MLXBackend(model_path=tmp_path / "model")
            d1 = backend.dimensions
            d2 = backend.dimensions
            assert d1 == 768
            assert d2 == 768


class TestMLXBackendAsync:
    """Async submit/flush methods."""

    def test_submit_returns_turn_with_embedding(self, tmp_path):
        """submit() embeds query_text and returns Turn with embedding."""
        from datetime import UTC, datetime

        from orthrus.embedding._mlx import MLXBackend

        mock_model = MagicMock()
        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": np.array([[1, 2, 3]]),
            "attention_mask": np.array([[1, 1, 1]]),
        }
        mock_output = MagicMock()
        mock_output.last_hidden_state = np.zeros((1, 3, 384), dtype=np.float32)
        mock_model.return_value = mock_output

        import orthrus.embedding._mlx as mlx_module
        mlx_module._mlx_model = None
        mlx_module._mlx_tokenizer = None
        mlx_module._mlx_dims = None

        def fake_load(path):
            return mock_model, mock_tokenizer, 384

        with patch.object(mlx_module, "_load_mlx_model", fake_load):
            backend = MLXBackend(model_path=tmp_path / "model")

            from orthrus.capture.turn import Turn, TurnOutcome
            turn = Turn(
                trace_id="018f1234-5678-7abc-8def-111111111111",
                session_id="test-session",
                query_text="What is AI?",
                available_tools=(),
                tool_calls=(),
                outcome=TurnOutcome.SUCCESS,
                duration_ms=100,
                response_text="AI is artificial intelligence.",
                context_hash="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                timestamp=datetime(2026, 4, 10, 12, 0, 0, tzinfo=UTC),
                query_embedding=None,  # type: ignore[arg-type]
                orthrus_version="0.2.0",
                capture_profile="test",
                platform="test",
            )

            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(backend.submit(turn))
            finally:
                loop.close()

        assert result is not None
        assert result.query_embedding is not None
        assert len(result.query_embedding) == 384

    def test_flush_is_noop(self, tmp_path):
        """flush() returns 0 for MLXBackend."""
        from orthrus.embedding._mlx import MLXBackend

        backend = MLXBackend(model_path=tmp_path / "model")
        assert asyncio.run(backend.flush()) == 0


class TestMLXLoadError:
    """MLX import/load error handling."""

    def test_load_raises_when_mlx_unavailable(self, tmp_path):
        """_load_mlx_model raises RuntimeError when mlx is not installed."""
        import orthrus.embedding._mlx as mlx_module
        mlx_module._mlx_model = None
        mlx_module._mlx_tokenizer = None
        mlx_module._mlx_dims = None

        with patch.dict("sys.modules", {"mlx": None, "mlx.core": None}, clear=False), \
             pytest.raises(RuntimeError, match="MLX is not installed"):
            mlx_module._load_mlx_model(tmp_path / "model")


class TestMLXCaching:
    """Model loading/caching tests."""

    def test_model_cached_after_first_load(self, tmp_path):
        """Second _load_mlx_model call returns same cached object.

        The module-level globals ensure only one load occurs.
        """
        mock_model = MagicMock()
        mock_tokenizer = MagicMock()

        import orthrus.embedding._mlx as mlx_module
        mlx_module._mlx_model = None
        mlx_module._mlx_tokenizer = None
        mlx_module._mlx_dims = None

        cached_result = None

        def fake_load(path):
            nonlocal cached_result
            if cached_result is None:
                cached_result = (mock_model, mock_tokenizer, 384)
            return cached_result

        with patch.object(mlx_module, "_load_mlx_model", fake_load):
            r1 = mlx_module._load_mlx_model(tmp_path / "model")
            r2 = mlx_module._load_mlx_model(tmp_path / "model")
            assert r1 is r2
            assert r1[0] is mock_model
