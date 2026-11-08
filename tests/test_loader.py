"""Tests for scenario loading, API endpoints, and database schema."""

import json
import sqlite3
import pytest
from fastapi.testclient import TestClient
import config
from db import init_db, get_connection
from app.loader import list_scenarios, load_scenario, validate_scenario
from main import app


@pytest.fixture
def test_db(tmp_path):
    """Create a temporary SQLite database for testing."""
    db_file = tmp_path / "test_sabilab.db"
    init_db(db_file)
    return db_file


def test_load_scenario_json():
    """Verify that scenarios/adaeze.json loads and contains all required Build Spec fields."""
    scenario_path = config.SCENARIOS_DIR / "adaeze.json"
    assert scenario_path.exists()

    with open(scenario_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Required fields from Build Spec section 2
    required_fields = [
        "id", "title", "status", "student_role", "roster",
        "owner", "facts", "timeline", "twist",
        "task", "checks", "approaches", "register", "variant_b"
    ]
    for field in required_fields:
        assert field in data, f"Missing required field: {field}"

    # Verify scenario identity and role
    assert data["id"] == "adaeze"
    assert data["title"] == "Adaeze’s Fabrics"
    assert data["status"] == "full"
    assert data["student_role"] == "Accountant"

    # Verify Scenario 1 ground truth facts
    facts = {f["key"]: f["value"] for f in data["facts"]}
    assert facts["cash_on_hand"] == "₦480,000"
    assert facts["overdue_kano_invoice"] == "₦350,000"
    assert facts["cash_remaining_if_paid_in_full"] == "₦130,000"
    assert facts["mrs_bello_discount_request"] == "20%"

    # Validate schema validator
    validate_scenario(data)


def test_list_scenarios_function():
    """Verify list_scenarios returns Adaeze's Fabrics."""
    scenarios = list_scenarios()
    assert len(scenarios) >= 1
    adaeze = next((s for s in scenarios if s["id"] == "adaeze"), None)
    assert adaeze is not None
    assert adaeze["title"] == "Adaeze’s Fabrics"
    assert adaeze["student_role"] == "Accountant"


def test_get_scenarios_endpoint():
    """Verify GET /scenarios endpoint returns 200 OK and Adaeze's Fabrics."""
    client = TestClient(app)
    response = client.get("/scenarios")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    adaeze = next((s for s in data if s["id"] == "adaeze"), None)
    assert adaeze is not None
    assert adaeze["title"] == "Adaeze’s Fabrics"


def test_db_tables_created(test_db):
    """Verify that all 12 tables from Build Spec Section 3 exist in SQLite."""
    conn = sqlite3.connect(str(test_db))
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {row[0] for row in cursor.fetchall()}
    conn.close()

    expected_tables = {
        "users", "sessions", "participants", "messages",
        "tasks", "readings", "clarifications", "scores",
        "results", "badges", "cards", "events"
    }
    for table in expected_tables:
        assert table in tables, f"Expected table '{table}' not found in database."
