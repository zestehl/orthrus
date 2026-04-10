"""
ARGUS audit trail — append-only log of all decisions and actions.

Every restart/kill/inject decision is recorded with full context:
entropy detections, directive checks, metrics snapshot. INSERT-only
(no UPDATE, no DELETE). Queryable by session, action type, time range.
Exportable as JSONL for external analysis.

This is the foundation for all other monitoring services — they all
write to the audit trail.
"""

import json
import logging
import sqlite3
from typing import Any, Dict, List, Optional

logger = logging.getLogger("orthrus.audit")


def ensure_table(cursor: sqlite3.Cursor, conn: sqlite3.Connection) -> None:
    """Create audit_log table if it doesn't exist."""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL DEFAULT (datetime('now')),
            session_id TEXT NOT NULL,
            action_type TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'info',
            entropy_detections TEXT,
            directive_checks TEXT,
            metrics TEXT,
            decision_reason TEXT,
            action_result TEXT,
            metadata TEXT
        )
    """)
    # Indexes for common queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_session
        ON audit_log(session_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_timestamp
        ON audit_log(timestamp)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_action_type
        ON audit_log(action_type)
    """)
    conn.commit()


def record_decision(
    cursor: sqlite3.Cursor,
    conn: sqlite3.Connection,
    session_id: str,
    action_type: str,
    severity: str = "info",
    entropy_detections: Optional[List[Dict]] = None,
    directive_checks: Optional[List[Dict]] = None,
    metrics: Optional[Dict] = None,
    decision_reason: Optional[str] = None,
    action_result: Optional[str] = None,
    metadata: Optional[Dict] = None,
) -> Optional[int]:
    """Record a decision in the audit trail. Returns the audit row ID."""
    try:
        cursor.execute(
            """
            INSERT INTO audit_log
            (session_id, action_type, severity, entropy_detections,
             directive_checks, metrics, decision_reason, action_result, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                action_type,
                severity,
                json.dumps(entropy_detections) if entropy_detections else None,
                json.dumps(directive_checks) if directive_checks else None,
                json.dumps(metrics) if metrics else None,
                decision_reason,
                action_result,
                json.dumps(metadata) if metadata else None,
            ),
        )
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        logger.error("Failed to record audit entry for %s: %s", session_id, e)
        return None


def record_entropy_event(
    cursor: sqlite3.Cursor,
    conn: sqlite3.Connection,
    session_id: str,
    entropy_type: str,
    severity: str,
    details: Dict[str, Any],
) -> Optional[int]:
    """Record an entropy detection event in the audit trail."""
    return record_decision(
        cursor,
        conn,
        session_id,
        action_type="entropy_detected",
        severity=severity,
        entropy_detections=[{"type": entropy_type, **details}],
        decision_reason=f"Entropy detected: {entropy_type}",
    )


def record_resource_alert(
    cursor: sqlite3.Cursor,
    conn: sqlite3.Connection,
    resource_type: str,
    severity: str,
    details: Dict[str, Any],
) -> Optional[int]:
    """Record a resource exhaustion alert in the audit trail."""
    return record_decision(
        cursor,
        conn,
        session_id="system",
        action_type="resource_alert",
        severity=severity,
        decision_reason=f"Resource alert: {resource_type}",
        metadata=details,
    )


def record_drift_event(
    cursor: sqlite3.Cursor,
    conn: sqlite3.Connection,
    file_label: str,
    change_type: str,
    old_hash: Optional[str],
    new_hash: Optional[str],
) -> Optional[int]:
    """Record a config drift event in the audit trail."""
    return record_decision(
        cursor,
        conn,
        session_id="system",
        action_type="config_drift",
        severity="warning",
        decision_reason=f"Config drift: {file_label} {change_type}",
        metadata={
            "file": file_label,
            "change_type": change_type,
            "old_hash": old_hash,
            "new_hash": new_hash,
        },
    )


def record_cleanup_event(
    cursor: sqlite3.Cursor,
    conn: sqlite3.Connection,
    findings: Dict[str, List[Dict]],
) -> Optional[int]:
    """Record a cleanup sweep result in the audit trail."""
    total = sum(len(v) for v in findings.values())
    if total == 0:
        return None
    return record_decision(
        cursor,
        conn,
        session_id="system",
        action_type="cleanup_sweep",
        severity="info" if total < 5 else "warning",
        decision_reason=f"Cleanup: {total} orphaned sessions found",
        metadata={k: len(v) for k, v in findings.items()},
    )


def record_provider_alert(
    cursor: sqlite3.Cursor,
    conn: sqlite3.Connection,
    providers: List[str],
    severity: str,
    details: Dict[str, Any],
) -> Optional[int]:
    """Record a provider health alert in the audit trail."""
    return record_decision(
        cursor,
        conn,
        session_id="system",
        action_type="provider_health",
        severity=severity,
        decision_reason=f"Provider health: {', '.join(providers)} ({severity})",
        metadata=details,
    )


def record_cost_alert(
    cursor: sqlite3.Cursor,
    conn: sqlite3.Connection,
    details: Dict[str, Any],
) -> Optional[int]:
    """Record a cost/budget alert in the audit trail."""
    daily = details.get("daily_budget", {})
    spent = daily.get("spent", 0)
    budget = daily.get("budget", 0)
    percent = daily.get("percent_used", 0)
    
    return record_decision(
        cursor,
        conn,
        session_id="system",
        action_type="cost_alert",
        severity="warning" if percent < 100 else "critical",
        decision_reason=f"Budget: ${spent:.2f} / ${budget:.2f} ({percent:.1f}%)",
        metadata=details,
    )


def record_circuit_event(
    cursor: sqlite3.Cursor,
    conn: sqlite3.Connection,
    provider: str,
    transition: str,
    reason: str,
) -> Optional[int]:
    """Record a circuit breaker state change in the audit trail."""
    severity = "critical" if "OPEN" in transition else "warning"
    return record_decision(
        cursor,
        conn,
        session_id="system",
        action_type="circuit_breaker",
        severity=severity,
        decision_reason=f"Circuit {transition} for {provider}: {reason}",
        metadata={"provider": provider, "transition": transition, "reason": reason},
    )


def query_by_session(
    cursor: sqlite3.Cursor,
    session_id: str,
    limit: int = 50,
) -> List[Dict]:
    """Query audit trail entries for a specific session."""
    cursor.execute(
        """
        SELECT * FROM audit_log
        WHERE session_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        (session_id, limit),
    )
    return [dict(row) for row in cursor.fetchall()]


