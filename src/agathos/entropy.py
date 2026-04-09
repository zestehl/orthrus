"""
Entropy detection algorithms for Agathos.

Each function takes a sqlite3.Cursor and session_id, returns List[Dict]
with entropy_type, severity, and details.

Pure functions — no side effects, no state.
"""

import json
import logging
import sqlite3
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("agathos.entropy")

# Import SessionDB/DEFAULT_DB_PATH at module level so tests can mock them
try:
    from hermes_state import SessionDB, DEFAULT_DB_PATH
except (ImportError, TypeError):
    SessionDB = None
    DEFAULT_DB_PATH = None


def detect_repeat_tool_calls(
    cursor: sqlite3.Cursor, session_id: str, threshold: int = 3
) -> List[Dict]:
    """Detect repeated identical tool calls within a session.

    Identifies when the same tool is called with identical arguments multiple
    times, indicating potential stuck loops or wasted iterations.

    Args:
        cursor: Database cursor for agathos.db
        session_id: Session to analyze
        threshold: Minimum repeat count to trigger detection (default: 3)

    Returns:
        List of detection dicts with keys:
        - entropy_type: "repeat_tool_calls"
        - severity: "warning" (3-4 repeats) or "critical" (5+)
        - details: JSON with tool_name, tool_args, count

    Query scope: Last 10 minutes of tool_calls table.
    """

    detections = []
    try:
        cursor.execute(
            """
            SELECT tool_name, tool_args, COUNT(*) as count
            FROM tool_calls
            WHERE session_id = ? AND timestamp > datetime('now', '-10 minutes')
            GROUP BY tool_name, tool_args
            HAVING count >= ?
        """,
            (session_id, threshold),
        )
        for row in cursor.fetchall():
            detections.append(
                {
                    "entropy_type": "repeat_tool_calls",
                    "severity": "warning" if row["count"] < 5 else "critical",
                    "details": json.dumps(
                        {
                            "tool_name": row["tool_name"],
                            "tool_args": row["tool_args"],
                            "count": row["count"],
                        }
                    ),
                }
            )
    except Exception as e:
        logger.error("Error detecting repeat tool calls: %s", e, exc_info=True)
    return detections


def detect_repeat_commands(
    cursor: sqlite3.Cursor, session_id: str, threshold: int = 3
) -> List[Dict]:
    """Detect repeated terminal commands within a session.

    Identifies when the same shell command is executed multiple times,
    indicating potential redundant operations or stuck terminal loops.

    Args:
        cursor: Database cursor for agathos.db
        session_id: Session to analyze
        threshold: Minimum repeat count to trigger detection (default: 3)

    Returns:
        List of detection dicts with keys:
        - entropy_type: "repeat_commands"
        - severity: "warning" (3-4 repeats) or "critical" (5+)
        - details: JSON with command, count

    Query scope: Last 10 minutes of terminal_commands table.
    """
    detections = []
    try:
        cursor.execute(
            """
            SELECT command, COUNT(*) as count
            FROM terminal_commands
            WHERE session_id = ? AND timestamp > datetime('now', '-10 minutes')
            GROUP BY command
            HAVING count >= ?
        """,
            (session_id, threshold),
        )
        for row in cursor.fetchall():
            detections.append(
                {
                    "entropy_type": "repeat_commands",
                    "severity": "warning" if row["count"] < 5 else "critical",
                    "details": json.dumps(
                        {"command": row["command"], "count": row["count"]}
                    ),
                }
            )
    except Exception as e:
        logger.error("Error detecting repeat commands: %s", e, exc_info=True)
    return detections


def detect_stuck_loops(cursor: sqlite3.Cursor, session_id: str) -> List[Dict]:
    """Detect stuck loops — repeating sequences of tool calls.

    Identifies when a pattern of tool calls repeats (e.g., read_file
    -> write_file -> read_file -> write_file), indicating the agent
    is stuck in a cycle without making progress.

    Args:
        cursor: Database cursor for agathos.db
        session_id: Session to analyze

    Returns:
        List of detection dicts with keys:
        - entropy_type: "stuck_loop"
        - severity: "warning" (2 repeats) or "critical" (3+)
        - details: JSON with pattern (tool sequence), repeat_count

    Algorithm: Scans last 50 tool calls, looks for repeating 3-call
    or 4-call sequences. Sequence must repeat at least twice.
    """
    detections = []
    try:
        cursor.execute(
            """
            SELECT tool_name, tool_args
            FROM tool_calls
            WHERE session_id = ?
            ORDER BY timestamp DESC
            LIMIT 10
        """,
            (session_id,),
        )
        tool_calls = [dict(row) for row in cursor.fetchall()]
        if len(tool_calls) >= 6:
            for pattern_length in range(2, 4):
                if len(tool_calls) >= pattern_length * 2:
                    pattern = tool_calls[:pattern_length]
                    next_pattern = tool_calls[pattern_length : pattern_length * 2]
                    if pattern == next_pattern:
                        detections.append(
                            {
                                "entropy_type": "stuck_loop",
                                "severity": "critical",
                                "details": json.dumps(
                                    {
                                        "pattern_length": pattern_length,
                                        "pattern": pattern,
                                    }
                                ),
                            }
                        )
    except Exception as e:
        logger.error("Error detecting stuck loops: %s", e, exc_info=True)
    return detections


