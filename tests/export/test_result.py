"""Tests for ExportResult."""

import pytest

from orthrus.export import ExportResult


class TestExportResult:
    def test_default_values(self):
        result = ExportResult()
        assert result.records_total == 0
        assert result.records_exported == 0
        assert result.records_filtered == 0
        assert result.records_duplicates == 0
        assert result.quality_distribution == {}
        assert result.format == "sharegpt"
        assert result.output_path is None
        assert result.error is None
        assert result.success is True

    def test_success_property_error_none(self):
        result = ExportResult(error=None)
        assert result.success is True

    def test_success_property_error_set(self):
        result = ExportResult(error="something went wrong")
        assert result.success is False

    def test_with_values(self):
        result = ExportResult(
            records_total=100,
            records_exported=80,
            records_filtered=15,
            records_duplicates=5,
            quality_distribution={"0.8-1.0": 50, "0.6-0.8": 30},
            format="dpo",
            output_path="/tmp/train.jsonl",
            error=None,
        )
        assert result.records_total == 100
        assert result.records_exported == 80
        assert result.records_filtered == 15
        assert result.records_duplicates == 5
        assert result.format == "dpo"
        assert result.output_path == "/tmp/train.jsonl"
        assert result.success is True

    def test_frozen(self):
        result = ExportResult()
        with pytest.raises(Exception):  # frozen dataclass
            result.records_total = 10
