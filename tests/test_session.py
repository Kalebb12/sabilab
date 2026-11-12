"""Tests for session management, scripted replies, and server-side twist trigger."""

from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from db import init_db, get_connection
from app.loader import load_scenario, render_scenario_text
from app.session import create_session, post_message, get_messages
from app.pipeline.llm import set_test_llm_handler
from app.twist import check_and_fire_twist, is_twist_fired
from main import app


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    """Set up an isolated test database for every test."""
    db_file = tmp_path / "test_session.db"
    monkeypatch.setattr("config.DB_PATH", db_file)
    monkeypatch.setattr("config.GROQ_API_KEY", "")
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


def test_teammate_keyword_replies_before_twist():
    """Verify addressed teammates use their matching bank lines before the twist."""
    start_time = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    sess = create_session({"first_name": "Caleb", "consent": True, "mode": "demo"}, current_time=start_time)
    session_id = sess["session_id"]

    # Student posts at t = 10s (twist threshold is 45s)
    t_msg = start_time + timedelta(seconds=10)
    replies = post_message(
        session_id,
        "Caleb",
        "Emeka, what is Mrs Bello's price request? Ngozi, is the blue Ankara in stock?",
        current_time=t_msg,
    )

    # Returned replies: student message, owner reaction, and 2 targeted teammates
    assert len(replies) == 4
    assert replies[0]["sender"] == "Caleb"
    assert replies[1]["sender"] == "Adaeze"
    assert replies[2]["sender"] == "Emeka"
    assert "20% off" in replies[2]["text"]
    assert replies[3]["sender"] == "Ngozi"
    assert "in stock" in replies[3]["text"]

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
    assert twist_msg["phase"] == "twist"
    assert "Kano Textiles cancelled supply" in twist_msg["text"]
    assert is_twist_fired(session_id)
    persisted_twist = next(message for message in get_messages(session_id) if message["id"] == twist_msg["id"])
    assert persisted_twist["phase"] == "twist"

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
    replies = post_message(
        session_id,
        "Caleb",
        "Emeka, what is the supplier payment condition? Ngozi, what is happening to stock?",
        current_time=t_after,
    )

    # Replies include the twist, student message, owner reaction, and targeted teammates.
    senders = [m["sender"] for m in replies]
    assert senders == ["Adaeze", "Caleb", "Adaeze", "Emeka", "Ngozi"]

    # Teammates use the approved bank, while Adaeze uses her after-twist fallback without a key.
    emeka_msg = next(m for m in replies if m["sender"] == "Emeka")
    assert "Ask Adaeze about cash" in emeka_msg["text"]

    ngozi_msg = next(m for m in replies if m["sender"] == "Ngozi")
    assert "in stock" in ngozi_msg["text"]
    owner_replies = [m for m in replies if m["sender"] == "Adaeze"]
    assert "Marketing proposed" in owner_replies[-1]["text"]


def test_naming_emeka_only_triggers_emeka():
    start_time = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    sess = create_session({"first_name": "Caleb", "consent": True, "mode": "demo"}, current_time=start_time)

    replies = post_message(
        sess["session_id"],
        "Caleb",
        "Emeka, is Mrs Bello asking for a discount?",
        current_time=start_time + timedelta(seconds=10),
    )

    teammate_replies = [message for message in replies if message["sender"] in {"Emeka", "Ngozi"}]
    assert [message["sender"] for message in teammate_replies] == ["Emeka"]


def test_teammate_stops_replying_after_two_answers():
    start_time = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    sess = create_session({"first_name": "Caleb", "consent": True, "mode": "demo"}, current_time=start_time)
    session_id = sess["session_id"]

    first = post_message(
        session_id, "Caleb", "Emeka, what discount does Mrs Bello request?",
        current_time=start_time + timedelta(seconds=10),
    )
    second = post_message(
        session_id, "Caleb", "Emeka, when does Mrs Bello need delivery?",
        current_time=start_time + timedelta(seconds=12),
    )
    third = post_message(
        session_id, "Caleb", "Emeka, what is our cash position?",
        current_time=start_time + timedelta(seconds=14),
    )

    replies = first + second + third
    assert sum(message["sender"] == "Emeka" for message in replies) == 2
    assert sum(message["sender"] == "Ngozi" for message in replies) == 0


def test_owner_falls_back_to_scripted_line_without_api_key(caplog):
    start_time = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    sess = create_session({"first_name": "Caleb", "consent": True, "mode": "demo"}, current_time=start_time)

    replies = post_message(
        sess["session_id"],
        "Caleb",
        "What is the current situation?",
        current_time=start_time + timedelta(seconds=10),
    )

    owner_reply = next(message["text"] for message in replies if message["sender"] == "Adaeze")
    assert owner_reply == "We have ₦480,000 cash on hand; I need a plan before this huddle ends."
    assert "path=scripted_fallback" in caplog.text


