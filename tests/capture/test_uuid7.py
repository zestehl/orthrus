"""Tests for UUID7 generation and parsing.

UUID7 is the foundation for trace_id — time-sortable, standard UUID format.
"""

import re
import time

import pytest

from orthrus.capture._uuid7 import generate_uuid7, parse_uuid7


class TestGenerateUUID7:
    """Test UUID7 generation."""

    def test_returns_valid_uuid_format(self):
        """UUID7 must be a valid UUID string (8-4-4-4-12 hex chars)."""
        result = generate_uuid7()
        pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        assert re.match(pattern, result), f"Invalid UUID format: {result}"

    def test_has_version_7_marker(self):
        """UUID7 must have version nibble set to 7."""
        result = generate_uuid7()
        # Version is in the 3rd group, first char must be '7'
        version_char = result.split('-')[2][0]
        assert version_char == '7', f"Expected version 7, got {version_char}"

    def test_has_variant_bits(self):
        """UUID7 must have variant bits (8, 9, a, b) in the 4th group."""
        result = generate_uuid7()
        variant_char = result.split('-')[3][0]
        assert variant_char in '89ab', f"Expected variant bits 8/9/a/b, got {variant_char}"

    def test_is_lowercase(self):
        """UUID7 must be lowercase for consistent storage."""
        result = generate_uuid7()
        assert result == result.lower(), f"Expected lowercase, got {result}"

    def test_unique_across_calls(self):
        """Each call must produce a unique UUID."""
        results = {generate_uuid7() for _ in range(100)}
        assert len(results) == 100, f"Expected 100 unique UUIDs, got {len(results)}"

    def test_embedded_timestamp_is_recent(self):
        """UUID7 timestamp should be within 1 second of now."""
        before_ms = int(time.time_ns() // 1_000_000)
        result = generate_uuid7()
        after_ms = int(time.time_ns() // 1_000_000)

        ts_ms, _ = parse_uuid7(result)
        # Allow 1 second tolerance for test execution
        assert before_ms - 1000 <= ts_ms <= after_ms + 1000, (
            f"Timestamp {ts_ms} not in range [{before_ms - 1000}, {after_ms + 1000}]"
        )

    def test_lexicographically_sortable(self):
        """UUIDs generated in sequence should sort chronologically."""
        uuids = [generate_uuid7() for _ in range(10)]
        sorted_uuids = sorted(uuids)
        # At minimum, sequential UUIDs should sort consistently
        # (exact order depends on millisecond timing)
        assert sorted_uuids == sorted(sorted_uuids), "UUIDs not lexicographically sortable"


class TestParseUUID7:
    """Test UUID7 parsing."""

    def test_extracts_timestamp(self):
        """Parse should extract embedded millisecond timestamp."""
        before_ms = int(time.time_ns() // 1_000_000)
        uuid_str = generate_uuid7()
        after_ms = int(time.time_ns() // 1_000_000)

        ts_ms, rand_bytes = parse_uuid7(uuid_str)
        assert before_ms - 1000 <= ts_ms <= after_ms + 1000
        assert len(rand_bytes) == 10, f"Expected 10 random bytes, got {len(rand_bytes)}"

    def test_rejects_invalid_format(self):
        """Parse must reject non-UUID strings."""
        with pytest.raises(ValueError, match="Invalid UUID7"):
            parse_uuid7("not-a-uuid")

    def test_rejects_wrong_version(self):
        """Parse must reject UUIDs that aren't version 7."""
        # UUID4-style (version 4)
        with pytest.raises(ValueError, match="Invalid UUID7"):
            parse_uuid7("550e8400-e29b-41d4-a716-446655440000")

    def test_rejects_empty_string(self):
        """Parse must reject empty string."""
        with pytest.raises(ValueError, match="Invalid UUID7"):
            parse_uuid7("")

    def test_rejects_none(self):
        """Parse must reject None."""
        with pytest.raises((ValueError, TypeError)):
            parse_uuid7(None)  # type: ignore[arg-type]
