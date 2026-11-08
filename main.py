"""FastAPI server for SabiLab."""

from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import config
from db import init_db
from app.loader import list_scenarios
from app.session import create_session, post_message, get_messages
from app.task import save_task


class SessionCreateRequest(BaseModel):
    first_name: str = "Student"
    consent: bool = False
    scenario_id: str = "adaeze"
    teammate_ids: Optional[List[str]] = None
    mode: str = "demo"


class MessagePostRequest(BaseModel):
    sender: str
    text: str


class TaskSubmitRequest(BaseModel):
    session_id: str
    text: str
    user_id: Optional[str] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database tables on application startup."""
    init_db()
    yield


app = FastAPI(title="SabiLab API", lifespan=lifespan)

# Mount static files directory for client assets
app.mount("/static", StaticFiles(directory=str(config.STATIC_DIR)), name="static")


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
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/session/{session_id}/message")
def send_message(session_id: str, req: MessagePostRequest):
    """Post a message to the session huddle and receive scripted replies."""
    try:
        return post_message(session_id, req.sender, req.text)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/session/{session_id}/messages")
def list_messages(session_id: str):
    """Retrieve all messages for a session, checking for twist trigger."""
    return get_messages(session_id)


@app.post("/task")
def submit_task(req: TaskSubmitRequest):
    """Save the individual task deliverable and report factual check results."""
    try:
        return save_task(req.session_id, req.text, req.user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/health")
def health_check():
    """Return health status of the application."""
    return {"status": "ok"}
