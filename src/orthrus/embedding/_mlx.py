"""MLXBackend — Apple Silicon GPU embeddings via MLX.

Provides fp16 GPU inference on Apple Silicon via the MLX library.
Models must be pre-converted to MLX format using ``mlx_lm.utils.convert``
before use with this backend.

Profile mapping:
    performance -> MLX fp16, GPU, <2GB, ~5ms/query

Requirements:
    - Apple Silicon Mac (arm64)
    - ``mlx`` and ``mlx-lm`` packages
    - Model pre-converted to MLX format

Conversion example::

    python -m mlx_lm.utils \\
        --model sentence-transformers/all-MiniLM-L6-v2 \\
        --output /path/to/mlx-model
"""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from typing import Any, cast

import structlog

logger = structlog.get_logger(__name__)

# Lazy state — module-level to share across instances
_mlx_model: Any = None
_mlx_tokenizer: Any = None
_mlx_dims: int | None = None
_mlx_lock = threading.Lock()


def _load_mlx_model(model_path: Path) -> tuple[Any, Any, int]:
    """Load a pre-converted MLX model and tokenizer.

    Args:
        model_path: Directory containing a converted MLX model.

    Returns:
        Tuple of (model, tokenizer, hidden_size).

    Raises:
        RuntimeError: If MLX is unavailable or model cannot be loaded.
    """
    global _mlx_model, _mlx_tokenizer, _mlx_dims

    if _mlx_model is not None and _mlx_tokenizer is not None:
        return _mlx_model, _mlx_tokenizer, _mlx_dims or 384

    with _mlx_lock:
        if _mlx_model is not None and _mlx_tokenizer is not None:
            return _mlx_model, _mlx_tokenizer, _mlx_dims or 384

        try:
            from mlx_lm import load
        except ImportError:
            raise RuntimeError(
                "MLX is not installed. Install with: uv pip install mlx mlx-lm"
            ) from None

        logger.info("mlx_loading_model", path=str(model_path))

        model, tokenizer = load(str(model_path), lazy=True, return_config=False)  # type: ignore[misc]
        tokenizer_type = type(tokenizer).__name__
        logger.info(
            "mlx_model_loaded",
            path=str(model_path),
            tokenizer_type=tokenizer_type,
        )

        hidden_size = _infer_hidden_size(model)

        _mlx_model = model
        _mlx_tokenizer = tokenizer
        _mlx_dims = hidden_size

        logger.info(
            "mlx_model_ready",
            path=str(model_path),
            hidden_size=hidden_size,
        )
        return model, tokenizer, hidden_size


def _infer_hidden_size(model: Any) -> int:
    """Infer embedding dimension from an MLX model."""
    # Try to get hidden_size from model config
    if hasattr(model, "config"):
        config = model.config
        if hasattr(config, "hidden_size"):
            return int(config.hidden_size)
        if hasattr(config, "d_model"):
            return int(config.d_model)
        if hasattr(config, "embedding_dim"):
            return int(config.embedding_dim)

    # Fallback: try loading config from the model
    config_path = getattr(model, "config_path", None)
    if config_path is not None:
        config_path = Path(config_path)
        if config_path.exists():
            config = json.loads(config_path.read_text())
            return int(
                config.get(
                    "hidden_size",
                    config.get("d_model", config.get("embedding_dim", 384)),
                )
            )

    # Default fallback
    logger.warning("mlx_hidden_size_inference_failed", using_default=384)
    return 384


def _mx_mean_pool(
    hidden_states: Any,
    attention_mask: Any,
    padding_side: str = "right",
) -> list[list[float]]:
    """Mean pool last hidden state over token dimension (MLX version)."""
    import mlx.core as mx

    if attention_mask is None:
        pooled = mx.mean(hidden_states, axis=1)
        return cast(list[list[float]], pooled.tolist())

    # Expand mask: (batch, seq) -> (batch, seq, 1)
    mask_expanded = mx.expand_dims(
        attention_mask.astype(mx.float32), axis=2
    )
    masked_hidden = hidden_states * mask_expanded
    sum_hidden = mx.sum(masked_hidden, axis=1)
    mask_sum = mx.sum(mask_expanded, axis=1)
    mask_sum = mx.maximum(mask_sum, 1e-9)
    pooled = sum_hidden / mask_sum

    return cast(list[list[float]], pooled.tolist())


class MLXBackend:
    """Embedding backend using MLX on Apple Silicon GPU.

    Loads a pre-converted MLX model directory and runs fp16 inference
    on the GPU (or CPU fallback). Models must be converted using
    ``mlx_lm`` before use.

    Args:
        model_path: Directory containing a converted MLX model.
            Use ``mlx_lm.utils.convert`` to convert a HuggingFace model::

                python -m mlx_lm.utils \\
                    --model sentence-transformers/all-MiniLM-L6-v2 \\
                    --output /path/to/mlx-model

        batch_size: Maximum batch size for inference (default 32).
        fallback_to_cpu: If True, fall back to CPU when GPU is unavailable.
            Default False (raises on GPU failure).

    Example::

        backend = MLXBackend(model_path=Path("~/mlx-embeddings"))
        worker = EmbeddingWorker(backend)
    """

    def __init__(
        self,
        model_path: Path,
        *,
        batch_size: int = 32,
        fallback_to_cpu: bool = False,
    ) -> None:
        self._model_path = model_path
        self._batch_size = batch_size
        self._fallback_to_cpu = fallback_to_cpu
        self._dimensions: int | None = None

    @property
    def dimensions(self) -> int:
        """Embedding vector dimensions (loaded from model on first access)."""
        if self._dimensions is None:
            _, _, hidden_size = _load_mlx_model(self._model_path)
            self._dimensions = hidden_size
        return self._dimensions

    def encode(self, texts: list[str]) -> list[list[float]]:
        """Encode texts to embedding vectors via MLX.

        Args:
            texts: List of non-empty strings.

        Returns:
            List of embedding vectors (list[float]), one per input text.
        """
        model, tokenizer, _ = _load_mlx_model(self._model_path)

        tokenizer_output = tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=256,
            return_tensors="mlx",
        )

        input_ids = tokenizer_output["input_ids"]
        attention_mask = tokenizer_output.get("attention_mask")

        # Most sentence-transformers models are bidirectional transformers.
        # mlx_lm converts them as causal LMs. Try bidirectional first,
        # fall back to causal LM path if that fails.
        try:
            # Bidirectional path
            outputs = model(input_ids=input_ids, attention_mask=attention_mask)
            last_hidden = outputs.last_hidden_state
            embeddings = _mx_mean_pool(last_hidden, attention_mask)
            return embeddings

        except TypeError:
            # Causal LM path — mean pool (same approach works for both)
            logger.debug("mlx_using_causal_lm_path")
            last_hidden = model(input_ids)
            if hasattr(last_hidden, "last_hidden_state"):
                last_hidden = last_hidden.last_hidden_state
            embeddings = _mx_mean_pool(last_hidden, attention_mask)
            return embeddings

    async def submit(self, turn: Any) -> Any:
        """Embed turn.query_text, return a new Turn with query_embedding set."""
        try:
            emb = await asyncio.to_thread(self.encode, [turn.query_text])
            return turn.with_embedding(emb[0])
        except Exception as exc:
            logger.warning(
                "mlx_submit_failed",
                trace_id=turn.trace_id,
                error=str(exc),
            )
            return turn

    async def flush(self) -> int:
        """Flush is a no-op for MLXBackend — MLX processes synchronously."""
        return 0
