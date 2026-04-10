"""Export configuration — format selection, quality, and deduplication settings."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ExportFormat(Enum):
    """Supported export formats for training data."""

    SHAREGPT = "sharegpt"
    DPO = "dpo"
    RAW = "raw"


@dataclass(frozen=True)
class ExportConfig:
    """Configuration for an export run.

    Attributes
    ----------
    format:
        Output format (sharegpt, dpo, raw).
    min_quality_score:
        Minimum quality score (0.0–1.0). Records below this are filtered out.
        Default 0.0 means no filtering.
    deduplicate:
        Whether to deduplicate records by embedding similarity.
        Default True.
    dedup_threshold:
        Cosine similarity threshold for deduplication (0.0–1.0).
        Records more similar than this to an already-selected record are
        skipped. Only used when deduplicate is True.
    include_fields:
        Which optional Turn fields to include in the output. If empty,
        all available fields are included.
    """

    format: ExportFormat = ExportFormat.SHAREGPT
    min_quality_score: float = 0.0
    deduplicate: bool = True
    dedup_threshold: float = 0.95
    include_fields: tuple[str, ...] = field(default_factory=lambda: ())

    def __post_init__(self) -> None:
        if not 0.0 <= self.min_quality_score <= 1.0:
            raise ValueError(
                f"min_quality_score must be in [0.0, 1.0], got {self.min_quality_score}"
            )
        if not 0.0 <= self.dedup_threshold <= 1.0:
            raise ValueError(
                f"dedup_threshold must be in [0.0, 1.0], got {self.dedup_threshold}"
            )
        if self.format not in ExportFormat:
            raise ValueError(f"format must be an ExportFormat, got {self.format!r}")
