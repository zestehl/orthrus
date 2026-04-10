"""Pydantic configuration models for Orthrus.

Resource profiles (minimal / standard / performance) control defaults
for all sub-systems. Every field has a sensible zero-config default.
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ResourceProfile(Enum):
    """Resource profile — controls default limits and feature flags."""

    MINIMAL = "minimal"
    STANDARD = "standard"
    PERFORMANCE = "performance"


# ---------------------------------------------------------------------------
# Sub-configs
# ---------------------------------------------------------------------------


class CaptureConfig(BaseModel):
    """Capture pipeline settings."""

    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    queue_max_size: int = Field(default=100, ge=1, le=10_000)
    flush_interval_seconds: int = Field(default=60, ge=1, le=3600)
    embed_async: bool = True
    embed_on_capture: bool = False  # True = block until embedding done

    def queue_size_for_profile(self, profile: ResourceProfile) -> int:
        """Return profile-appropriate queue size (may be overridden by user)."""
        if self.queue_max_size != 100:
            return self.queue_max_size  # user set explicitly
        return {
            ResourceProfile.MINIMAL: 10,
            ResourceProfile.STANDARD: 100,
            ResourceProfile.PERFORMANCE: 1000,
        }[profile]


class StorageConfig(BaseModel):
    """Persistent storage settings."""

    model_config = ConfigDict(extra="ignore")

    hot_max_days: int = Field(default=30, ge=1, le=365)
    warm_max_days: int = Field(default=90, ge=1, le=3650)
    warm_compression: Literal["none", "zstd", "lz4"] = "zstd"
    warm_compression_level: int = Field(default=3, ge=1, le=22)
    archive_compression: Literal["none", "zstd", "lz4"] = "zstd"
    archive_compression_level: int = Field(default=9, ge=1, le=22)
    parquet_row_group_size: int = Field(default=1000, ge=100, le=100_000)

    def hot_max_days_for_profile(self, profile: ResourceProfile) -> int:
        if self.hot_max_days != 30:
            return self.hot_max_days
        return {
            ResourceProfile.MINIMAL: 7,
            ResourceProfile.STANDARD: 30,
            ResourceProfile.PERFORMANCE: 90,
        }[profile]

    def warm_max_days_for_profile(self, profile: ResourceProfile) -> int:
        if self.warm_max_days != 90:
            return self.warm_max_days
        return {
            ResourceProfile.MINIMAL: 30,
            ResourceProfile.STANDARD: 90,
            ResourceProfile.PERFORMANCE: 365,
        }[profile]


class EmbeddingConfig(BaseModel):
    """Embedding generation settings."""

    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    model: str | None = None  # None = auto-select based on profile
    batch_size: int = Field(default=32, ge=1, le=256)
    device: Literal["auto", "cpu", "cuda", "metal"] = "auto"
    dimensions: int = Field(default=384, ge=64, le=4096)

    def default_model_for_profile(self, profile: ResourceProfile) -> str | None:
        if self.model is not None:
            return self.model
        return {
            ResourceProfile.MINIMAL: None,
            ResourceProfile.STANDARD: "all-MiniLM-L6-v2",
            ResourceProfile.PERFORMANCE: "E5-large-v2",
        }[profile]

    def dimensions_for_profile(self, profile: ResourceProfile) -> int:
        if self.dimensions != 384:
            return self.dimensions
        return {
            ResourceProfile.MINIMAL: 0,  # disabled
            ResourceProfile.STANDARD: 384,
            ResourceProfile.PERFORMANCE: 1024,
        }[profile]


class SearchConfig(BaseModel):
    """Search and retrieval settings."""

    model_config = ConfigDict(extra="ignore")

    default_mode: Literal["auto", "text", "vector", "hybrid"] = "auto"
    index_on_demand: bool = True
    max_results: int = Field(default=100, ge=1, le=10_000)
    text_score_threshold: float = Field(default=0.1, ge=0.0, le=1.0)
    hybrid_rerank_top_k: int = Field(default=20, ge=1, le=200)


class SyncTarget(BaseModel):
    """A single sync destination."""

    model_config = ConfigDict(extra="ignore")

    type: Literal["local", "rsync", "s3"]
    path: str  # local path or SSH/S3 URI
    schedule: Literal["manual", "hourly", "daily", "weekly"] = "daily"
    compression: Literal["none", "zstd"] = "zstd"
    compression_level: int = Field(default=3, ge=1, le=22)
    credentials: Literal["env", "file"] = "env"  # where to find secrets
    # S3-specific
    bucket: str | None = None
    prefix: str | None = None
    region: str | None = None
    # rsync-specific
    host: str | None = None
    user: str | None = None

    @model_validator(mode="after")
    def _validate_type_fields(self) -> SyncTarget:
        if self.type == "s3" and not self.bucket:
            raise ValueError("S3 target requires 'bucket' field")
        if self.type == "rsync" and not self.host:
            raise ValueError("rsync target requires 'host' field")
        return self


class SyncConfig(BaseModel):
    """Remote sync settings."""

    model_config = ConfigDict(extra="ignore")

    enabled: bool = False
    targets: list[SyncTarget] = Field(default_factory=list)
    local_retention_days: int = Field(default=30, ge=1, le=3650)
    remote_retention_days: int = Field(default=365, ge=1, le=36500)


# ---------------------------------------------------------------------------
# Root config
# ---------------------------------------------------------------------------


class Config(BaseModel):
    """Top-level Orthrus configuration.

    All fields have zero-config defaults. A config file only needs to
    override values that differ from the defaults.
    """

    model_config = ConfigDict(
        extra="ignore",
        validate_default=True,
    )

    version: int = 1
    profile: ResourceProfile = ResourceProfile.STANDARD

    capture: CaptureConfig = Field(default_factory=CaptureConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    sync: SyncConfig = Field(default_factory=SyncConfig)

    # Paths section — if omitted, resolved from XDG at load time
    paths: dict[str, str] = Field(default_factory=dict)

    @field_validator("profile", mode="before")
    @classmethod
    def _coerce_profile(cls, v: Any) -> ResourceProfile:
        if isinstance(v, ResourceProfile):
            return v
        if isinstance(v, str):
            return ResourceProfile(v.lower())
        raise ValueError(f"profile must be a string, got {type(v).__name__}")

    @classmethod
    def from_file(cls, path: Path | str) -> Config:
        """Load and validate config from a YAML file.

        Raises:
            ConfigFileNotFoundError: File does not exist.
            ValidationError: File contains invalid data.
        """
        path = Path(path).expanduser().resolve()
        if not path.is_file():
            raise ConfigFileNotFoundError(f"Config file not found: {path}")

        with open(path, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)

        if raw is None:
            raw = {}

        if not isinstance(raw, dict):
            raise ValidationError(f"Config file must be a YAML dict, got {type(raw).__name__}")

        return cls.model_validate(raw)

    @classmethod
    def default(cls) -> Config:
        """Return a Config with all defaults applied."""
        return cls()

    def effective_capture_queue_size(self) -> int:
        return self.capture.queue_size_for_profile(self.profile)

    def effective_hot_max_days(self) -> int:
        return self.storage.hot_max_days_for_profile(self.profile)

    def effective_warm_max_days(self) -> int:
        return self.storage.warm_max_days_for_profile(self.profile)

    def effective_embedding_model(self) -> str | None:
        return self.embedding.default_model_for_profile(self.profile)

    def effective_embedding_dimensions(self) -> int:
        return self.embedding.dimensions_for_profile(self.profile)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_config(path: Path | str | None = None) -> Config:
    """Load config with the standard search order.

    Search order:
    1. Explicit ``path`` argument
    2. ``ORTHRUS_CONFIG`` environment variable
    3. ``~/.orthrus/config.yaml``
    4. ``~/.config/orthrus/config.yaml`` (XDG)

    Returns:
        Validated Config with all defaults resolved.

    Raises:
        ConfigFileNotFoundError: No config file found in search path.
        ValidationError: Config file contains invalid data.
    """
    # 1. Explicit path
    if path is not None:
        return Config.from_file(path)

    # 2. ORTHRUS_CONFIG env var
    env_path = os.environ.get("ORTHRUS_CONFIG", "").strip()
    if env_path:
        return Config.from_file(env_path)

    # 3 & 4. Search default locations
    from orthrus.config._paths import default_config_search_paths

    tried: list[str] = []
    for candidate in default_config_search_paths():
        if candidate.is_file():
            return Config.from_file(candidate)
        tried.append(str(candidate))

    raise ConfigFileNotFoundError("No config file found. Searched:\n  " + "\n  ".join(tried))


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ConfigError(Exception):
    """Base exception for config-related errors."""


class ConfigFileNotFoundError(ConfigError):
    """Raised when no config file exists in the search path."""


class ValidationError(ConfigError):
    """Raised when a config file fails validation."""

    def __init__(self, message: str):
        super().__init__(message)
