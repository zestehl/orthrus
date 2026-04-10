"""Orthrus export module — training-format export for captured agent interactions.

Public API
----------
ExportFormat : Enum
    Supported export formats (ShareGPT, DPO, Raw).
ExportConfig : dataclass
    Export configuration (format, quality threshold, deduplication).
ExportResult : dataclass
    Statistics from an export run.
Exporter : class
    Main exporter — reads turns from storage and writes training files.

Example
-------
::

    from orthrus.export import Exporter, ExportConfig, ExportFormat
    from orthrus.config import load_config

    config = load_config()
    exporter = Exporter(storage_manager, ExportConfig(
        format=ExportFormat.SHAREGPT,
        min_quality_score=0.8,
    ))
    result = exporter.export(Path("train.jsonl"))
"""

from __future__ import annotations

from orthrus.export._config import ExportConfig, ExportFormat
from orthrus.export._exporter import Exporter, ExportError
from orthrus.export._result import ExportResult

__all__ = [
    "ExportConfig",
    "ExportFormat",
    "ExportResult",
    "ExportError",
    "Exporter",
]
