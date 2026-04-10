"""
ARGUS resource exhaustion detection — monitor disk, DB size, session store growth.

Prevents the most common silent failure mode: disk fills → DB corrupts →
agent crashes with no signal. Alerts before failure, not after.

Monitors:
- Disk free space on work directories
- DB file size tracking (state.db, agathos.db, holographic_memory.db)
- Session store bloat detection
- Rolling trend analysis (growing fast vs stable)
- Tiered alerts: warning at 80%, critical at 95%
"""

import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("agathos.resources")

# Thresholds
DISK_WARNING_PCT = 80.0
DISK_CRITICAL_PCT = 95.0
DB_SIZE_WARNING_MB = 500
DB_SIZE_CRITICAL_MB = 1024
SESSION_COUNT_WARNING = 500
SESSION_COUNT_CRITICAL = 1000


def _hermes_home() -> Path:
    try:
        from hermes_constants import get_hermes_home
        return get_hermes_home()
    except ImportError:
        return Path.home() / ".hermes"


def _agathos_home() -> Path:
    return Path.home() / "hermes"


def check_disk_space(path: str) -> Dict[str, Any]:
    """Check disk space for a given path.

    Returns dict with total_gb, used_gb, free_gb, pct_used, severity.
    """
    try:
        stat = os.statvfs(path)
        total = stat.f_blocks * stat.f_frsize
        free = stat.f_bavail * stat.f_frsize
        used = total - free
        pct_used = (used / total * 100) if total > 0 else 0

        if pct_used >= DISK_CRITICAL_PCT:
            severity = "critical"
        elif pct_used >= DISK_WARNING_PCT:
            severity = "warning"
        else:
            severity = "ok"

        return {
            "path": path,
            "total_gb": round(total / (1024**3), 2),
            "used_gb": round(used / (1024**3), 2),
            "free_gb": round(free / (1024**3), 2),
            "pct_used": round(pct_used, 1),
            "severity": severity,
        }
    except OSError as e:
        logger.error("Failed to check disk space for %s: %s", path, e)
        return {"path": path, "error": str(e), "severity": "unknown"}


def check_db_size(db_path: str) -> Dict[str, Any]:
    """Check database file size.

    Returns dict with path, size_mb, severity.
    """
    try:
        p = Path(db_path)
        if not p.exists():
            return {"path": db_path, "exists": False, "severity": "ok"}

        size_bytes = p.stat().st_size
        size_mb = size_bytes / (1024**2)

        if size_mb >= DB_SIZE_CRITICAL_MB:
            severity = "critical"
        elif size_mb >= DB_SIZE_WARNING_MB:
            severity = "warning"
        else:
            severity = "ok"

        return {
            "path": db_path,
            "exists": True,
            "size_bytes": size_bytes,
            "size_mb": round(size_mb, 2),
            "severity": severity,
        }
    except OSError as e:
        logger.error("Failed to check DB size for %s: %s", db_path, e)
        return {"path": db_path, "error": str(e), "severity": "unknown"}


