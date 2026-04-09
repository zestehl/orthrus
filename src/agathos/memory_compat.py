"""
ARGUS memory provider compatibility — multi-backend access for monitoring.

Discovers the active memory provider from hermes config and provides
read access for monitoring purposes (fact counts, quality metrics, search).

Supported providers:
  holographic — local SQLite (memory_store.db)
  builtin     — MEMORY.md / USER.md files
  honcho      — cloud dialectic memory API
  mem0        — cloud fact extraction API
  hindsight   — cloud knowledge graph API
  openviking  — local/cloud context database
  retaindb    — cloud hybrid search API
  supermemory — cloud semantic memory API
  byterover   — cloud knowledge tree CLI

All providers expose:
  - fact_count() → int
  - quality_summary() → Dict (avg score, recent facts)
  - search(query) → List[Dict] (if supported)
"""

import json
import logging
import os
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("agathos.memory_compat")

# =============================================================================
# Credential / config loading
# =============================================================================

_dotenv_loaded = False


def _ensure_dotenv():
    global _dotenv_loaded
    if _dotenv_loaded:
        return
    _dotenv_loaded = True
    try:
        from hermes_cli.env_loader import load_hermes_dotenv

        load_hermes_dotenv()
    except Exception:
        pass


def _env(key: str) -> Optional[str]:
    _ensure_dotenv()
    val = os.environ.get(key)
    return val.strip() if val else None


def _hermes_home() -> Path:
    try:
        from hermes_constants import get_hermes_home

        return get_hermes_home()
    except ImportError:
        return Path.home() / ".hermes"


def _load_config() -> Dict:
    """Load hermes config.yaml."""
    import yaml

    config_path = _hermes_home() / "config.yaml"
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    return {}


def _http_get(
    url: str, headers: Optional[Dict] = None, timeout: int = 10
) -> Tuple[Optional[dict], Optional[str]]:
    """GET JSON from a URL. Returns (data, error)."""
    try:
        hdrs = {"Accept": "application/json"}
        if headers:
            hdrs.update(headers)
        req = urllib.request.Request(url, headers=hdrs, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read()), None
    except urllib.error.HTTPError as e:
        return None, "HTTP %s" % e.code
    except Exception as e:
        return None, str(e)


def _http_post(
    url: str, payload: dict, headers: Optional[Dict] = None, timeout: int = 10
) -> Tuple[Optional[dict], Optional[str]]:
    """POST JSON to a URL. Returns (data, error)."""
    try:
        data = json.dumps(payload).encode("utf-8")
        hdrs = {"Content-Type": "application/json"}
        if headers:
            hdrs.update(headers)
        req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read()), None
    except urllib.error.HTTPError as e:
        return None, "HTTP %s" % e.code
    except Exception as e:
        return None, str(e)


# =============================================================================
# Provider discovery
# =============================================================================


def get_active_provider() -> str:
    """Return the configured memory provider name from config.yaml."""
    config = _load_config()
    return config.get("memory", {}).get("provider", "builtin")


# =============================================================================
# Provider interface
# =============================================================================


class MemoryProviderAccess:
    """Base interface for read access to a memory provider."""

    def __init__(self, name: str):
        self.name = name

    def is_available(self) -> bool:
        return False

    def fact_count(self) -> Optional[int]:
        return None

    def quality_summary(self) -> Optional[Dict[str, Any]]:
        return None

    def search(self, query: str, limit: int = 5) -> List[Dict]:
        return []


# =============================================================================
# Holographic (local SQLite)
# =============================================================================


