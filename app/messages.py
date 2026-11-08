"""Message dispatching and scripted teammate replies for SabiLab."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from db import get_connection
from app.loader import load_scenario
from app.twist import check_and_fire_twist, is_twist_fired


def post_message(session_id: str, sender: str, text: str, current_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Save user message, check twist, and generate scripted teammate replies."""
    now = current_time or datetime.now(timezone.utc)
    new_messages = []

    twist_msg = check_and_fire_twist(session_id, now)
    if twist_msg:
        new_messages.append(twist_msg)

    conn = get_connection()
    try:
        sess = conn.execute("SELECT scenario_id FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not sess:
            raise ValueError(f"Session '{session_id}' not found.")
        scenario = load_scenario(sess["scenario_id"])
        participants = conn.execute("SELECT display_name FROM participants WHERE session_id = ? AND kind = 'ai'", (session_id,)).fetchall()
        max_seq = conn.execute("SELECT COALESCE(MAX(sequence_number), 0) FROM messages WHERE session_id = ?", (session_id,)).fetchone()[0]

        student_msg_id = uuid.uuid4().hex[:12]
        max_seq += 1
        conn.execute(
            "INSERT INTO messages (id, session_id, sequence_number, sender, text, sent_time, phase) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (student_msg_id, session_id, max_seq, sender, text, now.isoformat(), "huddle"),
        )
        new_messages.append({"id": student_msg_id, "sender": sender, "text": text, "sequence_number": max_seq})

        twist_active = is_twist_fired(session_id)
        reply_key = "reply_after_twist" if twist_active else "reply_before_twist"
        roster_map = {t["name"]: t for t in scenario["roster"]}

        for p in participants:
            tm_name = p["display_name"]
            if tm_name in roster_map:
                reply_text = roster_map[tm_name][reply_key]
                tm_msg_id = uuid.uuid4().hex[:12]
                max_seq += 1
                conn.execute(
                    "INSERT INTO messages (id, session_id, sequence_number, sender, text, sent_time, phase) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (tm_msg_id, session_id, max_seq, tm_name, reply_text, now.isoformat(), "huddle"),
                )
                new_messages.append({"id": tm_msg_id, "sender": tm_name, "text": reply_text, "sequence_number": max_seq})
        conn.commit()
    finally:
        conn.close()

    return new_messages


def get_messages(session_id: str, current_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Retrieve all messages for a session, checking for twist trigger."""
    check_and_fire_twist(session_id, current_time)
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, sequence_number, sender, text, sent_time, phase FROM messages WHERE session_id = ? ORDER BY sequence_number ASC",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
