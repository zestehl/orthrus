"""Tests for orthrus.embedding._onnx — OnnxBackend."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from orthrus.embedding._onnx import OnnxBackend, _mean_pool


class TestOnnxBackend:
    """OnnxBackend unit tests (mocked)."""

    def test_init_defaults(self):
        """Default model is all-MiniLM-L6-v2 with CPU provider."""
        backend = OnnxBackend()
        assert backend._model_name == "sentence-transformers/all-MiniLM-L6-v2"
        assert backend._model_path is None
        assert backend._provider == "CPUExecutionProvider"
        assert backend._quantize is False
        assert backend._dimensions is None

    def test_init_custom(self, tmp_path):
        """Can pass custom model name, path, provider."""
        backend = OnnxBackend(
            model_name="my-model",
            model_path=tmp_path / "model",
            provider="CoreMLExecutionProvider",
            quantize=True,
        )
        assert backend._model_name == "my-model"
        assert backend._model_path == tmp_path / "model"
        assert backend._provider == "CoreMLExecutionProvider"
        assert backend._quantize is True

    def test_encode_mock(self, tmp_path):
        """encode() returns correct shape and type."""
        model = MagicMock()
        tokenizer = MagicMock()
        tokenizer.padding_side = "right"
        mock_inputs = {
            "input_ids": np.array([[1, 2, 3]]),
            "attention_mask": np.array([[1, 1, 1]]),
        }
        tokenizer.return_value = mock_inputs

        mock_output = MagicMock()
        mock_output.last_hidden_state = np.random.randn(1, 3, 384).astype(np.float32)
        model.return_value = mock_output

        import orthrus.embedding._onnx as onnx_module
        onnx_module._ort_model = None
        onnx_module._tokenizer = None

        def fake_load(name, path, provider):
            return model, tokenizer

        with patch.object(onnx_module, "_load_onnx_model", fake_load):
            backend = OnnxBackend()
            result = backend.encode(["hello world"])

        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], list)
        assert len(result[0]) == 384

    def test_encode_multiple_texts(self, tmp_path):
        """encode() handles batch of multiple texts."""
        model = MagicMock()
        tokenizer = MagicMock()
        tokenizer.padding_side = "right"
        mock_inputs = {
            "input_ids": np.array([[1, 2, 3], [4, 5, 0]]),
            "attention_mask": np.array([[1, 1, 1], [1, 1, 0]]),
        }
        tokenizer.return_value = mock_inputs

        mock_output = MagicMock()
        mock_output.last_hidden_state = np.random.randn(2, 3, 384).astype(np.float32)
        model.return_value = mock_output

        import orthrus.embedding._onnx as onnx_module
        onnx_module._ort_model = None
        onnx_module._tokenizer = None

        def fake_load(name, path, provider):
            return model, tokenizer

        with patch.object(onnx_module, "_load_onnx_model", fake_load):
            backend = OnnxBackend()
            result = backend.encode(["hello", "world test"])

        assert len(result) == 2
        assert all(isinstance(r, list) for r in result)
        assert all(len(r) == 384 for r in result)

    def test_encode_empty_list_propagates_error(self, tmp_path):
        """encode() with empty list — tokenizer raises IndexError, backend propagates."""
        model = MagicMock()
        tokenizer = MagicMock()
        # Real tokenizer raises IndexError on empty batch
        tokenizer.side_effect = IndexError("list index out of range")

        import orthrus.embedding._onnx as onnx_module
        onnx_module._ort_model = None
        onnx_module._tokenizer = None

        def fake_load(name, path, provider):
            return model, tokenizer

        with patch.object(onnx_module, "_load_onnx_model", fake_load):
            backend = OnnxBackend()
            with pytest.raises(IndexError):
                backend.encode([])

    def test_dimensions_triggers_load(self, tmp_path):
        """dimensions property loads model once and caches."""
        model = MagicMock()
        tokenizer = MagicMock()
        model.config.hidden_size = 384

        import orthrus.embedding._onnx as onnx_module
        onnx_module._ort_model = None
        onnx_module._tokenizer = None

        def fake_load(name, path, provider):
            return model, tokenizer

        with patch.object(onnx_module, "_load_onnx_model", fake_load):
            backend = OnnxBackend()
            d1 = backend.dimensions
            d2 = backend.dimensions

        assert d1 == 384
        assert d2 == 384


class TestMeanPool:
    """_mean_pool() utility tests."""

    def test_no_mask(self):
        """No attention mask — simple mean over sequence."""
        hidden = np.array([[[1.0, 0.0], [3.0, 0.0], [5.0, 0.0]]], dtype=np.float32)
        result = _mean_pool(hidden, None)
        # result is [[[3.0, 0.0]]] — list of batch results; result[0][0] is the embedding
        assert len(result) == 1
        assert len(result[0]) == 1
        np.testing.assert_allclose(result[0][0], [3.0, 0.0], rtol=1e-5)

    def test_with_attention_mask(self):
        """Attention mask zeroes out padding tokens."""
        hidden = np.array([[[1.0, 0.0], [3.0, 0.0], [0.0, 0.0]]], dtype=np.float32)
        mask = np.array([[1, 1, 0]])
        result = _mean_pool(hidden, mask)
        # Only first 2 tokens: (1+3)/2 = 2.0; result is [[2.0, 0.0]]
        assert len(result) == 1
        np.testing.assert_allclose(result[0], [2.0, 0.0], rtol=1e-5)

    def test_all_padding_masked(self):
        """All padding tokens — divisor clipped to 1e-9."""
        hidden = np.array([[[1.0, 0.0], [0.0, 0.0], [0.0, 0.0]]], dtype=np.float32)
        mask = np.array([[0, 0, 0]])
        result = _mean_pool(hidden, mask)
        assert len(result) == 1
        np.testing.assert_allclose(result[0][0], [0.0, 0.0], atol=1e-6)


class TestOnnxBackendAsync:
    """Async submit/flush methods on OnnxBackend."""

    def test_submit_returns_turn_with_embedding(self, tmp_path):
        """submit() embeds query_text and returns Turn with embedding."""
        from datetime import UTC, datetime

        from orthrus.embedding._onnx import OnnxBackend

        model = MagicMock()
        tokenizer = MagicMock()
        tokenizer.padding_side = "right"
        mock_inputs = {
            "input_ids": np.array([[1, 2, 3]]),
            "attention_mask": np.array([[1, 1, 1]]),
        }
        tokenizer.return_value = mock_inputs

        mock_output = MagicMock()
        mock_output.last_hidden_state = np.zeros((1, 3, 384), dtype=np.float32)
        model.return_value = mock_output

        import orthrus.embedding._onnx as onnx_module
        onnx_module._ort_model = None
        onnx_module._tokenizer = None

        def fake_load(name, path, provider):
            return model, tokenizer

        with patch.object(onnx_module, "_load_onnx_model", fake_load):
            backend = OnnxBackend()

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
        """flush() returns 0 for OnnxBackend."""
        backend = OnnxBackend()
        assert asyncio.run(backend.flush()) == 0
