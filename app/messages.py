"""Message dispatching and scripted teammate replies for SabiLab."""

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import config
from db import get_connection
from app.loader import load_scenario, render_scenario_text
from app.persona import generate_owner_reply
from app.twist import check_and_fire_twist, is_twist_fired

_KEYWORD_GROUPS = (
    (
        "stock",
        re.compile(r"\b(stock|inventory|warehouse|rolls?)\b", re.IGNORECASE),
    ),
    (
        "price_discount",
        re.compile(r"\b(price|discount|off|cost|rate)\b", re.IGNORECASE),
    ),
    (
        "delivery_dispatch",
        re.compile(r"\b(deliver(?:y)?|dispatch|12:30|2\s*pm)\b", re.IGNORECASE),
    ),
    (
        "cash_payment_default",
        re.compile(r"\b(cash|pay(?:ment)?|invoice|supplier|kano)\b|₦", re.IGNORECASE),
    ),
)
_QUESTION_START = re.compile(
    r"^(what|when|who|where|why|how|can|could|would|is|are|do|does|did|will|should|any|which)\b",
    re.IGNORECASE,
)


def _keyword_group(text: str) -> Optional[str]:
    for group, pattern in _KEYWORD_GROUPS:
        if pattern.search(text):
            return group
    return None


def _is_direct_question(text: str) -> bool:
    return "?" in text or bool(_QUESTION_START.search(text.strip()))


def _matching_teammates(
    text: str,
    participants: List[Dict[str, str]],
    roster: Dict[str, Dict[str, str]],
) -> List[str]:
    explicit = []
    for participant in participants:
        name = participant["display_name"]
        teammate = roster.get(name)
        if not teammate:
            continue
        terms = (name, teammate["role"])
        if any(re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text, re.IGNORECASE) for term in terms):
            explicit.append(name)
    if explicit:
        return explicit
    if not _is_direct_question(text):
        return []
    group = _keyword_group(text)
    if group is None:
        return []
    if group in {"stock", "delivery_dispatch"}:
        primary_name = "Ngozi"
    else:
        primary_name = "Emeka"
    return [primary_name] if primary_name in roster else []


def _reply_group(
    text: str,
    teammate_name: str,
    roster: Dict[str, Dict[str, str]],
) -> Optional[str]:
    mentions = []
    for name, teammate in roster.items():
        for term in (name, teammate["role"]):
            pattern = re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.IGNORECASE)
            mentions.extend((match.start(), match.end(), name) for match in pattern.finditer(text))
    mentions.sort()
    mention = next((item for item in mentions if item[2] == teammate_name), None)
    if mention is None:
        return _keyword_group(text)
    following = next((item[0] for item in mentions if item[0] > mention[0]), len(text))
    group = _keyword_group(text[mention[1]:following])
    return group if group is not None else _keyword_group(text)


def _save_huddle_reply(
    session_id: str,
    sender: str,
    text: str,
    now: datetime,
) -> Dict[str, Any]:
    conn = get_connection()
    try:
        max_seq = conn.execute(
            "SELECT COALESCE(MAX(sequence_number), 0) AS max_sequence "
            "FROM messages WHERE session_id = ?",
            (session_id,),
        ).fetchone()["max_sequence"]
        message_id = uuid.uuid4().hex[:12]
        sequence = max_seq + 1
        conn.execute(
            "INSERT INTO messages (id, session_id, sequence_number, sender, text, sent_time, phase) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (message_id, session_id, sequence, sender, text, now.isoformat(), "huddle"),
        )
        conn.commit()
        return {
            "id": message_id,
            "sender": sender,
            "text": text,
            "sequence_number": sequence,
        }
    finally:
        conn.close()


