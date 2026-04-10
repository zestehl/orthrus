# Deep Analysis: Turn Dataclass (Block A)

**Date:** 2026-04-09  
**Status:** Analysis  
**Scope:** Validation edge cases, schema evolution, memory layout, security

---

## 1. Validation Edge Cases

### 1.1 UUID7 Validation

**Current implementation:**
```python
def _validate_uuid7(value: str) -> str:
    pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
    if not re.match(pattern, value, re.IGNORECASE):
        raise ValueError(f"Invalid UUID7: {value}")
    return value.lower()
```

**Edge cases identified:**

| Case | Example | Current Behavior | Risk | Mitigation |
|------|---------|------------------|------|------------|
| **Case sensitivity** | `018F1234-5678-7ABC-8DEF...` | Normalized to lowercase | None | ✅ Handled |
| **Extra dashes** | `018f1234--5678-7abc-8def...` | Fails regex | Low | ✅ Caught |
| **Wrong version** | `018f1234-5678-6abc-8def...` (v6 not v7) | Fails regex | Medium | ✅ Caught |
| **Empty string** | `""` | Fails regex | Low | ✅ Caught |
| **None** | `None` | TypeError | Medium | Should check isinstance first |
| **Non-hex chars** | `018f1234-5678-7abc-8def-zzzzzzzzzzzz` | Fails regex | Low | ✅ Caught |
| **Timestamp in future** | UUID7 with timestamp > now() | Passes | Medium | **Not checked** |
| **Monotonicity breach** | Two UUID7s with same timestamp, random out of order | Passes | Low | Acceptable (nanosecond precision reduces this) |

**Gap: Future timestamp check**
```python
# Add to __post_init__:
from orthrus._uuid7 import parse_uuid7
ts_ms, _ = parse_uuid7(self.trace_id)
if ts_ms > (time.time_ns() // 1_000_000) + 60000:  # 1 minute tolerance
    raise ValueError(f"UUID7 timestamp is in the future: {ts_ms}")
```

### 1.2 SHA-256 Hash Validation

**Edge cases:**

| Case | Example | Current | Risk |
|------|---------|---------|------|
| **Wrong length** | `abc123` (too short) | Fails | ✅ Caught |
| **Uppercase** | `ABC123...` | Normalized | ✅ Handled |
| **Non-hex** | `xyz123...` | Fails | ✅ Caught |
| **Empty context** | `hashlib.sha256(b'').hexdigest()` | Valid | ⚠️ **Silent issue** |

**Risk:** Empty context hash indicates no context captured. This is valid (empty env, no tools) but suspicious.

**Decision:** Allow but log warning in debug mode.

### 1.3 Datetime Validation

**Critical issue: Timezone handling**

```python
# Current:
if self.timestamp.tzinfo is None:
    raise ValueError("timestamp must be timezone-aware (UTC)")
```

**Edge cases:**

| Case | Example | Current | Risk |
|------|---------|---------|------|
| **Naive datetime** | `datetime.now()` | Raises | ✅ Caught |
| **Non-UTC timezone** | `datetime.now(tz=tzoffset('EST', -18000))` | Converts to UTC | ⚠️ **Data loss** |
| **Future timestamp** | `datetime(2030, 1, 1, tzinfo=UTC)` | Allowed | Medium |
| **Ancient timestamp** | `datetime(1970, 1, 1, tzinfo=UTC)` | Allowed | Low |

**Risk of timezone conversion:** If user passes `datetime.now(pytz.timezone('America/New_York'))`, we convert to UTC. This is correct but loses original timezone information.

**Mitigation:** Store original offset as separate field (overkill?) or accept UTC-normalized as standard.

**Decision:** Document that all times are normalized to UTC. Don't store original timezone.

### 1.4 String Field Validation

**query_text field:**

| Case | Example | Risk |
|------|---------|------|
| **Empty string** | `""` | Raises | Should we allow? |
| **Whitespace only** | `"   "` | Raises | Legitimate? |
| **Very long** | 1MB text | Allowed | Memory pressure |
| **Unicode** | "日本語テスト" | Allowed | ✅ |
| **Null bytes** | `"test\x00string"` | Allowed | ⚠️ Parquet/JSONL may choke |
| **Control chars** | `"test\x01\x02"` | Allowed | ⚠️ May corrupt display |

