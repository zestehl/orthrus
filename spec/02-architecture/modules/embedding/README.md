# Module: embedding

---
status: implemented
priority: P1
implemented: 2026-04-10
tested: 45/45 tests passing
---

## Responsibility

Asynchronous text embedding generation with pluggable backends.

**In scope:**
- Backend abstraction (ONNX, Transformers, MLX)
- Async batch processing
- Model loading and caching
- Quantization (int8 for CPU, fp16 for GPU)

**Out of scope:**
- Model training or fine-tuning
- Multi-modal embeddings (images, audio)

## Interface

### Public API

```python
from orthrus.embedding import EmbeddingBackend, EmbeddingConfig

class EmbeddingBackend(Protocol):
    """Pluggable embedding backend."""

    def encode(self, texts: list[str]) -> list[list[float]]: ...
    def batch_size(self) -> int: ...
    def dimensions(self) -> int: ...

class EmbeddingWorker:
    """Async embedding generation worker."""

    def __init__(self, backend: EmbeddingBackend, config: EmbeddingConfig) -> None: ...

    def submit(self, text: str, turn_id: str) -> Future:
        """Submit text for embedding. Returns Future."""
        ...

    def shutdown(self) -> None:
        """Complete pending work and shutdown."""
        ...

# Backend implementations
class OnnxBackend(EmbeddingBackend): ...  # CPU, quantized
class TransformersBackend(EmbeddingBackend): ...  # GPU when available
class MLXBackend(EmbeddingBackend): ...  # Apple Silicon GPU
```

## Dependencies

- **config**: Model selection, resource profile (determines backend)
- **external**: onnxruntime, transformers, torch, mlx (optional)

## Resource Contract

| Profile | Backend | Batch | Memory | Latency |
|---------|---------|-------|--------|---------|
| minimal | None | N/A | 0 | N/A |
| standard | TransformersBackend (fp32, CPU/GPU) | 32 | <500MB | 20ms/query |
| performance | OnnxBackend (int8, CPU/CoreML) | 32 | <200MB | 50ms/query |
| Apple Silicon | MLXBackend (fp16, GPU) | 32 | <2GB | 5ms/query |

## Error Handling

| Error | Response |
|-------|----------|
| Model load fail | Degrade to no-embedding backend |
| OOM during inference | Reduce batch size, retry |
| Timeout | Return null embedding, log warning |

## Testing

- Unit: Backend produces expected dimensions
- Unit: Worker batch accumulation and timeout flushing
- Integration: Async pipeline processes texts end-to-end
- Benchmark: Latency and throughput by backend

## Implementation

**Files:**
- `src/orthrus/embedding/__init__.py` — Public re-exports
- `src/orthrus/embedding/_protocol.py` — EmbeddingBackend Protocol
- `src/orthrus/embedding/_transformers.py` — TransformersBackend (CPU/GPU, PyTorch)
- `src/orthrus/embedding/_onnx.py` — OnnxBackend (CPU/CoreML int8 quantized)
- `src/orthrus/embedding/_mlx.py` — MLXBackend (Apple Silicon GPU fp16)
- `src/orthrus/embedding/_worker.py` — EmbeddingWorker (async batch processing)

**Backend status:**
- `TransformersBackend` — implemented (CPU/GPU, PyTorch)
- `OnnxBackend` — implemented (CPU/CoreML int8 quantized)
- `MLXBackend` — implemented (Apple Silicon GPU fp16)
- Tests: `tests/embedding/` — 45 tests across 4 test files

**Profile mapping:**
| Profile | Backend | Batch | Memory | Latency |
|---------|---------|-------|--------|---------|
| minimal | None | N/A | 0 | N/A |
| standard | TransformersBackend (fp32, CPU/GPU) | 32 | <500MB | 20ms/query |
| performance | OnnxBackend (int8, CPU/CoreML) | 32 | <200MB | 50ms/query |
| (Apple Silicon) | MLXBackend (fp16, GPU) | 32 | <2GB | 5ms/query |
