"""Tests for sync models."""

from orthrus.sync._models import SyncError, SyncResult


class TestSyncResult:
    def test_success_true(self):
        r = SyncResult(success=True, files_transferred=10, bytes_transferred=1024)
        assert r.success is True
        assert r.failed is False
        assert r.files_transferred == 10
        assert r.bytes_transferred == 1024
        assert r.errors == ()
        assert r.target_results == ()

    def test_success_false_has_errors(self):
        r = SyncResult(success=False, errors=("error 1", "error 2"))
        assert r.success is False
        assert r.failed is True
        assert len(r.errors) == 2

    def test_frozen(self):
        r = SyncResult(success=True)
        import pytest
        with pytest.raises(AttributeError):  # frozen dataclass prevents mutation
            r.success = False  # type: ignore[misc]


class TestSyncError:
    def test_is_exception(self):
        err = SyncError("test message")
        assert isinstance(err, Exception)
        assert str(err) == "test message"

    def test_raisable(self):
        import pytest
        with pytest.raises(SyncError, match="boom"):
            raise SyncError("boom")
