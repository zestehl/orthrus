"""OnnxBackend — ONNX Runtime inference for embeddings.

Provides CPU/CoreML inference via ONNX Runtime, optionally int8-quantized.
Supports loading from a HuggingFace model (auto-exported to ONNX) or
a pre-exported ONNX model directory.

Profile mapping:
    minimal  -> None (no-op, embeddings disabled)
    standard -> ONNX int8 quantized, ~50ms/query, <200MB
    performance -> ONNX fp32 (faster but larger)
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import Any, cast

import numpy as np
import structlog

logger = structlog.get_logger(__name__)

# Lazy state — module-level to share across instances
_ort_model: Any = None
_tokenizer: Any = None
_onnx_lock = threading.Lock()


def _mean_pool(
    hidden_states: np.ndarray,
    attention_mask: np.ndarray | None,
    padding_side: str = "right",
) -> list[list[float]]:
    """Mean pool last hidden state over token dimension.

    Handles attention mask correctly — masks padding tokens so they
    don't contribute to the average.
    """
    if attention_mask is None:
        result = np.mean(hidden_states, axis=1).tolist()
        return [result]

    # Expand attention mask: (batch, seq_len) -> (batch, seq_len, 1)
    mask_expanded = np.expand_dims(attention_mask, axis=2).astype(np.float32)

    # Multiply hidden states by mask (0 for padding, 1 for real tokens)
    masked_hidden = hidden_states * mask_expanded

    # Sum over seq_len, divide by actual token count (sum of mask)
    sum_hidden = np.sum(masked_hidden, axis=1)
    mask_sum = np.sum(mask_expanded, axis=1).clip(min=1e-9)
    pooled = sum_hidden / mask_sum

    return cast(list[list[float]], pooled.tolist())


def _load_onnx_model(
    model_name: str,
    model_path: Path | None,
    provider: str = "CPUExecutionProvider",
) -> tuple[Any, Any]:
    """Load or export an ONNX model and tokenizer.

    Args:
        model_name: HuggingFace model ID (e.g. ``all-MiniLM-L6-v2``).
        model_path: Optional pre-exported ONNX model directory.
            If provided, the model is loaded directly from this path.
            If None, the model is exported to ONNX from the HuggingFace repo.
        provider: ONNX Runtime provider (``CPUExecutionProvider`` or
            ``CoreMLExecutionProvider`` for Apple Silicon).

    Returns:
        Tuple of (ORTModelForFeatureExtraction, tokenizer).
    """
    global _ort_model, _tokenizer

    if _ort_model is not None and _tokenizer is not None:
        return _ort_model, _tokenizer

    # Import here to avoid hard dependency when not using ONNX backend
    from optimum.onnxruntime import ORTModelForFeatureExtraction
    from transformers import AutoTokenizer

    with _onnx_lock:
        if _ort_model is not None and _tokenizer is not None:
            return _ort_model, _tokenizer

        if model_path is not None:
            logger.info("onnx_loading_from_path", path=str(model_path))
            _ort_model = ORTModelForFeatureExtraction.from_pretrained(
                str(model_path),
                provider=provider,
            )
            _tokenizer = AutoTokenizer.from_pretrained(str(model_path))  # type: ignore[no-untyped-call]
        else:
            logger.info("onnx_exporting_model", model=model_name)
            _ort_model = ORTModelForFeatureExtraction.from_pretrained(
                model_name,
                export=True,
                provider=provider,
            )
            _tokenizer = AutoTokenizer.from_pretrained(model_name)  # type: ignore[no-untyped-call]
            cache_dir = Path("~/.cache/huggingface/ort").expanduser()
            logger.info(
                "onnx_model_exported",
                cache_dir=str(cache_dir),
                hint="Export once, reuse next load",
            )

        logger.info(
            "onnx_model_loaded",
            model=model_name,
            provider=provider,
            dimensions=_ort_model.config.hidden_size,
        )
        return _ort_model, _tokenizer


class OnnxBackend:
    """Embedding backend using ONNX Runtime.

    Provides CPU/CoreML inference via ONNX Runtime, optionally int8-quantized.
    Lazy-loads the model on first encode call (thread-safe).

    Args:
        model_name: HuggingFace model ID for the embedding model.
            Default: ``sentence-transformers/all-MiniLM-L6-v2``.
        model_path: Optional path to a pre-exported ONNX model directory.
            If provided, ``model_name`` is ignored for the ONNX model.
        provider: ONNX Runtime provider string.
            - ``CPUExecutionProvider`` (default): pure CPU.
            - ``CoreMLExecutionProvider``: Apple Silicon GPU via CoreML.
        quantize: If True, apply int8 quantization on first load.
            Only used when model_path is None (export path).
    """

    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        *,
        model_path: Path | None = None,
        provider: str = "CPUExecutionProvider",
        quantize: bool = False,
    ) -> None:
        self._model_name = model_name
        self._model_path = model_path
        self._provider = provider
        self._quantize = quantize
        self._dimensions: int | None = None

    @property
    def dimensions(self) -> int:
        """Embedding vector dimensions (loaded from model on first access)."""
        if self._dimensions is None:
            model, _ = _load_onnx_model(
                self._model_name, self._model_path, self._provider
            )
            self._dimensions = model.config.hidden_size
        return self._dimensions

    def encode(self, texts: list[str]) -> list[list[float]]:
        """Encode texts to embedding vectors via ONNX Runtime.

        Args:
            texts: List of non-empty strings.

        Returns:
            List of embedding vectors (list[float]), one per input text.
        """
        model, tokenizer = _load_onnx_model(
            self._model_name, self._model_path, self._provider
        )

        inputs = tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=256,
            return_tensors="np",
        )

        outputs = model(**dict(inputs))

        last_hidden: np.ndarray = outputs.last_hidden_state

        attention_mask: np.ndarray | None = inputs.get("attention_mask")
        embeddings = _mean_pool(last_hidden, attention_mask, tokenizer.padding_side)

        return embeddings

    async def submit(self, turn: Any) -> Any:
        """Embed turn.query_text, return a new Turn with query_embedding set."""
        try:
            emb = await asyncio.to_thread(self.encode, [turn.query_text])
            return turn.with_embedding(emb[0])
        except Exception as exc:
            logger.warning(
                "onnx_submit_failed",
                trace_id=turn.trace_id,
                error=str(exc),
            )
            return turn

    async def flush(self) -> int:
        """Flush is a no-op for OnnxBackend — ONNX processes synchronously."""
        return 0
