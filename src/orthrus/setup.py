"""Orthrus setup module."""

import sys


def main() -> int:
    """Setup entry point."""
    try:
        from orthrus.legacy.setup import main as legacy_main  # type: ignore[import-untyped]

        return legacy_main()  # type: ignore[no-any-return]
    except ImportError:
        print("Orthrus setup not yet fully implemented.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