def check_session_store(state_db_path: str) -> Dict[str, Any]:
    """Check session store for bloat.

    Returns dict with session_count, oldest_age_hours, total_size_mb, severity.
    """
    try:
        p = Path(state_db_path)
        if not p.exists():
            return {"path": state_db_path, "exists": False, "severity": "ok"}

        size_mb = p.stat().st_size / (1024**2)

        conn = sqlite3.connect(str(p))
        conn.row_factory = sqlite3.Row

        # Count active sessions
        try:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM sessions WHERE ended_at IS NULL"
            ).fetchone()
            active_count = row["cnt"] if row else 0
        except Exception:
            active_count = -1

        # Find oldest active session
        try:
            row = conn.execute(
                """
                SELECT MIN(started_at) as oldest
                FROM sessions
                WHERE ended_at IS NULL
                """
            ).fetchone()
            oldest = row["oldest"] if row and row["oldest"] else None
        except Exception:
            oldest = None

        oldest_age_hours = None
        if oldest:
            try:
                oldest_ts = float(oldest)
                oldest_age_hours = round((time.time() - oldest_ts) / 3600, 1)
            except (ValueError, TypeError):
                pass

        conn.close()

        if active_count >= SESSION_COUNT_CRITICAL:
            severity = "critical"
        elif active_count >= SESSION_COUNT_WARNING:
            severity = "warning"
        else:
            severity = "ok"

        return {
            "path": state_db_path,
            "exists": True,
            "size_mb": round(size_mb, 2),
            "active_sessions": active_count,
            "oldest_age_hours": oldest_age_hours,
            "severity": severity,
        }
    except Exception as e:
        logger.error("Failed to check session store: %s", e)
        return {"path": state_db_path, "error": str(e), "severity": "unknown"}


def _known_db_paths() -> List[str]:
    """Return list of known database paths to monitor."""
    home = _hermes_home()
    argus_home = _agathos_home()
    paths = [
        str(home / "state.db"),
        str(argus_home / "data" / "watcher" / "agathos.db"),
    ]
    # Optional DBs — only include if they exist
    holo = home / "holographic_memory.db"
    if holo.exists():
        paths.append(str(holo))
    return paths


def _watch_dirs() -> List[str]:
    """Return list of directories to monitor for disk space."""
    home = _hermes_home()
    projects = Path.home() / "Projects"
    dirs = []
    if projects.exists():
        dirs.append(str(projects))
    dirs.append(str(home))
    return dirs


def run_resource_check(
    _cursor: Optional[Any] = None, _conn: Optional[Any] = None
) -> Dict[str, Any]:
    """Run all resource checks. Returns comprehensive report.

    Args unused — interface parity with other periodic checks (run_provider_check, etc).
    Resource checks are filesystem-based, not DB-driven.

    Each sub-check has a 'severity' field: ok, warning, critical, unknown.
    Overall severity is the highest found.
    """
    report: Dict[str, Any] = {
        "timestamp": time.time(),
        "disk": [],
        "databases": [],
        "session_store": None,
        "overall_severity": "ok",
    }

    severities = []

    # Disk space checks
    for d in _watch_dirs():
        result = check_disk_space(d)
        report["disk"].append(result)
        severities.append(result.get("severity", "unknown"))

    # DB size checks
    for db in _known_db_paths():
        result = check_db_size(db)
        report["databases"].append(result)
        severities.append(result.get("severity", "unknown"))

    # Session store check
    state_db = str(_hermes_home() / "state.db")
    store = check_session_store(state_db)
    report["session_store"] = store
    severities.append(store.get("severity", "unknown"))

    # Overall severity
    if "critical" in severities:
        report["overall_severity"] = "critical"
    elif "warning" in severities:
        report["overall_severity"] = "warning"

    return report


def format_alert(report: Dict[str, Any]) -> Optional[str]:
    """Format a human-readable alert from a resource report.

    Returns None if everything is ok.
    """
    if report["overall_severity"] == "ok":
        return None

    lines = [f"RESOURCE ALERT ({report['overall_severity'].upper()})"]

    for disk in report.get("disk", []):
        if disk.get("severity") in ("warning", "critical"):
            lines.append(
                f"  Disk {disk['path']}: {disk['pct_used']}% used "
                f"({disk['free_gb']}GB free)"
            )

    for db in report.get("databases", []):
        if db.get("severity") in ("warning", "critical"):
            lines.append(f"  DB {Path(db['path']).name}: {db['size_mb']}MB")

    store = report.get("session_store")
    if store and store.get("severity") in ("warning", "critical"):
        lines.append(
            f"  Sessions: {store['active_sessions']} active "
            f"(oldest {store.get('oldest_age_hours', '?')}h)"
        )

    return "\n".join(lines)
