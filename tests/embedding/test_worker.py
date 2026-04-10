"""Tests for EmbeddingWorker."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from orthrus.embedding import EmbeddingWorker


class _DummyBackend:
    """Minimal EmbeddingBackend that echoes texts as their ord sums."""

    def __init__(self, dimensions: int = 384) -> None:
        self._dimensions = dimensions
        self.encode_calls: list[list[str]] = []

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def encode(self, texts: list[str]) -> list[list[float]]:
        self.encode_calls.append(texts)
        # Echo a simple fixed-dimension vector (not meaningful, just deterministic)
        return [[float(len(t))] + [0.0] * (self._dimensions - 1) for t in texts]

    async def submit(self, turn: Any) -> Any:
        return turn

    async def flush(self) -> int:
        return 0


@pytest.fixture
def dummy_backend() -> _DummyBackend:
    return _DummyBackend(dimensions=384)


@pytest.fixture
def worker(dummy_backend: _DummyBackend) -> EmbeddingWorker:
    return EmbeddingWorker(dummy_backend, batch_size=4, batch_timeout=0.05)


class TestEmbeddingWorkerDimensions:
    def test_dimensions_delegated_to_backend(self, worker: EmbeddingWorker) -> None:
        assert worker.dimensions == 384


class TestEmbeddingWorkerSubmit:
    @pytest.mark.asyncio
    async def test_submit_returns_future(self, worker: EmbeddingWorker) -> None:
        fut = worker.submit("hello world")
        assert isinstance(fut, asyncio.Future)
        result = await fut
        assert isinstance(result, list)
        assert len(result) == 384
        assert result[0] == pytest.approx(11.0)  # len("hello world")

    @pytest.mark.asyncio
    async def test_submit_multiple_texts_batched(self, worker: EmbeddingWorker) -> None:
        # Submit 3 texts (less than batch_size=4) — should be resolved on timeout
        futures = [worker.submit(f"text{i}") for i in range(3)]
        results = await asyncio.gather(*futures)

        # All three should resolve
        assert len(results) == 3
        for r in results:
            assert isinstance(r, list)
            assert len(r) == 384

    @pytest.mark.asyncio
    async def test_submit_exceeding_batch_size_triggers_immediate_run(
        self, worker: EmbeddingWorker
    ) -> None:
        # batch_size=4, submit 5 — first 4 should run, last 1 waits
        futures = [worker.submit(f"text{i}") for i in range(5)]
        # The first 4 should resolve quickly (immediately after batch fills)
        first4 = await asyncio.gather(*futures[:4])
        assert len(first4) == 4
        # Fifth should resolve after timeout
        fifth = await futures[4]
        assert isinstance(fifth, list)

    @pytest.mark.asyncio
    async def test_shutdown_rejects_new_submissions(
        self, worker: EmbeddingWorker
    ) -> None:
        await worker.shutdown()
        with pytest.raises(RuntimeError, match="shut down"):
            worker.submit("new text")

    @pytest.mark.asyncio
    async def test_shutdown_cancels_pending_futures(
        self, worker: EmbeddingWorker
    ) -> None:
        # Submit something and cancel it via shutdown
        fut = worker.submit("cancel me")
        await worker.shutdown()
        assert fut.cancelled()

    @pytest.mark.asyncio
    async def test_flush_returns_count(self, worker: EmbeddingWorker) -> None:
        worker.submit("a")
        worker.submit("bb")
        count = await worker.flush()
        assert count == 2

    @pytest.mark.asyncio
    async def test_flush_empty_queue_returns_zero(self, worker: EmbeddingWorker) -> None:
        count = await worker.flush()
        assert count == 0


class TestEmbeddingWorkerBatching:
    @pytest.mark.asyncio
    async def test_batch_size_respected(
        self, dummy_backend: _DummyBackend, worker: EmbeddingWorker
    ) -> None:
        # Submit 4 texts (exactly batch size)
        for i in range(4):
            worker.submit(f"t{i}")

        # Wait for the batch to be processed
        await asyncio.sleep(0.2)

        # Should have exactly one encode call with all 4 texts
        assert len(dummy_backend.encode_calls) == 1
        assert dummy_backend.encode_calls[0] == ["t0", "t1", "t2", "t3"]

    @pytest.mark.asyncio
    async def test_partial_batch_runs_on_timeout(
        self, dummy_backend: _DummyBackend, worker: EmbeddingWorker
    ) -> None:
        # Submit 2 texts (less than batch size)
        worker.submit("short")
        worker.submit("longer text")

        # Should NOT run yet (partial batch)
        await asyncio.sleep(0.01)  # less than timeout
        assert len(dummy_backend.encode_calls) == 0

        # Wait for timeout to trigger
        await asyncio.sleep(0.1)  # more than timeout (0.05s)
        assert len(dummy_backend.encode_calls) == 1


class TestEmbeddingWorkerSubmitTurn:
    @pytest.mark.asyncio
    async def test_submit_turn_returns_turn_with_embedding(
        self, worker: EmbeddingWorker
    ) -> None:
        from datetime import UTC, datetime

        from orthrus.capture.turn import Turn

        turn = Turn(
            trace_id="018f1234-5678-7abc-8def-1234567890ab",
            session_id="test-session",
            timestamp=datetime.now(UTC),
            query_text="hello from turn",
            context_hash="a" * 64,
            available_tools=("tool_a",),
        )

        result = await worker.submit_turn(turn)
        assert result is not None
        assert result.trace_id == turn.trace_id
        assert result.query_embedding is not None
        assert len(result.query_embedding) == 384

    @pytest.mark.asyncio
    async def test_submit_turn_error_returns_original_turn(
        self, worker: EmbeddingWorker, dummy_backend: _DummyBackend, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from datetime import UTC, datetime

        from orthrus.capture.turn import Turn

        def raise_error(_: list[str]) -> list[list[float]]:
            raise RuntimeError("simulated encode failure")

        monkeypatch.setattr(dummy_backend, "encode", raise_error)

        turn = Turn(
            trace_id="018f1234-5678-7abc-8def-1234567890ab",
            session_id="test-session",
            timestamp=datetime.now(UTC),
            query_text="hello",
            context_hash="a" * 64,
            available_tools=(),
        )

        result = await worker.submit_turn(turn)
        assert result is turn  # returns original on error
