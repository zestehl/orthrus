"""Tests for CaptureManager and TurnData."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from orthrus.capture import (
    CaptureManager,
    CaptureConfig,
    CaptureError,
    CaptureNotStartedError,
    CaptureResult,
    CaptureStatus,
    EmbeddingBackend,
    TurnData,
)
from orthrus.capture._manager import (
    CaptureDisabledError,
)
from orthrus.capture.turn import ToolCall, TurnOutcome
from orthrus.storage import StorageManager, TurnRecord

from .conftest import NoOpEmbeddingBackend


# ---------------------------------------------------------------------------
# TurnData tests
# ---------------------------------------------------------------------------


class TestTurnData:
    """TurnData validation."""

    def test_minimal_construction(self, minimal_turn_data: TurnData):
        """Minimal valid TurnData constructs successfully."""
        assert minimal_turn_data.query_text == "What is the capital of France?"
        assert minimal_turn_data.outcome == TurnOutcome.SUCCESS
        assert len(minimal_turn_data.available_tools) == 2

    def test_outcome_defaults_to_success(self):
        """outcome defaults to SUCCESS when not provided."""
        td = TurnData(
            query_text="hello",
            context_hash="a" * 64,
            available_tools=(),
            tool_calls=(),
        )
        assert td.outcome == TurnOutcome.SUCCESS

    def test_outcome_from_string(self):
        """outcome can be passed as a string value."""
        td = TurnData(
            query_text="hello",
            context_hash="a" * 64,
            available_tools=(),
            tool_calls=(),
            outcome="error",
        )
        assert td.outcome == TurnOutcome.ERROR

    def test_invalid_outcome_string_rejected(self):
        """Invalid outcome string raises ValueError."""
        with pytest.raises(ValueError, match="outcome"):
            TurnData(
                query_text="hello",
                context_hash="a" * 64,
                available_tools=(),
                tool_calls=(),
                outcome="not_a_valid_outcome",
            )

    def test_empty_query_text_rejected(self):
        """Empty query_text raises ValueError."""
        with pytest.raises(ValueError, match="query_text"):
            TurnData(
                query_text="",
                context_hash="a" * 64,
                available_tools=(),
                tool_calls=(),
            )

    def test_whitespace_only_query_text_rejected(self):
        """Whitespace-only query_text raises ValueError."""
        with pytest.raises(ValueError, match="query_text"):
            TurnData(
                query_text="   ",
                context_hash="a" * 64,
                available_tools=(),
                tool_calls=(),
            )

    def test_query_text_too_long_rejected(self):
        """query_text > 10KB raises ValueError."""
        with pytest.raises(ValueError, match="max length"):
            TurnData(
                query_text="x" * 10_001,
                context_hash="a" * 64,
                available_tools=(),
                tool_calls=(),
            )

    def test_invalid_context_hash_rejected(self):
        """Invalid context_hash raises ValueError."""
        with pytest.raises(ValueError, match="context_hash"):
            TurnData(
                query_text="hello",
                context_hash="not-a-valid-sha256",
                available_tools=(),
                tool_calls=(),
            )

    def test_negative_duration_rejected(self):
        """Negative duration_ms raises ValueError."""
        with pytest.raises(ValueError, match="duration_ms"):
            TurnData(
                query_text="hello",
                context_hash="a" * 64,
                available_tools=(),
                tool_calls=(),
                duration_ms=-1,
            )

    def test_user_rating_out_of_range_rejected(self):
        """user_rating outside 0.0-1.0 raises ValueError."""
        with pytest.raises(ValueError, match="user_rating"):
            TurnData(
                query_text="hello",
                context_hash="a" * 64,
                available_tools=(),
                tool_calls=(),
                user_rating=1.5,
            )

    def test_available_tools_normalized_to_tuple(self):
        """available_tools list is normalized to tuple."""
        td = TurnData(
            query_text="hello",
            context_hash="a" * 64,
            available_tools=["web", "file"],
            tool_calls=(),
        )
        assert isinstance(td.available_tools, tuple)
        assert td.available_tools == ("web", "file")

    def test_as_dict_excludes_generated_fields(self):
        """as_dict() returns only TurnData fields, not generated ones."""
        td = TurnData(
            query_text="hello",
            context_hash="a" * 64,
            available_tools=(),
            tool_calls=(),
        )
        d = td.as_dict()
        assert "trace_id" not in d
        assert "session_id" not in d
        assert "timestamp" not in d
        assert "query_text" in d
        assert d["query_text"] == "hello"


# ---------------------------------------------------------------------------
# CaptureManager lifecycle tests
# ---------------------------------------------------------------------------


class TestCaptureManagerLifecycle:
    """CaptureManager start/shutdown."""

    @pytest.fixture
    def mock_storage(self) -> MagicMock:
        """Mock StorageManager that does nothing on write."""
        storage = MagicMock(spec=StorageManager)
        storage.write_turn = MagicMock(return_value=MagicMock(spec=TurnRecord))
        storage.flush = MagicMock()
        return storage

    @pytest.fixture
    def manager(
        self,
        capture_config: CaptureConfig,
        mock_storage: MagicMock,
    ) -> CaptureManager:
        return CaptureManager(capture_config, mock_storage)

    @pytest.mark.asyncio
    async def test_start_idempotent(self, manager: CaptureManager):
        """start() can be called multiple times safely."""
        await manager.start()
        await manager.start()  # should not raise

        assert manager.status().is_started

    @pytest.mark.asyncio
    async def test_shutdown_before_start_noops(
        self,
        capture_config: CaptureConfig,
        mock_storage: MagicMock,
    ):
        """shutdown() before start() is a safe no-op."""
        manager = CaptureManager(capture_config, mock_storage)
        await manager.shutdown()  # should not raise

    @pytest.mark.asyncio
    async def test_capture_before_start_raises(
        self,
        manager: CaptureManager,
        minimal_turn_data: TurnData,
    ):
        """capture() before start() raises CaptureNotStartedError."""
        with pytest.raises(CaptureNotStartedError):
            await manager.capture("session-001", minimal_turn_data)

    @pytest.mark.asyncio
    async def test_context_manager(self, manager: CaptureManager):
        """CaptureManager works as an async context manager."""
        async with manager:
            pass  # start() was called

        assert not manager.status().is_started


# ---------------------------------------------------------------------------
# CaptureManager.capture() tests
# ---------------------------------------------------------------------------


class TestCaptureManagerCapture:
    """CaptureManager.capture() behavior."""

    @pytest.fixture
    def mock_storage(self) -> MagicMock:
        """Mock StorageManager."""
        storage = MagicMock(spec=StorageManager)
        write_record = MagicMock(spec=TurnRecord)
        storage.write_turn = MagicMock(return_value=write_record)
        storage.flush = MagicMock()
        return storage

    @pytest.fixture
    def manager(
        self,
        capture_config: CaptureConfig,
        mock_storage: MagicMock,
    ) -> CaptureManager:
        return CaptureManager(capture_config, mock_storage)

    @pytest.mark.asyncio
    async def test_capture_returns_trace_id(
        self,
        manager: CaptureManager,
        minimal_turn_data: TurnData,
    ):
        """capture() returns a CaptureResult with a trace_id."""
        await manager.start()
        result = await manager.capture("session-001", minimal_turn_data)

        assert isinstance(result, CaptureResult)
        assert result.trace_id is not None
        assert len(result.trace_id) == 36  # UUID7 format
        assert result.error is None

    @pytest.mark.asyncio
    async def test_capture_empty_session_id_raises(
        self,
        manager: CaptureManager,
        minimal_turn_data: TurnData,
    ):
        """capture() with empty session_id raises CaptureError."""
        await manager.start()

        with pytest.raises(CaptureError, match="session_id"):
            await manager.capture("", minimal_turn_data)

    @pytest.mark.asyncio
    async def test_capture_whitespace_session_id_raises(
        self,
        manager: CaptureManager,
        minimal_turn_data: TurnData,
    ):
        """capture() with whitespace-only session_id raises CaptureError."""
        await manager.start()

        with pytest.raises(CaptureError, match="session_id"):
            await manager.capture("   ", minimal_turn_data)

    @pytest.mark.asyncio
    async def test_capture_disabled_config(
        self,
        capture_config: CaptureConfig,
        mock_storage: MagicMock,
        minimal_turn_data: TurnData,
    ):
        """capture() when disabled returns error result."""
        capture_config.enabled = False
        manager = CaptureManager(capture_config, mock_storage)
        await manager.start()

        result = await manager.capture("session-001", minimal_turn_data)

        assert result.trace_id == ""
        assert result.error == "capture_disabled"

    @pytest.mark.asyncio
    async def test_capture_increments_counter(
        self,
        manager: CaptureManager,
        minimal_turn_data: TurnData,
    ):
        """capture() increments the total_captured counter."""
        await manager.start()
        assert manager.total_captured == 0

        await manager.capture("session-001", minimal_turn_data)
        assert manager.total_captured == 1

        await manager.capture("session-001", minimal_turn_data)
        assert manager.total_captured == 2

    @pytest.mark.asyncio
    async def test_capture_shutdown_flushes_queue(
        self,
        capture_config: CaptureConfig,
        mock_storage: MagicMock,
        minimal_turn_data: TurnData,
    ):
        """shutdown() flushes the queue and storage."""
        manager = CaptureManager(capture_config, mock_storage)
        await manager.start()

        await manager.capture("session-001", minimal_turn_data)
        await manager.capture("session-001", minimal_turn_data)
        await manager.shutdown()

        # Storage.flush() should have been called
        mock_storage.flush.assert_called_once()


# ---------------------------------------------------------------------------
# CaptureManager status tests
# ---------------------------------------------------------------------------


class TestCaptureManagerStatus:
    """CaptureManager.status() behavior."""

    @pytest.fixture
    def mock_storage(self) -> MagicMock:
        storage = MagicMock(spec=StorageManager)
        storage.write_turn = MagicMock(return_value=MagicMock(spec=TurnRecord))
        storage.flush = MagicMock()
        return storage

    @pytest.fixture
    def manager(
        self,
        capture_config: CaptureConfig,
        mock_storage: MagicMock,
    ) -> CaptureManager:
        return CaptureManager(capture_config, mock_storage)

    def test_status_before_start(
        self,
        manager: CaptureManager,
    ):
        """status() before start() shows not started."""
        status = manager.status()
        assert status.is_started is False
        assert status.queue_depth == 0
        assert status.healthy is False

    @pytest.mark.asyncio
    async def test_status_after_start(
        self,
        manager: CaptureManager,
    ):
        """status() after start() shows started."""
        await manager.start()
        status = manager.status()
        assert status.is_started is True
        assert status.healthy is True

    @pytest.mark.asyncio
    async def test_status_reflects_queue_depth(
        self,
        manager: CaptureManager,
        minimal_turn_data: TurnData,
    ):
        """status() reflects the queue depth after captures."""
        await manager.start()
        await manager.capture("session-001", minimal_turn_data)

        status = manager.status()
        assert status.queue_depth >= 1


# ---------------------------------------------------------------------------
# CaptureResult dataclass tests
# ---------------------------------------------------------------------------


class TestCaptureResult:
    """CaptureResult frozen dataclass."""

    def test_basic_construction(self):
        """CaptureResult with trace_id only."""
        result = CaptureResult(trace_id="abc")
        assert result.trace_id == "abc"
        assert result.error is None

    def test_immutable(self):
        """CaptureResult is frozen."""
        result = CaptureResult(trace_id="abc")
        with pytest.raises(AttributeError):
            result.trace_id = "xyz"
