"""FastAPI server for SabiLab."""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import config
from db import init_db
from app.loader import list_scenarios
from app.session import create_session, post_message, get_messages
from app.task import save_task
from app.pipeline.pipeline import run_pipeline
from app.pipeline.gate import answer_clarification
from app.results import get_session_results
from app.card import publish_card, revoke_card, get_card_payload
from app.card_view import render_card_html
from app.review import render_review_html, list_review_rows, apply_review
from app.schemas import (
    SessionCreateRequest,
    MessagePostRequest,
    TaskSubmitRequest,
    ClarificationAnswerRequest,
    CardPublishRequest,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database tables on application startup."""
    init_db()
    yield


app = FastAPI(title="SabiLab API", lifespan=lifespan)
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


@app.post("/session/{session_id}/score")
def trigger_scoring(session_id: str):
    """Execute the full assessment pipeline (reading, clarification gate, scoring)."""
    try:
        return run_pipeline(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/session/{session_id}/clarify")
def submit_clarification(session_id: str, req: ClarificationAnswerRequest):
    """Submit a clarification answer and resume the assessment pipeline."""
    try:
        answer_clarification(session_id, req.message_id, req.answer)
        return run_pipeline(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/session/{session_id}/results")
def fetch_results(session_id: str):
    """Retrieve verified session scores, did well, improve, recommendations, and badges."""
    return get_session_results(session_id)


@app.post("/session/{session_id}/card")
def create_card(session_id: str, req: CardPublishRequest = CardPublishRequest()):
    """Publish an unguessable public Evidence Card."""
    try:
        return publish_card(session_id, req.visible_fields)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/card/{slug}", response_class=HTMLResponse)
def view_public_card(slug: str):
    """Serve the public mobile-first Evidence Card without requiring login."""
    payload = get_card_payload(slug)
    return HTMLResponse(content=render_card_html(payload))


@app.post("/card/{slug}/revoke")
def revoke_public_card(slug: str):
    """Revoke an active public Evidence Card."""
    if not revoke_card(slug):
        raise HTTPException(status_code=404, detail="Card not found or already revoked.")
    return {"status": "revoked", "slug": slug}


@app.get("/health")
def health_check():
    """Return health status of the application."""
    return {"status": "ok"}


# --- Reviewer dashboard (password-protected, server-side only) ---

@app.get("/review", response_class=HTMLResponse)
def review_page(request: Request, pw: str = ""):
    """Render reviewer dashboard; show results when password matches."""
    ok = bool(config.REVIEW_PASSWORD and pw == config.REVIEW_PASSWORD)
    rows = list_review_rows() if ok else []
    return HTMLResponse(render_review_html(ok, rows, pw=pw))


@app.post("/review/login")
def review_login(password: str = Form(...)):
    """Redirect back to review page with password as query param."""
    return RedirectResponse(url=f"/review?pw={password}", status_code=303)


@app.post("/review/confirm")
def review_confirm(
    pw: str = Form(...),
    score_id: int = Form(...),
    session_id: str = Form(...),
    level: str = Form(...),
    action: str = Form(...),
):
    """Apply reviewer decision and redirect back to dashboard."""
    if not config.REVIEW_PASSWORD or pw != config.REVIEW_PASSWORD:
        raise HTTPException(status_code=403, detail="Wrong password.")
    apply_review(score_id, session_id, level, action)
    return RedirectResponse(url=f"/review?pw={pw}", status_code=303)
