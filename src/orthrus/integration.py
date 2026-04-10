"""Orthrus Hermes integration plugin."""


class HermesPlugin:
    """Hermes plugin integration for Orthrus."""

    def __init__(self) -> None:
        """Initialize the Orthrus Hermes plugin."""
        self.name = "orthrus"

    def health_check(self) -> dict[str, str]:
        """Return health status for Hermes integration."""
        return {"status": "ok", "plugin": self.name}
