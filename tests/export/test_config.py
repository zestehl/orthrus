"""Tests for ExportConfig and ExportFormat."""

import pytest

from orthrus.export import ExportConfig, ExportFormat


class TestExportFormat:
    def test_all_formats_present(self):
        assert ExportFormat.SHAREGPT.value == "sharegpt"
        assert ExportFormat.DPO.value == "dpo"
        assert ExportFormat.RAW.value == "raw"

    def test_format_is_enum(self):
        assert isinstance(ExportFormat.SHAREGPT, ExportFormat)


class TestExportConfig:
    def test_default_values(self):
        cfg = ExportConfig()
        assert cfg.format == ExportFormat.SHAREGPT
        assert cfg.min_quality_score == 0.0
        assert cfg.deduplicate is True
        assert cfg.dedup_threshold == 0.95
        assert cfg.include_fields == ()

    def test_custom_values(self):
        cfg = ExportConfig(
            format=ExportFormat.DPO,
            min_quality_score=0.7,
            deduplicate=False,
            dedup_threshold=0.99,
        )
        assert cfg.format == ExportFormat.DPO
        assert cfg.min_quality_score == 0.7
        assert cfg.deduplicate is False
        assert cfg.dedup_threshold == 0.99

    def test_quality_score_too_high_raises(self):
        with pytest.raises(ValueError, match="min_quality_score"):
            ExportConfig(min_quality_score=1.5)

    def test_quality_score_negative_raises(self):
        with pytest.raises(ValueError, match="min_quality_score"):
            ExportConfig(min_quality_score=-0.1)

    def test_dedup_threshold_too_high_raises(self):
        with pytest.raises(ValueError, match="dedup_threshold"):
            ExportConfig(dedup_threshold=1.01)

    def test_dedup_threshold_negative_raises(self):
        with pytest.raises(ValueError, match="dedup_threshold"):
            ExportConfig(dedup_threshold=-0.01)

    def test_quality_boundary_0(self):
        cfg = ExportConfig(min_quality_score=0.0)
        assert cfg.min_quality_score == 0.0

    def test_quality_boundary_1(self):
        cfg = ExportConfig(min_quality_score=1.0)
        assert cfg.min_quality_score == 1.0

    def test_dedup_boundary_0(self):
        cfg = ExportConfig(dedup_threshold=0.0)
        assert cfg.dedup_threshold == 0.0

    def test_dedup_boundary_1(self):
        cfg = ExportConfig(dedup_threshold=1.0)
        assert cfg.dedup_threshold == 1.0
