"""EmbeddingWorker — async embedding request queue and batch processor.

Coordinates concurrent embedding requests against a single backend, batching
them to improve throughput. All inference runs in a thread pool to avoid
blocking the asyncio event loop.

Public API
----------
submit(text: str) -> asyncio.Future[list[float]]
    Submit a text for embedding. Returns a Future that resolves to the
    embedding vector. The Future is cancellable.
submit_turn(turn: Turn) -> Turn | None
    Convenience wrapper: embeds turn.query_text, returns a new Turn with
    query_embedding set (via Turn.with_embedding()).
flush() -> int
    Wait for all pending embeddings to complete. Returns the number processed.
shutdown() -> None
    Cancel pending work and shut down the background task.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress as _suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from orthrus.embedding._protocol import EmbeddingBackend

logger = structlog.get_logger(__name__)


@dataclass
class _EmbeddingRequest:
    """A single pending embedding request."""

    text: str
    future: asyncio.Future[list[float]]


class EmbeddingWorker:
    """Async worker that batches embedding requests against a backend.

    Submits texts via ``submit()`` and resolves them via a background
    task that collects batches and calls the backend.

    Thread-safety: all state is guarded by the asyncio event loop.

    Args:
        backend: EmbeddingBackend implementation to delegate to.
        batch_size: Maximum number of texts to batch per inference call.
        batch_timeout: Max seconds to wait before running a partial batch.
    """

    def __init__(
        self,
        backend: EmbeddingBackend,
        *,
        batch_size: int = 32,
        batch_timeout: float = 0.05,
    ) -> None:
        self._backend = backend
        self._batch_size = batch_size
        self._batch_timeout = batch_timeout

        # Pending requests accumulated since last inference call
        self._pending: list[_EmbeddingRequest] = []
        # asyncio events for graceful shutdown
        self._shutdown_event = asyncio.Event()
        self._done_event = asyncio.Event()
        # Background task
        self._task: asyncio.Task[None] | None = None
        # Track flush() callers
        self._flush_event: asyncio.Event | None = None
        self._flush_count = 0

    # ------------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------------

    @property
    def dimensions(self) -> int:
        """Embedding vector dimensions (delegated to backend)."""
        return self._backend.dimensions

    def submit(self, text: str) -> asyncio.Future[list[float]]:
        """Submit a text for embedding.

        Returns a Future that resolves to the embedding vector (list[float]).
        The Future is already scheduled — cancelling it removes the request
        from the next batch.

        Args:
            text: Non-empty text string to embed.
        """
        if self._shutdown_event.is_set():
            raise RuntimeError("EmbeddingWorker is shut down")

        fut: asyncio.Future[list[float]] = asyncio.Future()
        self._pending.append(_EmbeddingRequest(text=text, future=fut))

        # Start background task on first submission
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(
                self._run(), name="orthrus-embedding-worker"
            )

        return fut

    async def submit_turn(self, turn: Turn) -> Turn | None:
        """Embed turn.query_text, return a new Turn with query_embedding set.

        If embedding fails, returns the original turn unchanged.

        Args:
            turn: Turn to embed. Uses turn.query_text.
        """
        if not self._shutdown_event.is_set() and (
            self._task is None or self._task.done()
        ):
            self._task = asyncio.create_task(
                self._run(), name="orthrus-embedding-worker"
            )

        fut = self.submit(turn.query_text)
        try:
            embedding = await fut
            return turn.with_embedding(embedding)
        except Exception:
            logger.warning("embedding_failed_for_turn", trace_id=turn.trace_id)
            return turn

    async def flush(self) -> int:
        """Wait for all pending embeddings to complete.

        Returns the number of embeddings resolved in this flush.
        Safe to call concurrently from multiple coroutines — they will
        all wait for the same flush cycle.
        """
        if not self._pending:
            return 0

        # Create a shared event so all callers wait for the same thing
        flush_event = asyncio.Event()
        old_flush = self._flush_event
        self._flush_event = flush_event

        if old_flush is not None:
            old_flush.set()  # unblock any previous flush() caller

        try:
            await flush_event.wait()
            return self._flush_count
        finally:
            self._flush_count = 0

    async def shutdown(self) -> None:
        """Cancel pending work and shut down the background task.

        After shutdown, no new submissions are accepted.
        """
        self._shutdown_event.set()

        if self._task is not None and not self._task.done():
            self._task.cancel()
            with _suppress(asyncio.CancelledError):
                await self._task

        # Resolve any remaining futures with CancelledError
        for req in self._pending:
            if not req.future.done():
                req.future.cancel()

        self._done_event.set()
        logger.info("embedding_worker_shutdown")

    # ------------------------------------------------------------------------
    # Background task
    # ------------------------------------------------------------------------

    async def _run(self) -> None:
        """Background task: accumulate requests and batch-process them."""
        logger.info("embedding_worker_started")

        try:
            while not self._shutdown_event.is_set():
                # Wait for a batch to be ready (full or timeout)
                await self._wait_for_batch()

                if self._shutdown_event.is_set():
                    break

                # Drain the batch
                batch = self._pending[: self._batch_size]
                self._pending[: len(batch)] = []

                if not batch:
                    continue

                # Run inference in thread pool (backend may be blocking)
                texts = [req.text for req in batch]
                try:
                    embeddings: list[list[float]] = await asyncio.to_thread(
                        self._backend.encode, texts
                    )
                except Exception as exc:
                    logger.error("embedding_batch_error", error=str(exc))
                    for req in batch:
                        if not req.future.done():
                            req.future.set_exception(exc)
                    continue

                # Resolve futures
                flush_count = 0
                for req, emb in zip(batch, embeddings, strict=True):
                    if not req.future.done():
                        req.future.set_result(emb)
                        flush_count += 1

                if self._flush_event is not None and flush_count > 0:
                    self._flush_count = flush_count
                    self._flush_event.set()
                    self._flush_event = None

        except asyncio.CancelledError:
            logger.info("embedding_worker_cancelled")
            raise
        finally:
            self._done_event.set()
            logger.info("embedding_worker_exited")

    async def _wait_for_batch(self) -> None:
        """Wait until the pending queue has a full batch or times out."""
        if len(self._pending) >= self._batch_size:
            return  # already have a full batch

        # Wait for the timeout, or until we're shut down
        with _suppress(TimeoutError):
            await asyncio.wait_for(
                self._shutdown_event.wait(),
                timeout=self._batch_timeout,
            )


# Import Turn only for type hints (avoids circular import)
from orthrus.capture.turn import Turn  # noqa: E402, F401
