"""OnnxBackend — ONNX Runtime inference for embeddings.

Provides CPU inference via ONNX Runtime on any platform (x86, AMD, ARM).
Supports loading from a HuggingFace model (auto-exported to ONNX) or
a pre-exported ONNX model directory.

Platform/provider matrix:
    x86_64 Linux/Windows : CPUExecutionProvider (MKL-ML/OpenBLAS) or
                            ROCmExecutionProvider (AMD GPU)
    ARM64 (Apple Silicon) : CPUExecutionProvider or CoreMLExecutionProvider (Neural Engine)
    AMD GPU (Windows)      : DirectMLExecutionProvider
    Generic                : CPUExecutionProvider (always available)

The ``quantize`` flag applies int8 quantization to the exported model,
reducing memory ~4x at cost of minor accuracy loss.

Profile mapping:
    minimal      -> None (no-op, embeddings disabled)
    standard     -> ONNX fp32 CPU, ~50ms/query, <200MB
    performance  -> ONNX int8 quantized CPU, ~20ms/query, <100MB
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
    quantize: bool = False,
) -> tuple[Any, Any]:
    """Load or export an ONNX model and tokenizer.

    Args:
        model_name: HuggingFace model ID (e.g. ``all-MiniLM-L6-v2``).
        model_path: Optional pre-exported ONNX model directory.
            If provided, the model is loaded directly from this path.
            If None, the model is exported to ONNX from the HuggingFace repo.
        provider: ONNX Runtime provider string.
            - ``CPUExecutionProvider`` (default): pure CPU, works on all platforms.
            - ``CoreMLExecutionProvider``: Apple Silicon Neural Engine.
            - ``ROCmExecutionProvider``: AMD GPU (Linux ROCm).
            - ``DMLExecutionProvider``: DirectX GPU (Windows).
            Auto-detected if None.
        quantize: If True, apply int8 dynamic quantization after export.
            Reduces memory ~4x. Only used when model_path is None.

    Returns:
        Tuple of (ORTModelForFeatureExtraction, tokenizer).
    """
    global _ort_model, _tokenizer

    if _ort_model is not None and _tokenizer is not None:
        return _ort_model, _tokenizer

    # Auto-detect best available provider if none specified
    if provider == "CPUExecutionProvider":
        provider = _resolve_best_provider(provider)

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
            logger.info("onnx_exporting_model", model=model_name, quantize=quantize)
            _ort_model = ORTModelForFeatureExtraction.from_pretrained(
                model_name,
                export=True,
                provider=provider,
            )
            _tokenizer = AutoTokenizer.from_pretrained(model_name)  # type: ignore[no-untyped-call]

            if quantize:
                logger.info("onnx_quantizing", model=model_name)
                _quantize_model_dynamic_int8(_ort_model)

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


def _resolve_best_provider(requested: str) -> str:
    """Resolve the best available ONNX Runtime provider for this platform.

    Returns the most capable available provider that is compatible with
    the requested one. Falls back to ``CPUExecutionProvider`` if the
    requested provider is not available.

    Platform detection logic:
        - x86_64/AMD: prefer ``CPUExecutionProvider`` (MKL-ML/OpenBLAS),
          AMD GPUs use ``ROCmExecutionProvider`` on Linux.
        - ARM64/Apple Silicon: ``CoreMLExecutionProvider`` if available,
          otherwise ``CPUExecutionProvider``.
        - All platforms: ``CPUExecutionProvider`` is always available.
    """
    import platform

    import onnxruntime as ort

    available = ort.get_available_providers()
    system = platform.system()  # Darwin, Linux, Windows
    arch = platform.machine()  # arm64, x86_64, aarch64

    # If requested is available and platform matches, use it
    if requested in available:
        return requested

    # Apple Silicon: prefer CoreML, fall back to CPU
    if system == "Darwin" and arch == "arm64":
        if "CoreMLExecutionProvider" in available:
            logger.debug("onnx_provider_fallback", from_=requested, to="CoreMLExecutionProvider")
            return "CoreMLExecutionProvider"
        if "CPUExecutionProvider" in available:
            logger.debug("onnx_provider_fallback", from_=requested, to="CPUExecutionProvider")
            return "CPUExecutionProvider"

    # AMD GPU on Linux: ROCmExecutionProvider
    if "ROCmExecutionProvider" in available:
        return "ROCmExecutionProvider"

    # AMD/Intel GPU on Windows: DML or OpenVINO
    if "DMLExecutionProvider" in available:
        return "DMLExecutionProvider"
    if "OpenVINOExecutionProvider" in available:
        return "OpenVINOExecutionProvider"

    # Default fallback
    if "CPUExecutionProvider" in available:
        return "CPUExecutionProvider"

    # Last resort: return whatever was requested
    logger.warning("onnx_no_provider_found", available=available, using=requested)
    return requested


def _quantize_model_dynamic_int8(model: Any) -> None:
    """Apply dynamic int8 quantization to an ONNX model in-place.

    Uses optimum's ``ORTQuantizer`` to quantize weights to int8
    with dynamic activation quantization.
    """
    try:
        from optimum.onnxruntime import ORTQuantizer
        from optimum.onnxruntime.configuration import AutoQuantizationConfig
    except ImportError:
        logger.warning(
            "onnx_quantization_skipped",
            reason="optimum not installed",
            hint="Install with: uv pip install optimum[onnxruntime]",
        )
        return

    # ORTQuantizer.from_pretrained takes a model instance or path
    model_dir = getattr(model, "model_dir", None)
    if model_dir is None:
        logger.warning("onnx_quantization_skipped", reason="no model_dir on model")
        return

    quantizer = ORTQuantizer.from_pretrained(model_dir)
    qconfig = AutoQuantizationConfig.int8(per_channel=False, symmetric=False)
    logger.info("onnx_quantization_started", model_dir=str(model_dir))

    quantized_path = quantizer.quantize(
        quantization_config=qconfig,
        save_dir=str(model_dir),
    )
    logger.info("onnx_quantization_done", quantized_dir=str(quantized_path))


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
                self._model_name,
                self._model_path,
                self._provider,
                quantize=self._quantize,
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
            self._model_name,
            self._model_path,
            self._provider,
            quantize=self._quantize,
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
