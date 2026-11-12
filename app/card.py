"""Evidence Card publishing, revocation, and public retrieval."""

import json
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from db import get_connection
from app.results import get_session_results
from app.loader import load_scenario

CARD_VISIBLE_FIELDS = {
    "name",
    "scores",
    "quotes",
    "verification_tier",
    "growth_drill",
    "badges",
}
CARD_FIELD_ALIASES = {
    "levels": "scores",
    "recommendations": "growth_drill",
}
DEFAULT_CARD_FIELDS = [
    "name",
    "scores",
    "quotes",
    "verification_tier",
    "growth_drill",
    "badges",
]


def normalize_visible_fields(fields: Optional[List[str]]) -> List[str]:
    """Validate and normalize public card fields while accepting legacy names."""
    if fields is None:
        return list(DEFAULT_CARD_FIELDS)
    if not isinstance(fields, list):
        raise ValueError("visible_fields must be a list of supported field names.")

    normalized = []
    for field in fields:
        if not isinstance(field, str):
            raise ValueError("visible_fields entries must be strings.")
        name = CARD_FIELD_ALIASES.get(field, field)
        if name not in CARD_VISIBLE_FIELDS:
            raise ValueError(f"Unsupported card field: {field}")
        if name not in normalized:
            normalized.append(name)
    return normalized


def publish_card(
    session_id: str,
    visible_fields: Optional[List[str]] = None,
    tier: Optional[str] = None,
) -> Dict[str, Any]:
    """Publish an unguessable public Evidence Card for a session."""
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    slug = secrets.token_urlsafe(16)
    fields = normalize_visible_fields(visible_fields)

    try:
        sess = conn.execute(
            """SELECT s.user_id, r.routing
               FROM sessions s LEFT JOIN results r ON s.id = r.session_id
               WHERE s.id = ?""",
            (session_id,),
        ).fetchone()
        if not sess:
            raise ValueError(f"Session '{session_id}' not found.")
        if tier not in (None, "ai_assessed", "human_verified"):
            raise ValueError("tier must be 'ai_assessed' or 'human_verified'.")
        if tier == "human_verified" and sess["routing"] != "Human-verified":
            raise ValueError("A card can only be marked human-verified after reviewer confirmation.")
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
        sess = conn.execute("SELECT scenario_id FROM sessions WHERE id = ?", (card["session_id"],)).fetchone()
        rev_event = conn.execute(
            "SELECT time, details FROM events WHERE session_id = ? AND type = 'human_review' ORDER BY id DESC LIMIT 1",
            (card["session_id"],),
        ).fetchone()
    finally:
        conn.close()

    scenario_id = sess["scenario_id"] if sess else "adaeze"
    try:
        scen = load_scenario(scenario_id)
        role = scen.get("student_role", "Accountant")
        title = scen.get("title", "Adaeze's Fabrics")
    except Exception:
        role = "Accountant"
        title = "Adaeze's Fabrics"

    raw_name = (user["first_name"] if user else "").strip()
    student_name = raw_name if raw_name and raw_name.lower() != "student" else "SabiLab learner"
    results = get_session_results(card["session_id"])
    visible_fields = normalize_visible_fields(
        json.loads(card["visible_fields"]) if card.get("visible_fields") else None
    )

    reviewer_info = None
    if rev_event:
        d = json.loads(rev_event["details"] or "{}")
        reviewer_info = {"reviewer": d.get("reviewer", "SabiLab Reviewer"), "time": rev_event["time"]}

    return {
        "slug": card["slug"],
        "student_name": student_name if "name" in visible_fields else "SabiLab learner",
        "scenario_title": title,
        "student_role": role,
        "badge": results.get("badge") if "badges" in visible_fields else None,
        "scores": results.get("scores", []) if "scores" in visible_fields else [],
        "recommendation": results.get("recommendation", {}) if "growth_drill" in visible_fields else {},
        "routing": results.get("routing", "AI-assessed"),
        "published_time": card["published_time"],
        "reviewer_info": reviewer_info,
        "visible_fields": visible_fields,
        "comparison": results.get("comparison") if "scores" in visible_fields else None,
    }
