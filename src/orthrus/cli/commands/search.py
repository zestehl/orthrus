"""orthrus search — Search captured turns (P1)."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.panel import Panel

from orthrus.cli._console import console

search_app = typer.Typer(name="search", help="Search captured turns.")


@search_app.command()
def cmd_search(
    query: Annotated[str, typer.Argument(help="Search query text")],
    vector_from: Annotated[
        str | None,
        typer.Option("--vector-from", help="Search by semantic similarity to TEXT"),
    ] = None,
    top_k: Annotated[
        int,
        typer.Option("--top-k", "-k", help="Maximum results to return"),
    ] = 10,
    session: Annotated[
        str | None,
        typer.Option("--session", "-s", help="Filter by session ID"),
    ] = None,
    format: Annotated[
        str,
        typer.Option("--format", "-f", help="Output format: text (default) or json"),
    ] = "text",
) -> None:
    """Search captured turns by query."""
    console.print(Panel(
        "[bold yellow]search[/bold yellow] is not yet implemented.\n\n"
        "The [cyan]search[/cyan] module (P1) is pending development.\n"
        "File an issue: [link]https://github.com/your-org/orthrus[/link]",
        title="[bold]P1 — Not Yet Implemented[/bold]",
        border_style="yellow",
        expand=False,
    ))
    raise typer.Exit(code=1)
