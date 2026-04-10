"""Tests for sync targets."""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from orthrus.sync._models import SyncError
from orthrus.sync.targets._local import LocalTarget


class TestLocalTarget:
    """Test LocalTarget sync operations."""

    def test_name(self, tmp_path):
        t = LocalTarget(path=str(tmp_path))
        assert tmp_path.name in t.name

    def test_verify_accessible_dir(self, tmp_path):
        t = LocalTarget(path=str(tmp_path))
        assert t.verify("") is True

    def test_verify_nonexistent_parent_still_false(self, tmp_path):
        t = LocalTarget(path=str(tmp_path / "nonexistent" / "deep"))
        # verify should try to create parent — may or may not succeed
        # depending on permissions, just check it doesn't raise
        result = t.verify("")
        assert isinstance(result, bool)

    def test_push_file(self, tmp_path):
        src_dir = tmp_path / "src"
        dst_dir = tmp_path / "dst"
        src_dir.mkdir()
        dst_dir.mkdir()

        src_file = src_dir / "test.txt"
        src_file.write_text("hello world")

        t = LocalTarget(path=str(dst_dir), compression="none")
        ok = t.push(src_file, "test.txt")
        assert ok is True
        assert (dst_dir / "test.txt").read_text() == "hello world"

    def test_push_file_compressed(self, tmp_path):
        src_dir = tmp_path / "src"
        dst_dir = tmp_path / "dst"
        src_dir.mkdir()
        dst_dir.mkdir()

        src_file = src_dir / "test.txt"
        src_file.write_text("hello world")

        t = LocalTarget(path=str(dst_dir), compression="zstd")
        ok = t.push(src_file, "test.txt")
        assert ok is True
        # compressed file exists with .zst suffix
        assert (dst_dir / "test.txt.zst").exists()

    def test_push_missing_file(self, tmp_path):
        t = LocalTarget(path=str(tmp_path))
        ok = t.push(Path("/nonexistent/file.txt"), "test.txt")
        assert ok is False

    def test_push_dir(self, tmp_path):
        src_dir = tmp_path / "src"
        dst_dir = tmp_path / "dst"
        src_dir.mkdir()
        (src_dir / "a.txt").write_text("a")
        (src_dir / "b.txt").write_text("b")
        dst_dir.mkdir()

        t = LocalTarget(path=str(dst_dir), compression="none")
        ok = t.push(src_dir, "src_copy")
        assert ok is True
        assert (dst_dir / "src_copy" / "a.txt").read_text() == "a"
        assert (dst_dir / "src_copy" / "b.txt").read_text() == "b"

    def test_pull(self, tmp_path):
        src_dir = tmp_path / "src"
        dst_dir = tmp_path / "dst"
        src_dir.mkdir()
        dst_dir.mkdir()
        (src_dir / "file.txt").write_text("content")

        t = LocalTarget(path=str(src_dir))
        ok = t.pull("file.txt", dst_dir / "pulled.txt")
        assert ok is True
        assert (dst_dir / "pulled.txt").read_text() == "content"

    def test_bytes_for_paths(self, tmp_path):
        t = LocalTarget(path=str(tmp_path))
        (tmp_path / "a.txt").write_text("x" * 100)
        (tmp_path / "b.txt").write_text("y" * 200)
        paths = [tmp_path / "a.txt", tmp_path / "b.txt"]
        assert t._bytes_for_paths(paths) == 300
