"""XDG path resolution for Orthrus configuration and data directories."""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

try:
    from platformdirs import PlatformDirs
except ImportError:  # pragma: no cover — fallback if platformdirs ever absent
    import sys

    class PlatformDirs:  # type: ignore[no-redef]
        """Minimal fallback when platformdirs is not available."""

        def __init__(self, appname: str, appauthor: str | None = None):
            self.appname = appname
            self.appauthor = appauthor or appname

        @property
        def user_config_dir(self) -> str:
            if sys.platform == "win32":
                base = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
            elif sys.platform == "darwin":
                base = str(Path.home() / "Library" / "Application Support")
            else:
                base = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
            return str(Path(base) / self.appname)

        @property
        def user_data_dir(self) -> str:
            if sys.platform == "win32":
                base = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
            elif sys.platform == "darwin":
                base = str(Path.home() / "Library" / "Application Support")
            else:
                base = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
            return str(Path(base) / self.appname)

        @property
        def user_cache_dir(self) -> str:
            if sys.platform == "win32":
                base = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
            elif sys.platform == "darwin":
                base = str(Path.home() / "Library" / "Caches")
            else:
                base = os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))
            return str(Path(base) / self.appname)


_ORTHRUS_DIRS = PlatformDirs(appname="orthrus", appauthor="zestehl")


@dataclass(frozen=True)
class OrthrusDirs:
    """Resolved Orthrus data directories based on XDG conventions."""

    config: Path
    data: Path
    cache: Path

    def iter_search_paths(self) -> Iterator[Path]:
        """Yield config paths in search order (highest priority first)."""
        yield self.config
        legacy = Path.home() / ".orthrus"
        if legacy != self.config:
            yield legacy

    def data_sub(self, *parts: str) -> Path:
        """Resolve a subdirectory under the data dir."""
        return self.data.joinpath(*parts)


def orthrus_dirs() -> OrthrusDirs:
    """Return resolved Orthrus directories.

    Uses platformdirs for cross-platform XDG compliance:
    - config: ~/.config/orthrus/  (or platform equivalent)
    - data:   ~/.local/share/orthrus/  (or platform equivalent)
    - cache:  ~/.cache/orthrus/  (or platform equivalent)

    Raises:
        OSError: If required env vars are set to unresolvable paths.
    """
    config_str = _ORTHRUS_DIRS.user_config_dir
    data_str = _ORTHRUS_DIRS.user_data_dir
    cache_str = _ORTHRUS_DIRS.user_cache_dir

    config_path = Path(config_str).expanduser().resolve()
    data_path = Path(data_str).expanduser().resolve()
    cache_path = Path(cache_str).expanduser().resolve()

    return OrthrusDirs(config=config_path, data=data_path, cache=cache_path)


def default_config_path() -> Path:
    """Return the default config file path (~/.orthrus/config.yaml).

    This is the preferred config location for new installs.
    Falls back to ~/.config/orthrus/config.yaml for compatibility.
    """
    return orthrus_dirs().config / "config.yaml"


def default_config_search_paths() -> list[Path]:
    """Return config file search paths in priority order.

    Search order:
    1. ~/.orthrus/config.yaml  (legacy, preferred)
    2. ~/.config/orthrus/config.yaml  (XDG standard)

    The legacy path takes priority so that existing installations
    continue to work without migration.
    """
    dirs = orthrus_dirs()
    paths = list(dirs.iter_search_paths())

    # De-duplicate while preserving order
    seen: set[Path] = set()
    unique: list[Path] = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            unique.append(p)

    return [p / "config.yaml" for p in unique]
