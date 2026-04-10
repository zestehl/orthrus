# Orthrus Config Schema

---
status: approved
author: zestehl
date: 2026-04-10
parent: spec/INDEX.md
related: spec/04-apis/cli-spec.md, spec/04-apis/python-api.md
---

## Table of Contents
1. [Overview](#1-overview)
2. [Config File Location](#2-config-file-location)
3. [Root Config](#3-root-config)
4. [CaptureConfig](#4-captureconfig)
5. [StorageConfig](#5-storageconfig)
6. [EmbeddingConfig](#6-embeddingconfig)
7. [SearchConfig](#7-searchconfig)
8. [SyncConfig](#8-syncconfig)
9. [SyncTarget](#9-synctarget)
10. [Example Config](#10-example-config)

---

## 1. Overview

Orthrus uses a single YAML configuration file. All config objects are Pydantic models with zero-config defaults — a config file only needs to specify values that differ from defaults.

The root `Config` object composes all sub-configs:

```python
from orthrus.config import Config, load_config
cfg = load_config(Path("~/.orthrus/config.yaml"))
```

---

## 2. Config File Location

Default search order (first found wins):

1. `~/.orthrus/config.yaml`
2. `~/.config/orthrus/config.yaml`
3. `./config.yaml` (current working directory)

The path can be overridden via `--config` CLI flag or `ORTHRUS_CONFIG` environment variable.

---

## 3. Root Config

```yaml
version: 1              # int, default: 1
profile: standard       # enum: minimal | standard | performance

capture: {...}          # CaptureConfig
storage: {...}          # StorageConfig
embedding: {...}       # EmbeddingConfig
search: {...}           # SearchConfig
sync: {...}             # SyncConfig

paths:                  # dict[str, str], optional overrides
  capture: /path/to/capture
  warm: /path/to/warm
  archive: /path/to/archive
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `version` | int | `1` | Config format version |
| `profile` | enum | `standard` | Resource profile |
| `capture` | object | (see below) | Capture pipeline settings |
| `storage` | object | (see below) | Storage and rotation settings |
| `embedding` | object | (see below) | Embedding generation settings |
| `search` | object | (see below) | Search and retrieval settings |
| `sync` | object | (see below) | Remote sync settings |
| `paths` | dict | derived | Optional path overrides |

---

## 4. CaptureConfig

```yaml
capture:
  enabled: true
  queue_max_size: 100
  flush_interval_seconds: 60
  embed_async: true
  embed_on_capture: false
```

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `enabled` | bool | `true` | — | Enable capture pipeline |
| `queue_max_size` | int | `100` | 1–10000 | Max turns in memory queue |
| `flush_interval_seconds` | int | `60` | 1–3600 | Interval between batch writes |
| `embed_async` | bool | `true` | — | Generate embeddings asynchronously |
| `embed_on_capture` | bool | `false` | — | Generate embeddings synchronously on capture |

### Profile Defaults

| Setting | minimal | standard | performance |
|---------|---------|----------|-------------|
| `queue_max_size` | 10 | 100 | 1000 |
| `flush_interval_seconds` | 30 | 60 | 120 |

---

## 5. StorageConfig

```yaml
storage:
  hot_max_days: 30
  warm_max_days: 90
  warm_compression: zstd
  warm_compression_level: 3
  archive_compression: zstd
  archive_compression_level: 9
  parquet_row_group_size: 1000
```

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `hot_max_days` | int | `30` | 1–365 | Days to keep data in hot storage |
| `warm_max_days` | int | `90` | 1–3650 | Days to keep data in warm storage |
| `warm_compression` | enum | `zstd` | `none`, `zstd`, `lz4` | Compression for warm storage rotation |
| `warm_compression_level` | int | `3` | 1–22 | Compression level (higher = more CPU) |
| `archive_compression` | enum | `zstd` | `none`, `zstd`, `lz4` | Compression for archive rotation |
| `archive_compression_level` | int | `9` | 1–22 | Compression level (9 = maximum) |
| `parquet_row_group_size` | int | `1000` | 100–100000 | Rows per Parquet row group |

### Profile Defaults

| Setting | minimal | standard | performance |
|---------|---------|----------|-------------|
| `hot_max_days` | 7 | 30 | 90 |
| `warm_max_days` | 30 | 90 | 365 |
| `warm_compression` | zstd (level 9) | zstd (level 3) | lz4 |
| `archive_compression` | zstd (level 22) | zstd (level 9) | zstd (level 9) |

---

## 6. EmbeddingConfig

```yaml
embedding:
  enabled: true
  model: null
  batch_size: 32
  device: auto
  dimensions: 384
```

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `enabled` | bool | `true` | — | Enable embedding generation |
| `model` | str | `null` | HuggingFace model ID | Override default model |
| `batch_size` | int | `32` | 1–256 | Batch size for inference |
| `device` | enum | `auto` | `auto`, `cpu`, `cuda`, `metal` | Compute device |
| `dimensions` | int | `384` | 64–4096 | Embedding vector dimensions |

### Default Model

When `model: null`, uses `all-MiniLM-L6-v2` (384 dimensions, 22M parameters, MTEB 56.53).

### Backend Selection

| Profile | Backend | Quantization |
|---------|---------|--------------|
| minimal | None | — |
| standard | TransformersBackend | fp32 |
| performance | OnnxBackend | int8 |
| Apple Silicon | MLXBackend | fp16 |

---

## 7. SearchConfig

```yaml
search:
  default_mode: auto
  index_on_demand: true
  max_results: 100
  text_score_threshold: 0.1
  hybrid_rerank_top_k: 20
```

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `default_mode` | enum | `auto` | `auto`, `text`, `vector`, `hybrid` | Default search mode |
| `index_on_demand` | bool | `true` | — | Build index only when search is called |
| `max_results` | int | `100` | 1–10000 | Maximum results per query |
| `text_score_threshold` | float | `0.1` | 0.0–1.0 | Minimum text search relevance score |
| `hybrid_rerank_top_k` | int | `20` | 1–200 | Top-K for hybrid search reranking |

---

## 8. SyncConfig

```yaml
sync:
  enabled: false
  targets: []
  local_retention_days: 30
  remote_retention_days: 365
```

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `enabled` | bool | `false` | — | Enable remote sync |
| `targets` | array | `[]` | — | List of sync targets |
| `local_retention_days` | int | `30` | 1–3650 | Days to keep data locally after sync |
| `remote_retention_days` | int | `365` | 1–36500 | Days to keep data on remote |

---

## 9. SyncTarget

A single sync destination. Each entry in `sync.targets` is a `SyncTarget` object.

```yaml
sync:
  targets:
    - type: local
      path: /mnt/backup/orthrus
      schedule: daily
      compression: zstd
      compression_level: 3

    - type: rsync
      path: user@backup-server:/mnt/backup/orthrus
      schedule: daily
      compression: zstd
      compression_level: 3

    - type: s3
      path: /backup/orthrus
      bucket: my-orthrus-backup
      prefix: ""
      region: us-east-1
      schedule: daily
      compression: zstd
      compression_level: 3
```

### Common Fields

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `type` | enum | **required** | `local`, `rsync`, `s3` | Target type |
| `path` | str | **required** | — | Target path (see below) |
| `schedule` | enum | `daily` | `manual`, `hourly`, `daily`, `weekly` | Sync schedule |
| `compression` | enum | `zstd` | `none`, `zstd` | Compression for transfer |
| `compression_level` | int | `3` | 1–22 | Compression level |

### `type: local`

`path` is a local directory path. Data is copied directly.

### `type: rsync`

`path` is a remote path in `user@host:/path` format. Uses rsync over SSH.

Additional fields:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `user` | str | inferred from path | SSH user |
| `host` | str | inferred from path | SSH host |

### `type: s3`

`path` is a bucket prefix. Requires `bucket` field.

Additional fields:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `bucket` | str | **required** | S3 bucket name |
| `prefix` | str | `""` | Key prefix within bucket |
| `region` | str | `env` | AWS region or `env` to use `AWS_DEFAULT_REGION` |
| `credentials` | enum | `env` | `env` (default) or `file` |
| `host` | str | `s3.amazonaws.com` | S3 endpoint host (for MinIO, Wasabi, etc.) |

### Credential Management

- `credentials: env` — uses `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` environment variables
- `credentials: file` — uses `AWS_SHARED_CREDENTIALS_FILE` (`~/.aws/credentials`)

---

## 10. Example Config

```yaml
version: 1
profile: standard

capture:
  enabled: true
  queue_max_size: 100
  flush_interval_seconds: 60
  embed_async: true
  embed_on_capture: false

storage:
  hot_max_days: 30
  warm_max_days: 90
  warm_compression: zstd
  warm_compression_level: 3
  archive_compression: zstd
  archive_compression_level: 9
  parquet_row_group_size: 1000

embedding:
  enabled: true
  model: null  # uses all-MiniLM-L6-v2
  batch_size: 32
  device: auto
  dimensions: 384

search:
  default_mode: auto
  index_on_demand: true
  max_results: 100
  text_score_threshold: 0.1
  hybrid_rerank_top_k: 20

sync:
  enabled: false
  targets: []
  local_retention_days: 30
  remote_retention_days: 365
```

---

## Related Documents

- [CLI Specification](spec/04-apis/cli-spec.md) — Operator CLI interface
- [Python API Specification](spec/04-apis/python-api.md) — Python package public API
- [Sync Module Spec](spec/02-architecture/modules/sync/README.md) — sync target internals
