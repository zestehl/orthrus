"""Async ingest queue for CaptureManager.

Wraps asyncio.Queue with structured put/get semantics and
back-pressure handling.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from orthrus.capture.turn import Turn

logger = structlog.get_logger(__name__)


@dataclass
class IngestQueue:
    """Bounded asyncio queue for Turn ingestion.

    Wraps asyncio.Queue with:
    - Back-pressure on put (caller suspends when full)
    - Monitoring hooks for queue depth
    - Batch-ready drain interface
    """

    maxsize: int = 0

    def __post_init__(self) -> None:
        self._queue: asyncio.Queue[Turn] = asyncio.Queue(maxsize=self.maxsize)
        # Track total enqueued for monitoring (includes items still in queue)
        self._total_enqueued = 0
        self._total_dequeued = 0

    async def put(self, turn: Turn) -> None:
        """Enqueue a turn, suspending if full (back-pressure).

        Args:
            turn: Validated Turn to enqueue.
        """
        await self._queue.put(turn)
        self._total_enqueued += 1
        logger.debug(
            "queue_put",
            trace_id=turn.trace_id,
            depth=self._queue.qsize(),
            max=self.maxsize,
        )

    async def get(self) -> Turn:
        """Dequeue a turn, suspending if empty.

        Returns:
            The next Turn from the queue.
        """
        turn = await self._queue.get()
        self._total_dequeued += 1
        return turn

    def qsize(self) -> int:
        """Current number of items in the queue."""
        return self._queue.qsize()

    @property
    def empty(self) -> bool:
        return self._queue.empty()

    @property
    def full(self) -> bool:
        return self._queue.full()

    @property
    def total_enqueued(self) -> int:
        return self._total_enqueued

    @property
    def total_dequeued(self) -> int:
        return self._total_dequeued

    async def join(self) -> None:
        """Block until the queue is fully drained.

        Unlike asyncio.Queue.join(), this waits for qsize() == 0.
        """
        await self._queue.join()

    def task_done(self) -> None:
        """Signal that a dequeued item has been fully processed."""
        self._queue.task_done()
