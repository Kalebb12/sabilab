"""Scoring pass execution, verification retry, and database saving."""

import json
import logging
import time
from typing import Any, Dict, List
import config
from db import get_connection
from app.pipeline.llm import call_gemini_json
from app.pipeline.prompts import SCORING_SYSTEM_PROMPT
from app.pipeline.telemetry import run_stage
from app.pipeline.verification import verify_scoring_output

logger = logging.getLogger("sabilab.pipeline.scoring")


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
    t_llm = time.time()
    logger.info(f"[{session_id}] [llm_scoring] start")
    try:
        result = call_gemini_json(SCORING_SYSTEM_PROMPT, prompt, session_id=session_id, call_type="scoring")
        logger.info(f"[{session_id}] [llm_scoring] done in {time.time() - t_llm:.2f}s")
    except Exception:
        logger.exception(f"[{session_id}] [llm_scoring] call failed after {time.time() - t_llm:.2f}s")
        raise

    is_valid, errors = run_stage(
        session_id,
        "verification",
        lambda: verify_scoring_output(result, student_messages_map),
    )

    if not is_valid:
        t_r = time.time()
        logger.info(f"[{session_id}] [scoring_retry] start")
        retry_prompt = prompt + f"\nPrevious output failed verification with errors: {errors}. You must use exact quotes from the student. Try again."
        try:
            result = call_gemini_json(SCORING_SYSTEM_PROMPT, retry_prompt, session_id=session_id, call_type="scoring_retry")
            logger.info(f"[{session_id}] [scoring_retry] done in {time.time() - t_r:.2f}s")
            is_valid, errors = run_stage(
                session_id,
                "verification",
                lambda: verify_scoring_output(result, student_messages_map),
            )
        except Exception:
            logger.exception(f"[{session_id}] [scoring_retry] failed after {time.time() - t_r:.2f}s")
            raise

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
                fb.get("strength", {}).get("note", "Good attempt"),
                fb.get("improvement", "Continue practicing role-specific trade-offs"),
                fb.get("rewrite", "I recommend an immediate payment of ₦150k to Kano Textiles."),
                routing,
            ),
        )
        conn.execute("UPDATE sessions SET status = 'completed' WHERE id = ?", (session_id,))
        conn.commit()
    except Exception:
        logger.exception(f"[{session_id}] Database error saving scores/results")
        raise
    finally:
        conn.close()

    return {
        "scores": result.get("scores", []),
        "feedback": result.get("feedback", {}),
        "flags": result.get("flags", {}),
        "routing": routing,
        "verification_passed": is_valid,
        "verification_errors": errors,
    }
