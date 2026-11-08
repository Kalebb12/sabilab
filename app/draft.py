"""Session draft backup persistence using events table."""

import json
from datetime import datetime, timezone
from typing import Optional
from db import get_connection


def save_draft_backup(session_id: str, text: str) -> None:
    """Store the latest in-progress draft text in the events log."""
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO events (session_id, type, time, details) VALUES (?, ?, ?, ?)",
            (session_id, "draft_autosave", now, json.dumps({"text": text})),
        )
        conn.commit()
    finally:
        conn.close()


def get_draft_backup(session_id: str) -> Optional[str]:
    """Retrieve the most recent autosaved draft text for a session."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT details FROM events WHERE session_id = ? AND type = 'draft_autosave' ORDER BY id DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        if not row:
            return None
        data = json.loads(row["details"] or "{}")
        return data.get("text")
    finally:
        conn.close()
