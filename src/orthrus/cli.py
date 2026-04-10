"""Orthrus CLI — Entry point for the orthrus command-line interface.

Installed via pyproject.toml as the `orthrus` command.
"""

from __future__ import annotations

import sys


def main() -> int:
    """Entry point for the `orthrus` CLI (installed via pyproject.toml)."""
    from orthrus.cli import main_cli

    try:
        return main_cli()
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
