"""Orthrus configuration module — YAML loading, resource profiles, XDG paths."""

from orthrus.config._models import (
    CaptureConfig,
    Config,
    EmbeddingConfig,
    ResourceProfile,
    SearchConfig,
    StorageConfig,
    SyncConfig,
    SyncTarget,
    load_config,
)
from orthrus.config._paths import (
    default_config_path,
    default_config_search_paths,
    orthrus_dirs,
)

__all__ = [
    "Config",
    "CaptureConfig",
    "StorageConfig",
    "EmbeddingConfig",
    "SearchConfig",
    "SyncConfig",
    "SyncTarget",
    "ResourceProfile",
    "load_config",
    "orthrus_dirs",
    "default_config_path",
    "default_config_search_paths",
]
