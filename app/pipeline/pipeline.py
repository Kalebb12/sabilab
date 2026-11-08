"""Orchestrator for the complete assessment pipeline."""

from typing import Any, Dict
from db import get_connection
from app.loader import load_scenario
from app.pipeline.prepare import prepare_transcript
from app.pipeline.reading import execute_reading_pass
from app.pipeline.gate import evaluate_gate, get_clarifications
from app.pipeline.scoring import execute_scoring_pass
from checks import report_checks


def run_pipeline(session_id: str) -> Dict[str, Any]:
    """Execute the assessment pipeline: prepare, reading, clarification gate, and scoring."""
    conn = get_connection()
    try:
        sess = conn.execute("SELECT scenario_id, status FROM sessions WHERE id = ?", (session_id,)).fetchone()
        task_row = conn.execute("SELECT text FROM tasks WHERE session_id = ?", (session_id,)).fetchone()
        if not sess:
            raise ValueError(f"Session '{session_id}' not found.")
    finally:
        conn.close()

    scenario = load_scenario(sess["scenario_id"])
    transcript, student_messages_map = prepare_transcript(session_id)

    # 1. Reading pass
    reading_result = execute_reading_pass(session_id, transcript, scenario)

    # 2. Clarification gate
    # If the session is already clarified, skip gate; otherwise evaluate gate
    clarifications = get_clarifications(session_id)
    if sess["status"] != "clarified" and not any(c.get("answer") for c in clarifications):
        gate_questions = evaluate_gate(session_id, reading_result)
        if gate_questions:
            return {
                "status": "awaiting_clarification",
                "session_id": session_id,
                "clarification_requests": gate_questions,
                "reading": reading_result,
            }

    # 3. Scoring pass
    task_text = task_row["text"] if task_row else ""
    checks = report_checks(task_text, scenario.get("checks", []))
    scoring_result = execute_scoring_pass(
        session_id=session_id,
        transcript=transcript,
        student_messages_map=student_messages_map,
        readings=reading_result,
        clarifications=clarifications,
        scenario=scenario,
        checks=checks,
    )

    return {
        "status": "completed",
        "session_id": session_id,
        "scoring": scoring_result,
    }
