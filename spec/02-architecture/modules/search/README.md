# Module: search

---
status: implemented
priority: P1
---

## Responsibility

Search over captured turns: text search and vector similarity.

**In scope:**
- Full-text search over query_text
- Vector similarity search (cosine)
- Brute-force and indexed search (Annoy)
- Hybrid ranking (text + vector)

**Out of scope:**
- Complex SQL queries (use DuckDB or load Parquet yourself)
- Real-time streaming search

## Interface

### Public API

```python
from orthrus.search import SearchManager, SearchQuery, SearchResult

class SearchQuery:
    """Query specification."""
    text: Optional[str] = None
    vector: Optional[List[float]] = None
    mode: Literal["auto", "text", "vector", "hybrid"] = "auto"
    filters: Dict[str, Any] = {}  # e.g., {"success": True}
    max_results: int = 10

class SearchResult:
    """Search result."""
    turn_id: str
    score: float
    turn_data: Dict  # Partial data

class SearchManager:
    """Manages search over stored turns."""
    
    def __init__(self, storage: StorageManager, config: SearchConfig) -> None: ...
    
    def search(self, query: SearchQuery) -> List[SearchResult]:
        """Execute search, returns ranked results."""
        ...
    
    def build_index(self, force: bool = False) -> None:
        """Build or rebuild Annoy index from storage."""
        ...
    
    def index_status(self) -> IndexStatus:
        """Index freshness, coverage, size."""
        ...
```

### CLI

```bash
orthrus search "query text"
orthrus search --vector-from "similar text" --top-k 10
orthrus search --mode hybrid --filter success=true
```

## Dependencies

- **storage**: Read Parquet files
- **embedding**: Optional, for query vectorization
- **external**: Annoy (optional index), numpy

## Resource Contract

| Method | Time (100K records) | Time (1M records) |
|--------|---------------------|-------------------|
| Text brute-force | 100ms | 1s |
| Vector brute-force | 500ms | 5s |
| Vector indexed (Annoy) | 5ms | 10ms |

## Error Handling

| Error | Response |
|-------|----------|
| No index | Fall back to brute-force |
| Index stale | Log warning, use anyway |
| Missing embeddings | Exclude those records from vector search |

## Testing

- Unit: Cosine similarity correctness
- Integration: Search returns expected results
- Benchmark: Latency vs dataset size

## Implementation

**Files:**
- `src/orthrus/search/_manager.py` — SearchManager, SearchQuery, SearchResult, SearchError
- `src/orthrus/search/_text.py` — TextSearchManager (BM25), BM25Indexer
- `src/orthrus/search/_vector.py` — VectorSearchManager (Annoy), VectorIndexer

**Architecture:**
- `SearchManager` is the coordinator — combines text and vector search
- `TextSearchManager` — BM25 ranking over `query_text`, `response_text`, `error_message` fields
- `VectorSearchManager` — Annoy approximate nearest neighbor index, cosine similarity
- Hybrid mode: reciprocal rank fusion (RRF) combining text + vector scores

**Status:**
- All spec interfaces implemented per `src/orthrus/search/__init__.py`
- Tests: **NOT YET WRITTEN** — `tests/search/` does not exist
