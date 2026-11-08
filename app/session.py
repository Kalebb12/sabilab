"""Session creation and lifecycle management for SabiLab."""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from db import get_connection
from app.loader import load_scenario
from app.twist import log_event
from app.messages import post_message, get_messages


def _get_attempt_number(conn, user_id: str, scenario_id: str) -> tuple[int, str]:
    """Return (attempt_number, variant) for a new session based on prior completed attempts."""
    prior = conn.execute(
        """SELECT s.id FROM sessions s
           WHERE s.user_id = ? AND s.scenario_id = ? AND (
               s.status IN ('completed', 'scored') OR
               EXISTS (SELECT 1 FROM results r WHERE r.session_id = s.id)
           ) ORDER BY s.start_time""",
        (user_id, scenario_id),
    ).fetchall()
    count = len(prior)
    if count == 0:
        return 1, "A"
    elif count == 1:
        return 2, "B"
    return count + 1, "B"


def create_session(data: Dict[str, Any], current_time: Optional[datetime] = None) -> Dict[str, Any]:
    """Start a new session after validating consent and saving chosen teammates."""
    if not data.get("consent"):
        raise ValueError("Consent is required to start a session.")

    scenario = load_scenario(data.get("scenario_id", "adaeze"))
    now = current_time or datetime.now(timezone.utc)
    user_id = data.get("user_id") or uuid.uuid4().hex[:12]
    session_id = uuid.uuid4().hex[:12]
    first_name = data.get("first_name", "Student")
    mode = data.get("mode", "demo")

    conn = get_connection()
    try:
        exists = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO users (id, first_name, consent_version, consent_time) VALUES (?, ?, ?, ?)",
                (user_id, first_name, "v0.1", now.isoformat()),
            )
        attempt_number, variant = _get_attempt_number(conn, user_id, scenario["id"])
        if attempt_number > 2:
            raise ValueError("Maximum of 2 attempts allowed per scenario.")
        conn.execute(
            "INSERT INTO sessions (id, user_id, scenario_id, variant, attempt_number, mode, language, start_time, status)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, user_id, scenario["id"], variant, attempt_number, mode, "en", now.isoformat(), "huddle"),
        )
        conn.execute(
            "INSERT INTO participants (session_id, seat, kind, persona, display_name) VALUES (?, ?, ?, ?, ?)",
            (session_id, 1, "student", scenario["student_role"], first_name),
        )
        teammate_ids = data.get("teammate_ids") or ["sales", "operations"]
        chosen = [t for t in scenario["roster"] if t["id"] in teammate_ids][:2]
        for seat_idx, tm in enumerate(chosen, start=2):
            conn.execute(
                "INSERT INTO participants (session_id, seat, kind, persona, display_name) VALUES (?, ?, ?, ?, ?)",
                (session_id, seat_idx, "ai", tm["role"], tm["name"]),
            )
        seq = 1
        owner_opening = scenario["owner"]["scripted_lines"]["opening"]
        conn.execute(
            "INSERT INTO messages (id, session_id, sequence_number, sender, text, sent_time, phase) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (uuid.uuid4().hex[:12], session_id, seq, scenario["owner"]["name"], owner_opening, now.isoformat(), "huddle"),
        )
        for tm in chosen:
            seq += 1
            conn.execute(
                "INSERT INTO messages (id, session_id, sequence_number, sender, text, sent_time, phase) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (uuid.uuid4().hex[:12], session_id, seq, tm["name"], tm["opening_line"], now.isoformat(), "huddle"),
            )
        conn.commit()
    finally:
        conn.close()

    log_event(session_id, "session_start", json.dumps({"mode": mode, "teammates": [t["id"] for t in chosen]}), now)
    brief = scenario.get("student_brief", "")
    if variant == "B":
        vb = scenario.get("variant_b", {}).get("facts", {})
        brief += "\n\n[Variant B facts] " + "; ".join(f"{k}: {v}" for k, v in vb.items())
    return {
        "session_id": session_id,
        "user_id": user_id,
        "attempt_number": attempt_number,
        "variant": variant,
        "student_role": scenario["student_role"],
        "private_brief": brief,
        "roster": chosen,
        "mode": mode,
        "start_time": now.isoformat(),
    }
