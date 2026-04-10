"""Export formatters — pluggable output format handlers.

Each formatter implements the ExportFormatter protocol and is responsible
for converting a single Turn into the format's JSON-serializable record.

Built-in formatters
-------------------
ShareGPTFormatter : ShareGPT conversation format
DPOFormatter      : DPO preference-pair format
RawFormatter      : Pass-through of all Turn fields
"""

from __future__ import annotations

from orthrus.export._formats._dpo import DPOFormatter
from orthrus.export._formats._raw import RawFormatter
from orthrus.export._formats._sharegpt import ShareGPTFormatter

__all__ = [
    "ShareGPTFormatter",
    "DPOFormatter",
    "RawFormatter",
]
