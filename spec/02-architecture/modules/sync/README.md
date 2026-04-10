# Module: sync

---
status: implemented
priority: P2
---

## Responsibility

Optional remote synchronization of captured data.

**In scope:**
- Local directory sync (external drive, NAS)
- rsync/SSH sync
- S3-compatible sync (AWS, MinIO, Wasabi)
- Encryption at rest (age)
- Compression for transfer

**Out of scope:**
- Real-time collaboration
- Conflict resolution (last-write-wins)
- Cloud-native features (CDN, global replication)

## Interface

### Public API

```python
from orthrus.sync import SyncManager, SyncTarget, SyncConfig

class SyncTarget(Protocol):
    """Pluggable sync target."""
    
    def push(self, local_path: Path, remote_path: str) -> bool: ...
    def pull(self, remote_path: str, local_path: Path) -> bool: ...
    def verify(self, remote_path: str) -> bool: ...

class SyncConfig:
    """Sync configuration."""
    enabled: bool = False
    targets: List[SyncTarget]
    schedule: Literal["manual", "hourly", "daily"]
    encrypt: bool = False
    compression: Literal["none", "zstd", "lz4"] = "zstd"

class SyncManager:
    """Manages sync operations."""
    
    def __init__(self, config: SyncConfig) -> None: ...
    
    def sync(self, dry_run: bool = False) -> SyncResult:
        """Execute sync to all configured targets."""
        ...
    
    def schedule_sync(self) -> None:
        """Setup cron or background thread for scheduled sync."""
        ...

class LocalTarget(SyncTarget): ...
class RsyncTarget(SyncTarget): ...
class S3Target(SyncTarget): ...

class SyncResult:
    success: bool
    bytes_transferred: int
    files_transferred: int
    errors: List[str]
```

### CLI

```bash
orthrus sync --dry-run
orthrus sync --target s3
orthrus sync --encrypt --compression zstd
```

## Dependencies

- **storage**: Read files to sync
- **config**: Sync targets and credentials
- **external**: boto3 (S3), paramiko (SFTP), pyage (encryption)

## Resource Contract

- Sync is background operation
- Respects bandwidth limits (configurable)
- Resumable on failure

## Error Handling

| Error | Response |
|-------|----------|
| Network fail | Retry with exponential backoff, max 24h |
| Auth fail | Alert user, stop retrying |
| Target full | Alert user, stop sync |

## Testing

- Unit: Target protocol compliance
- Integration: Mock S3/minio sync
- Property: Interrupted sync is resumable
