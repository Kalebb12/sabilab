"""Evidence Card publishing, revocation, and public retrieval."""

import json
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from db import get_connection
from app.results import get_session_results


def publish_card(session_id: str, visible_fields: Optional[List[str]] = None) -> Dict[str, Any]:
    """Publish an unguessable public Evidence Card for a session."""
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    slug = secrets.token_urlsafe(16)
    fields = visible_fields or ["badges", "levels", "quotes", "verification_tier", "recommendations"]

    try:
        sess = conn.execute("SELECT user_id FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not sess:
            raise ValueError(f"Session '{session_id}' not found.")
        user_id = sess["user_id"]
        conn.execute(
            "INSERT INTO cards (slug, user_id, session_id, visible_fields, published_time) VALUES (?, ?, ?, ?, ?)",
            (slug, user_id, session_id, json.dumps(fields), now),
        )
        conn.commit()
    finally:
        conn.close()

    return {"slug": slug, "card_url": f"/card/{slug}", "published_time": now}


def revoke_card(slug: str) -> bool:
    """Revoke an existing Evidence Card so it is no longer publicly viewable."""
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    try:
        cursor = conn.execute(
            "UPDATE cards SET revoked_time = ? WHERE slug = ? AND revoked_time IS NULL",
            (now, slug),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def get_card_payload(slug: str) -> Optional[Dict[str, Any]]:
    """Retrieve verified card details if the card exists and has not been revoked."""
    conn = get_connection()
    try:
        card = conn.execute(
            "SELECT slug, user_id, session_id, visible_fields, published_time, revoked_time FROM cards WHERE slug = ?",
            (slug,),
        ).fetchone()
        if not card or card["revoked_time"]:
            return None
        user = conn.execute("SELECT first_name FROM users WHERE id = ?", (card["user_id"],)).fetchone()
    finally:
        conn.close()

    student_name = user["first_name"] if user else "Student"
    results = get_session_results(card["session_id"])

    return {
        "slug": card["slug"],
        "student_name": student_name,
        "badge": results.get("badge"),
        "scores": results.get("scores", []),
        "recommendation": results.get("recommendation", {}),
        "routing": results.get("routing", "AI-assessed"),
        "published_time": card["published_time"],
        "comparison": results.get("comparison"),
    }
