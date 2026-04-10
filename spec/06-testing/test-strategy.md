# Orthrus Testing Specification

---
status: approved
author: zestehl
date: 2026-04-10
parent: spec/INDEX.md
related: spec/02-architecture/ML_DATA_CAPTURE_ARCHITECTURE.md
---

## Table of Contents
1. [Overview](#1-overview)
2. [Test Structure](#2-test-structure)
3. [Unit Tests](#3-unit-tests)
4. [Integration Tests](#4-integration-tests)
5. [Performance Targets](#5-performance-targets)
6. [Quality Gates](#6-quality-gates)
7. [CI/CD](#7-cicd)

---

## 1. Overview

Orthrus maintains a test suite that verifies correctness, enforces performance contracts, and prevents regression across all modules. Tests are written in pytest with property-based testing for core data transformations.

**Goals:**
- All tests must pass before any PR is merged
- No external services required (fully offline)
- Tests are deterministic (no random flakiness)
- Performance tests are optional but reported when run

---

## 2. Test Structure

```
tests/
├── __init__.py
├── conftest.py              # Shared fixtures
├── capture/
│   ├── __init__.py
│   ├── test_manager.py      # CaptureManager lifecycle, queue behavior
│   ├── test_turn.py         # Turn dataclass validation
│   └── test_worker.py      # EmbeddingWorker async behavior
├── storage/
│   ├── __init__.py
│   ├── test_parquet.py      # Parquet round-trip, schema enforcement
│   ├── test_jsonl.py        # JSONL round-trip
│   ├── test_rotation.py     # Rotation policy
│   └── test_manifest.py     # Manifest build/verify
├── config/
│   ├── __init__.py
│   ├── test_models.py       # Config validation, defaults
│   └── test_paths.py        # StoragePaths resolution
├── export/
│   ├── __init__.py
│   ├── test_formats.py      # ShareGPT, DPO, Raw format correctness
│   └── test_exporter.py     # Exporter pipeline, filtering
├── search/
│   ├── __init__.py
│   └── test_manager.py      # SearchManager (stub or implementation)
├── sync/
│   ├── __init__.py
│   ├── test_models.py       # SyncResult, SyncError
│   ├── test_targets.py      # LocalTarget, bytes_for_paths
│   └── test_manager.py     # SyncManager dry-run, verify
└── embedding/
    ├── __init__.py
    ├── test_protocol.py     # EmbeddingBackend Protocol conformance
    └── test_worker.py      # EmbeddingWorker submit/shutdown
```

---

## 3. Unit Tests

### 3.1 Coverage Targets

| Module | Coverage target | Current |
|--------|----------------|---------|
| capture | 90% | 168 tests |
| storage | 90% | 57 tests |
| config | 90% | 44 tests |
| export | 90% | 63 tests |
| sync | 90% | 18 tests |
| embedding | 85% | 45 tests |

**Total: 355 tests (2026-04-10)**

### 3.2 Required Test Categories

For each module, tests must cover:

**Happy path:**
- Valid input produces correct output
- Defaults are applied correctly
- Output is deterministic

**Error handling:**
- Invalid input raises the expected exception type
- Error messages are actionable (not bare `AssertionError`)
- Partial/corrupt input is handled gracefully

**Edge cases:**
- Empty inputs (empty strings, empty tuples, empty lists)
- Maximum-sized inputs (large batches, max int values)
- Unicode in text fields
- Very old / very future timestamps

### 3.3 Key Test Patterns

**Round-trip tests:** Write → read → verify field equality
```python
def test_parquet_roundtrip(tmp_path):
    records = [make_turn_record() for _ in range(10)]
    writer = ParquetWriter(tmp_path, TURN_SCHEMA)
    for r in records:
        writer.write(r)
    writer.close()
    read = list(read_turns(tmp_path))
    assert len(read) == 10
    assert read[0].trace_id == records[0].trace_id
```

**Fixture: `sample_turn`**
```python
@pytest.fixture
def sample_turn():
    return Turn(
        trace_id="0191c123-4567-7abc-8def-123456789000",
        session_id="test-session-001",
        timestamp=datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc),
        schema_version=1,
        query_text="Show me the files in the current directory",
        context_hash="a" * 64,
        available_tools=("terminal", "file_read"),
        parent_trace_id=None,
        query_embedding=None,
        active_skills=(),
        reasoning_content=None,
        tool_selection=None,
        tool_calls=(),
        outcome=TurnOutcome.SUCCESS,
        duration_ms=150,
        error_class=None,
        user_rating=None,
        response_text="Here are the files: ...",
        response_embedding=None,
        orthrus_version="0.2.0",
        capture_profile="standard",
        platform="macos",
    )
```

**Config validation tests:**
```python
def test_invalid_profile():
    with pytest.raises(ValidationError):
        Config(profile="invalid")
```

---

## 4. Integration Tests

Integration tests exercise cross-module workflows. They require the full package but no external services.

### 4.1 Required Integration Scenarios

| Scenario | Modules involved | Description |
|---------|------------------|-------------|
| Capture → Storage | capture + storage | Turn captured and written to Parquet, readable |
| Export pipeline | storage + export | All turns read, filtered by quality, exported |
| Config → Capture | config + capture | Config loaded, CaptureManager initialized |
| Sync round-trip | storage + sync | LocalTarget push then pull, files match |
| Embedding lifecycle | capture + embedding | Turn captured, embedding generated async |

### 4.2 Offline Requirement

All integration tests must:
- Use only local filesystem (tmp_path fixture)
- Mock no external services
- Not require network access
- Be deterministic (no race conditions, no timeouts)

---

## 5. Performance Targets

Performance tests are **optional** and reported to the user when run. They are not gatekeeping but provide early warning.

### 5.1 Capture Latency

Capture pipeline must meet NFR-001: p99 < 10ms per turn.

```python
@pytest.mark.performance
def test_capture_latency(benchmark_turns):
    """Capture 1000 turns and measure p99 latency."""
    times = []
    for turn in benchmark_turns:
        start = time.perf_counter()
        await capture_manager.capture(turn)
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)
    p99 = sorted(times)[int(len(times) * 0.99)]
    assert p99 < 10, f"p99 latency {p99:.1f}ms exceeds 10ms target"
```

### 5.2 Export Throughput

Export must process at least 10,000 turns/minute (166/second) for bulk operations.

### 5.3 Storage Efficiency

Measured daily volume must not exceed NFR-002: 50MB/day on standard profile.

| Metric | Target | Measurement |
|--------|--------|-------------|
| Raw storage per turn | ~50KB | Parquet file stats |
| Compressed storage per turn | ~5KB | After warm rotation |

### 5.4 Running Performance Tests

```bash
# Run all tests including performance
pytest tests/ --enable-performance

# Run only performance tests
pytest tests/ -m performance

# Benchmark embedding
pytest tests/embedding/ -v --benchmark-only
```

---

## 6. Quality Gates

### 6.1 Pre-commit Gates (required before commit)

```bash
# All must pass
ruff check src/
ruff check tests/
mypy src/orthrus/
mypy tests/orthrus/
pytest tests/ -q --tb=short
```

### 6.2 PR Gates

| Gate | Requirement |
|------|-------------|
| ruff | 0 errors (warnings OK) |
| mypy | 0 errors |
| tests | 355/355 passing |
| docs | No dead links in spec/ |

### 6.3 Lint Exceptions

Known lint exceptions are documented inline:
```python
result = some_cast  # type: ignore[misc]  # Pydantic casts to GenericAlias
```

No bare `# noqa:` without a code. No broad `# noqa:` suppression.

---

## 7. CI/CD

### 7.1 GitHub Actions (if applicable)

```yaml
name: orthrus CI
on: [push, pull_request]
jobs:
  test:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/uv-action@v1
        with:
          enable-cache: true
      - run: uv run pytest tests/ -q --tb=short
      - run: uv run ruff check src/ tests/
      - run: uv run mypy src/orthrus/
```

### 7.2 Local Verification

Before any commit:

```bash
cd ~/Projects/orthrus
uv run pytest tests/ -q --tb=short
uv run ruff check src/ tests/
uv run mypy src/orthrus/
```

### 7.3 Test Database

Tests use `tmp_path` fixtures exclusively. No permanent test database is required. Each test gets an isolated temporary directory.

---

## Related Documents

- [Non-Functional Requirements](../01-requirements/README.md) — NFR-001 to NFR-005
- [Storage Module Spec](../02-architecture/modules/storage/README.md) — Parquet format, rotation
- [Export Module Spec](../02-architecture/modules/export/README.md) — Export pipeline
- [Embedding Module Spec](../02-architecture/modules/embedding/README.md) — Async embedding worker