def test_rewritten_scenario_amounts_match_each_variant_answer_key():
    scenario = load_scenario("adaeze")

    def rendered_lines(variant):
        return [
            render_scenario_text(line, scenario, variant)
            for line in [
                *scenario["owner"]["scripted_lines"].values(),
                *(
                    teammate[key]
                    for teammate in scenario["roster"][:2]
                    for key in ("reply_before_twist", "reply_after_twist")
                ),
                scenario["keyword_reply_bank"]["Emeka"]["price_discount"],
            ]
        ]

    lines_a = rendered_lines("A")
    lines_b = rendered_lines("B")

    assert all(len(line.split()) <= 35 for line in lines_a + lines_b)
    assert "20%" in lines_a[0] and "₦480,000" in lines_a[1]
    assert "₦350,000" in lines_a[2] and "₦130,000" in lines_a[2]
    assert "20%" in lines_a[-1]
    assert "15%" in lines_b[0] and "₦550,000" in lines_b[1]
    assert "₦400,000" in lines_b[2] and "₦150,000" in lines_b[2]
    assert "15%" in lines_b[-1]


def test_owner_persona_receives_last_two_messages_and_current_beat():
    start_time = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    sess = create_session({"first_name": "Caleb", "consent": True, "mode": "demo"}, current_time=start_time)
    prompts = []

    def mock_owner(system_instruction, prompt):
        prompts.append(prompt)
        return {"reply": "Cash flow is tight, and Kano supplies our needed raw materials."}

    set_test_llm_handler(mock_owner)
    try:
        post_message(
            sess["session_id"],
            "Caleb",
            "We can discuss the customer discount.",
            current_time=start_time + timedelta(seconds=10),
        )
        post_message(
            sess["session_id"],
            "Caleb",
            "The delivery deadline is still important.",
            current_time=start_time + timedelta(seconds=50),
        )
    finally:
        set_test_llm_handler(None)

    assert len(prompts) == 2
    assert "Current beat: after_twist" in prompts[-1]
    assert "We can discuss the customer discount." in prompts[-1]
    assert "The delivery deadline is still important." in prompts[-1]


def test_owner_persona_falls_back_instead_of_recommending_actions():
    start_time = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    sess = create_session({"first_name": "Caleb", "consent": True, "mode": "demo"}, current_time=start_time)
    set_test_llm_handler(
        lambda system_instruction, prompt: {"reply": "You should pay Kano today."}
    )

    try:
        replies = post_message(
            sess["session_id"],
            "Caleb",
            "Kano's invoice is overdue.",
            current_time=start_time + timedelta(seconds=10),
        )
    finally:
        set_test_llm_handler(None)

    owner_reply = next(message["text"] for message in replies if message["sender"] == "Adaeze")
    assert owner_reply == "We have ₦480,000 cash on hand; I need a plan before this huddle ends."


def test_owner_persona_falls_back_on_unlisted_amount():
    start_time = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    sess = create_session({"first_name": "Caleb", "consent": True, "mode": "demo"}, current_time=start_time)
    set_test_llm_handler(
        lambda system_instruction, prompt: {"reply": "The cash amount is ₦300,000."}
    )

    try:
        replies = post_message(
            sess["session_id"],
            "Caleb",
            "Could we discuss the discount?",
            current_time=start_time + timedelta(seconds=10),
        )
    finally:
        set_test_llm_handler(None)

    owner_reply = next(message["text"] for message in replies if message["sender"] == "Adaeze")
    assert owner_reply == "We have ₦480,000 cash on hand; I need a plan before this huddle ends."


def test_owner_persona_falls_back_on_inferred_constraint():
    start_time = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
    sess = create_session({"first_name": "Caleb", "consent": True, "mode": "demo"}, current_time=start_time)
    set_test_llm_handler(
        lambda system_instruction, prompt: {
            "reply": "My current cash on hand limits my ability to make a partial payment."
        }
    )

    try:
        replies = post_message(
            sess["session_id"],
            "Caleb",
            "Could we discuss the discount?",
            current_time=start_time + timedelta(seconds=10),
        )
    finally:
        set_test_llm_handler(None)

    owner_reply = next(message["text"] for message in replies if message["sender"] == "Adaeze")
    assert owner_reply == "We have ₦480,000 cash on hand; I need a plan before this huddle ends."
