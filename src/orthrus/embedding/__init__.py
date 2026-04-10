"""Embedding module — async text embedding generation with pluggable backends.

Public API
----------
EmbeddingBackend : Protocol
    Interface any backend must implement.
EmbeddingWorker : class
    Async worker that manages a queue of embedding requests.
TransformersBackend : class
    Backend using sentence-transformers.

Example
-------
::

    from orthrus.embedding import EmbeddingWorker, TransformersBackend
    from orthrus.config import EmbeddingConfig

    config = EmbeddingConfig(model="all-MiniLM-L6-v2", dimensions=384)
    backend = TransformersBackend(config)
    worker = EmbeddingWorker(backend, batch_size=32)

    future = await worker.submit("What is the capital of France?")
    embedding = await future  # List[float]

    await worker.shutdown()
"""

from __future__ import annotations

from orthrus.embedding._protocol import EmbeddingBackend  # noqa: F401
from orthrus.embedding._transformers import TransformersBackend
from orthrus.embedding._worker import EmbeddingWorker

__all__ = [
    "EmbeddingBackend",
    "EmbeddingWorker",
    "TransformersBackend",
]
