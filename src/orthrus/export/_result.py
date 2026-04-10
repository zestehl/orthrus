"""ExportResult — statistics returned from an export run."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ExportResult:
    """Statistics from a completed export run.

    Attributes
    ----------
    records_total:
        Total records scanned from storage.
    records_exported:
        Records written to the output file (after filtering and dedup).
    records_filtered:
        Records skipped due to quality threshold or schema.
    records_duplicates:
        Records skipped as duplicates.
    quality_distribution:
        Histogram of quality scores. Keys are bin labels
        ("0.0-0.2", "0.2-0.4", "0.4-0.6", "0.6-0.8", "0.8-1.0"),
        values are record counts.
    format:
        Export format used (sharegpt, dpo, raw).
    output_path:
        Path to the file that was written.
    error:
        Error message if the export failed, otherwise None.
    """

    records_total: int = 0
    records_exported: int = 0
    records_filtered: int = 0
    records_duplicates: int = 0
    quality_distribution: dict[str, int] = field(default_factory=dict)
    format: str = "sharegpt"
    output_path: str | None = None
    error: str | None = None

    @property
    def success(self) -> bool:
        """Return True if the export completed without errors."""
        return self.error is None

    def _bin_quality(self, score: float) -> str:
        """Return the quality bin label for a score."""
        if score < 0.2:
            return "0.0-0.2"
        if score < 0.4:
            return "0.2-0.4"
        if score < 0.6:
            return "0.4-0.6"
        if score < 0.8:
            return "0.6-0.8"
        return "0.8-1.0"
