"""Side-by-side comparison of attempt 1 vs attempt 2 for a user and scenario."""

from typing import Any, Dict, Optional
from db import get_connection


def _scores_by_criterion(session_id: str) -> Dict[str, str]:
    """Return criterion -> level map for one scored session."""
    conn = get_connection()
    try:
        rows = conn.execute("SELECT criterion, level FROM scores WHERE session_id = ?", (session_id,)).fetchall()
        return {r["criterion"]: r["level"] for r in rows}
    finally:
        conn.close()


def get_comparison(user_id: str, scenario_id: str) -> Optional[Dict[str, Any]]:
    """Return side-by-side criterion levels for attempt 1 vs attempt 2."""
    conn = get_connection()
    try:
        sessions = conn.execute(
            "SELECT id, attempt_number FROM sessions WHERE user_id = ? AND scenario_id = ? ORDER BY attempt_number",
            (user_id, scenario_id),
        ).fetchall()
    finally:
        conn.close()

    if len(sessions) < 2:
        return None  # Comparison only available after two attempts

    s1 = _scores_by_criterion(sessions[0]["id"])
    s2 = _scores_by_criterion(sessions[1]["id"])
    all_criteria = sorted(set(s1) | set(s2))

    rows = [
        {
            "criterion": c,
            "attempt_1": s1.get(c, "Insufficient evidence"),
            "attempt_2": s2.get(c, "Insufficient evidence"),
        }
        for c in all_criteria
    ]
    return {
        "session_1": sessions[0]["id"],
        "session_2": sessions[1]["id"],
        "rows": rows,
    }
