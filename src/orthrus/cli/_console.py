"""Shared Rich console and output utilities for orthrus CLI."""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.theme import Theme

_custom_theme = Theme({
    "info": "cyan",
    "success": "green",
    "warning": "yellow",
    "error": "bold red",
    "muted": "dim",
    "header": "bold cyan",
})

console = Console(theme=_custom_theme)
err_console = Console(theme=_custom_theme, stderr=True)


def print_info(msg: str) -> None:
    console.print(f"[info]ℹ[/info] {msg}")


def print_success(msg: str) -> None:
    console.print(f"[success]✓[/success] {msg}")


def print_warning(msg: str) -> None:
    console.print(f"[warning]⚠[/warning] {msg}")


def print_error(msg: str) -> None:
    err_console.print(f"[error]✗[/error] {msg}")


def print_panel(title: str, content: str, *, style: str = "cyan") -> None:
    console.print(Panel(content, title=title, border_style=style))


def make_key_value_table(rows: list[tuple[str, str]], title: str | None = None) -> Table:
    """Build a two-column key/value table."""
    table = Table(box=None, show_header=False, padding=(0, 2), title=title)
    table.add_column("key", style="bold")
    table.add_column("value", style="")
    for k, v in rows:
        table.add_row(k, v)
    return table


def make_status_table(title: str | None = None) -> Table:
    """Build a status table with header-style columns."""
    table = Table(
        box=None,
        show_header=True,
        header_style="header",
        title=title,
        pad_edge=False,
    )
    table.add_column("Property", style="bold cyan", justify="left")
    table.add_column("Value", style="", justify="left")
    return table
