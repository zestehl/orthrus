"""orthrus config — Config file management."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
import yaml
from rich.panel import Panel

from orthrus.cli._console import console, print_success
from orthrus.cli.commands.util import get_config
from orthrus.config import Config

config_app = typer.Typer(name="config", help="Config file management.")


@config_app.command("init")
def cmd_init(
    path: Annotated[
        Path,
        typer.Option(
            "--path",
            "-p",
            help="Output path",
        ),
    ] = Path("~/.orthrus/config.yaml"),
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Overwrite existing file"),
    ] = False,
) -> None:
    """Create a default config file."""
    resolved = path.expanduser().resolve()
    if resolved.exists() and not force:
        raise typer.BadParameter(f"{resolved} already exists (use --force to overwrite)")

    cfg = Config.default()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    data = cfg.model_dump(mode="json")
    with open(resolved, "w", encoding="utf-8") as fh:
        yaml.dump(data, fh, default_flow_style=False, sort_keys=False)

    print_success(f"Created default config at [dim]{resolved}[/dim]")


@config_app.command("validate")
def cmd_validate() -> None:
    """Validate the current config."""
    cfg = get_config()
    _ = cfg
    print_success("Config is valid.")


@config_app.command("show")
def cmd_show() -> None:
    """Display the effective config."""
    cfg = get_config()
    data = cfg.model_dump(mode="json")
    output = yaml.dump(data, default_flow_style=False, sort_keys=False)
    console.print(Panel(
        f"[dim]{output}[/dim]",
        title="[bold]Effective Config[/bold]",
        border_style="cyan",
        expand=False,
        padding=(1, 2),
    ))
