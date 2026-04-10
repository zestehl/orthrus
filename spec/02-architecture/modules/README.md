# Orthrus Module Specifications

Each module is an independent component with clear interfaces. Module specs define:

1. **Responsibility**: What this module does and does not do
2. **Interface**: Public API (Python) and CLI commands
3. **Dependencies**: What it requires from other modules
4. **Resource Contract**: Memory, CPU, storage guarantees
5. **Error Handling**: Failure modes and recovery

---

## Module Overview

| Module | Responsibility | Critical Path |
|--------|--------------|---------------|
| **capture** | Turn capture, validation, queue management | Yes (P0) |
| **storage** | Parquet/JSONL writing, rotation, compression | Yes (P0) |
| **embedding** | Async embedding generation, backends | Yes (P1) |
| **search** | Text and vector search, index management | No (P1) |
| **sync** | Remote synchronization, encryption | No (P2) |
| **export** | Training format export (ShareGPT, DPO) | Yes (P1) |
| **config** | Configuration loading, validation, profiles | Yes (P0) |
| **cli** | Command-line interface, commands | Yes (P0) |

---

## Dependency Graph

```
config (no dependencies)
    ↓
capture → storage
    ↓
embedding (optional)
    ↓
search (depends on storage, optional embedding)
    ↓
export (depends on storage, search)
    ↓
sync (depends on storage)
    ↓
cli (orchestrates all)
```

---

## Module Spec Format

Each module spec follows this structure:

```markdown
# Module: [Name]

## Responsibility
What this module does. Explicit boundaries (what it does NOT do).

## Interface

### Public API
```python
class ModuleName:
    def method(self, ...) -> ...: ...
```

### CLI Commands
```bash
orthrus module command [args]
```

## Dependencies
- Module X: requires Y interface
- External: library Z

## Resource Contract
- Memory: X MB typical, Y MB peak
- CPU: async/threaded/parallel
- Storage: writes to path P

## Error Handling
- Failure modes
- Recovery strategy

## Testing Strategy
Unit, integration, property-based tests.
```

---

## Module Specs

| Module | Spec Status | Priority | Description |
|--------|-------------|----------|-------------|
| config | draft | P0 | Configuration loading, validation, profiles |
| capture | in-progress | P0 | Turn capture, ingest queue, async pipeline |
| storage | draft | P0 | Parquet/JSONL writing, rotation, compression |
| embedding | draft | P1 | Async embedding generation, pluggable backends |
| search | draft | P1 | Text and vector search, index management |
| export | draft | P1 | Training format export (ShareGPT, DPO) |
| sync | draft | P2 | Remote synchronization, encryption |
| cli | draft | P0 | Command-line interface |

## Critical Path

Implementation order:

1. **config** → **storage** → **capture** (P0 core)
2. **cli** (orchestration layer)
3. **embedding** (enhances capture)
4. **search** (consumes storage)
5. **export** (consumes storage + search)
6. **sync** (optional, independent)
