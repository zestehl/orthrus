![AGATHOS Logo](https://raw.githubusercontent.com/zestehl/agathos/main/assets/agathos_logo.jpg)

# Agathos — Agent Guardian & Health Oversight System

Agathos is the immune system for Hermes Agent — a background daemon that detects entropy in agent sessions and takes corrective action before quality degrades.

## What It Does

- **Session Monitoring** — Watches cron jobs, delegate tasks, and manual sessions
- **Entropy Detection** — Catches repeat tool calls, stuck loops, and wasted cycles  
- **Quality Enforcement** — Restarts or kills sessions that fall below ML data quality thresholds
- **Cost Protection** — Alerts on budget overruns and circuit-breaks failing providers
- **Action Execution** — Injects corrective prompts, restarts, or terminates as needed
- **Notification Fan-out** — Sends alerts via Telegram, Discord, Slack, or webhooks

## Installation

### Prerequisites

- Python 3.9+
- Hermes Agent installed and configured
- [uv](https://docs.astral.sh/uv/) package manager

### Install uv (if not already installed)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
# or via Homebrew
brew install uv
```

### Install Agathos

```bash
git clone https://github.com/zestehl/agathos.git
cd agathos

# Create virtual environment and install
uv venv
uv pip install -e ".[dev]"

# Or use the locked dependencies
uv pip sync uv.lock
uv pip install -e .
```

## Quick Start

```bash
# Using uv run (no need to activate venv)
uv run agathos-setup

# Or start the daemon directly
uv run agathos

# Check status
uv run agathos status

# Run audit for stale references
uv run agathos-audit

# Or activate the venv and use directly
source .venv/bin/activate
agathos-setup
```

## Development Commands

```bash
# Install dev dependencies
uv pip install -e ".[dev]"

# Run linting
uv run ruff check src/agathos

# Run type checking
uv run mypy src/agathos

# Run tests
uv run pytest tests/

# Run POSIX compliance checks
uv run python tests/run_posix_compliance_check.py

# Run audit for stale references
uv run agathos-audit --strict
```

## Configuration

Agathos creates its config directory at `~/.hermes/agathos/`:

```yaml
# ~/.hermes/agathos/config.yaml
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

## Hermes Integration

When installed alongside Hermes Agent, Agathos:
- Auto-registers via entry points (`hermes.plugins`)
- Hooks into session lifecycle (start/end)
- Exports health checks and metrics
- Falls back to subprocess mode if Hermes internals unavailable

## Architecture

```
┌─────────────────────────────────────────┐
│           Hermes Agent                  │
│  ┌─────────────────────────────────┐    │
│  │  Agathos Plugin (optional)    │    │
│  │  - Session hooks                │    │
│  │  - Health checks              │    │
│  │  - Metrics export               │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
                    │
                    │ (subprocess / internal)
                    ▼
┌─────────────────────────────────────────┐
│           Agathos Daemon                │
│  ┌─────────┐ ┌─────────┐ ┌──────────┐ │
│  │ Entropy │ │ Actions │ │  Audit   │ │
│  │   Detection   Execution    Trail  │ │
│  └─────────┘ └─────────┘ └──────────┘ │
│  ┌─────────┐ ┌─────────┐ ┌──────────┐ │
│  │ Circuit │ │  Cost   │ │ Notifications │
│  │ Breaker │ │ Monitor │ │           │ │
│  └─────────┘ └─────────┘ └──────────┘ │
└─────────────────────────────────────────┘
```

## Testing

```bash
# Run POSIX compliance checks
uv run python tests/run_posix_compliance_check.py

# Run audit for stale references
uv run agathos-audit --strict
```

## CLI Reference

| Command | Description |
|---------|-------------|
| `agathos` | Start daemon (foreground) |
| `agathos status` | Check daemon status |
| `agathos start` | Start daemon with service management |
| `agathos stop` | Stop daemon |
| `agathos setup` | Interactive configuration |
| `agathos-audit` | Audit for stale argus references |

## Documentation

- [Integration Analysis](AGATHOS-HERMES-INTEGRATION-ANALYSIS.md)
- [POSIX Compliance](POSIX_COMPLIANCE_AUDIT.md)
- [Venv Setup](VENV_SETUP.md)

## License

MIT

---

**Good code defends itself. Agathos ensures your agents do too.**
