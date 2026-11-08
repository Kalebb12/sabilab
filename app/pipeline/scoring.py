"""Scoring pass execution, verification retry, and database saving."""

import json
from typing import Any, Dict, List
import config
from db import get_connection
from app.pipeline.llm import call_gemini_json
from app.pipeline.prompts import SCORING_SYSTEM_PROMPT
from app.pipeline.verification import verify_scoring_output


def build_scoring_prompt(transcript: List[Dict[str, Any]], readings: Dict[str, Any], clarifications: List[Dict[str, Any]], scenario: Dict[str, Any], checks: List[Dict[str, Any]]) -> str:
    """Build the scoring pass prompt with transcript, facts, checks, and readings."""
    transcript_text = "\n".join(
        f"[{m['message_id']}] ({m['role']}) {m['sender']}: {m['text']}"
        for m in transcript
    )
    return f"""<student>Student</student>
<checks>{json.dumps(checks, indent=2)}</checks>
<scenario_facts>{json.dumps([f"{f['key']}: {f['value']}" for f in scenario.get('facts', [])], indent=2)}</scenario_facts>
<readings>{json.dumps(readings.get('readings', []), indent=2)}</readings>
<clarifications>{json.dumps(clarifications, indent=2)}</clarifications>
<transcript>
{transcript_text}
</transcript>

Score each criterion using only the rubric and student evidence. Return JSON matching schema."""


def execute_scoring_pass(session_id: str, transcript: List[Dict[str, Any]], student_messages_map: Dict[str, str], readings: Dict[str, Any], clarifications: List[Dict[str, Any]], scenario: Dict[str, Any], checks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Run scoring pass, retry once if verification fails, and save scores to database."""
    prompt = build_scoring_prompt(transcript, readings, clarifications, scenario, checks)
    result = call_gemini_json(SCORING_SYSTEM_PROMPT, prompt, session_id=session_id, call_type="scoring")

    # Verification and retry once if verification fails
    is_valid, errors = verify_scoring_output(result, student_messages_map)
    if not is_valid:
        retry_prompt = prompt + f"\nPrevious output failed verification with errors: {errors}. You must use exact quotes from the student. Try again."
        result = call_gemini_json(SCORING_SYSTEM_PROMPT, retry_prompt, session_id=session_id, call_type="scoring_retry")
        is_valid, errors = verify_scoring_output(result, student_messages_map)

    # Determine routing
    routing = "AI-assessed"
    if not is_valid or readings.get("possible_injection") or readings.get("severe_tone") or result.get("flags", {}).get("needs_human_review"):
        routing = "needs_review"

    # Persist scores in database
    conn = get_connection()
    try:
        model_version = f"{config.GEMINI_MODEL}:{config.PROMPT_VERSION_SCORING}"
        for s in result.get("scores", []):
            conn.execute(
                "INSERT INTO scores (session_id, dimension, criterion, level, confidence, evidence, counter_evidence, reason, rubric_version, model_and_version, prompt_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    s.get("dimension", "General"),
                    s.get("criterion", "Unknown"),
                    s.get("level", "insufficient_evidence"),
                    s.get("confidence", "low"),
                    s.get("evidence", ""),
                    s.get("counter_evidence") or "",
                    s.get("reason", ""),
                    config.RUBRIC_VERSION,
                    model_version,
                    config.PROMPT_VERSION_SCORING,
                ),
            )
        # Persist summary results
        fb = result.get("feedback", {})
        levels_map = {s.get("criterion"): s.get("level") for s in result.get("scores", [])}
        conn.execute(
            "INSERT INTO results (session_id, levels, did_well, improve, recommendation, routing) VALUES (?, ?, ?, ?, ?, ?)",
            (
                session_id,
                json.dumps(levels_map),
                fb.get("strength", {}).get("note", "Good work on factual communication."),
                fb.get("improvement", "Work on trade-off reasoning."),
                fb.get("rewrite", "Practice structuring recommendations clearly."),
                routing,
            ),
        )
        conn.execute("UPDATE sessions SET status = 'completed' WHERE id = ?", (session_id,))
        conn.commit()
    finally:
        conn.close()

    result["routing"] = routing
    result["verification_passed"] = is_valid
    return result
