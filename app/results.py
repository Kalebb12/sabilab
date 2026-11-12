"""Results compilation, weakest area recommendation, and badge evaluation."""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from db import get_connection
from app.rubric import get_rubric, normalize_level, get_level_display

LEVEL_ORDER = {}
for _level_key, _level_data in get_rubric().get("levels", {}).items():
    LEVEL_ORDER[_level_key] = _level_data.get("order", 0)
    LEVEL_ORDER[_level_data.get("display", _level_key)] = _level_data.get("order", 0)

RECOMMENDATIONS = {
    "Communication": {
        "area": "Communication & Clarity",
        "drill": "3-minute clarity drill: write a request with who, what, and by when in under 30 words.",
        "guide": "The 3W Framework: Who, What, When.",
        "habit": "Before sending, check that your message names the person responsible and the exact deadline.",
        "simulation": "Communication Solo Simulation",
    },
    "Leadership": {
        "area": "Decisive Delegation & Ownership",
        "drill": "Ownership drill: state the decision, the trade-off, and assign one clear owner with a deadline.",
        "guide": "Single-Owner Framework: Every task has exactly one owner and a deadline.",
        "habit": "Never end a huddle message without assigning an owner and a deadline.",
        "simulation": "Leadership Solo Simulation",
    },
    "Creative thinking": {
        "area": "Option Generation & Problem Framing",
        "drill": "Two-path drill: propose two distinct options with one trade-off before deciding.",
        "guide": "Diverge Before Deciding: Frame the problem before proposing solutions.",
        "habit": "Always generate at least two contrasting options with explicit trade-offs.",
        "simulation": "Creative Thinking Solo Simulation",
    },
    "Accounts": {
        "area": "Accounts & Cash Prioritisation",
        "drill": "Cash buffer drill: calculate remaining liquid cash before proposing supplier payments or customer discounts.",
        "guide": "Working Capital Rule: Never commit more than 70% of liquid cash in a single transaction.",
        "habit": "Always calculate and state the remaining cash balance alongside every proposed payment.",
        "simulation": "Accounts Solo Simulation",
    },
    "Role skill": {
        "area": "Accounts & Cash Prioritisation",
        "drill": "Cash buffer drill: calculate remaining liquid cash before proposing supplier payments or customer discounts.",
        "guide": "Working Capital Rule: Never commit more than 70% of liquid cash in a single transaction.",
        "habit": "Always calculate and state the remaining cash balance alongside every proposed payment.",
        "simulation": "Accounts Solo Simulation",
    },
}


def evaluate_badges(session_id: str, scores: List[Dict[str, Any]], routing: str) -> Optional[Dict[str, Any]]:
    """Award a badge if all dimensions meet Foundation or higher, capped at Proficient."""
    if not scores:
        return None
    dim_scores: Dict[str, List[str]] = {}
    for s in scores:
        lvl = s.get("level", "insufficient_evidence")
        canon = normalize_level(lvl)
        if not canon or canon == "insufficient_evidence":
            continue
        dim = s.get("dimension", "General")
        dim_scores.setdefault(dim, []).append(canon)
    if not dim_scores:
        return None
    for dim, levels in dim_scores.items():
        if min(LEVEL_ORDER.get(l, 0) for l in levels) < LEVEL_ORDER["foundation"]:
            return None
    scored = [normalize_level(s["level"]) for s in scores if normalize_level(s.get("level")) != "insufficient_evidence"]
    badge_level = "Proficient" if scored and min(LEVEL_ORDER.get(l, 0) for l in scored) >= LEVEL_ORDER["proficient"] else "Foundation"
    badge_tier = "AI-assessed" if routing == "AI-assessed" else "Pending review"

    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    try:
        sess = conn.execute("SELECT user_id FROM sessions WHERE id = ?", (session_id,)).fetchone()
        user_id = sess["user_id"] if sess else "unknown"
        badge_id = uuid.uuid4().hex[:12]
        badge_name = "Adaeze's Fabrics - SME Accounts & Communication"
        conn.execute(
            "INSERT INTO badges (id, user_id, session_id, name, level, tier, issued_time) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (badge_id, user_id, session_id, badge_name, badge_level, badge_tier, now),
        )
        conn.commit()
        return {"id": badge_id, "name": badge_name, "level": badge_level, "tier": badge_tier, "issued_time": now}
    finally:
        conn.close()


def get_recommendation_for_weakest(scores: List[Dict[str, Any]]) -> Dict[str, str]:
    """Identify the weakest scored area and return corresponding drill, guide, and habit."""
    if not scores:
        return RECOMMENDATIONS["Communication"]
    lowest = min(scores, key=lambda s: LEVEL_ORDER.get(s.get("level"), 0))
    dim = lowest.get("dimension", "Communication")
    return RECOMMENDATIONS.get(dim, RECOMMENDATIONS["Communication"])


def get_session_results(session_id: str) -> Dict[str, Any]:
    """Compile scored criteria with quotes, did well, improve, recommendations, and badges."""
    from app.comparison import get_comparison
    conn = get_connection()
    try:
        sess = conn.execute("SELECT user_id, scenario_id FROM sessions WHERE id = ?", (session_id,)).fetchone()
        user_row = conn.execute("SELECT first_name FROM users WHERE id = ?", (sess["user_id"],)).fetchone() if sess else None
        scores = conn.execute(
            "SELECT dimension, criterion, level, confidence, evidence, counter_evidence, reason FROM scores WHERE session_id = ?",
            (session_id,),
        ).fetchall()
        result_row = conn.execute("SELECT levels, did_well, improve, routing FROM results WHERE session_id = ?", (session_id,)).fetchone()
        badge_row = conn.execute("SELECT id, name, level, tier, issued_time FROM badges WHERE session_id = ?", (session_id,)).fetchone()
    finally:
        conn.close()

    raw_name = (user_row["first_name"] if user_row else "").strip()
    student_name = raw_name if raw_name and raw_name.lower() != "student" else "SabiLab learner"
    score_list = []
    for s in scores:
        item = dict(s)
        if not item.get("evidence") or normalize_level(item.get("level")) == "insufficient_evidence":
            item["level"] = "insufficient_evidence"
            item["evidence"] = ""
        score_list.append(item)

    rec = get_recommendation_for_weakest(score_list)
    badge = dict(badge_row) if badge_row else None
    if not badge and score_list and result_row:
        badge = evaluate_badges(session_id, score_list, result_row["routing"])
    comp = get_comparison(sess["user_id"], sess["scenario_id"]) if sess else None

    return {
        "session_id": session_id,
        "student_name": student_name,
        "first_name": student_name,
        "scores": score_list,
        "did_well": result_row["did_well"] if result_row else "",
        "improve": result_row["improve"] if result_row else "",
        "routing": result_row["routing"] if result_row else "AI-assessed",
        "recommendation": rec,
        "badge": badge,
        "comparison": comp,
    }
