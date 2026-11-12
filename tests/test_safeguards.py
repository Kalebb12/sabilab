"""Tests for message length limits, rate limits, draft persistence, and cost tracking."""

from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
import config
from db import init_db
from app.session import create_session, post_message
from app.task import save_task
from app.cost import log_llm_cost, get_cost_summary
from app.pipeline.llm import set_test_llm_handler
from main import app


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    """Isolate database for safeguards tests."""
    db_file = tmp_path / "safeguards_test.db"
    monkeypatch.setattr("config.DB_PATH", db_file)
    monkeypatch.setattr("config.GROQ_API_KEY", "")
    init_db(db_file)
    yield db_file
    set_test_llm_handler(None)


def test_message_length_cap():
    """Posting a message exceeding MESSAGE_MAX_CHARS returns 400."""
    client = TestClient(app)
    sess = create_session({"consent": True, "first_name": "Bola", "mode": "demo"})
    sid = sess["session_id"]

    # 501 character string
    long_msg = "A" * (config.MESSAGE_MAX_CHARS + 1)
    res = client.post(f"/session/{sid}/message", json={"sender": "Bola", "text": long_msg})
    assert res.status_code == 400
    assert "maximum length" in res.json()["detail"]


def test_per_session_rate_limit():
    """Sending messages too quickly in the same session triggers a 429 rate limit error."""
    client = TestClient(app)
    sess = create_session({"consent": True, "first_name": "Emeka", "mode": "demo"})
    sid = sess["session_id"]

    # First message succeeds
    res1 = client.post(f"/session/{sid}/message", json={"sender": "Emeka", "text": "First message"})
    assert res1.status_code == 200

    # Second immediate message from the same sender triggers rate limit
    res2 = client.post(f"/session/{sid}/message", json={"sender": "Emeka", "text": "Immediate second message"})
    assert res2.status_code == 429
    assert "Rate limit exceeded" in res2.json()["detail"]


def test_draft_autosave_and_resume():
    """Draft can be autosaved and resumed via session draft backup endpoint."""
    client = TestClient(app)
    sess = create_session({"consent": True, "first_name": "Funke", "mode": "demo"})
    sid = sess["session_id"]

    # Initially draft is None
    init_res = client.get(f"/session/{sid}/draft")
    assert init_res.status_code == 200
    assert init_res.json()["draft"] is None

    # Autosave draft
    draft_text = "Pay Kano Textiles ₦150,000 today from our ₦480,000 cash balance."
    save_res = client.post(f"/session/{sid}/draft", json={"text": draft_text})
    assert save_res.status_code == 200

    # Resume draft
    get_res = client.get(f"/session/{sid}/draft")
    assert get_res.status_code == 200
    assert get_res.json()["draft"] == draft_text


def test_cost_logging_summary_per_session():
    """Tokens and USD cost are tracked per session and accessible via GET /session/{id}/cost."""
    client = TestClient(app)
    sess = create_session({"consent": True, "first_name": "Segun", "mode": "demo"})
    sid = sess["session_id"]

    # Log 2 mock LLM calls
    response = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=1000, completion_tokens=200))
    priced_model = next(iter(config.LLM_MODEL_PRICES_PER_M))
    log_llm_cost(sid, "reading", model=priced_model, response=response)
    log_llm_cost(sid, "scoring", input_tokens=2000, output_tokens=400, model=priced_model)

    res = client.get(f"/session/{sid}/cost")
    assert res.status_code == 200
    data = res.json()
    assert data["session_id"] == sid
    assert data["total_calls"] == 2
    assert data["total_input_tokens"] == 3000
    assert data["total_output_tokens"] == 600
    assert data["total_cost_usd"] > 0
    assert len(data["calls"]) == 2
