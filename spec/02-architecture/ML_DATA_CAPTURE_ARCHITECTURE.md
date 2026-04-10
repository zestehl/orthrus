# Orthrus ML Data Capture Architecture
## Durable, Fast, Lightweight — Hardware-Agnostic Design

**Version:** 0.1.0  
**Date:** 2026-04-09  
**Status:** Design Document  

---

## 1. Design Principles

### 1.1 Durability Over Performance
- **Formats outlive software**: Parquet, JSONL, SQLite will be readable in 2035
- **Source of truth is immutable**: Raw captures never modified, only rotated
- **Reversible transformations**: Every derived dataset can be regenerated from raw
- **No vendor lock-in**: No proprietary formats or cloud-dependent APIs

### 1.2 Resource Adaption
- **Memory-bounded by configuration**: User specifies limits, software adapts
- **Graceful degradation**: Features disable automatically under pressure
- **No hard requirements**: Works on 2GB RAM or 64GB, single-core or GPU cluster

### 1.3 Zero Configuration Defaults
- **Sensible defaults for capture**: Works immediately without tuning
- **Opt-in complexity**: Advanced features require explicit configuration
- **Clear resource contracts**: User understands cost of each feature

---

## 2. Resource Profiles

Software adapts to declared resource class, not detected hardware:

### Profile: `minimal`
**Target:** 2GB RAM, slow storage, no GPU  
**Use case:** Embedded agents, edge devices, containers with limits

| Feature | Behavior |
|---------|----------|
| Embeddings | Disabled (text search only) |
| Index | None (brute force if any) |
| Compression | zstd level 9 (storage over CPU) |
| Rotation | Aggressive (keep only 7 days hot) |
| Sync | Manual only |
| Queue | Max 10 turns in memory |

### Profile: `standard` (default)
**Target:** 4-8GB RAM, SSD, optional GPU  
**Use case:** Developer workstations, laptops, cloud instances

| Feature | Behavior |
|---------|----------|
| Embeddings | CPU with quantized model (ONNX int8) |
| Index | Annoy on demand (rebuildable) |
| Compression | zstd level 3 (balanced) |
| Rotation | 30 days hot, 90 days warm |
| Sync | Configurable schedule |
| Queue | Max 100 turns in memory |

### Profile: `performance`
**Target:** 16GB+ RAM, fast NVMe, GPU available  
**Use case:** ML workstations, training nodes, high-throughput agents

| Feature | Behavior |
|---------|----------|
| Embeddings | GPU batch inference (CUDA/Metal) |
| Index | FAISS HNSW persistent + Annoy |
| Compression | lz4 (speed over ratio) |
| Rotation | 90 days hot, 1 year warm |
| Sync | Real-time streaming |
| Queue | Max 1000 turns, background workers |

---

## 3. Storage Architecture

### 3.1 Data Layout (Time-Partitioned)

```
~/.orthrus/
├── config.yaml              # User configuration + resource profile
├── capture/                 # Current, uncompressed, hot data
│   └── 2026/
│       └── 04/
│           └── 09/
│               ├── session-uuid7-turns.parquet
│               ├── session-uuid7-trajectories.jsonl
│               └── session-uuid7-manifest.json
├── warm/                    # Compressed, less frequently accessed
│   └── 2026/
│       └── 03/
├── archive/                 # Highly compressed, immutable
│   └── 2026/
│       └── Q1/
└── derived/                 # Computed data (rebuildable)
    ├── indices/             # Annoy, FAISS (disposable)
    ├── embeddings/          # Pre-computed embedding cache
    └── exports/             # Training datasets (ShareGPT, DPO)
```

### 3.2 Rotation Policy (Configurable)

| Tier | Trigger | Compression | Default Retention |
|------|---------|-------------|-------------------|
| Hot (`capture/`) | Active use | None | 7 days (minimal), 30 days (standard), 90 days (performance) |
| Warm (`warm/`) | Daily cron | zstd:3 | 30 days (minimal), 90 days (standard), 365 days (performance) |
| Archive (`archive/`) | Monthly cron | zstd:19 | 90 days (minimal), 1 year (standard), forever (performance) |