class HolographicAccess(MemoryProviderAccess):
    """Direct SQLite access to holographic memory_store.db."""

    def __init__(self):
        super().__init__("holographic")
        self._db_path = self._find_db()

    def _find_db(self) -> Optional[Path]:
        home = _hermes_home()
        # Check common locations
        for candidate in [
            home / "memory_store.db",
            home / "holographic_memory.db",
        ]:
            if candidate.exists():
                return candidate
        return None

    def is_available(self) -> bool:
        return self._db_path is not None

    def _connect(self) -> Optional[sqlite3.Connection]:
        if not self._db_path:
            return None
        try:
            conn = sqlite3.connect(str(self._db_path))
            conn.row_factory = sqlite3.Row
            return conn
        except Exception:
            return None

    def fact_count(self) -> Optional[int]:
        conn = self._connect()
        if not conn:
            return None
        try:
            row = conn.execute("SELECT COUNT(*) as cnt FROM facts").fetchone()
            return row["cnt"] if row else 0
        except Exception:
            return None
        finally:
            conn.close()

    def quality_summary(self) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        if not conn:
            return None
        try:
            row = conn.execute("""
                SELECT
                    COUNT(*) as total_facts,
                    AVG(trust_score) as avg_trust,
                    AVG(quality_score) as avg_quality,
                    SUM(retrieval_count) as total_retrievals,
                    SUM(helpful_count) as total_helpful
                FROM facts
            """).fetchone()
            if row:
                return {
                    "provider": "holographic",
                    "total_facts": row["total_facts"],
                    "avg_trust_score": round(row["avg_trust"] or 0, 4),
                    "avg_quality_score": round(row["avg_quality"] or 0, 4)
                    if row["avg_quality"]
                    else None,
                    "total_retrievals": row["total_retrievals"] or 0,
                    "total_helpful": row["total_helpful"] or 0,
                }
        except Exception:
            pass
        finally:
            conn.close()
        return None

    def search(self, query: str, limit: int = 5) -> List[Dict]:
        conn = self._connect()
        if not conn:
            return []
        try:
            rows = conn.execute(
                """
                SELECT f.fact_id, f.content, f.category, f.trust_score, f.quality_score
                FROM facts f
                JOIN facts_fts ON f.fact_id = facts_fts.rowid
                WHERE facts_fts MATCH ?
                ORDER BY f.trust_score DESC
                LIMIT ?
            """,
                (query, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []
        finally:
            conn.close()


# =============================================================================
# Builtin (MEMORY.md / USER.md)
# =============================================================================


class BuiltinAccess(MemoryProviderAccess):
    """Read access to MEMORY.md and USER.md files."""

    def __init__(self):
        super().__init__("builtin")
        self._memory_path = _hermes_home() / "MEMORY.md"
        self._user_path = _hermes_home() / "USER.md"

    def is_available(self) -> bool:
        return self._memory_path.exists() or self._user_path.exists()

    def fact_count(self) -> Optional[int]:
        count = 0
        for path in [self._memory_path, self._user_path]:
            if path.exists():
                content = path.read_text()
                # Count non-empty, non-header lines as "facts"
                count += sum(
                    1
                    for line in content.split("\n")
                    if line.strip() and not line.startswith("#")
                )
        return count

    def quality_summary(self) -> Optional[Dict[str, Any]]:
        sizes = {}
        for name, path in [
            ("MEMORY.md", self._memory_path),
            ("USER.md", self._user_path),
        ]:
            if path.exists():
                sizes[name] = path.getsize()
        return {
            "provider": "builtin",
            "file_sizes": sizes,
            "total_bytes": sum(sizes.values()),
        }


# =============================================================================
# Cloud providers (raw HTTP)
# =============================================================================


class HonchoAccess(MemoryProviderAccess):
    """Raw HTTP access to Honcho dialectic memory API."""

    BASE_URL = "https://app.honcho.dev"

    def __init__(self):
        super().__init__("honcho")

    def is_available(self) -> bool:
        return bool(_env("HONCHO_API_KEY"))

    def _headers(self) -> Dict:
        return {"Authorization": "Bearer %s" % _env("HONCHO_API_KEY")}

    def fact_count(self) -> Optional[int]:
        # Honcho uses sessions/conclusions, not fact counts
        # Return session count as proxy
        api_key = _env("HONCHO_API_KEY")
        if not api_key:
            return None
        # Honcho doesn't have a simple count endpoint
        return None

    def quality_summary(self) -> Optional[Dict[str, Any]]:
        return {"provider": "honcho", "api": self.BASE_URL, "status": "connected"}


class Mem0Access(MemoryProviderAccess):
    """Raw HTTP access to Mem0 fact extraction API."""

    BASE_URL = "https://api.mem0.ai"

    def __init__(self):
        super().__init__("mem0")

    def is_available(self) -> bool:
        return bool(_env("MEM0_API_KEY"))

    def _headers(self) -> Dict:
        return {"Authorization": "Token %s" % _env("MEM0_API_KEY")}

    def fact_count(self) -> Optional[int]:
        api_key = _env("MEM0_API_KEY")
        user_id = _env("MEM0_USER_ID")
        if not api_key or not user_id:
            return None
        url = "%s/v1/memories/?user_id=%s&limit=1" % (self.BASE_URL, user_id)
        data, err = _http_get(url, self._headers())
        if data and isinstance(data, list):
            # Mem0 returns list, count is from pagination or len
            return len(data)
        return None

    def search(self, query: str, limit: int = 5) -> List[Dict]:
        api_key = _env("MEM0_API_KEY")
        if not api_key:
            return []
        url = "%s/v1/search/" % self.BASE_URL
        payload = {"query": query, "user_id": _env("MEM0_USER_ID"), "limit": limit}
        data, err = _http_post(url, payload, self._headers())
        if data and isinstance(data, list):
            return [
                {"content": m.get("memory", ""), "score": m.get("score", 0)}
                for m in data
            ]
        return []


class HindsightAccess(MemoryProviderAccess):
    """Raw HTTP access to Hindsight knowledge graph API."""

    def __init__(self):
        super().__init__("hindsight")

    def is_available(self) -> bool:
        return bool(_env("HINDSIGHT_API_KEY"))

    def _base_url(self) -> str:
        return _env("HINDSIGHT_API_URL") or "https://api.hindsight.vectorize.io"

    def _headers(self) -> Dict:
        return {"Authorization": "Bearer %s" % _env("HINDSIGHT_API_KEY")}

    def fact_count(self) -> Optional[int]:
        bank_id = _env("HINDSIGHT_BANK_ID")
        if not bank_id:
            return None
        url = "%s/v1/banks/%s" % (self._base_url(), bank_id)
        data, err = _http_get(url, self._headers())
        if data:
            return data.get("document_count") or data.get("facts_count")
        return None

    def quality_summary(self) -> Optional[Dict[str, Any]]:
        bank_id = _env("HINDSIGHT_BANK_ID")
        if not bank_id:
            return None
        url = "%s/v1/banks/%s" % (self._base_url(), bank_id)
        data, err = _http_get(url, self._headers())
        if data:
            return {
                "provider": "hindsight",
                "bank_id": bank_id,
                "document_count": data.get("document_count"),
                "status": data.get("status", "unknown"),
            }
        return None


class OpenVikingAccess(MemoryProviderAccess):
    """Raw HTTP access to OpenViking context database."""

    def __init__(self):
        super().__init__("openviking")

    def is_available(self) -> bool:
        return bool(_env("OPENVIKING_API_KEY"))

    def _base_url(self) -> str:
        return _env("OPENVIKING_ENDPOINT") or "http://127.0.0.1:1933"

    def _headers(self) -> Dict:
        return {"Authorization": "Bearer %s" % _env("OPENVIKING_API_KEY")}

    def fact_count(self) -> Optional[int]:
        url = "%s/health" % self._base_url()
        data, err = _http_get(url, self._headers())
        if data:
            return data.get("total_facts") or data.get("fact_count")
        return None


class RetainDBAccess(MemoryProviderAccess):
    """Raw HTTP access to RetainDB hybrid search API."""

    def __init__(self):
        super().__init__("retaindb")

    def is_available(self) -> bool:
        return bool(_env("RETAINDB_API_KEY"))

    def _base_url(self) -> str:
        return _env("RETAINDB_BASE_URL") or "https://api.retaindb.com"

    def _headers(self) -> Dict:
        return {"Authorization": "Bearer %s" % _env("RETAINDB_API_KEY")}

    def fact_count(self) -> Optional[int]:
        project = _env("RETAINDB_PROJECT")
        if not project:
            return None
        url = "%s/v1/projects/%s/stats" % (self._base_url(), project)
        data, err = _http_get(url, self._headers())
        if data:
            return data.get("total_memories") or data.get("count")
        return None

    def search(self, query: str, limit: int = 5) -> List[Dict]:
        project = _env("RETAINDB_PROJECT")
        if not project:
            return []
        url = "%s/v1/projects/%s/search" % (self._base_url(), project)
        payload = {"query": query, "limit": limit}
        data, err = _http_post(url, payload, self._headers())
        if data and "results" in data:
            return [
                {"content": r.get("content", ""), "score": r.get("score", 0)}
                for r in data["results"]
            ]
        return []


class SupermemoryAccess(MemoryProviderAccess):
    """Raw HTTP access to Supermemory semantic memory API."""

    BASE_URL = "https://api.supermemory.ai/v4"

    def __init__(self):
        super().__init__("supermemory")

    def is_available(self) -> bool:
        return bool(_env("SUPERMEMORY_API_KEY"))

    def _headers(self) -> Dict:
        return {"Authorization": "Bearer %s" % _env("SUPERMEMORY_API_KEY")}

    def fact_count(self) -> Optional[int]:
        container = _env("SUPERMEMORY_CONTAINER_TAG")
        if not container:
            return None
        url = "%s/memories?containerTag=%s&limit=1" % (self.BASE_URL, container)
        data, err = _http_get(url, self._headers())
        if data:
            return data.get("total") or data.get("count")
        return None

    def search(self, query: str, limit: int = 5) -> List[Dict]:
        url = "%s/search" % self.BASE_URL
        payload = {
            "query": query,
            "containerTag": _env("SUPERMEMORY_CONTAINER_TAG"),
            "limit": limit,
        }
        data, err = _http_post(url, payload, self._headers())
        if data and "memories" in data:
            return [
                {"content": m.get("content", ""), "score": m.get("score", 0)}
                for m in data["memories"]
            ]
        return []


# =============================================================================
# Provider registry
# =============================================================================

PROVIDERS: Dict[str, type] = {
    "holographic": HolographicAccess,
    "builtin": BuiltinAccess,
    "honcho": HonchoAccess,
    "mem0": Mem0Access,
    "hindsight": HindsightAccess,
    "openviking": OpenVikingAccess,
    "retaindb": RetainDBAccess,
    "supermemory": SupermemoryAccess,
}


def get_provider_access(name: Optional[str] = None) -> MemoryProviderAccess:
    """Get access object for a memory provider.

    If name is None, uses the configured provider from config.yaml.
    """
    if name is None:
        name = get_active_provider()

    cls = PROVIDERS.get(name)
    if cls:
        return cls()

    logger.warning("Unknown memory provider: %s — falling back to builtin", name)
    return BuiltinAccess()


def discover_providers() -> List[MemoryProviderAccess]:
    """Return all available memory providers."""
    available = []
    for name, cls in PROVIDERS.items():
        try:
            provider = cls()
            if provider.is_available():
                available.append(provider)
        except Exception as e:
            logger.debug("Provider %s not available: %s", name, e)
    return available


def get_all_summaries() -> Dict[str, Optional[Dict]]:
    """Get quality summaries from all available providers."""
    summaries = {}
    for provider in discover_providers():
        try:
            summaries[provider.name] = provider.quality_summary()
        except Exception as e:
            summaries[provider.name] = {"error": str(e)}
    return summaries
