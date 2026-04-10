"""Shared fixtures for storage tests."""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

# Redirect HERMES_HOME so orthrus_dirs() and storage resolve under tmp_path
os.environ["HERMES_HOME"] = "/tmp/orthrus-hermes-home"

from orthrus.capture.turn import ToolCall, Turn, TurnOutcome
from orthrus.config._models import StorageConfig


@pytest.fixture
def storage_tmp_path(tmp_path: Path) -> Path:
    """Storage root under tmp_path, with capture/warm/archive/derived."""
    root = tmp_path / ".orthrus"
    for tier in ("capture", "warm", "archive", "derived"):
        (root / tier).mkdir(parents=True)
    return root


@pytest.fixture
def storage_config() -> StorageConfig:
    """Default storage config for tests."""
    return StorageConfig(
        hot_max_days=7,
        warm_max_days=30,
        warm_compression="zstd",
        warm_compression_level=3,
        archive_compression="zstd",
        archive_compression_level=9,
        parquet_row_group_size=100,
    )


@pytest.fixture
def sample_turn() -> Turn:
    """A minimal valid Turn for testing."""
    return Turn(
        trace_id="018f1234-5678-7abc-8def-1234567890ab",
        session_id="test-session-001",
        timestamp=datetime(2026, 4, 10, 12, 0, 0, tzinfo=UTC),
        query_text="What is the capital of France?",
        context_hash=hashlib.sha256(b"test-context").hexdigest(),
        available_tools=("web_search", "file_read"),
        tool_calls=(
            ToolCall(
                tool_name="web_search",
                arguments_hash=hashlib.sha256(b'{"q":"France capital"}').hexdigest(),
                output_hash=hashlib.sha256(b'"Paris"').hexdigest(),
                duration_ms=150,
                exit_code=0,
                success=True,
            ),
        ),
        outcome=TurnOutcome.SUCCESS,
        duration_ms=200,
        response_text="The capital of France is Paris.",
        orthrus_version="0.2.0",
        capture_profile="standard",
        platform="darwin-arm64",
    )


@pytest.fixture
def sample_turn_2() -> Turn:
    """A second distinct Turn for batch testing."""
    return Turn(
        trace_id="018f1234-5678-7abc-8def-1234567890ac",
        session_id="test-session-001",
        timestamp=datetime(2026, 4, 10, 12, 1, 0, tzinfo=UTC),
        query_text="Tell me about quantum computing",
        context_hash=hashlib.sha256(b"test-context-2").hexdigest(),
        available_tools=("web_search", "file_read"),
        tool_calls=(),
        outcome=TurnOutcome.SUCCESS,
        duration_ms=100,
        response_text="Quantum computing uses qubits.",
        orthrus_version="0.2.0",
        capture_profile="standard",
        platform="darwin-arm64",
    )
