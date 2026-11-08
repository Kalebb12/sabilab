"""Results compilation, weakest area recommendation, and badge evaluation."""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from db import get_connection

LEVEL_ORDER = {"insufficient_evidence": 0, "Needs practice": 1, "Foundation": 2, "Proficient": 3}

RECOMMENDATIONS = {
    "Communication": {
        "area": "Communication & Clarity",
        "drill": "3-minute clarity drill: write a request with who, what, and by when in under 30 words.",
        "guide": "The 3W Framework: Who, What, When.",
        "habit": "Before sending, check that your message names the person responsible and the exact deadline.",
        "simulation": "Communication Solo Simulation",
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

    # Group scores by dimension — skip Insufficient evidence (no data, not a fail)
    dim_scores = {}
    for s in scores:
        lvl = s.get("level", "insufficient_evidence")
        if lvl in {"insufficient_evidence", "Insufficient evidence"}:
            continue
        dim = s.get("dimension", "General")
        dim_scores.setdefault(dim, []).append(lvl)

    # At least one scored dimension is required
    if not dim_scores:
        return None

    # Every scored dimension must achieve at least Foundation
    for dim, levels in dim_scores.items():
        min_level = min(LEVEL_ORDER.get(lvl, 0) for lvl in levels)
        if min_level < LEVEL_ORDER["Foundation"]:
            return None

    # Badge level is based only on scored criteria
    scored_levels = [s.get("level") for s in scores if s.get("level") not in {"insufficient_evidence", "Insufficient evidence"}]
    overall_min = min(LEVEL_ORDER.get(lvl, 0) for lvl in scored_levels) if scored_levels else 0
    badge_level = "Proficient" if overall_min >= LEVEL_ORDER["Proficient"] else "Foundation"
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
    """Identify the weakest scored area and return the corresponding drill, guide, and habit."""
    if not scores:
        return RECOMMENDATIONS["Communication"]

    lowest_score = min(scores, key=lambda s: LEVEL_ORDER.get(s.get("level"), 0))
    dim = lowest_score.get("dimension", "Communication")
    return RECOMMENDATIONS.get(dim, RECOMMENDATIONS["Communication"])


def get_session_results(session_id: str) -> Dict[str, Any]:
    """Compile scored criteria with quotes, did well, improve, recommendations, and badges."""
    conn = get_connection()
    try:
        scores = conn.execute(
            "SELECT dimension, criterion, level, confidence, evidence, counter_evidence, reason FROM scores WHERE session_id = ?",
            (session_id,),
        ).fetchall()
        result_row = conn.execute("SELECT levels, did_well, improve, routing FROM results WHERE session_id = ?", (session_id,)).fetchone()
        badge_row = conn.execute("SELECT id, name, level, tier, issued_time FROM badges WHERE session_id = ?", (session_id,)).fetchone()
    finally:
        conn.close()

    score_list = []
    for s in scores:
        item = dict(s)
        # Ensure Insufficient evidence is shown when there is no quote
        if not item.get("evidence"):
            item["level"] = "Insufficient evidence"
            item["evidence"] = "Insufficient evidence"
        score_list.append(item)

    recommendation = get_recommendation_for_weakest(score_list)
    badge_data = dict(badge_row) if badge_row else None

    # If badge not yet evaluated, evaluate now
    if not badge_data and score_list and result_row:
        badge_data = evaluate_badges(session_id, score_list, result_row["routing"])

    return {
        "session_id": session_id,
        "scores": score_list,
        "did_well": result_row["did_well"] if result_row else "",
        "improve": result_row["improve"] if result_row else "",
        "routing": result_row["routing"] if result_row else "AI-assessed",
        "recommendation": recommendation,
        "badge": badge_data,
    }
