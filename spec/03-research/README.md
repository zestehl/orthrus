# Orthrus Research Queue

Active and queued research investigations.

---

## Active Research

None currently. See queue below.

---

## Research Queue (Prioritized)

### P0: Critical Path (Blocking Implementation)

1. **Embedding Model Selection** (03-research/embedding-models/)
   - Question: Which embedding model for `standard` profile (4-8GB RAM, CPU)?
   - Options: all-MiniLM-L6-v2, E5-base-v2, GTE-base, BGE-small-en
   - Metrics: Quality (MTEB), size, inference speed (ONNX quantized)
   - Blocking: Core capture implementation

2. **Storage Format Validation** (03-research/storage-formats/)
   - Question: Is Parquet overhead acceptable for `minimal` profile?
   - Options: Parquet vs MessagePack vs raw Arrow IPC
   - Metrics: File size, read/write speed, memory usage
   - Blocking: Writer implementation

### P1: Important (Before v0.2)

3. **Compression Benchmarks** (03-research/compression/)
   - Question: Which compression level balances size and CPU?
   - Options: zstd 3/9/19, lz4, none
   - Metrics: Compression ratio, compression time, decompression time
   - Context: Warm/archive tier storage

4. **Index Performance** (03-research/indexing/)
   - Question: Annoy vs HNSW for 100K-1M vectors?
   - Options: Annoy, FAISS HNSW, hnswlib
   - Metrics: Build time, query time, recall@10, memory usage
   - Context: Optional index layer

### P2: Nice to Have (Future Releases)

5. **DuckDB Integration Value**
   - Question: Does DuckDB add value for text search on Parquet?
   - Metrics: Query performance vs custom implementation
   - Trade-off: Dependency weight vs functionality

6. **Sync Protocol Comparison**
   - Question: rsync vs rclone vs custom for various targets?
   - Metrics: Speed, reliability, dependency footprint
   - Context: Optional sync feature

7. **Encryption Overhead**
   - Question: What is the cost of age encryption on large datasets?
   - Metrics: Throughput, CPU usage, compression interaction
   - Context: Optional encryption feature

---

## Research Process

1. Create research document from TEMPLATE.md
2. Document methodology and collect data
3. Update decision-log with findings
4. Mark research as `complete` in status
5. Archive research document (kept for history)

---

## Completed Research

| Topic | Date | Conclusion | Decision |
|-------|------|------------|----------|
| File vs Database storage | 2026-04-09 | Parquet+JSONL more durable | decision-log.md #1 |
| Resource profiles | 2026-04-09 | User-declared over detection | decision-log.md #2 |
| Embedding strategy | 2026-04-09 | Async with lazy fallback | decision-log.md #3 |
