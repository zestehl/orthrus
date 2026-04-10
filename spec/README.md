# Orthrus Specification Directory

Systematic specification and research for the Orthrus ML data capture system.

**Status:** Research and specification phase  
**Approach:** Document-first design. No implementation code until specifications are reviewed and approved.

---

## Directory Structure

```
spec/
├── 01-requirements/        # What we must build
│   ├── user-stories.md
│   ├── functional-requirements.md
│   ├── non-functional-requirements.md
│   └── constraints.md
├── 02-architecture/        # How we build it
│   ├── ML_DATA_CAPTURE_ARCHITECTURE.md  # (moved from docs/)
│   ├── component-diagram.md
│   ├── data-flow.md
│   └── decision-log.md
├── 03-research/            # Evidence and investigation
│   ├── embedding-models/     # Model comparisons, benchmarks
│   ├── storage-formats/      # Parquet, Arrow, alternatives
│   ├── compression/          # zstd, lz4 benchmarks
│   └── indexing/               # Annoy, FAISS, HNSW
├── 04-apis/                # Interface specifications
│   ├── cli-spec.md
│   ├── python-api.md
│   └── config-schema.md
├── 05-data-formats/        # Schema specifications
│   ├── turn-schema-v1.md
│   ├── parquet-format.md
│   └── trajectory-format.md
├── 06-testing/             # Test strategy and specs
│   ├── test-strategy.md
│   ├── performance-targets.md
│   └── integration-tests.md
└── 07-deployment/          # Operations and packaging
    ├── installation.md
    ├── packaging.md
    └── operations.md
```

---

## Specification Workflow

1. **Research** (03-research/)  
   Gather evidence, benchmarks, prior art. Document trade-offs with data.

2. **Requirements** (01-requirements/)  
   Define what success looks like. User stories first, constraints explicit.

3. **Architecture** (02-architecture/)  
   System design based on research and requirements. Decision log tracks choices.

4. **APIs and Formats** (04-apis/, 05-data-formats/)  
   Concrete interface specifications. Machine-readable schemas.

5. **Testing Strategy** (06-testing/)  
   How we verify correctness, performance, durability.

6. **Deployment** (07-deployment/)  
   Packaging, installation, operations runbooks.

---

## Decision Log Format

Every architectural decision requires an entry in `02-architecture/decision-log.md`:

```markdown
## YYYY-MM-DD: [Decision Title]

**Context:** What situation led to this decision?

**Options Considered:**
1. Option A (pros/cons)
2. Option B (pros/cons)

**Decision:** Which option chosen and why.

**Consequences:** What this enables and what it forecloses.

**Reversibility:** Can this be undone? At what cost?
```

---

## Research Format

Research documents in `03-research/` must include:

- **Question:** What are we investigating?
- **Methodology:** How did we test/evaluate?
- **Data:** Raw results, benchmarks, measurements
- **Analysis:** Interpretation of data
- **Recommendation:** What should we do based on this?
- **Risks:** What could invalidate this recommendation?

---

## Approval Process

Specifications move through states:

| State | Meaning | Who Can Move |
|-------|---------|--------------|
| `draft` | Initial exploration, may be wrong | Author |
| `review` | Ready for critique, needs feedback | Author |
| `approved` | Agreed upon, implementation can proceed | zestehl |
| `superseded` | Replaced by newer spec, kept for history | zestehl |

State is tracked in document header:

```yaml
---
status: draft
author: zestehl
date: 2026-04-09
---
```

---

## Current Status

| Document | Status | Notes |
|----------|--------|-------|
| ML_DATA_CAPTURE_ARCHITECTURE.md | draft | High-level architecture, needs decomposition into specific specs |

---

## Research Queue

Next investigations needed:

1. **Embedding model comparison** - Which model balances quality/size/speed for standard profile?
2. **Parquet vs MessagePack** - For minimal profile, is Parquet overhead acceptable?
3. **zstd compression levels** - Benchmark size reduction vs CPU time
4. **Annoy vs HNSW** - Index rebuild speed and query performance
5. **DuckDB integration** - Does it add value for text search on Parquet?

---

## No Implementation Code Here

This directory is for specifications only. Implementation lives in `src/`.

**Rule:** A specification must be marked `approved` before corresponding implementation code is written.

**Exception:** Spike implementations for research purposes must be:
- Located in `research/spikes/`
- Clearly marked as experimental
- Deleted or moved to `src/` after research concludes
