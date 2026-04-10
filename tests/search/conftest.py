"""Shared fixtures for search tests."""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

# Redirect HERMES_HOME so storage resolves under tmp_path
os.environ["HERMES_HOME"] = "/tmp/orthrus-search-hermes-home"

from orthrus.capture.turn import ToolCall, Turn, TurnOutcome
from orthrus.storage._parquet import ParquetWriter


@pytest.fixture
def search_tmp_path(tmp_path: Path) -> Path:
    """Storage root under tmp_path with capture directory."""
    root = tmp_path / ".orthrus"
    (root / "capture").mkdir(parents=True)
    return root


@pytest.fixture
def sample_turn_1() -> Turn:
    """Turn about France."""
    return Turn(
        trace_id="018f1234-5678-7abc-8def-111111111101",
        session_id="session-france",
        timestamp=datetime(2026, 4, 10, 10, 0, 0, tzinfo=UTC),
        query_text="What is the capital of France?",
        context_hash=hashlib.sha256(b"context-france").hexdigest(),
        available_tools=("web_search",),
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
        query_embedding=[0.1] * 384,
        orthrus_version="0.2.0",
        capture_profile="standard",
        platform="darwin-arm64",
    )


@pytest.fixture
def sample_turn_2() -> Turn:
    """Turn about quantum computing."""
    return Turn(
        trace_id="018f1234-5678-7abc-8def-222222222202",
        session_id="session-quantum",
        timestamp=datetime(2026, 4, 10, 11, 0, 0, tzinfo=UTC),
        query_text="Explain quantum computing in simple terms",
        context_hash=hashlib.sha256(b"context-quantum").hexdigest(),
        available_tools=("web_search", "file_read"),
        tool_calls=(),
        outcome=TurnOutcome.SUCCESS,
        duration_ms=150,
        response_text="Quantum computing uses qubits that can be 0 and 1 simultaneously.",
        query_embedding=[0.2] * 384,
        orthrus_version="0.2.0",
        capture_profile="standard",
        platform="darwin-arm64",
    )


@pytest.fixture
def sample_turn_3() -> Turn:
    """Turn about Python errors."""
    return Turn(
        trace_id="018f1234-5678-7abc-8def-333333333303",
        session_id="session-python",
        timestamp=datetime(2026, 4, 10, 12, 0, 0, tzinfo=UTC),
        query_text="How do I fix a TypeError in Python?",
        context_hash=hashlib.sha256(b"context-python").hexdigest(),
        available_tools=("file_read",),
        tool_calls=(
            ToolCall(
                tool_name="file_read",
                arguments_hash=hashlib.sha256(b'{"path":"main.py"}').hexdigest(),
                output_hash=hashlib.sha256(b'"line 42..."').hexdigest(),
                duration_ms=50,
                exit_code=1,
                success=False,
            ),
        ),
        outcome=TurnOutcome.ERROR,
        duration_ms=300,
        response_text="TypeError usually means you passed the wrong type.",
        query_embedding=[0.3] * 384,
        error_class="TypeError",
        orthrus_version="0.2.0",
        capture_profile="standard",
        platform="darwin-arm64",
    )


@pytest.fixture
def sample_turn_4() -> Turn:
    """Turn about ML embeddings."""
    return Turn(
        trace_id="018f1234-5678-7abc-8def-444444444404",
        session_id="session-ml",
        timestamp=datetime(2026, 4, 10, 13, 0, 0, tzinfo=UTC),
        query_text="What are sentence embeddings for NLP?",
        context_hash=hashlib.sha256(b"context-ml").hexdigest(),
        available_tools=("web_search",),
        tool_calls=(),
        outcome=TurnOutcome.SUCCESS,
        duration_ms=120,
        response_text="Embeddings represent text as dense vectors.",
        query_embedding=[0.4] * 384,
        orthrus_version="0.2.0",
        capture_profile="standard",
        platform="darwin-arm64",
    )


@pytest.fixture
def parquet_file_1(
    search_tmp_path: Path, sample_turn_1: Turn, sample_turn_2: Turn
) -> Path:
    """Parquet file with turns 1 and 2 (yyyy/mm/dd structure for StorageManager)."""
    # StorageManager expects yyyy/mm/dd/ directory structure
    path = search_tmp_path / "capture" / "2026" / "04" / "10" / "turns_000.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = ParquetWriter(path)
    writer.write(sample_turn_1)
    writer.write(sample_turn_2)
    writer.close()
    return path


@pytest.fixture
def parquet_file_2(
    search_tmp_path: Path, sample_turn_3: Turn, sample_turn_4: Turn
) -> Path:
    """Parquet file with turns 3 and 4 (yyyy/mm/dd structure for StorageManager)."""
    path = search_tmp_path / "capture" / "2026" / "04" / "10" / "turns_001.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = ParquetWriter(path)
    writer.write(sample_turn_3)
    writer.write(sample_turn_4)
    writer.close()
    return path


@pytest.fixture
def parquet_paths(
    parquet_file_1: Path, parquet_file_2: Path
) -> list[Path]:
    """List of parquet file paths."""
    return [parquet_file_1, parquet_file_2]
