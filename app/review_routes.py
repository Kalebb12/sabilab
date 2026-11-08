"""FastAPI routes for password-protected reviewer dashboard."""

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
import config
from app.review import render_review_html, list_review_rows, apply_review

router = APIRouter()


@router.get("/review", response_class=HTMLResponse)
def review_page(request: Request, pw: str = ""):
    """Render reviewer dashboard; show results when password matches."""
    ok = bool(config.REVIEW_PASSWORD and pw == config.REVIEW_PASSWORD)
    rows = list_review_rows() if ok else []
    return HTMLResponse(render_review_html(ok, rows, pw=pw))


@router.post("/review/login")
def review_login(password: str = Form(...)):
    """Redirect back to review page with password as query param."""
    return RedirectResponse(url=f"/review?pw={password}", status_code=303)


@router.post("/review/confirm")
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
