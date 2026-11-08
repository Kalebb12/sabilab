"""FastAPI routes for public Evidence Cards."""

import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from app.card import publish_card, revoke_card, get_card_payload
from app.card_view import render_card_html
from app.schemas import CardPublishRequest

router = APIRouter()
logger = logging.getLogger("sabilab.card_routes")


@router.post("/session/{session_id}/card")
def create_card(session_id: str, req: CardPublishRequest = CardPublishRequest()):
    """Publish an unguessable public Evidence Card."""
    try:
        return publish_card(session_id, req.visible_fields)
    except ValueError as e:
        logger.exception("[%s] Evidence Card publication failed", session_id)
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/card/{slug}", response_class=HTMLResponse)
def view_public_card(slug: str):
    """Serve the public mobile-first Evidence Card without requiring login."""
    payload = get_card_payload(slug)
    return HTMLResponse(content=render_card_html(payload))


@router.post("/card/{slug}/revoke")
def revoke_public_card(slug: str):
    """Revoke an active public Evidence Card."""
    if not revoke_card(slug):
        raise HTTPException(status_code=404, detail="Card not found or already revoked.")
    return {"status": "revoked", "slug": slug}
