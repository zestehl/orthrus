# Orthrus CLI Specification

---
status: approved
author: zestehl
date: 2026-04-10
parent: spec/INDEX.md
related: spec/04-apis/python-api.md
---

## Table of Contents
1. [Overview](#1-overview)
2. [Invocation](#2-invocation)
3. [Global Options](#3-global-options)
4. [Command: capture](#4-command-capture)
5. [Command: config](#5-command-config)
6. [Command: export](#6-command-export)
7. [Command: search](#7-command-search)
8. [Command: sync](#8-command-sync)
9. [Exit Codes](#9-exit-codes)
10. [Output Formats](#10-output-formats)

---

## 1. Overview

The Orthrus CLI is the primary operator interface for the ML data capture system. It is implemented with [Typer](https://typer.tiangolo.com/) 0.24.1 and uses [Rich](https://github.com/Textualize/rich) for formatted console output.

### 1.1 Command Hierarchy

```
orthrus
├── capture   Capture pipeline management
├── config    Config file management
├── export    Export turns to training formats
├── search    Search captured turns
└── sync      Remote synchronization
```

### 1.2 Entry Point

The CLI is installed as the `orthrus` console script via the `pyproject.toml` `[project.scripts]` entry. The canonical invocation is:

```bash
orthrus [global options] <command> [command options] [arguments]
```

### 1.3 Dependencies

- Typer >= 0.24.1
- Rich >= 10.0.0
- All orthrus modules (capture, storage, config, export, search, sync)

---

## 2. Invocation

### 2.1 Help Flag

```bash
orthrus --help          # Show top-level help
orthrus <cmd> --help    # Show command-specific help
```

### 2.2 Version

```bash
orthrus --version       # Print orthrus version and exit
```

---

## 3. Global Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--config`, `-c` | Path | `~/.orthrus/config.yaml` | Path to config file |
| `--quiet`, `-q` | flag | false | Suppress informational output |
| `--verbose`, `-v` | flag | false | Enable verbose output |
| `--output-format` | Text | `text` | Output format for non-table output: `text` or `json` |

---

## 4. Command: capture

Manages the capture pipeline that records agent interactions.

**App:** `capture_app = typer.Typer(name="capture")`

### 4.1 `capture status`

Show current capture pipeline status.

```bash
orthrus capture status
```

**Output:** Rich table with the following rows:

| Field | Description |
|-------|-------------|
| Queue depth | Current queue depth as `N / MAX` |
| Total captured | Cumulative turn count |
| Started | `Yes` if the capture loop is running |
| Draining | `Yes` if graceful shutdown is in progress |
| Embedding | `Enabled` or `Disabled` |
| Healthy | `Yes` (green) or `No` (red) |

**Internal behavior:** Instantiates `CaptureManager` briefly to query `status()`. Fails gracefully if capture is disabled in config.

### 4.2 `capture enable`

Enable the capture pipeline in the config file.

```bash
orthrus capture enable [--config FILE]
```

| Option | Type | Description |
|--------|------|-------------|
| `--config`, `-c` | Path | Config file to modify (default: config in use) |

**Behavior:** Sets `capture.enabled = true` in the YAML config file.

### 4.3 `capture disable`

Disable the capture pipeline in the config file.

```bash
orthrus capture disable [--config FILE]
```

| Option | Type | Description |
|--------|------|-------------|
| `--config`, `-c` | Path | Config file to modify (default: config in use) |

**Behavior:** Sets `capture.enabled = false` in the YAML config file.

---

## 5. Command: config

Manages the Orthrus YAML configuration file.

**App:** `config_app = typer.Typer(name="config")`

### 5.1 `config init`

Create a default config file.

```bash
orthrus config init [--path PATH] [--force]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--path`, `-p` | Path | `~/.orthrus/config.yaml` | Output path |
| `--force`, `-f` | bool | false | Overwrite existing file |

**Errors:**
- Exits with error if file exists and `--force` not set.

### 5.2 `config validate`

Validate the current config file.

```bash
orthrus config validate
```

**Behavior:** Loads the config via `get_config()`. Exits 0 if valid, exits 1 with error message if invalid.

### 5.3 `config show`

Display the effective config.

```bash
orthrus config show [--format json|text]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--format`, `-f` | Text | `text` | `text` (YAML) or `json` |

---

## 6. Command: export

Exports captured turns to training data formats.

**App:** `export_app = typer.Typer(name="export")`

### 6.1 `export` (default command)

Export turns to a JSONL file.

```bash
orthrus export --output FILE [--format FORMAT] [--min-quality SCORE]
    [--session ID] [--since DATETIME] [--until DATETIME] [--dry-run]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--output`, `-o` | str | **required** | Output JSONL file path |
| `--format`, `-f` | str | `sharegpt` | Export format: `sharegpt`, `dpo`, or `raw` |
| `--min-quality` | float | `0.0` | Minimum quality score (0.0–1.0) |
| `--session`, `-s` | str | all | Export single session only |
| `--since` | datetime | all | Start datetime (ISO-8601) |
| `--until` | datetime | all | End datetime (ISO-8601) |
| `--dry-run` | bool | false | Count matching turns without writing file |

**Output on success:**
```
Exported 1234 turns to output.jsonl
```

**Output on dry-run:**
```
Would export 1234 turns (dry-run)
```

**Datetime parsing:** Accepts ISO-8601 strings with optional `Z` suffix. Naive datetimes are treated as UTC.

---

## 7. Command: search

Searches captured turns by text query or semantic similarity.

```bash
orthrus search QUERY [--vector-from TEXT] [--top-k K] [--session ID]
    [--mode MODE] [--format text|json]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `QUERY` | str | **required** | Search query text |
| `--vector-from` | str | none | Embed TEXT and search by semantic similarity |
| `--top-k`, `-k` | int | 10 | Maximum results to return |
| `--session`, `-s` | str | none | Filter by session ID |
| `--mode`, `-m` | str | `auto` | Search mode: `auto`, `text`, `vector`, `hybrid` |
| `--format`, `-f` | str | `text` | Output format: `text` (default) or `json` |

**Mode behavior:**

| Mode | Behavior |
|------|----------|
| `auto` | Use text if only `QUERY`, vector if `--vector-from` provided, both if both provided |
| `text` | Full-text search on query_text |
| `vector` | Semantic similarity using `--vector-from` TEXT as query embedding |
| `hybrid` | Text + vector fused via Reciprocal Rank Fusion (RRF) |

**Output (text):** Rich table with Score, Trace ID, Session, Query columns.

---

## 8. Command: sync

Synchronizes captured data to remote targets.

**App:** `sync_app = typer.Typer(name="sync")`

### 8.1 `sync` (default command)

Sync captured data to configured targets.

```bash
orthrus sync [--target NAME] [--dry-run] [--verbose]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--target` | str | all | Target name to sync (default: all configured targets) |
| `--dry-run` | bool | false | List changes without applying them |
| `--verbose` | bool | false | Show individual file transfers |

**Output:** Rich table with columns:

| Column | Description |
|--------|-------------|
| Target | Target name |
| Status | `success` (green) or `failed` (red) |
| Files | Files transferred (local) or bytes transferred (rsync/S3) |
| Duration | Elapsed time |

**Internal behavior:** Loads storage paths via `get_storage_paths()`, instantiates `SyncManager` with all configured targets, calls `sync(dry_run=...)`, and prints results.

---

## 9. Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Command failed (validation error, file error, operation error) |
| 2 | Import or initialization error |

---

## 10. Output Formats

All commands use [Rich](https://github.com/Textualize/rich) for formatted console output. Table output is used for status displays. Plain text is the default for all other output.

### 10.1 JSON Output

When `--format json` is specified, commands output a single JSON object or array to stdout. This is suitable for scripting.

### 10.2 Error Output

Errors are printed to stderr as a plain text message prefixed with `Error:`. The exit code is set to 1.

---

## Related Documents

- [Python API Specification](spec/04-apis/python-api.md) — Orthrus Python package public API
- [Config Schema](spec/04-apis/config-schema.md) — YAML config field definitions
- [Capture Module Spec](spec/02-architecture/modules/capture/README.md) — capture pipeline internals
- [Export Module Spec](spec/02-architecture/modules/export/README.md) — export format details
- [Sync Module Spec](spec/02-architecture/modules/sync/README.md) — sync target configuration
