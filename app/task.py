"""Task submission and check evaluation handler for SabiLab."""

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from db import get_connection
from app.loader import load_scenario
from app.twist import log_event
from checks import report_checks


def save_task(session_id: str, text: str, user_id: Optional[str] = None, current_time: Optional[datetime] = None) -> Dict[str, Any]:
    """Store the student's task submission, update session state, and evaluate check figures."""
    conn = get_connection()
    now = current_time or datetime.now(timezone.utc)
    try:
        sess = conn.execute("SELECT user_id, scenario_id FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not sess:
            raise ValueError(f"Session '{session_id}' not found.")

        uid = user_id or sess["user_id"]
        cursor = conn.execute(
            "INSERT INTO tasks (session_id, user_id, text, submitted_time) VALUES (?, ?, ?, ?)",
            (session_id, uid, text, now.isoformat()),
        )
        task_id = cursor.lastrowid
        conn.execute("UPDATE sessions SET status = 'task_submitted' WHERE id = ?", (session_id,))
        conn.commit()
    finally:
        conn.close()

    log_event(session_id, "submit", json.dumps({"task_id": task_id, "length": len(text)}), now)
    scenario = load_scenario(sess["scenario_id"])
    check_results = report_checks(text, scenario["checks"])

    return {
        "task_id": task_id,
        "session_id": session_id,
        "user_id": uid,
        "text": text,
        "submitted_time": now.isoformat(),
        "checks": check_results,
    }
