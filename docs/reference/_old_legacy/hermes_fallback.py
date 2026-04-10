"""
Hermes internals fallback — subprocess stubs when hermes-agent modules
are unavailable (wrong Python version, missing modules, etc.).

This module provides the same interface as the real hermes modules:
  pause_job, resume_job, trigger_job, list_jobs, get_job, update_job
  SessionDB, DEFAULT_DB_PATH, _hermes_load_config, load_hermes_dotenv

Import from this module on ImportError from the real hermes modules.
"""

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List


def _hermes_path(*parts: str) -> Path:
    """Build a path under HERMES_HOME (~/.hermes)."""
    return Path.home() / ".hermes".join(parts)


def pause_job(job_id, reason=None):
    r = subprocess.run(
        ["hermes", "cron", "pause", str(job_id)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return {"id": job_id, "enabled": False} if r.returncode == 0 else None


def resume_job(job_id):
    r = subprocess.run(
        ["hermes", "cron", "resume", str(job_id)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return {"id": job_id, "enabled": True} if r.returncode == 0 else None


def trigger_job(job_id):
    r = subprocess.run(
        ["hermes", "cron", "run", str(job_id)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return {"id": job_id} if r.returncode == 0 else None


def list_jobs(include_disabled=False):
    r = subprocess.run(
        ["hermes", "cron", "list", "--all"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if r.returncode == 0:
        try:
            return json.loads(r.stdout).get("jobs", [])
        except json.JSONDecodeError:
            return []
    return []


def get_job(job_id):
    for j in list_jobs(include_disabled=True):
        if j.get("id") == job_id:
            return j
    return None


def update_job(job_id, updates):
    return None


class SessionDB:
    """Stub when hermes internals unavailable."""

    def __init__(self, path):
        pass

    def list_sessions_rich(self, **kw):
        return []

    def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        return []

    def close(self):
        pass


DEFAULT_DB_PATH = str(Path.home() / ".hermes" / "state.db")


def _hermes_load_config():
    return {}


def load_hermes_dotenv():
    """Fallback: load hermes .env — no-op when hermes internals unavailable."""
    pass
