You are configuring ARGUS — the Agent Resource Guardian & Unified Supervisor.
ARGUS monitors agent sessions for entropy, quality, and productivity.
Your job: generate a `directives.yaml` that tells ARGUS what to enforce.

## Context Gathering

1. Read the user's SOUL.md (usually at ~/.hermes/SOUL.md or ~/.hermes/soul.md).
   This contains their persona, preferences, and quality expectations.

2. Read recent session data to understand their workflow:
   - What tools do they use most?
   - What does "productive" look like for them?
   - Do they care about quality scores, fact extraction, trajectories?
   - What's their typical session length and iteration count?

3. Check if holographic_memory.db exists at ~/.hermes/holographic_memory.db.
   If it does, the user is running ML data pipelines — quality and fact checks
   are relevant. If not, skip those checks.

4. Check if there are active cron jobs or delegate sessions.
   These indicate automated workflows that need monitoring.

## Output

Write the file to: `directives.yaml` (in the current working directory).

Follow this schema EXACTLY:

```yaml
prime_directive: |
  <1-3 sentence natural language directive synthesized from SOUL.md>

checks:
  # Always include entropy checks — these are universal
  - name: repeat_tool_calls
    type: entropy_threshold
    entropy_type: repeat_tool_calls
    min_count: 3
    window: 10m
    severity: warning
    enabled: true

  - name: error_cascade
    type: entropy_threshold
    entropy_type: error_cascade
    min_count: 3
    severity: warning
    enabled: true

  - name: budget_pressure
    type: budget_threshold
    warning_ratio: 0.70
    critical_ratio: 0.85
    near_exhaustion_ratio: 0.90
    enabled: true

  # Include quality checks ONLY if holographic_memory.db exists
  - name: quality_gate
    type: quality_threshold
    metric: avg_quality
    threshold: <0.85-0.98 based on SOUL.md quality expectations>
    window: 2h
    severity: warning
    enabled: true

  - name: fact_extraction
    type: count_threshold
    table: facts
    min_count: 1
    window: 30m
    quality_threshold: <same as quality_gate threshold>
    severity: warning
    enabled: true

  - name: trajectory_generation
    type: count_threshold
    table: trajectories
    min_count: 2
    window: 2h
    quality_threshold: <same as quality_gate threshold>
    severity: warning
    enabled: true
```

## Rules

- NEVER set severity to "critical" unless SOUL.md explicitly demands it.
  Warning gives the agent a chance to self-correct before ARGUS intervenes.
- Quality thresholds should match the user's stated standards.
  "Maximum Quality" → 0.95+. "Good enough" → 0.85.
- Budget ratios should be generous. Don't trigger at 50% — that's premature.
- If SOUL.md mentions specific outputs (files, databases, APIs), consider
  whether a custom check would be appropriate and add a comment suggesting it.
- Keep the YAML clean and commented. The user will read this.
