# Module: export

---
status: not-started
priority: P1
---

## Responsibility

Export captured data to training formats (ShareGPT, DPO, raw).

**In scope:**
- ShareGPT format export
- DPO preference pair extraction
- Quality scoring and filtering
- Dataset deduplication
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

class ExportConfig:
    """Export configuration."""
    format: ExportFormat
    min_quality_score: float = 0.0
    deduplicate: bool = True
    dedup_threshold: float = 0.95  # Embedding similarity

class Exporter:
    """Export captured data to training formats."""
    
    def __init__(self, storage: StorageManager, config: ExportConfig) -> None: ...
    
    def export(
        self,
        output_path: Path,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> ExportResult:
        """
        Export data to file.
        Returns statistics about exported records.
        """
        ...
    
    def compute_quality(self, turn_id: str) -> float:
        """Compute quality score for a single turn."""
        ...

class ExportResult:
    records_total: int
    records_exported: int
    records_filtered: int
    quality_distribution: Dict[str, int]  # binned scores
```

### CLI

```bash
orthrus export --format sharegpt --output train.jsonl
orthrus export --format dpo --min-quality 0.8 --since 2026-01-01
```

## Dependencies

- **storage**: Read turns from Parquet
- **search**: Optional, for deduplication
- **embedding**: For deduplication (compute similarity)

## Resource Contract

- Streaming export: Memory O(1) regardless of dataset size
- Quality scoring: May require loading model (CPU/GPU)
- Deduplication: Requires embeddings

## Error Handling

| Error | Response |
|-------|----------|
| No data in range | Empty export, log warning |
| Write permission denied | Raise immediately |
| Quality model fail | Export without quality scores |

## Testing

- Unit: Format validation (load exported in standard tools)
- Integration: Export round-trip (capture → export → validate)
- Property: Streaming doesn't load entire dataset
