# Module: capture

---
status: not-started
priority: P0
---

## Responsibility

Capture agent turns with minimal latency and guaranteed durability.

**In scope:**
- Turn validation and normalization
- Ingest queue management (bounded, async)
- Coordination with storage module for persistence
- Coordination with embedding module for vector generation

**Out of scope:**
- Embedding generation (delegates to embedding module)
- Persistent storage (delegates to storage module)
- Search functionality (handled by search module)

## Interface

### Public API

```python
from orthrus.capture import CaptureManager, Turn, TurnData

class TurnData:
    """Data required to capture a turn."""
    query_text: str
    context_ref: str
    available_tools: List[str]
    tool_calls: List[Dict]
    success: bool
    duration_ms: int

class CaptureManager:
    """Manages turn capture lifecycle."""
    
    def __init__(self, config: CaptureConfig) -> None: ...
    
    def start(self) -> None:
        """Start capture workers."""
        ...
    
    def capture(self, turn: TurnData) -> str:
        """
        Capture a turn.
        
        Returns trace_id immediately (non-blocking).
        Raises CaptureError if queue full and cannot flush.
        """
        ...
    
    def shutdown(self, timeout_seconds: float = 30.0) -> None:
        """Graceful shutdown, flush queue."""
        ...
    
    def status(self) -> CaptureStatus:
        """Current queue depth, workers, health."""
        ...
```

### CLI

```bash
# No direct CLI commands. Managed via `orthrus capture` in CLI module.
```

## Dependencies

- **config**: Load capture settings, resource profile
- **storage**: Persist turns to Parquet/JSONL
- **embedding**: Request async embedding generation

## Resource Contract

| Profile | Queue Size | Memory | Latency Target |
|---------|------------|--------|----------------|
| minimal | 10 turns | <50MB | <20ms |
| standard | 100 turns | <100MB | <10ms |
| performance | 1000 turns | <500MB | <5ms |

## Error Handling

| Error | Response | Recovery |
|-------|----------|----------|
| Queue full | Drop oldest, log warning | Increase flush frequency |
| Storage write fail | Retry 3x, then alert | Queue continues, alerts user |
| Embedding fail | Mark embedding null | Text capture succeeds |

## Testing

- Unit: Queue behavior under pressure
- Integration: End-to-end capture with mock storage
- Property: All captured turns are valid schema
