"""Integration test for clarification gate triggering and resolution."""

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
    db_file = tmp_path / "test_gate.db"
    monkeypatch.setattr("config.DB_PATH", db_file)
    init_db(db_file)
    yield db_file
    set_test_llm_handler(None)


def test_vague_message_triggers_gate_and_clarification_flow():
    """Verify that an ambiguous message triggers the clarification gate and resumes on answer."""
    sess = create_session({"first_name": "Caleb", "consent": True, "mode": "demo"})
    sid = sess["session_id"]
    post_message(sid, "Caleb", "Emeka, handle that soon.")
    save_task(sid, "Pay Kano 150k and give Mrs Bello 10% discount.")

    def mock_llm(system_instruction, prompt):
        if "Reading pass" in system_instruction:
            return {
                "readings": [
                    {
                        "message_id": "M4",
                        "language": "en",
                        "intent": "Vague task delegation",
                        "clarity": "unclear",
                        "ambiguity": "what task to handle and deadline",
                        "tone": "neutral",
                        "tone_flags": [],
                        "register_fit": "fits",
                    }
                ],
                "clarification_requests": [{"message_id": "M4", "question": "What exactly do you need from Emeka, and by when?"}],
                "possible_injection": False,
                "severe_tone": False,
            }
        else:
            return {
                "scores": [
                    {
                        "dimension": "Communication",
                        "criterion": "C1 Clarity",
                        "level": "Foundation",
                        "confidence": "high",
                        "evidence": "Pay Kano 150k",
                        "evidence_message_id": "M7",
                        "counter_evidence": None,
                        "reason": "Clarified intent allows action.",
                    }
                ],
                "feedback": {
                    "strength": {"quote": "Pay Kano 150k", "note": "Clear settlement amount."},
                    "improvement": "Specify deadlines upfront.",
                    "rewrite": "Please confirm stock before 12pm.",
                },
                "flags": {"possible_injection": False, "severe_tone": False, "needs_human_review": False},
            }

    set_test_llm_handler(mock_llm)
    client = TestClient(app)

    # 1. Trigger scoring -> should trigger clarification gate
    resp = client.post(f"/session/{sid}/score")
    assert resp.status_code == 200
    gate_data = resp.json()
    assert gate_data["status"] == "awaiting_clarification"
    assert len(gate_data["clarification_requests"]) == 1
    assert "What exactly do you need from Emeka" in gate_data["clarification_requests"][0]["question"]

    # 2. Answer clarification question -> should resume and complete scoring
    ans_resp = client.post(
        f"/session/{sid}/clarify",
        json={"message_id": "M4", "answer": "I need Emeka to verify blue Ankara inventory before 12pm."},
    )
    assert ans_resp.status_code == 200
    res_data = ans_resp.json()
    assert res_data["status"] == "completed"
    assert res_data["scoring"]["routing"] == "AI-assessed"