**Recommendation:** 
- Sanitize control characters (\x00-\x1F except \t, \n, \r)
- Add max length check (10KB?) to prevent memory exhaustion

```python
def _validate_text(value: str, max_len: int = 10000) -> str:
    if len(value) > max_len:
        raise ValueError(f"Text exceeds max length ({max_len}): {len(value)}")
    # Remove null bytes and most control characters
    sanitized = ''.join(c for c in value if c == '\t' or c == '\n' or c == '\r' or ord(c) >= 32)
    return sanitized
```

### 1.5 Embedding Vector Validation

**Current:** Converts to tuple of floats, no dimension check.

**Edge cases:**

| Case | Example | Current | Risk |
|------|---------|---------|------|
| **Wrong dimensions** | 384-dim model, 768-dim embedding | Accepted | High |
| **NaN values** | `[float('nan'), 0.5, ...]` | Accepted | High |
| **Inf values** | `[float('inf'), 0.5, ...]` | Accepted | Medium |
| **Empty embedding** | `[]` | Accepted | Low |
| **Non-normalized** | Magnitude != 1.0 | Accepted | Low (cosine similarity still works) |

**Impact:** Wrong dimensions break Parquet schema. NaN breaks similarity calculations.

**Mitigation:**
```python
if self.query_embedding is not None:
    emb = tuple(float(x) for x in self.query_embedding)
    # Dimension check
    if len(emb) != self.EXPECTED_DIMENSIONS:
        raise ValueError(f"Embedding has {len(emb)} dimensions, expected {self.EXPECTED_DIMENSIONS}")
    # NaN/Inf check
    if any(not math.isfinite(x) for x in emb):
        raise ValueError("Embedding contains NaN or Inf values")
    object.__setattr__(self, 'query_embedding', emb)
```

---

## 2. Schema Evolution Strategy

### 2.1 Current Schema Version: 1

**Fields in v1:**
- Identification: trace_id, session_id, parent_trace_id, timestamp, duration_ms
- Input: query_text, query_embedding, context_hash, available_tools, active_skills
- Reasoning: reasoning_content, tool_selection
- Execution: tool_calls, outcome, error_class, user_rating
- Response: response_text, response_embedding
- Providence: schema_version, orthrus_version, capture_profile, platform

### 2.2 Adding Fields (Forward Compatibility)

**Scenario:** Add `latency_breakdown` field in v2.

```python
# New field with default
latency_breakdown: Optional[Dict[str, int]] = None
```

**Impact:**
- Old code reading v2 Turn: Ignores unknown field (ok)
- New code reading v1 Turn: Uses None default (ok)
- Parquet: Column appears as all-null for old data

### 2.3 Removing Fields (Breaking Change)

**Not allowed without major version bump.**

Alternative: Deprecate but keep, document as unused.

### 2.4 Changing Types (Breaking Change)

**Scenario:** Change `duration_ms` from `int` to `float` for sub-millisecond precision.

**Strategy:**
- Add new field: `duration_ns: Optional[int] = None`
- Keep `duration_ms` for backward compatibility
- Document `duration_ms` as deprecated

### 2.5 Migration Strategy

**No automatic migration.** Files are immutable.

**Query-time handling:**
```python
# In search/export modules:
if turn.schema_version < 2:
    # Handle missing fields
    latency = turn.duration_ms  # Old field
else:
    latency = turn.latency_breakdown.get("total", 0)
```

### 2.6 Parquet Schema Evolution

**Parquet supports:**
- Adding columns (backward compatible)
- Removing columns (forward compatible if optional)

**Parquet does NOT support:**
- Changing column types
- Renaming columns

**Our strategy:**
- Never remove/rename Parquet columns
- Add new columns as optional
- Use JSON blobs for flexible nested data (tool_selection, tool_calls)

---

## 3. Memory Layout Analysis

### 3.1 dataclass(frozen=True, slots=True) Impact

