"""Orthrus CLI — Typer-based command-line interface.

Usage:
    orthrus [OPTIONS] COMMAND [OPTIONS]

Global options:
    --config PATH   Config file path
    -v, --verbose  Enable verbose output

Commands:
    capture          Capture pipeline management
    config           Config file management
    search           Search captured turns
    export           Export turns to training formats
    sync             Sync storage to remote targets
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from orthrus import __version__
from orthrus.cli._console import console
from orthrus.cli._console import print_error as print_error  # noqa: F401
from orthrus.cli.commands import capture_app, config_app
from orthrus.cli.commands.export import cmd_export
from orthrus.cli.commands.search import cmd_search
from orthrus.cli.commands.sync import cmd_sync

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="orthrus",
    help="Orthrus — Agentic Turn Capture System",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    pretty_exceptions_show_locals=False,
)


# ---------------------------------------------------------------------------
# Global state (set in callback)
# ---------------------------------------------------------------------------

_config_path: Path | None = None
_verbose = False


def get_config_path() -> Path | None:
    return _config_path


def is_verbose() -> bool:
    return _verbose


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"[bold]orthrus[/bold] [cyan]{__version__}[/cyan]")
        raise typer.Exit(code=0)


@app.callback(invoke_without_command=True)
def cli_callback(
    ctx: typer.Context,
    config: Annotated[
        Path | None,
        typer.Option(
            "--config",
            "-c",
            is_eager=True,
            help="Config file path",
        ),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable verbose output"),
    ] = False,
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            is_eager=True,
            callback=_version_callback,
            help="Show version and exit",
        ),
    ] = None,
) -> None:
    """Orthrus — Agentic Turn Capture System."""
    global _config_path, _verbose
    _config_path = config
    _verbose = verbose


# ---------------------------------------------------------------------------
# Subcommand groups (have sub-commands)
# ---------------------------------------------------------------------------

app.add_typer(capture_app, name="capture")
app.add_typer(config_app, name="config")


# ---------------------------------------------------------------------------
# Direct commands (single-command modules)
# ---------------------------------------------------------------------------

# These are registered directly on the main app so the command name is clean:
#   orthrus search <query>
#   orthrus export --output <path>
#   orthrus sync [--target NAME]
app.command(name="search")(cmd_search)
app.command(name="export")(cmd_export)
app.command(name="sync")(cmd_sync)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main_cli(argv: list[str] | None = None) -> int:
    """Invoke the CLI. Returns exit code."""
    try:
        app(argv, standalone_mode=True)
        return 0
    except typer.Exit as e:
        return e.exit_code
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 1
    except Exception:
        raise  # Let Typer's pretty_exceptions handle it


if __name__ == "__main__":
    raise SystemExit(main_cli())
