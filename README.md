![AGATHOS Logo](assets/agathos_logo.jpg)

# AGATHOS - Agent Guardian & Health Oversight System

AGATHOS is the immune system for Hermes — a background daemon that detects entropy in agent sessions and takes corrective action before quality degrades.

## What It Does

- **Session Monitoring** — Watches cron jobs, delegate tasks, and manual sessions
- **Entropy Detection** — Catches repeat tool calls, stuck loops, and wasted cycles
- **Quality Enforcement** — Restarts or kills sessions that fall below ML data quality thresholds
- **Cost Protection** — Alerts on budget overruns and circuit-breaks failing providers
- **Action Execution** — Injects corrective prompts, restarts, or terminates as needed
- **Notification Fan-out** — Sends alerts via Telegram, Discord, Slack, or webhooks

AGATHOS integrates directly with Hermes internals — using `cron.jobs` for discovery, `SessionDB` for state, and `hermes_cli.config` for user overrides. It respects the existing structure without duplicating logic.

## Configuration

All advanced features default to **OFF**. Enable only what you need:

```yaml
agathos:
  # Core (always on)
  poll_interval: 30
  entropy_detection_enabled: true
  actions_enabled: true
  
  # Optional features (default OFF — opt-in)
  ml_data_enabled: false
  cost_monitoring:
    enabled: false
    daily_budget: 20.00
  circuit_breaker:
    enabled: false
```

Interactive setup: `agathos setup`

---

**Good code defends itself. AGATHOS ensures your agents do too.**
