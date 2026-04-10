"""Tests for orthrus.storage._paths."""

from __future__ import annotations

from datetime import UTC, datetime, timezone

from orthrus.storage._paths import StoragePaths


class TestStoragePaths:
    """StoragePaths path resolution and name generation."""

    def test_resolve_creates_directories(self, tmp_path, monkeypatch):
        """resolve() creates all tier directories."""
        # Override _data_root to use tmp_path
        import orthrus.storage._paths as p
        monkeypatch.setattr(p, "_data_root", lambda: tmp_path)

        paths = StoragePaths.resolve()

        assert paths.capture.is_dir()
        assert paths.warm.is_dir()
        assert paths.archive.is_dir()
        assert paths.derived.is_dir()

    def test_resolve_with_overrides(self, tmp_path, monkeypatch):
        """resolve() applies path overrides from config."""
        import orthrus.storage._paths as p
        monkeypatch.setattr(p, "_data_root", lambda: tmp_path)

        overrides = {
            "capture": str(tmp_path / "my_capture"),
            "warm": str(tmp_path / "my_warm"),
        }
        paths = StoragePaths.resolve(config_paths=overrides)

        assert paths.capture == tmp_path / "my_capture"
        assert paths.warm == tmp_path / "my_warm"
        assert paths.archive.exists()  # default still created
        assert paths.derived.exists()  # default still created

    def test_capture_for_date(self, tmp_path, monkeypatch):
        """capture_for_date() returns correct YYYY/MM/DD subdirectory."""
        import orthrus.storage._paths as p
        monkeypatch.setattr(p, "_data_root", lambda: tmp_path)

        paths = StoragePaths.resolve()
        ts = datetime(2026, 4, 9, 14, 30, 0, tzinfo=UTC)
        result = paths.capture_for_date(ts)

        assert result == paths.capture / "2026" / "04" / "09"

    def test_capture_for_date_eastern_to_utc(self, tmp_path, monkeypatch):
        """capture_for_date() converts local timezone to UTC date."""
        import orthrus.storage._paths as p
        monkeypatch.setattr(p, "_data_root", lambda: tmp_path)

        paths = StoragePaths.resolve()
        # 2026-04-09 01:00 EST = 2026-04-09 05:00 UTC — same calendar day
        from datetime import timedelta
        est_delta = timedelta(hours=-5)
        est_tz = timezone(est_delta)
        est = datetime(2026, 4, 9, 1, 0, 0, tzinfo=est_tz)
        result = paths.capture_for_date(est)
        assert result == paths.capture / "2026" / "04" / "09"

    def test_session_prefix_sanitizes_session_id(self):
        """session_prefix() replaces non-alphanumeric chars."""
        prefix = StoragePaths.session_prefix("session-001!", datetime.now(UTC))
        assert "!" not in prefix
        assert "session-001_" in prefix  # unsafe chars become underscores

    def test_turns_filename(self):
        """turns_filename() builds correct parquet filename."""
        ts = datetime(2026, 4, 9, tzinfo=UTC)
        name = StoragePaths.turns_filename("my-session", ts)
        assert name == "my-session-20260409-turns.parquet"

    def test_trajectories_filename(self):
        """trajectories_filename() builds correct jsonl filename."""
        ts = datetime(2026, 4, 9, tzinfo=UTC)
        name = StoragePaths.trajectories_filename("my-session", ts)
        assert name == "my-session-20260409-trajectories.jsonl"

    def test_manifest_filename(self):
        """manifest_filename() builds correct manifest filename."""
        ts = datetime(2026, 4, 9, tzinfo=UTC)
        name = StoragePaths.manifest_filename("my-session", ts)
        assert name == "my-session-20260409-manifest.json"
# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
