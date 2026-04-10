"""orthrus export — Export turns to training formats (P1)."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.panel import Panel

from orthrus.cli._console import console

export_app = typer.Typer(name="export", help="Export turns to training formats.")


@export_app.command()
def cmd_export(
    output: Annotated[
        str,
        typer.Option("--output", "-o", help="Output file path"),
    ],
    format: Annotated[
        str,
        typer.Option("--format", "-f", help="Export format: sharegpt (default), dpo, raw"),
    ] = "sharegpt",
    min_quality: Annotated[
        float,
        typer.Option("--min-quality", help="Minimum quality score (0.0–1.0)"),
    ] = 0.0,
    session: Annotated[
        str | None,
        typer.Option("--session", "-s", help="Export single session only"),
    ] = None,
    since: Annotated[
        str | None,
        typer.Option("--since", help="ISO-8601 date — export turns after this date"),
    ] = None,
) -> None:
    """Export captured turns to a training format."""
    console.print(Panel(
        "[bold yellow]export[/bold yellow] is not yet implemented.\n\n"
        "The [cyan]export[/cyan] module (P1) is pending development.\n"
        "File an issue: [link]https://github.com/your-org/orthrus[/link]",
        title="[bold]P1 — Not Yet Implemented[/bold]",
        border_style="yellow",
        expand=False,
    ))
    raise typer.Exit(code=1)
