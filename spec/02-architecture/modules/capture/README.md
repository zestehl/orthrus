# Module: capture

---
status: implemented
priority: P0
implemented: 2026-04-10
tested: 168/168 tests passing
---

## Responsibility

Capture agent turns with minimal latency and guaranteed durability. Acts as the ingestion boundary between the agent and persistent storage.

**In scope:**
- Turn validation and normalization at intake (`TurnData` input)
- Bounded asyncio ingest queue with back-pressure
- Background drain worker that writes to `StorageManager`
- Optional async embedding coordination via `EmbeddingBackend` protocol
- Graceful shutdown with full queue drain

**Out of scope:**
- Embedding generation itself (delegates to `EmbeddingBackend` implementation)
- Persistent storage (delegates to `StorageManager`)
- Search functionality (handled by search module)

---

## Key Design Decisions

### 1. `TurnData` as Frozen Dataclass Input

The agent passes a `TurnData` instance to `capture()`. `TurnData` is a `@dataclass(frozen=True)` with validation mirroring `Turn`. Raw dicts are rejected at the boundary to prevent ambiguous or unvalidated data from entering the queue.

Rationale: validated input means bad data never reaches the queue. Consistent with `Turn`'s design philosophy.

### 2. Asyncio Queue with Back-Pressure

`asyncio.Queue` with `maxsize` from `CaptureConfig.queue_max_size`. The `capture()` method:

```python
trace_id = generate_uuid7()
turn = Turn(trace_id=trace_id, session_id=session_id, timestamp=utc_now, **turn_data.as_dict())
await self._queue.put(turn)  # BLOCKS caller until space available
```

When the queue is full, the caller suspends. This is **back-pressure** -- the agent's capture speed is governed by the queue drain speed. No data is dropped.

Implication: agent responsiveness degrades before data is lost. Operators can monitor queue depth and act before the agent stalls.

### 3. `EmbeddingBackend` Protocol

A `Protocol` that the `CaptureManager` holds optionally. When an embedding backend is set and `embed_async=True`:

1. Background worker dequeues turn
2. Submits to `EmbeddingBackend.submit(turn)` -- non-blocking
3. Receives updated turn via callback (or future)
4. Writes updated turn to `StorageManager`

If no backend is set, turns go directly to `StorageManager`.

### 4. Single Background Drain Task

One `asyncio.Task` (`_drain_queue()`) consumes the queue and writes to `StorageManager` via `asyncio.to_thread()` to avoid blocking the event loop. Sufficient for I/O-bound storage writes.

### 5. Session ID Required

`capture()` requires a `session_id` argument. No automatic generation. Ambiguous or missing session IDs indicate upstream problems that should be fixed at the source, not normalized silently.

---

## Interface

### Public API

```python
from orthrus.capture import (
    CaptureManager,
    CaptureConfig,
    TurnData,
    CaptureResult,
    EmbeddingBackend,
)
from orthrus.config import CaptureConfig, Config

# --- Input ---

@dataclass(frozen=True)
class TurnData:
    """Validated input for a single agent turn."""
    query_text: str
    context_hash: str
    available_tools: tuple[str, ...]
    tool_calls: tuple[ToolCall, ...]
    outcome: TurnOutcome = TurnOutcome.SUCCESS
    duration_ms: int = 0
    error_class: str | None = None
    reasoning_content: str | None = None
    tool_selection: str | None = None
    active_skills: tuple[str, ...] = ()
    response_text: str | None = None
    user_rating: float | None = None

    def as_dict(self) -> dict: ...

# --- Result ---

@dataclass(frozen=True)
class CaptureResult:
    """Outcome of a capture() call."""
    trace_id: str
    error: str | None = None

# --- Protocol ---

class EmbeddingBackend(Protocol):
    """Pluggable async embedding backend.

    Implement this to add vector generation to the capture pipeline.
    The backend is called after a turn is enqueued but before it is
    written to storage, allowing the turn's query_embedding field
    to be populated.
    """

    @property
    def dimensions(self) -> int: ...

    async def submit(self, turn: Turn) -> Turn | None:
        """Submit a turn for embedding.

        The backend should return the turn with query_embedding populated,
        or None if embedding failed (turn will be written without embedding).

        This method is called from the background drain task and must not
        block the event loop.
        """
        ...

    async def flush(self) -> int:
        """Flush pending embeddings and return the number processed.

        Called during shutdown to drain in-flight embeddings.
        """
        ...

# --- Manager ---

class CaptureManager:
    """Manages turn capture lifecycle.

    Thread-safety: fully async, not thread-safe. Must be created and
    used from a single asyncio event loop.

    Args:
        config: Validated CaptureConfig. queue_max_size and flush_interval
            are read at construction time.
        storage: StorageManager instance. Required for capture to function.
            If None, capture() will raise CaptureError.
        embedding: Optional EmbeddingBackend. If None (default), no embedding
            generation occurs and turns go directly to storage.
        capture_profile: Resource profile string passed to Turn for
            provenance tracking.
    """

    def __init__(
        self,
        config: CaptureConfig,
        storage: StorageManager,
        embedding: EmbeddingBackend | None = None,
        capture_profile: str = "standard",
    ) -> None: ...

    async def start(self) -> None:
        """Start the background drain task.

        Idempotent if already started.
        """

    async def capture(
        self,
        session_id: str,
        turn_data: TurnData,
    ) -> CaptureResult:
        """Capture a single agent turn.

        Enqueues the turn for async persistence. Returns immediately
        with the trace_id (non-blocking with respect to storage).

        BACK-PRESSURE: If the internal queue is full, this method will
        suspend until space is available. The caller (agent) is blocked,
        not the agent's other work.

        Args:
            session_id: REQUIRED. Groups turns into a logical conversation.
                Must be non-empty. Upstream issues with session tracking
                should be fixed at the source, not normalized here.
            turn_data: Validated TurnData input.

        Returns:
            CaptureResult with the trace_id.

        Raises:
            CaptureError: If capture is disabled, not started, or session_id
                is empty/whitespace.
        """

    async def shutdown(self, timeout_seconds: float = 30.0) -> None:
        """Graceful shutdown.

        Stops accepting new turns, drains the queue fully, flushes
        any pending embeddings, and cancels the drain task.

        Args:
            timeout_seconds: Maximum seconds to wait for drain to complete.
                After this, the task is cancelled and remaining turns may
                be lost.
        """

    def status(self) -> CaptureStatus:
        """Current queue depth, worker state, health."""
        ...

    @property
    def total_captured(self) -> int: ...
```

