# Module: cli

---
status: implemented
priority: P0
implemented: 2026-04-10
tested: 168/168 tests passing
---

## Responsibility

Command-line interface for Orthrus. Orchestrates all other modules.

**In scope:**
- Command parsing and dispatch via Typer 0.24.1
- Rich terminal output (panels, tables, styled text)
- Subcommands: capture, search, export, sync, config
- Global flags: --config, --verbose
- Shell completion for all commands

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
orthrus --verbose <command>

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

## Dependencies

- **All other modules**: CLI orchestrates
- **external**: typer==0.24.1, rich==14.0.0

## Resource Contract

- CLI startup <500ms
- Graceful degradation if modules unavailable
- Rich renders only on terminals (auto-detected)

## Error Handling

All errors print to stderr with Rich styling. Exit codes:
- `0` — success
- `1` — application error (not found, validation failure)
- `2` — invalid CLI usage (bad arguments)

## Testing

- Unit: Command parsing
- Integration: End-to-end with temp directories
- Property: Invalid inputs produce error codes

## File Structure

```
src/orthrus/
├── cli.py                    # Entry point (orthrus command)
└── cli/
    ├── __init__.py           # Typer app, global --config/--verbose, subcommand registration
    ├── _console.py           # Shared Rich console, styled print helpers
    └── commands/
        ├── __init__.py       # Sub-app exports (capture_app, config_app)
        ├── config.py         # config init / validate / show  (typer.Typer sub-app)
        ├── capture.py        # capture status / enable / disable  (typer.Typer sub-app)
        ├── search.py         # search <query>  (direct @app.command)
        ├── export.py         # export --output <path>  (direct @app.command)
        ├── sync.py           # sync [--target]  (direct @app.command)
        └── util.py           # get_config(), require_config() helpers
```

## Implementation Notes

### Typer 0.24.1 Patterns

- `typer.Typer()` as root app + `add_typer()` for subcommand groups
- `Annotated[Type, typer.Option()]` / `Annotated[Type, typer.Argument()]` for typed options
- `typer.Option(is_eager=True)` on `--config` so config is loaded before subcommand parsing
- `typer.BadParameter()` for validation errors on individual options
- `typer.Exit(code=N)` for clean early termination with specific exit codes
- `pretty_exceptions_enable=False` to disable Rich traceback formatting at the app level

### Rich Output

- `Console(stderr=True)` dedicated console for error output
- `Panel` for boxed messages (config display, not-implemented stubs)
- `Table` with `show_header=False` for key/value output
- `rich.markup` inline (`[bold]`, `[cyan]`, `[green]`, etc.) for styled inline text
- Custom `Theme` with semantic tokens (`info`, `success`, `warning`, `error`)

### Command Organization

- `capture` and `config` have multiple sub-commands → `typer.Typer()` sub-apps registered via `add_typer()`
- `search`, `export`, `sync` are single commands → registered directly via `@app.command(name="...")`
- `get_config()` is called lazily in command bodies, not in `main` callback, so `--help` works without a config file
