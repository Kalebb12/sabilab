"""Twist trigger and event logging functions for SabiLab."""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import config
from db import get_connection
from app.loader import load_scenario


def log_event(session_id: str, event_type: str, details: Optional[str] = None, event_time: Optional[datetime] = None) -> None:
    """Record an audit or timing event in the events table."""
    conn = get_connection()
    t = (event_time or datetime.now(timezone.utc)).isoformat()
    try:
        conn.execute(
            "INSERT INTO events (session_id, type, time, details) VALUES (?, ?, ?, ?)",
            (session_id, event_type, t, details),
        )
        conn.commit()
    finally:
        conn.close()


def is_twist_fired(session_id: str) -> bool:
    """Check if the twist event has already fired for this session."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT 1 FROM events WHERE session_id = ? AND type = 'twist_fired'", (session_id,)).fetchone()
        return row is not None
    finally:
        conn.close()


def check_and_fire_twist(session_id: str, current_time: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """Fire twist message if elapsed time reaches halfway threshold and twist has not yet fired."""
    if is_twist_fired(session_id):
        return None

    conn = get_connection()
    try:
        sess = conn.execute("SELECT start_time, mode, scenario_id FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not sess:
            return None
        start_dt = datetime.fromisoformat(sess["start_time"])
        now = current_time or datetime.now(timezone.utc)
        elapsed = (now - start_dt).total_seconds()

        # Demo mode: 90s huddle with twist at 45s; Real mode: 900s with twist at 450s
        timing = config.TIMING_DEMO if sess["mode"] == "demo" else config.TIMING_REAL
        threshold = timing["huddle"] * timing["twist_ratio"]
        if elapsed < threshold:
            return None

        scenario = load_scenario(sess["scenario_id"])
        max_seq = conn.execute("SELECT COALESCE(MAX(sequence_number), 0) FROM messages WHERE session_id = ?", (session_id,)).fetchone()[0]
        twist_text = scenario["twist"]["text"]
        twist_id = uuid.uuid4().hex[:12]
        conn.execute(
            "INSERT INTO messages (id, session_id, sequence_number, sender, text, sent_time, phase) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (twist_id, session_id, max_seq + 1, scenario["owner"]["name"], twist_text, now.isoformat(), "huddle"),
        )
        conn.commit()
    finally:
        conn.close()

    log_event(session_id, "twist_fired", json.dumps({"elapsed_seconds": elapsed}), now)
    return {"id": twist_id, "sender": scenario["owner"]["name"], "text": twist_text, "sequence_number": max_seq + 1}