### 3.3 Size Budget (Per Agent Instance)

| Profile | Daily | Monthly | Yearly |
|---------|-------|---------|--------|
| minimal | 10MB | 300MB | 3.6GB |
| standard | 50MB | 1.5GB | 18GB |
| performance | 200MB | 6GB | 72GB |

---

## 4. Capture Pipeline

### 4.1 Pipeline Stages

```
Agent Turn
    ↓
Capture (synchronous, <10ms) → UUID assignment, timestamp
    ↓
Ingest Queue (async, bounded) → Memory-safe buffering
    ↓
Embedding Worker (async, optional) → Vector generation
    ↓
Parquet Writer (async, batched) → Columnar storage
    ↓
JSONL Writer (async, streaming) → Training format
    ↓
Rotation Worker (scheduled) → Tier movement
    ↓
Sync Worker (configurable) → Remote durability
```

### 4.2 The Turn Schema (Minimal, Extensible)

```python
@dataclass
class AgentTurn:
    # Identification
    trace_id: str              # UUID7 (time-sortable)
    session_id: str            # Groups turns
    timestamp: datetime        # UTC
    
    # Input
    query_text: str
    query_embedding: Optional[List[float]] = None  # Lazy, nullable
    
    # Context (lightweight references)
    context_ref: str           # Hash of full context (stored separately)
    available_tools: List[str]
    
    # Execution
    tool_calls: List[Dict]     # Tool, args, duration, exit_code
    
    # Outcome
    success: bool
    duration_ms: int
    
    # Providence
    orthrus_version: str
    capture_schema_version: int = 1
```

### 4.3 Memory Safety

| Resource State | Action |
|----------------|--------|
| Queue > 50% capacity | Increase flush frequency |
| Queue > 90% capacity | Drop oldest unprocessed, log warning |
| Memory pressure detected | Pause embedding generation, write raw only |
| Disk < 10% free | Stop capture, alert user, preserve existing data |
| Disk < 5% free | Emergency rotation to archive, continue minimal capture |

---

## 5. Embedding Generation

### 5.1 Modular Embedding Backends

```python
class EmbeddingBackend(Protocol):
    def encode(self, texts: List[str]) -> List[List[float]]: ...
    def batch_size(self) -> int: ...
    def latency_ms(self) -> float: ...

# Implementations:
# - NoopBackend: Returns None (minimal profile)
# - OnnxBackend: CPU inference with quantized model (standard)
# - MlxBackend: Apple Silicon GPU (performance on Mac)
# - TransformersBackend: HuggingFace with device auto-detection
```

### 5.2 Lazy Generation

Embedding generation is **asynchronous and optional**:

1. Turn captured with `query_embedding=None`
2. Query text searchable via text indexing (if enabled)
3. Embedding worker processes in background when resources available
4. Completed embeddings written to separate column in Parquet

This allows capture to proceed even if embedding generation fails or is slow.

### 5.3 Model Selection (User-Configurable)

| Profile | Default Model | Dimensions | Size |
|---------|---------------|------------|------|
| minimal | None | N/A | N/A |
| standard | all-MiniLM-L6-v2 | 384 | 22MB |
| performance | E5-large-v2 | 1024 | 1.2GB |

---

## 6. Search and Retrieval

### 6.1 Search Modes

| Mode | Implementation | When to Use |
|------|----------------|-------------|
| `text` | Full-text on query_text | No embeddings, fast enough |
| `vector` | Brute-force cosine from Parquet | <100K records, exact results |
| `index` | Annoy/FAISS approximation | >100K records, speed critical |
| `hybrid` | Text + vector reranking | Best relevance |

### 6.2 Index as Performance Layer

Indices are **disposable optimizations**, not required:

```python
class SearchManager:
    def search(self, query: str, mode: str = "auto") -> List[Result]:
        if mode == "auto":
            mode = self._select_mode(query)
        
        if mode == "text":
            return self._search_text(query)
        elif mode == "vector" and self._has_embeddings():
            if self._index_fresh():
                return self._search_index(query)
            else:
                return self._search_brute_force(query)
```

**Index lifecycle:**
- Built on demand (explicit user request or cron)
- Stored in `derived/indices/` with timestamp
- Manifest tracks which Parquet files are indexed
- Rebuilding from source is always possible

---

## 7. Durability and Sync

### 7.1 Local Durability

| Mechanism | Purpose |
|-----------|---------|
| Append-only writes | No corruption from crashes |
| Row group validation | Parquet footer checksums |
| Manifest files | JSON manifest per session with SHA-256 of files |
| Journal file | WAL for in-flight captures (<1s window) |

### 7.2 Remote Sync (Optional)

Sync is **optional and configurable**:

```yaml
# config.yaml
sync:
  enabled: false              # Default: local only
  targets:
    - type: rsync
      host: backup.example.com
      path: /backups/orthrus/
      schedule: hourly
      compression: zstd
    - type: s3
      bucket: my-datasets
      prefix: orthrus/
      credentials: env  # or ~/.aws/credentials
  retention:
    local_days: 30
    remote_days: 365
```

**Sync targets supported:**
- `local`: Another directory (external drive, network mount)
- `rsync`: SSH/remote server
- `s3`: S3-compatible (AWS, MinIO, Wasabi, etc.)
- `rclone`: Any rclone backend (Google Drive, B2, etc.)

### 7.3 Encryption

| Layer | Method | When |
|-------|--------|------|
| At-rest local | None (user filesystem handles this) | Default |
| At-rest local | age | Optional, user key |
| In-transit | TLS | All network sync |
| Remote storage | age or S3 SSE | User configured |

---

## 8. Training Export

### 8.1 Export Formats

| Format | Use Case | Schema |
|--------|----------|--------|
| ShareGPT | Supervised fine-tuning | conversations array |
| OpenAI | Function calling training | messages with tool_calls |
| DPO | Preference optimization | prompt/chosen/rejected |
| Raw Parquet | Custom processing | Full turn schema |

### 8.2 Dataset Quality Scoring

Each exported example includes quality metadata:

```json
{
  "conversations": [...],
  "quality_score": 0.92,
  "quality_factors": {
    "session_length": 0.9,
    "success_rate": 1.0,
    "user_rating": 0.8,
    "complexity": 0.95
  }
}
```

**Filtering at export:**
- Minimum quality threshold
- Exclude error turns (optional)
- Balance intents
- Deduplication by embedding similarity

---

## 9. Implementation Plan

### Phase 1: Core Capture (Weeks 1-2)
- `Turn` dataclass with validation
- Parquet writer with schema evolution
- JSONL writer with rotation
- Bounded ingest queue (asyncio)
- Configuration loader with profiles
- CLI: `orthrus capture --status`

### Phase 2: Embedding (Week 3)
- Embedding backend protocol
- ONNX backend (CPU, quantized)
- Async embedding worker
- Lazy embedding (nullable in schema)
- CLI: `orthrus embed --index`

### Phase 3: Search (Week 4)
- Text search ( DuckDB or brute force)
- Brute-force vector search
- Annoy index builder
- Index manifest tracking
- CLI: `orthrus search "query"`

### Phase 4: Rotation and Sync (Week 5)
- Rotation daemon (cron-based)
- Compression pipeline
- Sync manager (rsync, s3)
- Encryption (age)
- CLI: `orthrus sync --dry-run`

### Phase 5: Training Export (Week 6)
- ShareGPT exporter
- DPO pair extractor
- Quality scoring
- CLI: `orthrus export --format sharegpt --quality 0.9`

---

## 10. Dependencies

