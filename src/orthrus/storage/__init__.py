"""Orthrus storage module — durable persistence of Turn records.

Public API:
    StorageManager   — write, flush, rotate, verify
    StoragePaths     — resolve and inspect storage paths
    TurnRecord       — Turn with its written file paths
    RotationResult   — outcome of a rotation pass
    StorageError     — base exception
    DiskFullError    — disk space exhausted
"""

from orthrus.storage._jsonl import (
    JSONLWriter,
    jsonl_file_stats,
    read_jsonl,
    turn_to_jsonl_record,
)
from orthrus.storage._manager import (
    DiskFullError,
    StorageError,
    StorageManager,
    TurnRecord,
)
from orthrus.storage._manifest import (
    FileEntry,
    Manifest,
    build_file_entry,
    build_manifest,
    read_manifest,
    verify_file,
    verify_manifest_integrity,
    write_manifest,
)
from orthrus.storage._parquet import (
    TURN_SCHEMA,
    ParquetWriter,
    parquet_file_stats,
    read_turns,
    turn_to_record,
)
from orthrus.storage._paths import StoragePaths
from orthrus.storage._rotation import FileRotation, RotationResult, rotate

__all__ = [
    # Manager
    "StorageManager",
    "TurnRecord",
    "RotationResult",
    "FileRotation",
    # Paths
    "StoragePaths",
    # Config models
    "StorageError",
    "DiskFullError",
    # Manifest
    "Manifest",
    "FileEntry",
    "write_manifest",
    "read_manifest",
    "build_manifest",
    "build_file_entry",
    "verify_file",
    "verify_manifest_integrity",
    # Parquet
    "ParquetWriter",
    "TURN_SCHEMA",
    "turn_to_record",
    "read_turns",
    "parquet_file_stats",
    # JSONL
    "JSONLWriter",
    "turn_to_jsonl_record",
    "read_jsonl",
    "jsonl_file_stats",
    # Rotation
    "rotate",
]
