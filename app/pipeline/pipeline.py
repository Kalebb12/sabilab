"""Orchestrator for the complete assessment pipeline."""

import logging
from typing import Any, Dict
from db import get_connection
from app.cost import get_cost_summary
from app.loader import load_scenario
from app.pipeline.prepare import prepare_transcript
from app.pipeline.reading import execute_reading_pass
from app.pipeline.gate import evaluate_gate, get_clarifications
from app.pipeline.scoring import execute_scoring_pass
from app.pipeline.telemetry import (
    get_pipeline_status,
    run_stage,
    set_pipeline_status,
    try_start_pipeline,
)
from checks import report_checks

logger = logging.getLogger("sabilab.pipeline")


def run_pipeline(session_id: str) -> Dict[str, Any]:
    """Execute the assessment pipeline: prepare, reading, clarification gate, and scoring."""
    if not try_start_pipeline(session_id):
        status = get_pipeline_status(session_id) or {"status": "running"}
        return {"session_id": session_id, **status}
    try:
        def prepare():
            conn = get_connection()
            try:
                sess = conn.execute(
                    "SELECT scenario_id, status FROM sessions WHERE id = ?",
                    (session_id,),
                ).fetchone()
                task_row = conn.execute(
                    "SELECT text FROM tasks WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
                if not sess:
                    raise ValueError(f"Session '{session_id}' not found.")
            finally:
                conn.close()
            scenario = load_scenario(sess["scenario_id"])
            transcript, student_messages_map = prepare_transcript(session_id)
            return sess, task_row, scenario, transcript, student_messages_map

        sess, task_row, scenario, transcript, student_messages_map = run_stage(
            session_id, "prepare", prepare
        )

        reading_result = run_stage(
            session_id,
            "reading",
            lambda: execute_reading_pass(session_id, transcript, scenario),
        )

        def gate():
            clarifications = get_clarifications(session_id)
            gate_questions = []
            if sess["status"] != "clarified" and not any(
                c.get("answer") for c in clarifications
            ):
                gate_questions = evaluate_gate(session_id, reading_result)
            return clarifications, gate_questions

        clarifications, gate_questions = run_stage(session_id, "gate", gate)
        if gate_questions:
            set_pipeline_status(session_id, "done")
            return {
                "status": "awaiting_clarification",
                "session_id": session_id,
                "clarification_requests": gate_questions,
                "reading": reading_result,
            }

        def scoring():
            task_text = task_row["text"] if task_row else ""
            checks = report_checks(task_text, scenario.get("checks", []))
            return execute_scoring_pass(
                session_id=session_id,
                transcript=transcript,
                student_messages_map=student_messages_map,
                readings=reading_result,
                clarifications=clarifications,
                scenario=scenario,
                checks=checks,
            )

        scoring_result = run_stage(session_id, "scoring", scoring)
        set_pipeline_status(session_id, "done")
        return {
            "status": "completed",
            "session_id": session_id,
            "scoring": scoring_result,
        }
    except Exception as exc:
        logger.exception("[%s] Pipeline execution failed", session_id)
        try:
            set_pipeline_status(
                session_id,
                "failed",
                error_message=str(exc) or type(exc).__name__,
            )
        except Exception:
            logger.exception("[%s] Failed to save pipeline failure status", session_id)
        raise
    finally:
        try:
            usage = get_cost_summary(session_id)
            logger.info(
                "[%s] LLM session usage calls=%d input_tokens=%d output_tokens=%d "
                "total_tokens=%d cost_usd=%.6f",
                session_id,
                usage["total_calls"],
                usage["total_input_tokens"],
                usage["total_output_tokens"],
                usage["total_input_tokens"] + usage["total_output_tokens"],
                usage["total_cost_usd"],
            )
        except Exception:
            logger.exception("[%s] Could not log session LLM usage", session_id)
