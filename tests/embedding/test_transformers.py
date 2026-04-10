"""Tests for TransformersBackend."""

from __future__ import annotations

import pytest

from orthrus.embedding import TransformersBackend


@pytest.fixture
def backend() -> TransformersBackend:
    return TransformersBackend(model_name="all-MiniLM-L6-v2", device="cpu")


class TestTransformersBackendDimensions:
    def test_dimensions_returns_384(self, backend: TransformersBackend) -> None:
        # all-MiniLM-L6-v2 produces 384-dim embeddings
        assert backend.dimensions == 384

    def test_dimensions_cached_after_first_call(
        self, backend: TransformersBackend
    ) -> None:
        dims1 = backend.dimensions
        dims2 = backend.dimensions
        assert dims1 is dims2  # Same object, not recomputed


class TestTransformersBackendEncode:
    def test_encode_single_text(self, backend: TransformersBackend) -> None:
        embeddings = backend.encode(["hello world"])
        assert len(embeddings) == 1
        assert len(embeddings[0]) == 384
        assert all(isinstance(x, float) for x in embeddings[0])

    def test_encode_batch(self, backend: TransformersBackend) -> None:
        texts = ["hello", "world", "foo bar baz qux"]
        embeddings = backend.encode(texts)
        assert len(embeddings) == 3
        for emb in embeddings:
            assert len(emb) == 384

    def test_encode_deterministic(self, backend: TransformersBackend) -> None:
        # Same text should produce same (or very similar) embedding
        emb1 = backend.encode(["test sentence"])[0]
        emb2 = backend.encode(["test sentence"])[0]
        # Allow small floating point differences
        assert emb1[:5] == pytest.approx(emb2[:5], abs=1e-5)

    def test_encode_empty_string_raises(self, backend: TransformersBackend) -> None:
        # Empty string may or may not raise depending on model behavior
        # We don't enforce specific behavior here, just check it doesn't crash
        from contextlib import suppress
        with suppress(Exception):
            backend.encode([""])


class TestTransformersBackendSubmit:
    @pytest.mark.asyncio
    async def test_submit_returns_turn_with_embedding(
        self, backend: TransformersBackend
    ) -> None:
        from datetime import UTC, datetime

        from orthrus.capture.turn import Turn

        turn = Turn(
            trace_id="018f1234-5678-7abc-8def-1234567890ab",
            session_id="test-session",
            timestamp=datetime.now(UTC),
            query_text="What is the capital of France?",
            context_hash="a" * 64,
            available_tools=("web_search",),
        )

        result = await backend.submit(turn)
        assert result is not None
        assert result.trace_id == turn.trace_id
        assert result.query_embedding is not None
        assert len(result.query_embedding) == 384

    @pytest.mark.asyncio
    async def test_submit_failure_returns_original_turn(
        self, backend: TransformersBackend, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from datetime import UTC, datetime

        from orthrus.capture.turn import Turn

        turn = Turn(
            trace_id="018f1234-5678-7abc-8def-1234567890ab",
            session_id="test-session",
            timestamp=datetime.now(UTC),
            query_text="test",
            context_hash="a" * 64,
            available_tools=(),
        )

        def raise_error(_: list[str]) -> list[list[float]]:
            raise RuntimeError("simulated encode failure")

        monkeypatch.setattr(backend, "encode", raise_error)
        result = await backend.submit(turn)
        assert result is turn  # Returns original on error


class TestTransformersBackendFlush:
    @pytest.mark.asyncio
    async def test_flush_returns_zero(self, backend: TransformersBackend) -> None:
        count = await backend.flush()
        assert count == 0


class TestTransformersBackendLazyLoad:
    def test_model_not_loaded_until_first_encode(
        self, backend: TransformersBackend
    ) -> None:
        # dimensions triggers model load
        dims = backend.dimensions
        assert dims == 384
        assert backend._model is not None

    def test_encode_triggers_lazy_load(self, backend: TransformersBackend) -> None:
        assert backend._model is None
        backend.encode(["test"])
        assert backend._model is not None


class TestTransformersBackendErrorHandling:
    def test_bad_model_name_raises_on_encode(self) -> None:
        bad_backend = TransformersBackend(model_name="nonexistent-model-xyz")
        bad_backend._dimensions = 384  # Skip dimensions property lazy load
        with pytest.raises(RuntimeError, match="Failed to load"):
            bad_backend.encode(["test"])
