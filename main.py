"""FastAPI server for SabiLab."""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import config
from db import init_db
from app.loader import list_scenarios
from app.session import create_session, post_message, get_messages
from app.task import save_task
from app.cost import get_cost_summary
from app.draft import save_draft_backup, get_draft_backup
from app.pipeline.pipeline import run_pipeline
from app.pipeline.telemetry import get_pipeline_status
from app.pipeline.gate import answer_clarification
from app.results import get_session_results
from app.review_routes import router as review_router
from app.card_routes import router as card_router
from app.schemas import (
    SessionCreateRequest,
    MessagePostRequest,
    TaskSubmitRequest,
    ClarificationAnswerRequest,
    DraftSaveRequest,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database tables on application startup."""
    init_db()
    yield


app = FastAPI(title="SabiLab API", lifespan=lifespan)
logger = logging.getLogger("sabilab.main")
app.mount("/static", StaticFiles(directory=str(config.STATIC_DIR)), name="static")
app.include_router(review_router)
app.include_router(card_router)


@app.get("/")
def serve_index():
    """Serve the single-page application interface if present."""
    index_file = config.STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "SabiLab API running", "scenarios": "/scenarios"}


@app.get("/scenarios")
def get_scenarios():
    """List all available scenarios from the scenarios directory."""
    return list_scenarios()


@app.post("/session", status_code=201)
def start_session(req: SessionCreateRequest):
    """Start a session after verifying consent, returning private brief and roster."""
    if not req.consent:
        raise HTTPException(status_code=400, detail="Consent is required to start a session.")
    try:
        return create_session(req.model_dump())
    except ValueError as e:
        logger.exception("Session creation failed")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/session/{session_id}/message")
def send_message(session_id: str, req: MessagePostRequest):
    """Post a message to the session huddle and receive scripted replies."""
    try:
        return post_message(session_id, req.sender, req.text)
    except ValueError as e:
        logger.exception("[%s] Message posting failed", session_id)
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        elif "rate limit" in msg.lower():
            raise HTTPException(status_code=429, detail=msg)
        raise HTTPException(status_code=400, detail=msg)


@app.get("/session/{session_id}/messages")
def list_messages(session_id: str):
    """Retrieve all messages for a session, checking for twist trigger."""
    return get_messages(session_id)


@app.post("/session/{session_id}/draft")
def record_draft(session_id: str, req: DraftSaveRequest):
    """Persist an in-progress draft backup for a session."""
    save_draft_backup(session_id, req.text)
    return {"status": "saved", "session_id": session_id}


@app.get("/session/{session_id}/draft")
def fetch_draft(session_id: str):
    """Retrieve the latest autosaved draft backup for a session."""
    return {"session_id": session_id, "draft": get_draft_backup(session_id)}


@app.post("/task")
def submit_task(req: TaskSubmitRequest):
    """Save the individual task deliverable and report factual check results."""
    try:
        return save_task(req.session_id, req.text, req.user_id)
    except ValueError as e:
        logger.exception("[%s] Task submission failed", req.session_id)
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/session/{session_id}/score")
def trigger_scoring(session_id: str):
    """Execute the full assessment pipeline (reading, clarification gate, scoring)."""
    try:
        return run_pipeline(session_id)
    except ValueError as e:
        logger.exception(f"[{session_id}] Session not found or invalid in scoring")
        status_code = 404 if "not found" in str(e).lower() else 500
        raise HTTPException(status_code=status_code, detail=str(e))
    except Exception as e:
        logger.exception(f"[{session_id}] Pipeline execution failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/session/{session_id}/pipeline-status")
def pipeline_status(session_id: str):
    """Return the current persisted status of a session's scoring pipeline."""
    status = get_pipeline_status(session_id)
    if status is None:
        raise HTTPException(status_code=404, detail="No pipeline run exists for this session.")
    return status


@app.post("/session/{session_id}/clarify")
def submit_clarification(session_id: str, req: ClarificationAnswerRequest):
    """Submit a clarification answer and resume the assessment pipeline."""
    try:
        answer_clarification(session_id, req.message_id, req.answer)
        return run_pipeline(session_id)
    except ValueError as e:
        logger.exception(f"[{session_id}] Session not found or invalid in clarification")
        status_code = 404 if "not found" in str(e).lower() else 500
        raise HTTPException(status_code=status_code, detail=str(e))
    except Exception as e:
        logger.exception(f"[{session_id}] Pipeline execution after clarification failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/session/{session_id}/results")
def fetch_results(session_id: str):
    """Retrieve verified session scores, feedback, and badges."""
    return get_session_results(session_id)


@app.get("/session/{session_id}/cost")
def session_cost(session_id: str):
    """Return token counts and cost summary for a session."""
    return get_cost_summary(session_id)


@app.get("/health")
def health_check():
    """Return health status."""
    return {"status": "ok"}
