# Orthrus Requirements

What Orthrus must do, and what constraints it must operate within.

---

## User Stories

### As an agent developer...

**US-001: Capture Agent Interactions**
> I want to capture every turn my agent takes (input, reasoning, output, tools used) so that I can analyze behavior and improve my agent over time.

**US-002: Export Training Data**
> I want to export captured interactions in standard formats (ShareGPT, DPO) so that I can fine-tune models on my agent's behavior.

**US-003: Search Past Interactions**
> I want to search my agent's history by content or similarity so that I can find examples, debug issues, and understand usage patterns.

### As an ML engineer...

**US-004: Quality Dataset**
> I want the exported data to include quality scores and metadata so that I can filter for high-quality examples and balance my training dataset.

**US-005: Hardware Flexibility**
> I want the system to work on my laptop (8GB RAM) and my server (64GB RAM) without reconfiguration so that I can develop locally and deploy remotely.

### As an operator...

**US-006: Durability**
> I want my data to survive software updates, configuration changes, and time (years) so that my training investment is not lost.

**US-007: Privacy**
> I want sensitive data (credentials, PII) to be automatically redacted or never captured so that my data is safe to store and share.

---

## Functional Requirements

| ID | Requirement | Priority | Acceptance Criteria |
|----|-------------|----------|---------------------|
| FR-001 | Capture agent turns with query, context, tools, outcome | P0 | All fields in schema captured, <10ms overhead |
| FR-002 | Export to ShareGPT format | P0 | Valid JSONL, loads in Axolotl/TRL |
| FR-003 | Export to DPO format | P0 | Preference pairs extractable |
| FR-004 | Text search over history | P1 | Query returns relevant turns in <1s |
| FR-005 | Vector search over history | P1 | Similarity search with configurable threshold |
| FR-006 | Configurable resource profiles | P0 | minimal/standard/performance work as specified |
| FR-007 | Automatic data rotation | P1 | Old data compressed and archived per policy |
| FR-008 | Optional sync to remote | P2 | rsync/S3 targets supported |

---

## Non-Functional Requirements

| ID | Requirement | Target | Measurement |
|----|-------------|--------|-------------|
| NFR-001 | Capture latency | <10ms | p99 across 1000 turns |
| NFR-002 | Storage efficiency | 50MB/day | Measured on standard profile |
| NFR-003 | Memory bounded | <500MB peak | RSS during normal operation |
| NFR-004 | Data durability | 10+ years | Parquet format validation |
| NFR-005 | No lock-in | Exit cost <1 day | Can migrate to alternative in 1 day |

---

## Constraints

**Technical:**
- Python 3.12+ only
- No compiled extensions required for minimal profile
- No network services (embedded mode)

**Legal/Ethical:**
- GDPR/CCPA compliance for PII
- User owns their data (no telemetry to vendor)
- Open source (MIT license)

---

**Status:** Approved — all functional and non-functional requirements implemented across 8 modules.

---

## Deferred (Post v1.0)

- Real-time collaboration (multi-agent sync)
- Cloud-hosted aggregation service
- Automated model fine-tuning pipeline
- Web UI for exploration