### Core (Required)
```toml
[project.dependencies]
"pyarrow==16.0.0"      # Parquet
"numpy==1.26.4"        # Arrays
"pydantic==2.11.5"     # Validation
"structlog==25.3.0"    # Structured logging
"platformdirs==4.2.0"  # XDG dirs (cross-platform)
```

### Optional Profiles
```toml
[project.optional-dependencies]
# Minimal: no extras needed

# Standard profile
standard = [
    "onnxruntime==1.17.1",      # CPU inference
    "tokenizers==0.15.2",       # Fast tokenization
    "annoy==1.17.3",            # Index
    "duckdb==0.10.0",           # Query engine
]

# Performance profile
performance = [
    "transformers==4.39.3",     # GPU inference
    "torch==2.2.2",             # Backend
    "faiss-cpu==1.7.4",         # HNSW index
    # Platform-specific GPU:
    # "faiss-gpu==1.7.4"        # CUDA (installed separately)
    # "mlx==0.13.0"             # Apple Silicon (installed separately)
]

# Sync targets
sync = [
    "boto3==1.34.0",            # S3
    "paramiko==3.4.0",          # SFTP (for rsync-over-ssh)
]

# Encryption
encryption = [
    "pyage==1.1.0",             # age encryption
]
```

---

## Appendix A: Configuration Schema

```yaml
# ~/.orthrus/config.yaml
version: 1

# Resource profile selection
profile: standard  # minimal, standard, performance

# Storage paths (defaults to XDG dirs)
paths:
  capture: ~/.local/share/orthrus/capture
  warm: ~/.cache/orthrus/warm
  archive: ~/.local/share/orthrus/archive
  derived: ~/.cache/orthrus/derived

# Capture settings
capture:
  enabled: true
  queue_max_size: 100      # Turns in memory
  flush_interval_seconds: 60
  embed_async: true       # Generate embeddings in background
  embed_on_capture: false   # Wait for embedding (slower)

# Rotation
rotation:
  hot_max_days: 30
  warm_max_days: 90
  archive_compression: zstd
  archive_level: 9

# Sync (disabled by default)
sync:
  enabled: false
  targets: []

# Search
search:
  default_mode: auto      # auto, text, vector, hybrid
  index_on_demand: true   # Build index if not present
  max_results: 100
```

---

## Appendix B: Parquet Schema (Version 1)

```python
import pyarrow as pa

TURN_SCHEMA_V1 = pa.schema([
    # Identification
    ("trace_id", pa.string()),
    ("session_id", pa.string()),
    ("timestamp", pa.timestamp("us", "UTC")),
    ("schema_version", pa.int8()),
    
    # Input
    ("query_text", pa.string()),
    ("query_embedding", pa.list_(pa.float32(), 384)),  # Nullable
    ("query_intent", pa.string()),  # Nullable
    
    # Context
    ("context_ref", pa.string()),     # Hash of full context
    ("available_tools", pa.list_(pa.string())),
    
    # Execution
    ("tool_calls_json", pa.binary()),   # Compressed JSON
    ("duration_ms", pa.int32()),
    ("success", pa.bool_()),
    ("error_class", pa.string()),       # Nullable
    
    # Providence
    ("orthrus_version", pa.string()),
    ("capture_profile", pa.string()),
])
```

---

## Appendix C: API Design Philosophy

**CLI as primary interface:**
```bash
# User workflows
orthrus status                    # Health, storage usage, capture rate
orthrus capture --enable          # Start capturing
orthrus search "failed to load"   # Find similar turns
orthrus export --format sharegpt  # Generate training data
orthrus sync --target s3          # Push to remote
```

**Python API for integration:**
```python
from orthrus import CaptureManager

capture = CaptureManager(profile="standard")
capture.start()

turn_id = capture.record_turn(
    query="move to directory",
    tool_calls=[{"tool": "terminal", "args": {"cmd": "cd ..."}}],
    success=True,
)

capture.shutdown()
```