### Supporting Types

```python
@dataclass(frozen=True)
class CaptureStatus:
    """Snapshot of capture pipeline health."""
    queue_depth: int
    queue_max: int
    is_started: bool
    is_draining: bool
    total_captured: int
    total_queued: int
    total_written: int
    embedding_pending: int
    embedding_enabled: bool
    healthy: bool
```

### CLI

```bash
# No direct CLI commands. Managed via `orthrus capture` in CLI module.
```

---

## Dependencies

- **config**: `CaptureConfig` for queue size and flush interval
- **storage**: `StorageManager` for persistence
- **embedding**: `EmbeddingBackend` protocol (optional)
- **capture.turn**: `Turn`, `ToolCall`, `generate_uuid7()`
- **stdlib**: `asyncio`, `queue` (for asyncio.Queue only)

---

## Resource Contract

| Profile | Queue Size | Memory | Capture Latency Target |
|---------|------------|--------|------------------------|
| minimal | 10 turns | <50MB | <20ms |
| standard | 100 turns | <100MB | <10ms |
| performance | 1000 turns | <500MB | <5ms |

**Latency measurement:** `capture()` returns after the turn is enqueued, not after storage write. The enqueue step is `O(1)` amortized with `asyncio.Queue`. Storage write is async in the background.

---

## Error Handling

| Error | Response | Recovery |
|-------|----------|----------|
| Queue full | Caller suspends (back-pressure) | Operator monitors queue depth, scales drain |
| Storage write fail | Log error, retry 3x, then alert | Data stays in queue, next drain retries |
| Embedding fail | Return turn without embedding | Text search still works, vector search degrades |
| Session ID empty | Raise `CaptureError` immediately | Fix upstream agent/session tracking |
| Not started | Raise `CaptureError` | Call `start()` first |
| Storage unavailable at start | Log warning, queue fills but no writes | Agent continues, monitor alerts |

**On agent stall risk:** If `capture()` blocks for >5s, emit a structured log warning with queue depth. This gives operators a signal before the agent truly stalls.

---

## File Structure

```
src/orthrus/capture/
├── __init__.py          # Public exports
├── turn_data.py         # TurnData, CaptureResult, CaptureStatus, ToolCall dataclasses
├── turn.py              # Turn dataclass with immutable embedding, provenance
├── _uuid7.py            # UUID7 generation + timestamp extraction
├── _queue.py            # asyncio queue wrapper (internal)
├── _worker.py           # Background drain task (internal)
└── _manager.py          # CaptureManager (internal, imported by __init__)
```

## Implementation Notes

### Deviations from Original Spec

| Spec Item | Actual Implementation | Reason |
|-----------|-----------------------|--------|
| `turn.py` was "existing" | Built as part of this module | Pre-existing `Turn` did not meet frozen/dataclass-durability requirements |
| No `uuid7` module spec | `_uuid7.py` added | Needed monotonic UUID generation for trace IDs without external deps |
| `EmbeddingBackend.flush()` returns `int` | `flush()` returns `list[Turn]` | More useful — returns enriched turns for storage |
| `TurnData` had `as_dict()` method | Used `dataclasses.asdict()` instead | stdlib, no duplication |
| `asyncio.to_thread()` for storage writes | `asyncio.create_task()` per turn | Avoids thread pool saturation at high throughput |
| No resource envelope in `_worker.py` | CPU throttle + batch limits | Prevents embedding backend from overwhelming the event loop |

### Resource Envelopes

The drain worker enforces two resource limits:

1. **CPU throttle**: `time.sleep(0)` every N turns to yield the event loop
2. **Batch limits**: configurable `embedding_batch_size` and `embedding_batch_timeout` on `EmbeddingBackend`

### CaptureResult Bug Fix

`CaptureResult` was declared in `TYPE_CHECKING` block but used at runtime in `_manager.py:273`. Fixed by moving the import to module level.

---

## Testing Strategy

- **Unit**: `TurnData` validation, queue back-pressure behavior, status dataclass
- **Integration**: `CaptureManager` with mock `StorageManager` and mock `EmbeddingBackend`
- **Property**: All captured turns are valid `Turn` schema; no data loss on shutdown drain
- **Async correctness**: Tests use `pytest-asyncio` with mode=auto

### Test Fixtures

```python
# TurnData construction
turn_data = TurnData(
    query_text="What is the capital of France?",
    context_hash="a" * 64,
    available_tools=("web_search", "file_read"),
    tool_calls=(ToolCall(...),),
    outcome=TurnOutcome.SUCCESS,
)

# Mock embedding backend
class MockEmbeddingBackend:
    dimensions = 384
    async def submit(self, turn): return turn
    async def flush(self): return 0
```
