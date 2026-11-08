"""Prepare and anonymize session messages before LLM processing."""

import re
from typing import Any, Dict, List, Tuple
from db import get_connection


def strip_pii(text: str) -> str:
    """Remove phone numbers and email addresses from text."""
    # Strip emails
    cleaned = re.sub(r'[\w\.-]+@[\w\.-]+\.\w+', '[EMAIL_REDACTED]', text)
    # Strip phone numbers (Nigerian and international formats)
    cleaned = re.sub(r'(\+?\d{1,4}?[-.\s]?\(?\d{1,3}?\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4})', '[PHONE_REDACTED]', cleaned)
    return cleaned


def prepare_transcript(session_id: str) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """Format, number, and anonymize transcript messages for the reading and scoring passes."""
    conn = get_connection()
    try:
        student_part = conn.execute(
            "SELECT display_name, persona FROM participants WHERE session_id = ? AND kind = 'student'",
            (session_id,),
        ).fetchone()
        student_name = student_part["display_name"] if student_part else "Student"
        student_role = student_part["persona"] if student_part else "Student"

        rows = conn.execute(
            "SELECT id, sequence_number, sender, text, phase FROM messages WHERE session_id = ? ORDER BY sequence_number ASC",
            (session_id,),
        ).fetchall()

        task_row = conn.execute(
            "SELECT id, text FROM tasks WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    finally:
        conn.close()

    transcript = []
    student_messages_map = {}

    for r in rows:
        is_student = (r["sender"] == student_name or r["sender"] == "Student")
        display_sender = "Student" if is_student else r["sender"]
        sanitized_text = strip_pii(r["text"])
        msg_id = f"M{r['sequence_number']}"

        transcript.append({
            "message_id": msg_id,
            "raw_id": r["id"],
            "sender": display_sender,
            "role": student_role if is_student else "Teammate",
            "phase": r["phase"],
            "text": sanitized_text,
            "is_student": is_student,
        })
        if is_student:
            student_messages_map[msg_id] = r["text"]

    # Append student's task submission as final message if present
    if task_row:
        task_msg_id = f"M{len(transcript) + 1}"
        transcript.append({
            "message_id": task_msg_id,
            "raw_id": f"task_{task_row['id']}",
            "sender": "Student",
            "role": student_role,
            "phase": "task",
            "text": strip_pii(task_row["text"]),
            "is_student": True,
        })
        student_messages_map[task_msg_id] = task_row["text"]

    return transcript, student_messages_map