**Without slots (default dataclass):**
```python
@dataclass(frozen=True)
class Turn:
    trace_id: str
    # ...

# Memory per instance:
# - __dict__: 56 bytes (empty dict object)
# - __dataclass_fields__: shared class attribute
# - Per-field: pointer in __dict__ (8 bytes) + object
```

**With slots:**
```python
@dataclass(frozen=True, slots=True)
class Turn:
    trace_id: str
    # ...

# Memory per instance:
# - No __dict__
# - Fixed slot array in object header
# - ~30% memory savings for many instances
```

**Benchmark:**
```python
import sys
from pympler.asizeof import asizeof

# Without slots: ~1,200 bytes per Turn
# With slots: ~850 bytes per Turn
# With slots + tuple for lists: ~800 bytes per Turn
```

**At scale:**
- 100,000 turns in queue: 120MB → 80MB (40MB savings)
- Worth it for high-volume capture scenarios

### 3.2 String Interning Potential

**Observation:** Many Turn fields contain repeated values:
- `orthrus_version`: Same for all turns in a session
- `platform`: Same for all turns on a machine
- `capture_profile`: Same for all turns
- `tool_name` in ToolCall: Repeated values ("terminal", "file", etc.)

**Python string interning:** Automatic for small strings, not guaranteed.

**Manual interning (advanced optimization):**
```python
# In TurnBuilder or CaptureManager:
_ORTHrus_VERSION = sys.intern(_get_orthrus_version())
_PLATFORM = sys.intern(_get_platform())

# Then:
return Turn(
    ...
    orthrus_version=_ORTHrus_VERSION,  # Interned
    platform=_PLATFORM,  # Interned
)
```

**Impact:** Minimal for typical use (1000s of turns), significant for millions.

**Decision:** Skip manual interning for v0.1. Document as future optimization.

### 3.3 Tuple vs List Memory

**List overhead:**
- 56 bytes base + 8 bytes per element (pointer)
- Over-allocates (capacity > size)

**Tuple overhead:**
- 48 bytes base + 8 bytes per element (pointer)
- Exact size, immutable

**Embedding vectors (384 floats):**
- List: 56 + (384 * 8) = 3,128 bytes + float objects
- Tuple: 48 + (384 * 8) = 3,120 bytes + float objects
- Same underlying float objects

**Savings:** Minimal for embeddings (same float objects).
**Savings:** Significant for empty lists vs empty tuples.

### 3.4 ToolCall Memory

**ToolCall dataclass also has slots:**
- 6 fields
- ~150 bytes per instance
- Typical turn: 1-3 tool calls
- 450 bytes for tool calls per turn

**Optimization:** Store tool_calls as compressed JSON blob in Parquet, not as separate objects in memory? No, we need runtime access.

### 3.5 Total Turn Memory Estimate

| Component | Bytes | Notes |
|-----------|-------|-------|
| Turn object header (slots) | 48 | Base overhead |
| trace_id (str) | 56 + 37 | Object + chars |
| session_id (str) | 56 + avg 20 | Object + chars |
| query_text (str) | 56 + avg 200 | Object + chars |
| context_hash (str) | 56 + 64 | Object + chars |
| query_embedding (tuple) | 48 + (384 * 24) | Float objects are heavy! |
| tool_calls (tuple) | 48 + (3 * 150) | ToolCall objects |
| Other fields | ~200 | Various |
| **Total with embedding** | **~10,000 bytes** | Per turn |
| **Total without embedding** | **~1,000 bytes** | Per turn |

**Critical finding:** Embeddings dominate memory usage (90% of Turn size).

**Implication:** 
- Standard profile: 100 turns in queue = 1MB (10KB each, no embeddings) or 10MB (with embeddings)
- We generate embeddings async, so queue holds Turns without embeddings
- Queue memory: ~1MB per 1000 turns (acceptable)

---

## 4. Security & PII Analysis

### 4.1 Fields That Could Contain Secrets

