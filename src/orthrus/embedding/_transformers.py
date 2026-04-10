"""TransformersBackend — sentence-transformers implementation of EmbeddingBackend."""

from __future__ import annotations

import asyncio
import threading

import structlog

if __name__ == "__main__":
    # Allow running as a script to download / verify model
    import sys

    sys.path.insert(0, "src")

from sentence_transformers import SentenceTransformer

logger = structlog.get_logger(__name__)


class TransformersBackend:
    """Embedding backend using sentence-transformers.

    Loads ``model_name`` lazily on first encode call. The model is cached
    in memory after first load.

    Args:
        model_name: HuggingFace model ID or local path.
            Defaults to ``all-MiniLM-L6-v2``.
        device: ``cpu``, ``cuda``, or ``auto`` (default).
            ``auto`` picks CUDA if available, falls back to CPU.
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        *,
        device: str = "cpu",
    ) -> None:
        self._model_name = model_name
        self._device = device
        self._model: SentenceTransformer | None = None
        self._dimensions: int | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------------
    # EmbeddingBackend interface
    # ------------------------------------------------------------------------

    @property
    def dimensions(self) -> int:
        """Embedding vector dimensions (loaded from model on first access)."""
        if self._dimensions is None:
            self._ensure_model()
            assert self._model is not None
            self._dimensions = self._model.get_sentence_embedding_dimension()
        return self._dimensions  # type: ignore[return-value]

    def encode(self, texts: list[str]) -> list[list[float]]:
        """Encode a batch of texts into embedding vectors.

        Called by EmbeddingWorker in a thread. This method is synchronous
        and blocking.

        Args:
            texts: List of non-empty strings.

        Returns:
            List of embedding vectors (list[float]), one per input text,
            in the same order.

        Raises:
            RuntimeError: If model loading fails.
        """
        self._ensure_model()
        assert self._model is not None
        embeddings = self._model.encode(texts, convert_to_numpy=False)
        return [emb.tolist() for emb in embeddings]

    async def submit(self, turn: Turn) -> Turn | None:
        """Embed turn.query_text and return a new Turn with query_embedding set.

        Args:
            turn: Turn to embed. Uses turn.query_text.

        Returns:
            A new Turn with query_embedding set, or the original turn
            unchanged if encoding fails.
        """
        try:
            emb = await self._async_encode(turn.query_text)
            return turn.with_embedding(emb)
        except Exception as exc:
            logger.warning(
                "transformers_submit_failed",
                trace_id=turn.trace_id,
                error=str(exc),
            )
            return turn

    async def flush(self) -> int:
        """Flush is a no-op for TransformersBackend.

        Sentence-transformers processes synchronously; there is no
        in-flight work beyond what the worker has already waited for.
        """
        return 0

    # ------------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------------

    def _ensure_model(self) -> None:
        """Lazily load the model (thread-safe)."""
        if self._model is not None:
            return

        with self._lock:
            if self._model is not None:  # double-check after acquiring lock
                return

            logger.info("transformers_loading_model", model=self._model_name)
            try:
                device = self._device
                if device == "auto":
                    device = "cpu"  # default to CPU unless explicitly requested

                self._model = SentenceTransformer(self._model_name, device=device)
                self._dimensions = self._model.get_sentence_embedding_dimension()
                logger.info(
                    "transformers_model_loaded",
                    model=self._model_name,
                    dimensions=self._dimensions,
                )
            except Exception as exc:
                logger.error(
                    "transformers_model_load_failed",
                    model=self._model_name,
                    error=str(exc),
                )
                raise RuntimeError(
                    f"Failed to load embedding model '{self._model_name}': {exc}"
                ) from exc

    async def _async_encode(self, text: str) -> list[float]:
        """Encode a single text asynchronously (runs in thread pool)."""
        batch: list[list[float]] = await asyncio.to_thread(
            self.encode, [text]
        )
        return batch[0]


# Import Turn only for type hints (avoids circular import at module level)
from orthrus.capture.turn import Turn  # noqa: E402, F401, E501
