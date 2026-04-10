"""Shared utilities for orthrus CLI commands."""

from __future__ import annotations

import pathlib

import typer

from orthrus.cli._console import print_error
from orthrus.config import Config, ConfigFileNotFoundError
from orthrus.storage._paths import StoragePaths

__all__: list[str] = ["get_config", "require_config", "get_storage_paths"]


def _get_config_path_from_cli() -> pathlib.Path | None:
    """Late import to avoid circular reference."""
    from orthrus.cli import get_config_path
    return get_config_path()


def get_config() -> Config:
    """Load the orthrus config, raising a rich error on failure."""
    path = _get_config_path_from_cli()
    if path is not None:
        return Config.from_file(path)

    try:
        from orthrus.config import load_config
        return load_config()
    except ConfigFileNotFoundError:
        print_error("No config file found. Run 'orthrus config init' first.")
        raise typer.Exit(code=1) from None


def require_config() -> Config:
    """Alias for get_config — exists for readability in commands that need a file."""
    return get_config()


def get_storage_paths(cfg: Config) -> StoragePaths:
    """Build StoragePaths from config."""
    return StoragePaths.from_config(cfg)