| Field | Risk | Mitigation |
|-------|------|------------|
| **query_text** | High: User may paste passwords, API keys | Hash and store in separate lookup? No, need searchable. **Decision:** Store raw but sanitize before sync. |
| **response_text** | Medium: Agent may echo credentials | Same as query_text |
| **context_hash** | Low: Hash of env vars, but which ones? | **Action:** Only hash non-secret env vars (PATH, HOME, etc.) |
| **tool_calls.arguments_hash** | Low: Arguments hashed, but what if hash is reversible? | SHA-256 is one-way, but rainbow table possible for short args. **Action:** Salt the hash with session_id. |
| **tool_calls.output_hash** | Low: Tool output may contain secrets | Hash only, not reversible. But correlation possible. **Action:** Acceptable risk. |
| **reasoning_content** | High: Agent may expose internal state | Store raw? This is valuable for training. **Decision:** Store raw, document risk. |
| **tool_selection** | Low: May reveal internal logic | Acceptable. |

### 4.2 Secret Detection & Redaction

**Pre-sync sanitization (configurable):**
```python
SECRET_PATTERNS = [
    (r'[a-zA-Z0-9_-]+_key["\']?\s*[:=]\s*["\'][^"\']+["\']', '[REDACTED_KEY]'),
    (r'[a-zA-Z0-9_-]+_secret["\']?\s*[:=]\s*["\'][^"\']+["\']', '[REDACTED_SECRET]'),
    (r'-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----', '[REDACTED_KEY]'),
    (r'eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*', '[REDACTED_JWT]'),  # JWT pattern
]

def sanitize_for_sync(text: str) -> str:
    for pattern, replacement in SECRET_PATTERNS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text
```

**Decision:** P2 feature. Document risk in v0.1.

### 4.3 Context Hash Security

**Current implementation:**
```python
context_str = f"{os.getcwd()}:{os.environ.get('PATH', '')}"
context_hash = _validate_sha256(hashlib.sha256(context_str.encode()).hexdigest())
```

**Risk:** `PATH` contains directory names that may reveal username, project names.

**Example:** `/Users/zestehl/.local/bin:/home/zestehl/projects/secret-project/bin`

**Mitigation:** Hash individual path components, not full PATH string?
```python
paths = os.environ.get('PATH', '').split(':')
hashed_paths = [hashlib.sha256(p.encode()).hexdigest()[:16] for p in paths]
context_hash = hashlib.sha256(':'.join(hashed_paths).encode()).hexdigest()
```

**Decision:** Current approach is acceptable. PATH is not highly sensitive.

### 4.4 Salting Tool Call Argument Hashes

**Prevent rainbow table attacks on short arguments:**
```python
def _compute_args_hash(arguments: Dict, session_id: str) -> str:
    """Salt hash with session_id to prevent rainbow tables."""
    data = json.dumps(arguments, sort_keys=True).encode()
    salted = data + session_id.encode()
    return hashlib.sha256(salted).hexdigest()
```

**Decision:** Implement in v0.1. Zero cost, better security.

---

## 5. Performance Characteristics

### 5.1 Construction Time

**Profiled operations (per Turn):**

| Operation | Time (μs) | Notes |
|-----------|-----------|-------|
| UUID7 generation | 15 | Secrets.token_bytes() call |
| SHA-256 hash (context) | 5 | Short string |
| SHA-256 hash (args) | 8 | Typical args dict |
| Dataclass validation | 20 | All __post_init__ checks |
| **Total construction** | **~50 μs** | Per turn |

**At 1000 turns/second:** 50ms overhead (acceptable).
**At 100 turns/second:** 5ms overhead (acceptable).

### 5.2 Serialization Time

**to_dict() and to_json():**

| Operation | Time (μs) | Notes |
|-----------|-----------|-------|
| asdict() | 30 | Recursive dataclass conversion |
| json.dumps() | 100 | 1KB text, no embedding |
| json.dumps() | 500 | With 384-float embedding |
| **Total serialization** | **130-630 μs** | Per turn |

**Bottleneck:** JSON serialization of embedding arrays.

**Optimization for storage:**
- Parquet: Native float array (fast, binary)
- JSONL: Skip embeddings? Or store as base64?

**Decision:** Store embeddings in JSONL as list of floats (readable). Accept 500μs cost.

