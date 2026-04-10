# Research: Turn Dataclass Durability Patterns

---
status: in-progress
author: agent
date: 2026-04-09
question: What are the best practices for durable, immutable data structures in Python that must survive 10+ years of schema evolution?
---

## Question

The Turn dataclass is the foundation of Orthrus. It must:
- Be immutable (no accidental mutation)
- Validate at construction (no invalid data enters the system)
- Support schema evolution (future versions can add fields without breaking old data)
- Be serializable to Parquet/JSONL without loss
- Survive 10+ years (Python 3.12 → future versions)

## Methodology

1. Review prior art: MLflow, W&B, OpenTelemetry, Pydantic, Apache Arrow
2. Examine UUID7 vs alternatives for time-sortable IDs
3. Evaluate immutability patterns in Python dataclasses
4. Analyze schema evolution strategies

## Findings

### 1. Time-Sortable IDs: UUID7 vs Alternatives

**UUID7 (draft-peabody-dispatch-new-uuid-format-01)**
- Unix timestamp (milliseconds) in first 48 bits
- Random in remaining 80 bits
- Lexicographically sortable by time
- Embedded in standard UUID format (backward compatible)

**Alternatives considered:**
- **ULID**: 26-character string, base32 encoded, sortable
  - Pros: Lexicographically sortable as string
  - Cons: Not native UUID, requires dependency
- **KSUID (K-Sortable Unique Identifier)**: 20 bytes, base62
  - Pros: More timestamp precision (seconds + 4-byte sequence)
  - Cons: Non-standard, requires dependency
- **Snowflake (Twitter-style)**: 64-bit integer
  - Pros: Very compact (8 bytes)
  - Cons: Requires coordination/sequence generator, not UUID compatible
- **UUID4**: Pure random
  - Pros: Standard, no dependencies
  - Cons: Not time-sortable (breaks chronological queries)

**Decision:** UUID7 is optimal for Orthrus
- Native UUID type (interoperable)
- Time-sortable (efficient range queries)
- No additional dependencies (use uuid6 library or implement)
- Future-proof (being standardized)

### 2. Immutability Patterns

**Option A: frozen dataclass**
```python
@dataclass(frozen=True)
class Turn:
    ...
```
- Pros: Native Python, clear intent, hashable
- Cons: post_init validation requires object.__setattr__ hacks
- Verdict: **Recommended for Orthrus**

**Option B: Pydantic BaseModel**
```python
class Turn(BaseModel):
    model_config = ConfigDict(frozen=True)
```
- Pros: Built-in validation, JSON schema generation, excellent error messages
- Cons: Slight overhead, validation on every construction (can be slow for high-volume capture)
- Verdict: **Consider for validation layer, not core storage**

**Option C: NamedTuple**
```python
class Turn(NamedTuple):
    ...
```
- Pros: Truly immutable, lightweight
- Cons: No defaults, verbose, hard to extend
- Verdict: **Not recommended**

**Option D: Manual __slots__ with property access**
- Pros: Memory efficient
- Cons: Boilerplate heavy, error-prone
- Verdict: **Not recommended**

**Hybrid Approach for Orthrus:**
```python
# Core immutable dataclass (storage layer)
@dataclass(frozen=True, slots=True)  # slots for memory efficiency
class Turn:
    ...

# Validation wrapper (construction layer)
@dataclass
class TurnBuilder:
    def build(self) -> Turn:
        # validation happens here
        return Turn(...)
```

### 3. Schema Evolution Strategies

**Forward Compatibility (old code reads new data):**
- Ignore unknown fields (Parquet/JSONL natural behavior)
- Default values for new fields (use `field(default_factory=...)`)

**Backward Compatibility (new code reads old data):**
- All new fields must have defaults
- Use `Optional` for fields that didn't exist before
- Version field (`schema_version`) for migration logic

**Pattern: Schema versioning with discriminated union**
```python
@dataclass(frozen=True)
class TurnV1:
    schema_version: Literal[1] = 1
    ...

@dataclass(frozen=True)
class TurnV2:
    schema_version: Literal[2] = 2
    new_field: str = "default"
    ...

Turn = Union[TurnV1, TurnV2]

# Loader can upgrade V1 → V2
```

