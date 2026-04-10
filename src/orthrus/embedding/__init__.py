"""Embedding module — async text embedding generation with pluggable backends.

Public API
----------
EmbeddingBackend : Protocol
    Interface any backend must implement.
EmbeddingWorker : class
    Async worker that manages a queue of embedding requests.
TransformersBackend : class
    Backend using sentence-transformers (CPU/GPU, PyTorch).
OnnxBackend : class
    Backend using ONNX Runtime (CPU/CoreML, int8 quantized).
MLXBackend : class
    Backend using MLX (Apple Silicon GPU, fp16).

Example
-------
::

    from orthrus.embedding import EmbeddingWorker, TransformersBackend

    backend = TransformersBackend(model_name="all-MiniLM-L6-v2")
    worker = EmbeddingWorker(backend, batch_size=32)

    future = await worker.submit("What is the capital of France?")
    embedding = await future  # List[float]

    await worker.shutdown()
"""

from __future__ import annotations

from orthrus.embedding._mlx import MLXBackend
from orthrus.embedding._onnx import OnnxBackend
from orthrus.embedding._protocol import EmbeddingBackend  # noqa: F401
from orthrus.embedding._transformers import TransformersBackend
from orthrus.embedding._worker import EmbeddingWorker

__all__ = [
    "EmbeddingBackend",
    "EmbeddingWorker",
    "TransformersBackend",
    "OnnxBackend",
    "MLXBackend",
]
