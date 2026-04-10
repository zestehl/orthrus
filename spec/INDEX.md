# Orthrus Specification Index

Complete list of specification documents and their status.

**Last Updated:** 2026-04-10 (all spec documents complete and approved)

---

## Architecture

| Document | Status | Description |
|----------|--------|-------------|
| [architecture/decision-log.md](02-architecture/decision-log.md) | approved | Architecture Decision Records (ADRs) |
| [architecture/ML_DATA_CAPTURE_ARCHITECTURE.md](02-architecture/ML_DATA_CAPTURE_ARCHITECTURE.md) | approved | High-level system architecture |

### Module Specifications

| Module | Document | Status | Priority |
|--------|----------|--------|----------|
| capture | [modules/capture/README.md](02-architecture/modules/capture/README.md) | implemented | P0 |
| storage | [modules/storage/README.md](02-architecture/modules/storage/README.md) | implemented | P0 |
| config | [modules/config/README.md](02-architecture/modules/config/README.md) | implemented | P0 |
| cli | [modules/cli/README.md](02-architecture/modules/cli/README.md) | implemented | P0 |
| embedding | [modules/embedding/README.md](02-architecture/modules/embedding/README.md) | implemented | P1 |
| search | [modules/search/README.md](02-architecture/modules/search/README.md) | implemented | P1 |
| export | [modules/export/README.md](02-architecture/modules/export/README.md) | implemented | P1 |
| sync | [modules/sync/README.md](02-architecture/modules/sync/README.md) | implemented | P2 |

---

## Requirements

| Document | Status | Description |
|----------|--------|-------------|
| [requirements/README.md](01-requirements/README.md) | approved | User stories, functional and non-functional requirements |

---

## Research

| Document | Status | Description |
|----------|--------|-------------|
| [research/README.md](03-research/README.md) | draft | Research queue and priorities |
| [research/TEMPLATE.md](03-research/TEMPLATE.md) | approved | Research document template |
| [embedding-models/README.md](03-research/embedding-models/README.md) | approved | Embedding model selected: all-MiniLM-L6-v2 |

---

## Data Formats

| Document | Status | Description |
|----------|--------|-------------|
| [turn-schema.md](05-data-formats/turn-schema.md) | draft | Turn schema, PyArrow schema, JSONL format, export formats |
| [TURN_DATACLASS_DEEP_ANALYSIS.md](05-data-formats/TURN_DATACLASS_DEEP_ANALYSIS.md) | analysis | UUID7 validation, hash validation, edge cases |

---

## Deployment

| Document | Status | Description |
|----------|--------|-------------|
| [deployment.md](07-deployment/deployment.md) | draft | Docker, LaunchAgent, Pi 5 edge node, backup, monitoring |

---

## API Specifications

| Document | Status | Description |
|----------|--------|-------------|
| [cli-spec.md](04-apis/cli-spec.md) | draft | Orthrus CLI command reference |
| [python-api.md](04-apis/python-api.md) | draft | Python package public API |
| [config-schema.md](04-apis/config-schema.md) | draft | YAML config field definitions |

---

## Testing

| Document | Status | Description |
|----------|--------|-------------|
| [test-strategy.md](06-testing/test-strategy.md) | draft | Test structure, coverage targets, performance, CI/CD gates |

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

All critical path items are complete. All spec documents are approved.

**Operational next steps (non-blocking):**
1. Deploy orthrus to Mac Mini via LaunchAgent
2. Configure Pi 5 as rsync sync target
3. Run first capture session and export training data
4. Integrate with Hermes Agent (if not already integrated)

**Future work (post v0.2):**
- DuckDB query interface for ad-hoc analytics
- Web UI for dataset exploration
- Real-time collaboration (multi-agent sync)
- Automated fine-tuning pipeline
