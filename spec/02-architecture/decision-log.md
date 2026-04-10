# Orthrus Architecture Decision Log

---
status: approved
date: 2026-04-10
---

## 2026-04-09: File-Based Storage Over Database

**Context:** We need durable, portable storage for agent telemetry and trajectories. Must survive 10+ years, work on resource-constrained devices, and avoid vendor lock-in.

**Options Considered:**

1. **LanceDB** (embedded vector database)
   - Pros: Fast vector search, Arrow-native, easy API
   - Cons: New project (<2 years), may not exist in 10 years, embedding lock-in
   - Risk: Database format becomes unreadable if project dies

2. **SQLite + FAISS** (relational + external index)
   - Pros: SQLite is 25+ years old, proven durable
   - Cons: Two separate systems, index management complexity, not columnar for analytics
   - Risk: Schema migrations over time, index rebuild complexity

3. **Parquet + JSONL files** (file-based)
   - Pros: Apache standard, readable by any tool, columnar, compressed, no lock-in
   - Cons: Requires manual indexing, search is slower without optimization
   - Risk: Directory structure management, no ACID without careful design

**Decision:** Choose option 3 (Parquet + JSONL files) with lazy indexing (Annoy/HNSW as disposable performance layer).

**Rationale:**
- Durability trumps performance for this use case
- Parquet is an Apache standard with multiple independent implementations
- JSONL is plain text, human-readable, universally parseable
- Indices can be rebuilt from source files at any time
- Zero dependency on specific software existing in the future

**Consequences:**
- Acceptable: Search is slower without pre-built indices (brute force acceptable up to ~100K records)
- Acceptable: Must implement rotation and directory management ourselves
- Mitigated: Use well-tested libraries (pyarrow) for Parquet I/O, not custom format

**Reversibility:** Low cost. Can migrate to database later by reading Parquet files and inserting into DB. Migration script would be straightforward.

**Related Research:**
- storage-formats/parquet-durability.md (TODO)

---

## 2026-04-09: Resource Profiles Over Hardware Detection

**Context:** Software must work across diverse hardware from 2GB embedded devices to 64GB workstations. Need to avoid "it works on my machine" problems.

**Options Considered:**

1. **Hardware Detection** (auto-detect RAM, CPU, GPU)
   - Pros: Zero configuration, adapts automatically
   - Cons: Wrong assumptions possible, container limits vs physical hardware, user surprise
   - Risk: Detection logic bugs, unexpected resource contention

2. **User-Declared Profiles** (minimal/standard/performance)
   - Pros: Explicit contract, portable across machines, predictable behavior
   - Cons: Requires user to choose, may be suboptimal if chosen wrong
   - Risk: User selects performance on underpowered hardware

3. **Hybrid** (detect with override)
   - Pros: Best of both worlds
   - Cons: Complexity, two code paths to test
   - Risk: Override mechanism bugs, inconsistent behavior

**Decision:** Choose option 2 (user-declared profiles) with sensible defaults.

**Rationale:**
- Explicit is better than implicit (Zen of Python)
- User understands their constraints (containers, shared machines)
- Testing is easier with fixed profiles
- Documentation is clearer

**Consequences:**
- Acceptable: Some users may run with suboptimal settings
- Mitigated: Sensible default (standard) works for most cases
- Mitigated: Clear error messages if profile exceeds resources

**Reversibility:** Trivial. Can add auto-detection later as opt-in feature.

---

## 2026-04-09: Lazy Embedding Generation

**Context:** Embeddings are expensive to generate but valuable for search. Need to balance capture speed with embedding coverage.

**Options Considered:**

1. **Synchronous Embedding** (generate before capture completes)
   - Pros: All records have embeddings, consistent state
   - Cons: Slows capture by 50-100ms per turn, CPU pressure during agent interaction
   - Risk: Timeout issues, dropped turns under load

2. **Async Queue** (capture immediately, embed in background)
   - Pros: Fast capture, embeddings generated when resources available
   - Cons: Temporary state without embeddings, queue management complexity
   - Risk: Queue overflow, embedding never completes for some records

3. **Optional/On-Demand** (embed only when needed for search)
   - Pros: Zero overhead for capture, minimal storage
   - Cons: First search is slow, complex cache management
   - Risk: User confusion about search performance

**Decision:** Choose option 2 (async queue) with option 3 as fallback if queue saturated.

**Rationale:**
- Capture speed is critical (agent responsiveness)
- Embeddings are valuable but not strictly required (text search works)
- Background processing respects resource constraints

**Consequences:**
- Acceptable: Some records temporarily without embeddings
- Mitigated: Schema allows null embeddings, search gracefully degrades
- Mitigated: Monitoring/alerting if embedding queue falls behind

**Reversibility:** Low cost. Can change embedding strategy by reprocessing Parquet files.

---
