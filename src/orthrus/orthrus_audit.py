"""Orthrus audit module."""

import sys


def main() -> int:
    """Audit entry point."""
    try:
        from orthrus.legacy.orthrus_audit import main as legacy_main  # type: ignore[import-untyped]

        return legacy_main()  # type: ignore[no-any-return]
    except ImportError:
        print("Orthrus audit not yet fully implemented.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
