"""S3-compatible sync target."""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path
from typing import Any

import structlog

from orthrus.sync._models import SyncError
from orthrus.sync.targets._base import BaseSyncTarget

logger = structlog.get_logger(__name__)


class S3Target(BaseSyncTarget):
    """Sync to an S3-compatible object store (AWS, MinIO, Wasabi, etc.).

    Requires boto3. Install with: uv pip install boto3

    Parameters
    ----------
    bucket:
        S3 bucket name.
    prefix:
        Prefix path inside the bucket (e.g. "orthrus/backups/").
    region:
        AWS region. Set to None to use the default chain.
    credentials:
        How to find credentials: "env" (AWS_ACCESS_KEY_ID etc.),
        "file" (~/.aws/credentials), or "none" (IAM roles / instance profile).
    endpoint_url:
        Override endpoint URL for non-AWS S3-compatible services
        (MinIO, Wasabi, etc.).
    storage_class:
        S3 storage class for uploaded objects (STANDARD, GLACIER, etc.).
    """

    def __init__(
        self,
        *,
        bucket: str,
        prefix: str = "",
        region: str | None = None,
        credentials: str = "env",
        endpoint_url: str | None = None,
        storage_class: str = "STANDARD",
        compression: str = "zstd",
        compression_level: int = 3,
    ) -> None:
        super().__init__(compression=compression, compression_level=compression_level)
        self._bucket = bucket
        self._prefix = prefix.rstrip("/")
        self._region = region
        self._credentials = credentials
        self._endpoint_url = endpoint_url
        self._storage_class = storage_class
        self._client: Any = None  # boto3 client, lazy-initialized

    @property
    def name(self) -> str:
        return f"s3:{self._bucket}/{self._prefix or ''}"

    @property
    def _s3(self) -> Any:
        """Lazily create an S3 client."""
        if self._client is None:
            try:
                import boto3
            except ImportError as exc:
                raise SyncError(
                    "boto3 required for S3 sync. Install with: uv pip install boto3"
                ) from exc

            kwargs: dict[str, Any] = {"service_name": "s3"}
            if self._region:
                kwargs["region_name"] = self._region
            if self._endpoint_url:
                kwargs["endpoint_url"] = self._endpoint_url
            if self._credentials == "env":
                pass  # boto3 searches env vars by default
            elif self._credentials == "file":
                import os
                os.environ.setdefault(
                    "AWS_SHARED_CREDENTIALS_FILE",
                    str(Path.home() / ".aws" / "credentials"),
                )

            self._client = boto3.client(**kwargs)
        return self._client

    def push(self, local_path: Path, remote_path: str) -> bool:
        """Upload a local file or directory to S3."""
        src = local_path.resolve()
        key = self._make_key(remote_path, src)

        if not src.exists():
            logger.warning("s3_push_src_missing", src=src)
            return False

        try:
            ok = self._push_dir(src, key) if src.is_dir() else self._push_file(src, key)
            if ok:
                logger.info("s3_push_ok", src=src, bucket=self._bucket, key=key)
            return ok
        except SyncError:
            return False
        except Exception as exc:
            logger.error("s3_push_exception", src=src, error=str(exc))
            return False

    def pull(self, remote_path: str, local_path: Path) -> bool:
        """Download a remote object from S3 to local."""
        key = self._make_key(remote_path, local_path)
        dst = local_path.resolve()

        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            self._s3.download_file(self._bucket, key, str(dst))
            logger.info("s3_pull_ok", bucket=self._bucket, key=key, dst=dst)
            return True
        except Exception as exc:
            logger.error("s3_pull_failed", bucket=self._bucket, key=key, dst=dst, error=str(exc))
            return False

    def verify(self, remote_path: str) -> bool:
        """Check if an object exists in S3."""
        key = self._prefix + "/" + remote_path if remote_path else self._prefix
        try:
            self._s3.head_object(Bucket=self._bucket, Key=key)
            return True
        except Exception:
            return False

    def _make_key(self, remote_path: str, local_path: Path) -> str:
        """Build the S3 object key from a remote path and local source."""
        parts = [self._prefix] if self._prefix else []
        if remote_path:
            parts.append(remote_path)
        elif local_path.is_dir():
            parts.append(local_path.name)
        else:
            parts.append(local_path.name)
        return "/".join(parts)

    def _push_file(self, src: Path, key: str) -> bool:
        """Upload a single file to S3, optionally compressed."""
        extra_args: dict[str, Any] = {"StorageClass": self._storage_class}

        if self._compression == "zstd" and src.is_file():
            # Compress to a temp file then upload
            compressed = src.with_suffix(src.suffix + ".zst")
            self._zstd_compress(src, compressed)
            src = compressed
            extra_args["ContentEncoding"] = "zstd"
            key = key + ".zst"

        try:
            self._s3.upload_file(str(src), self._bucket, key, ExtraArgs=extra_args)
            return True
        finally:
            # Clean up temp compressed file if we created one
            if self._compression == "zstd" and src.suffix == ".zst" and src.name.endswith(".zst"):
                with suppress(OSError):
                    src.unlink()

    def _push_dir(self, src_dir: Path, key_prefix: str) -> bool:
        """Upload a directory to S3 by uploading each file."""

        ok = True
        for file_path in src_dir.rglob("*"):
            if not file_path.is_file():
                continue
            rel = file_path.relative_to(src_dir)
            file_key = f"{key_prefix}/{rel}"

            extra_args: dict[str, Any] = {"StorageClass": self._storage_class}

            if self._compression == "zstd":
                compressed = file_path.with_suffix(file_path.suffix + ".zst")
                self._zstd_compress(file_path, compressed)
                file_path = compressed
                extra_args["ContentEncoding"] = "zstd"
                file_key = file_key + ".zst"

            try:
                self._s3.upload_file(str(file_path), self._bucket, file_key, ExtraArgs=extra_args)
            except Exception as exc:
                logger.error("s3_push_file_failed", file=file_path, key=file_key, error=str(exc))
                ok = False

            # Clean up temp compressed file
            if self._compression == "zstd" and file_path.suffix == ".zst":
                with suppress(OSError):
                    file_path.unlink()

        return ok
