"""orthrus sync — Sync storage to remote targets."""

from __future__ import annotations

from typing import Annotated

import structlog
import typer
from rich.table import Table

from orthrus.cli._console import console
from orthrus.cli.commands.util import get_config, get_storage_paths
from orthrus.sync._manager import SyncManager

sync_app = typer.Typer(name="sync", help="Sync storage to remote targets.")
logger = structlog.get_logger(__name__)


@sync_app.command()
def cmd_sync(
    target: Annotated[
        str | None,
        typer.Option("--target", "-t", help="Sync to a specific target by name"),
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
    """Sync captured data to configured remote targets."""
    try:
        cfg = get_config()
    except SystemExit:
        console.print("[yellow]No config file found. Using defaults.[/yellow]")
        from orthrus.config._models import Config
        cfg = Config()

    if not cfg.sync.enabled:
        msg = "Sync is disabled in config. Set sync.enabled: true to enable."
        console.print(f"[yellow]{msg}[/yellow]")
        raise typer.Exit(code=1)

    if not cfg.sync.targets:
        msg = "No sync targets configured. Add targets to sync.targets in your config."
        console.print(f"[yellow]{msg}[/yellow]")
        raise typer.Exit(code=1)

    try:
        storage_paths = get_storage_paths(cfg)
        manager = SyncManager(cfg.sync, storage_paths=storage_paths)
    except Exception as exc:
        console.print(f"[red]Failed to initialize sync manager: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    # Verify targets first
    console.print("[dim]Verifying targets...[/dim]")
    status = manager.verify_targets()
    unreachable = [name for name, ok in status.items() if not ok]
    if unreachable:
        console.print(f"[red]Unreachable targets: {', '.join(unreachable)}[/red]")
        if not dry_run:
            raise typer.Exit(code=1)

    # Run sync
    console.print(f"[dim]Syncing to {[h.target.name for h in manager._targets]}...[/dim]")
    result = manager.sync(dry_run=dry_run, verbose=verbose, target_name=target)

    # Report
    table = Table(title="Sync Result", show_header=True)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Success", "✓" if result.success else "✗")
    table.add_row("Files transferred", str(result.files_transferred))
    table.add_row("Bytes transferred", _fmt_bytes(result.bytes_transferred))
    table.add_row("Errors", str(len(result.errors)))

    console.print(table)

    if result.errors:
        console.print("[red]Errors:[/red]")
        for err in result.errors:
            console.print(f"  • {err}")

    if not result.success:
        raise typer.Exit(code=1)


def _fmt_bytes(n: int) -> str:
    """Format bytes as human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"
