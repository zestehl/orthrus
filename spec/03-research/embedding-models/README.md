# Research: Embedding Model Selection

---
status: approved
author: zestehl
date: 2026-04-10
question: Which embedding model balances quality, size, and speed for the `standard` profile (4-8GB RAM, CPU inference)?
decided: all-MiniLM-L6-v2
---

## Question

For the `standard` resource profile (default), we need an embedding model that:
- Runs on CPU (no GPU requirement)
- Fits in ~4GB RAM alongside other processes
- Generates 384-1024 dimensional embeddings
- Processes queries in <100ms (batch of 1)
- Achieves acceptable retrieval quality

## Methodology

1. Select candidate models from MTEB leaderboard
2. Download and convert to ONNX with quantization (int8)
3. Benchmark inference latency on reference hardware (to be specified)
4. Measure embedding quality on domain-relevant queries (if available)

## Candidates

| Model | Dimensions | Parameters | MTEB Avg | ONNX Size | RAM at runtime |
|-------|------------|------------|----------|-----------|----------------|
| **all-MiniLM-L6-v2** | 384 | 22M | 56.53 | ~90MB | <200MB |
| all-mpnet-base-v2 | 768 | 109M | 63.30 | ~440MB | ~500MB |
| E5-base-v2 | 768 | 109M | 63.55 | ~440MB | ~500MB |
| GTE-base | 768 | 109M | 63.13 | ~440MB | ~500MB |
| BGE-small-en-v1.5 | 384 | 33M | 62.17 | ~130MB | ~300MB |

**Selected:** all-MiniLM-L6-v2

## Data

**MTEB (Massive Text Embedding Benchmark) scores** from [HuggingFace MTEB Leaderboard](https://huggingface.co/spaces/mteb/leaderboard):

| Benchmark | all-MiniLM-L6-v2 | E5-base-v2 | GTE-base | BGE-small |
|-----------|------------------|------------|----------|-----------|
| Average | 56.53 | 63.55 | 63.13 | 62.17 |
| Retrieval | 42.4 | 53.1 | 52.8 | 53.2 |
| Clustering | 37.4 | 43.8 | 43.2 | 43.0 |
| PairClassification | 84.0 | 85.9 | 85.4 | 85.7 |
| Reranking | 59.6 | 63.4 | 62.9 | 62.5 |
| STS (semantic sim.) | 76.5 | 80.2 | 79.7 | 80.1 |

**Model size comparison** (HuggingFace transformers, fp32):

| Model | Disk size | Quantized (int8) |
|-------|----------|-----------------|
| all-MiniLM-L6-v2 | ~90MB | ~25MB |
| all-mpnet-base-v2 | ~440MB | ~110MB |
| E5-base-v2 | ~440MB | ~110MB |
| BGE-small-en-v1.5 | ~130MB | ~35MB |

## Analysis

all-MiniLM-L6-v2 is chosen over higher-scoring alternatives for the `standard` profile based on:

1. **RAM constraint:** At 4-8GB total, loading a 440MB model + tokenizer + torch is marginal. all-MiniLM-L6-v2 fits in <200MB RAM with room for other processes.

2. **MTEB retrieval score is adequate:** 42.4 is sufficient for agent-specific retrieval (the query corpus is narrow domain, not general web). Higher scores are calibrated on broad retrieval tasks.

3. **384 dimensions:** Half the vector storage of 768-dim models. For 1M turns: 384-dim × 4 bytes × 1M = ~1.5GB vs 3GB. Significant storage savings at scale.

4. **Established baseline:** all-MiniLM-L6-v2 is the most-used sentence embedding model in open-source projects. Wide community support, well-understood behavior.

5. **Quantization-friendly:** 22M params is the sweet spot for int8 quantization — nearly lossless compression to ~25MB with ONNX.

**Candidates considered but not selected:**

- **E5-base-v2 (63.55):** Higher quality, but 5× memory for marginal retrieval improvement on narrow domain.
- **BGE-small-en-v1.5 (62.17):** Better score than all-MiniLM-L6-v2 but 50% larger (33M vs 22M params). Still a viable alternative if quality needs improvement.
- **all-mpnet-base-v2 (63.30):** Too large for standard profile RAM envelope.

## Recommendation

**Use all-MiniLM-L6-v2** as the default for the `standard` profile.

- Default: `model=None` (uses all-MiniLM-L6-v2), `dimensions=384`
- Override path: `embedding.model` in config
- Future upgrade: Consider BGE-small-en-v1.5 as a drop-in quality improvement (same dimensions, 50% larger, 5+ MTEB points higher)

## Risks

1. **Domain mismatch:** MTEB is general-purpose. Agent-specific retrieval quality may differ.
2. **Quantization degradation:** ONNX int8 quantization may degrade embeddings slightly. Mitigation: benchmark on representative queries before shipping quantized.

## Related Decisions

- decision-log.md #3: Lazy embedding generation (this research informs that decision)

## References

- [MTEB Leaderboard](https://huggingface.co/spaces/mteb/leaderboard)
- [ONNX Runtime](https://onnxruntime.ai/)
- [Sentence Transformers](https://www.sbert.net/)
