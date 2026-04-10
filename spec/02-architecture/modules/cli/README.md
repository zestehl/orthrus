# Module: cli

---
status: not-started
priority: P0
---

## Responsibility

Command-line interface for Orthrus. Orchestrates all other modules.

**In scope:**
- Command parsing and dispatch
- Subcommands: capture, search, export, sync, config
- Global flags: --config, --verbose, --version
- Error handling and user messages

**Out of scope:**
- Web UI (future)
- Interactive TUI (future)
- Configuration file editing (separate command)

## Interface

### Commands

```bash
# Global
orthrus --version
orthrus --config ~/.orthrus/config.yaml <command>

# Capture management
orthrus capture status
orthrus capture enable
orthrus capture disable

# Search
orthrus search "query"
orthrus search --vector-from "text" --top-k 5
orthrus search --session <uuid>

# Export
orthrus export --format sharegpt --output train.jsonl
orthrus export --format dpo --min-quality 0.8

# Sync
orthrus sync --dry-run
orthrus sync --target <name>

# Config
orthrus config init
orthrus config validate
orthrus config show
```

### Error Output

```
error: <clear message>
help: <suggestion to fix>
```

## Dependencies

- **All other modules**: CLI orchestrates
- **external**: argparse (stdlib) or typer (optional)

## Resource Contract

- CLI startup <500ms
- Graceful degradation if modules unavailable

## Testing

- Unit: Command parsing
- Integration: End-to-end with temp directories
- Property: Invalid inputs produce error codes
