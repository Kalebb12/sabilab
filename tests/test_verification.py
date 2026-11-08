"""Unit tests for pipeline verification checks."""

import pytest
from app.pipeline.verification import verify_scoring_output


def test_verification_valid_output():
    """Verify that accurate student quotes and valid rubric levels pass verification."""
    student_messages = {
        "M1": "We have ₦480,000 cash on hand.",
        "M2": "I recommend paying Kano Textiles ₦150,000 today.",
    }
    scoring_data = {
        "scores": [
            {
                "dimension": "Role skill",
                "criterion": "A1 Accuracy",
                "level": "Proficient",
                "confidence": "high",
                "evidence": "₦480,000",
                "evidence_message_id": "M1",
                "counter_evidence": None,
                "reason": "Accurately cited cash on hand.",
            }
        ],
        "feedback": {
            "strength": {"quote": "paying Kano Textiles ₦150,000 today", "note": "Clear figure."},
            "improvement": "Include timeline details.",
            "rewrite": "Pay today by 1pm.",
        },
    }
    is_valid, errors = verify_scoring_output(scoring_data, student_messages)
    assert is_valid is True
    assert len(errors) == 0


def test_verification_rejects_forged_quote():
    """Verify that a forged or hallucinated quote fails verification."""
    student_messages = {
        "M1": "What is our cash balance?",
    }
    scoring_data = {
        "scores": [
            {
                "dimension": "Role skill",
                "criterion": "A1 Accuracy",
                "level": "Proficient",
                "confidence": "high",
                "evidence": "I will personally pay off all debts tomorrow",
                "evidence_message_id": "M1",
                "counter_evidence": None,
                "reason": "Made a strong promise.",
            }
        ]
    }
    is_valid, errors = verify_scoring_output(scoring_data, student_messages)
    assert is_valid is False
    assert any("not an exact substring" in e for e in errors)


def test_verification_rejects_above_proficient():
    """Verify that levels above Proficient (e.g. Distinguished) fail verification."""
    student_messages = {"M1": "We have ₦480,000 cash"}
    scoring_data = {
        "scores": [
            {
                "dimension": "Communication",
                "criterion": "C1 Clarity",
                "level": "Distinguished",
                "confidence": "high",
                "evidence": "480,000",
                "evidence_message_id": "M1",
                "reason": "Exemplary work.",
            }
        ]
    }
    is_valid, errors = verify_scoring_output(scoring_data, student_messages)
    assert is_valid is False
    assert any("exceeds cap" in e for e in errors)
