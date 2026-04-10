"""CaptureManager — async ingest pipeline coordinator.

Public API is in __init__.py.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

from orthrus.capture._queue import IngestQueue
from orthrus.capture._worker import drain_queue
from orthrus.capture.turn import Turn
from orthrus.capture.turn_data import CaptureResult, CaptureStatus, TurnData
from orthrus.config import CaptureConfig, ResourceProfile
from orthrus.embedding import EmbeddingBackend

if TYPE_CHECKING:
    from orthrus.storage import StorageManager
logger = structlog.get_logger(__name__)

# Import generate_uuid7 lazily to avoid circular imports
_generate_uuid7: Callable[..., str] | None = None


def _uuid7() -> str:
    global _generate_uuid7
    if _generate_uuid7 is None:
        from orthrus.capture._uuid7 import generate_uuid7 as _g

        _generate_uuid7 = _g
    return _generate_uuid7()


# Import TurnOutcome lazily for Turn construction
_turn_outcome_cls: type | None = None


def _turn_outcome() -> type:
    global _turn_outcome_cls
    if _turn_outcome_cls is None:
        from orthrus.capture.turn import TurnOutcome

        _turn_outcome_cls = TurnOutcome
    return _turn_outcome_cls


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class CaptureError(Exception):
    """Raised when capture fails."""


class CaptureNotStartedError(CaptureError):
    """Raised when capture() is called before start()."""


class CaptureDisabledError(CaptureError):
    """Raised when capture() is called but capture is disabled in config."""


# ---------------------------------------------------------------------------
# Internal state
# ---------------------------------------------------------------------------


@dataclass
class _DrainState:
    """State shared between CaptureManager and the drain task."""

    task: asyncio.Task[None] | None = None
    shutdown_event: asyncio.Event | None = None
    done_event: asyncio.Event | None = None


# ---------------------------------------------------------------------------
# CaptureManager
# ---------------------------------------------------------------------------


class CaptureManager:
    """Manages turn capture lifecycle with async ingest queue.

    Coordinates validated turn intake, bounded queuing with back-pressure,
    background drain to StorageManager, and optional async embedding.

    Thread-safety: fully async. Must be created and used within a single
    asyncio event loop. Not safe to use from multiple concurrent coroutines
    without external synchronization.

    Args:
        config: Validated CaptureConfig. queue_max_size and flush_interval
            are read at construction.
        storage: StorageManager instance. Required. Must be started before
            CaptureManager.start() is called.
        embedding: Optional EmbeddingBackend. If None, no vector generation
            occurs and turns go directly to storage.
        capture_profile: String passed to each Turn's capture_profile field
            for provenance tracking. Defaults to "standard".
    """

    def __init__(
        self,
        config: CaptureConfig,
        storage: StorageManager,
        embedding: EmbeddingBackend | None = None,
        capture_profile: str = "standard",
        resource_profile: ResourceProfile | None = None,
    ) -> None:
        """Initialize CaptureManager.

        Args:
            config: Validated CaptureConfig.
            storage: StorageManager instance.
            embedding: Optional EmbeddingBackend.
            capture_profile: String for Turn.provenance tracking.
            resource_profile: ResourceProfile enum for queue sizing.
                Defaults to STANDARD if None.
        """
        if not config.enabled:
            logger.warning("capture_disabled_in_config")

        self._config = config
        self._storage = storage
        self._embedding = embedding
        self._capture_profile = capture_profile

        # Resolve resource profile enum
        if resource_profile is None:
            resource_profile = ResourceProfile.STANDARD

        # Queue with profile-appropriate max size
        queue_size = config.queue_size_for_profile(resource_profile)
        self._queue: IngestQueue = IngestQueue(maxsize=queue_size)

        # Drain task state
        self._drain: _DrainState = _DrainState()

        # Counters (guarded by the event loop — accessed only from async ctx)
        self._total_captured = 0
        self._total_written = 0

        # Spool for write counts from drain task
        self._write_event: asyncio.Event | None = None
        self._write_counts: list[int] = []

    # ------------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------------

    async def start(self) -> None:
        """Start the background drain task.

        Idempotent — if already started, this is a no-op.
        Must be called before capture(). Should be called after the
        StorageManager is initialized.
        """
        if self._drain.task is not None and not self._drain.task.done():
            logger.debug("capture_manager_already_started")
            return

        self._drain.shutdown_event = asyncio.Event()
        self._drain.done_event = asyncio.Event()

        self._drain.task = asyncio.create_task(
            self._run_drain(),
            name="orthrus-capture-drain",
        )
        logger.info("capture_manager_started", queue_max=self._queue.maxsize)

    async def _run_drain(self) -> None:
        """Internal drain coroutine wrapper.

        Handles count tracking and logging around the core drain_queue call.
        """

        try:
            # These are set in start() before this task runs, but mypy can't track that
            assert self._drain.done_event is not None
            assert self._drain.shutdown_event is not None
            await drain_queue(
                queue=self._queue,
                storage=self._storage,
                embedding=self._embedding,
                done_event=self._drain.done_event,
                shutdown_event=self._drain.shutdown_event,
            )
        except asyncio.CancelledError:
            logger.info("capture_drain_cancelled")
            raise

    async def capture(
        self,
        session_id: str,
        turn_data: TurnData,
    ) -> CaptureResult:
        """Capture a single agent turn.

        Validates input, enqueues for async persistence, and returns
        immediately with the trace_id.

        BACK-PRESSURE: If the internal queue is full, this coroutine
        suspends until space is available. The calling agent is blocked,
        preventing data loss under pressure.

        Args:
            session_id: REQUIRED. Groups turns into a logical conversation.
                Must be non-empty. Ambiguous session tracking is an upstream
                problem — fix it at the source.
            turn_data: Validated TurnData input from the agent.

        Returns:
            CaptureResult with the trace_id and any error message.

        Raises:
            CaptureNotStartedError: If start() has not been called.
            CaptureDisabledError: If capture is disabled in config.
            CaptureError: If session_id is empty or turn construction fails.
        """
        # --- Pre-flight checks ---
        if self._drain.task is None:
            raise CaptureNotStartedError("CaptureManager.start() must be called before capture()")

        if not self._config.enabled:
            return CaptureResult(
                trace_id="",
                error="capture_disabled",
            )

        # --- Validate session_id ---
        if not isinstance(session_id, str) or not session_id.strip():
            raise CaptureError(f"session_id is required and must be non-empty, got {session_id!r}")
        session_id = session_id.strip()

        # --- Build the Turn ---
        trace_id = _uuid7()
        timestamp = datetime.now(UTC)

        try:
            turn = Turn(
                trace_id=trace_id,
                session_id=session_id,
                timestamp=timestamp,
                capture_profile=self._capture_profile,
                **turn_data.as_dict(),  # type: ignore[arg-type]
            )
        except (ValueError, TypeError) as exc:
            raise CaptureError(f"Turn construction failed: {exc}") from exc

        # --- Enqueue (back-pressure if full) ---
        try:
            await self._queue.put(turn)
        except asyncio.CancelledError:
            raise CaptureError("capture interrupted by shutdown") from None

        self._total_captured += 1

        logger.debug(
            "turn_captured",
            trace_id=trace_id,
            session_id=session_id,
            queue_depth=self._queue.qsize(),
        )

        return CaptureResult(trace_id=trace_id)

    async def shutdown(self, timeout_seconds: float = 30.0) -> None:
        """Graceful shutdown.

        Stops accepting new turns, waits for the queue to drain fully,
        flushes any pending embeddings, and cancels the drain task.

        Args:
            timeout_seconds: Maximum seconds to wait for drain to complete.
                After this, the drain task is cancelled and remaining turns
                may be lost.
        """
        if self._drain.shutdown_event is None:
            logger.debug("shutdown_called_before_start")
            return

        logger.info("capture_shutdown_initiated", timeout=timeout_seconds)

        # Signal the drain task to stop accepting new items
        self._drain.shutdown_event.set()

        if self._drain.task is None or self._drain.task.done():
            logger.info("capture_shutdown_no_task")
            return

        # Wait for drain to finish with a timeout
        if self._drain.done_event is not None:
            try:
                await asyncio.wait_for(
                    self._drain.done_event.wait(),
                    timeout=timeout_seconds,
                )
            except TimeoutError:
                logger.warning(
                    "capture_shutdown_timeout",
                    timeout=timeout_seconds,
                    queue_remaining=self._queue.qsize(),
                )
                self._drain.task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._drain.task

        # Flush storage
        try:
            self._storage.flush()
        except Exception as exc:
            logger.error("capture_shutdown_flush_error", error=str(exc))

        # Final status
        logger.info(
            "capture_shutdown_complete",
            total_captured=self._total_captured,
            total_written=self._total_written,
        )

    # ------------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------------

    def status(self) -> CaptureStatus:
        """Return a snapshot of the capture pipeline health.

        All values are point-in-time snapshots from the caller's
        perspective.
        """
        from orthrus.capture.turn_data import CaptureStatus

        is_started = self._drain.task is not None and not self._drain.task.done()
        is_draining = (
            is_started
            and self._drain.shutdown_event is not None
            and self._drain.shutdown_event.is_set()
        )

        return CaptureStatus(
            queue_depth=self._queue.qsize(),
            queue_max=self._queue.maxsize,
            is_started=is_started,
            is_draining=is_draining,
            total_captured=self._total_captured,
            total_queued=self._queue.total_enqueued,
            total_written=self._total_written,
            embedding_pending=0,  # placeholder until embedding backend has this
            embedding_enabled=self._embedding is not None,
            healthy=is_started and self._queue.qsize() < self._queue.maxsize,
        )

    @property
    def total_captured(self) -> int:
        return self._total_captured

    async def __aenter__(self) -> CaptureManager:
        await self.start()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.shutdown()
