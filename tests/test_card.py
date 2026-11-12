"""Integration tests for Evidence Card generation, public viewing, visible_fields, and revocation."""

import pytest
from fastapi.testclient import TestClient
from db import init_db
from app.session import create_session, post_message
from app.task import save_task
from app.pipeline.llm import set_test_llm_handler
from app.card import get_card_payload, publish_card
from app.card_view import render_card_html
from app.review import apply_review
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
    save_task(sid, "Pay Kano Textiles ₦150,000 today from our ₦480,000 cash balance.")

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
        return {
            "scores": [
                {
                    "dimension": "Accounts",
                    "criterion": "A1",
                    "level": "proficient",
                    "confidence": "high",
                    "evidence": "₦480,000 cash balance",
                    "evidence_message_id": "M7",
                    "counter_evidence": None,
                    "reason": "Accurately stated cash figure.",
                },
                {
                    "dimension": "Communication",
                    "criterion": "C1",
                    "level": "foundation",
                    "confidence": "high",
                    "evidence": "Pay Kano Textiles ₦150,000 today",
                    "evidence_message_id": "M7",
                    "counter_evidence": None,
                    "reason": "Clear action with amount.",
                },
                {
                    "dimension": "Creative thinking",
                    "criterion": "R1",
                    "level": "insufficient_evidence",
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

    score_resp = client.post(f"/session/{sid}/score")
    assert score_resp.status_code == 200

    card_resp = client.post(f"/session/{sid}/card", json={})
    assert card_resp.status_code == 200
    slug = card_resp.json()["slug"]

    view_resp = client.get(f"/card/{slug}")
    assert view_resp.status_code == 200
    html = view_resp.text

    assert "Chioma" in html
    assert "Evidence Card" in html
    assert "AI-assessed" in html
    assert "Accuracy" in html  # Criterion display name
    assert "₦480,000 cash balance" in html
    assert "highest level an AI can award is Proficient" in html
    assert "<details class=\"insufficient-group\">" in html

    revoke_resp = client.post(f"/card/{slug}/revoke")
    assert revoke_resp.status_code == 200

    revoked_view = client.get(f"/card/{slug}")
    assert revoked_view.status_code == 200
    assert "Card Unavailable" in revoked_view.text


def test_respect_visible_fields_on_public_card():
    """Verify that fields omitted from visible_fields are hidden on the public card."""
    sess = create_session({"first_name": "Tunde", "consent": True, "mode": "demo"})
    sid = sess["session_id"]
    save_task(sid, "Pay Kano Textiles ₦150,000 today from our ₦480,000 cash.")
    from app.pipeline.prepare import prepare_transcript

    _, student_messages = prepare_transcript(sid)
    evidence_message_id = next(
        message_id
        for message_id, text in student_messages.items()
        if "Pay Kano Textiles ₦150,000" in text
    )

    def mock_llm(system_instruction, prompt):
        if "Reading pass" in system_instruction:
            return {"readings": [], "clarification_requests": [], "possible_injection": False, "severe_tone": False}
        return {
            "scores": [
                {"dimension": "Accounts", "criterion": "A1", "level": "foundation", "confidence": "high", "evidence": "Pay Kano Textiles ₦150,000", "evidence_message_id": evidence_message_id, "reason": "Good note."}
            ],
            "feedback": {"strength": {"quote": "Pay Kano Textiles ₦150,000", "note": "Clear."}, "improvement": "Time.", "rewrite": "1pm."},
            "flags": {"possible_injection": False, "severe_tone": False, "needs_human_review": False},
        }

    set_test_llm_handler(mock_llm)
    client = TestClient(app)
    client.post(f"/session/{sid}/score")

    # Only publish with "levels" (hiding quotes, recommendations, and badges)
    card_resp = client.post(f"/session/{sid}/card", json={"visible_fields": ["levels"]})
    slug = card_resp.json()["slug"]

    html = client.get(f"/card/{slug}").text
    assert "Accuracy" in html
    assert "Targeted Growth Drill" not in html
    assert "&ldquo;Pay Kano Textiles ₦150,000&rdquo;" not in html


def test_outdated_data_shows_retake_banner():
    """Scores with outdated criteria or levels render an outdated result banner."""
    sess = create_session({"first_name": "Kemi", "consent": True, "mode": "demo"})
    sid = sess["session_id"]
    from db import get_connection
    conn = get_connection()
    conn.execute(
        "INSERT INTO scores (session_id, dimension, criterion, level, confidence, evidence, reason, rubric_version, model_and_version, prompt_version) VALUES (?, 'General', 'OldCrit', 'novice', 'low', 'none', 'none', 'v0.1', 'm', 'v0.1')",
        (sid,),
    )
    conn.commit()
    conn.close()

    client = TestClient(app)
    card_resp = client.post(f"/session/{sid}/card", json={})
    slug = card_resp.json()["slug"]

    html = client.get(f"/card/{slug}").text
    assert "Outdated result, please retake the scenario" in html


def _insert_card_score(session_id, *, level="Foundation", evidence="I paused payment."):
    from db import get_connection

    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO scores
           (session_id, dimension, criterion, level, confidence, evidence, counter_evidence,
            reason, rubric_version, model_and_version, prompt_version)
           VALUES (?, 'Leadership', 'L4', ?, 'high', ?, '', 'Accepted ownership.', 'v1', 'test', 'v1')""",
        (session_id, level, evidence),
    )
    conn.execute(
        """INSERT INTO results (session_id, levels, did_well, improve, recommendation, routing)
           VALUES (?, '{}', 'Good ownership.', 'Explain the change.', '{}', 'AI-assessed')""",
        (session_id,),
    )
    conn.commit()
    score_id = cursor.lastrowid
    conn.close()
    return score_id


def test_new_visible_fields_filter_content_and_escape_student_name():
    sess = create_session(
        {"first_name": "<img src=x onerror=alert(1)>", "consent": True, "mode": "demo"}
    )
    sid = sess["session_id"]
    _insert_card_score(sid)

    published = publish_card(sid, ["name", "scores", "growth_drill"], tier="ai_assessed")
    payload = get_card_payload(published["slug"])
    html = render_card_html(payload)

    assert payload["visible_fields"] == ["name", "scores", "growth_drill"]
    assert payload["student_name"] == "<img src=x onerror=alert(1)>"
    assert "&lt;img src=x onerror=alert(1)&gt;" in html
    assert "<img src=x onerror=alert(1)>" not in html
    assert "Ownership" in html
    assert "Targeted Growth Drill" in html
    assert "I paused payment." not in html
    assert "AI-assessed" not in html


def test_human_verified_status_requires_a_recorded_review():
    sess = create_session({"first_name": "Amina", "consent": True, "mode": "demo"})
    sid = sess["session_id"]
    score_id = _insert_card_score(sid)

    with pytest.raises(ValueError, match="reviewer confirmation"):
        publish_card(sid, tier="human_verified")

    apply_review(score_id, sid, "Foundation", "confirm")
    published = publish_card(sid, tier="human_verified")
    html = render_card_html(get_card_payload(published["slug"]))

    assert "Human-verified" in html
    assert "A reviewer confirmed this result" in html


def test_public_card_rejects_unknown_visible_fields():
    sess = create_session({"first_name": "Kemi", "consent": True, "mode": "demo"})
    client = TestClient(app)

    response = client.post(
        f"/session/{sess['session_id']}/card",
        json={"visible_fields": ["private_transcript"]},
    )

    assert response.status_code == 422
