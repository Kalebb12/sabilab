"""Pipeline stage timing and exception logging."""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, TypeVar

from db import get_connection

T = TypeVar("T")
logger = logging.getLogger("sabilab.pipeline")


def set_pipeline_status(
    session_id: str,
    status: str,
    stage: Optional[str] = None,
    error_message: Optional[str] = None,
) -> None:
    """Persist the latest pipeline state, preserving its stage when omitted."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO pipeline_status
               (session_id, status, current_stage, error_message, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(session_id) DO UPDATE SET
                 status = excluded.status,
                 current_stage = COALESCE(excluded.current_stage, pipeline_status.current_stage),
                 error_message = excluded.error_message,
                 updated_at = excluded.updated_at""",
            (
                session_id,
                status,
                stage,
                error_message,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
    except Exception:
        logger.exception("[%s] Could not persist pipeline status", session_id)
        raise
    finally:
        conn.close()


def get_pipeline_status(session_id: str) -> Optional[Dict[str, Any]]:
    """Return the persisted status for a pipeline run, or None before it starts."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT status, current_stage, error_message FROM pipeline_status WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return dict(row) if row else None
    except Exception:
        logger.exception("[%s] Could not read pipeline status", session_id)
        raise
    finally:
        conn.close()


def try_start_pipeline(session_id: str) -> bool:
    """Atomically mark a session running unless another pipeline owns it."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO pipeline_status
               (session_id, status, current_stage, error_message, updated_at)
               VALUES (?, 'running', 'prepare', NULL, ?)
               ON CONFLICT(session_id) DO UPDATE SET
                 status = 'running', current_stage = 'prepare',
                 error_message = NULL, updated_at = excluded.updated_at
               WHERE pipeline_status.status != 'running'""",
            (session_id, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return cursor.rowcount == 1
    finally:
        conn.close()


def run_stage(session_id: str, stage: str, operation: Callable[[], T]) -> T:
    """Run one pipeline stage while logging its duration and any traceback."""
    started = time.monotonic()
    logger.info("[%s] [%s] start", session_id, stage)
    outcome = "done"
    try:
        set_pipeline_status(session_id, "running", stage)
        return operation()
    except Exception as exc:
        outcome = "failed"
        logger.exception("[%s] [%s] failed", session_id, stage)
        try:
            set_pipeline_status(
                session_id,
                "failed",
                stage,
                str(exc) or type(exc).__name__,
            )
        except Exception:
            logger.exception("[%s] Failed to save pipeline failure status", session_id)
        raise
    finally:
        logger.info(
            "[%s] [%s] %s in %.2fs",
            session_id,
            stage,
            outcome,
            time.monotonic() - started,
        )