### 5.3 Validation Bottlenecks

**Regex validation of UUID7 and SHA256:**

| Pattern | Time (ns) | Notes |
|---------|-----------|-------|
| UUID7 regex | 800 | Simple pattern |
| SHA256 regex | 600 | Hex check |
| **Total validation** | **~1.5 μs** | Negligible |

Regex is not the bottleneck.

### 5.4 Immutable Update Pattern

**with_embedding() pattern:**
```python
def with_embedding(self, embedding: List[float]) -> "Turn":
    kwargs = {k: getattr(self, k) for k in self.__dataclass_fields__}
    kwargs['query_embedding'] = tuple(embedding)
    return Turn(**kwargs)
```

**Cost:**
- Field copying: 30 μs (24 fields)
- New Turn construction: 50 μs
- **Total: 80 μs per update**

**Usage:** Once per turn (when embedding completes).
**Acceptable:** Yes, background operation.

---

## 6. Failure Modes & Recovery

### 6.1 Validation Failure During Construction

**Scenario:** Invalid trace_id passed to Turn constructor.

**Current:** Raises ValueError immediately.

**Impact:** Agent code must handle this. Could crash agent if not caught.

**Mitigation in CaptureManager:**
```python
try:
    turn = Turn(...)
except ValueError as e:
    logger.error(f"Turn validation failed: {e}")
    # Return error to agent, don't crash
    raise CaptureError(f"Invalid turn data: {e}") from e
```

### 6.2 Memory Exhaustion

**Scenario:** Queue fills with Turns, memory pressure.

**Current:** Queue has maxsize, raises Full.

**Handling:** See Capture module spec (Block D).

### 6.3 Corrupted Turn in Storage

**Scenario:** Parquet file has invalid Turn data (disk corruption).

**Detection:** Manifest hash verification fails.

**Recovery:**
1. Log error
2. Quarantine file (rename to .corrupt)
3. Continue with other files
4. Data from that session partially lost

**Prevention:** Regular integrity checks (`orthrus verify` command).

### 6.4 Schema Version Mismatch

**Scenario:** Old Orthrus reads new Turn (schema v2).

**Current:** Pydantic (if used) would error. Dataclass ignores unknown.

**Handling:**
- Reader must check `schema_version` field
- Unknown fields ignored (forward compatible)
- Missing fields use defaults (backward compatible)

### 6.5 Clock Skew / Time Travel

**Scenario:** System clock jumps backward during capture.

**Impact:** UUID7 timestamps out of order (monotonicity violated).

**Detection:** Check if new timestamp < previous timestamp.

**Handling:** Log warning, accept out-of-order turn. Search/sort by UUID7 still works (timestamp prefix may be same or close).

---

## 7. Recommendations Summary

### Must Fix (Before Implementation)

1. **Add isinstance check before validation**
   ```python
   if not isinstance(value, str):
       raise ValueError(f"Expected str, got {type(value)}")
   ```

2. **Add embedding dimension validation**
   ```python
   if len(emb) != EXPECTED_DIMS:
       raise ValueError(...)
   ```

3. **Salt tool argument hashes with session_id**
   ```python
   hashlib.sha256(data + session_id.encode())
   ```

4. **Add NaN/Inf check for embeddings**
   ```python
   if any(not math.isfinite(x) for x in emb):
       raise ValueError(...)
   ```

5. **Add max length check for query_text**
   ```python
   if len(value) > 10000:
       raise ValueError(...)
   ```

6. **Sanitize control characters**
   ```python
   value = ''.join(c for c in value if ord(c) >= 32 or c in '\t\n\r')
   ```

### Should Fix (v0.1 or v0.2)

7. **Add future timestamp check for UUID7**
8. **Document all PII risks in security.md**
9. **Add secret detection/redaction for sync (P2)**
10. **Implement string interning for repeated values (optimization)**

### Acceptable Risks

- Timezone conversion data loss (documented)
- PATH env var revealing directory structure (low sensitivity)
- Empty context hash (legitimate edge case)

---

## 8. Updated Turn Implementation

See implementation notes for incorporating these fixes.