def query_by_action_type(
    cursor: sqlite3.Cursor,
    action_type: str,
    limit: int = 50,
) -> List[Dict]:
    """Query audit trail entries by action type."""
    cursor.execute(
        """
        SELECT * FROM audit_log
        WHERE action_type = ?
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        (action_type, limit),
    )
    return [dict(row) for row in cursor.fetchall()]


def query_by_time_range(
    cursor: sqlite3.Cursor,
    start_time: str,
    end_time: str,
    limit: int = 200,
) -> List[Dict]:
    """Query audit trail entries within a time range (ISO format)."""
    cursor.execute(
        """
        SELECT * FROM audit_log
        WHERE timestamp BETWEEN ? AND ?
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        (start_time, end_time, limit),
    )
    return [dict(row) for row in cursor.fetchall()]


def export_jsonl(
    cursor: sqlite3.Cursor,
    output_path: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
) -> int:
    """Export audit trail to JSONL format. Returns record count."""
    if start_time and end_time:
        cursor.execute(
            """
            SELECT * FROM audit_log
            WHERE timestamp BETWEEN ? AND ?
            ORDER BY timestamp ASC
            """,
            (start_time, end_time),
        )
    else:
        cursor.execute("SELECT * FROM audit_log ORDER BY timestamp ASC")

    rows = cursor.fetchall()
    count = 0
    with open(output_path, "w") as f:
        for row in rows:
            record = dict(row)
            # Parse JSON fields back to objects for clean export
            for field in ("entropy_detections", "directive_checks", "metrics", "metadata"):
                if record.get(field) and isinstance(record[field], str):
                    try:
                        record[field] = json.loads(record[field])
                    except (json.JSONDecodeError, TypeError):
                        pass
            f.write(json.dumps(record, default=str) + "\n")
            count += 1

    logger.info("Exported %d audit records to %s", count, output_path)
    return count


def get_summary(
    cursor: sqlite3.Cursor,
    hours: int = 24,
) -> Dict[str, Any]:
    """Get audit trail summary for the last N hours."""
    cursor.execute(
        """
        SELECT
            action_type,
            severity,
            COUNT(*) as count
        FROM audit_log
        WHERE timestamp > datetime('now', ?)
        GROUP BY action_type, severity
        ORDER BY count DESC
        """,
        (f"-{hours} hours",),
    )
    by_type = {}
    for row in cursor.fetchall():
        key = row["action_type"]
        if key not in by_type:
            by_type[key] = {"total": 0, "by_severity": {}}
        by_type[key]["total"] += row["count"]
        by_type[key]["by_severity"][row["severity"]] = row["count"]

    cursor.execute(
        """
        SELECT COUNT(*) as total FROM audit_log
        WHERE timestamp > datetime('now', ?)
        """,
        (f"-{hours} hours",),
    )
    total = cursor.fetchone()["total"]

    return {"hours": hours, "total_entries": total, "by_action_type": by_type}
