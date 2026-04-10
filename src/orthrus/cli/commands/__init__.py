"""Orthrus CLI command groups."""

from orthrus.cli.commands.capture import capture_app
from orthrus.cli.commands.config import config_app

__all__ = [
    "capture_app",
    "config_app",
]
