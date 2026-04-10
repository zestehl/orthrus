"""orthrus search — Search captured turns (text, vector, or hybrid)."""

from __future__ import annotations

import json
from typing import Annotated

import typer

from orthrus.cli._console import console
from orthrus.cli.commands.util import get_config
from orthrus.embedding import TransformersBackend
from orthrus.search import SearchManager, SearchQuery
from orthrus.storage._manager import StorageManager

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
    mode: Annotated[
        str,
        typer.Option(
            "--mode",
            "-m",
            help="Search mode: auto, text, vector, hybrid",
        ),
    ] = "auto",
    format: Annotated[
        str,
        typer.Option("--format", "-f", help="Output format: text (default) or json"),
    ] = "text",
) -> None:
    """Search captured turns by query text or semantic similarity."""
    if mode not in {"auto", "text", "vector", "hybrid"}:
        raise typer.BadParameter(
            f"--mode must be one of: auto, text, vector, hybrid (got {mode!r})"
        )

    filters: dict[str, object] = {}
    if session:
        filters["session_id"] = session

    try:
        config = get_config()
    except Exception as exc:
        console.print(f"[red]Failed to load config:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    storage = StorageManager(config.storage)

    # Build query
    if vector_from:
        # Semantic search: embed the vector_from text, then search by similarity
        backend = TransformersBackend()
        embeddings = backend.encode([vector_from])
        vector: list[float] = embeddings[0]
        search_query = SearchQuery(
            text=query,
            vector=vector,
            mode="vector",
            filters=filters,
            max_results=top_k,
        )
        # backend not needed for SearchManager when vector is pre-computed
        manager = SearchManager(storage=storage, embedding=None, index_dir=None)
    else:
        # Text or hybrid search
        embedding_backend: TransformersBackend | None = None
        if mode in {"auto", "hybrid"}:
            embedding_backend = TransformersBackend()

        manager = SearchManager(
            storage=storage,
            embedding=embedding_backend,
            index_dir=None,
        )
        search_query = SearchQuery(
            text=query,
            mode=mode,  # type: ignore[arg-type]  # validated above
            filters=filters,
            max_results=top_k,
        )

    try:
        results = manager.search(search_query)
    except Exception as exc:
        console.print(f"[red]Search failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if format == "json":
        output = [
            {
                "trace_id": r.trace_id,
                "score": r.score,
                "query_text": r.turn_data.get("query_text"),
                "response_text": r.turn_data.get("response_text"),
                "session_id": r.turn_data.get("session_id"),
                "outcome": r.turn_data.get("outcome"),
            }
            for r in results
        ]
        console.print(json.dumps(output, indent=2, default=str))
    else:
        if not results:
            console.print("[dim]No results found.[/dim]")
            return

        from rich.table import Table

        table = Table(title=f"[bold]Search Results ({len(results)})[/bold]")
        table.add_column("Score", style="cyan", justify="right", width=7)
        table.add_column("Trace ID", style="dim", width=16)
        table.add_column("Session", style="dim", width=16)
        table.add_column("Query", style="white")

        for r in results:
            q = r.turn_data.get("query_text", "")
            q = q[:80] + "..." if len(q) > 80 else q
            table.add_row(
                f"{r.score:.4f}",
                r.trace_id[:16],
                r.turn_data.get("session_id", "")[:16],
                q,
            )

        console.print(table)
