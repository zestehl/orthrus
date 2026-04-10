"""EmbeddingBackend Protocol — interface for all embedding backends."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from orthrus.capture.turn import Turn


class EmbeddingBackend(Protocol):
    """Pluggable async embedding backend.

    Implement this protocol to add vector generation to the capture pipeline.
    The backend is called after a turn is dequeued but before it is written
    to storage, allowing the turn's query_embedding field to be populated.

    All methods are async to avoid blocking the drain task.
    """

    @property
    def dimensions(self) -> int:
        """Embedding vector dimensions."""

    def encode(self, texts: list[str]) -> list[list[float]]:
        """Encode a batch of texts.

        Called by EmbeddingWorker in a thread pool. Must be synchronous
        and blocking.

        Args:
            texts: List of non-empty strings.

        Returns:
            List of embedding vectors (list[float]), one per input text.
        """

    async def submit(self, turn: Turn) -> Turn | None:
        """Submit a turn for async embedding.

        The backend should return the turn with query_embedding set
        (via Turn.with_embedding()), or None if embedding failed.
        The returned turn is what gets written to storage.

        This method is called from the drain task and must not block
        the event loop (delegate long work to a thread pool if needed).
        """

    async def flush(self) -> int:
        """Flush pending embeddings and return the number processed.

        Called during shutdown to ensure all in-flight embeddings complete
        before the worker exits.
        """
