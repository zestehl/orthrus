# Orthrus Python API Specification

---
status: approved
author: zestehl
date: 2026-04-10
parent: spec/INDEX.md
related: spec/04-apis/cli-spec.md
---

## Table of Contents
1. [Overview](#1-overview)
2. [Package Structure](#2-package-structure)
3. [Module: orthrus.capture](#3-module-orthruscapture)
4. [Module: orthrus.config](#4-module-orthrusconfig)
5. [Module: orthrus.storage](#5-module-orthrusstorage)
6. [Module: orthrus.export](#6-module-orthrusexport)
7. [Module: orthrus.search](#7-module-orthrussearch)
8. [Module: orthrus.sync](#8-module-orthrussync)
9. [Module: orthrus.embedding](#9-module-orthrusembedding)

---

## 1. Overview

This document specifies the public Python API for Orthrus v0.1.0. All public symbols are exported from each module's `__init__.py` and are listed in the module's `__all__`. Anything not in `__all__` is considered private and subject to change.

### 1.1 Design Principles

- **Immutable by default:** Configuration objects are frozen dataclasses. `StoragePaths` uses `frozen=True`.
- **Async primary:** The `CaptureManager`, `EmbeddingWorker`, `Exporter`, and `SearchManager` use `asyncio` for concurrent operations.
- **Error hierarchy:** Each module defines an error hierarchy rooted at a base exception type.
- **No runtime dependency on external services:** All storage is local-first. Remote targets (S3, rsync) are opt-in.

### 1.2 Type Annotations

All public functions use standard library type annotations. No stubs needed.

### 1.3 Dependencies

Public API modules depend only on:
- Python 3.12 standard library
- `structlog` for structured logging
- `pyarrow` for Parquet I/O
- `pydantic` for config models
- Module-specific optional dependencies (e.g., `zstandard`, `boto3`)

---

## 2. Package Structure

```python
import orthrus.capture  # Capture pipeline
import orthrus.config   # Config models and loading
import orthrus.storage # Storage management and rotation
import orthrus.export  # Training data export
import orthrus.search  # Search management
import orthrus.sync   # Remote synchronization
import orthrus.embedding  # Embedding backends and workers
```

Top-level `import orthrus` does **not** re-export submodules (private).

---

## 3. Module: `orthrus.capture`

**Purpose:** Capture agent turns with async queue and optional background embedding.

**Public API:**

```python
from orthrus.capture import (
    CaptureManager,   # Async capture pipeline
    CaptureConfig,    # Pydantic config model
    CaptureStatus,    # Status snapshot (frozen dataclass)
    CaptureResult,     # Result of a single capture operation
    CaptureError,      # Base exception
    CaptureNotStartedError,
    CaptureDisabledError,
    TurnData,          # Turn data carrier (dataclass)
    Turn,              # Core turn data model
    ToolCall,          # Tool call model
    TurnOutcome,       # Turn outcome model
    EmbeddingBackend,  # Protocol (from orthrus.embedding)
)
```

### 3.1 `CaptureManager`

```python
class CaptureManager:
    def __init__(
        self,
        config: CaptureConfig,
        storage: StorageManager,
        embedding: EmbeddingWorker | None,
        capture_profile: str,
        resource_profile: ResourceProfile,
    ) -> None: ...

    async def start() -> None: ...
    async def capture(turn_data: TurnData) -> CaptureResult: ...
    def status() -> CaptureStatus: ...
    async def shutdown() -> None: ...
```

### 3.2 `TurnData`

```python
@dataclass
class TurnData:
    session_id: str
    turn: Turn
    outcome: TurnOutcome
    embedding_text: str | None = None
```

### 3.3 `CaptureStatus`

```python
@dataclass(frozen=True)
class CaptureStatus:
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

---

## 4. Module: `orthrus.config`

**Purpose:** Configuration models, loading, and path resolution.

**Public API:**

```python
from orthrus.config import (
    Config,              # Root config (frozen Pydantic model)
    CaptureConfig,       # Capture section
    StorageConfig,       # Storage section
    EmbeddingConfig,     # Embedding section
    SearchConfig,        # Search section
    SyncConfig,         # Sync section
    SyncTarget,         # Individual sync target (Protocol or model)
    ResourceProfile,    # Enum: minimal, standard, performance
    load_config,        # Function: load from YAML path
    ConfigFileNotFoundError,
    orthrus_dirs,        # Function: resolve orthrus directories
    default_config_path,  # Path to default config
    default_config_search_paths,  # Search paths list
)
```

### 4.1 `Config` (frozen Pydantic model)

```
Config.model_fields:
  capture: CaptureConfig
  storage: StorageConfig
  embedding: EmbeddingConfig
  search: SearchConfig
  sync: SyncConfig
  profile: ResourceProfile
  paths: dict[str, str]
  storage_paths: StoragePaths  # resolved, not raw dict

Config.default() -> Config  # class method
load_config(path: Path | None = None) -> Config
```

### 4.2 `ResourceProfile`

```python
class ResourceProfile(str, Enum):
    minimal = "minimal"
    standard = "standard"
    performance = "performance"
```

### 4.3 `SyncConfig`

```python
@dataclass
class SyncConfig:
    enabled: bool
    targets: dict[str, dict]  # name -> target config dict
```

### 4.4 `SyncTarget` Protocol

```python
class SyncTarget(Protocol):
    """Plugable sync target."""

    def push(self, hot: Path, warm: Path, manifest: Manifest) -> SyncResult: ...
    def pull(self, hot: Path, warm: Path, manifest: Manifest) -> SyncResult: ...
    def verify(self) -> bool: ...
    def bytes_for_paths(self, paths: list[Path]) -> int: ...
    def target_name(self) -> str: ...
```

---

## 5. Module: `orthrus.storage`

**Purpose:** Durable storage of captured turns in Parquet/JSONL with rotation.

**Public API:**

```python
from orthrus.storage import (
    StorageManager,        # Main storage orchestrator
    TurnRecord,           # Dataclass: single turn record
    StoragePaths,         # Frozen dataclass: path resolver
    StorageError,         # Base exception
    DiskFullError,        # Raised on disk exhaustion
    RotationResult,       # Result of a rotation operation
    FileRotation,         # Rotation policy class
    rotate,               # Standalone rotation function
    Manifest,            # Manifest model
    FileEntry,           # File entry model
    write_manifest,       # Write manifest to YAML
    read_manifest,        # Read manifest from YAML
    build_manifest,       # Build manifest from directory
    build_file_entry,     # Build single file entry
    verify_file,          # Verify single file integrity
    verify_manifest_integrity,  # Verify all files in manifest
    ParquetWriter,        # Parquet batch writer
    TURN_SCHEMA,          # PyArrow schema for turn records
    turn_to_record,       # Convert TurnData -> TurnRecord
    read_turns,          # Read turns from Parquet files
    parquet_file_stats,  # Stats for a parquet file
    JSONLWriter,         # JSONL batch writer
    turn_to_jsonl_record, # Convert TurnData -> dict
    read_jsonl,          # Read turns from JSONL files
    jsonl_file_stats,    # Stats for a JSONL file
)
```

### 5.1 `StorageManager`

```python
class StorageManager:
    def __init__(self, config: StorageConfig, paths: StoragePaths) -> None: ...

    async def write(self, turn_data: TurnData) -> TurnRecord: ...
    async def read_turns(self, since: datetime | None = None, until: datetime | None = None, session_filter: str | None = None) -> list[TurnRecord]: ...
    async def rotate() -> RotationResult: ...
    def paths() -> StoragePaths: ...
```

### 5.2 `StoragePaths` (frozen dataclass)

```python
@dataclass(frozen=True)
class StoragePaths:
    capture: Path       # Hot storage root
    warm: Path         # Warm storage root
    archive: Path      # Archive root
    manifest: Path     # Manifest file path

    def resolve() -> StoragePaths: ...  # class method, from config or defaults
```

### 5.3 `Manifest`

```python
class Manifest(TypedDict):
    version: str
    created: datetime
    updated: datetime
    files: dict[str, FileEntry]
```

### 5.4 `FileEntry`

```python
class FileEntry(TypedDict):
    path: str
    size_bytes: int
    compressed_size_bytes: int
    hash: str  # xxHash64
    created: datetime
    metadata: dict[str, Any]
```

---

## 6. Module: `orthrus.export`

**Purpose:** Export captured turns to training formats (ShareGPT, DPO, Raw).

**Public API:**

```python
from orthrus.export import (
    Exporter,          # Main export orchestrator
    ExportConfig,     # Configuration
    ExportResult,     # Result of an export operation
    ExportError,      # Base exception
    ExportFormat,    # Enum: SHAREGPT, DPO, RAW
)
```

### 6.1 `ExportConfig`

```python
@dataclass
class ExportConfig:
    format: ExportFormat = ExportFormat.SHAREGPT
    min_quality: float = 0.0
    since: datetime | None = None
    until: datetime | None = None
    session_filter: str | None = None
```

### 6.2 `ExportResult`

```python
@dataclass(frozen=True)
class ExportResult:
    format: ExportFormat
    file_path: Path
    turns_exported: int
    turns_evaluated: int
    bytes_written: int
    duration_ms: int
    success: bool
    error: str | None = None
```

### 6.3 `Exporter`

```python
class Exporter:
    def __init__(self, config: ExportConfig, storage: StorageManager) -> None: ...

    async def export(self, output: Path) -> ExportResult: ...
    async def count(self) -> int: ...  # Count matching turns
```

---

## 7. Module: `orthrus.search`

**Purpose:** Text and vector search over captured turns.

**Public API:**

```python
from orthrus.search import (
    SearchManager,    # Main search orchestrator
    SearchQuery,      # Query model
    SearchResult,     # Result model
    SearchError,      # Base exception
    SEARCHABLE_FIELDS, # tuple[str, ...] of searchable field names
)
```

### 7.1 `SearchQuery`

```python
@dataclass
class SearchQuery:
    text: str                    # Text query
    vector: list[float] | None = None  # Pre-computed vector embedding
    top_k: int = 10
    session_filter: str | None = None
    threshold: float | None = None
```

### 7.2 `SearchResult`

```python
@dataclass
class SearchResult:
    turn: TurnRecord
    score: float
    highlights: list[str]
```

---

## 8. Module: `orthrus.sync`

**Purpose:** Remote synchronization of captured data to local dirs, rsync/SSH, or S3-compatible storage.

**Public API:**

```python
from orthrus.sync import (
    SyncManager,   # Main sync orchestrator
    SyncResult,    # Result of a sync operation
)
```

### 8.1 `SyncResult`

```python
@dataclass(frozen=True)
class SyncResult:
    target_name: str
    success: bool
    files_transferred: int
    bytes_transferred: int
    duration_ms: int
    error: str | None = None
```

### 8.2 `SyncManager`

```python
class SyncManager:
    def __init__(
        self,
        targets: list[SyncTarget],
        storage_paths: StoragePaths,
        dry_run: bool = False,
    ) -> None: ...

    def sync(self, target_name: str | None = None) -> list[SyncResult]: ...
```

---

## 9. Module: `orthrus.embedding`

**Purpose:** Asynchronous text embedding with pluggable backends.

**Public API:**

```python
from orthrus.embedding import (
    EmbeddingBackend,       # Protocol
    EmbeddingWorker,       # Async worker
    EmbeddingConfig,       # Pydantic config model
    TransformersBackend,   # Transformers + sentence-transformers
    OnnxBackend,           # ONNX Runtime (int8 quantized)
    MLXBackend,            # Apple Silicon MLX
)
```

### 9.1 `EmbeddingBackend` Protocol

```python
class EmbeddingBackend(Protocol):
    def encode(self, texts: list[str]) -> list[list[float]]: ...
    def batch_size(self) -> int: ...
    def dimensions(self) -> int: ...
```

### 9.2 `EmbeddingWorker`

```python
class EmbeddingWorker:
    def __init__(self, backend: EmbeddingBackend, config: EmbeddingConfig) -> None: ...

    def submit(self, text: str, turn_id: str) -> asyncio.Future[list[float]]: ...
    async def shutdown() -> None: ...
```

### 9.3 Backend Reference

| Backend | Model | Quantization | Platform |
|---------|-------|-------------|----------|
| `TransformersBackend` | `all-MiniLM-L6-v2` (default) | fp32 | CPU/GPU |
| `OnnxBackend` | HuggingFace model ID | int8 | CPU/CoreML |
| `MLXBackend` | Pre-exported MLX directory | fp16 | Apple Silicon GPU |

---

## Related Documents

- [CLI Specification](spec/04-apis/cli-spec.md) — Operator CLI interface
- [Config Schema](spec/04-apis/config-schema.md) — YAML config field definitions
- [Capture Module Spec](spec/02-architecture/modules/capture/README.md) — capture pipeline internals
- [Export Module Spec](spec/02-architecture/modules/export/README.md) — export format details
- [Storage Module Spec](spec/02-architecture/modules/storage/README.md) — storage format details
- [Search Module Spec](spec/02-architecture/modules/search/README.md) — search internals
- [Sync Module Spec](spec/02-architecture/modules/sync/README.md) — sync target internals
- [Embedding Module Spec](spec/02-architecture/modules/embedding/README.md) — embedding backends