def post_message(
    session_id: str,
    sender: str,
    text: str,
    current_time: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Save a student message, then return an owner reaction and relevant team replies."""
    if len(text.strip()) == 0:
        raise ValueError("Message cannot be empty.")
    if len(text) > config.MESSAGE_MAX_CHARS:
        raise ValueError(f"Message exceeds maximum length of {config.MESSAGE_MAX_CHARS} characters.")

    now = current_time or datetime.now(timezone.utc)
    new_messages = []
    twist_msg = check_and_fire_twist(session_id, now)
    if twist_msg:
        new_messages.append(twist_msg)

    conn = get_connection()
    try:
        sess = conn.execute(
            "SELECT scenario_id, variant FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if not sess:
            raise ValueError(f"Session '{session_id}' not found.")

        last_msg = conn.execute(
            "SELECT sent_time FROM messages WHERE session_id = ? AND sender = ? "
            "AND sequence_number > 3 ORDER BY sequence_number DESC LIMIT 1",
            (session_id, sender),
        ).fetchone()
        if last_msg:
            last_dt = datetime.fromisoformat(last_msg["sent_time"])
            if (now - last_dt).total_seconds() < config.MESSAGE_RATE_LIMIT_SECONDS:
                raise ValueError("Rate limit exceeded: please wait a moment before sending another message.")

        scenario = load_scenario(sess["scenario_id"])
        participants = conn.execute(
            "SELECT display_name FROM participants WHERE session_id = ? AND kind = 'ai'",
            (session_id,),
        ).fetchall()
        student_msg_id = uuid.uuid4().hex[:12]
        max_seq = conn.execute(
            "SELECT COALESCE(MAX(sequence_number), 0) AS max_sequence "
            "FROM messages WHERE session_id = ?",
            (session_id,),
        ).fetchone()["max_sequence"]
        sequence = max_seq + 1
        conn.execute(
            "INSERT INTO messages (id, session_id, sequence_number, sender, text, sent_time, phase) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (student_msg_id, session_id, sequence, sender, text, now.isoformat(), "huddle"),
        )
        conn.commit()
    finally:
        conn.close()

    new_messages.append({
        "id": student_msg_id,
        "sender": sender,
        "text": text,
        "sequence_number": sequence,
    })

    twist_active = is_twist_fired(session_id)
    owner_reply = generate_owner_reply(session_id, sender, twist_active)
    new_messages.append(
        _save_huddle_reply(session_id, scenario["owner"]["name"], owner_reply, now)
    )

    roster_map = {teammate["name"]: teammate for teammate in scenario["roster"]}
    selected_teammates = _matching_teammates(text, participants, roster_map)
    bank = scenario.get("keyword_reply_bank", {})
    for teammate_name in selected_teammates:
        teammate_bank = bank.get(teammate_name)
        if not teammate_bank:
            continue

        conn = get_connection()
        try:
            total_messages = conn.execute(
                "SELECT COUNT(*) AS message_count FROM messages "
                "WHERE session_id = ? AND sender = ?",
                (session_id, teammate_name),
            ).fetchone()["message_count"]
        finally:
            conn.close()
        if total_messages - 1 >= 2:
            continue

        group = _reply_group(text, teammate_name, roster_map)
        reply_key = group if group in teammate_bank else "cash_payment_default"
        reply = render_scenario_text(teammate_bank[reply_key], scenario, sess["variant"])
        new_messages.append(_save_huddle_reply(session_id, teammate_name, reply, now))

    return new_messages


def get_messages(session_id: str, current_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Retrieve all messages for a session, checking for twist trigger."""
    check_and_fire_twist(session_id, current_time)
    conn = get_connection()
    try:
        twist_event = conn.execute(
            "SELECT time, details FROM events WHERE session_id = ? AND type = 'twist_fired' "
            "ORDER BY id DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        twist_details = json.loads(twist_event["details"] or "{}") if twist_event else {}
        twist_id = twist_details.get("message_id")
        rows = conn.execute(
            "SELECT id, sequence_number, sender, text, sent_time, phase "
            "FROM messages WHERE session_id = ? ORDER BY sequence_number ASC",
            (session_id,),
        ).fetchall()
        messages = [dict(row) for row in rows]
        for message in messages:
            is_twist = message["id"] == twist_id if twist_id else (
                twist_event is not None
                and message["sender"] == "Adaeze"
                and message["sent_time"] == twist_event["time"]
            )
            if is_twist:
                message["phase"] = "twist"
        return messages
    finally:
        conn.close()
