"""Exporter — streaming export of turns to training formats.

The Exporter reads turns from Parquet files managed by StorageManager,
applies quality filtering and deduplication, and writes records in the
requested format to a JSONL output file.

Memory contract: O(1) with respect to dataset size — only one Parquet
file is buffered in memory at a time.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import structlog

from orthrus.capture.turn import Turn, TurnOutcome
from orthrus.config._models import Config
from orthrus.export._config import ExportConfig, ExportFormat
from orthrus.export._formats._base import ExportFormatter
from orthrus.export._formats._dpo import DPOFormatter
from orthrus.export._formats._raw import RawFormatter
from orthrus.export._formats._sharegpt import ShareGPTFormatter
from orthrus.export._result import ExportResult
from orthrus.storage._manager import StorageManager
from orthrus.storage._parquet import read_turns

logger = structlog.get_logger(__name__)

# --------------------------------------------------------------------------:
# Errors
# --------------------------------------------------------------------------


class ExportError(Exception):
    """Raised when an export operation fails unrecoverably."""


# --------------------------------------------------------------------------:
# Quality scoring
# --------------------------------------------------------------------------:


def compute_quality(turn: Turn) -> float:
    """Compute a heuristic quality score for a Turn (0.0-1.0).

    This is a rule-based scorer. Production systems should substitute a
    trained quality model via the embedding backend.

    Scoring rules
    -------------
    Base: 0.5
    + Response present: +0.2
    + Outcome SUCCESS: +0.1
    + Outcome ERROR/TIMEOUT/PARTIAL: -0.1
    + Reasoning content present: +0.05
    + Tool calls all successful: +0.1
    + Tool calls any failed: -0.1
    + user_rating present: overrides everything

    Returns
    -------
    float
        Quality score clamped to [0.0, 1.0].
    """
    if turn.user_rating is not None:
        return max(0.0, min(1.0, turn.user_rating))

    score = 0.5

    if turn.response_text:
        score += 0.2

    if turn.outcome.value == "success":
        score += 0.1
    elif turn.outcome.value in ("error", "timeout", "partial"):
        score -= 0.1

    if turn.reasoning_content:
        score += 0.05

    if turn.tool_calls:
        if all(tc.success for tc in turn.tool_calls):
            score += 0.1
        elif any(not tc.success for tc in turn.tool_calls):
            score -= 0.1

    return max(0.0, min(1.0, score))


def _cosine_similarity(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    """Cosine similarity between two embedding vectors."""
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


# --------------------------------------------------------------------------:
# Dedup cache
# --------------------------------------------------------------------------:


class _DedupCache:
    """Bounded cache for embedding-based deduplication.

    Bounded to ``max_size`` entries to keep memory constant regardless
    of dataset size.
    """

    def __init__(self, max_size: int = 10_000) -> None:
        self._cache: list[tuple[str, tuple[float, ...]]] = []
        self._max_size = max_size

    def is_duplicate(self, embedding: tuple[float, ...], threshold: float) -> bool:
        """Return True if any cached embedding has cosine similarity >= threshold."""
        for _cached_id, cached_emb in self._cache:
            sim = _cosine_similarity(embedding, cached_emb)
            if sim >= threshold:
                logger.debug("dedup_hit", sim=round(sim, 4), threshold=threshold)
                return True
        return False

    def add(self, trace_id: str, embedding: tuple[float, ...]) -> None:
        """Add an embedding, evicting the oldest entry when at capacity."""
        if len(self._cache) >= self._max_size:
            self._cache.pop(0)
        self._cache.append((trace_id, embedding))


# --------------------------------------------------------------------------:
# Turn reconstruction from Parquet storage dicts
# --------------------------------------------------------------------------:


def _reconstruct_turn(record: dict[str, object]) -> Turn | None:
    """Reconstruct a Turn from a Parquet storage record dict.

    Used by Exporter to read back stored turns for export.
    Returns None if required fields are missing or unparseable.
    """
    # Required fields
    trace_id = record.get("trace_id")
    session_id = record.get("session_id")
    timestamp_val = record.get("timestamp")
    query_text = record.get("query_text")

    if not all(isinstance(v, str) and v for v in [trace_id, session_id, query_text]):
        return None
    if not timestamp_val:
        return None

    # Parse timestamp
    if isinstance(timestamp_val, datetime):
        timestamp = timestamp_val
    elif isinstance(timestamp_val, str):
        try:
            timestamp = datetime.fromisoformat(timestamp_val.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None

    # Parse outcome
    outcome_str = str(record.get("outcome", "success"))
    try:
        outcome = TurnOutcome(outcome_str)
    except ValueError:
        outcome = TurnOutcome.SUCCESS

    # Parse query_embedding
    query_emb_val = record.get("query_embedding")
    if isinstance(query_emb_val, list) and query_emb_val:
        try:
            query_emb: tuple[float, ...] | None = tuple(float(x) for x in query_emb_val)
        except (ValueError, TypeError):
            query_emb = None
    else:
        query_emb = None

    # Parse response_embedding
    resp_emb_val = record.get("response_embedding")
    if isinstance(resp_emb_val, list) and resp_emb_val:
        try:
            resp_emb: tuple[float, ...] | None = tuple(float(x) for x in resp_emb_val)
        except (ValueError, TypeError):
            resp_emb = None
    else:
        resp_emb = None

    # Parse available_tools
    available_tools_raw = record.get("available_tools", [])
    available_tools: tuple[str, ...] = (
        tuple(str(x) for x in available_tools_raw)
        if isinstance(available_tools_raw, list)
        else ()
    )

    # Parse active_skills
    active_skills_raw = record.get("active_skills", [])
    active_skills: tuple[str, ...] = (
        tuple(str(x) for x in active_skills_raw)
        if isinstance(active_skills_raw, list)
        else ()
    )

    # Optional string fields
    def _str(val: object) -> str | None:
        return str(val) if val is not None else None

    def _str_or_none(val: object) -> str | None:
        return str(val) if val else None

    context_hash_val = record.get("context_ref")
    context_hash = str(context_hash_val) if context_hash_val else "0" * 64

    try:
        return Turn(
            trace_id=str(trace_id),
            session_id=str(session_id),
            timestamp=timestamp,
            query_text=str(query_text),
            context_hash=context_hash,
            available_tools=available_tools,
            parent_trace_id=_str(record.get("parent_trace_id")),
            query_embedding=query_emb,
            active_skills=active_skills,
            reasoning_content=_str_or_none(record.get("reasoning_content")),
            tool_selection=_str_or_none(record.get("tool_selection")),
            tool_calls=(),  # tool_calls not stored in parquet schema
            outcome=outcome,
            duration_ms=int(cast(int, record.get("duration_ms", 0))),
            error_class=_str_or_none(record.get("error_class")),
            user_rating=float(cast(float, record["user_rating"]))
            if record.get("user_rating") is not None
            else None,
            response_text=_str_or_none(record.get("response_text")),
            response_embedding=resp_emb,
        )
    except Exception:
        return None


# --------------------------------------------------------------------------:
# Exporter
# --------------------------------------------------------------------------:


class Exporter:
    """Export captured turns to training formats (ShareGPT, DPO, Raw).

    Reads Parquet files from StorageManager, applies quality filtering and
    embedding-based deduplication, and streams records to a JSONL output.

    Parameters
    ----------
    storage :
        StorageManager instance to read turns from.
    config :
        ExportConfig with format, quality threshold, and dedup settings.
    config_root :
        Optional orthrus Config for embedding backend resolution.
    """

    def __init__(
        self,
        storage: StorageManager,
        config: ExportConfig,
        config_root: Config | None = None,
    ) -> None:
        self._storage = storage
        self._config = config
        self._config_root = config_root or Config()
        self._formatter = self._resolve_formatter(config.format)
        self._dedup: _DedupCache | None = (
            _DedupCache() if config.deduplicate else None
        )

    def _resolve_formatter(self, fmt: ExportFormat) -> ExportFormatter:
        """Return the formatter instance for the given format."""
        formatter_map: dict[ExportFormat, ExportFormatter] = {
            ExportFormat.SHAREGPT: ShareGPTFormatter(),
            ExportFormat.DPO: DPOFormatter(),
            ExportFormat.RAW: RawFormatter(),
        }
        return formatter_map[fmt]

    # ------------------------------------------------------------------:
    # Public API
    # ------------------------------------------------------------------:

    def export(
        self,
        output_path: Path,
        since: datetime | None = None,
        until: datetime | None = None,
        session_id: str | None = None,
    ) -> ExportResult:
        """Export turns to a JSONL file.

        Parameters
        ----------
        output_path :
            Destination file (created or overwritten).
        since :
            Only export turns with timestamp >= this UTC datetime.
        until :
            Only export turns with timestamp <= this UTC datetime.
        session_id :
            If set, only export turns from this session.

        Returns
        -------
        ExportResult
            Statistics from the export run.
        """
        total = 0
        exported = 0
        filtered = 0
        duplicates = 0
        quality_bins: dict[str, int] = {
            "0.0-0.2": 0,
            "0.2-0.4": 0,
            "0.4-0.6": 0,
            "0.6-0.8": 0,
            "0.8-1.0": 0,
        }
        output_path_str = str(output_path)

        # Collect files
        try:
            files = self._storage.get_hot_files(since=since)
        except Exception as exc:  # pragma: no cover — defensive
            return ExportResult(
                error=f"Failed to enumerate files: {exc}",
                format=self._config.format.value,
                output_path=output_path_str,
            )

        if not files:
            logger.warning("export_no_files", since=since, until=until)
            return ExportResult(
                error=None,
                format=self._config.format.value,
                output_path=output_path_str,
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(output_path, "w", encoding="utf-8") as fh:
                for file_path in files:
                    file_records = 0
                    try:
                        records = read_turns(file_path)
                    except Exception as exc:
                        logger.warning("export_skip_file", path=str(file_path), error=str(exc))
                        filtered += 1
                        continue

                    for record in records:
                        total += 1

                        turn = _reconstruct_turn(record)
                        if turn is None:
                            filtered += 1
                            continue

                        # Time range filter (apply naive tz awareness if needed)
                        ts_utc = turn.timestamp
                        if ts_utc.tzinfo is None:
                            ts_utc = ts_utc.replace(tzinfo=UTC)
                        if since is not None:
                            since_utc = (
                                since.astimezone(UTC) if since.tzinfo
                                else since.replace(tzinfo=UTC)
                            )
                            if ts_utc < since_utc:
                                continue
                        if until is not None:
                            until_utc = (
                                until.astimezone(UTC) if until.tzinfo
                                else until.replace(tzinfo=UTC)
                            )
                            if ts_utc > until_utc:
                                continue
                        if session_id is not None and turn.session_id != session_id:
                            continue

                        # Quality
                        quality = compute_quality(turn)
                        bin_label = _quality_bin(quality)
                        quality_bins[bin_label] = quality_bins[bin_label] + 1

                        if quality < self._config.min_quality_score:
                            filtered += 1
                            continue

                        # Deduplication
                        if (
                            self._dedup is not None
                            and turn.query_embedding is not None
                        ):
                            if self._dedup.is_duplicate(
                                turn.query_embedding, self._config.dedup_threshold
                            ):
                                duplicates += 1
                                continue
                            self._dedup.add(turn.trace_id, turn.query_embedding)

                        # Format and write
                        output_record = self._formatter.format(turn)
                        if output_record is None:
                            filtered += 1
                            continue

                        fh.write(json.dumps(output_record, ensure_ascii=False) + "\n")
                        exported += 1
                        file_records += 1

                    logger.debug("export_file_done", path=str(file_path), records=file_records)

        except OSError as exc:
            return ExportResult(
                error=f"Write error ({output_path}): {exc}",
                records_total=total,
                records_exported=exported,
                records_filtered=filtered,
                records_duplicates=duplicates,
                quality_distribution=quality_bins,
                format=self._config.format.value,
                output_path=output_path_str,
            )

        logger.info(
            "export_complete",
            total=total,
            exported=exported,
            filtered=filtered,
            duplicates=duplicates,
            format=self._config.format.value,
        )

        return ExportResult(
            records_total=total,
            records_exported=exported,
            records_filtered=filtered,
            records_duplicates=duplicates,
            quality_distribution=quality_bins,
            format=self._config.format.value,
            output_path=output_path_str,
            error=None,
        )

    def compute_quality(self, turn: Turn) -> float:
        """Compute quality score for a single Turn.

        Uses the heuristic scorer. Pass an embedding backend to
        ``__init__`` to use a trained model instead.
        """
        return compute_quality(turn)


# --------------------------------------------------------------------------:
# Helpers
# --------------------------------------------------------------------------:


def _quality_bin(score: float) -> str:
    """Return the quality bin label for a score."""
    if score < 0.2:
        return "0.0-0.2"
    if score < 0.4:
        return "0.2-0.4"
    if score < 0.6:
        return "0.4-0.6"
    if score < 0.8:
        return "0.6-0.8"
    return "0.8-1.0"
