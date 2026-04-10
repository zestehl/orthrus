"""Shared fixtures for capture tests."""

from __future__ import annotations

import os
import pytest

# Redirect HERMES_HOME so orthrus_dirs() and storage resolve under tmp_path
os.environ["HERMES_HOME"] = "/tmp/orthrus-hermes-home"

from orthrus.capture.turn_data import TurnData
from orthrus.capture.turn import ToolCall, TurnOutcome
from orthrus.config import CaptureConfig


@pytest.fixture
def capture_config() -> CaptureConfig:
    """Default capture config for tests."""
    return CaptureConfig(
        enabled=True,
        queue_max_size=10,
        flush_interval_seconds=60,
        embed_async=True,
        embed_on_capture=False,
    )


@pytest.fixture
def minimal_turn_data() -> TurnData:
    """Minimal valid TurnData for testing."""
    return TurnData(
        query_text="What is the capital of France?",
        context_hash="a" * 64,
        available_tools=("web_search", "file_read"),
        tool_calls=(
            ToolCall(
                tool_name="web_search",
                arguments_hash="b" * 64,
                output_hash="c" * 64,
                duration_ms=150,
                exit_code=0,
                success=True,
            ),
        ),
        outcome=TurnOutcome.SUCCESS,
        duration_ms=200,
        response_text="Paris",
    )


class NoOpEmbeddingBackend:
    """Mock embedding backend that does nothing."""

    dimensions = 384

    async def submit(self, turn):
        return turn  # return unchanged

    async def flush(self) -> int:
        return 0