**Orthrus approach:**
- Single dataclass with all optional new fields (simpler)
- `schema_version` field for explicit versioning
- Upgrade logic in loader (not constructor)

### 4. Hash Validation

**SHA-256 for content addressing:**
- 64 hex characters
- Universal, unambiguous
- Can verify integrity years later

**Validation at construction:**
```python
def __post_init__(self):
    if not re.match(r'^[a-f0-9]{64}$', self.context_hash):
        raise ValueError(f"Invalid SHA-256 hash: {self.context_hash}")
```

**Consideration:** Post-init validation requires `frozen=True` workaround:
```python
object.__setattr__(self, 'field', validated_value)
```

### 5. Datetime Handling

**Critical decision: Require timezone-aware datetimes**
```python
# Validation
def _validate_datetime(self, ts: datetime) -> datetime:
    if ts.tzinfo is None:
        raise ValueError("Timestamp must be timezone-aware (UTC)")
    return ts.astimezone(timezone.utc)  # Normalize to UTC
```

**Why:** Naive datetimes cause silent bugs when machines cross timezone boundaries or daylight saving transitions.

**Default:** `datetime.now(timezone.utc)` — always explicit

### 6. Prior Art Analysis

**MLflow Tracking:**
- Uses protobuf for runs/metrics (complex, not human-readable)
- Heavyweight for Orthrus use case

**Weights & Biases:**
- Custom data format, cloud-dependent
- Not portable/durable

**OpenTelemetry Span:**
- Similar structure (trace_id, span_id, parent_id, timestamps)
- Very similar to Turn concept
- Uses 16-byte TraceID/SpanID (hex strings)

**Apache Arrow Schema:**
- Columnar, but same field concepts
- Strong typing, nullability

### 7. Embedding Storage

**Options for float vectors:**
1. `List[float]` - Python native, but boxed floats (memory overhead)
2. `array.array('f')` - Compact, mutable (bad for immutable dataclass)
3. `tuple[float, ...]` - Immutable, but still boxed
4. `numpy.ndarray` - Best performance, but complex serialization
5. Store in Parquet native, skip Python field

**Orthrus approach:**
- Use `List[float]` in dataclass (convenience)
- PyArrow converts to native float32 array in Parquet
- Memory overhead acceptable for capture-time (temporary)

## Intelligent Defaults

Based on research, recommended defaults:

| Field | Default | Rationale |
|-------|---------|-----------|
| `trace_id` | Required (no default) | Must be explicit, never accidental |
| `session_id` | Required | Must be explicit |
| `timestamp` | `datetime.now(timezone.utc)` | Capture time is natural default |
| `schema_version` | `1` | Current schema |
| `duration_ms` | `0` | Will be updated post-capture |
| `outcome` | `TurnOutcome.SUCCESS` | Optimistic default |
| `tool_calls` | `[]` | Empty list (field default_factory) |
| `available_tools` | `[]` | Must be populated by caller |
| `active_skills` | `[]` | Optional context |
| `capture_profile` | `"standard"` | Matches default profile |
| `orthrus_version` | `importlib.metadata.version("orthrus")` | Auto-detect |
| `platform` | `f"{sys.platform}-{platform.machine()}"` | Auto-detect |

## Recommendations

1. **Use `@dataclass(frozen=True, slots=True)`** for memory efficiency and immutability
2. **Use UUID7** for trace_id (via uuid7 library or vendored implementation)
3. **Require UTC timestamps** at construction, validate in __post_init__
4. **Use SHA-256 hex strings** for content hashes, validate format
5. **Include schema_version** as int (not string) for easy comparisons
6. **Separate validation from construction** using TurnBuilder pattern for complex validation
7. **All optional fields for evolution** must have meaningful defaults

## Risks

1. **UUID7 library availability** - May need to vendor implementation
2. **Frozen dataclass + __post_init__** - Awkward validation pattern, easy to get wrong
3. **Pydantic temptation** - May want to switch later for validation, but it's slower
4. **Timezone enforcement** - Breaking change if users pass naive datetimes

## Related Decisions

- decision-log.md #1: File-based storage (affects serialization)
- Future: Schema evolution policy (when to bump schema_version)
