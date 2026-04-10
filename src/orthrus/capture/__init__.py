"""Orthrus capture module — Turn data structures and async ingest pipeline.

Public API:
    CaptureManager  — async ingest manager with back-pressure queue
    CaptureConfig   — configuration for capture pipeline
    TurnData        — validated input dataclass for capture()
    CaptureResult   — result returned from capture()
    CaptureStatus   — pipeline health snapshot
    EmbeddingBackend — Protocol for optional async embedding
    CaptureError    — base exception
    Turn            — atomic turn dataclass (from turn.py)
    ToolCall        — tool call record (from turn.py)
    TurnOutcome     — outcome enum (from turn.py)
    generate_uuid7  — UUID7 generation (from _uuid7.py)
"""

from orthrus.capture._manager import (
    CaptureDisabledError,
    CaptureError,
    CaptureManager,
    CaptureNotStartedError,
)
from orthrus.capture._worker import EmbeddingBackend
from orthrus.capture.turn import (
    ToolCall,
    Turn,
    TurnOutcome,
)
from orthrus.capture.turn_data import (
    CaptureResult,
    CaptureStatus,
    TurnData,
)
from orthrus.config import CaptureConfig

__all__ = [
    # Manager
    "CaptureManager",
    "CaptureError",
    "CaptureNotStartedError",
    "CaptureDisabledError",
    # Config
    "CaptureConfig",
    # Data classes
    "TurnData",
    "CaptureResult",
    "CaptureStatus",
    # Embedding protocol
    "EmbeddingBackend",
    # Re-exports from turn.py
    "Turn",
    "ToolCall",
    "TurnOutcome",
]
