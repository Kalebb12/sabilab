"""Unit tests for pipeline verification checks enforcing rubric and quote rules."""

import pytest
from app.pipeline.verification import (
    sanitize_unverified_scores,
    verify_scoring_output,
)


def test_verification_valid_output():
    """Verify that accurate student quotes and valid rubric levels pass verification."""
    student_messages = {
        "M1": "We have ₦480,000 cash on hand.",
        "M2": "I recommend paying Kano Textiles ₦150,000 today.",
    }
    scoring_data = {
        "scores": [
            {
                "dimension": "Accounts",
                "criterion": "A1",
                "level": "proficient",
                "confidence": "high",
                "evidence": "₦480,000 cash on hand",
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
    student_messages = {"M1": "What is our cash balance?"}
    scoring_data = {
        "scores": [
            {
                "dimension": "Accounts",
                "criterion": "A1",
                "level": "proficient",
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


def test_verification_rejects_short_or_single_word_quote():
    """Quotes under 8 chars or under 2 words (like 'No') must be rejected."""
    student_messages = {"M1": "No", "M2": "Short"}
    scoring_data = {
        "scores": [
            {
                "dimension": "Communication",
                "criterion": "C1",
                "level": "foundation",
                "evidence": "No",
                "evidence_message_id": "M1",
                "reason": "Replied no.",
            }
        ]
    }
    is_valid, errors = verify_scoring_output(scoring_data, student_messages)
    assert is_valid is False
    assert any("shorter than 8 characters" in e or "under 2 words" in e for e in errors)


def test_verification_rejects_invalid_criterion_or_level():
    """Verify that criteria or levels not in rubric.json (e.g. novice, C99) fail verification."""
    student_messages = {"M1": "We have ₦480,000 cash on hand."}
    scoring_data = {
        "scores": [
            {
                "dimension": "General",
                "criterion": "C99",
                "level": "novice",
                "evidence": "₦480,000 cash on hand",
                "evidence_message_id": "M1",
                "reason": "Invalid crit and level.",
            }
        ]
    }
    is_valid, errors = verify_scoring_output(scoring_data, student_messages)
    assert is_valid is False
    assert any("not recognized in rubric.json" in e for e in errors)
    assert any("not in rubric.json" in e for e in errors)


def test_unverified_quotes_are_withheld_before_scores_are_saved():
    student_messages = {
        "M1": "I realised payment was double-booked.",
        "M2": "I paused the Kano Textiles payment.",
    }
    scoring_data = {
        "scores": [
            {
                "criterion": "L4",
                "level": "foundation",
                "evidence": "I realised payment was double‑booked.",
                "evidence_message_id": "M1",
                "reason": "Accepted ownership.",
            },
            {
                "criterion": "A1",
                "level": "foundation",
                "evidence": "I paused the Kano Textiles payment.",
                "evidence_message_id": "M2",
                "reason": "Verified evidence.",
            },
        ],
        "feedback": {
            "strength": {"quote": "fabricated strength quote", "note": "Good work."}
        },
    }

    sanitized = sanitize_unverified_scores(scoring_data, student_messages)

    assert sanitized["scores"][0]["level"] == "insufficient_evidence"
    assert sanitized["scores"][0]["evidence"] == ""
    assert sanitized["scores"][1]["level"] == "foundation"
    assert sanitized["feedback"]["strength"]["quote"] == ""
