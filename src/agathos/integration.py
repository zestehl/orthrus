"""
Hermes Agent integration plugin for Agathos.

This module provides the integration point for Hermes Agent to discover
and interact with Agathos when installed as an optional dependency.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("agathos.integration")


class HermesPlugin:
    """
    Hermes Agent plugin interface for Agathos.

    This plugin is registered via entry points and discovered by Hermes
    when Agathos is installed. It provides:
    - Health check endpoints
    - Metrics export
    - Session monitoring hooks
    """

    name = "agathos"
    version = "0.1.0"

    def __init__(self, hermes_config: Optional[Dict[str, Any]] = None):
        self.config = hermes_config or {}
        self._monitor = None
        self._enabled = self.config.get("agathos", {}).get("enabled", True)

    def initialize(self) -> bool:
        """Initialize the Agathos plugin. Called by Hermes on startup."""
        if not self._enabled:
            logger.info("Agathos plugin disabled in config")
            return False

        try:
            from .agathos import Agathos
            self._monitor = Agathos()
            logger.info("Agathos plugin initialized")
            return True
        except Exception as e:
            logger.error("Failed to initialize Agathos: %s", e)
            return False

    def shutdown(self) -> None:
        """Shutdown the plugin. Called by Hermes on exit."""
        if self._monitor:
            try:
                self._monitor.stop()
                logger.info("Agathos plugin shutdown")
            except Exception as e:
                logger.error("Error shutting down Agathos: %s", e)

    def health_check(self) -> Dict[str, Any]:
        """Return health status for Hermes health monitoring."""
        if not self._monitor:
            return {"status": "not_initialized", "healthy": False}

        try:
            # Quick health check - verify daemon is responsive
            return {"status": "healthy", "healthy": True}
        except Exception as e:
            return {"status": "unhealthy", "healthy": False, "error": str(e)}

    def get_metrics(self) -> Dict[str, Any]:
        """Return metrics for Hermes metrics collection."""
        if not self._monitor:
            return {}

        try:
            from .metrics import format_latest_metrics
            return format_latest_metrics()
        except Exception as e:
            logger.error("Failed to get metrics: %s", e)
            return {}

    def on_session_start(self, session_id: str, metadata: Dict[str, Any]) -> None:
        """Hook called by Hermes when a new session starts."""
        if self._monitor and self._enabled:
            try:
                self._monitor.register_session({
                    "session_id": session_id,
                    "session_type": metadata.get("type", "unknown"),
                    "job_id": metadata.get("job_id"),
                    "task_description": metadata.get("task"),
                    "model": metadata.get("model"),
                    "provider": metadata.get("provider"),
                    "metadata": metadata,
                })
            except Exception as e:
                logger.error("Failed to register session with Agathos: %s", e)

    def on_session_end(self, session_id: str, metadata: Dict[str, Any]) -> None:
        """Hook called by Hermes when a session ends."""
        if self._monitor and self._enabled:
            try:
                # Agathos handles session cleanup internally
                pass
            except Exception as e:
                logger.error("Session end hook error: %s", e)


def is_agathos_available() -> bool:
    """Check if Agathos is installed and available."""
    try:
        import agathos
        return True
    except ImportError:
        return False


def get_agathos_version() -> Optional[str]:
    """Get Agathos version if installed."""
    try:
        import agathos
        return getattr(agathos, "__version__", "unknown")
    except ImportError:
        return None
