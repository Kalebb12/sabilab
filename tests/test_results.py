"""Unit tests for badge rules and weakest area recommendations."""

import pytest
from app.results import evaluate_badges, get_recommendation_for_weakest, LEVEL_ORDER


def test_badge_awarded_when_all_dimensions_at_least_foundation():
    """Verify that a badge is issued when all evaluated dimensions meet Foundation or higher."""
    scores = [
        {"dimension": "Communication", "criterion": "C1 Clarity", "level": "Foundation", "evidence": "quote"},
        {"dimension": "Role skill", "criterion": "A1 Accuracy", "level": "Proficient", "evidence": "quote"},
    ]
    badge = evaluate_badges("dummy_session", scores, routing="AI-assessed")
    assert badge is not None
    assert badge["level"] == "Foundation"
    assert badge["tier"] == "AI-assessed"


def test_badge_proficient_when_all_dimensions_proficient():
    """Verify that badge level is Proficient when all criteria reach Proficient."""
    scores = [
        {"dimension": "Communication", "criterion": "C1 Clarity", "level": "Proficient", "evidence": "quote"},
        {"dimension": "Role skill", "criterion": "A1 Accuracy", "level": "Proficient", "evidence": "quote"},
    ]
    badge = evaluate_badges("dummy_session", scores, routing="AI-assessed")
    assert badge is not None
    assert badge["level"] == "Proficient"


def test_badge_denied_when_any_dimension_needs_practice():
    """Verify that no badge is issued if any dimension is Needs practice."""
    scores = [
        {"dimension": "Communication", "criterion": "C1 Clarity", "level": "Needs practice", "evidence": "quote"},
        {"dimension": "Role skill", "criterion": "A1 Accuracy", "level": "Proficient", "evidence": "quote"},
    ]
    badge = evaluate_badges("dummy_session", scores, routing="AI-assessed")
    assert badge is None


def test_recommendation_maps_to_weakest_area():
    """Verify that the weakest scored criterion determines the recommended drill, guide, and habit."""
    scores = [
        {"dimension": "Role skill", "criterion": "A1 Accuracy", "level": "Needs practice"},
        {"dimension": "Communication", "criterion": "C1 Clarity", "level": "Proficient"},
    ]
    rec = get_recommendation_for_weakest(scores)
    assert "Accounts" in rec["area"]
    assert "drill" in rec
    assert "guide" in rec
    assert "habit" in rec
