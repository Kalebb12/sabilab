"""Tests for multi-attempt tracking, variant B facts, and side-by-side comparison."""

import pytest
from fastapi.testclient import TestClient
from app.session import create_session
from app.task import save_task
from app.card import publish_card
from db import get_connection


def _seed_score(session_id: str, criterion: str, level: str, quote: str):
    """Helper to insert verified score and result row."""
    conn = get_connection()
    conn.execute(
        """INSERT INTO scores (session_id, dimension, criterion, level, confidence, evidence, reason, rubric_version, model_and_version, prompt_version)
           VALUES (?, 'Communication', ?, ?, 'High', ?, 'Good', 'v0.2', 'test-model', 'v0.2')""",
        (session_id, criterion, level, quote),
    )
    conn.execute(
        """INSERT INTO results (session_id, levels, did_well, improve, recommendation, routing)
           VALUES (?, '{}', 'Clear communication', 'Be faster', 'Practice drill', 'AI-assessed')""",
        (session_id,),
    )
    conn.execute("UPDATE sessions SET status = 'completed' WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()


def test_first_and_second_attempt_variants():
    """First attempt uses variant A; second attempt uses variant B with updated brief."""
    s1 = create_session({"consent": True, "first_name": "Tunde", "mode": "demo"})
    assert s1["attempt_number"] == 1
    assert s1["variant"] == "A"
    assert "Variant B facts" not in s1["private_brief"]

    user_id = s1["user_id"]
    # Mark session 1 as completed/scored
    _seed_score(s1["session_id"], "Clarity and Brevity", "Foundation", "hello")

    s2 = create_session({"consent": True, "user_id": user_id, "first_name": "Tunde", "mode": "demo"})
    assert s2["attempt_number"] == 2
    assert s2["variant"] == "B"
    assert "Variant B facts" in s2["private_brief"]
    assert "₦550,000" in s2["private_brief"] or "550,000" in s2["private_brief"]


def test_variant_b_checks_evaluation():
    """Task submission for variant B evaluates against variant B check figures."""
    s1 = create_session({"consent": True, "first_name": "Amina", "mode": "demo"})
    _seed_score(s1["session_id"], "Clarity and Brevity", "Needs practice", "hi")

    s2 = create_session({"consent": True, "user_id": s1["user_id"], "first_name": "Amina", "mode": "demo"})
    # Variant B has ₦550,000 cash, ₦400,000 invoice, ₦150,000 remaining, 15% discount
    res = save_task(s2["session_id"], "We have 550k on hand, Kano invoice is 400k, leaving 150k. Offer 15% discount.")
    checks = {c["id"]: c["matched"] for c in res["checks"]}
    assert checks["K1"] is True  # 550k
    assert checks["K2"] is True  # 400k
    assert checks["K3"] is True  # 150k
    assert checks["K4"] is True  # 15%


def test_side_by_side_results_and_card():
    """Results and public Evidence Card show attempt 1 vs attempt 2 side by side."""
    from main import app
    client = TestClient(app)

    s1 = create_session({"consent": True, "first_name": "Chidi", "mode": "demo"})
    _seed_score(s1["session_id"], "C1", "Needs practice", "first try text")

    s2 = create_session({"consent": True, "user_id": s1["user_id"], "first_name": "Chidi", "mode": "demo"})
    _seed_score(s2["session_id"], "C1", "Proficient", "second try text")

    # Check results API for session 2
    r_results = client.get(f"/session/{s2['session_id']}/results")
    assert r_results.status_code == 200
    comp = r_results.json().get("comparison")
    assert comp is not None
    assert len(comp["rows"]) >= 1
    row = next(r for r in comp["rows"] if r["criterion"] == "C1")
    assert row["attempt_1"] == "Needs practice"
    assert row["attempt_2"] == "Proficient"

    # Publish card for session 2 and verify public card view
    pub = publish_card(s2["session_id"])
    r_card = client.get(f"/card/{pub['slug']}")
    assert r_card.status_code == 200
    assert "Attempt Comparison" in r_card.text
    assert "Needs practice" in r_card.text
    assert "Proficient" in r_card.text


def test_more_than_two_attempts_allowed():
    """Additional attempts keep working and stay on variant B after the first retry."""
    s1 = create_session({"consent": True, "first_name": "Ngozi", "mode": "demo"})
    _seed_score(s1["session_id"], "Clarity and Brevity", "Foundation", "text 1")

    s2 = create_session({"consent": True, "user_id": s1["user_id"], "first_name": "Ngozi", "mode": "demo"})
    _seed_score(s2["session_id"], "Clarity and Brevity", "Proficient", "text 2")

    s3 = create_session({"consent": True, "user_id": s1["user_id"], "first_name": "Ngozi", "mode": "demo"})
    assert s3["attempt_number"] == 3
    assert s3["variant"] == "B"
    assert "[Variant B facts]" in s3["private_brief"]
    assert "Cash on hand: ₦550,000" in s3["private_brief"]
