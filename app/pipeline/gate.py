"""Clarification gate to request restatements for unclear or non-English messages."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List
from db import get_connection

logger = logging.getLogger("sabilab.pipeline.gate")


def evaluate_gate(session_id: str, reading_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Determine if clarification is required and persist up to 2 questions in database."""
    unclear_items = []

    # Check clarification requests directly from reading pass
    for req in reading_result.get("clarification_requests", []):
        if req.get("question") and req.get("message_id"):
            unclear_items.append(req)

    # Check readings for unclear clarity or non-English language
    for r in reading_result.get("readings", []):
        if len(unclear_items) >= 2:
            break
        mid = r.get("message_id")
        if any(item.get("message_id") == mid for item in unclear_items):
            continue
        if r.get("language") == "non_english":
            unclear_items.append({"message_id": mid, "question": "Please restate this message in English."})
        elif r.get("clarity") == "unclear":
            amb = r.get("ambiguity") or "your request"
            unclear_items.append({"message_id": mid, "question": f"Could you please clarify {amb}?"})

    questions_to_ask = unclear_items[:2]
    if not questions_to_ask:
        return []

    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    try:
        saved = []
        for q in questions_to_ask:
            cursor = conn.execute(
                "INSERT INTO clarifications (session_id, message_id, question, asked_time) VALUES (?, ?, ?, ?)",
                (session_id, q["message_id"], q["question"], now),
            )
            saved.append({"id": cursor.lastrowid, "message_id": q["message_id"], "question": q["question"]})
        conn.execute("UPDATE sessions SET status = 'awaiting_clarification' WHERE id = ?", (session_id,))
        conn.commit()
        return saved
    except Exception:
        logger.exception(f"[{session_id}] Error in evaluate_gate database operations")
        raise
    finally:
        conn.close()


def answer_clarification(session_id: str, message_id: str, answer: str) -> None:
    """Save the student's answer to a clarification question."""
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    try:
        conn.execute(
            "UPDATE clarifications SET answer = ?, answered_time = ? WHERE session_id = ? AND message_id = ?",
            (answer, now, session_id, message_id),
        )
        conn.execute("UPDATE sessions SET status = 'clarified' WHERE id = ?", (session_id,))
        conn.commit()
    except Exception:
        logger.exception(f"[{session_id}] Error answering clarification for message {message_id}")
        raise
    finally:
        conn.close()


def get_clarifications(session_id: str) -> List[Dict[str, Any]]:
    """Fetch all asked and answered clarifications for a session."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT message_id, question, answer, asked_time, answered_time FROM clarifications WHERE session_id = ?",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