def detect_no_file_changes(cursor: sqlite3.Cursor, session_id: str) -> List[Dict]:
    """Detect write_file/patch operations that produced no file changes.

    Identifies when write_file or patch tools report file_changed=False,
    indicating the operation had no effect (e.g., writing same content,
    patch with non-matching old_string).

    Args:
        cursor: Database cursor for agathos.db
        session_id: Session to analyze

    Returns:
        List of detection dicts with keys:
        - entropy_type: "no_file_changes"
        - severity: "critical" (all cases — wasted operations)
        - details: JSON with tool_call_id, tool_name, file_path

    Query scope: Last 10 minutes, write_file and patch tools only.
    """
    detections = []
    try:
        cursor.execute(
            """
            SELECT tc.id, tc.tool_name, tc.file_path
            FROM tool_calls tc
            WHERE tc.session_id = ?
            AND tc.tool_name IN ('write_file', 'patch')
            AND tc.file_changed = FALSE
            AND tc.timestamp > datetime('now', '-10 minutes')
        """,
            (session_id,),
        )
        for row in cursor.fetchall():
            detections.append(
                {
                    "entropy_type": "no_file_changes",
                    "severity": "critical",
                    "details": json.dumps(
                        {
                            "tool_call_id": row["id"],
                            "tool_name": row["tool_name"],
                            "file_path": row["file_path"],
                        }
                    ),
                }
            )
    except Exception as e:
        logger.error("Error detecting no file changes: %s", e, exc_info=True)
    return detections


def detect_error_cascade(cursor: sqlite3.Cursor, session_id: str) -> List[Dict]:
    """Detect cascading tool failures — consecutive errors without successes.

    Identifies when 3+ consecutive tool calls fail, indicating the agent
    is in a failure spiral (e.g., repeatedly trying the same failing operation).

    Args:
        cursor: Database cursor for agathos.db
        session_id: Session to analyze

    Returns:
        List of detection dicts with keys:
        - entropy_type: "error_cascade"
        - severity: "warning" (3-4 consecutive) or "critical" (5+)
        - details: JSON with consecutive_errors, tools (list), error_messages

    Algorithm: Scans last 20 tool calls, finds longest consecutive error
    run. Returns one detection per cascade found.
    """
    detections = []
    try:
        cursor.execute(
            """
            SELECT tool_name, success, error_message, timestamp
            FROM tool_calls
            WHERE session_id = ?
            ORDER BY timestamp ASC
            LIMIT 20
        """,
            (session_id,),
        )
        rows = cursor.fetchall()
        if len(rows) < 3:
            return detections

        # Scan for longest consecutive error run
        max_run = 0
        current_run = 0
        run_tools = []
        current_run_tools = []

        for row in rows:
            is_error = (row["success"] == 0) or (
                row["success"] is None and bool(row["error_message"])
            )
            if is_error:
                current_run += 1
                current_run_tools.append(row["tool_name"])
            else:
                if current_run > max_run:
                    max_run = current_run
                    run_tools = list(current_run_tools)
                current_run = 0
                current_run_tools = []

        # Check final run
        if current_run > max_run:
            max_run = current_run
            run_tools = list(current_run_tools)

        if max_run >= 3:
            severity = "warning" if max_run < 5 else "critical"
            detections.append(
                {
                    "entropy_type": "error_cascade",
                    "severity": severity,
                    "details": json.dumps(
                        {
                            "consecutive_errors": max_run,
                            "tools": run_tools[:5],
                        }
                    ),
                }
            )
            logger.warning(
                "Error cascade detected in session %s: %d consecutive failures",
                session_id[:15],
                max_run,
            )
    except Exception as e:
        logger.error("Error detecting error cascade: %s", e, exc_info=True)
    return detections


