"""Scoring pass execution, verification retry, and database saving."""

import json
import logging
import time
from typing import Any, Dict, List
import config
from db import get_connection
from app.pipeline.llm import call_llm_json
from app.pipeline.prompts import SCORING_SYSTEM_PROMPT
from app.pipeline.telemetry import run_stage
from app.pipeline.verification import (
    sanitize_unverified_scores,
    verify_scoring_output,
)
from app.rubric import (
    get_compact_rubric_prompt,
    get_criteria_map,
    get_criterion_ids,
    get_level_keys,
    normalize_level,
    get_level_display,
)

logger = logging.getLogger("sabilab.pipeline.scoring")


def build_scoring_prompt(transcript: List[Dict[str, Any]], readings: Dict[str, Any], clarifications: List[Dict[str, Any]], scenario: Dict[str, Any], checks: List[Dict[str, Any]], student_name: str = "Student") -> str:
    """Build the scoring pass prompt with compact rubric, facts, checks, and readings."""
    t_text = "\n".join(f"[{m['message_id']}] ({m['role']}) {m['sender']}: {m['text']}" for m in transcript)
    rubric_text = get_compact_rubric_prompt()
    facts = json.dumps([f"{f['key']}: {f['value']}" for f in scenario.get("facts", [])], indent=2)
    return f"""<student>{student_name}</student>
<rubric>\n{rubric_text}\n</rubric>
<checks>{json.dumps(checks, indent=2)}</checks>
<scenario_facts>{facts}</scenario_facts>
<readings>{json.dumps(readings.get('readings', []), indent=2)}</readings>
<clarifications>{json.dumps(clarifications, indent=2)}</clarifications>
<transcript>\n{t_text}\n</transcript>

Score each criterion using only the rubric and student evidence. Return JSON matching schema."""


def execute_scoring_pass(session_id: str, transcript: List[Dict[str, Any]], student_messages_map: Dict[str, str], readings: Dict[str, Any], clarifications: List[Dict[str, Any]], scenario: Dict[str, Any], checks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Run scoring pass, retry once if verification fails, and save scores to database."""
    conn = get_connection()
    try:
        user_row = conn.execute("SELECT u.first_name FROM sessions s JOIN users u ON s.user_id = u.id WHERE s.id = ?", (session_id,)).fetchone()
        raw_name = (user_row["first_name"] if user_row else "").strip()
        student_name = raw_name if raw_name and raw_name.lower() != "student" else "SabiLab learner"
    finally:
        conn.close()

    prompt = build_scoring_prompt(transcript, readings, clarifications, scenario, checks, student_name)
    t_llm = time.time()
    try:
        result = call_llm_json(SCORING_SYSTEM_PROMPT, prompt, session_id=session_id, call_type="scoring")
    except Exception:
        logger.exception(f"[{session_id}] [llm_scoring] failed after {time.time() - t_llm:.2f}s")
        raise

    is_valid, errors = run_stage(session_id, "verification", lambda: verify_scoring_output(result, student_messages_map))
    if not is_valid:
        logger.warning(f"[{session_id}] [verification_failed] {errors}")
        criteria = ", ".join(get_criterion_ids())
        levels = ", ".join(get_level_keys())
        retry_prompt = prompt + f"\nOutput failed verification: {errors}. Use only these rubric criteria: {criteria}. Valid levels: {levels}. Quotes must be exact substrings of student messages, at least 8 characters and 2 words. Try again."
        try:
            result = call_llm_json(SCORING_SYSTEM_PROMPT, retry_prompt, session_id=session_id, call_type="scoring_retry")
            is_valid, errors = run_stage(session_id, "verification", lambda: verify_scoring_output(result, student_messages_map))
        except Exception:
            logger.exception(f"[{session_id}] [scoring_retry] failed")
            raise

    if not is_valid:
        result = sanitize_unverified_scores(result, student_messages_map)

    routing = "AI-assessed"
    if not is_valid or readings.get("possible_injection") or readings.get("severe_tone") or result.get("flags", {}).get("needs_human_review"):
        routing = "needs_review"

    conn = get_connection()
    try:
        model_version = f"{config.LLM_MODEL_SCORING}:{config.PROMPT_VERSION_SCORING}"
        criteria_map = get_criteria_map()
        for s in result.get("scores", []):
            cid = s.get("criterion", "Unknown")
            dim = criteria_map.get(cid, {}).get("dimension", s.get("dimension", "General"))
            lvl = get_level_display(s.get("level", "insufficient_evidence"))
            conn.execute(
                "INSERT INTO scores (session_id, dimension, criterion, level, confidence, evidence, counter_evidence, reason, rubric_version, model_and_version, prompt_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (session_id, dim, cid, lvl, s.get("confidence", "low"), s.get("evidence", ""), s.get("counter_evidence") or "", s.get("reason", ""), config.RUBRIC_VERSION, model_version, config.PROMPT_VERSION_SCORING),
            )
        fb = result.get("feedback", {})
        levels_map = {s.get("criterion"): (normalize_level(s.get("level")) or s.get("level")) for s in result.get("scores", [])}
        conn.execute(
            "INSERT INTO results (session_id, levels, did_well, improve, recommendation, routing) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, json.dumps(levels_map), fb.get("strength", {}).get("note", "Good attempt"), fb.get("improvement", "Continue practicing role trade-offs"), fb.get("rewrite", "Pay Kano Textiles ₦150k today."), routing),
        )
        conn.execute("UPDATE sessions SET status = 'completed' WHERE id = ?", (session_id,))
        conn.commit()
    finally:
        conn.close()

    return {"scores": result.get("scores", []), "feedback": result.get("feedback", {}), "flags": result.get("flags", {}), "routing": routing, "verification_passed": is_valid, "verification_errors": errors}
