"""Tests for session management, scripted replies, and server-side twist trigger."""

from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from db import init_db, get_connection
from app.session import create_session, post_message, get_messages
from app.twist import check_and_fire_twist, is_twist_fired
from main import app


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    """Set up an isolated test database for every test."""
    db_file = tmp_path / "test_session.db"
    monkeypatch.setattr("config.DB_PATH", db_file)
    init_db(db_file)
    return db_file


def test_session_requires_consent():
    """Verify that a session cannot start without consent=true."""
    client = TestClient(app)

    # Missing consent
    resp = client.post("/session", json={"first_name": "Caleb", "consent": False})
    assert resp.status_code == 400
    assert "Consent is required" in resp.json()["detail"]

    # Direct function call missing consent
    with pytest.raises(ValueError, match="Consent is required"):
        create_session({"first_name": "Caleb", "consent": False})


def test_session_start_success():
    """Verify session creation returns private brief, roster, and seeds opening lines."""
    client = TestClient(app)
    resp = client.post(
        "/session",
        json={
            "first_name": "Caleb",
            "consent": True,
            "scenario_id": "adaeze",
            "teammate_ids": ["sales", "operations"],
            "mode": "demo",
        },
    )
    assert resp.status_code == 201
    data = resp.json()

    assert "session_id" in data
    assert data["student_role"] == "Accountant"
    assert "Mrs Bello is asking for a 20% discount" in data["private_brief"]
    assert len(data["roster"]) == 2
    assert {t["id"] for t in data["roster"]} == {"sales", "operations"}

    # Verify session start event is logged
    conn = get_connection()
    events = conn.execute("SELECT type FROM events WHERE session_id = ?", (data["session_id"],)).fetchall()
    assert any(e["type"] == "session_start" for e in events)

    # Verify opening messages exist in database
    msgs = conn.execute("SELECT sender, sequence_number, phase FROM messages WHERE session_id = ? ORDER BY sequence_number", (data["session_id"],)).fetchall()
    conn.close()
    assert len(msgs) >= 3  # Adaeze + 2 teammates
    assert msgs[0]["sender"] == "Adaeze"
    assert msgs[0]["sequence_number"] == 1
    assert msgs[0]["phase"] == "huddle"


def test_teammate_scripted_replies_before_twist():
    """Verify teammates reply with before-twist lines before the twist point."""
    start_time = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    sess = create_session({"first_name": "Caleb", "consent": True, "mode": "demo"}, current_time=start_time)
    session_id = sess["session_id"]

    # Student posts at t = 10s (twist threshold is 45s)
    t_msg = start_time + timedelta(seconds=10)
    replies = post_message(session_id, "Caleb", "What is our current cash position?", current_time=t_msg)

    # Returned replies: student message + 2 teammate replies
    assert len(replies) == 3
    assert replies[0]["sender"] == "Caleb"
    assert replies[1]["sender"] == "Emeka"
    assert "cuts our margin very thin" in replies[1]["text"]
    assert replies[2]["sender"] == "Ngozi"
    assert "standing by to pack and send" in replies[2]["text"]

    # Twist should not have fired yet
    assert not is_twist_fired(session_id)


def test_twist_fires_once_at_server_clock_threshold():
    """Verify twist fires when elapsed time reaches threshold and only fires once."""
    start_time = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    sess = create_session({"first_name": "Caleb", "consent": True, "mode": "demo"}, current_time=start_time)
    session_id = sess["session_id"]

    # Demo mode threshold is 90s * 0.5 = 45s
    # At t = 44s: twist does NOT fire
    twist_early = check_and_fire_twist(session_id, current_time=start_time + timedelta(seconds=44))
    assert twist_early is None
    assert not is_twist_fired(session_id)

    # At t = 45s: twist FIRES
    twist_msg = check_and_fire_twist(session_id, current_time=start_time + timedelta(seconds=45))
    assert twist_msg is not None
    assert twist_msg["sender"] == "Adaeze"
    assert "Kano Textiles has cancelled our supply" in twist_msg["text"]
    assert is_twist_fired(session_id)

    # Calling check_and_fire_twist again at t = 50s returns None (fires once only)
    twist_repeat = check_and_fire_twist(session_id, current_time=start_time + timedelta(seconds=50))
    assert twist_repeat is None

    # Verify event table has exactly one twist_fired event
    conn = get_connection()
    events = conn.execute("SELECT type, details FROM events WHERE session_id = ? AND type = 'twist_fired'", (session_id,)).fetchall()
    assert len(events) == 1
    assert "elapsed_seconds" in events[0]["details"]
    conn.close()


def test_teammate_replies_switch_after_twist():
    """Verify teammate scripted replies switch to after-twist set once twist fires."""
    start_time = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    sess = create_session({"first_name": "Caleb", "consent": True, "mode": "demo"}, current_time=start_time)
    session_id = sess["session_id"]

    # Student posts at t = 50s (past the 45s twist mark)
    t_after = start_time + timedelta(seconds=50)
    replies = post_message(session_id, "Caleb", "We need to deal with Kano Textiles immediately.", current_time=t_after)

    # Replies include: Twist message + Student message + 2 teammate after-twist replies
    senders = [m["sender"] for m in replies]
    assert senders == ["Adaeze", "Caleb", "Emeka", "Ngozi"]

    # Emeka and Ngozi replies are from the after-twist set
    emeka_msg = next(m for m in replies if m["sender"] == "Emeka")
    assert "Without Kano, we have no more stock coming in" in emeka_msg["text"]

    ngozi_msg = next(m for m in replies if m["sender"] == "Ngozi")
    assert "warehouse will run completely dry" in ngozi_msg["text"]
