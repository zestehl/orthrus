# Module: storage

---
status: not-started
priority: P0
---

## Responsibility

Durable persistence of turn data in Parquet and JSONL formats. Time-partitioned storage with automatic rotation.

**In scope:**
- Parquet file writing (append, schema evolution)
- JSONL file writing (streaming)
- Directory structure management (time-partitioned)
- Rotation (hot → warm → archive)
- Compression (zstd levels)
- Integrity verification (hashes)

**Out of scope:**
- Search (handled by search module)
- Remote sync (handled by sync module)
- Encryption at rest (handled by sync module for remote)

## Interface

### Public API

```python
from orthrus.storage import StorageManager, TurnRecord

class StorageManager:
    """Manages persistent storage."""
    
    def __init__(self, config: StorageConfig) -> None: ...
    
    def write_turn(self, turn: TurnRecord) -> Path:
        """
        Write turn to appropriate Parquet and JSONL files.
        Returns path to written file.
        """
        ...
    
    def rotate(self) -> RotationResult:
        """
        Execute rotation policy. Move hot→warm→archive.
        Returns summary of actions taken.
        """
        ...
    
    def get_hot_files(self, since: Optional[datetime] = None) -> List[Path]:
        """List hot storage files, optionally filtered by time."""
        ...
    
    def verify_integrity(self, file: Path) -> bool:
        """Verify file checksum against manifest."""
        ...
```

## Dependencies

- **config**: Storage paths, rotation policy, compression levels
- **external**: pyarrow (Parquet), zstd (compression)

## Resource Contract

- **Memory**: Bounded by row group size (default 1000 rows)
- **CPU**: I/O bound, uses pyarrow's optimized writers
- **Storage**: Append-only, never modifies existing files

## Error Handling

| Error | Response |
|-------|----------|
| Disk full | Stop writes, alert, preserve existing data |
| Corrupt file | Log error, skip file, continue with others |
| Permission denied | Alert user, continue in-memory (bounded) |

## Testing

- Unit: Parquet round-trip, compression ratios
- Integration: Rotation with large datasets
- Property: All writes are durable (fsync verified)
