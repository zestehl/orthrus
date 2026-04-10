"""Tests for orthrus.config — YAML loading, resource profiles, XDG paths."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError as PydanticValidationError

from orthrus.config._models import (
    CaptureConfig,
    Config,
    ConfigError,
    ConfigFileNotFoundError,
    EmbeddingConfig,
    ResourceProfile,
    SearchConfig,
    StorageConfig,
    SyncTarget,
    load_config,
)
from orthrus.config._paths import (
    default_config_path,
    default_config_search_paths,
    orthrus_dirs,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write_config(tmp: Path, content: str | dict) -> Path:
    """Write a config YAML file and return its path."""
    path = tmp / "config.yaml"
    path.write_text(yaml.dump(content) if isinstance(content, dict) else content)
    return path


# ---------------------------------------------------------------------------
# ResourceProfile
# ---------------------------------------------------------------------------

class TestResourceProfile:
    def test_all_variants(self):
        assert ResourceProfile.MINIMAL.value == "minimal"
        assert ResourceProfile.STANDARD.value == "standard"
        assert ResourceProfile.PERFORMANCE.value == "performance"

    def test_coerce_from_string(self):
        cfg = Config.model_validate({"profile": "performance"})
        assert cfg.profile == ResourceProfile.PERFORMANCE

    def test_reject_invalid_profile(self):
        with pytest.raises(PydanticValidationError, match="profile"):
            Config.model_validate({"profile": "invalid"})


# ---------------------------------------------------------------------------
# Config — defaults
# ---------------------------------------------------------------------------

class TestConfigDefaults:
    def test_all_defaults(self):
        cfg = Config()
        assert cfg.version == 1
        assert cfg.profile == ResourceProfile.STANDARD
        assert cfg.capture.enabled is True
        assert cfg.capture.queue_max_size == 100
        assert cfg.storage.hot_max_days == 30
        assert cfg.storage.warm_max_days == 90
        assert cfg.embedding.enabled is True
        assert cfg.search.default_mode == "auto"
        assert cfg.sync.enabled is False
        assert cfg.sync.targets == []

    def test_default_capture_queue_size_per_profile(self):
        cfg_minimal = Config(profile=ResourceProfile.MINIMAL)
        cfg_standard = Config(profile=ResourceProfile.STANDARD)
        cfg_perf = Config(profile=ResourceProfile.PERFORMANCE)

        assert cfg_minimal.effective_capture_queue_size() == 10
        assert cfg_standard.effective_capture_queue_size() == 100
        assert cfg_perf.effective_capture_queue_size() == 1000

    def test_user_queue_size_overrides_profile_default(self):
        cfg = Config(
            profile=ResourceProfile.MINIMAL,
            capture=CaptureConfig(queue_max_size=50),
        )
        assert cfg.effective_capture_queue_size() == 50  # user override wins

    def test_effective_hot_max_days(self):
        cfg_minimal = Config(profile=ResourceProfile.MINIMAL)
        cfg_standard = Config(profile=ResourceProfile.STANDARD)
        cfg_perf = Config(profile=ResourceProfile.PERFORMANCE)

        assert cfg_minimal.effective_hot_max_days() == 7
        assert cfg_standard.effective_hot_max_days() == 30
        assert cfg_perf.effective_hot_max_days() == 90

    def test_effective_warm_max_days(self):
        cfg_minimal = Config(profile=ResourceProfile.MINIMAL)
        cfg_standard = Config(profile=ResourceProfile.STANDARD)
        cfg_perf = Config(profile=ResourceProfile.PERFORMANCE)

        assert cfg_minimal.effective_warm_max_days() == 30
        assert cfg_standard.effective_warm_max_days() == 90
        assert cfg_perf.effective_warm_max_days() == 365

    def test_effective_embedding_model(self):
        cfg_minimal = Config(profile=ResourceProfile.MINIMAL)
        cfg_standard = Config(profile=ResourceProfile.STANDARD)
        cfg_perf = Config(profile=ResourceProfile.PERFORMANCE)

        assert cfg_minimal.effective_embedding_model() is None
        assert cfg_standard.effective_embedding_model() == "all-MiniLM-L6-v2"
        assert cfg_perf.effective_embedding_model() == "E5-large-v2"

    def test_effective_embedding_dimensions(self):
        cfg_minimal = Config(profile=ResourceProfile.MINIMAL)
        cfg_standard = Config(profile=ResourceProfile.STANDARD)
        cfg_perf = Config(profile=ResourceProfile.PERFORMANCE)

        assert cfg_minimal.effective_embedding_dimensions() == 0
        assert cfg_standard.effective_embedding_dimensions() == 384
        assert cfg_perf.effective_embedding_dimensions() == 1024

    def test_embedding_model_override_wins(self):
        cfg = Config(
            profile=ResourceProfile.STANDARD,
            embedding=EmbeddingConfig(model="my-custom-model"),
        )
        assert cfg.effective_embedding_model() == "my-custom-model"


# ---------------------------------------------------------------------------
# Config — file loading
# ---------------------------------------------------------------------------

class TestConfigFromFile:
    def test_minimal_file(self, tmp_path: Path):
        path = write_config(tmp_path, {"profile": "minimal"})
        cfg = Config.from_file(path)
        assert cfg.profile == ResourceProfile.MINIMAL

    def test_full_override(self, tmp_path: Path):
        path = write_config(tmp_path, {
            "profile": "performance",
            "capture": {"enabled": False, "queue_max_size": 200},
            "storage": {"hot_max_days": 14},
        })
        cfg = Config.from_file(path)
        assert cfg.profile == ResourceProfile.PERFORMANCE
        assert cfg.capture.enabled is False
        assert cfg.capture.queue_max_size == 200
        assert cfg.storage.hot_max_days == 14

    def test_extra_fields_ignored(self, tmp_path: Path):
        path = write_config(tmp_path, {
            "profile": "standard",
            "unknown_field": "should be ignored",
            "capture": {
                "unknown_capture_field": 99,
            },
        })
        cfg = Config.from_file(path)
        assert cfg.profile == ResourceProfile.STANDARD  # loads fine

    def test_missing_file_raises(self, tmp_path: Path):
        nonexistent = tmp_path / "does_not_exist.yaml"
        with pytest.raises(ConfigFileNotFoundError, match="does_not_exist"):
            Config.from_file(nonexistent)

    def test_empty_file_uses_defaults(self, tmp_path: Path):
        path = tmp_path / "empty.yaml"
        path.write_text("")
        cfg = Config.from_file(path)
        assert cfg.profile == ResourceProfile.STANDARD

    def test_invalid_yaml(self, tmp_path: Path):
        path = tmp_path / "bad.yaml"
        path.write_text("  not: valid: yaml: [")
        with pytest.raises(yaml.YAMLError):
            Config.from_file(path)

    def test_wrong_root_type(self, tmp_path: Path):
        path = tmp_path / "bad.yaml"
        path.write_text("- not\n- a\n- dict\n")
        with pytest.raises(ConfigError, match="dict"):
            Config.from_file(path)


# ---------------------------------------------------------------------------
# load_config — search order
# ---------------------------------------------------------------------------

class TestLoadConfig:
    def test_explicit_path(self, tmp_path: Path):
        path = write_config(tmp_path, {"profile": "minimal"})
        cfg = load_config(path)
        assert cfg.profile == ResourceProfile.MINIMAL

    def test_env_var_overrides_search(self, tmp_path: Path, monkeypatch):
        path = write_config(tmp_path, {"profile": "performance"})
        monkeypatch.setenv("ORTHRUS_CONFIG", str(path))
        cfg = load_config()
        assert cfg.profile == ResourceProfile.PERFORMANCE

    def test_no_config_found(self, tmp_path: Path, monkeypatch):
        # Point everything to a directory with no config
        monkeypatch.setenv("ORTHRUS_CONFIG", "")
        monkeypatch.setattr(
            "orthrus.config._paths._ORTHRUS_DIRS",
            type("_", (), {
                "user_config_dir": str(tmp_path),
                "user_data_dir": str(tmp_path),
                "user_cache_dir": str(tmp_path),
            })(),
        )
        with pytest.raises(ConfigFileNotFoundError, match="No config file found"):
            load_config()


# ---------------------------------------------------------------------------
# Sub-config validation
# ---------------------------------------------------------------------------

class TestSyncTarget:
    def test_valid_local_target(self):
        t = SyncTarget(type="local", path="/backup/orthrus")
        assert t.type == "local"

    def test_valid_rsync_target(self):
        t = SyncTarget(type="rsync", host="backup.example.com", path="/backups/")
        assert t.type == "rsync"

    def test_valid_s3_target(self):
        t = SyncTarget(type="s3", bucket="my-dataset", path="s3://my-dataset/orthrus/")
        assert t.type == "s3"

    def test_s3_missing_bucket(self):
        with pytest.raises(PydanticValidationError, match="bucket"):
            SyncTarget(type="s3", path="s3://my-dataset/")

    def test_rsync_missing_host(self):
        with pytest.raises(PydanticValidationError, match="host"):
            SyncTarget(type="rsync", path="/backups/")

    def test_compression_levels_validated(self):
        t = SyncTarget(type="local", path="/backup", compression_level=22)
        assert t.compression_level == 22


class TestStorageConfig:
    def test_compression_defaults(self):
        cfg = StorageConfig()
        assert cfg.warm_compression == "zstd"
        assert cfg.warm_compression_level == 3
        assert cfg.archive_compression == "zstd"
        assert cfg.archive_compression_level == 9


class TestEmbeddingConfig:
    def test_device_auto(self):
        cfg = EmbeddingConfig(device="auto")
        assert cfg.device == "auto"

    def test_reject_invalid_device(self):
        with pytest.raises(PydanticValidationError):
            EmbeddingConfig(device="gpu")  # not a valid literal


class TestSearchConfig:
    def test_defaults(self):
        cfg = SearchConfig()
        assert cfg.default_mode == "auto"
        assert cfg.index_on_demand is True
        assert cfg.max_results == 100

    def test_reject_invalid_mode(self):
        with pytest.raises(PydanticValidationError):
            SearchConfig(default_mode="fast")  # not a valid literal


class TestCaptureConfig:
    def test_queue_bounds(self):
        with pytest.raises(PydanticValidationError):
            CaptureConfig(queue_max_size=0)  # too low
        with pytest.raises(PydanticValidationError):
            CaptureConfig(queue_max_size=50_000)  # too high

    def test_flush_interval_bounds(self):
        with pytest.raises(PydanticValidationError):
            CaptureConfig(flush_interval_seconds=0)
        with pytest.raises(PydanticValidationError):
            CaptureConfig(flush_interval_seconds=10_000)


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

class TestOrthrusDirs:
    def test_dirs_are_paths(self):
        dirs = orthrus_dirs()
        assert isinstance(dirs.config, Path)
        assert isinstance(dirs.data, Path)
        assert isinstance(dirs.cache, Path)

    def test_config_path_expanded(self):
        dirs = orthrus_dirs()
        assert "~" not in str(dirs.config)

    def test_data_sub(self):
        dirs = orthrus_dirs()
        sub = dirs.data_sub("capture", "2026", "04")
        assert str(sub).endswith("capture/2026/04")

    def test_iter_search_paths_includes_legacy(self, monkeypatch):
        # When config dir is NOT ~/.orthrus, legacy should also be checked
        dirs = orthrus_dirs()
        paths = list(dirs.iter_search_paths())
        assert len(paths) >= 1

    def test_default_config_path(self):
        p = default_config_path()
        assert p.name == "config.yaml"
        assert "orthrus" in str(p).lower()


class TestDefaultConfigSearchPaths:
    def test_returns_list_of_paths(self):
        paths = default_config_search_paths()
        assert isinstance(paths, list)
        assert all(isinstance(p, Path) for p in paths)
        assert all(p.name == "config.yaml" for p in paths)

    def test_deduplicated(self):
        paths = default_config_search_paths()
        assert len(paths) == len(set(paths))
