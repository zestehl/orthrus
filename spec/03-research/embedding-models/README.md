# Research: Embedding Model Selection

---
status: draft
author: zestehl
date: 2026-04-09
question: Which embedding model balances quality, size, and speed for the `standard` profile (4-8GB RAM, CPU inference)?
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

| Model | Dimensions | Parameters | MTEB Avg | Notes |
|-------|------------|------------|----------|-------|
| all-MiniLM-L6-v2 | 384 | 22M | 56.53 | Standard baseline, widely used |
| all-mpnet-base-v2 | 768 | 109M | 63.30 | Higher quality, larger |
| E5-base-v2 | 768 | 109M | 63.55 | Better for retrieval, newer |
| GTE-base | 768 | 109M | 63.13 | General text embeddings |
| BGE-small-en-v1.5 | 384 | 33M | 62.17 | BAAI, good quality/size |

## Metrics to Collect

1. **Model size** (ONNX quantized): MB on disk
2. **Memory at runtime**: Peak RAM during inference
3. **Inference latency**: Single query, batch of 8
4. **Quality proxy**: Embedding similarity on test queries

## Data

(TODO: Run benchmarks and fill in)

## Analysis

(TODO: After data collection)

## Recommendation

(TODO: Pending analysis)

## Risks

1. **ONNX conversion quality**: Quantization may degrade embeddings significantly
2. **Hardware variance**: Benchmarks on one machine may not generalize
3. **Domain mismatch**: MTEB scores may not reflect agent-specific retrieval

## Related Decisions

- decision-log.md #3: Lazy embedding generation (this research informs that decision)

## References

- [MTEB Leaderboard](https://huggingface.co/spaces/mteb/leaderboard)
- [ONNX Runtime](https://onnxruntime.ai/)
- [Sentence Transformers](https://www.sbert.net/)
