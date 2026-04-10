# Module: export

---
status: implemented
priority: P1
implemented: 2026-04-10
tested: 63/63 tests passing
---

## Responsibility

Export captured data to training formats (ShareGPT, DPO, raw).

**In scope:**
- ShareGPT format export
- DPO preference pair extraction
- Quality scoring and filtering
- Dataset deduplication (embedding-based)
- Streaming export (large datasets)

**Out of scope:**
- Model training or fine-tuning
- Dataset hosting (HF Hub upload is CLI wrapper)

## Interface

### Public API

```python
from orthrus.export import Exporter, ExportConfig, ExportFormat

class ExportFormat(Enum):
    SHAREGPT = "sharegpt"
    DPO = "dpo"
    RAW = "raw"

@dataclass(frozen=True)
class ExportConfig:
    """Export configuration."""
    format: ExportFormat = ExportFormat.SHAREGPT
    min_quality_score: float = 0.0
    deduplicate: bool = True
    dedup_threshold: float = 0.95  # Cosine similarity
    include_fields: tuple[str, ...] = ()  # Empty = all fields

@dataclass(frozen=True)
class ExportResult:
    """Result of an export run."""
    records_total: int = 0
    records_exported: int = 0
    records_filtered: int = 0
    records_duplicates: int = 0
    quality_distribution: dict[str, int] = field(default_factory=dict)
    format: str = ""
    output_path: str = ""
    error: str | None = None

    @property
    def success(self) -> bool: ...

class Exporter:
    """Export captured data to training formats."""

    def __init__(
        self,
        storage: StorageManager,
        config: ExportConfig,
        config_root: Config | None = None,
    ) -> None: ...

    def export(
        self,
        output_path: Path,
        since: datetime | None = None,
        until: datetime | None = None,
        session_id: str | None = None,
    ) -> ExportResult:
        """
        Export data to JSONL file.
        Returns statistics about exported records.
        Memory: O(1) — streams one Parquet file at a time.
        """
        ...

    def compute_quality(self, turn: Turn) -> float:
        """Compute quality score for a single Turn (heuristic scorer)."""
        ...
```

### Formatters

```python
class ExportFormatter(Protocol):
    """Export format handler protocol."""
    def format(self, turn: Turn) -> dict | None: ...
    def can_format(self, turn: Turn) -> bool: ...

# Implementations:
ShareGPTFormatter  # conversations array, system/human/gpt roles
DPOFormatter       # prompt/chosen/rejected for preference training
RawFormatter       # Full Turn dict passthrough
```

### CLI

```bash
orthrus export --format sharegpt --output train.jsonl
orthrus export --format dpo --min-quality 0.8 --since 2026-01-01
orthrus export --format raw --output raw.jsonl --deduplicate
```

## Quality Scoring (Heuristic)

| Factor | Score Delta |
|--------|-------------|
| Base | +0.5 |
| Response present | +0.2 |
| Outcome SUCCESS | +0.1 |
| Outcome ERROR/TIMEOUT/PARTIAL | -0.1 |
| Reasoning content | +0.05 |
| All tool calls successful | +0.1 |
| Any tool call failed | -0.1 |
| user_rating set | overrides all (clamped to [0,1]) |

Final score clamped to [0.0, 1.0]. Production path substitutes a trained model.

## Dependencies

- **storage**: Read turns from Parquet via `StorageManager`
- **embedding**: Optional, for deduplication
- **config**: Optional Config root for embedding backend resolution

## Resource Contract

- Streaming export: Memory O(1) — one Parquet file buffered at a time
- Dedup cache: Bounded to 10,000 entries max
- Quality scoring: Pure Python heuristic, no model loading

## Error Handling

| Error | Response |
|-------|----------|
| No data in range | Empty export, log warning, returns ExportResult with 0s |
| Write permission denied | Returns ExportResult with error field set |
| Storage read failure | Skips file, logs warning, continues |
| Turn reconstruction failure | Filters out bad record, continues |
| Malformed export | Filters out, continues |

## Testing

- Unit: Format validation (load exported in standard tools)
- Unit: Quality scoring edge cases (float precision via pytest.approx)
- Integration: Export round-trip (capture → export → validate)
- Property: Streaming doesn't load entire dataset
- Dedup: cosine similarity cache correctness
