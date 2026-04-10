# Orthrus Agent Reference

**Status:** Active development — v0.2.0
**Root:** `~/Projects/orthrus/`
**Always use:** `.venv/bin/python` or `uv run` — NOT the hermes-agent venv

---

## Active Source Tree

```
src/orthrus/
├── __init__.py              # __version__ = "0.1.0"
├── cli.py                   # stub → orthrus.legacy.cli (not yet built)
├── setup.py                 # stub → orthrus.legacy.setup (not yet built)
├── orthrus_audit.py        # stub → orthrus.legacy.orthrus_audit (not yet built)
├── integration.py           # HermesPlugin with health_check()
├── capture/
│   ├── __init__.py
│   ├── _uuid7.py           # generate_uuid7(), parse_uuid7() — no deps
│   └── turn.py             # CORE: Turn, ToolCall, TurnOutcome (frozen/slots)
└── config/                  # DONE — YAML loading, resource profiles, XDG paths
    ├── __init__.py         # Public API: Config, load_config, etc.
    ├── _paths.py           # orthrus_dirs(), default_config_search_paths()
    └── _models.py          # CaptureConfig, StorageConfig, EmbeddingConfig, SearchConfig, SyncConfig, SyncTarget
```

## Tests

```
tests/
├── capture/
│   ├── test_turn.py        # 28 tests: immutability, validation, embeddings
│   └── test_uuid7.py       # 11 tests: generation, parsing, format
└── config/
    └── test_config.py      # 41 tests: Config, ResourceProfile, XDG paths

# Run all:
cd ~/Projects/orthrus && uv run pytest tests/ -v
```

---

## Core Data Model

### Turn (frozen, slots, validated at construction)

```python
from orthrus.capture.turn import Turn, ToolCall, TurnOutcome
from datetime import datetime, timezone
import hashlib

t = Turn(
    trace_id="018f1234-5678-7abc-8def-0123456789ab",  # UUID7 required
    session_id="session-001",
    timestamp=datetime.now(timezone.utc),
    query_text="What is the capital of France?",
    context_hash=hashlib.sha256(b"context").hexdigest(),
    available_tools=("web_search", "file_read"),
    tool_calls=(
        ToolCall(
            tool_name="web_search",
            arguments_hash=hashlib.sha256(b'{"q":"France"}').hexdigest(),
            output_hash=hashlib.sha256(b'"Paris"').hexdigest(),
            duration_ms=150,
            exit_code=0,
            success=True,
        ),
    ),
)
```

Key facts:
- **frozen=True, slots=True** — immutable, hashable
- **SHA-256 hashes** for args/outputs — never raw storage
- **UUID7 trace_id** — lexicographically sortable by time
- **384-dim embeddings** — validated at construction
- **Providence fields** auto-populated: orthrus_version, capture_profile, platform
- **TurnOutcome enum:** SUCCESS | ERROR | TIMEOUT | PARTIAL

### UUID7

```python
from orthrus.capture._uuid7 import generate_uuid7, parse_uuid7

uid = generate_uuid7()           # "018f1234-5678-7abc-8def-..."
ts_ms, rand = parse_uuid7(uid)  # (1744292409123, b'...')
```

### Config (resource profiles, XDG paths)

```python
from orthrus.config import load_config, Config, ResourceProfile

cfg = load_config()                          # search path, or explicit path
cfg = load_config(Path("~/.orthrus/config.yaml"))

cfg.profile                        # ResourceProfile.STANDARD (default)
cfg.effective_capture_queue_size()  # 10/100/1000 per profile
cfg.effective_embedding_model()     # None/all-MiniLM-L6-v2/E5-large-v2
```

---

## Common Commands

```bash
cd ~/Projects/orthrus

uv pip install -e .              # install
uv run pytest tests/ -v          # run tests
uv run ruff check src/orthrus    # lint
uv run ruff format src/orthrus    # format
uv run mypy src/orthrus           # type check
uv run pytest tests/ -q           # quick test
```

---

## Key Constraints

- **DO NOT edit `docs/reference/agathos/` or `docs/reference/_old_legacy/`** — frozen
- **DO NOT use hermes-agent venv** — always `.venv/bin/python` or `uv run`
- **DO NOT use pip directly** — use `uv pip`
- **cli.py/setup.py/orthrus_audit.py are stubs** — legacy module not yet built

---

## Adding a field to Turn

1. Add field to dataclass in `src/orthrus/capture/turn.py`
2. Add validation in `__post_init__`
3. Add test in `tests/capture/test_turn.py`
4. Run: `uv run ruff check src/orthrus && uv run mypy src/orthrus`

---

## Related Skills

- `orthrus-directive` — full project navigation, spec workflow, stack
- `python-pro` — Python 3.12+ patterns
- `ml-data-collection-directives` — trajectory generation, KB enrichment
