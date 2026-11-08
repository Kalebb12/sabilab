"""Integration tests for Evidence Card generation, public viewing, and revocation."""

import pytest
from fastapi.testclient import TestClient
from db import init_db
from app.session import create_session, post_message
from app.task import save_task
from app.pipeline.llm import set_test_llm_handler
from main import app


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    """Set up an isolated test database for every test."""
    db_file = tmp_path / "test_card.db"
    monkeypatch.setattr("config.DB_PATH", db_file)
    init_db(db_file)
    yield db_file
    set_test_llm_handler(None)


def test_card_publishing_and_public_view_without_login():
    """Verify that a finished session produces an unguessable card that opens with no login."""
    sess = create_session({"first_name": "Chioma", "consent": True, "mode": "demo"})
    sid = sess["session_id"]
    post_message(sid, "Chioma", "What is the cash balance?")
    save_task(sid, "Pay Kano Textiles ₦150,000 today from our ₦480,000 cash.")

    def mock_llm(system_instruction, prompt):
        if "Reading pass" in system_instruction:
            return {
                "readings": [
                    {"message_id": "M4", "language": "en", "intent": "Cash query", "clarity": "clear", "tone": "neutral", "tone_flags": [], "register_fit": "fits"},
                    {"message_id": "M7", "language": "en", "intent": "Recommendation", "clarity": "clear", "tone": "positive", "tone_flags": [], "register_fit": "fits"},
                ],
                "clarification_requests": [],
                "possible_injection": False,
                "severe_tone": False,
            }
        else:
            return {
                "scores": [
                    {
                        "dimension": "Role skill",
                        "criterion": "A1 Accuracy",
                        "level": "Proficient",
                        "confidence": "high",
                        "evidence": "₦480,000",
                        "evidence_message_id": "M7",
                        "counter_evidence": None,
                        "reason": "Accurately stated cash figure.",
                    },
                    {
                        "dimension": "Communication",
                        "criterion": "C1 Clarity",
                        "level": "Foundation",
                        "confidence": "high",
                        "evidence": "Pay Kano Textiles ₦150,000 today",
                        "evidence_message_id": "M7",
                        "counter_evidence": None,
                        "reason": "Clear action with amount.",
                    },
                    {
                        "dimension": "Creative thinking",
                        "criterion": "R1 Problem framing",
                        "level": "Insufficient evidence",
                        "confidence": "low",
                        "evidence": "",
                        "evidence_message_id": "",
                        "reason": "No creative framing observed.",
                    },
                ],
                "feedback": {
                    "strength": {"quote": "Pay Kano Textiles ₦150,000 today", "note": "Clear settlement terms."},
                    "improvement": "Add a firm delivery timeline.",
                    "rewrite": "Dispatch payment by 1pm.",
                },
                "flags": {"possible_injection": False, "severe_tone": False, "needs_human_review": False},
            }

    set_test_llm_handler(mock_llm)
    client = TestClient(app)

    # 1. Run scoring
    score_resp = client.post(f"/session/{sid}/score")
    assert score_resp.status_code == 200

    # 2. Publish Evidence Card
    card_resp = client.post(f"/session/{sid}/card", json={})
    assert card_resp.status_code == 200
    card_data = card_resp.json()
    slug = card_data["slug"]
    assert len(slug) >= 20  # secrets.token_urlsafe(16) produces >= 22 chars

    # 3. View public Evidence Card without login
    view_resp = client.get(f"/card/{slug}")
    assert view_resp.status_code == 200
    html = view_resp.text

    assert "Chioma" in html
    assert "Adaeze’s Fabrics" in html
    assert "AI-assessed" in html
    assert "₦480,000" in html
    assert "Insufficient evidence" in html
    assert "Statement of Limits" in html

    # 4. Revoke card
    revoke_resp = client.post(f"/card/{slug}/revoke")
    assert revoke_resp.status_code == 200

    # 5. Verify revoked card is unavailable
    revoked_view = client.get(f"/card/{slug}")
    assert revoked_view.status_code == 200
    assert "Card Unavailable" in revoked_view.text
