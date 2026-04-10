"""orthrus export — Export turns to training formats (ShareGPT, DPO, Raw)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from orthrus.cli._console import console
from orthrus.config._models import load_config
from orthrus.export import ExportConfig, Exporter, ExportFormat
from orthrus.storage._manager import StorageManager

export_app = typer.Typer(name="export", help="Export turns to training formats.")


def _parse_datetime(value: str | None) -> datetime | None:
    """Parse an ISO-8601 datetime string to UTC-aware datetime."""
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        # Handle dates with or without time
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=None)  # naive — treated as UTC
        return dt
    except ValueError:
        raise typer.BadParameter(f"Invalid ISO-8601 datetime: {value!r}") from None


@export_app.command()
def cmd_export(
    output: Annotated[
        str,
        typer.Option("--output", "-o", help="Output JSONL file path"),
    ],
    format: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help="Export format: sharegpt, dpo, or raw (default: sharegpt)",
        ),
    ] = "sharegpt",
    min_quality: Annotated[
        float,
        typer.Option("--min-quality", help="Minimum quality score 0.0-1.0 (default: 0.0)"),
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
    rich_console = Console()

    # Validate format
    fmt_lower = format.lower().strip()
    valid_formats = {"sharegpt", "dpo", "raw"}
    if fmt_lower not in valid_formats:
        raise typer.BadParameter(
            f"Invalid format {format!r}. Must be one of: {', '.join(sorted(valid_formats))}"
        )
    export_format = ExportFormat(fmt_lower)

    # Validate min_quality
    if not (0.0 <= min_quality <= 1.0):
        raise typer.BadParameter(
            f"--min-quality must be in [0.0, 1.0], got {min_quality}"
        )

    # Parse since
    since_dt = _parse_datetime(since)

    # Resolve output path
    output_path = Path(output).expanduser().resolve()

    # Load config and build storage
    try:
        config = load_config()
    except Exception as exc:
        console.print(f"[red]Failed to load config:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    storage = StorageManager(config.storage)

    # Build export config
    export_config = ExportConfig(
        format=export_format,
        min_quality_score=min_quality,
        deduplicate=True,
        dedup_threshold=0.95,
    )

    exporter = Exporter(storage=storage, config=export_config, config_root=config)

    console.print(
        f"[dim]Exporting to[/dim] [cyan]{output_path}[/cyan] "
        f"[dim]format={fmt_lower}, min_quality={min_quality}[/dim]"
    )

    result = exporter.export(
        output_path=output_path,
        since=since_dt,
        session_id=session,
    )

    if not result.success:
        console.print(f"[red]Export failed:[/red] {result.error}")
        raise typer.Exit(code=1)

    # Render results table
    table = Table(title="Export Summary", show_header=True, header_style="bold")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", justify="right", style="white")

    table.add_row("Total scanned", str(result.records_total))
    table.add_row("Exported", str(result.records_exported))
    table.add_row("Filtered", str(result.records_filtered))
    table.add_row("Duplicates", str(result.records_duplicates))
    table.add_row("Format", result.format)
    if result.output_path:
        table.add_row("Output", result.output_path)

    rich_console.print(table)

    # Quality distribution
    if result.quality_distribution:
        dist_table = Table(
            title="Quality Distribution",
            show_header=True,
            header_style="bold",
        )
        dist_table.add_column("Quality Band", style="cyan")
        dist_table.add_column("Count", justify="right", style="white")
        for band in ["0.0-0.2", "0.2-0.4", "0.4-0.6", "0.6-0.8", "0.8-1.0"]:
            count = result.quality_distribution.get(band, 0)
            dist_table.add_row(band, str(count))
        rich_console.print(dist_table)

    if result.records_exported == 0:
        console.print(
            "[yellow]Warning: No records exported. "
            "Check --since and --min-quality settings.[/yellow]"
        )
    else:
        console.print(
            f"[green]Export complete:[/green] {result.records_exported} records written."
        )
