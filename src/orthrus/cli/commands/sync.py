"""orthrus sync — Sync storage to remote targets (P2)."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.panel import Panel

from orthrus.cli._console import console
from orthrus.cli.commands.util import get_config

sync_app = typer.Typer(name="sync", help="Sync storage to remote targets.")


@sync_app.command()
def cmd_sync(
    target: Annotated[
        str | None,
        typer.Option("--target", "-t", help="Sync target name from config"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show what would be synced without making changes"),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show detailed sync operations"),
    ] = False,
) -> None:
    """Sync storage to configured remote targets."""
    try:
        cfg = get_config()
    except SystemExit:
        # No config file — show not-implemented panel
        console.print(Panel(
            "[bold yellow]sync[/bold yellow] is not yet implemented.\n\n"
            "The [cyan]sync[/cyan] module (P2) is pending development.\n"
            "File an issue: [link]https://github.com/your-org/orthrus[/link]",
            title="[bold]P2 — Not Yet Implemented[/bold]",
            border_style="yellow",
            expand=False,
        ))
        raise typer.Exit(code=1) from None

    if not cfg.sync.enabled:
        console.print(Panel(
            "[bold red]sync[/bold red] is not enabled.\n\n"
            "Set [cyan]sync.enabled: true[/cyan] and add targets to your config.",
            title="[bold]Sync Disabled[/bold]",
            border_style="red",
            expand=False,
        ))
        raise typer.Exit(code=1)

    console.print(Panel(
        "[bold yellow]sync[/bold yellow] is not yet implemented.\n\n"
        "The [cyan]sync[/cyan] module (P2) is pending development.\n"
        "File an issue: [link]https://github.com/your-org/orthrus[/link]",
        title="[bold]P2 — Not Yet Implemented[/bold]",
        border_style="yellow",
        expand=False,
    ))
    raise typer.Exit(code=1)
