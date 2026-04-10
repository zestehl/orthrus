# Orthrus Data Formats

---
status: approved
author: zestehl
date: 2026-04-10
parent: spec/INDEX.md
related: spec/04-apis/python-api.md, spec/02-architecture/modules/storage/README.md
---

## Table of Contents
1. [Overview](#1-overview)
2. [Turn Schema](#2-turn-schema)
3. [PyArrow Schema](#3-pyarrow-schema)
4. [JSONL Format](#4-jsonl-format)
5. [Export Formats](#5-export-formats)
6. [Schema Versioning](#6-schema-versioning)

---

## 1. Overview

Orthrus captures agent interactions as `Turn` records and stores them using two interchangeable formats:

| Format | File extension | Use case |
|--------|---------------|----------|
| Parquet | `.parquet` | Analytics, bulk read, columnar queries |
| JSONL | `.jsonl` | Debugging, line-by-line streaming, human-readable |

Both formats are fully specified below. The system chooses format per-file at write time; either can be used for storage, rotation, and export.

---

## 2. Turn Schema

The `Turn` dataclass is the canonical in-memory representation. All fields are typed with Python standard library types.

### 2.1 `Turn`

```python
@dataclass
class Turn:
    trace_id: str                        # UUIDv7, unique per turn
    session_id: str                      # Groups turns into a conversation
    timestamp: datetime                  # UTC, microsecond precision
    schema_version: int                  # Schema version (current: 1)

    # Query
    query_text: str                      # Raw user/agent query text
    context_hash: str                     # SHA-256 of context for deduplication
    available_tools: tuple[str, ...]     # Tools available at query time
    parent_trace_id: str | None          # Parent turn trace_id (for multi-turn)
    query_embedding: tuple[float, ...] | None  # 384-dim vector (all-MiniLM-L6-v2)
    active_skills: tuple[str, ...]        # Skill names active during this turn

    # Reasoning & Tool Use
    reasoning_content: str | None         # Raw reasoning output (may be empty)
    tool_selection: str | None           # LLM tool selection reasoning
    tool_calls: tuple[ToolCall, ...]     # Tools invoked during this turn

    # Outcome
    outcome: TurnOutcome                # Enum: success | error | timeout | partial
    duration_ms: int                     # Wall-clock ms from query to response
    error_class: str | None              # Exception class name if outcome=error
    user_rating: float | None            # Optional quality rating (0.0–1.0)

    # Response
    response_text: str | None           # Assistant response text
    response_embedding: tuple[float, ...] | None  # Embedding of response_text

    # Metadata
    orthrus_version: str                # orthrus version string
    capture_profile: str                 # Resource profile at capture time
    platform: str                        # Platform identifier (e.g., "macos", "linux")
```

### 2.2 `ToolCall`

```python
@dataclass
class ToolCall:
    tool_name: str      # Tool identifier
    arguments_hash: str  # SHA-256 of serialized arguments
    output_hash: str    # SHA-256 of tool output
    duration_ms: int    # Tool execution time
    exit_code: int      # Process exit code (0 = success)
    success: bool      # True if exit_code == 0
```

### 2.3 `TurnOutcome`

```python
class TurnOutcome(str, Enum):
    SUCCESS = "success"    # Turn completed with valid response
    ERROR   = "error"      # Turn encountered an exception
    TIMEOUT = "timeout"   # Turn exceeded time limit
    PARTIAL = "partial"   # Turn partially completed (e.g., some tools failed)
```

---

## 3. PyArrow Schema

Orthrus uses PyArrow for columnar Parquet storage. The schema maps Turn fields to PyArrow types.

```
turn_id:           string      (UUID7 string)
session_id:        string
timestamp:          timestamp[us, tz=UTC]
schema_version:     int8

query_text:         string
query_embedding:   list<item: float>   (384-dim vector, nullable)
query_intent:       string             (reserved, currently unused)

context_ref:        string             (SHA-256 hash of context)
available_tools:    list<item: string>
active_skills:      list<item: string>

reasoning_content:  string
tool_selection:     string
tool_calls:         string             (JSON-serialized list of ToolCall dicts)

duration_ms:        int64
outcome:            string             (TurnOutcome enum value)

response_text:      string
response_embedding: list<item: float>  (384-dim vector, nullable)

error_class:        string             (nullable)
orthrus_version:     string
capture_profile:    string
platform:           string
```

**Notes:**
- `query_embedding` and `response_embedding` are stored as variable-length float lists. Null when embeddings are not yet generated.
- `tool_calls` is JSON-serialized (not nested Parquet) for simplicity and cross-tool compatibility.
- `schema_version` as `int8` reflects the schema evolution version of the Turn dataclass.
- Timestamps use microsecond precision in UTC.

---

## 4. JSONL Format

Each line is a valid JSON object representing a single turn. Field types map to JSON native types as follows:

| Python type | JSON type |
|-------------|----------|
| `str` | string |
| `datetime` | ISO-8601 string |
| `int` | number |
| `float` | number |
| `tuple` | array |
| `None` | `null` |
| `TurnOutcome` | string (enum value) |
| `Path` | string |

### 4.1 JSONL Field Mapping

```
trace_id            string (UUID7)
session_id           string
timestamp           string (ISO-8601)
schema_version       integer

query_text          string
query_embedding     array[float] | null
parent_trace_id     string | null
context_hash        string
available_tools     array[string]
active_skills       array[string]

reasoning_content   string | null
tool_selection      string | null
tool_calls          array[object] | null

duration_ms         integer
outcome             string
response_text       string | null
response_embedding  array[float] | null

error_class          string | null
user_rating         float | null
orthrus_version     string
capture_profile     string
platform            string
```

### 4.2 ToolCall JSON Object

```json
{
  "tool_name": "string",
  "arguments_hash": "string (SHA-256)",
  "output_hash": "string (SHA-256)",
  "duration_ms": "integer",
  "exit_code": "integer",
  "success": "boolean"
}
```

---

## 5. Export Formats

Orthrus exports turns to training formats. Each format is JSONL (one JSON object per line) with format-specific fields.

### 5.1 ShareGPT Format

Conversation-style format for instruction tuning. Each record is a `conversations` array with alternating `human`/`gpt` roles.

**Reference:** [ShareGPT (HuggingFaceH4)](https://github.com/HuggingFaceH4/ShareGPT)

**Required fields:**

```json
{
  "conversations": [
    { "from": "system", "value": "Tools available: tool_a, tool_b\nActive skills: skill_x" },
    { "from": "human",  "value": "<query_text>" },
    { "from": "gpt",    "value": "<reasoning_content>\n\n<response_text>" }
  ],
  "turn_id": "018f1234-5678-7abc-8def-123456789abc",
  "session_id": "session-abc123"
}
```

**Optional fields:** `quality` (float, `user_rating`), `outcome` (string, non-success only), `tool_calls` (array).

**Null handling:** Records with empty `query_text` or `response_text` are skipped.

**Reasoning prefix:** When `reasoning_content` is non-empty, it is prepended to `response_text` inside `<reasoning>` XML tags.

### 5.2 DPO Format

Preference-pair format for Direct Preference Optimization (DPO). Each record contains `prompt`, `chosen`, and `rejected`.

**Reference:** [DPO Paper (arXiv:2305.18290)](https://arxiv.org/abs/2305.18290)

**Fields:**

```json
{
  "prompt": "<query_text>\n[Tools: tool_a, tool_b]\n[Skills: skill_x]",
  "chosen": "<reasoning_content>\n\n<response_text>",
  "rejected": "[Tool failure: tool_name exited with code 1]",
  "turn_id": "018f1234-5678-7abc-8def-123456789abc",
  "session_id": "session-abc123",
  "outcome": "error"
}
```

**Prompt construction:** `query_text` is joined with available tools and active skills as bracketed tags.

**Rejected synthesis:**

| Outcome | Rejected source |
|---------|----------------|
| `error`/`timeout`/`partial` + tool failure | Tool name + exit code |
| `error`/`timeout`/`partial` + no tools | Error class or timeout message |
| `success` | `"[Skipped — no dispreferred response available]"` |

**Null handling:** Records with empty `query_text` are skipped (prompt is required).

### 5.3 Raw Format

Complete passthrough of all Turn fields as JSON. No filtering or transformation.

**Fields:** All non-None Turn fields serialized as JSON. Embeddings are arrays of floats. `tool_calls` is an array of `ToolCall` objects. `TurnOutcome` is serialized as its string value.

```json
{
  "trace_id": "018f1234-5678-7abc-8def-123456789abc",
  "session_id": "session-abc123",
  "timestamp": "2026-04-10T12:00:00.000000+00:00",
  "schema_version": 1,
  "query_text": "...",
  "query_embedding": [0.001, -0.023, ...],
  "available_tools": ["tool_a", "tool_b"],
  "tool_calls": [
    {
      "tool_name": "tool_a",
      "arguments_hash": "sha256hash",
      "output_hash": "sha256hash",
      "duration_ms": 42,
      "exit_code": 0,
      "success": true
    }
  ],
  "outcome": "success",
  ...
}
```

---

## 6. Schema Versioning

Orthrus uses a single `schema_version` integer field in every record (Parquet and JSONL). The current schema version is **1**.

### 6.1 Version Policy

- **Major versions** (increment on breaking changes): All existing records remain readable; new schema may drop or rename fields.
- **Minor additions** (no version bump): New nullable fields are added; existing readers ignore unknown fields.
- **No downgrades**: Older orthrus versions may not read newer schemas. Users should retain original data.

### 6.2 Schema History

| Version | Date | Change |
|---------|------|--------|
| 1 | 2026-04-10 | Initial schema. All currently implemented fields. |

---

## Related Documents

- [Python API Specification](spec/04-apis/python-api.md) — `Turn`, `ToolCall`, `TurnOutcome` types
- [Storage Module Spec](spec/02-architecture/modules/storage/README.md) — Storage layout, rotation
- [Export Module Spec](spec/02-architecture/modules/export/README.md) — Export pipeline
- [TURN_DATACLASS_DEEP_ANALYSIS.md](05-data-formats/TURN_DATACLASS_DEEP_ANALYSIS.md) — Validation edge cases, UUID7, hash validation
