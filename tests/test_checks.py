"""Tests for checks.py normalization and figure pattern matching."""

import pytest
from checks import normalize_text, report_checks
from app.loader import load_scenario


@pytest.fixture
def adaeze_checks():
    """Load checks defined in the Adaeze's Fabrics scenario."""
    scenario = load_scenario("adaeze")
    return scenario["checks"]


def test_checks_350k_and_variants(adaeze_checks):
    """Verify '350k', '₦350,000', and '350000' all match the overdue invoice check (K2)."""
    for variant in ["350k", "₦350,000", "350000"]:
        results = report_checks(f"Pay {variant} to Kano Textiles immediately.", adaeze_checks)
        matched = {r["id"]: r["matched"] for r in results}
        assert matched["K2"] is True, f"Expected K2 to match '{variant}'"
        assert matched["K3"] is False, f"Expected K3 NOT to match '{variant}'"


def test_checks_130k_and_variants(adaeze_checks):
    """Verify '₦130,000' and '130k' all match the remaining cash check (K3)."""
    for variant in ["₦130,000", "130k"]:
        results = report_checks(f"That leaves {variant} cash buffer.", adaeze_checks)
        matched = {r["id"]: r["matched"] for r in results}
        assert matched["K3"] is True, f"Expected K3 to match '{variant}'"
        assert matched["K2"] is False, f"Expected K2 NOT to match '{variant}'"


def test_checks_garbage_text_matches_none(adaeze_checks):
    """Verify garbage text matches none of the scenario checks."""
    garbage = "hello random text nothing about fabrics or invoices xyz 999999"
    results = report_checks(garbage, adaeze_checks)
    assert not any(r["matched"] for r in results)


def test_checks_word_numbers_stretch_goal(adaeze_checks):
    """Verify spelled-out numbers match the corresponding checks."""
    text_130 = "Leaving one hundred and thirty thousand naira in cash reserve."
    results_130 = report_checks(text_130, adaeze_checks)
    matched_130 = {r["id"]: r["matched"] for r in results_130}
    assert matched_130["K3"] is True

    text_350 = "The invoice of three hundred and fifty thousand naira is overdue."
    results_350 = report_checks(text_350, adaeze_checks)
    matched_350 = {r["id"]: r["matched"] for r in results_350}
    assert matched_350["K2"] is True
