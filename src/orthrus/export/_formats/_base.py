"""ExportFormatter Protocol — interface for all export format handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from orthrus.capture.turn import Turn


class ExportFormatter(Protocol):
    """Pluggable export format handler.

    Each formatter handles one output format (ShareGPT, DPO, Raw).
    Formatters are stateless — they only define how a Turn maps to
    a JSON-serializable output record.
    """

    @property
    def format_name(self) -> str:
        """Unique identifier for this format (e.g., 'sharegpt', 'dpo')."""

    def format(self, turn: Turn) -> dict[str, object] | None:
        """Convert a single Turn into a JSON-serializable output record.

        Args:
            turn: A validated Turn instance.

        Returns:
            A dict ready for ``json.dumps``, or None to skip this turn
            (e.g., required fields are missing).
        """
