"""Background drain task for CaptureManager.

The drain task runs as an asyncio.Task, consuming turns from the
ingest queue and writing them to StorageManager. It handles:
- Async embedding submission
- Storage writes via asyncio.to_thread() (storage is sync)
- Graceful shutdown with full drain
"""

from __future__ import annotations

__all__ = ["EmbeddingBackend"]

import asyncio
from typing import TYPE_CHECKING

import structlog

from orthrus.embedding import EmbeddingBackend

if TYPE_CHECKING:
    from orthrus.capture._queue import IngestQueue
    from orthrus.storage import StorageManager

logger = structlog.get_logger(__name__)


async def drain_queue(
    queue: IngestQueue,
    storage: StorageManager,
    embedding: EmbeddingBackend | None,
    done_event: asyncio.Event,
    shutdown_event: asyncio.Event,
) -> None:
    """Background task that drains the ingest queue.

    Consumes turns from ``queue`` and writes them to ``storage``.
    If ``embedding`` is set, submits turns for async embedding before
    writing.

    Args:
        queue: The ingest queue to drain.
        storage: StorageManager to write turns to.
        embedding: Optional embedding backend.
        done_event: Set when the worker exits cleanly (no more turns).
        shutdown_event: Set by CaptureManager.shutdown() to signal exit.
    """
    logger.info("drain_worker_started")

    try:
        while True:
            # Wait for either a turn or a shutdown signal
            try:
                # Use wait_for with a periodic check for shutdown
                turn = await asyncio.wait_for(
                    queue.get(),
                    timeout=1.0,
                )
            except TimeoutError:
                # Check shutdown flag
                if shutdown_event.is_set():
                    logger.info("drain_worker_shutdown_check")
                    if queue.empty:
                        break
                    continue
                continue

            # Process the turn
            try:
                if embedding is not None:
                    # Submit for async embedding, then write
                    updated_turn = await embedding.submit(turn)
                    if updated_turn is not None:
                        turn = updated_turn
                    # else: embedding failed, write original turn without embedding

                # Write to storage in a thread to avoid blocking the event loop
                await asyncio.to_thread(storage.write_turn, turn)
                queue.task_done()

            except Exception as exc:
                logger.error(
                    "drain_write_error",
                    trace_id=turn.trace_id,
                    error=str(exc),
                    exc_info=True,
                )
                queue.task_done()
                # Continue processing other turns

    except asyncio.CancelledError:
        logger.info("drain_worker_cancelled")
        raise
    finally:
        done_event.set()
        logger.info(
            "drain_worker_exited",
            total_dequeued=queue.total_dequeued,
        )
