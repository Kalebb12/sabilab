"""Tests for POST /task submission and database persistence."""

import pytest
from fastapi.testclient import TestClient
from db import init_db, get_connection
from app.session import create_session
from main import app


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    """Set up an isolated test database for every test."""
    db_file = tmp_path / "test_task.db"
    monkeypatch.setattr("config.DB_PATH", db_file)
    init_db(db_file)
    return db_file


def test_submit_task_endpoint():
    """Verify POST /task stores task, logs submit event, and returns check results."""
    sess = create_session({"first_name": "Caleb", "consent": True, "mode": "demo"})
    session_id = sess["session_id"]
    client = TestClient(app)

    task_text = (
        "We currently have ₦480,000 in cash. I propose paying Kano Textiles ₦150k today "
        "to restore fabric supply, and negotiating Mrs Bello's discount to 10% instead of 20%."
    )
    resp = client.post("/task", json={"session_id": session_id, "text": task_text})
    assert resp.status_code == 200
    data = resp.json()

    assert data["session_id"] == session_id
    assert "task_id" in data
    assert "checks" in data

    # Verify check results
    matched = {c["id"]: c["matched"] for c in data["checks"]}
    assert matched["K1"] is True  # 480,000 cash on hand
    assert matched["K4"] is True  # 20% or 10% discount
    assert matched["K5"] is True  # 150k partial payment

    # Verify task row exists in tasks table
    conn = get_connection()
    task_row = conn.execute("SELECT text, session_id FROM tasks WHERE session_id = ?", (session_id,)).fetchone()
    assert task_row is not None
    assert task_row["text"] == task_text

    # Verify submit event logged in events table
    event_row = conn.execute("SELECT type, details FROM events WHERE session_id = ? AND type = 'submit'", (session_id,)).fetchone()
    assert event_row is not None
    assert "length" in event_row["details"]

    # Verify session status updated
    sess_row = conn.execute("SELECT status FROM sessions WHERE id = ?", (session_id,)).fetchone()
    assert sess_row["status"] == "task_submitted"
    conn.close()


def test_submit_task_invalid_session():
    """Verify POST /task returns 404 if session does not exist."""
    client = TestClient(app)
    resp = client.post("/task", json={"session_id": "nonexistent_id", "text": "Some text"})
    assert resp.status_code == 404