def detect_budget_pressure(
    cursor: sqlite3.Cursor,
    session_id: str,
    max_budget: int,
    db_path: str,
) -> List[Dict]:
    """Detect unproductive iteration budget burn.

    Counts assistant messages from state.db (each = 1 API call / iteration).
    Flags when budget ratio is high AND session shows entropy or errors.
    """
    detections = []

    # Strip type prefix: cron_ec1a5e9f4c12 -> ec1a5e9f4c12
    parts = session_id.split("_", 1)
    real_session_id = parts[1] if len(parts) == 2 else session_id

    try:
        db = SessionDB(db_path)
        try:
            messages = db.get_messages(real_session_id)
        finally:
            db.close()
    except Exception:
        return detections

    if not messages:
        return detections

    # Count assistant messages (each = 1 iteration consumed)
    iterations_used = sum(1 for m in messages if m.get("role") == "assistant")
    if iterations_used == 0:
        return detections

    if max_budget <= 0:
        return detections

    # Compute session age from first message timestamp
    timestamps = []
    for m in messages:
        ts = m.get("timestamp")
        if ts:
            try:
                timestamps.append(float(ts))
            except (ValueError, TypeError):
                pass

    if timestamps:
        session_age_sec = max(timestamps) - min(timestamps)
        session_age_min = max(session_age_sec / 60.0, 1.0)
    else:
        session_age_min = 1.0

    burn_rate = iterations_used / session_age_min
    budget_ratio = iterations_used / max_budget

    # Check recent error rate from agathos.db
    cursor.execute(
        """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as errors
        FROM tool_calls
        WHERE session_id = ?
        AND timestamp > datetime('now', '-5 minutes')
    """,
        (session_id,),
    )
    row = cursor.fetchone()
    total_recent = row["total"] if row and row["total"] else 0
    error_recent = row["errors"] if row and row["errors"] else 0
    error_rate = error_recent / total_recent if total_recent > 0 else 0.0

    # Check for existing entropy detections in last 10 min
    cursor.execute(
        """
        SELECT COUNT(*) as cnt FROM entropy_detections
        WHERE session_id = ?
        AND timestamp > datetime('now', '-10 minutes')
    """,
        (session_id,),
    )
    entropy_row = cursor.fetchone()
    has_entropy = (entropy_row["cnt"] > 0) if entropy_row else False

    # Decision: flag when budget is draining unproductively
    has_problems = has_entropy or error_rate > 0.5

    if budget_ratio >= 0.85 and has_problems:
        severity = "critical"
    elif budget_ratio >= 0.70 and has_problems:
        severity = "warning"
    elif budget_ratio >= 0.90:
        severity = "warning"
    else:
        return detections

    detections.append(
        {
            "entropy_type": "budget_pressure",
            "severity": severity,
            "details": json.dumps(
                {
                    "iterations_used": iterations_used,
                    "max_budget": max_budget,
                    "budget_ratio": round(budget_ratio, 3),
                    "burn_rate_per_min": round(burn_rate, 2),
                    "session_age_min": round(session_age_min, 1),
                    "error_rate": round(error_rate, 3),
                    "has_entropy": has_entropy,
                }
            ),
        }
    )
    logger.warning(
        "Budget pressure in session %s: %d/%d iterations (%.0f%%), burn %.1f/min",
        session_id[:15],
        iterations_used,
        max_budget,
        budget_ratio * 100,
        burn_rate,
    )

    return detections


def detect_tool_error(tool_name: str, result: str) -> Tuple[bool, str]:
    """Detect tool failures using same heuristic as agent.display._detect_tool_failure.

    Returns (is_error, error_detail).  Empty string for error_detail on success.
    """
    if not result:
        return False, ""

    # Terminal: check exit_code in JSON result
    if tool_name == "terminal":
        try:
            data = json.loads(result)
            exit_code = data.get("exit_code")
            if exit_code is not None and exit_code != 0:
                return True, "exit %s" % exit_code
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass
        return False, ""

    # Memory: check for capacity errors
    if tool_name == "memory":
        try:
            data = json.loads(result)
            if data.get("success") is False and "exceed the limit" in data.get(
                "error", ""
            ):
                return True, "memory full"
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass

    # Generic: check first 500 chars for error indicators
    lower = result[:500].lower()
    if '"error"' in lower or '"failed"' in lower or result.startswith("Error"):
        return True, "error detected"

    return False, ""


def detect_file_changed(tool_name: str, result: str, is_error: bool) -> Optional[bool]:
    """Detect if a write_file/patch operation actually changed a file.

    Returns True if file was changed, False if not, None if unknown/not applicable.
    """
    if tool_name not in ("write_file", "patch"):
        return None  # Not a write operation

    if is_error:
        return False  # Error means file wasn't changed

    if not result:
        return None  # Can't determine

    try:
        data = json.loads(result)
        if isinstance(data, dict):
            if data.get("success") is True:
                return True
            if "content" in data or "diff" in data:
                return True
            if data.get("error"):
                return False
    except (json.JSONDecodeError, TypeError):
        pass

    # Non-JSON result from write tool without error → assume changed
    return True
