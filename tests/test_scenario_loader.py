"""Unit tests for Phase 1: Scenario Loader and Verification Checks."""

import pytest
from scenario_loader import (
    list_scenarios,
    load_scenario,
    normalize_text_for_checks,
    run_checks,
    _validate_scenario,
)


def test_list_scenarios():
    """Verify that list_scenarios returns the in-scope scenario."""
    scenarios = list_scenarios()
    assert len(scenarios) >= 1
    ids = [s["id"] for s in scenarios]
    assert "adaezes_fabrics" in ids
    adaeze = next(s for s in scenarios if s["id"] == "adaezes_fabrics")
    assert adaeze["title"] == "Adaeze’s Fabrics"
    assert adaeze["status"] == "full"
    assert adaeze["student_role"] == "Accountant"


def test_load_scenario():
    """Verify loading full configuration for Adaeze's Fabrics."""
    scenario = load_scenario("adaezes_fabrics")
    assert scenario["id"] == "adaezes_fabrics"
    assert scenario["student_role"] == "Accountant"
    assert len(scenario["roster"]) == 4

    # Verify roster teammate structure
    sales = next(t for t in scenario["roster"] if t["id"] == "sales")
    assert sales["name"] == "Emeka"
    assert "Mrs Bello" in sales["opening_line"]
    assert "Kano" in sales["reply_after_twist"]

    # Verify owner and client
    assert scenario["owner"]["name"] == "Adaeze"
    assert "Mrs Bello wants 20% off" in scenario["owner"]["scripted_lines"]["opening"]
    assert scenario["client"]["name"] == "Mrs Bello"

    # Verify facts
    facts = {f["key"]: f["value"] for f in scenario["facts"]}
    assert facts["cash_on_hand"] == "₦480,000"
    assert facts["overdue_kano_invoice"] == "₦350,000"
    assert facts["cash_remaining_if_paid_in_full"] == "₦130,000"

    # Verify twist and task
    assert "cancelled our supply" in scenario["twist"]["text"]
    assert "Write your recommendation" in scenario["task"]["prompt"]

    # Verify checks and register
    assert len(scenario["checks"]) >= 5
    assert "Adaeze" in scenario["register"]
    assert "variant_b" in scenario


def test_load_nonexistent_scenario():
    """Verify loading an invalid scenario ID raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_scenario("non_existent_scenario")


def test_validate_scenario_missing_field():
    """Verify validation raises ValueError if a required field is missing."""
    with pytest.raises(ValueError, match="Missing required field"):
        _validate_scenario({"id": "test", "title": "Test"})


def test_normalize_text():
    """Verify text normalization removes spaces, commas, naira symbols and expands 'k'."""
    assert normalize_text_for_checks("₦480,000") == "480000"
    assert normalize_text_for_checks("350k") == "350000"
    assert normalize_text_for_checks("Pay 150k today") == "pay150000today"
    assert normalize_text_for_checks("20% discount") == "20%discount"


def test_run_checks_matching():
    """Verify code check reports which figures appear in student task."""
    scenario = load_scenario("adaezes_fabrics")
    sample_text = (
        "I recommend paying Kano Textiles ₦150k today to resume raw fabric supply, "
        "leaving ₦330,000 in cash. For Mrs Bello, we should limit her discount to 10% "
        "because our cash is ₦480,000 and we still owe ₦350,000."
    )
    results = run_checks(sample_text, scenario["checks"])
    matched_ids = {r["id"] for r in results if r["matched"]}

    assert "K1" in matched_ids  # 480,000
    assert "K2" in matched_ids  # 350,000
    assert "K4" in matched_ids  # 10%
    assert "K5" in matched_ids  # 150k
