# Orthrus Specification Index

Complete list of specification documents and their status.

**Last Updated:** 2026-04-09

---

## Architecture

| Document | Status | Description |
|----------|--------|-------------|
| [architecture/decision-log.md](02-architecture/decision-log.md) | draft | Architecture Decision Records (ADRs) |
| [architecture/ML_DATA_CAPTURE_ARCHITECTURE.md](02-architecture/ML_DATA_CAPTURE_ARCHITECTURE.md) | draft | High-level system architecture |

### Module Specifications

| Module | Document | Status | Priority |
|--------|----------|--------|----------|
| capture | [modules/capture/README.md](02-architecture/modules/capture/README.md) | draft | P0 |
| storage | [modules/storage/README.md](02-architecture/modules/storage/README.md) | draft | P0 |
| config | [modules/config/README.md](02-architecture/modules/config/README.md) | draft | P0 |
| cli | [modules/cli/README.md](02-architecture/modules/cli/README.md) | draft | P0 |
| embedding | [modules/embedding/README.md](02-architecture/modules/embedding/README.md) | draft | P1 |
| search | [modules/search/README.md](02-architecture/modules/search/README.md) | draft | P1 |
| export | [modules/export/README.md](02-architecture/modules/export/README.md) | draft | P1 |
| sync | [modules/sync/README.md](02-architecture/modules/sync/README.md) | draft | P2 |

---

## Requirements

| Document | Status | Description |
|----------|--------|-------------|
| [requirements/README.md](01-requirements/README.md) | draft | User stories, functional and non-functional requirements |

---

## Research

| Document | Status | Description |
|----------|--------|-------------|
| [research/README.md](03-research/README.md) | draft | Research queue and priorities |
| [research/TEMPLATE.md](03-research/TEMPLATE.md) | approved | Research document template |
| [research/embedding-models/README.md](03-research/embedding-models/README.md) | draft | Embedding model selection (P0 blocking) |

---

## Pending Directories

These directories exist but have no documents yet:

- `04-apis/` - API specifications (CLI schema, Python API)
- `05-data-formats/` - Schema specifications (Turn, Parquet, Trajectory)
- `06-testing/` - Test strategy, performance targets
- `07-deployment/` - Installation, packaging, operations

---

## Legend

| Status | Meaning |
|--------|---------|
| draft | Initial exploration, may change significantly |
| review | Ready for feedback and critique |
| approved | Agreed upon, implementation can proceed |
| superseded | Replaced by newer spec, kept for history |

| Priority | Meaning |
|----------|---------|
| P0 | Critical path, blocks v0.1 release |
| P1 | Important, in v0.1 or v0.2 |
| P2 | Nice to have, future release |

---

## Next Steps

1. **Complete research**: embedding-models selection (P0 blocking)
2. **Review architecture**: Mark high-level architecture as approved
3. **Detail module specs**: Move from interface sketches to full specifications
4. **API specifications**: CLI command schemas, config file formats
5. **Data format specs**: Exact Parquet schemas, JSONL formats
