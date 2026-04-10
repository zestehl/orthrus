"""Orthrus CLI — Entry point for the Orthrus monitoring system."""

import sys


def main() -> int:
    """Main entry point for Orthrus CLI."""
    try:
        from orthrus.legacy.cli import main as legacy_main  # type: ignore[import-untyped]

        return legacy_main()  # type: ignore[no-any-return]
    except ImportError:
        print("Orthrus CLI not yet fully implemented.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
