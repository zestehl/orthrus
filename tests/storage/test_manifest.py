"""Tests for orthrus.storage._manifest."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

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


@pytest.fixture
def sample_manifest(tmp_path) -> tuple[Manifest, Path]:
    """A manifest with two file entries."""
    files = [
        FileEntry(
            name="session-20260409-turns.parquet",
            checksum="sha256:" + "a" * 64,
            size_bytes=12345,
            num_rows=100,
            type="parquet",
        ),
        FileEntry(
            name="session-20260409-trajectories.jsonl",
            checksum="sha256:" + "b" * 64,
            size_bytes=6789,
            num_rows=50,
            type="jsonl",
        ),
    ]
    manifest = build_manifest("test-session", "2026-04-09", files)
    path = tmp_path / "manifest.json"
    return manifest, path


class TestFileEntry:
    """FileEntry construction."""

    def test_checksum_prefix(self):
        """Checksum field always starts with sha256:."""
        entry = FileEntry(
            name="test.parquet",
            checksum="sha256:abc123",
            size_bytes=100,
            num_rows=10,
            type="parquet",
        )
        assert entry.checksum.startswith("sha256:")


class TestManifest:
    """Manifest to_dict / build."""

    def test_to_dict_structure(self, sample_manifest):
        """to_dict() produces a valid serializable dict."""
        manifest, _ = sample_manifest
        d = manifest.to_dict()

        assert d["version"] == 1
        assert d["session_id"] == "test-session"
        assert d["date"] == "2026-04-09"
        assert len(d["files"]) == 2
        assert d["generated_at"]  # non-empty

    def test_manifest_roundtrip(self, tmp_path, sample_manifest):
        """write_manifest + read_manifest preserves all data."""
        manifest, path = sample_manifest
        write_manifest(manifest, path)

        loaded = read_manifest(path)

        assert loaded.version == manifest.version
        assert loaded.session_id == manifest.session_id
        assert loaded.date == manifest.date
        assert len(loaded.files) == len(manifest.files)
        assert loaded.files[0].name == manifest.files[0].name


class TestVerifyFile:
    """File integrity verification."""

    def test_verify_valid_file(self, tmp_path):
        """verify_file returns True for an unchanged file."""
        path = tmp_path / "test.txt"
        path.write_text("hello world")

        import hashlib
        expected = "sha256:" + hashlib.sha256(b"hello world").hexdigest()

        assert verify_file(path, expected) is True

    def test_verify_tampered_file(self, tmp_path):
        """verify_file returns False for a tampered file."""
        path = tmp_path / "test.txt"
        path.write_text("hello world")

        import hashlib
        wrong_checksum = "sha256:" + hashlib.sha256(b"tampered!").hexdigest()

        assert verify_file(path, wrong_checksum) is False

    def test_verify_missing_file(self, tmp_path):
        """verify_file returns False for a missing file."""
        path = tmp_path / "does-not-exist.txt"
        assert verify_file(path, "sha256:abc123") is False


class TestVerifyManifestIntegrity:
    """Full manifest integrity check."""

    def test_all_files_valid(self, tmp_path, sample_manifest):
        """verify_manifest_integrity returns True for all valid files."""
        manifest, manifest_path = sample_manifest
        # Write manifest
        write_manifest(manifest, manifest_path)
        # Create the files
        pq_path = tmp_path / manifest.files[0].name
        pq_path.write_bytes(b"fake parquet data")
        jsonl_path = tmp_path / manifest.files[1].name
        jsonl_path.write_bytes(b'{"fake": "jsonl"}')

        # Override checksums with actual file content
        import hashlib
        manifest_data = {
            "version": 1,
            "session_id": "test-session",
            "date": "2026-04-09",
            "generated_at": "2026-04-09T00:00:00+00:00",
            "files": [
                {
                    "name": pq_path.name,
                    "checksum": "sha256:" + hashlib.sha256(pq_path.read_bytes()).hexdigest(),
                    "size_bytes": pq_path.stat().st_size,
                    "num_rows": 100,
                    "type": "parquet",
                },
                {
                    "name": jsonl_path.name,
                    "checksum": "sha256:" + hashlib.sha256(jsonl_path.read_bytes()).hexdigest(),
                    "size_bytes": jsonl_path.stat().st_size,
                    "num_rows": 50,
                    "type": "jsonl",
                },
            ],
        }
        manifest_path.write_text(json.dumps(manifest_data))
        loaded_manifest = read_manifest(manifest_path)

        results = verify_manifest_integrity(loaded_manifest, tmp_path)
        assert all(results.values())


class TestBuildFileEntry:
    """build_file_entry from real file."""

    def test_build_from_file(self, tmp_path):
        """build_file_entry computes correct checksum from real file."""
        path = tmp_path / "test.parquet"
        path.write_bytes(b"parquet data here")

        entry = build_file_entry(path, num_rows=42)

        import hashlib
        expected = "sha256:" + hashlib.sha256(b"parquet data here").hexdigest()
        assert entry.checksum == expected
        assert entry.num_rows == 42
        assert entry.size_bytes == len(b"parquet data here")
        assert entry.type == "parquet"
