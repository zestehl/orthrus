"""orthrus capture — Capture pipeline management."""

from __future__ import annotations

import asyncio
import signal
import threading
from typing import Annotated, Any

import structlog
import typer
import yaml

from orthrus.cli._console import (
    console,
    make_status_table,
    print_success,
    print_warning,
)
from orthrus.cli.commands.util import require_config
from orthrus.config import Config

capture_app = typer.Typer(name="capture", help="Capture pipeline management.")


async def _query_status(cfg: Config) -> dict[str, Any]:
    """Query capture status by instantiating CaptureManager briefly."""
    from orthrus.capture import CaptureManager
    from orthrus.storage import StorageManager, StoragePaths

    storage = StorageManager(cfg.storage, StoragePaths.resolve(cfg.paths))
    manager = CaptureManager(
        config=cfg.capture,
        storage=storage,
        embedding=None,
        capture_profile=cfg.profile.value,
        resource_profile=cfg.profile,
    )
    await manager.start()
    try:
        status = manager.status()
        return {
            "queue_depth": status.queue_depth,
            "queue_max": status.queue_max,
            "is_started": status.is_started,
            "is_draining": status.is_draining,
            "total_captured": status.total_captured,
            "embedding_enabled": status.embedding_enabled,
            "healthy": status.healthy,
        }
    finally:
        await manager.shutdown()


@capture_app.command("status")
def cmd_status() -> None:
    """Show capture pipeline status."""
    cfg = require_config()

    if not cfg.capture.enabled:
        print_warning("Capture is disabled (capture.enabled=false in config)")
        return

    status = asyncio.run(_query_status(cfg))

    table = make_status_table(title="[bold]Capture Status[/bold]")
    table.add_row("Queue depth", f"{status['queue_depth']} / {status['queue_max']}")
    table.add_row("Total captured", str(status["total_captured"]))
    table.add_row("Started", "Yes" if status["is_started"] else "No")
    table.add_row("Draining", "Yes" if status["is_draining"] else "No")
    table.add_row("Embedding", "Enabled" if status["embedding_enabled"] else "Disabled")
    table.add_row("Healthy", "[green]Yes[/green]" if status["healthy"] else "[red]No[/red]")
    console.print(table)


@capture_app.command("enable")
def cmd_enable(
    config_override: Annotated[
        str | None,
        typer.Option(
            "--config",
            "-c",
            help="Config file to modify (default: config file in use)",
        ),
    ] = None,
    path: Annotated[
        str | None,
        typer.Option(
            "--path",
            "-p",
            help="Path to save modified config (default: same as --config)",
        ),
    ] = None,
) -> None:
    """Enable capture."""
    _set_capture_enabled(enable=True, config_override=config_override, path=path)


@capture_app.command("disable")
def cmd_disable(
    config_override: Annotated[
        str | None,
        typer.Option(
            "--config",
            "-c",
            help="Config file to modify (default: config file in use)",
        ),
    ] = None,
    path: Annotated[
        str | None,
        typer.Option(
            "--path",
            "-p",
            help="Path to save modified config (default: same as --config)",
        ),
    ] = None,
) -> None:
    """Disable capture."""
    _set_capture_enabled(enable=False, config_override=config_override, path=path)


def _set_capture_enabled(
    enable: bool,
    config_override: str | None,
    path: str | None,
) -> None:
    """Helper to set capture.enabled and save."""
    from pathlib import Path

    # Determine target path
    if config_override:
        target = Path(config_override).expanduser().resolve()
    elif path:
        target = Path(path).expanduser().resolve()
    else:
        # Save to config file in use, or default location
        cfg = None
        try:
            from orthrus.config import load_config
            cfg = load_config()
        except Exception:
            pass
        if cfg is not None:
            # Find the file that was loaded
            from orthrus.config import default_config_search_paths
            for candidate in default_config_search_paths():
                if candidate.is_file():
                    target = candidate
                    break
            else:
                target = Path("~/.orthrus/config.yaml").expanduser().resolve()
        else:
            target = Path("~/.orthrus/config.yaml").expanduser().resolve()

    # Load or default
    if target.is_file():
        cfg = Config.from_file(target)
    else:
        cfg = Config.default()
        state = "enabled" if enable else "disabled"
        print_success(f"No config at {target}, creating with capture {state}")

    cfg.capture.enabled = enable
    target.parent.mkdir(parents=True, exist_ok=True)
    data = cfg.model_dump(mode="json")
    with open(target, "w", encoding="utf-8") as fh:
        yaml.dump(data, fh, default_flow_style=False, sort_keys=False)

    state = "[green]enabled[/green]" if enable else "[red]disabled[/red]"
    print_success(f"Capture {state} — saved to [dim]{target}[/dim]")


@capture_app.command("run")
def cmd_run() -> None:
    """Start the capture daemon (runs until SIGTERM/SIGINT)."""
    logger = structlog.get_logger(__name__)

    cfg = require_config()
    if not cfg.capture.enabled:
        console.print("[red]Capture is disabled. Run 'orthrus capture enable' first.[/red]")
        raise typer.Exit(code=1)

    from orthrus.capture import CaptureManager
    from orthrus.storage import StorageManager, StoragePaths

    storage = StorageManager(cfg.storage, StoragePaths.resolve(cfg.paths))
    manager = CaptureManager(
        config=cfg.capture,
        storage=storage,
        embedding=None,  # CLI mode: no async embedding
        capture_profile=cfg.profile.value,
        resource_profile=cfg.profile,
    )

    shutdown_event = threading.Event()

    def _sigterm_handler(signum: int, frame: object) -> None:
        logger.info("sigterm_received", signal=signum)
        shutdown_event.set()

    # Install signal handlers on the main thread
    signal.signal(signal.SIGTERM, _sigterm_handler)
    signal.signal(signal.SIGINT, _sigterm_handler)

    async def _run() -> None:
        await manager.start()
        try:
            while not shutdown_event.is_set():
                await asyncio.sleep(1)
        finally:
            await manager.shutdown(timeout_seconds=30.0)

    console.print("[dim]Orthrus capture daemon running. PID: "
                 f"{threading.main_thread().ident}[/dim]")
    console.print("[dim]Send SIGTERM or SIGINT to stop gracefully.[/dim]")

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        logger.info("sigint_received")
    except Exception as exc:
        logger.error("capture_daemon_error", error=str(exc), exc_info=True)
        raise typer.Exit(code=1) from exc

    console.print("[dim]Capture daemon stopped.[/dim]")
