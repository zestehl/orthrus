# Module: embedding

---
status: in-progress
priority: P1
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
    
    def encode(self, texts: List[str]) -> List[List[float]]: ...
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
```

## Dependencies

- **config**: Model selection, resource profile (determines backend)
- **external**: onnxruntime, transformers, torch, mlx (optional)

## Resource Contract

| Profile | Backend | Batch | Memory | Latency |
|---------|---------|-------|--------|---------|
| minimal | None | N/A | 0 | N/A |
| standard | ONNX int8 | 32 | <200MB | 50ms/query |
| performance | GPU fp16 | 128 | <2GB | 5ms/query |

## Error Handling

| Error | Response |
|-------|----------|
| Model load fail | Degrade to no-embedding backend |
| OOM during inference | Reduce batch size, retry |
| Timeout | Return null embedding, log warning |

## Testing

- Unit: Backend produces expected dimensions
- Integration: Async pipeline processes 1000 texts
- Benchmark: Latency and throughput by backend

## Implementation

**Files:**
- `src/orthrus/embedding/_protocol.py` — EmbeddingBackend Protocol
- `src/orthrus/embedding/_transformers.py` — TransformersBackend (GPU when available)
- `src/orthrus/embedding/_worker.py` — EmbeddingWorker (async batch processing)

**Status:**
- `TransformersBackend` — implemented
- `OnnxBackend` — **NOT YET IMPLEMENTED** (CPU quantized per spec)
- `MLXBackend` — **NOT YET IMPLEMENTED** (Apple Silicon GPU)

**Tests:** `tests/embedding/` exists with test_transformers.py, test_worker.py
